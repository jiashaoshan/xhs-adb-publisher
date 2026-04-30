#!/usr/bin/env python3
"""
xhs-adb-publisher 多设备批量发布入口

功能：
  - 指定多台 Android 设备的 serial（或用 adb devices 自动发现）
  - 每个设备绑定独立的小红书账号
  - 并发执行发布任务（每设备独立线程 + 随机错峰，降低风控）
  - 支持设备-账号映射配置

用法：
  # 指定设备列表（逗号分隔）
  python3 batch_publisher.py --devices "R3CN8A,5SDF8B" \
    --product-url "https://ai.hcrzx.com" --product-name "AI智能助手"

  # 使用配置文件
  python3 batch_publisher.py --config config/devices.json \
    --product-url "https://ai.hcrzx.com"

  # 自动发现 adb devices（所有已连接设备）
  python3 batch_publisher.py --auto-discover \
    --product-url "https://ai.hcrzx.com"

  # 指定并发数（默认不限制，全部同时）
  python3 batch_publisher.py --devices "R3CN8A,5SDF8B" --concurrency 2 \
    --product-url "https://ai.hcrzx.com"
"""
import argparse, json, logging, os, random, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.absolute()
DATA_DIR = SCRIPT_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_DIR = SCRIPT_DIR / "config"

log_file = DATA_DIR / f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(str(log_file), encoding="utf-8")],
)
logger = logging.getLogger("batch-publisher")

sys.path.insert(0, str(SCRIPT_DIR / "scripts"))
from xhs_article_publisher import run as gen_article

def discover_devices() -> list:
    """通过 adb devices 自动发现已连接设备"""
    import subprocess
    result = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=10)
    devices = []
    for line in result.stdout.strip().split("\n")[1:]:  # 跳过第一行 "List of devices attached"
        parts = line.strip().split()
        if len(parts) == 2 and parts[1] == "device":
            devices.append(parts[0])
    logger.info(f"自动发现 {len(devices)} 台设备: {devices}")
    return devices

def load_device_config(path: str) -> list:
    """加载设备配置文件，格式：
    [
      {"serial": "R3CN8A", "note": "华为P40-账号A"},
      {"serial": "5SDF8B", "note": "小米13-账号B"}
    ]
    """
    fp = Path(path)
    if not fp.exists():
        raise FileNotFoundError(f"设备配置文件不存在: {path}")
    return json.loads(fp.read_text())

def generate_and_publish(serial: str, product_url: str, product_name: str,
                         target_audience: str, dry_run: bool = False) -> dict:
    """
    单设备单次完整任务：LLM 生成 → ADB 发布
    供线程池调用。
    """
    task_id = f"[{serial}]"
    logger.info(f"{task_id} 开始任务...")
    start = time.time()

    # 错峰启动（每个设备启动差 1-3 秒，避免同时操作被检测）
    stagger = random.uniform(1, 3)
    time.sleep(stagger)

    try:
        # 步骤1: LLM 生成文章
        logger.info(f"{task_id} LLM 生成文章...")
        article = gen_article(
            product_url=product_url,
            product_name=product_name,
            target_audience=target_audience,
        )
        logger.info(f"{task_id} 文章生成完成: {article['title']} "
                     f"(编辑器 {len(article['editor_body'])}字, "
                     f"小红书正文 {len(article['xhs_body'])}字)")

        if dry_run:
            elapsed = time.time() - start
            logger.info(f"{task_id} dry-run 模式，跳过发布")
            return {
                "serial": serial, "status": "dry_run",
                "title": article["title"], "elapsed_s": round(elapsed, 1)
            }

        # 步骤2: ADB 发布（通过 phone_controller 的 publish_article）
        from phone_controller import publish_article
        result = publish_article(
            serial=serial,
            product_url=product_url,
            article=article,
        )
        result["elapsed_s"] = round(time.time() - start, 1)
        logger.info(f"{task_id} 完成: {result['status']} ({result.get('elapsed_s', 0)}s)")
        return result

    except Exception as e:
        elapsed = time.time() - start
        logger.error(f"{task_id} 任务失败 ({elapsed:.1f}s): {e}")
        return {
            "serial": serial, "status": "failed",
            "error": str(e), "elapsed_s": round(elapsed, 1)
        }

def main():
    parser = argparse.ArgumentParser(description="小红书多设备批量发布器")
    parser.add_argument("--devices", help="设备序列号（逗号分隔）")
    parser.add_argument("--config", help="设备配置文件路径")
    parser.add_argument("--auto-discover", action="store_true", help="自动发现 adb 设备")
    parser.add_argument("--product-url", required=True, help="产品链接")
    parser.add_argument("--product-name", default="", help="产品名称")
    parser.add_argument("--target-audience", default="", help="目标受众")
    parser.add_argument("--concurrency", type=int, default=0,
                        help="最大并发数（0=不限制）")
    parser.add_argument("--dry-run", action="store_true", help="仅生成不发布")
    parser.add_argument("--output", help="结果保存路径（JSON）")
    args = parser.parse_args()

    # 确定设备列表
    devices = []
    if args.devices:
        devices = [d.strip() for d in args.devices.split(",") if d.strip()]
    elif args.config:
        configs = load_device_config(args.config)
        devices = [d["serial"] for d in configs]
    elif args.auto_discover:
        devices = discover_devices()
    else:
        parser.print_help()
        print("\n错误: 请通过 --devices, --config 或 --auto-discover 指定设备")
        sys.exit(1)

    if not devices:
        print("错误: 未发现任何设备")
        sys.exit(1)

    logger.info(f"========== 批量发布启动 ==========")
    logger.info(f"设备: {devices}")
    logger.info(f"产品: {args.product_name or args.product_url}")
    logger.info(f"并发: {'无限制' if args.concurrency == 0 else args.concurrency}")
    logger.info(f"模式: {'模拟(不发布)' if args.dry_run else '正式发布'}")
    print()

    # 并发执行
    max_workers = args.concurrency or len(devices)
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                generate_and_publish,
                serial=d, product_url=args.product_url,
                product_name=args.product_name, target_audience=args.target_audience,
                dry_run=args.dry_run,
            ): d for d in devices
        }

        for future in as_completed(futures):
            serial = futures[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                logger.error(f"[{serial}] 线程异常: {e}")
                results.append({"serial": serial, "status": "error", "error": str(e)})

    # 汇总结果
    published = [r for r in results if r.get("status") == "published"]
    failed = [r for r in results if r.get("status") == "failed"]
    dry_run_results = [r for r in results if r.get("status") == "dry_run"]

    print()
    logger.info("========== 批量发布结果 ==========")
    logger.info(f"✅ 发布成功: {len(published)}/{len(devices)}")
    logger.info(f"❌ 发布失败: {len(failed)}/{len(devices)}")
    if dry_run_results:
        logger.info(f"🔍 模拟模式: {len(dry_run_results)}/{len(devices)}")

    for r in failed:
        logger.warning(f"  ❌ {r['serial']}: {r.get('error', '未知错误')}")

    # 保存结果
    report = {
        "timestamp": datetime.now().isoformat(),
        "product_url": args.product_url,
        "total": len(devices),
        "published": len(published),
        "failed": len(failed),
        "dry_run": len(dry_run_results),
        "results": results,
    }

    output_path = args.output or str(DATA_DIR / f"batch_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    Path(output_path).write_text(json.dumps(report, ensure_ascii=False, indent=2))
    logger.info(f"结果报告已保存: {output_path}")

    # 非零退出码表示有失败
    sys.exit(0 if len(failed) == 0 else 1)

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
小红书文章发布技能 (xhs-adb-publisher) — 统一编排入口

功能:
  1. 发布文章：LLM 生成 → Pexels 配图 → ADB 发布长文
  2. 评论区获客 (TODO)
  3. 写想法 / 写长文 (ADB 直发)

命令行:
  # 完整发布流程（推荐）
  python3 xhs_adb_publisher.py --publish --product-url "https://ai.hcrzx.com"

  # 仅生成不发布
  python3 xhs_adb_publisher.py --publish --dry-run --product-url "https://ai.hcrzx.com"

  # 直接写想法（跳过LLM直接发）
  python3 xhs_adb_publisher.py --write-thought "正文内容" --title "标题"

  # 直接写长文
  python3 xhs_adb_publisher.py --write-long "编辑器正文" --xhs-body "小红书正文" --title "标题"
"""
import argparse, json, logging, sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.absolute()
SKILL_DIR = SCRIPT_DIR
DATA_DIR = SKILL_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

log_file = DATA_DIR / f"publisher_{datetime.now().strftime('%Y%m%d')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(str(log_file), encoding="utf-8")],
)

sys.path.insert(0, str(SCRIPT_DIR / "scripts"))
from phone_controller import xie_xie_fa, xie_chang_wen

def banner():
    print()
    print("  ╔══════════════════════════════════════╗")
    print("  ║   小红书文章发布技能                  ║")
    print("  ║   LLM → Pexels → ADB 全自动发布      ║")
    print("  ╚══════════════════════════════════════╝")
    print()

def cmd_publish(args):
    """发布文章: LLM → Pexels → ADB"""
    from xhs_article_publisher import run
    result = run(
        product_url=args.product_url,
        product_name=args.product_name or "",
        target_audience=args.target_audience or "",
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result

def cmd_write_thought(args):
    """直接写想法"""
    xie_xie_fa(args.content, args.title or "测试标题")
    print(f"✅ 写想法已发布: {args.content[:20]}")

def cmd_write_long(args):
    """直接写长文"""
    xie_chang_wen(args.editor_body, args.xhs_body or "", args.title or "")
    print(f"✅ 写长文已发布")

def main():
    banner()
    parser = argparse.ArgumentParser(description="小红书文章发布技能")
    
    # 发布模式
    parser.add_argument("--publish", action="store_true", help="完整发布: LLM→Pexels→ADB")
    parser.add_argument("--product-url", help="产品链接")
    parser.add_argument("--product-name", help="产品名称（可选）")
    parser.add_argument("--target-audience", help="目标受众（可选）")
    parser.add_argument("--dry-run", action="store_true", help="仅生成不发布")
    
    # 直发模式
    parser.add_argument("--write-thought", help="直接写想法（正文）")
    parser.add_argument("--write-long", help="直接写长文（编辑器正文）")
    parser.add_argument("--xhs-body", help="小红书正文")
    parser.add_argument("--title", help="标题")
    parser.add_argument("--content", help="正文内容（写想法用）")
    
    args = parser.parse_args()
    
    if args.publish:
        cmd_publish(args)
    elif args.write_thought:
        cmd_write_thought(args)
    elif args.write_long:
        cmd_write_long(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()

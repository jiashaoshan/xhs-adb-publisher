"""
小红书图文日常发布模块

功能:
  1. TrendRadar MCP 获取 juejin 热点新闻（前2条）
  2. 打开文章链接，获取全文内容
  3. LLM 改写文章（取精髓、融入自己的话）
  4. 生成封面图（豆包）
  5. ADB 发布图文到小红书
"""
import json, logging, os, sys, subprocess
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.absolute()
SKILL_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from xhs_llm import call_llm_json, call_llm
from phone_controller import publish_image_article

logger = logging.getLogger("xhs-daily-image")

TEMPORARY_FILES_DIR = SKILL_DIR / "data" / "xhs_images"
DATA_DIR = SKILL_DIR / "data"
PUBLISHED_FILE = DATA_DIR / "published-daily-images.json"

TRENDRADAR_MCP_URL = "http://100.111.235.91:3333/mcp"

MAX_TITLE_LEN = 20
MAX_BODY_LEN = 1000
MIN_BODY_LEN = 300
DAILY_SERIAL = "6DHQR8MJMVH6AAMZ"  # 图文日常发布专用设备

# ============================================================
# 工具函数
# ============================================================

def _smart_truncate_title(title: str) -> str:
    """智能截断标题，避免截在英文单词/文件扩展名/标点中间"""
    if len(title) <= MAX_TITLE_LEN:
        return title.strip()

    truncated = title[:MAX_TITLE_LEN].strip()

    # 如果截断位置在英文字母中间，往前找到单词/缩写边界
    if truncated and truncated[-1].isascii() and truncated[-1].isalpha():
        cut = len(truncated) - 1
        while cut > 0 and truncated[cut].isascii() and (truncated[cut].isalpha() or truncated[cut] == '.'):
            cut -= 1
        if cut > MAX_TITLE_LEN - 5:
            truncated = truncated[:cut+1]

    # 去掉末尾的句号、逗号等无意义符号
    truncated = truncated.rstrip('，。,.')

    return truncated.strip()

HASHTAG_POOL = [
    "AI编程", "技术分享", "程序员日常", "AI工具", "开发技巧",
    "效率提升", "前端开发", "代码规范", "程序员必备", "科技改变生活",
    "自学编程", "编程入门", "技术干货", "AI写代码", "开发者",
    "Android开发", "工具推荐", "学习打卡", "职场干货", "提升效率",
]

def _generate_hashtags(title: str, body: str) -> str:
    """根据标题和内容生成相关的话题标签"""
    text = title + body
    matched = []
    for tag in HASHTAG_POOL:
        keywords = tag.replace("#", "")
        if keywords in text:
            matched.append(tag)
        elif tag == "AI编程" and ("AI" in text or "代码" in text):
            matched.append(tag)
        elif tag == "Android开发" and ("Android" in text or "android" in text.lower()):
            matched.append(tag)
        elif tag == "效率提升" and ("效率" in text or "提速" in text or "快" in title):
            matched.append(tag)

    if len(matched) < 3:
        fallback = ["技术分享", "程序员日常", "科技改变生活"]
        for f in fallback:
            if f not in matched:
                matched.append(f)
    if "AI编程" not in matched and ("AI" in text or "代码" in text):
        matched.insert(0, "AI编程")

    return "\n\n" + " ".join(f"#{t}" for t in matched[:5])


def _strip_existing_hashtags(body: str) -> str:
    """去掉正文末尾 LLM 自带的话题标签行，避免重复"""
    lines = body.rstrip().split("\n")
    # 从末尾向上去掉所有纯标签行（以 # 开头的行）
    while lines and lines[-1].strip().startswith("#"):
        lines.pop()
    return "\n".join(lines).rstrip()

# ============================================================
# TrendRadar MCP 客户端
# ============================================================

def _mcp_init(url: str = TRENDRADAR_MCP_URL) -> str:
    import requests
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream, application/json",
    }
    no_proxy = {"http": None, "https": None}
    r = requests.post(url, json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "xhs-daily-image", "version": "1.0"}
        }
    }, headers=headers, proxies=no_proxy, timeout=10)
    sid = r.headers.get("mcp-session-id")
    if not sid:
        raise RuntimeError("MCP 初始化失败")
    headers["Mcp-Session-Id"] = sid
    requests.post(url, json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                  headers=headers, proxies=no_proxy, timeout=5)
    return sid

def _mcp_call(url: str, sid: str, tool_name: str, args: dict) -> dict:
    import requests
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream, application/json",
        "Mcp-Session-Id": sid,
    }
    no_proxy = {"http": None, "https": None}
    r = requests.post(url, json={
        "jsonrpc": "2.0", "id": 99, "method": "tools/call",
        "params": {"name": tool_name, "arguments": args}
    }, headers=headers, proxies=no_proxy, timeout=60)
    for line in r.text.split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            try:
                d = json.loads(line[6:])
                if "result" in d:
                    for c in d["result"].get("content", []):
                        t = c.get("text", "")
                        if t:
                            try: return json.loads(t)
                            except: return {"raw_text": t}
            except: pass
    return None

def _mcp_close(url: str, sid: str):
    import requests
    try: requests.delete(url, headers={"Mcp-Session-Id": sid}, timeout=5)
    except: pass

# ============================================================
# 步骤1: 获取 juejin 热点
# ============================================================

def fetch_juejin_hotspots(limit: int = 2) -> list:
    logger.info("📡 连接 TrendRadar MCP...")
    sid = _mcp_init()
    try:
        logger.info(f"🔍 获取 juejin 热点 (limit={limit})...")
        result = _mcp_call(TRENDRADAR_MCP_URL, sid, "get_latest_news", {
            "platforms": ["juejin"], "limit": limit, "include_url": True,
        })
        if not result or not isinstance(result, dict):
            logger.warning("TrendRadar 返回空数据")
            return []
        items = result.get("data", [])
        logger.info(f"  获取到 {len(items)} 条 juejin 热点")
        return items
    finally:
        _mcp_close(TRENDRADAR_MCP_URL, sid)

# ============================================================
# 步骤2: 读取文章内容
# ============================================================

def fetch_article_contents(articles: list) -> list:
    sid = _mcp_init()
    enriched = []
    try:
        for i, article in enumerate(articles):
            url = article.get("url", "")
            title = article.get("title", "")
            logger.info(f"📖 [{i+1}/{len(articles)}] 读取: {title[:40]}...")
            if not url:
                enriched.append({**article, "content": title})
                continue
            result = _mcp_call(TRENDRADAR_MCP_URL, sid, "read_article", {
                "url": url, "timeout": 30,
            })
            content = ""
            if result:
                if isinstance(result, dict):
                    data = result.get("data", {})
                    content = data.get("content", "") or data.get("text", "") or result.get("content", "") or result.get("raw_text", "")
                elif isinstance(result, str):
                    content = result
            if not content or len(content) < 200:
                logger.info(f"  read_article 返回内容不足 ({len(content)}字)，重试 batch 模式...")
                result2 = _mcp_call(TRENDRADAR_MCP_URL, sid, "read_articles_batch", {
                    "urls": [url], "timeout": 30,
                })
                if result2 and isinstance(result2, dict):
                    data2 = result2.get("data", {})
                    articles_list = data2.get("articles", [])
                    if articles_list and len(articles_list) > 0:
                        content = articles_list[0].get("content", "")
                    elif not content:
                        content = data2.get("content", "") or result2.get("content", "") or ""
            if not content or len(content) < 200:
                logger.warning(f"  ⚠️ 无法读取文章内容，使用标题作为素材")
                content = title
            if len(content) > 5000:
                content = content[:5000]
            enriched.append({**article, "content": content})
            logger.info(f"  ✅ 读取完成 ({len(content)} 字)")
    finally:
        _mcp_close(TRENDRADAR_MCP_URL, sid)
    return enriched

# ============================================================
# 步骤3: LLM 改写文章
# ============================================================

REWRITE_PROMPT = """你是一个小红书科技博主，擅长把技术文章改写成通俗易懂、有个人观点的小红书笔记。

## 原文信息
- 标题：{title}
- 来源：{platform}

## 原文内容
{content}

## 改写要求

1. **用自己的话重写**，不要直接复制原文
2. **取精髓**：提炼原文最核心的观点/技术/方法，去掉啰嗦的铺垫
3. **加入个人视角**：
   - "我试了一下，确实好用"
   - "说实话，这个方案比xxx强太多了"
   - "做了这么多年xx，第一次见到这种思路"
4. **口语化**，像跟朋友聊天一样
5. **用 Emoji 增加表现力**：
   - 用 🎯💡🔥😱✨🤯 等表情符号分隔段落和开头，让内容更活泼
   - 每个要点前可以放一个相关 emoji（如 💻 代码、📱 工具、⏰ 效率）
   - 情绪强烈的句子前加表情（如 "😱 说实话我也被震惊了"、"😂 试了一下笑死我了"）
   - 不要过度使用，每段 1-2 个即可，保持自然
6. **结构**：
    - 开头：一句话钩子（制造好奇心）
    - 中间：核心内容（2-3个要点，每个100-150字）
    - 结尾：个人总结 + 互动引导
7. **字数 300-800 字**（不包括话题标签，标签会另外加）
8. **不要加**：产品链接、二维码、"关注我"等营销话术
9. 每段不超过 3 行，手机阅读友好
10. **标题 ≤18 字**，简洁有力，不要带英文文件扩展名（如 .md）

## 输出格式
纯 JSON：
{{
  "title": "标题（≤18字，小红书风格）",
  "body": "改写后的正文"
}}
"""

REWRITE_NO_CONTENT_PROMPT = """你是一个小红书科技博主，擅长根据技术话题创作通俗易懂、有个人观点的小红书笔记。

## 参考标题
{title}

说明：原文无法抓取，请根据标题主题，结合你对该领域的技术知识，创作一篇原创小红书笔记。

## 创作要求

1. **基于标题主题自由发挥**，融入你的技术知识
2. **加入个人视角**：
   - "我最近试了一下，发现..."
   - "说实话，这个方案比传统做法强太多了"
   - "做了这么多年开发，第一次见到这种思路"
   - "其实原理很简单，但90%的人都忽略了..."
3. **口语化**，像跟朋友聊天一样，用"你"和"我"
4. **用 Emoji 增加表现力**：
   - 用 🎯💡🔥😱✨🤯 等表情符号分隔段落和开头
   - 每个要点前可以放一个相关 emoji
   - 情绪强烈的句子前加表情（如 "😱 说实话我也被震惊了"）
   - 每段 1-2 个即可，保持自然
5. **结构**：
    - 开头：一句话钩子（制造好奇心，关联标题主题）
    - 中间：核心内容（2-3个要点，每个100-150字，结合具体场景）
    - 结尾：个人总结 + 互动引导（"你们有没有遇到过？评论区聊聊"）
6. **字数 300-800 字**（不包括话题标签，标签会另外加）
7. **不要加**：产品链接、二维码、"关注我"等营销话术
8. 每段不超过 3 行，手机阅读友好
9. **标题 ≤18 字**，简洁有力

## 输出格式
纯 JSON：
{{
  "title": "标题（≤18字，小红书风格，有吸引力）",
  "body": "改写后的正文"
}}
"""

def rewrite_article(article: dict) -> dict:
    title = article.get("title", "")
    platform = article.get("platform", "juejin")
    content = article.get("content", "")
    logger.info(f"✍️ LLM 改写: {title[:30]}...")

    if len(content) < 200:
        logger.info(f"  原文内容不足 ({len(content)}字)，切换无原文创作模式")
        prompt = REWRITE_NO_CONTENT_PROMPT.format(title=title)
    else:
        prompt = REWRITE_PROMPT.format(title=title, platform=platform, content=content)

    try:
        result = call_llm_json(
            system_prompt="你是一个小红书科技博主，擅长技术内容通俗化改写。严格JSON格式输出。",
            user_prompt=prompt, temperature=0.7, max_tokens=4096,
        )
        new_title = result.get("title", title[:MAX_TITLE_LEN]).strip()
        new_body = result.get("body", "").strip()
        # 智能标题截断
        new_title = _smart_truncate_title(new_title)
        # 去掉 LLM 自带的话题标签（如果有），追加统一生成的话题标签
        new_body = _strip_existing_hashtags(new_body)
        new_body = new_body + _generate_hashtags(new_title, new_body)
        body_len = len(new_body)
        if body_len < MIN_BODY_LEN:
            logger.warning(f"  正文 {body_len} 字 < {MIN_BODY_LEN}")
        logger.info(f"  ✅ 改写完成: {len(new_title)}字标题, {body_len}字正文")
        return {"title": new_title, "body": new_body, "source_title": title, "source_url": article.get("url", "")}
    except Exception as e:
        logger.error(f"  ❌ 改写失败: {e}")
        short_title = _smart_truncate_title(title[:MAX_TITLE_LEN]) if len(title) > MAX_TITLE_LEN else title
        short_body = content[:MAX_BODY_LEN] + _generate_hashtags(title, content[:200])
        return {"title": short_title, "body": short_body, "source_title": title, "source_url": article.get("url", "")}

# ============================================================
# 步骤4: 生成封面图
# ============================================================

def generate_cover_image(title: str, body: str, output_dir: Path) -> str:
    """调用豆包生成封面图"""
    doubao_script = Path.home() / ".openclaw/workspace/skills/doubao-image-create/scripts/generate.js"
    doubao_output = Path.home() / ".openclaw/workspace/skills/doubao-image-create/output/image.jpg"
    cover_template = SKILL_DIR / "templates" / "cover-prompt-daily.md"

    if not doubao_script.exists():
        raise FileNotFoundError(f"豆包生成脚本未找到: {doubao_script}")

    output_dir.mkdir(parents=True, exist_ok=True)
    cover_path = output_dir / "cover.jpg"

    # 加载模板
    if cover_template.exists():
        template = cover_template.read_text(encoding="utf-8")
    else:
        template = '帮我生成图片：小红书科技类封面图，现代简约风格，3:4比例。标题：{{article_title}}\n副标题：{{article_subtitle}}'

    # 提取副标题（正文第一句，30字内）
    first_line = body.split("\n")[0].strip()
    subtitle = first_line[:30] if len(first_line) > 30 else first_line
    # 去掉常见开头符号
    subtitle = subtitle.lstrip("✨💡🎯🔥💥📌").strip()

    # 填充占位符
    cover_prompt = template.replace("{{article_title}}", title)
    cover_prompt = cover_prompt.replace("{{article_subtitle}}", subtitle)

    logger.info(f"🎨 生成封面图: {title[:30]}...")
    cmd = ["node", str(doubao_script), cover_prompt, "--size", "1024", "--watermark", "false"]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
        if doubao_output.exists():
            import shutil
            shutil.copy2(str(doubao_output), str(cover_path))
            logger.info(f"  ✅ 封面图生成: {cover_path}")
            return str(cover_path)
        else:
            raise FileNotFoundError(f"豆包未生成图片: {doubao_output}")
    except Exception as e:
        logger.error(f"  ❌ 封面图生成失败: {e}")
        raise

# ============================================================
# 步骤5: 推送图片到手机
# ============================================================

def push_images_to_device(image_paths: list, serial: str = None) -> bool:
    serial_arg = f"-s {serial}" if serial else ""
    remote_dir = "/sdcard/DCIM/Camera"
    for img_path in image_paths:
        filename = Path(img_path).name
        remote_path = f"{remote_dir}/{filename}"
        cmd = f"adb {serial_arg} push \"{img_path}\" \"{remote_path}\""
        logger.info(f"📱 推送图片 ({serial or 'default'}): {filename}")
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                logger.error(f"推送失败: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"推送异常: {e}")
            return False
    refresh_cmd = f"adb {serial_arg} shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file://{remote_dir}"
    subprocess.run(refresh_cmd, shell=True, capture_output=True)
    logger.info(f"✅ 已推送 {len(image_paths)} 张图片")
    return True

# ============================================================
# 数据持久化
# ============================================================

def save_published(entry: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    records = []
    if PUBLISHED_FILE.exists():
        try: records = json.loads(PUBLISHED_FILE.read_text())
        except: pass
    records.append(entry)
    PUBLISHED_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2))

# ============================================================
# 主流程
# ============================================================

def run(dry_run: bool = False, serial: str = None) -> dict:
    """
    完整图文日常发布流程

    Args:
        dry_run: 仅生成不发布
        serial: ADB 设备串号（默认使用 DAILY_SERIAL）
    """
    result = {"status": "started", "steps": []}
    serial = serial or DAILY_SERIAL
    logger.info(f"📱 目标设备: {serial}")

    # ═══ 步骤1 ═══
    logger.info("═" * 50)
    logger.info("步骤1/5: 获取 juejin 热点新闻...")
    hotspots = fetch_juejin_hotspots(limit=2)
    if not hotspots:
        result["status"] = "failed"
        result["error"] = "未获取到 juejin 热点"
        return result
    result["steps"].append({"step": "fetch_hotspots", "count": len(hotspots), "status": "ok"})
    for i, h in enumerate(hotspots):
        logger.info(f"  [{i+1}] {h.get('title', '')[:50]}")

    # ═══ 步骤2 ═══
    logger.info("\n" + "═" * 50)
    logger.info("步骤2/5: 读取文章全文...")
    enriched = fetch_article_contents(hotspots)
    result["steps"].append({"step": "read_articles", "count": len(enriched), "status": "ok"})

    # ═══ 步骤3 ═══
    logger.info("\n" + "═" * 50)
    logger.info("步骤3/5: LLM 改写文章...")
    rewritten = []
    for i, article in enumerate(enriched):
        logger.info(f"\n  [{i+1}/{len(enriched)}]")
        rw = rewrite_article(article)
        rewritten.append(rw)
    result["articles"] = rewritten
    result["steps"].append({"step": "rewrite", "count": len(rewritten), "status": "ok"})

    if dry_run:
        result["status"] = "dry_run"
        logger.info("\n📋 干运行模式，跳过发布")
        return result

    # ═══ 步骤4-5 ═══
    logger.info("\n" + "═" * 50)
    logger.info("步骤4-5/5: 生成封面图 + ADB 发布...")
    image_dir = TEMPORARY_FILES_DIR
    published = []

    for i, article in enumerate(rewritten):
        title = article["title"]
        body = article["body"]
        logger.info(f"\n  [{i+1}/{len(rewritten)}] 发布: {title} ({serial})")

        for f in image_dir.glob("*.jpg"):
            try: f.unlink()
            except: pass

        try:
            cover_path = generate_cover_image(title, body, image_dir)
            if not push_images_to_device([cover_path], serial):
                result["steps"].append({"step": f"publish_{i+1}", "status": "failed", "error": "图片推送失败"})
                continue

            xhs_body = body[:MAX_BODY_LEN] if len(body) > MAX_BODY_LEN else body
            publish_image_article(serial=serial, title=title[:MAX_TITLE_LEN], xhs_body=xhs_body, image_count=1)

            record = {
                "title": title, "source_title": article["source_title"],
                "source_url": article["source_url"], "published_at": datetime.now().isoformat(),
                "type": "图文日常发布", "body_chars": len(body), "device": serial,
            }
            save_published(record)
            published.append(record)
            logger.info(f"  ✅ 发布成功: {title}")
            result["steps"].append({"step": f"publish_{i+1}", "status": "ok"})
        except Exception as e:
            logger.error(f"  ❌ 发布失败: {e}")
            result["steps"].append({"step": f"publish_{i+1}", "status": "failed", "error": str(e)})

    result["published"] = published
    result["status"] = "published" if published else "failed"
    return result


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", handlers=[logging.StreamHandler()])
    parser = argparse.ArgumentParser(description="图文日常发布：TrendRadar juejin热点→LLM改写→ADB发布")
    parser.add_argument("--dry-run", action="store_true", help="仅生成不发布")
    parser.add_argument("--publish", action="store_true", help="生成并发布")
    parser.add_argument("--serial", "-s", help=f"ADB设备串号（默认: {DAILY_SERIAL}）")
    args = parser.parse_args()
    result = run(dry_run=args.dry_run, serial=args.serial)
    print(json.dumps(result, ensure_ascii=False, indent=2))

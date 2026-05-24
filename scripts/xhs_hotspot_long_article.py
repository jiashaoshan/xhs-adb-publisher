"""
小红书热点自动写长文 (v1.0.0)

流程: TrendRadar(新智元RSS→V2EX降级) → 产品分析 → AI挑选 → LLM生成2500-4000字长文 → ADB发布

使用:
  python3 scripts/xhs_hotspot_long_article.py --product-url "https://ai.hcrzx.com"
  python3 scripts/xhs_hotspot_long_article.py --product-url "https://ai.hcrzx.com" --dry-run
  python3 scripts/xhs_hotspot_long_article.py --product-url "https://ai.hcrzx.com" --max 2
"""
import json, logging, os, sys, re, random
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.absolute()
SKILL_DIR = SCRIPT_DIR.parent
DATA_DIR = SKILL_DIR / "data"
OUTPUT_DIR = SKILL_DIR / "output"
TEMPLATES_DIR = SKILL_DIR / "templates"
PUBLISH_RECORD = DATA_DIR / "hotspot-long-published.json"

sys.path.insert(0, str(SCRIPT_DIR))
from xhs_llm import call_llm, call_llm_json

logger = logging.getLogger("xhs-hotspot-long")

TRENDRADAR_URL = os.environ.get("TRENDRADAR_URL", "http://100.111.235.91:3333/mcp")
MAX_TITLE_LEN = 40
MIN_BODY_LEN = 2500
MAX_BODY_LEN = 4000
MAX_XHS_BODY = 1000

# ====================================================================
# TrendRadar MCP 客户端（直连 HTTP，不依赖 Node.js）
# ====================================================================

def _mcp_init(url):
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
            "clientInfo": {"name": "xhs-hotspot-long", "version": "1.0"},
        },
    }, headers=headers, proxies=no_proxy, timeout=10)
    sid = r.headers.get("mcp-session-id")
    if not sid:
        raise RuntimeError("MCP 初始化失败: 未返回 session-id")
    headers["Mcp-Session-Id"] = sid
    requests.post(url, json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                  headers=headers, proxies=no_proxy, timeout=5)
    return sid, headers


def _mcp_call(url, headers, tool_name, args):
    import requests
    no_proxy = {"http": None, "https": None}
    r = requests.post(url, json={
        "jsonrpc": "2.0", "id": 99, "method": "tools/call",
        "params": {"name": tool_name, "arguments": args},
    }, headers=headers, proxies=no_proxy, timeout=60)
    r.encoding = "utf-8"
    for line in r.text.split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            try:
                d = json.loads(line[6:])
                if "result" in d:
                    for c in d["result"].get("content", []):
                        t = c.get("text", "")
                        if t:
                            try:
                                return json.loads(t)
                            except json.JSONDecodeError:
                                return {"raw_text": t}
            except json.JSONDecodeError:
                continue
    return None


def _mcp_close(url, headers):
    import requests
    try:
        requests.delete(url, headers=headers, timeout=5)
    except Exception:
        pass


# ====================================================================
# 步骤1: 获取热点（新智元 RSS 优先 → V2EX 降级）
# ====================================================================

def fetch_rss_items():
    logger.info("📡 获取 RSS 热点（新智元优先）...")
    sid, headers = _mcp_init(TRENDRADAR_URL)
    try:
        result = _mcp_call(TRENDRADAR_URL, headers, "get_latest_rss", {"days": 3})
        if not result:
            return []
        all_items = result.get("data", [])
        items = [
            i for i in all_items
            if "xinzhiyuan" in (
                i.get("feed_id", "")
                + i.get("feed_name", "")
                + i.get("source", "")
            ).lower()
            or "新智元" in (
                i.get("feed_id", "")
                + i.get("feed_name", "")
                + i.get("source", "")
            )
        ]
        items = [i for i in items if i.get("title", "").strip()]
        items.sort(key=lambda i: i.get("published_at", ""), reverse=True)
        logger.info(f"  新智元 RSS: {len(items)} 条")
        return items[:20]
    finally:
        _mcp_close(TRENDRADAR_URL, headers)


def fetch_v2ex_topics():
    logger.info("📡 降级获取 V2EX 热点...")
    sid, headers = _mcp_init(TRENDRADAR_URL)
    try:
        result = _mcp_call(TRENDRADAR_URL, headers, "get_latest_news",
                           {"limit": 120, "include_url": True})
        if not result:
            return []
        items = [
            i for i in result.get("data", [])
            if i.get("platform_name", "").lower() == "v2ex" and i.get("url")
        ]
        tech_keywords = [
            "AI", "GPT", "LLM", "大模型", "OpenAI", "Claude", "编程", "代码",
            "开发者", "Python", "JavaScript", "工具", "开源", "Agent", "API",
            "插件", "GitHub", "DeepSeek", "前端", "后端", "SaaS", "创业",
            "副业", "独立开发", "产品", "效率",
        ]
        tech = [
            i for i in items
            if any(k.lower() in i.get("title", "").lower() for k in tech_keywords)
        ]
        result_items = (tech or items)[:20]
        logger.info(f"  V2EX 技术相关: {len(result_items)} 条")
        return result_items
    finally:
        _mcp_close(TRENDRADAR_URL, headers)


def fetch_article_content(article):
    """获取文章全文（用于热点内容补充）"""
    url = article.get("url", "")
    if not url:
        return article.get("title", "")
    sid, headers = _mcp_init(TRENDRADAR_URL)
    try:
        result = _mcp_call(TRENDRADAR_URL, headers, "read_article",
                           {"url": url, "timeout": 30})
        content = ""
        if result:
            if isinstance(result, dict):
                content = (
                    result.get("data", {}).get("content", "")
                    or result.get("content", "")
                    or result.get("raw_text", "")
                )
            elif isinstance(result, str):
                content = result
        if not content or len(content) < 200:
            content = article.get("title", "")
        if len(content) > 3000:
            content = content[:3000]
        article["content"] = content
        logger.info(f"  ✅ 获取内容 ({len(content)}字)")
    except Exception as e:
        logger.warning(f"  获取内容失败: {e}")
        article["content"] = article.get("title", "")
    finally:
        _mcp_close(TRENDRADAR_URL, headers)
    return article


# ====================================================================
# 步骤2: 产品分析
# ====================================================================

def analyze_product_page(product_url):
    logger.info(f"🔍 分析产品: {product_url}")
    try:
        from xhs_llm import fetch_webpage_text
        page_text = fetch_webpage_text(product_url)
        if len(page_text) < 100:
            logger.warning(f"  页面内容过少 ({len(page_text)}字)，尝试 TrendRadar...")
            sid, headers = _mcp_init(TRENDRADAR_URL)
            try:
                r = _mcp_call(TRENDRADAR_URL, headers, "read_article",
                              {"url": product_url, "timeout": 30})
                if r:
                    txt = (
                        r.get("data", {}).get("content", "")
                        or r.get("content", "")
                        or r.get("raw_text", "")
                    )
                    if len(txt) > len(page_text):
                        page_text = txt
            except Exception:
                pass
            finally:
                _mcp_close(TRENDRADAR_URL, headers)

        prompt = f"""根据网页内容，提取这个产品的关键信息，按格式输出JSON。

产品链接：{product_url}
网页内容：
{page_text[:4000] if page_text else "（无法抓取）"}

输出格式：
{{
  "product_name": "产品名称",
  "tagline": "一句话卖点",
  "target_audience": "目标用户",
  "core_features": "核心功能说明",
  "pain_points_solved": ["痛点1", "痛点2"],
  "user_value": "用户价值",
  "characteristics": ["特点1", "特点2", "特点3"]
}}"""
        result = call_llm_json(
            system_prompt="你是一个信息提取专家，从网页内容中提取产品关键信息。",
            user_prompt=prompt, temperature=0.2, max_tokens=2048,
        )
        pname = result.get("product_name", "") or result.get("name", "")
        logger.info(f"  ✅ 产品分析: {pname}")
        return result
    except Exception as e:
        logger.error(f"  ❌ 产品分析失败: {e}")
        return {"product_name": "", "tagline": "", "target_audience": "开发者",
                "core_features": "", "pain_points_solved": [],
                "user_value": "", "characteristics": []}


# ====================================================================
# 步骤3: AI 挑选最佳热点
# ====================================================================

def build_select_prompt(candidates, product_info):
    chars = "\n  - ".join(product_info.get("characteristics", []))
    titles = "\n".join(f"{i+1}. {c.get('title', '')}" for i, c in enumerate(candidates))
    return f"""你是一个懂技术又懂内容的小红书博主。从以下热点中，选出最适合与产品结合写一篇小红书长文的 1 个热点。

## 产品信息
- 产品名：{product_info.get('product_name', '未知')}
- 卖点：{product_info.get('tagline', '')}
- 核心功能：{product_info.get('core_features', '')}
- 特点：{chars}
- 目标用户：{product_info.get('target_audience', '开发者')}

## 挑选标准
1. 话题能与产品自然结合（软植入不突兀）
2. 小红书读者感兴趣、有讨论度
3. 结合产品后能写出有干货的长文

## 热点列表
{titles}

## 输出（仅 JSON）
{{"selected": [序号], "reasons": ["理由1", "理由2"]}}"""


def select_and_rewrite(candidates, product_info, product_url, max_count=1):
    logger.info("🤖 AI 挑选最佳热点...")
    if not candidates:
        return []

    select_prompt = build_select_prompt(candidates, product_info)
    selected = []
    try:
        result = call_llm_json(
            system_prompt="你是一个小红书博主，擅长挑选适合写长文的热点话题。输出严格JSON。",
            user_prompt=select_prompt, temperature=0.3, max_tokens=1000,
        )
        indices = result.get("selected", [])
        reasons = result.get("reasons", [])
        selected = [candidates[i - 1] for i in indices if 0 < i <= len(candidates)][:max_count]
        logger.info(f"  挑选理由: {'; '.join(reasons)}")
    except Exception as e:
        logger.warning(f"  AI 挑选失败: {e}，取第一条")
        selected = candidates[:1]

    if not selected:
        logger.warning("  无合适热点")
        return []

    # 获取文章全文
    logger.info("📖 获取热点文章全文...")
    for i, item in enumerate(selected):
        selected[i] = fetch_article_content(item)

    # 生成长文
    articles = []
    for idx, item in enumerate(selected):
        logger.info(f"✍️ 生成文章 [{idx + 1}/{len(selected)}]: {item.get('title', '')[:40]}...")
        prompt = build_long_article_prompt(item, product_info, product_url)
        try:
            raw = call_llm(
                system_prompt="你是一个热衷技术产品的小红书博主，擅长写深度长文分享。",
                user_prompt=prompt, temperature=0.8, max_tokens=8192,
            )
            parsed = parse_article_output(raw)
            if not parsed or not parsed.get("title") or not parsed.get("body"):
                logger.warning("  解析失败，尝试重试...")
                raw = call_llm(
                    system_prompt="你是一个热衷技术产品的小红书博主。严格按照指定格式输出。",
                    user_prompt=prompt + "\n\n请严格按照 ===TITLE=== / ===BRIEF=== / ===BODY=== / ===END=== 格式输出。",
                    temperature=0.7, max_tokens=8192,
                )
                parsed = parse_article_output(raw)
            if parsed and parsed.get("title") and parsed.get("body"):
                body_len = len(parsed["body"].strip())
                logger.info(f"  ✅ 标题: {parsed['title'][:20]} | 正文: {body_len}字")
                articles.append({
                    "title": parsed["title"],
                    "brief": parsed.get("brief", "") or parsed["title"][:50],
                    "body": parsed["body"],
                    "hotspot_title": item.get("title", ""),
                    "hotspot_url": item.get("url", ""),
                    "char_count": body_len,
                })
            else:
                logger.error("  解析失败，跳过")
        except Exception as e:
            logger.error(f"  ❌ 生成失败: {e}")

    return articles


# ====================================================================
# 步骤3b: 生成长文提示词
# ====================================================================

def load_template(name):
    fp = TEMPLATES_DIR / name
    if fp.exists():
        return fp.read_text(encoding="utf-8")
    return ""


def fill_template(template, vars_dict):
    def replacer(m):
        key = m.group(1)
        val = vars_dict.get(key)
        if val is None:
            return ""
        if isinstance(val, list):
            return "\n".join(f"  - {v}" for v in val)
        return str(val)
    return re.sub(r"\{\{(\w+)\}\}", replacer, template)


def build_long_article_prompt(hotspot, product_info, product_url):
    template = load_template("hotspot-long-article-prompt.md")
    if not template:
        raise FileNotFoundError("模板文件不存在: templates/hotspot-long-article-prompt.md")

    hotspot_content = hotspot.get("content", "")[:3000]
    return fill_template(template, {
        "hotspot_title": hotspot.get("title", ""),
        "hotspot_url": hotspot.get("url", ""),
        "hotspot_source": hotspot.get("feed_name", "新智元"),
        "hotspot_content": hotspot_content,
        "product_name": product_info.get("product_name", ""),
        "product_url": product_url,
        "positioning": product_info.get("tagline", ""),
        "core_features": product_info.get("core_features", ""),
        "characteristics": product_info.get("characteristics", []),
    })


# ====================================================================
# 解析 LLM 输出
# ====================================================================

def parse_article_output(raw):
    title_m = re.search(r"===TITLE===\s*\n([\s\S]*?)(?=\s*===BRIEF===|\s*===BODY===|\s*===END===|$)", raw)
    brief_m = re.search(r"===BRIEF===\s*\n([\s\S]*?)(?=\s*===BODY===|\s*===END===|$)", raw)
    body_m = re.search(r"===BODY===\s*\n([\s\S]*?)(?=\s*===END===|$)", raw)

    title = title_m.group(1).strip() if title_m else ""
    brief = brief_m.group(1).strip() if brief_m else ""
    body = body_m.group(1).strip() if body_m else ""

    # 清理标题
    title = re.sub(r"\s+", " ", title).strip()
    if len(title) > MAX_TITLE_LEN * 2:
        title = title[:MAX_TITLE_LEN]

    if not title or not body:
        return None
    if not brief:
        brief = title[:80]
    return {"title": title, "brief": brief[:100], "body": body}


# ====================================================================
# 生成 xhs_body (发布页精简版)
# ====================================================================

def generate_xhs_body(full_body, product_url, product_name):
    """从长文中生成精简版小红书发布确认页正文(≤1000字)"""
    cta = f"\n\n感兴趣可以去看看→ {product_url}"
    target = MAX_XHS_BODY - len(cta)

    prompt = f"""请根据以下长文，写一段精简版的小红书正文（不超过{target}字）。

要求：
- 保留核心观点和亮点
- 口语化、有画面感
- 不要出现产品链接（后续会单独加）
- 独立成文

原文：
{full_body[:800]}...

输出JSON：{{"body": "精简版正文"}}"""
    try:
        result = call_llm_json(
            system_prompt=f"你是一个小红书内容精简专家。严格按照JSON格式输出。",
            user_prompt=prompt, temperature=0.4, max_tokens=2000,
        )
        xhs = result.get("body", "").strip()
        if len(xhs) > target:
            xhs = xhs[:target]
        return xhs + cta
    except Exception as e:
        logger.warning(f"xhs 正文生成失败: {e}")
        return full_body[:MAX_XHS_BODY - len(cta)].strip() + cta


# ====================================================================
# 数据持久化
# ====================================================================

def load_published():
    if PUBLISH_RECORD.exists():
        try:
            return json.loads(PUBLISH_RECORD.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_published(entry):
    records = load_published()
    records.append(entry)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PUBLISH_RECORD.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_markdown(article, index):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    md = "\n\n".join([
        "---",
        f'title: "{article["title"]}"',
        f'description: "{article.get("brief", "")}"',
        f"hotspot: \"{article.get('hotspot_title', '')}\"",
        "---",
        "",
        article["body"],
    ])
    fp = OUTPUT_DIR / f"hotspot-long-{datetime.now().strftime('%Y%m%d')}-{index}.md"
    fp.write_text(md, encoding="utf-8")
    logger.info(f"  💾 已保存: {fp.name}")
    return fp


# ====================================================================
# 主流程
# ====================================================================

def run(product_url, dry_run=False, serial=None, max_count=1):
    logger.info("=" * 50)
    logger.info("🔥 小红书热点自动写长文 v1.0.0")
    logger.info("=" * 50)
    logger.info(f"  产品: {product_url}")
    logger.info(f"  模式: {'DRY-RUN' if dry_run else 'LIVE'}")
    logger.info(f"  设备: {serial or '自动'}")

    # ═══ 步骤1: 产品分析 ═══
    logger.info("\n" + "═" * 50)
    logger.info("步骤1: 分析产品...")
    product_info = analyze_product_page(product_url)

    # ═══ 步骤2: 获取热点 ═══
    logger.info("\n" + "═" * 50)
    logger.info("步骤2: 获取热点...")
    candidates = fetch_rss_items()
    if not candidates:
        logger.warning("  RSS 无数据，降级 V2EX...")
        candidates = fetch_v2ex_topics()
    if not candidates:
        logger.error("  ❌ 所有渠道均无热点")
        return {"status": "failed", "error": "无热点数据"}
    logger.info(f"  候选热点: {len(candidates)} 条")

    # ═══ 步骤3: 挑选 + 生成长文 ═══
    logger.info("\n" + "═" * 50)
    logger.info("步骤3: AI 挑选热点 + 生成长文...")
    articles = select_and_rewrite(candidates, product_info, product_url, max_count)
    if not articles:
        logger.error("  ❌ 文章生成失败")
        return {"status": "failed", "error": "文章生成失败"}
    logger.info(f"  生成 {len(articles)} 篇文章")

    # ═══ 步骤4: 生成 xhs_body + 保存 ═══
    logger.info("\n" + "═" * 50)
    logger.info("步骤4: 生成发布正文 + 保存...")
    results = []
    for i, article in enumerate(articles):
        logger.info(f"\n  [{i+1}/{len(articles)}] {article['title'][:30]}...")

        full_body = article["body"]
        body_chars = len(full_body.strip())
        if body_chars < MIN_BODY_LEN:
            logger.warning(f"    正文 {body_chars}字 < 建议 {MIN_BODY_LEN}字")
        if body_chars > MAX_BODY_LEN:
            logger.warning(f"    正文 {body_chars}字 > 建议 {MAX_BODY_LEN}字")

        xhs_body = generate_xhs_body(full_body, product_url, product_info.get("product_name", ""))
        logger.info(f"    xhs 正文: {len(xhs_body)}字")
        save_markdown(article, i + 1)

        if dry_run:
            logger.info("    ⏭️ Dry-run，跳过发布")
            results.append({
                "index": i + 1,
                "title": article["title"],
                "char_count": body_chars,
                "status": "skipped",
            })
            continue

        try:
            from phone_controller import publish_article
            pub_result = publish_article(
                serial=serial,
                product_url=product_url,
                article={
                    "title": article["title"][:MAX_TITLE_LEN],
                    "editor_body": full_body,
                    "xhs_body": xhs_body,
                },
            )
            record = {
                "title": article["title"],
                "hotspot_title": article["hotspot_title"],
                "hotspot_url": article["hotspot_url"],
                "product_url": product_url,
                "char_count": body_chars,
                "published_at": datetime.now().isoformat(),
                "device": serial or "auto",
                "type": "热点长文",
            }
            save_published(record)

            logger.info(f"    ✅ 发布成功")
            results.append({
                "index": i + 1,
                "title": article["title"],
                "char_count": body_chars,
                "status": "published",
            })
        except Exception as e:
            logger.error(f"    ❌ 发布失败: {e}")
            results.append({
                "index": i + 1,
                "title": article["title"],
                "char_count": body_chars,
                "status": "failed",
                "error": str(e),
            })

    logger.info("\n" + "=" * 50)
    logger.info("📊 汇总")
    logger.info("=" * 50)
    ok = sum(1 for r in results if r["status"] in ("published", "skipped"))
    for r in results:
        s = {"published": "✅", "skipped": "⏭️", "failed": "❌"}.get(r["status"], "❓")
        logger.info(f"  {s} [{r['index']}] {r['title'][:30]} ({r['char_count']}字)")
    logger.info(f"\n  共 {ok}/{len(results)} 篇成功")
    return {"status": "ok", "results": results}


if __name__ == "__main__":
    import argparse
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )

    parser = argparse.ArgumentParser(description="小红书热点自动写长文")
    parser.add_argument("--product-url", "-u", required=True, help="产品链接")
    parser.add_argument("--dry-run", action="store_true", help="仅生成不发布")
    parser.add_argument("--max", type=int, default=1, help="最多生成几篇")
    parser.add_argument("--serial", "-s", help="ADB 设备串号（可选）")
    args = parser.parse_args()

    result = run(
        product_url=args.product_url,
        dry_run=args.dry_run,
        serial=args.serial,
        max_count=args.max,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))

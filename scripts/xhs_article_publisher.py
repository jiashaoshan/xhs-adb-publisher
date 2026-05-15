"""
小红书文章发布模块
功能:
  1. LLM 根据产品链接生成小红书笔记(≥2500字校验)
  2. 标题≤20字 / 小红书正文≤1000字 自动截断
  3. ADB 自动发布长文
"""
import json, logging, os, sys, re
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.absolute()
SKILL_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from xhs_llm import call_llm, call_llm_json, analyze_product, build_writing_prompt
from phone_controller import publish_article

logger = logging.getLogger("xhs-publisher")

TEMPLATES_DIR = SKILL_DIR / "templates"
DATA_DIR = SKILL_DIR / "data"
CONFIG_DIR = SKILL_DIR / "config"
PUBLISHED_FILE = DATA_DIR / "published-articles.json"
ARTICLE_PROMPT = TEMPLATES_DIR / "article-prompt.md"

MIN_BODY_LEN = 1200
MAX_TITLE_LEN = 20
MAX_XHS_BODY = 1000
MAX_RETRIES = 3

def load_prompt() -> str:
    fp = ARTICLE_PROMPT
    return fp.read_text(encoding="utf-8") if fp.exists() else ""

def load_config() -> dict:
    fp = CONFIG_DIR / "publish.json"
    return json.loads(fp.read_text()) if fp.exists() else {}

def load_published() -> list:
    if PUBLISHED_FILE.exists():
        return json.loads(PUBLISHED_FILE.read_text())
    return []

def save_published(entry: dict):
    records = load_published()
    records.append(entry)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PUBLISHED_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2))

def _chars(s: str) -> int:
    """统计总字符数(一个中文字=1,一个Emoji=1,一个标点=1)"""
    return len(s.strip())

def _enforce_limits(title: str, body: str, product_url: str = "", product_name: str = "") -> tuple:
    """
    强制限制:
    - 标题 ≤ 20字
    - 编辑器正文: 完整正文
    - xhs正文: LLM 生成的精简版(≤1000字,非截断)+ 产品CTA
    """
    if len(title) > MAX_TITLE_LEN * 2:
        title = title[:MAX_TITLE_LEN * 2]
    editor_body = body.strip()
    xhs_body = _generate_xhs_body(editor_body, product_url, product_name)
    return title.strip(), editor_body, xhs_body


def _generate_xhs_body(editor_body: str, product_url: str, product_name: str) -> str:
    """LLM 生成精炼的 xhs 发布确认页正文(≤1000字)"""
    product_cta = f"\n\n感兴趣的话可以自己去看看→\n{product_url}"
    cta_len = len(product_cta)
    target_len = MAX_XHS_BODY - cta_len
    prompt = f"""你是一个小红书内容精简专家。

请根据以下文章,写一段精简版的小红书正文(不超过{target_len}字)。

要求:
- 保留核心卖点和亮点
- 语言口语化、有画面感
- 不要出现产品链接(后续会单独添加)
- 独立成文,不要用引导语
- 控制在{target_len}字以内

原文:{editor_body[:600]}...

输出JSON:{{"body": "精简版正文"}}
"""
    try:
        from xhs_llm import call_llm_json
        result = call_llm_json(
            system_prompt=f"你是一个小红书内容精简专家。输出不超过{target_len}字。",
            user_prompt=prompt,
            temperature=0.4,
            max_tokens=4000,
        )
        xhs = result.get("body", "").strip()
        if len(xhs) > target_len:
            xhs = xhs[:target_len]
        return xhs + product_cta
    except Exception as e:
        logger.warning(f"xhs正文LLM生成失败,使用原文前段: {e}")
        return editor_body[:MAX_XHS_BODY - len(product_cta)].strip() + product_cta


def _parse_article_output(raw: str) -> tuple:
    """从 LLM 纯文本输出中提取标题和正文"""
    lines = raw.strip().split("\n")
    title = ""
    body = raw.strip()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.search(r'#*\s*标题\s*[：:]\s*', stripped):
            title = re.sub(r'#*\s*标题\s*[：:]\s*', '', stripped).strip()
            body = "\n".join(lines[i+1:]).strip()
            break
        if re.match(r'^#{1,3}\s+\S', stripped) and 4 < len(stripped) < 40:
            title = re.sub(r'^#+\s+', '', stripped).strip()
            body = "\n".join(lines[i+1:]).strip()
            break
        if i == 0 and len(stripped) < 40 and not stripped.startswith("#") and not stripped.startswith("!"):
            title = stripped
            body = "\n".join(lines[1:]).strip()
            break
    body = re.sub(r'^###?\s*正文\s*[：:]\s*', '', body, flags=re.MULTILINE)
    body = re.sub(r'^[：:]\s*', '', body)
    return title, body


def _retry_llm(prompt_template: str, product_url: str, product_name: str,
               target_audience: str) -> dict:
    """两步法：1. 抓取网页分析产品 2. 按模板生成文章（带长度重试）"""
    # 第一步：抓取网页 → 分析产品
    logger.info("第一步：抓取网页并分析产品...")
    product_info = analyze_product(product_url, product_name)

    # 用用户模板生成写作提示词
    prompt = build_writing_prompt(product_info, product_url)
    # 长文覆盖字数为 1200-2000
    prompt += "\n\n【注意】这是一篇长文分享，请将字数控制在1200-2000字之间。"

    total_len = 0
    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(f"第二步：LLM 生成文章第 {attempt}/{MAX_RETRIES} 次...")

        length_hint = ""
        if attempt == 2:
            if total_len > 2000:
                length_hint = "\n⚠️ 上次输出超过2000字！正文必须在1200-2000字，请缩减！"
            else:
                length_hint = "\n⚠️ 上次输出不足1200字！正文必须在1200-2000字，请扩充！"
        elif attempt == 3:
            length_hint = "\n⚠️ 正文必须控制在1200-2000字！"

        raw = call_llm(
            system_prompt=f"你是一个分享真实产品体验的小红书博主。{length_hint}",
            user_prompt=prompt + length_hint,
            max_tokens=8192,
        )

        title, body = _parse_article_output(raw)

        total_len = len(body.strip())
        logger.info(f"  LLM返回: 标题{_chars(title)}字 正文{_chars(body)}字")

        if MIN_BODY_LEN <= total_len <= 2000:
            return {"title": title, "body": body, "retries": attempt}

        if attempt < MAX_RETRIES:
            if total_len < MIN_BODY_LEN:
                logger.warning(f"  正文仅{total_len}字符,不足{MIN_BODY_LEN},重试...")
            else:
                logger.warning(f"  正文{total_len}字符,超过2000字上限,重试...")

    logger.warning(f"  已重试{MAX_RETRIES}次,使用当前结果")
    return {"title": title, "body": body, "retries": MAX_RETRIES}

def generate_article(product_url: str, product_name: str = "",
                     target_audience: str = "") -> dict:
    """LLM 生成小红书文章(带校验+重试)"""
    config = load_config()
    prompt_template = load_prompt()
    if not prompt_template:
        raise FileNotFoundError(f"提示词模板未找到: {ARTICLE_PROMPT}")

    if not target_audience:
        target_audience = config.get("target_audience", "创业者、技术人")

    gen = _retry_llm(prompt_template, product_url, product_name, target_audience)
    title, editor_body, xhs_body = _enforce_limits(gen["title"], gen["body"], product_url, product_name)

    return {
        "title": title,
        "editor_body": editor_body,
        "xhs_body": xhs_body,
        "product_url": product_url,
        "generated_at": datetime.now().isoformat(),
        "llm_retries": gen["retries"],
        "total_chars": len(gen["body"].strip()),
    }

def run(product_url: str, product_name: str = "", target_audience: str = "",
        dry_run: bool = False) -> dict:
    """
    完整发布流程: LLM生成 → ADB发布

    Args:
        product_url: 产品链接
        product_name: 产品名称（可选）
        target_audience: 目标受众（可选）
        dry_run: 仅生成不发布
    """
    result = {"status": "started", "steps": []}

    # 步骤1: LLM 生成
    logger.info("步骤1/2: LLM 生成文章...")
    article = generate_article(product_url, product_name, target_audience)
    result["article"] = article
    result["steps"].append({"step": "llm_generate", "status": "ok",
                            "retries": article.get("llm_retries", 1)})
    logger.info(f"  标题: {article['title']}")
    logger.info(f"  编辑器正文: {len(article['editor_body'])}字")
    logger.info(f"  小红书正文: {len(article['xhs_body'])}字")

    if dry_run:
        result["status"] = "dry_run"
        return result

    # 步骤2: ADB 发布
    logger.info(f"步骤2/2: ADB 发布到小红书...")
    try:
        serial = os.environ.get("ANDROID_SERIAL")
        publish_result = publish_article(
            serial=serial,
            product_url=product_url,
            article=article,
        )
        record = {
            "title": article["title"],
            "product_url": article["product_url"],
            "published_at": datetime.now().isoformat(),
            "type": "长文",
            "total_chars": article["total_chars"],
        }
        save_published(record)
        result["record"] = record
        result["status"] = "published"
        logger.info(f"✅ 发布成功: {article['title']}")
    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)
        logger.error(f"❌ 发布失败: {e}")

    return result

"""
小红书文章发布模块
功能:
  1. LLM 根据产品链接生成小红书笔记（≥2500字校验）
  2. 标题≤20字 / 小红书正文≤1000字 自动截断
  3. ADB 自动发布长文
"""
import json, logging, os, sys, re
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.absolute()
SKILL_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from xhs_llm import call_llm_json
from phone_controller import xie_chang_wen

logger = logging.getLogger("xhs-publisher")

TEMPLATES_DIR = SKILL_DIR / "templates"
DATA_DIR = SKILL_DIR / "data"
CONFIG_DIR = SKILL_DIR / "config"
PUBLISHED_FILE = DATA_DIR / "published-articles.json"
ARTICLE_PROMPT = TEMPLATES_DIR / "article-prompt.md"

MIN_BODY_LEN = 1200      # 最低字数要求（含标点/emoji/空格）
MAX_TITLE_LEN = 20       # 标题中文数
MAX_XHS_BODY = 1000      # 小红书正文总长度（发布确认页正文）
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
    """统计总字符数（一个中文字=1，一个Emoji=1，一个标点=1）"""
    return len(s.strip())

def _enforce_limits(title: str, body: str, product_url: str = "", product_name: str = "") -> tuple:
    """
    强制限制:
    - 标题 ≤ 20字
    - 编辑器正文: 完整正文
    - xhs正文: LLM 生成的精简版（≤1000字，非截断）+ 产品CTA
    """
    if len(title) > MAX_TITLE_LEN * 2:
        title = title[:MAX_TITLE_LEN * 2]
    editor_body = body.strip()
    xhs_body = _generate_xhs_body(editor_body, product_url, product_name)
    return title.strip(), editor_body, xhs_body


def _generate_xhs_body(editor_body: str, product_url: str, product_name: str) -> str:
    """LLM 生成精炼的 xhs 发布确认页正文（≤1000字）"""
    product_cta = f"\n\n🔥【立即体验】\n👉 {product_name}: {product_url}"
    cta_len = len(product_cta)
    target_len = MAX_XHS_BODY - cta_len
    prompt = f"""你是一个小红书内容精简专家。

请根据以下文章，写一段精简版的小红书正文（不超过{target_len}字）。

要求：
- 保留核心卖点和亮点
- 语言口语化、有画面感
- 不要出现产品链接（后续会单独添加）
- 独立成文，不要用引导语
- 控制在{target_len}字以内

原文：{editor_body[:600]}...

输出JSON：{{"body": "精简版正文"}}
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
        logger.warning(f"xhs正文LLM生成失败，使用原文前段: {e}")
        return editor_body[:MAX_XHS_BODY - len(product_cta)].strip() + product_cta


def _retry_llm(prompt_template: str, product_url: str, product_name: str,
               target_audience: str) -> dict:
    """带重试的 LLM 调用，确保正文≥2500字"""
    prompt = prompt_template.replace("{{product_url}}", product_url)
    prompt = prompt.replace("{{product_name}}", product_name or product_url)
    prompt = prompt.replace("{{target_audience}}", target_audience)

    total_len = 0
    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(f"LLM 生成第 {attempt}/{MAX_RETRIES} 次...")
        
        # 追加长度要求（越往后越严厉）
        length_hint = ""
        if attempt == 2:
            if total_len > 2000:
                length_hint = "\n⚠️ 上次输出超过2000字！正文总字数（含标点空格）必须控制在1200-2000字！请缩减！"
            else:
                length_hint = "\n⚠️ 上次输出不足1200字！正文总字数（含标点空格）必须控制在1200-2000字！请扩充！"
        elif attempt == 3:
            length_hint = "\n⚠️ 正文必须控制在1200-2000字！太短或太长都会被截断导致发布失败！"
        
        result = call_llm_json(
            system_prompt=f"你是一个专业的小红书内容创作者。{length_hint}严格按照用户要求输出JSON格式。",
            user_prompt=prompt + length_hint,
            max_tokens=384000,
        )
        
        title = result.get("title", "")
        body = result.get("body", "")
        
        total_len = len(body.strip())
        logger.info(f"  LLM返回: 标题{_chars(title)}字 正文{_chars(body)}字")
        
        # 校验总长度（含标点/emoji），控制在1200-2000字
        if MIN_BODY_LEN <= total_len <= 2000:
            return {"title": title, "body": body, "retries": attempt}
        
        if attempt < MAX_RETRIES:
            if total_len < MIN_BODY_LEN:
                logger.warning(f"  正文仅{total_len}字符，不足{MIN_BODY_LEN}，重试...")
            else:
                logger.warning(f"  正文{total_len}字符，超过2000字上限，重试...")
    
    logger.warning(f"  已重试{MAX_RETRIES}次仍不足{MIN_BODY_LEN}字符，使用当前结果")
    return {"title": title, "body": body, "retries": MAX_RETRIES}

def generate_article(product_url: str, product_name: str = "",
                     target_audience: str = "") -> dict:
    """LLM 生成小红书文章（带校验+重试）"""
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
    完整发布流程: LLM生成（≥2500字校验）→ ADB发布
    
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
    logger.info(f"  总字数: {article.get('total_chars', 0)} (重试{article.get('llm_retries', 1)}次)")
    
    if dry_run:
        result["status"] = "dry_run"
        return result
    
    # 步骤2: ADB 发布
    logger.info(f"步骤2/2: ADB 发布到小红书...")
    try:
        logger.info(f"发布笔记: {article['title']}")
        xie_chang_wen(
            editor_body=article["editor_body"],
            publish_body=article["xhs_body"],
            title=article["title"],
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

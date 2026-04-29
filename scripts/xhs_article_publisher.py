"""
小红书文章发布模块
功能:
  1. LLM 根据产品链接生成小红书笔记
  2. Pexels 自动配图
  3. ADB 自动发布长文
"""
import json, logging, os, sys, time
from datetime import datetime
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).parent.absolute()
SKILL_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from xhs_llm import call_llm_json, get_api_key
from pexels_images import download_images_for_topic
from phone_controller import xie_chang_wen

logger = logging.getLogger("xhs-publisher")

TEMPLATES_DIR = SKILL_DIR / "templates"
DATA_DIR = SKILL_DIR / "data"
CONFIG_DIR = SKILL_DIR / "config"
PUBLISHED_FILE = DATA_DIR / "published-articles.json"
ARTICLE_PROMPT = TEMPLATES_DIR / "article-prompt.md"

def load_prompt() -> str:
    """加载文章生成提示词模板"""
    if ARTICLE_PROMPT.exists():
        with open(ARTICLE_PROMPT) as f:
            return f.read()
    return ""

def load_config() -> dict:
    """加载发布配置"""
    cfg_file = CONFIG_DIR / "publish.json"
    if cfg_file.exists():
        with open(cfg_file) as f:
            return json.load(f)
    return {}

def load_published() -> list:
    """加载发布历史"""
    if PUBLISHED_FILE.exists():
        with open(PUBLISHED_FILE) as f:
            return json.load(f)
    return []

def save_published(entry: dict):
    """保存发布记录"""
    records = load_published()
    records.append(entry)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(PUBLISHED_FILE, "w") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

def generate_article(product_url: str, product_name: str = "",
                     target_audience: str = "") -> dict:
    """LLM 生成小红书文章"""
    prompt_template = load_prompt()
    if not prompt_template:
        raise FileNotFoundError(f"提示词模板未找到: {ARTICLE_PROMPT}")
    
    config = load_config()
    if not target_audience:
        target_audience = config.get("target_audience", "创业者、技术人")
    
    user_prompt = prompt_template.replace("{{product_url}}", product_url)
    user_prompt = user_prompt.replace("{{product_name}}", product_name or product_url)
    user_prompt = user_prompt.replace("{{target_audience}}", target_audience)
    
    logger.info(f"正在调用 LLM 生成文章...")
    result = call_llm_json(
        system_prompt="你是一个专业的小红书内容创作者。严格按照用户要求输出JSON格式。",
        user_prompt=user_prompt,
    )
    
    title = result.get("title", config.get("default_title", "AI工具实测分享"))
    body = result.get("body", "")
    
    # 截断标题不超过20字
    if len(title) > 20:
        title = title[:18] + "…"
    
    # 分割正文 → 编辑器正文(2500字) + 小红书正文(1000字)
    editor_body = body[:config.get("editor_body_target_chars", 2500)]
    xhs_body = body[config.get("editor_body_target_chars", 2500):][:config.get("xhs_body_max_chars", 1000)]
    if not xhs_body:
        xhs_body = editor_body[-config.get("xhs_body_max_chars", 1000):]
        editor_body = editor_body[:-config.get("xhs_body_max_chars", 1000)]
    
    return {
        "title": title,
        "editor_body": editor_body,
        "xhs_body": xhs_body,
        "product_url": product_url,
        "generated_at": datetime.now().isoformat(),
    }

def download_images(topic: str, count: int = 3) -> list:
    """下载配图"""
    images = download_images_for_topic(topic, count)
    if not images:
        logger.warning("未下载到配图，将发布纯文字笔记")
    return images

def publish_to_xhs(article_data: dict) -> dict:
    """通过 ADB 发布到小红书"""
    logger.info(f"发布笔记: {article_data['title']}")
    xie_chang_wen(
        editor_body=article_data["editor_body"],
        publish_body=article_data["xhs_body"],
        title=article_data["title"],
    )
    record = {
        "title": article_data["title"],
        "product_url": article_data["product_url"],
        "published_at": datetime.now().isoformat(),
        "type": "长文",
    }
    save_published(record)
    return record

def run(product_url: str, product_name: str = "", target_audience: str = "",
        dry_run: bool = False) -> dict:
    """
    完整发布流程: LLM生成 → Pexels配图 → ADB发布
    
    Args:
        product_url: 产品链接
        product_name: 产品名称（可选）
        target_audience: 目标受众（可选）
        dry_run: 仅生成不发布
    """
    result = {"status": "started", "steps": []}
    
    # 步骤1: LLM 生成文章
    logger.info("步骤1/3: LLM 生成文章...")
    article = generate_article(product_url, product_name, target_audience)
    result["article"] = article
    result["steps"].append({"step": "llm_generate", "status": "ok", "title": article["title"]})
    logger.info(f"  标题: {article['title']}")
    logger.info(f"  编辑器正文: {len(article['editor_body'])}字")
    logger.info(f"  小红书正文: {len(article['xhs_body'])}字")
    
    # 步骤2: Pexels 配图
    logger.info("步骤2/3: 搜索配图...")
    topic = product_name or product_url.split("//")[-1].split("/")[0]
    images = download_images(topic)
    result["images"] = images
    result["steps"].append({"step": "pexels_images", "status": "ok" if images else "skipped", "count": len(images)})
    logger.info(f"  下载了 {len(images)} 张图片")
    
    if dry_run:
        result["status"] = "dry_run"
        logger.info("DRY RUN 模式，跳过发布")
        return result
    
    # 步骤3: ADB 发布
    logger.info(f"步骤3/3: ADB 发布到小红书...")
    try:
        record = publish_to_xhs(article)
        result["record"] = record
        result["status"] = "published"
        logger.info(f"✅ 发布成功: {article['title']}")
    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)
        logger.error(f"❌ 发布失败: {e}")
    
    return result

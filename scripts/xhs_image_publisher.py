"""
小红书图文发布模块
功能:
  1. LLM 根据产品链接/主题生成小红书热文(2000-2500字)
  2. 根据热文生成文生图提示词(封面1张+内容4张)
  3. 调用豆包生成图片
  4. ADB 推送图片到手机
  5. ADB 从相册选择发布图文
"""
import json, logging, os, sys, re, subprocess, tempfile, shutil
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.absolute()
SKILL_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from xhs_llm import call_llm_json
from phone_controller import publish_image_article

logger = logging.getLogger("xhs-image-publisher")

TEMPLATES_DIR = SKILL_DIR / "templates"
DATA_DIR = SKILL_DIR / "data"
CONFIG_DIR = SKILL_DIR / "config"
PUBLISHED_FILE = DATA_DIR / "published-articles.json"

MIN_BODY_LEN = 300
MAX_BODY_LEN = 1000
MAX_TITLE_LEN = 20
MAX_XHS_BODY = 1000
MAX_RETRIES = 3
import random

# 封面图提示词模板（随机选）
COVER_PROMPT_FILES = sorted(TEMPLATES_DIR.glob("cover-prompt-*.md"))

# 文章类型与提示词模板映射
ARTICLE_TYPES = {
    "general": "short-article-prompt.md",  # 默认使用短模板
}

def load_prompt(article_type: str = "general") -> str:
    """加载短文章提示词模板（标题≤20字，正文≤1000字）"""
    template_file = ARTICLE_TYPES.get(article_type, "short-article-prompt.md")
    fp = TEMPLATES_DIR / template_file
    if fp.exists():
        return fp.read_text(encoding="utf-8")
    # fallback to default
    fp = TEMPLATES_DIR / "article-prompt.md"
    return fp.read_text(encoding="utf-8") if fp.exists() else ""

def load_config() -> dict:
    fp = CONFIG_DIR / "publish.json"
    return json.loads(fp.read_text()) if fp.exists() else {}

def save_published(entry: dict):
    records = []
    if PUBLISHED_FILE.exists():
        records = json.loads(PUBLISHED_FILE.read_text())
    records.append(entry)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PUBLISHED_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2))

def detect_article_type(topic: str, product_url: str = "") -> str:
    """根据主题自动检测文章类型"""
    topic_lower = (topic + " " + product_url).lower()
    
    if any(kw in topic_lower for kw in ["教程", "指南", "步骤", "how to", "入门", "攻略"]):
        return "tutorial"
    elif any(kw in topic_lower for kw in ["故事", "经历", "体验", "感受", "日记", "plog"]):
        return "story"
    elif any(kw in topic_lower for kw in ["对比", "测评", "vs", "评测", "哪个好", "区别"]):
        return "comparison"
    elif any(kw in topic_lower for kw in ["清单", "合集", "推荐", "top", "必备", "神器"]):
        return "list"
    else:
        return "general"

def _retry_llm_generate(topic: str, product_url: str, article_type: str) -> dict:
    """带重试的 LLM 文章生成，确保1500-2000字"""
    prompt_template = load_prompt(article_type)
    if not prompt_template:
        raise FileNotFoundError(f"提示词模板未找到")
    
    prompt = prompt_template.replace("{{topic}}", topic)
    prompt = prompt.replace("{{product_url}}", product_url)
    prompt = prompt.replace("{{product_name}}", topic)
    
    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(f"LLM 生成文章第 {attempt}/{MAX_RETRIES} 次...")
        
        length_hint = f"\n\n⚠️ 重要：正文总字数（含标点空格）必须在{MIN_BODY_LEN}-{MAX_BODY_LEN}字之间。"
        if attempt > 1:
            length_hint += f"\n上次生成字数不符合要求，请调整。\n请严格控制字数，不要超出范围。"
        
        result = call_llm_json(
            system_prompt=f"你是一位小红书内容营销专家。{length_hint}",
            user_prompt=prompt + length_hint,
            max_tokens=4096,
            temperature=0.7,
        )
        
        title = result.get("title", "")
        body = result.get("body", "")
        total_len = len(body.strip())
        
        logger.info(f"  LLM返回: 标题{len(title)}字 正文{total_len}字")
        
        if MIN_BODY_LEN <= total_len <= MAX_BODY_LEN or attempt >= MAX_RETRIES:
            return {"title": title, "body": body, "retries": attempt, "article_type": article_type}
        
        if total_len < MIN_BODY_LEN:
            logger.warning(f"  正文仅{total_len}字符，不足{MIN_BODY_LEN}，重试...")
        else:
            logger.warning(f"  正文{total_len}字符，超过{MAX_BODY_LEN}，重试...")
    
    logger.warning(f"  已重试{MAX_RETRIES}次，使用当前结果")
    return {"title": title, "body": body, "retries": MAX_RETRIES, "article_type": article_type}


def generate_cover_prompt(title: str, body: str, product_url: str = "") -> str:
    """从封面提示词模板中随机选一个生成封面图提示词"""
    if not COVER_PROMPT_FILES:
        logger.warning("封面提示词模板未找到")
        return f"小红书封面图，3:4比例，标题：{title[:50]}"
    
    chosen = random.choice(COVER_PROMPT_FILES)
    template = chosen.read_text(encoding="utf-8")
    logger.info(f"选用封面模板: {chosen.name}")
    
    # 提取产品宣传语（从正文中提取短句）
    product_slogan = _extract_slogan(body, product_url)
    # 提取关键词
    article_title = title[:30]
    
    prompt = template.replace("{{product_slogan}}", product_slogan)
    prompt = prompt.replace("{{article_title}}", article_title)
    
    logger.info(f"封面图提示词: {prompt[:200]}...")
    return prompt


def _extract_slogan(body: str, product_url: str = "") -> str:
    """从正文中提取产品宣传语（10字以内的短句）"""
    if product_url:
        return "限时免费"
    # 从正文中提取短句
    lines = body.split("\n")
    for line in lines:
        line = line.strip()
        if 6 <= len(line) <= 20 and not line.startswith("#"):
            # 找带关键动作的短句
            for kw in ["免费", "好用", "推荐", "神器", "必备", "宝藏", "省钱", "薅羊毛"]:
                if kw in line:
                    return line[:20]
    return "快来看看"


def generate_cover_image(prompt: str, output_dir: Path) -> str:
    """调用豆包生成封面图"""
    doubao_script = Path.home() / ".openclaw/workspace/skills/doubao-image-create/scripts/generate.js"
    doubao_output = Path.home() / ".openclaw/workspace/skills/doubao-image-create/output/image.jpg"
    
    if not doubao_script.exists():
        raise FileNotFoundError(f"豆包生成脚本未找到: {doubao_script}")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    cover_path = output_dir / "cover.jpg"
    
    logger.info("生成封面图...")
    cmd = ["node", str(doubao_script), prompt, "--size", "1024", "--watermark", "false"]
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

def push_images_to_device(image_paths: list, serial: str = None) -> bool:
    """将图片推送到手机相册"""
    serial_arg = f"-s {serial}" if serial else ""
    
    # 推送到手机 Download 目录，小红书会自动扫描
    remote_dir = "/sdcard/DCIM/Camera"
    
    for img_path in image_paths:
        filename = Path(img_path).name
        remote_path = f"{remote_dir}/{filename}"
        cmd = f"adb {serial_arg} push \"{img_path}\" \"{remote_path}\""
        logger.info(f"推送图片: {filename}")
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                logger.error(f"推送失败: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"推送异常: {e}")
            return False
    
    # 刷新媒体库
    refresh_cmd = f"adb {serial_arg} shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file://{remote_dir}"
    subprocess.run(refresh_cmd, shell=True, capture_output=True)
    
    logger.info(f"✅ 已推送 {len(image_paths)} 张图片到手机")
    return True

def generate_article(topic: str, product_url: str = "", article_type: str = None) -> dict:
    """生成文章 + 封面图提示词"""
    if not article_type:
        article_type = detect_article_type(topic, product_url)
    
    logger.info(f"文章类型: {article_type}")
    
    # 步骤1: 生成文章（标题≤20字，正文≤1000字）
    logger.info("步骤1/2: LLM 生成文章...")
    article = _retry_llm_generate(topic, product_url, article_type)
    
    # 步骤2: 生成封面图提示词（从模板填充）
    logger.info("步骤2/2: 生成封面图提示词...")
    cover_prompt = generate_cover_prompt(article["title"], article["body"], product_url)
    
    # 正文已≤1000字，直接用作xhs正文
    xhs_body = article["body"]
    if len(xhs_body) > MAX_XHS_BODY:
        xhs_body = xhs_body[:MAX_XHS_BODY]
    
    return {
        "title": article["title"][:MAX_TITLE_LEN * 2],
        "body": article["body"],
        "xhs_body": xhs_body,
        "article_type": article_type,
        "cover_prompt": cover_prompt,
        "product_url": product_url,
        "generated_at": datetime.now().isoformat(),
        "llm_retries": article["retries"],
    }


def run(topic: str, product_url: str = "", article_type: str = None, 
        dry_run: bool = False, serial: str = None) -> dict:
    """
    完整图文发布流程: 生成文章 → 生成封面图 → 推送封面 → ADB发布
    """
    result = {"status": "started", "steps": []}
    
    # 步骤1: 生成内容
    logger.info("=" * 40)
    logger.info("开始图文发布流程")
    logger.info("=" * 40)
    
    article = generate_article(topic, product_url, article_type)
    result["article"] = article
    result["steps"].append({"step": "generate_article", "status": "ok"})
    
    logger.info(f"标题: {article['title']}")
    logger.info(f"正文: {len(article['body'])}字")
    
    if dry_run:
        result["status"] = "dry_run"
        return result
    
    # 步骤2: 生成封面图
    logger.info("-" * 40)
    logger.info("生成封面图...")
    
    image_dir = DATA_DIR / "xhs_images"
    image_dir.mkdir(parents=True, exist_ok=True)
    for f in image_dir.glob("*.jpg"):
        f.unlink()
    
    cover_path = generate_cover_image(article["cover_prompt"], image_dir)
    image_paths = [cover_path]
    result["cover_path"] = cover_path
    result["steps"].append({"step": "generate_cover", "status": "ok"})
    
    if not cover_path:
        result["status"] = "failed"
        result["error"] = "封面图生成失败"
        return result
    
    # 步骤3: 推送封面图到手机
    logger.info("-" * 40)
    logger.info("推送封面图到手机...")
    
    if not push_images_to_device(image_paths, serial):
        result["status"] = "failed"
        result["error"] = "图片推送失败"
        return result
    
    result["steps"].append({"step": "push_image", "status": "ok"})
    
    # 步骤4: ADB 发布（只选1张封面图）
    logger.info("-" * 40)
    logger.info("ADB 发布图文（1张封面图）...")
    
    try:
        publish_image_article(
            serial=serial,
            title=article["title"][:MAX_TITLE_LEN],
            xhs_body=article["xhs_body"],
            image_count=1,  # 只发1张封面图
        )
        
        record = {
            "title": article["title"],
            "product_url": product_url,
            "published_at": datetime.now().isoformat(),
            "type": "封面图文",
            "image_count": 1,
        }
        save_published(record)
        
        result["record"] = record
        result["status"] = "published"
        logger.info(f"✅ 图文发布成功: {article['title']}")
        
    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)
        logger.error(f"❌ 发布失败: {e}")
    
    return result

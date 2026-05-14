"""
Pexels 图片搜索与下载模块
通过 Pexels API 搜索与产品相关的图片并下载到本地，支持推送到手机相册
"""
import json, logging, os, requests, time, subprocess
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

PEXELS_API_URL = "https://api.pexels.com/v1/search"
DATA_DIR = Path(__file__).parent.parent / "data"

def _get_api_key() -> Optional[str]:
    """从环境变量读取 Pexels API Key"""
    key = os.environ.get("PEXELS_API_KEY")
    if key:
        return key
    # fallback: 从openclaw.json读取
    try:
        cfg = os.path.expanduser("~/.openclaw/openclaw.json")
        if os.path.exists(cfg):
            with open(cfg) as f:
                env = json.load(f).get("env", {})
                return env.get("PEXELS_API_KEY")
    except: pass
    return None

def search_images(query: str, count: int = 3) -> List[dict]:
    """
    搜索 Pexels 图片
    返回: [{"url": "...", "photographer": "...", "alt": "..."}, ...]
    """
    api_key = _get_api_key()
    if not api_key:
        logger.warning("未配置 PEXELS_API_KEY，跳过图片搜索")
        return []
    
    headers = {"Authorization": api_key}
    params = {"query": query, "per_page": count, "orientation": "portrait"}
    
    try:
        resp = requests.get(PEXELS_API_URL, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        photos = data.get("photos", [])
        results = []
        for p in photos[:count]:
            src = p.get("src", {})
            url = src.get("portrait") or src.get("medium") or src.get("original")
            if url:
                results.append({
                    "url": url,
                    "photographer": p.get("photographer", ""),
                    "alt": p.get("alt", ""),
                    "width": p.get("width", 0),
                    "height": p.get("height", 0),
                })
        logger.info(f"Pexels 搜索 '{query}': 找到 {len(results)} 张图片")
        return results
    except Exception as e:
        logger.error(f"Pexels 搜索失败: {e}")
        return []

def download_image(url: str, filepath: str) -> Optional[str]:
    """下载图片到本地"""
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "wb") as f:
            f.write(resp.content)
        logger.info(f"图片已下载: {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"图片下载失败 {url}: {e}")
        return None

def download_images_for_topic(topic: str, count: int = 3, save_dir: Optional[str] = None) -> List[str]:
    """
    搜索并下载与主题相关的图片
    返回: [本地文件路径, ...]
    """
    images = search_images(topic, count)
    if not images:
        return []

    if not save_dir:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        save_dir = str(DATA_DIR / "pexels")

    downloaded = []
    for i, img in enumerate(images):
        filename = f"{topic.replace(' ', '_')}_{i+1}.jpg"
        filepath = os.path.join(save_dir, filename)
        result = download_image(img["url"], filepath)
        if result:
            downloaded.append(result)
    return downloaded


def push_images_to_phone(local_paths: List[str], serial: str = None) -> List[str]:
    """
    将本地图片推送到手机相册
    返回: [手机端路径, ...]
    """
    if not local_paths:
        return []

    # 手机相册路径
    phone_dir = "/sdcard/DCIM/Camera"
    phone_paths = []

    for local_path in local_paths:
        if not os.path.exists(local_path):
            logger.warning(f"图片不存在: {local_path}")
            continue

        filename = os.path.basename(local_path)
        phone_path = f"{phone_dir}/{filename}"

        # 构建adb命令
        cmd = ["adb"]
        if serial:
            cmd.extend(["-s", serial])
        cmd.extend(["push", local_path, phone_path])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                logger.info(f"图片已推送到手机: {phone_path}")
                phone_paths.append(phone_path)
            else:
                logger.error(f"推送失败: {result.stderr}")
        except Exception as e:
            logger.error(f"推送图片异常: {e}")

    # 刷新相册
    if phone_paths:
        refresh_cmd = ["adb"]
        if serial:
            refresh_cmd.extend(["-s", serial])
        refresh_cmd.extend([
            "shell", "am", "broadcast",
            "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
            "-d", f"file://{phone_dir}"
        ])
        try:
            subprocess.run(refresh_cmd, capture_output=True, timeout=10)
            logger.info("相册已刷新")
        except Exception as e:
            logger.warning(f"刷新相册失败: {e}")

    return phone_paths


def get_images_for_article(topic: str, count: int = 3, serial: str = None) -> dict:
    """
    获取文章配图并推送到手机
    返回: {"local_paths": [...], "phone_paths": [...]}
    """
    logger.info(f"开始搜索图片: {topic}, 数量: {count}")

    # 1. 搜索并下载图片
    local_paths = download_images_for_topic(topic, count)
    if not local_paths:
        logger.warning("未获取到图片")
        return {"local_paths": [], "phone_paths": []}

    logger.info(f"下载完成: {len(local_paths)} 张图片")

    # 2. 推送到手机
    phone_paths = push_images_to_phone(local_paths, serial)
    logger.info(f"推送到手机: {len(phone_paths)} 张图片")

    return {
        "local_paths": local_paths,
        "phone_paths": phone_paths,
        "count": len(phone_paths)
    }

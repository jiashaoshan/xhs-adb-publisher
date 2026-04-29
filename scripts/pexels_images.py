"""
Pexels 图片搜索与下载模块
通过 Pexels API 搜索与产品相关的图片并下载到本地
"""
import json, logging, os, requests, time
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

PEXELS_API_URL = "https://api.pexels.com/v1/search"
DATA_DIR = Path(__file__).parent / "data"

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

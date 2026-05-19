import json, logging, os, requests
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# ── LLM 配置 ────
LLM_API_URL = None
LLM_API_KEY = None
DEFAULT_MODEL = "qianfan-code-latest"
DEFAULT_MAX_TOKENS = 8192
DEFAULT_TIMEOUT = 300
LLM_RETRY_DELAY = 15

# 备选 Provider（主用不通时自动切换）
FALLBACK_API_URL = None
FALLBACK_API_KEY = None
FALLBACK_MODEL = "deepseek-v4-flash"
FALLBACK_PROVIDER_IDS = ["deepseek"]


def _load_llm_config():
    """从 openclaw.json 读取 LLM 配置（主用千帆，自动备选 deepseek）"""
    global LLM_API_URL, LLM_API_KEY, DEFAULT_MODEL
    global FALLBACK_API_URL, FALLBACK_API_KEY, FALLBACK_MODEL
    if LLM_API_URL and LLM_API_KEY:
        return
    try:
        cfg_path = os.path.expanduser("~/.openclaw/openclaw.json")
        if os.path.exists(cfg_path):
            with open(cfg_path) as f:
                data = json.load(f)
            providers = data.get("models", {}).get("providers", {})

            for provider_id, p in providers.items():
                pid = provider_id.lower()

                # 主用：千帆
                if "qianfan" in pid or "baidu" in pid:
                    LLM_API_URL = p.get("baseUrl", "") + "/chat/completions"
                    LLM_API_KEY = p.get("apiKey", "")
                    models = p.get("models", [])
                    if models:
                        DEFAULT_MODEL = models[0].get("id", "qianfan-code-latest")
                    logger.info(f"主用: {LLM_API_URL} | 模型: {DEFAULT_MODEL}")

                # 备选：deepseek
                elif any(fid in pid for fid in FALLBACK_PROVIDER_IDS):
                    if not FALLBACK_API_URL:
                        FALLBACK_API_URL = p.get("baseUrl", "") + "/chat/completions"
                        FALLBACK_API_KEY = p.get("apiKey", "")
                        fb_models = p.get("models", [])
                        if fb_models:
                            FALLBACK_MODEL = fb_models[0].get("id", "deepseek-v4-flash")
                        logger.info(f"备选: {FALLBACK_API_URL} | 模型: {FALLBACK_MODEL}")
    except Exception as e:
        logger.debug(f"读取 openclaw.json LLM 配置失败: {e}")

    # fallback: 环境变量（兜底用 deepseek）
    if not LLM_API_URL:
        LLM_API_URL = os.environ.get("LLM_API_URL", "https://api.deepseek.com/chat/completions")
        LLM_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

def get_api_key() -> str:
    _load_llm_config()
    if not LLM_API_KEY:
        raise EnvironmentError(
            "未找到 LLM API Key。\n"
            "请在 ~/.openclaw/openclaw.json 的 models.providers 中配置千帆，"
            "或设置环境变量 DEEPSEEK_API_KEY"
        )
    return LLM_API_KEY

def call_llm(system_prompt: str, user_prompt: str, model: str = None,
             temperature: float = 0.7, max_tokens: int = None,
             response_format: Optional[Dict] = None,
             timeout: int = DEFAULT_TIMEOUT) -> str:
    _load_llm_config()
    api_key = LLM_API_KEY
    api_url = LLM_API_URL
    if model is None:
        model = DEFAULT_MODEL
    if max_tokens is None:
        max_tokens = DEFAULT_MAX_TOKENS

    # max_tokens 限制，超过 8192 容易失败
    if max_tokens > 8192:
        logger.warning(f"max_tokens {max_tokens} 过大，调整为 8192")
        max_tokens = 8192

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ], "temperature": temperature, "max_tokens": max_tokens}
    if response_format:
        payload["response_format"] = response_format

    logger.info(f"LLM 调用: {api_url} | 模型: {model} | max_tokens: {max_tokens}")
    import time as _time
    max_retries = 3
    for attempt in range(max_retries):
        try:
            resp = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429 and attempt < max_retries - 1:
                delay = LLM_RETRY_DELAY * (2 ** attempt)
                logger.warning(f"429 限流，{delay}秒后重试 ({attempt+1}/{max_retries})...")
                _time.sleep(delay)
                continue
            # 429 重试耗尽，切备选
            if e.response.status_code == 429 and FALLBACK_API_URL:
                logger.warning(f"千帆限流，切换到备选: {FALLBACK_MODEL}")
                fb_headers = {"Authorization": f"Bearer {FALLBACK_API_KEY}", "Content-Type": "application/json"}
                fb_payload = dict(payload, model=FALLBACK_MODEL)
                try:
                    fb_resp = requests.post(FALLBACK_API_URL, headers=fb_headers, json=fb_payload, timeout=timeout)
                    fb_resp.raise_for_status()
                    return fb_resp.json()["choices"][0]["message"]["content"].strip()
                except Exception as fb_e:
                    logger.error(f"备选也失败: {fb_e}")
                    raise
            logger.error(f"LLM 调用失败: {e}")
            raise
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            raise

def fetch_webpage_text(url: str) -> str:
    """抓取网页内容并提取可读文本（含 meta 兜底，适配 SPA）"""
    import re
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()

        # 自动检测编码
        content_type = resp.headers.get("content-type", "")
        if "charset=" in content_type:
            enc = content_type.split("charset=")[-1].split(";")[0].strip()
            resp.encoding = enc
        elif resp.apparent_encoding:
            resp.encoding = resp.apparent_encoding

        html = resp.text

        # 先尝试从 meta 提取（SPA 页面兜底）
        meta_title = re.search(r'<title>(.*?)</title>', html, re.DOTALL)
        meta_desc = re.search(
            r'<meta[^>]*name=["\']description["\'][^>]*content=["\'](.*?)["\']',
            html, re.DOTALL
        )
        if not meta_desc:
            meta_desc = re.search(
                r'<meta[^>]*content=["\'](.*?)["\'][^>]*name=["\']description["\']',
                html, re.DOTALL
            )
        meta_keywords = re.search(
            r'<meta[^>]*name=["\']keywords["\'][^>]*content=["\'](.*?)["\']',
            html, re.DOTALL
        )

        meta_parts = []
        if meta_title:
            meta_parts.append(f"网站标题：{meta_title.group(1).strip()}")
        if meta_desc:
            meta_parts.append(f"描述：{meta_desc.group(1).strip()}")
        if meta_keywords:
            meta_parts.append(f"关键词：{meta_keywords.group(1).strip()}")
        meta_text = "\n".join(meta_parts)

        # 清理 HTML 取可见文本
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
        text = re.sub(r'<nav[^>]*>.*?</nav>', '', text, flags=re.DOTALL)
        text = re.sub(r'<footer[^>]*>.*?</footer>', '', text, flags=re.DOTALL)
        text = re.sub(r'<header[^>]*>.*?</header>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'&[a-zA-Z]+;', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()

        # 如果可见文本太少，用 meta 信息替代
        if len(text) < 100 and meta_text:
            text = meta_text

        text = text[:3000]
        logger.info(f"抓取网页成功: {url} → {len(text)} 字符")
        return text
    except Exception as e:
        logger.warning(f"抓取网页失败: {url} -> {e}")
        return ""


def analyze_product(url: str, name: str = "") -> dict:
    """
    第一步：抓取网页内容 → LLM 提取结构化产品信息
    返回: {"product_name", "positioning", "core_features", "characteristics"}
    """
    # 先抓取网页
    page_text = fetch_webpage_text(url)

    prompt = f"""根据网页内容，提取这个产品的关键信息，按格式输出JSON。

产品链接：{url}
产品名称参考：{name or "未知"}

网页内容：
{page_text[:2500] if page_text else "（无法抓取）"}

输出格式：
{{
  "product_name": "产品名称",
  "positioning": "产品定位（一句话说明这是做什么的）",
  "core_features": "核心功能说明",
  "characteristics": ["特点1", "特点2", "特点3", "特点4"]
}}
"""
    logger.info(f"分析产品: {url}")
    result = call_llm_json(
        system_prompt="你是一个信息提取专家，从网页内容中提取产品关键信息，不要编造网页中没有的内容。",
        user_prompt=prompt,
        temperature=0.2,
        max_tokens=2048,
    )
    logger.info(f"分析结果: {result.get('product_name', '未知')}")
    return result


SCRIPT_DIR = Path(__file__).parent.absolute()
TEMPLATES_DIR = SCRIPT_DIR / ".." / "templates"
USER_PROMPT_FILE = TEMPLATES_DIR / "user-article-prompt.md"


def build_writing_prompt(product_info: dict, product_url: str = "") -> str:
    """从模板文件读取提示词，填入产品信息和链接"""
    fp = USER_PROMPT_FILE
    if not fp.exists():
        logger.warning(f"用户提示词模板未找到: {fp}，使用内置模板")
        fp = TEMPLATES_DIR / "short-article-prompt.md"

    template = fp.read_text(encoding="utf-8")
    chars = "\n  - ".join(product_info.get("characteristics", []))

    return (template
            .replace("{{product_name}}", product_info.get("product_name", ""))
            .replace("{{positioning}}", product_info.get("positioning", ""))
            .replace("{{core_features}}", product_info.get("core_features", ""))
            .replace("{{characteristics}}", chars)
            .replace("{{product_url}}", product_url))


def call_llm_json(*args, **kwargs) -> dict:
    # 不用 response_format=json_object 约束，避免模型截断输出
    # 提示词已要求输出JSON，模型会自动遵循
    content = call_llm(*args, **kwargs)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        import re
        m = re.search(r'\{.*\}', content, re.DOTALL)
        if m:
            return json.loads(m.group())
        raise ValueError(f"LLM 返回非 JSON: {content[:100]}")

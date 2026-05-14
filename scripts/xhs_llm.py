import json, logging, os, requests
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# ── 千帆 LLM 配置（从 openclaw.json 自动读取）────
LLM_API_URL = None
LLM_API_KEY = None
DEFAULT_MODEL = "qianfan-code-latest"
DEFAULT_MAX_TOKENS = 8192
DEFAULT_TIMEOUT = 180

def _load_llm_config():
    """从 openclaw.json 读取千帆 LLM 配置"""
    global LLM_API_URL, LLM_API_KEY
    if LLM_API_URL and LLM_API_KEY:
        return
    try:
        cfg = os.path.expanduser("~/.openclaw/openclaw.json")
        if os.path.exists(cfg):
            with open(cfg) as f:
                data = json.load(f)
            providers = data.get("models", {}).get("providers", {})
            for provider_id, p in providers.items():
                if "qianfan" in provider_id.lower() or "baidu" in provider_id.lower():
                    LLM_API_URL = p.get("baseUrl", "") + "/chat/completions"
                    LLM_API_KEY = p.get("apiKey", "")
                    models = p.get("models", [])
                    if models:
                        global DEFAULT_MODEL
                        DEFAULT_MODEL = models[0].get("id", "qianfan-code-latest")
                    logger.info(f"LLM 配置: {LLM_API_URL} | 模型: {DEFAULT_MODEL}")
                    return
    except Exception as e:
        logger.debug(f"读取 openclaw.json LLM 配置失败: {e}")

    # fallback: 环境变量 / DeepSeek 兼容
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

    # 千帆 API 的 max_tokens 限制，超过 8192 容易失败
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
    try:
        resp = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"LLM 调用失败: {e}")
        raise

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

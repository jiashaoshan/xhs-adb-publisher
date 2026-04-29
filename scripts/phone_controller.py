"""
Phone Controller — 通过 ADB 操控 Android 手机的核心模块
封装了 uiautomator2 的基本操作和小红书发布流程

所有 time.sleep 加入了随机抖动 (±20%) 以模拟真人操作节奏
"""
import uiautomator2 as u2
import time, os, random, logging

logger = logging.getLogger(__name__)
_DEVICE = None

def jitter(sec: float, ratio: float = 0.2) -> float:
    """带随机抖动的 sleep: sec * (1 ± ratio)"""
    actual = sec * (1 + random.uniform(-ratio, ratio))
    time.sleep(max(actual, 0.1))
    return actual

def get_device():
    global _DEVICE
    if _DEVICE is None:
        serial = os.environ.get("ANDROID_SERIAL")
        _DEVICE = u2.connect(serial) if serial else u2.connect()
    return _DEVICE

# ── 基础操作 ──────────────────────────────────────────

def home():
    get_device().press("home"); jitter(0.3)

def tap(x, y):
    get_device().click(int(x), int(y))

def send_text(text):
    get_device().send_keys(text)

def press_key(key):
    get_device().press(key)

# ── 小红书发布流程 ────────────────────────────────────

def open_xhs():
    d = get_device()
    d.press("home"); jitter(0.5)
    d.app_start("com.xingin.xhs"); jitter(3, 0.1)  # app启动少抖
    d.click(540, 2284); jitter(1.5)  # +号
    return d

def click_xie_wenzi(d=None):
    d = d or get_device()
    d.click(540, 2079); jitter(1.5)

def card_style_to_publish(d=None):
    d = d or get_device()
    jitter(1.5)
    for _ in range(30):
        if not d(text="图片生成中").exists(timeout=0.5):
            break
        jitter(0.5)
    btns = list(d(text="下一步", className="android.widget.TextView"))
    if btns:
        btns[-1].click()
    else:
        d.click(897, 2226)
    jitter(2)

def set_visibility_and_publish(d=None):
    d = d or get_device()
    d.click(204, 1842); jitter(0.8)     # 公开可见
    jitter(0.3)
    d.click(297, 2232); jitter(0.5)     # 仅自己可见
    jitter(0.5)
    d.click(687, 2211); jitter(2.5)     # 发布笔记
    d.press("home"); jitter(0.5)
    d.press("home")

# ── 写想法 ─────────────────────────────────────────

def xie_xie_fa(content, title="测试标题"):
    d = open_xhs()
    click_xie_wenzi(d)
    d.click(540, 1000); jitter(0.3)
    d.send_keys(content); jitter(0.3)
    btns = list(d(text="下一步", className="android.widget.TextView"))
    btns[0].click() if btns else d.click(920, 176)
    card_style_to_publish(d)
    d.click(562, 629); jitter(0.3)
    d.send_keys(title); jitter(0.3)
    set_visibility_and_publish(d)

# ── 写长文 ─────────────────────────────────────────

def xie_chang_wen(editor_body, publish_body="", title=""):
    d = open_xhs()
    click_xie_wenzi(d)
    d.click(375, 1931); jitter(2)       # 写长文
    if title:
        d.click(200, 300); jitter(0.3)
        d.send_keys(title); jitter(0.3)
    d.click(540, 600); jitter(0.3)
    d.send_keys(editor_body); jitter(0.3)
    logger.info("一键排版中...")
    d.click(540, 2232); jitter(3)        # 一键排版
    templates = ["清晰明朗", "简约基础", "灵感备忘", "涂鸦马克", "素雅底纹"]
    for t in templates:
        try:
            el = d(text=t)
            if el.exists(timeout=0.5):
                el.click(); logger.info(f"选择模板: {t}"); jitter(0.3); break
        except: pass
    btns = list(d(text="下一步", className="android.widget.TextView"))
    btns[-1].click() if btns else d.click(897, 2256)
    jitter(2)
    if publish_body:
        d.click(540, 752); jitter(0.8)
        d.send_keys(publish_body); jitter(0.3)
    set_visibility_and_publish(d)

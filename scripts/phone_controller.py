"""
Phone Controller — 通过 ADB 操控 Android 手机的核心模块
封装了 uiautomator2 的基本操作和小红书发布流程

✅ 支持多设备：所有函数接受 device 参数，不依赖全局单例
✅ 所有 time.sleep 加入了随机抖动 (±20%) 以模拟真人操作节奏
"""
import uiautomator2 as u2
import time, os, random, logging, threading

logger = logging.getLogger(__name__)

# 设备缓存 {serial: device}
_device_pool = {}
_device_pool_lock = threading.Lock()

def jitter(sec: float, ratio: float = 0.2) -> float:
    """带随机抖动的 sleep: sec * (1 ± ratio)"""
    actual = sec * (1 + random.uniform(-ratio, ratio))
    time.sleep(max(actual, 0.1))
    return actual

# 参考屏幕尺寸 (OnePlus PGCM10)
REF_W, REF_H = 1080, 2400

def get_device(serial: str = None) -> u2.Device:
    """
    获取指定 serial 的设备连接，带缓存。
    不传 serial 时读取环境变量 ANDROID_SERIAL 或连接唯一设备。
    """
    global _device_pool, _device_pool_lock
    serial = serial or os.environ.get("ANDROID_SERIAL")
    key = serial or "__default__"

    with _device_pool_lock:
        if key not in _device_pool:
            d = u2.connect(serial) if serial else u2.connect()
            _device_pool[key] = d
            logger.info(f"连接设备 {key} | 分辨率 {d.info.get('displayWidth')}x{d.info.get('displayHeight')}")
        return _device_pool[key]

def _scale(d: u2.Device, x: int, y: int) -> tuple:
    """按比例缩放坐标到目标设备分辨率"""
    info = d.info
    sw = info.get('displayWidth', REF_W)
    sh = info.get('displayHeight', REF_H)
    return int(x * sw / REF_W), int(y * sh / REF_H)

def home(device: u2.Device = None):
    (device or get_device()).press("home"); jitter(0.3)

def tap(x: int, y: int, device: u2.Device = None):
    device = device or get_device()
    device.click(*_scale(device, x, y))

def send_text(text: str, device: u2.Device = None):
    (device or get_device()).send_keys(text)

def press_key(key: str, device: u2.Device = None):
    (device or get_device()).press(key)

def open_xhs(device: u2.Device = None) -> u2.Device:
    """
    打开小红书并点击底部 + 号
    返回 device 对象便于链式调用
    """
    d = device or get_device()
    d.press("home"); jitter(0.5)
    d.app_start("com.xingin.xhs"); jitter(3, 0.1)
    d.click(*_scale(d, 540, 2284)); jitter(1.5)
    return d

def click_xie_wenzi(device: u2.Device = None):
    d = device or get_device()
    d.click(*_scale(d, 540, 2079)); jitter(1.5)

def card_style_to_publish(device: u2.Device = None):
    d = device or get_device()
    jitter(1.5)
    for _ in range(30):
        if not d(text="图片生成中").exists(timeout=0.5):
            break
        jitter(0.5)
    btns = list(d(text="下一步", className="android.widget.TextView"))
    if btns: btns[-1].click()
    else: d.click(*_scale(d, 897, 2226))
    jitter(2)

def set_visibility_and_publish(device: u2.Device = None):
    d = device or get_device()
    d.click(*_scale(d, 204, 1842)); jitter(0.8)
    jitter(0.3)
    d.click(*_scale(d, 297, 2232)); jitter(0.5)
    jitter(0.5)
    d.click(*_scale(d, 687, 2211)); jitter(3)
    for _ in range(3):
        d.press("home"); jitter(0.3)

def xie_xie_fa(content: str, title: str = "测试标题", serial: str = None):
    """写想法（纯文字直发）"""
    d = get_device(serial)
    open_xhs(d)
    click_xie_wenzi(d)
    d.click(*_scale(d, 540, 1000)); jitter(0.3)
    d.send_keys(content); jitter(0.3)
    btns = list(d(text="下一步", className="android.widget.TextView"))
    btns[0].click() if btns else d.click(*_scale(d, 920, 176))
    card_style_to_publish(d)
    d.click(*_scale(d, 562, 629)); jitter(0.3)
    d.send_keys(title); jitter(0.3)
    set_visibility_and_publish(d)

def xie_chang_wen(editor_body: str, publish_body: str = "", title: str = "",
                  serial: str = None):
    """写长文（含一键排版、发布确认页正文）"""
    d = get_device(serial)
    open_xhs(d)
    click_xie_wenzi(d)
    d.click(*_scale(d, 375, 1931)); jitter(2)
    if title:
        d.click(*_scale(d, 200, 300)); jitter(0.3)
        d.send_keys(title); jitter(0.3)
    d.click(*_scale(d, 540, 600)); jitter(0.3)
    d.send_keys(editor_body); jitter(0.3)
    logger.info("一键排版中...")
    d.click(*_scale(d, 540, 2232)); jitter(3)
    templates = ["清晰明朗", "简约基础", "灵感备忘", "涂鸦马克", "素雅底纹"]
    for t in templates:
        try:
            el = d(text=t)
            if el.exists(timeout=0.5):
                el.click(); logger.info(f"选择模板: {t}"); jitter(0.3); break
        except:
            pass
    btns = list(d(text="下一步", className="android.widget.TextView"))
    btns[-1].click() if btns else d.click(*_scale(d, 897, 2256))

    # 等发布确认页预览渲染完成
    jitter(8, 0.1)
    for _ in range(20):
        if not d(text="图片生成中").exists(timeout=0.3):
            break
        jitter(0.3)

    if publish_body:
        d.click(*_scale(d, 540, 752)); jitter(0.5)
        d.send_keys(publish_body); jitter(0.5)

    set_visibility_and_publish(d)
    d.app_stop('com.xingin.xhs')
    logger.info("关闭小红书后台")


def publish_article(serial: str, product_url: str, article: dict) -> dict:
    """
    在指定设备上执行完整发布流程（LLM + ADB）。

    设计用于多设备并发调用，内部调用 xhs_article_publisher.run()
    但通过 serial 参数区分设备连接。

    Args:
        serial: Android 设备序列号
        product_url: 产品链接
        article: 已生成的文章内容（含 title, editor_body, xhs_body）
    """
    title = article.get("title", "")
    editor_body = article.get("editor_body", "")
    xhs_body = article.get("xhs_body", "")

    logger.info(f"[{serial}] 开始发布: {title}")

    try:
        xie_chang_wen(
            editor_body=editor_body,
            publish_body=xhs_body,
            title=title,
            serial=serial,
        )
        result = {
            "serial": serial,
            "status": "published",
            "title": title,
            "product_url": product_url,
        }
        logger.info(f"[{serial}] ✅ 发布成功: {title}")
    except Exception as e:
        result = {
            "serial": serial,
            "status": "failed",
            "title": title,
            "error": str(e),
        }
        logger.error(f"[{serial}] ❌ 发布失败: {e}")

    return result

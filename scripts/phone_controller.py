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

REF_W, REF_H = 1080, 2400

def _scale(d: u2.Device, x: int, y: int) -> tuple:
    """按比例缩放坐标到目标设备分辨率"""
    info = d.info
    sw = info.get('displayWidth', REF_W)
    sh = info.get('displayHeight', REF_H)
    return int(x * sw / REF_W), int(y * sh / REF_H)

def get_device(serial: str = None) -> u2.Device:
    global _device_pool, _device_pool_lock
    serial = serial or os.environ.get("ANDROID_SERIAL")
    key = serial or "__default__"
    with _device_pool_lock:
        if key not in _device_pool:
            d = u2.connect(serial) if serial else u2.connect()
            _device_pool[key] = d
            logger.info(f"连接设备 {key} | 分辨率 {d.info.get('displayWidth')}x{d.info.get('displayHeight')}")
        return _device_pool[key]

def home(device: u2.Device = None):
    (device or get_device()).press("home"); jitter(0.3)

def send_text(text: str, device: u2.Device = None):
    (device or get_device()).send_keys(text)

def press_key(key: str, device: u2.Device = None):
    (device or get_device()).press(key)

def open_xhs(device: u2.Device = None) -> u2.Device:
    d = device or get_device()
    d.press("home"); jitter(0.5)
    d.app_start("com.xingin.xhs"); jitter(3, 0.1)
    # 关闭草稿弹窗
    for txt in ["存草稿", "不保存"]:
        el = d(textContains=txt)
        if el.exists(timeout=1):
            el.click(); jitter(1)
            break
    # 底部+号：坐标540,2284（底部导航栏中间）
    d.click(int(d.info.get("displayWidth",1080))/2, int(d.info.get("displayHeight",2400))*0.95)
    jitter(2)
    return d

def click_xie_wenzi(device: u2.Device = None):
    d = device or get_device()
    el = d(text="写文字")
    if el.exists(timeout=1):
        el.click()
    else:
        d.click(int(d.info.get("displayWidth",1080))/2, int(d.info.get("displayHeight",2400))*0.86)
    jitter(1.5)

def card_style_to_publish(device: u2.Device = None):
    d = device or get_device()
    jitter(1.5)
    for _ in range(30):
        if not d(text="图片生成中").exists(timeout=0.5):
            break
        jitter(0.5)
    # 等待"下一步"按钮出现
    for _ in range(10):
        btns = list(d(text="下一步"))
        if btns:
            btns[-1].click()
            break
        jitter(0.5)
    jitter(2)

def set_visibility_and_publish(device: u2.Device = None):
    d = device or get_device()
    # 点击可见性设置区（"公开可见"文本）
    el = d(textContains="公开可见")
    if el.exists(timeout=2):
        el.click(); logger.info("点击: 公开可见")
    else:
        # fallback到坐标
        d.click(*_scale(d, 204, 1842)); logger.info("坐标点击可见性")
    jitter(1)
    # 弹出菜单中选择"仅自己可见"
    el = d(text="仅自己可见")
    if el.exists(timeout=2):
        el.click(); logger.info("选择: 仅自己可见")
    else:
        d.click(*_scale(d, 297, 2232)); logger.info("坐标选择可见性")
    jitter(0.5)
    # 点击"发布笔记"按钮
    el = d(text="发布笔记")
    if el.exists(timeout=2):
        el.click(); logger.info("点击: 发布笔记")
    else:
        sw = d.info.get('displayWidth', REF_W)
        sh = d.info.get('displayHeight', REF_H)
        d.click(int(sw * 0.65), int(sh * 0.92))
        logger.info("坐标点击发布")
    jitter(3)
    for _ in range(3):
        d.press("home"); jitter(0.3)

def xie_xie_fa(content: str, title: str = "测试标题", serial: str = None):
    """写想法（纯文字直发）"""
    d = get_device(serial)
    open_xhs(d)
    click_xie_wenzi(d)
    # 点击正文输入区
    d.click(int(d.info.get("displayWidth",1080))/2, int(d.info.get("displayHeight",2400))*0.42)
    jitter(0.3)
    d.send_keys(content); jitter(0.3)
    btns = list(d(text="下一步"))
    btns[0].click() if btns else card_style_to_publish(d)
    card_style_to_publish(d)
    # 标题输入区
    d.click(int(d.info.get("displayWidth",1080))/2, int(d.info.get("displayHeight",2400))*0.26)
    jitter(0.3)
    d.send_keys(title); jitter(0.3)
    set_visibility_and_publish(d)

def xie_chang_wen(editor_body: str, publish_body: str = "", title: str = "",
                  serial: str = None):
    """写长文（含一键排版、发布确认页正文）"""
    d = get_device(serial)
    open_xhs(d)
    click_xie_wenzi(d)
    # 点击"写长文"
    el = d(text="写长文")
    if el.exists(timeout=2):
        el.click()
    else:
        for txt in ["长文"]:
            el = d(textContains=txt)
            if el.exists(timeout=1):
                el.click(); break
    jitter(2)
    if title:
        # 通过文本查找"输入标题"
        el = d(text="输入标题")
        if el.exists(timeout=2):
            el.click(); jitter(0.3)
            d.send_keys(title); jitter(0.3)
    # 点击正文编辑区
    d.click(int(d.info.get("displayWidth",1080))/2, int(d.info.get("displayHeight",2400))*0.25)
    jitter(0.3)
    chunk_size = 500
    for i in range(0, len(editor_body), chunk_size):
        chunk = editor_body[i:i+chunk_size]
        d.send_keys(chunk); jitter(0.2)
    jitter(0.3)
    logger.info("一键排版中...")
    el = d(text="一键排版")
    if el.exists(timeout=3):
        el.click(); logger.info("点击一键排版")
    # 固定等待15秒（确保排版渲染完成，包括生成封面和摘要）
    logger.info("等待排版渲染中...")
    jitter(15, 0.1)
    # 额外等待"图片生成中"消失
    for _ in range(20):
        if not d(text="图片生成中").exists(timeout=0.5):
            break
        jitter(0.5)
    jitter(2)
    # 点击"下一步"
    for _ in range(10):
        btns = list(d(text="下一步"))
        if btns:
            btns[-1].click(); logger.info("点击下一步"); break
        # 同时检查是否有"选择喜欢的排版" - 如果有说明还在模板页
        if d(textContains="选择喜欢的排版").exists(timeout=0.3):
            logger.info("仍在模板选择页，再点一次模板")
            for t in ["涂鸦马克"]:
                el = d(text=t)
                if el.exists(timeout=0.3):
                    el.click(); break
            break
        jitter(0.5)
    # 如果还在模板选择页，再等渲染后点下一步
    for _ in range(5):
        if d(textContains="选择喜欢的排版").exists(timeout=0.3):
            jitter(2)
            btns = list(d(text="下一步"))
            if btns:
                btns[-1].click(); logger.info("模板页再点下一步"); break
        else:
            break
    # 等发布确认页渲染
    jitter(8, 0.1)
    for _ in range(20):
        if not d(text="图片生成中").exists(timeout=0.3):
            break
        jitter(0.3)
    # 发布确认页正文
    if publish_body:
        el = d(text="添加正文")
        if el.exists(timeout=2):
            el.click(); jitter(0.5)
            d.send_keys(publish_body); jitter(0.5)
    set_visibility_and_publish(d)
    d.app_stop('com.xingin.xhs')
    logger.info("关闭小红书后台")


def publish_article(serial: str, product_url: str, article: dict) -> dict:
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

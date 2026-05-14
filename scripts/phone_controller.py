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
    jitter(8)
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
    jitter(24, 0.1)
    # 额外等待"图片生成中"消失
    for _ in range(20):
        if not d(text="图片生成中").exists(timeout=0.5):
            break
        jitter(0.5)
    jitter(2)
    # 点击"下一步"（从卡片样式页到模板选择/发布确认页）
    for _ in range(10):
        btns = list(d(text="下一步"))
        if btns:
            btns[-1].click(); logger.info("点击下一步"); break
        jitter(0.5)
    jitter(2)
    # 检测并处理模板选择页
    for _ in range(8):
        if d(textContains="选择喜欢的排版").exists(timeout=0.3):
            logger.info("仍在模板选择页")
            # 先选一个模板
            for tpl in ["涂鸦马克"]:
                el = d(text=tpl)
                if el.exists(timeout=0.3):
                    el.click(); logger.info(f"选择模板: {tpl}"); break
            jitter(1)
            # 再点下一步
            btns = list(d(text="下一步"))
            if btns:
                btns[-1].click(); logger.info("模板页点击下一步")
            jitter(2)
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
        found = False
        for txt in ["添加正文或发语音", "添加正文"]:
            el = d(textContains=txt)
            if el.exists(timeout=1):
                el.click(); jitter(0.5); found = True; break
        if found:
            d.send_keys(publish_body); jitter(0.5)
            logger.info(f"输入发布确认页正文: {len(publish_body)}字")
        else:
            # fallback: 直接点击正文区域
            sh = d.info.get('displayHeight', 2400)
            d.click(int(d.info.get('displayWidth',1080))/2, int(sh*0.5))
            jitter(0.3)
            d.send_keys(publish_body); jitter(0.3)
    set_visibility_and_publish(d)
    d.app_stop('com.xingin.xhs')
    logger.info("关闭小红书后台")


def insert_images_to_editor(image_count: int = 3, serial: str = None, d: u2.Device = None):
    """
    在长文编辑器中插入图片
    流程: 点击底部工具栏图库按钮 → 选择相册 → 选择图片 → 确认
    
    小红书8.78版本编辑器底部工具栏布局:
    - 左起: 图库(图片图标) | 拍照 | 模版 | ... | 键盘
    """
    device = d or get_device(serial)
    logger.info(f"开始插入 {image_count} 张图片到编辑器...")
    sw = device.info.get('displayWidth', REF_W)
    sh = device.info.get('displayHeight', REF_H)

    # 先上滑一点点，确保键盘收起 → 露出底部工具栏
    device.swipe(sw // 2, sh // 2, sw // 2, sh // 3, duration=0.2)
    jitter(0.5)

    for i in range(image_count):
        logger.info(f"插入第 {i+1}/{image_count} 张图片...")

        # 点击底部工具栏的"图库"按钮
        # 小红书编辑器的图片按钮通常在最底层底部工具栏，x 靠近左边
        # 尝试descripton搜索
        clicked = False
        for desc in ["图库", "图片", "相册", "添加图片"]:
            el = device(description=desc)
            if el.exists(timeout=1):
                el.click()
                clicked = True
                logger.info(f"点击: {desc}")
                break

        if not clicked:
            # 坐标方式点底部工具栏第一个图标（图库按钮）
            # 底部工具栏 ~y=sh*0.93，图库按钮在 ~x=sw*0.15
            positions = [
                (sw * 0.12, sh * 0.93),
                (sw * 0.20, sh * 0.93),
                (sw * 0.28, sh * 0.93),
            ]
            for x, y in positions:
                device.click(int(x), int(y))
                jitter(0.8)
                # 检查是否打开了相册/图片选择界面
                if device(textContains="相册").exists(timeout=1) or \
                   device(textContains="选择").exists(timeout=1) or \
                   device(text="所有照片").exists(timeout=1) or \
                   device(text="最近项目").exists(timeout=1):
                    clicked = True
                    logger.info(f"打开图库: ({x:.0f}, {y:.0f})")
                    break

        if not clicked:
            logger.warning("未找到图片插入按钮，跳过")
            return False

        jitter(1.5)

        # 已进入相册选择界面，选择第i张照片
        # 小红书相册网格: 3列，每行相同高度
        grid_cols = 3
        grid_start_y = sh * 0.18
        item_size = sw / grid_cols
        row = i // grid_cols
        col = i % grid_cols
        x = int(item_size * (col + 0.5))
        y = int(grid_start_y + item_size * (row + 0.5))
        device.click(x, y)
        logger.info(f"选择图片 {i+1}/{image_count}")
        jitter(1)

        # 确认选择（点击图片后可能自动返回编辑器）
        for txt in ["下一步", "完成", "确定"]:
            el = device(text=txt)
            if el.exists(timeout=1):
                el.click()
                logger.info(f"确认: {txt}")
                jitter(1)
                break

        jitter(2)

    # 插入完成后，点击正文区域继续
    device.click(sw // 2, int(sh * 0.4))
    jitter(0.5)
    logger.info("图片插入完成")
    return True


def xie_chang_wen_with_images(
    editor_body: str,
    publish_body: str = "",
    title: str = "",
    image_count: int = 0,
    serial: str = None
):
    """写长文（含图片插入）"""
    d = get_device(serial)
    open_xhs(d)
    click_xie_wenzi(d)

    el = d(text="写长文")
    if el.exists(timeout=2):
        el.click()
    else:
        for txt in ["长文"]:
            el = d(textContains=txt)
            if el.exists(timeout=1):
                el.click()
                break
    jitter(2)

    if title:
        el = d(text="输入标题")
        if el.exists(timeout=2):
            el.click()
            jitter(0.3)
            d.send_keys(title)
            jitter(0.3)

    # 点击正文编辑区
    d.click(int(d.info.get("displayWidth",1080))/2, int(d.info.get("displayHeight",2400))*0.25)
    jitter(0.3)

    # 插入图片
    if image_count > 0:
        insert_images_to_editor(image_count, serial, d)
        d.click(int(d.info.get("displayWidth",1080))/2, int(d.info.get("displayHeight",2400))*0.25)
        jitter(0.5)

    # 输入正文
    chunk_size = 500
    for i in range(0, len(editor_body), chunk_size):
        chunk = editor_body[i:i+chunk_size]
        d.send_keys(chunk)
        jitter(0.2)
    jitter(0.3)

    logger.info("一键排版中...")
    el = d(text="一键排版")
    if el.exists(timeout=3):
        el.click()
        logger.info("点击一键排版")

    logger.info("等待排版渲染中...")
    jitter(24, 0.1)

    for _ in range(20):
        if not d(text="图片生成中").exists(timeout=0.5):
            break
        jitter(0.5)
    jitter(2)

    for _ in range(10):
        btns = list(d(text="下一步"))
        if btns:
            btns[-1].click()
            logger.info("点击下一步")
            break
        jitter(0.5)
    jitter(2)
    # 检测并处理模板选择页
    for _ in range(8):
        if d(textContains="选择喜欢的排版").exists(timeout=0.3):
            logger.info("仍在模板选择页")
            for tpl in ["涂鸦马克"]:
                el = d(text=tpl)
                if el.exists(timeout=0.3):
                    el.click()
                    logger.info(f"选择模板: {tpl}")
                    break
            jitter(1)
            btns = list(d(text="下一步"))
            if btns:
                btns[-1].click()
                logger.info("模板页点击下一步")
            jitter(2)
        else:
            break

    jitter(8, 0.1)
    for _ in range(20):
        if not d(text="图片生成中").exists(timeout=0.3):
            break
        jitter(0.3)

    if publish_body:
        found = False
        for txt in ["添加正文或发语音", "添加正文"]:
            el = d(textContains=txt)
            if el.exists(timeout=1):
                el.click()
                jitter(0.5)
                found = True
                break
        if found:
            d.send_keys(publish_body)
            jitter(0.5)
            logger.info(f"输入发布确认页正文: {len(publish_body)}字")
        else:
            sh = d.info.get('displayHeight', 2400)
            d.click(int(d.info.get('displayWidth',1080))/2, int(sh*0.5))
            jitter(0.3)
            d.send_keys(publish_body)
            jitter(0.3)

    set_visibility_and_publish(d)
    d.app_stop('com.xingin.xhs')
    logger.info("关闭小红书后台")


def publish_article(serial: str, product_url: str, article: dict, image_count: int = 0) -> dict:
    """发布文章，支持图片"""
    title = article.get("title", "")
    editor_body = article.get("editor_body", "")
    xhs_body = article.get("xhs_body", "")
    logger.info(f"[{serial}] 开始发布: {title}, 图片: {image_count}张")
    try:
        if image_count > 0:
            xie_chang_wen_with_images(
                editor_body=editor_body,
                publish_body=xhs_body,
                title=title,
                image_count=image_count,
                serial=serial,
            )
        else:
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
            "image_count": image_count,
        }
        logger.info(f"[{serial}] ✅ 发布成功: {title}")
    except Exception as e:
        result = {
            "serial": serial,
            "status": "failed",
            "title": title,
            "error": str(e),
            "image_count": image_count,
        }
        logger.error(f"[{serial}] ❌ 发布失败: {e}")
    return result

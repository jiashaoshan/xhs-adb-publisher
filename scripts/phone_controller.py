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
            # 确保 ATX Keyboard 是默认输入法（中文输入必须）
            ensure_atx_keyboard(d, key)
        return _device_pool[key]


def ensure_atx_keyboard(d: u2.Device, key: str = ""):
    """确保 ATX Keyboard 设置为默认输入法，否则 send_keys 无法输入中文"""
    try:
        current_ime = d.shell("settings get secure default_input_method").output.strip()
        logger.info(f"[{key}] 当前输入法: {current_ime}")
        if "atx" in current_ime.lower() or "adbkeyboard" in current_ime.lower():
            logger.info(f"[{key}] ✅ ATX Keyboard 已为默认输入法")
            return
        logger.info(f"[{key}] 设置 ATX Keyboard 为默认输入法...")
        # 方式1: ime set
        d.shell("ime enable com.github.uiautomator/.AdbKeyboardService")
        d.shell("ime set com.github.uiautomator/.AdbKeyboardService")
        time.sleep(0.5)
        after = d.shell("settings get secure default_input_method").output.strip()
        if "atx" in after.lower() or "adbkeyboard" in after.lower():
            logger.info(f"[{key}] ✅ ATX Keyboard 设置成功")
            return
        # 方式2: settings put (ColorOS 绕过)
        logger.info(f"[{key}] ime set 被拦截，用 settings put...")
        d.shell("settings put secure default_input_method com.github.uiautomator/.AdbKeyboardService")
        time.sleep(0.5)
        after = d.shell("settings get secure default_input_method").output.strip()
        if "atx" in after.lower() or "adbkeyboard" in after.lower():
            logger.info(f"[{key}] ✅ settings put 设置成功")
            return
        # 方式3: set_fasttext_ime (uiautomator2 内置)
        logger.info(f"[{key}] 尝试 set_fasttext_ime...")
        try:
            d.set_fasttext_ime()
            logger.info(f"[{key}] ✅ set_fasttext_ime 成功")
        except Exception as e2:
            logger.warning(f"[{key}] ❌ 自动设置均失败(ColorOS限制): {e2}")
            logger.warning(f"[{key}] 请手动: 设置→其他设置→键盘与输入法→默认输入法→ATX Keyboard")
    except Exception as e:
        logger.warning(f"[{key}] ⚠️ 设置输入法出错: {e}")

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
    """确保公开可见 + 发布笔记"""
    d = device or get_device()
    logger.info("确认可见范围: 公开可见")

    # 检查当前是否显示"公开可见"（默认就是公开，无需改动）
    el = d(textContains="公开可见")
    if el.exists(timeout=2):
        logger.info("已是公开可见")
    else:
        # 如果当前是"仅自己可见"，点开切换
        el = d(textContains="仅自己可见")
        if el.exists(timeout=2):
            el.click()
            logger.info("点击: 仅自己可见（准备切换）")
            jitter(1)
            # 弹出菜单中选择"公开可见"
            for pub_text in ["公开可见", "公开", "所有人可见"]:
                pub_el = d(text=pub_text)
                if pub_el.exists(timeout=1):
                    pub_el.click()
                    logger.info(f"选择: {pub_text}")
                    jitter(0.5)
                    break
        else:
            # 找不到可见性设置，尝试坐标点击
            d.click(*_scale(d, 174, 1765))
            logger.info("坐标点击可见性区域")
            jitter(1)
            for pub_text in ["公开可见", "公开", "所有人可见"]:
                pub_el = d(text=pub_text)
                if pub_el.exists(timeout=1):
                    pub_el.click()
                    logger.info(f"选择: {pub_text}")
                    jitter(0.5)
                    break

    # 点击"发布笔记"按钮
    el = d(text="发布笔记")
    if el.exists(timeout=2):
        el.click(); logger.info("点击: 发布笔记")
    else:
        d.click(*_scale(d, 688, 2239))
        logger.info("坐标点击发布")
    jitter(15)
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


def publish_article(serial: str, product_url: str, article: dict, image_count: int = 0) -> dict:
    """发布文章"""
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


def publish_image_article(serial: str, title: str, xhs_body: str, image_count: int = 1) -> dict:
    """
    发布图文笔记（从相册选择图片）
    
    流程:
    桌面 → 打开小红书 → 点击+号 → 从相册选择
    → 选择图片 → 下一步（等待5s）→ 下一步
    → 在'添加标题'处输入标题（等待3s）
    → 在'添加正文或发语音'处输入正文
    → 直接点击'发布笔记' → 等待15s → 3下home回桌面
    """
    d = get_device(serial)
    
    logger.info(f"[{serial}] 开始发布图文: {title}")
    
    # 回到桌面并打开小红书
    d.press("home")
    jitter(0.5)
    d.app_start("com.xingin.xhs")
    jitter(3, 0.1)
    
    # 处理草稿弹窗
    for txt in ["存草稿", "不保存"]:
        el = d(textContains=txt)
        if el.exists(timeout=1):
            el.click()
            jitter(1)
            break
    
    # 点击底部+号
    sw = d.info.get("displayWidth", 1080)
    sh = d.info.get("displayHeight", 2400)
    d.click(sw / 2, sh * 0.95)
    logger.info("点击 +号")
    jitter(2)
    
    # 点击"从相册选择"
    el = d(text="从相册选择")
    if el.exists(timeout=2):
        el.click()
        logger.info("点击: 从相册选择")
    else:
        for txt in ["相册", "选择照片"]:
            el = d(textContains=txt)
            if el.exists(timeout=1):
                el.click()
                logger.info(f"点击: {txt}")
                break
        else:
            d.click(sw / 2, sh * 0.75)
            logger.info("坐标点击相册区域")
    jitter(2)
    
    # 选择图片（点击右上角对勾）
    logger.info(f"选择 {image_count} 张图片...")
    selected = 0
    for i in range(image_count):
        row = i // 3
        col = i % 3
        cell_cx = 180 + col * 360
        cell_cy = 650 + row * 360
        check_x = cell_cx + 80
        check_y = cell_cy - 120
        
        sx, sy = _scale(d, check_x, check_y)
        d.click(sx, sy)
        logger.info(f"  点击第{i+1}张图对勾: ({sx}, {sy})")
        jitter(0.4)
        selected += 1
        if selected >= image_count:
            break
    
    logger.info(f"已选择 {selected} 张图片")
    jitter(1)
    
    # 点击"下一步"（进入编辑页）
    for _ in range(5):
        btns = list(d(text="下一步"))
        if btns:
            btns[-1].click()
            logger.info("点击: 下一步（进入编辑页）")
            break
        jitter(0.5)
    
    # 等待5秒确保编辑页渲染完成
    logger.info("等待编辑页渲染（5秒）...")
    jitter(5, 0.1)
    
    # 再次点击"下一步"（进入发布确认页）
    for _ in range(5):
        btns = list(d(text="下一步"))
        if btns:
            btns[-1].click()
            logger.info("点击: 下一步（进入发布确认页）")
            break
        jitter(0.5)
    
    # 等待发布确认页完全渲染（10秒）
    logger.info("等待发布确认页渲染（10秒）...")
    jitter(10, 0.1)
    
    # 查找EditText（多次尝试，防止ATX缓存问题）
    edit_texts = []
    for retry in range(3):
        edit_texts = list(d(className="android.widget.EditText"))
        if len(edit_texts) >= 2:
            logger.info(f"找到 {len(edit_texts)} 个EditText")
            break
        if retry < 2:
            logger.info(f"EditText不足({len(edit_texts)}个)，重试...")
            jitter(1)
    
    # 在"添加标题"处输入标题
    if title:
        if len(edit_texts) >= 1:
            edit_texts[0].click()
            logger.info("点击: 添加标题 (EditText[0])")
            jitter(0.5)
            d.send_keys(title[:20])
            logger.info(f"输入标题: {title[:20]}")
            # 等待3秒让UI稳定，再输正文
            logger.info("等待3秒后输入正文...")
            jitter(3, 0.1)
        else:
            d.click(*_scale(d, 559, 548))  # 精确坐标：添加标题EditText中心
            logger.info("坐标点击标题区域")
    
    # 在"添加正文或发语音"处输入正文
    if xhs_body:
        body_et = d(className="android.widget.EditText", instance=1)
        if body_et.exists(timeout=3):
            body_et.click()
            logger.info("点击: 添加正文或发语音 (EditText[1])")
            jitter(0.5)
            chunk_size = 500
            for i in range(0, len(xhs_body), chunk_size):
                chunk = xhs_body[i:i+chunk_size]
                d.send_keys(chunk)
                jitter(0.2)
            logger.info(f"输入正文: {len(xhs_body)}字")
        else:
            d.click(*_scale(d, 540, 998))  # 精确坐标：添加正文或发语音EditText中心
            logger.info("坐标点击正文区域")
            jitter(0.5)
            chunk_size = 500
            for i in range(0, len(xhs_body), chunk_size):
                chunk = xhs_body[i:i+chunk_size]
                d.send_keys(chunk)
                jitter(0.2)
            logger.info(f"输入正文: {len(xhs_body)}字")
    
    # 等待5秒确保页面稳定，再点击"发布笔记"
    logger.info("等待5秒后点击发布笔记...")
    jitter(5, 0.1)
    
    # 优先文本查找"发布笔记"，试试多种匹配方式
    pub_clicked = False
    for sel in [d(text="发布笔记"), d(textContains="发布笔记"), d(text="发布"), d(descriptionContains="发布")]:
        if sel.exists(timeout=2):
            sel.click()
            logger.info("点击: 发布笔记")
            pub_clicked = True
            break
    
    if not pub_clicked:
        # 遍历所有Button
        for b in d(className="android.widget.Button"):
            txt = b.info.get("text", "")
            desc = b.info.get("contentDescription", "")
            if "发布" in txt or "发布" in desc:
                b.click()
                logger.info(f"点击: 发布笔记 (viaButton: text='{txt}')")
                pub_clicked = True
                break
    
    if not pub_clicked:
        d.click(*_scale(d, 688, 2239))
        logger.info("坐标点击发布")
    
    # 等待15秒发布动画 + 3下home回桌面
    logger.info("等待发布动画（15秒）...")
    jitter(15)
    for _ in range(3):
        d.press("home")
        jitter(0.3)
    
    # 关闭小红书后台
    d.app_stop('com.xingin.xhs')
    logger.info("关闭小红书后台")
    
    return {
        "serial": serial,
        "status": "published",
        "title": title,
        "image_count": image_count,
    }

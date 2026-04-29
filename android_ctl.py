#!/usr/bin/env python3
"""
Android Phone Controller - 小红书自动化发布
用法: python3 android_ctl.py <action> [args...]

动作:
  写想法 <内容> [标题]     - 纯文字笔记 (标题可选，默认"测试标题")
  写长文 <编辑区正文> [小红书正文] [标题]  - 长文笔记
  home                    - 回桌面
  info                    - 设备信息
"""

import uiautomator2 as u2
import sys, time, os

_DEVICE = None

def get_device():
    global _DEVICE
    if _DEVICE is None:
        serial = os.environ.get('ANDROID_SERIAL')
        _DEVICE = u2.connect(serial) if serial else u2.connect()
    return _DEVICE

def _open_xhs():
    """打开小红书并点击+号"""
    d = get_device()
    d.press('home'); time.sleep(0.3)
    d.app_start('com.xingin.xhs'); time.sleep(3)
    d.click(540, 2284); time.sleep(1.5)  # +号
    return d

def _click_xie_wenzi(d):
    """点击写文字"""
    d.click(540, 2079); time.sleep(1.5)

def _card_style_to_publish(d):
    """从卡片样式页 → 渲染完成 → 下一步 → 发布确认页"""
    time.sleep(1.5)
    for _ in range(30):
        if not d(text='图片生成中').exists(timeout=0.5):
            break
        time.sleep(0.5)
    next_btns = list(d(text='下一步', className='android.widget.TextView'))
    if next_btns:
        next_btns[-1].click()
    else:
        d.click(897, 2226)
    time.sleep(2)

def _visibility_and_publish(d):
    """公开可见 → 仅自己可见 → 发布笔记 → 桌面"""
    d.click(204, 1842); time.sleep(0.8)     # 公开可见
    time.sleep(0.3)
    d.click(297, 2232); time.sleep(0.5)     # 仅自己可见
    time.sleep(0.5)
    d.click(687, 2211); time.sleep(2.5)     # 发布笔记
    d.press('home'); time.sleep(0.5)
    d.press('home')

# ===== 写想法 =====

def xie_xie_fa(content, title="测试标题"):
    """纯文字笔记"""
    d = _open_xhs()
    _click_xie_wenzi(d)
    
    d.click(540, 1000); time.sleep(0.3)
    d.send_keys(content); time.sleep(0.3)
    
    # 下一步(顶) → 卡片样式
    next_btns = list(d(text='下一步', className='android.widget.TextView'))
    next_btns[0].click() if next_btns else d.click(920, 176)
    
    _card_style_to_publish(d)
    
    d.click(562, 629); time.sleep(0.3)   # 添加标题
    d.send_keys(title); time.sleep(0.3)
    
    _visibility_and_publish(d)
    print(f"✅ 写想法已发布: {content[:20]} | 标题: {title[:10]}")

# ===== 写长文 =====

def xie_chang_wen(editor_body, publish_body="", title=""):
    """
    长文笔记
    参数: editor_body=编辑区正文, publish_body=发布确认页正文(小红书正文), title=标题
    """
    d = _open_xhs()
    _click_xie_wenzi(d)
    
    d.click(375, 1931); time.sleep(2)       # 写长文
    
    if title:
        d.click(200, 300); time.sleep(0.3)
        d.send_keys(title); time.sleep(0.3)  # 标题
    
    d.click(540, 600); time.sleep(0.3)
    d.send_keys(editor_body); time.sleep(0.3) # 编辑区正文
    
    print("  一键排版中...")
    d.click(540, 2232); time.sleep(3)         # 一键排版
    
    # 选模板 → 下一步
    templates = ['清晰明朗', '简约基础', '灵感备忘', '涂鸦马克', '素雅底纹']
    for t in templates:
        try:
            el = d(text=t)
            if el.exists(timeout=0.5):
                el.click(); print(f"  选择模板: {t}"); time.sleep(0.3); break
        except: pass
    
    next_btns = list(d(text='下一步', className='android.widget.TextView'))
    if next_btns: next_btns[-1].click()
    else: d.click(897, 2256)
    time.sleep(2)
    
    # 发布确认页: 仅录入小红书正文(标题自动带入)
    if publish_body:
        d.click(540, 752); time.sleep(0.8)
        d.send_keys(publish_body); time.sleep(0.3)
    
    _visibility_and_publish(d)
    name = publish_body[:15] if publish_body else editor_body[:15]
    print(f"✅ 写长文已发布: {name}{'...' if len(name)>=15 else ''}")

# ===== 入口 =====

if __name__ == '__main__':
    actions = {
        '写想法': lambda a: xie_xie_fa(' '.join(a[:-1]) if len(a)>1 else a[0], a[-1] if len(a)>1 else "测试标题"),
        '写长文': lambda a: xie_chang_wen(a[0] if len(a)>0 else "", a[1] if len(a)>1 else "", a[2] if len(a)>2 else ""),
        'home': lambda a: get_device().press('home'),
        'info': lambda a: print(f"设备: {'x'.join(map(str,[get_device().info.get('displayWidth'),get_device().info.get('displayHeight')]))}"),
    }
    
    if len(sys.argv) < 2:
        print("用法: python3 android_ctl.py <动作> [参数...]\n")
        for k in actions:
            print(f"  {k}")
        sys.exit(1)
    
    handler = actions.get(sys.argv[1])
    if handler:
        try: handler(sys.argv[2:])
        except Exception as e:
            print(f"❌ {e}")
            import traceback; traceback.print_exc()
    else:
        print(f"未知动作: {sys.argv[1]}")
        print(f"可用: {', '.join(actions.keys())}")

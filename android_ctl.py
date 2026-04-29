#!/usr/bin/env python3
"""
Android Phone Controller - CLI 兼容入口
(核心逻辑迁移至 scripts/phone_controller.py)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))
from phone_controller import xie_xie_fa, xie_chang_wen, get_device

if __name__ == "__main__":
    actions = {
        "写想法": lambda a: xie_xie_fa(" ".join(a[:-1]) if len(a)>1 else a[0], a[-1] if len(a)>1 else "测试标题"),
        "写长文": lambda a: xie_chang_wen(a[0] if len(a)>0 else "", a[1] if len(a)>1 else "", a[2] if len(a)>2 else ""),
        "home": lambda a: get_device().press("home"),
        "info": lambda a: print(f"设备: {get_device().info}"),
    }
    if len(sys.argv) < 2:
        print("用法: python3 android_ctl.py <动作> [参数...]\n  写想法 / 写长文 / home / info")
        sys.exit(1)
    handler = actions.get(sys.argv[1])
    if handler:
        try: handler(sys.argv[2:])
        except Exception as e: print(f"❌ {e}")
    else:
        print(f"未知: {sys.argv[1]}")

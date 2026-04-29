#!/bin/bash
set -e

echo "=== XHS ADB Publisher 安装脚本 ==="
echo ""

# 检查 adb
if ! command -v adb &> /dev/null; then
    echo "❌ 未找到 adb，请先安装 Android Platform Tools"
    echo "   macOS: brew install android-platform-tools"
    echo "   Linux: sudo apt install adb"
    exit 1
fi
echo "✅ adb 已安装"

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 未找到 python3"
    exit 1
fi
echo "✅ python3 $(python3 --version)"

# 安装依赖
echo ""
echo "安装 Python 依赖..."
pip3 install uiautomator2 adbutils

# 检查设备
echo ""
echo "检查设备连接..."
adb devices
echo ""
echo "⚠️  确保你的设备已显示在列表中"
echo "   如有多个设备，设置环境变量: export ANDROID_SERIAL=设备序列号"
echo ""

# 测试
echo "测试连接..."
python3 android_ctl.py info || echo "请连接手机后重试"

echo ""
echo "=== 安装完成 ==="
echo "使用方式:"
echo "  export ANDROID_SERIAL=你的设备序列号"
echo "  python3 android_ctl.py 写想法 '内容' '标题'"
echo "  python3 android_ctl.py 写长文 '编辑器正文' '小红书正文' '标题'"

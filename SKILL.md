---
name: XHS ADB Publisher
description: 通过ADB操控Android手机实现小红书自动化发笔记。支持写想法(纯文字)和写长文(带排版)两种模式。
version: 1.0.0
author: JARVIS
slug: xhs-adb-publisher
---

# XHS ADB Publisher

通过 Android Debug Bridge (ADB) + uiautomator2 操控手机，实现小红书笔记的自动化发布。

## 前提条件

1. Android 手机一台（已开启开发者选项和 USB 调试）
2. USB 数据线连接电脑（或 WiFi ADB）
3. 手机上安装 ATX Keyboard（设为默认输入法，支持中文输入）
4. 手机上安装小红书 App

## 功能

- **写想法** — 纯文字笔记，支持自定义标题和正文
- **写长文** — 长文笔记，支持一键排版、模板选择、分段正文

## 安装

```bash
pip install uiautomator2 adbutils
```

## 使用

```bash
# 写想法
ANDROID_SERIAL=<设备序列号> python3 android_ctl.py 写想法 "正文内容" "标题"

# 写长文（编辑器正文 + 小红书正文 + 标题）
ANDROID_SERIAL=<设备序列号> python3 android_ctl.py 写长文 "编辑区正文" "小红书正文" "标题"
```

## 详细文档

见 [README.md](./README.md)

---
name: XHS ADB Publisher
description: |
  小红书自动化发布技能
  功能：文章发布（LLM生成+Pexels配图+ADB发布）+ 评论区获客(TODO)
  基于 ADB (uiautomator2) 操控手机 + DeepSeek API 驱动 AI 内容生成
metadata:
  openclaw:
    emoji: "📕"
    requires:
      env: ["DEEPSEEK_API_KEY", "ANDROID_SERIAL"]
    category: "acquisition"
    tags: ["xiaohongshu", "publish", "adb", "automation", "ai"]
---

# 小红书发布技能 (xhs-adb-publisher)

通过 ADB 操控 Android 手机实现小红书全自动运营。两个核心能力：

## 功能矩阵

| 功能 | 说明 | 关联脚本 |
|------|------|----------|
| 📝 发布文章 | LLM 生成 → Pexels 配图 → ADB 发布长文 | `xhs_article_publisher.py` |
| 💬 评论区获客 | 搜索 → AI评分 → LLM评论 → ADB 评论 (TODO) | `xhs_comment_acquisition.py` |
| ✏️ 写想法 | 纯文字笔记直发 | `phone_controller.py` |
| 📄 写长文 | 长文笔记直发（含一键排版） | `phone_controller.py` |

## 依赖

- Android 手机 + USB 连接
- Python 3.8+
- uiautomator2 + adbutils
- DeepSeek API Key（环境变量 `DEEPSEEK_API_KEY`）
- Pexels API Key（可选，环境变量 `PEXELS_API_KEY`）

## 快速使用

```bash
# 发布文章（完整流程）
python3 xhs_adb_publisher.py --publish --product-url "https://example.com" --product-name "产品名"

# 仅生成文章不发布
python3 xhs_adb_publisher.py --publish --dry-run --product-url "https://example.com"

# 直接写长文
python3 xhs_adb_publisher.py --write-long "编辑器正文" --xhs-body "小红书正文" --title "标题"
```

## 文件结构

```
xhs-adb-publisher/
├── xhs_adb_publisher.py           ← 统一编排入口
├── SKILL.md                       ← 本文
├── README.md                      ← 完整文档
├── android_ctl.py                 ← 旧版CLI（兼容保留）
├── scripts/
│   ├── phone_controller.py        ← ADB 手机操控核心
│   ├── xhs_article_publisher.py   ← 文章发布模块 (LLM→Pexels→ADB)
│   ├── xhs_comment_acquisition.py ← 评论区获客模块 (占位)
│   ├── xhs_llm.py                 ← LLM API 封装
│   └── pexels_images.py           ← Pexels 图片搜索下载
├── templates/
│   ├── article-prompt.md          ← 文章生成提示词
│   └── comment-prompt.md          ← 评论提示词 (占位)
├── config/
│   ├── publish.json               ← 发布配置
│   ├── pexels.json                ← Pexels 配置
│   └── keywords.json              ← 关键词配置 (占位)
├── data/                           ← 运行时数据 (自动创建)
├── requirements.txt
└── install.sh
```

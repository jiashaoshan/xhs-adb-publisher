---
name: XHS ADB Publisher
description: |
  小红书自动化运营技能
  功能：文章发布（LLM生成+Pexels配图+ADB发布）+ 评论区获客（MCP+LLM）
  基于 uiautomator2 (ADB) + xiaohongshu-mcp + DeepSeek API
metadata:
  openclaw:
    emoji: "📕"
    requires:
      env: ["DEEPSEEK_API_KEY", "ANDROID_SERIAL"]
      services: ["xiaohongshu-mcp (http://localhost:18060)"]
    category: "acquisition"
    tags: ["xiaohongshu", "publish", "adb", "automation", "ai", "comment-acquisition"]
---

# 小红书运营技能 (xhs-adb-publisher)

双引擎驱动：ADB 操控手机发布笔记 + MCP API 评论区获客。

## 功能矩阵

| 功能 | 方式 | 说明 |
|------|------|------|
| 📝 发布文章 | ADB+LLM | LLM 生成 → Pexels 配图 → ADB 发布长文 |
| 💬 评论区获客 | MCP+LLM | 搜索 → AI评分 → LLM评论 → MCP发表 |
| ✏️ 写想法 | ADB | 纯文字笔记直发 |
| 📄 写长文 | ADB | 长文笔记（含一键排版） |

## 评论区获客流程

```
[1. 关键词] → AI生成 / 配置读取
      ↓
[2. 搜索] → MCP API 搜索关键词笔记 (feed_id + xsec_token)
      ↓
[3. 评分] → LLM 4维评分 (热度40 + 互动30 + 时效20 + 质量10)
      ↓
[4. 详情] → MCP API 获取笔记正文 + 评论区上下文
      ↓
[5. 生成评论] → LLM 根据笔记内容生成小红书风格评论
      ↓
[6. 发送] → MCP API 发表评论 (POST /api/v1/feeds/comment)
      ↓
[7. 记录] → JSON 持久化已评论笔记，避免重复
```

### 评论风格（AI 选择）

| 风格 | 说明 |
|------|------|
| 赞同共鸣型 | 对笔记内容表示强烈认同，引发情感连接 |
| 补充分享型 | 补充自己的相关经验，增加价值 |
| 提问互动型 | 提出开放性问题，引导作者回复 |
| 经验交流型 | 分享自身经历，建立平等交流 |

## 依赖

### 硬件
- Android 手机 + USB 连接（仅发布功能需要）
- ATX Keyboard 设为默认输入法（仅发布功能需要）

### 服务
- **xiaohongshu-mcp**（评论区获客需要）
  ```bash
  # 下载并启动
  ./xiaohongshu-mcp-darwin-arm64
  # 默认监听 localhost:18060
  ```

### 环境变量
- `DEEPSEEK_API_KEY` — LLM 文章/评论生成
- `ANDROID_SERIAL` — ADB 设备串号（仅发布需要）
- `XHS_MCP_URL` — MCP 地址（默认 http://localhost:18060）
- `XHS_PRODUCT_URL` — 默认产品链接（可选）
- `XHS_PRODUCT_NAME` — 默认产品名称（可选）
- `PEXELS_API_KEY` — Pexels 配图（可选，发布用）

## 快速使用

### 评论区获客

```bash
# 手动指定关键词
python3 scripts/xhs_comment_acquisition.py -k "AI工具推荐" -u "https://ai.hcrzx.com"

# 自动模式（AI生成关键词 → 搜索 → 评论）
python3 scripts/xhs_comment_acquisition.py --auto -u "https://ai.hcrzx.com" -n "慧辰AI分析"

# Dry-run 安全测试
python3 scripts/xhs_comment_acquisition.py -k "数据分析" --dry-run -vv

# 限制本运行评论数
python3 scripts/xhs_comment_acquisition.py -k "效率工具" --max-comments 3

# 通过环境变量配置产品信息
export XHS_PRODUCT_URL="https://ai.hcrzx.com"
export XHS_PRODUCT_NAME="慧辰AI分析"
python3 scripts/xhs_comment_acquisition.py --auto
```

### 发布文章

```bash
# 完整发布（LLM生成 + Pexels配图 + ADB发布）
python3 xhs_adb_publisher.py --publish --product-url "https://ai.hcrzx.com"

# 仅生成不发布
python3 xhs_adb_publisher.py --publish --dry-run --product-url "https://ai.hcrzx.com"

# 直接写想法
python3 xhs_adb_publisher.py --write-thought "正文内容" --title "标题"
```

## 多设备并发发布

支持同时操控多台 Android 手机（每台绑定不同小红书账号）并发发布。

```bash
# 方式1: 命令行指定设备列表
.venv/bin/python3 batch_publisher.py \
  --devices "R3CN8A,R3CN8B,R3CN8C" \
  --product-url "https://ai.hcrzx.com" \
  --product-name "AI智能助手"

# 方式2: 使用设备配置文件
.venv/bin/python3 batch_publisher.py \
  --config config/devices.json \
  --product-url "https://ai.hcrzx.com"

# 方式3: 自动发现所有 adb device
.venv/bin/python3 batch_publisher.py \
  --auto-discover \
  --product-url "https://ai.hcrzx.com" \
  --dry-run  # 先模拟运行

# 限制并发数（降低风控）
.venv/bin/python3 batch_publisher.py \
  --devices "R3CN8A,R3CN8B,R3CN8C,R3CN8D" \
  --concurrency 2 \
  --product-url "https://ai.hcrzx.com"
```

**设备配置文件格式** (`config/devices.json`):
```json
[
  {"serial": "R3CN8A", "note": "华为P40 - 账号A"},
  {"serial": "R3CN8B", "note": "小米13 - 账号B"}
]
```

## 文件结构

```
xhs-adb-publisher/
├── xhs_adb_publisher.py           ← CLI 入口（发布+获客）
├── SKILL.md                       ← 本文
├── scripts/
│   ├── phone_controller.py        ← ADB 手机操控核心
│   ├── xhs_article_publisher.py   ← 文章发布模块
│   ├── xhs_comment_acquisition.py ← ✅ 评论区获客模块
│   ├── xhs_llm.py                 ← LLM API 封装
│   └── pexels_images.py           ← Pexels 图片搜索
├── templates/
│   ├── article-prompt.md          ← 文章生成提示词
│   └── comment-prompt.md          ← ✅ 评论生成提示词
├── config/
│   ├── publish.json               ← 发布+获客配置
│   ├── pexels.json                ← Pexels 配置
│   └── keywords.json              ← ✅ 种子关键词
└── data/                           ← 运行时数据（评论历史）
```

## 评论获客配置

`config/publish.json` → `acquisition` 段:

| 参数 | 默认值 | 说明 |
|------|--------|------|
| max_comments_per_run | 5 | 每次运行最多评论 |
| max_comments_per_day | 20 | 每天评论上限 |
| max_comments_per_hour | 5 | 每小时评论上限 |
| base_interval_seconds | 180 | 评论间隔（秒） |
| active_hours | [8, 23] | 活跃时段 |

## 风控策略

- ✅ 反爬策略：活跃时段 + 每日/小时上限 + 抖动延迟
- ✅ 历史去重：JSON 持久化记录，永不重复评论
- ✅ AI 生成关键词：动态换词，避免固定词频特征
- ✅ 评论风格多样化：4种风格 AI 选择，不模板化
- ✅ Dry-run 模式：安全测试，不发真实评论

## FAQ

### Q: MCP 服务器提示未登录？
A: 先运行 `./xiaohongshu-login-darwin-arm64` 扫码登录。

### Q: 没有手机能运行评论区获客吗？
A: 可以！评论区获客只依赖 MCP API，不需要手机。

### Q: 评论发送失败怎么办？
A: 检查 MCP 服务器是否运行、账号是否登录。使用 `--dry-run` 先测试。

### Q: 如何查看评论历史？
A: 查看 `data/commented-history.json` 文件。

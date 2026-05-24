---
name: XHS ADB Publisher
description: |
  小红书自动化运营技能
  功能：文章发布 + 图文发布 + 评论区获客 + 热点自动写长文
  基于 uiautomator2 (ADB) + xiaohongshu-mcp + TrendRadar + LLM（千帆主用，deepseek备选）
metadata:
  openclaw:
    emoji: "📕"
    requires:
      env: ["ANDROID_SERIAL"]
      services: ["xiaohongshu-mcp (http://localhost:18060)"]
    category: "acquisition"
    tags: ["xiaohongshu", "publish", "adb", "automation", "ai", "comment-acquisition"]
---

# 小红书运营技能 (xhs-adb-publisher)

两步法文章生成：**抓取产品网页 → LLM 分析 → 模板填充 → ADB 发布**。

## 功能矩阵

| 功能 | 方式 | 说明 |
|------|------|------|
| 📝 发布文章 | ADB+LLM | 抓网页→LLM分析→模板生成→ADB发布长文 |
| 🖼️ 图文发布 | ADB+LLM+豆包 | LLM生成短文 → 豆包封面图 → ADB发布图文 |
| 💬 评论区获客 | MCP+LLM | 搜索 → AI评分 → LLM评论 → MCP发表 |
| ✏️ 写想法 | ADB | 纯文字笔记直发 |
| 📄 写长文 | ADB | 长文笔记（含一键排版） |
| 🔥 热点自动写长文 | TrendRadar+LLM+ADB | 获取热点 → 产品分析 → LLM生成3000字长文 → ADB发布 |

## 文章生成流程

```
[产品链接]
    ↓
[第一步: 抓取网页] → fetch_webpage_text(url) — 含 SPA 兼容 (meta 兜底)
    ↓
  LLM 提取结构化信息 → analyze_product()
    ↓
  {product_name, positioning, core_features, characteristics}
    ↓
[第二步: 模板填充] → templates/user-article-prompt.md
    ↓
  替换 {{product_name}} {{positioning}} {{core_features}} {{characteristics}} {{product_url}}
    ↓
  LLM 生成小红书正文（纯文本输出）
    ↓
  _parse_article_output() 提取标题+正文（支持多种格式）
    ↓
  发布/预览
```

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

## 热点自动写长文 (v1.0.0)

### 架构

```
产品链接
    ↓
步骤1: LLM 分析产品（卖点/核心功能/特点）
    ↓
步骤2: TrendRadar MCP 获取热点
  ├── 主渠道: 新智元 RSS（AI/科技深度文章）
  └── 降级: V2EX 热榜（技术话题）
    ↓
步骤3: AI 挑选最适合与产品结合的热点
    ↓
步骤4: LLM 生成 2500-4000 字长文
  ├── 从热点话题切入（行业趋势/技术讨论）
  ├── 自然引出产品（分享真实体验）
  └── 正文嵌入产品链接，引导点击
    ↓
步骤5: ADB 发布长文到小红书
  ├── 完整正文 (editor_body) → 一键排版
  └── 精简版 (xhs_body) → 发布确认页
```

### 快速使用

```bash
# 全自动（分析产品 → 获取热点 → 生成文章 → ADB发布长文）
python3 xhs_adb_publisher.py --hotspot-long --product-url "https://ai.hcrzx.com"

# 测试模式（不实际发布）
python3 xhs_adb_publisher.py --hotspot-long --product-url "https://ai.hcrzx.com" --dry-run

# 指定设备
python3 xhs_adb_publisher.py --hotspot-long --product-url "https://ai.hcrzx.com" --serial R3CN8A
```

## LLM 模型配置

从 `config/llm.json` 读取：

```json
{
  "provider": "baiduqianfancodingplan",
  "api_key": "bce-v3/xxx",
  "model": "qianfan-code-latest"
}
```

| provider | 说明 | 默认模型 |
|----------|------|---------|
| `baiduqianfancodingplan` | 百度千帆编码计划 | `qianfan-code-latest` |
| `deepseek` | DeepSeek API | `deepseek-v4-flash` |
| `sensenova` | 燧原科技 API | `deepseek-v4-flash` |

优先级: `config/llm.json` > 环境变量 `LLM_API_KEY` / `LLM_MODEL` / `DEEPSEEK_API_KEY`

当千帆 API 429 限流时，自动切换到备选 deepseek（需设置 `DEEPSEEK_API_KEY` 环境变量）。

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
- `ANDROID_SERIAL` — ADB 设备串号（仅发布需要）
- `XHS_MCP_URL` — MCP 地址（默认 http://localhost:18060）
- `XHS_PRODUCT_URL` — 默认产品链接（可选）
- `XHS_PRODUCT_NAME` — 默认产品名称（可选）

## 快速使用

### 发布文章（两步法生成 + ADB 发布）

```bash
# 完整发布
python3 xhs_adb_publisher.py --publish --product-url "https://ai.hcrzx.com"

# 仅生成不发布（预览）
python3 xhs_adb_publisher.py --publish --dry-run --product-url "https://ai.hcrzx.com"

# 直接写想法
python3 xhs_adb_publisher.py --write-thought "正文内容" --title "标题"
```

### 图文发布

```bash
# 完整图文发布（LLM生成短文 + 豆包AI封面图 + ADB发布）
python3 xhs_adb_publisher.py --publish-image --topic "白菜价PPT"

# 带产品链接
python3 xhs_adb_publisher.py --publish-image --topic "AI工具" --product-url "https://example.com"

# 指定文章类型（可选，自动检测）
python3 xhs_adb_publisher.py --publish-image --topic "Python教程" --article-type tutorial

# 仅生成不发布（预览）
python3 xhs_adb_publisher.py --publish-image --topic "测试" --dry-run
```

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

## 多设备并发发布

支持同时操控多台 Android 手机（每台绑定不同小红书账号）并发发布。

```bash
# 方式1: 命令行指定设备列表
python3 batch_publisher.py \
  --devices "R3CN8A,R3CN8B,R3CN8C" \
  --product-url "https://ai.hcrzx.com" \
  --product-name "AI智能助手"

# 方式2: 使用设备配置文件
python3 batch_publisher.py \
  --config config/devices.json \
  --product-url "https://ai.hcrzx.com"

# 方式3: 自动发现所有 adb device
python3 batch_publisher.py \
  --auto-discover \
  --product-url "https://ai.hcrzx.com" \
  --dry-run  # 先模拟运行

# 限制并发数（降低风控）
python3 batch_publisher.py \
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

## 提示词模板自定义

文章内容由 `templates/user-article-prompt.md` 控制，可随时编辑无需改代码：

```markdown
【产品信息】
- 产品名：{{product_name}}
- 定位：{{positioning}}
- 核心功能：{{core_features}}
- 特点：{{characteristics}}

【写作要求】
- 标题不超过20字（含Emoji），不用营销词
- 正文以个人真实使用体验切入
- 语气像跟朋友聊天
- 自然加入产品链接（{{product_url}}）
```

## 文件结构

```
xhs-adb-publisher/
├── xhs_adb_publisher.py           ← CLI 入口（发布+获客）
├── batch_publisher.py             ← 多设备批量发布
├── SKILL.md                       ← 本文
├── README.md                      ← 详细文档
├── scripts/
│   ├── phone_controller.py          ← ADB 手机操控核心
│   ├── xhs_article_publisher.py     ← 文章发布模块（两步法 LLM→ADB）
│   ├── xhs_image_publisher.py       ← 图文发布模块
│   ├── xhs_comment_acquisition.py   ← 评论区获客模块
│   ├── xhs_daily_image_publisher.py ← 图文日常发布模块
│   ├── xhs_hotspot_long_article.py  ← ★ 热点自动写长文模块
│   ├── xhs_llm.py                   ← LLM API 封装（千帆主用，deepseek备选）
├── templates/
│   ├── user-article-prompt.md     ← 用户自定义文章模板（含占位符）
│   ├── short-article-prompt.md    ← 短文章模板（300-1000字）
│   ├── article-prompt.md          ← 文章生成提示词
│   ├── cover-prompt-1.md          ← 封面模板1：蓝色手举手机
│   ├── cover-prompt-2.md          ← 封面模板2：卡通小马梗图
│   ├── tutorial-prompt.md         ← 教程提示词
│   ├── story-prompt.md            ← 故事提示词
│   ├── comparison-prompt.md       ← 对比提示词
│   ├── list-prompt.md             ← 清单提示词
│   ├── comment-prompt.md          ← 评论生成提示词
│   ├── cover-prompt-daily.md      ← 封面图提示词（日常版）
│   └── hotspot-long-article-prompt.md ← ★ 热点长文生成提示词
├── config/
│   ├── llm.json                   ← LLM 配置（provider/api_key/model）
│   ├── publish.json               ← 发布+获客配置
│   └── keywords.json              ← 种子关键词
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

### Q: 文章内容模板在哪里改？
A: 编辑 `templates/user-article-prompt.md`，支持 `{{product_name}}` 等占位符，改完立即生效。

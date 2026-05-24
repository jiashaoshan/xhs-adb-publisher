# XHS ADB Publisher

通过 ADB 操控 Android 手机，自动化运营小红书账号。

**核心能力**：文章发布 + 图文发布 + 评论区获客 + 热点自动写长文

---

## 快速开始

### 1. 环境准备

```bash
pip install uiautomator2 adbutils requests
```

**LLM 配置**：编辑 `config/llm.json`，配置 provider 和 API Key：

```json
{
  "provider": "baiduqianfancodingplan",
  "api_key": "bce-v3/xxx",
  "model": "qianfan-code-latest"
}
```

支持 `baiduqianfancodingplan`（千帆编码计划）、`deepseek`、`sensenova` 等 provider。

**评论区获客额外依赖：**
- 启动 [xiaohongshu-mcp](https://github.com/yanzengyun/xiaohongshu-mcp) 服务（默认监听 `http://localhost:18060`）

### 2. 手机端配置

| 步骤 | 操作 |
|------|------|
| ① | 开启「开发者选项」和「USB 调试」（或无线调试） |
| ② | `adb pair` 配对 → `adb connect` 连接 |
| ③ | 安装 ATX Keyboard（`uiautomator2 init` 会自动装） |
| ④ | **设置→其他设置→键盘与输入法→默认输入法→ATX Keyboard** |

> ⚠️ ATX Keyboard 必须设为**默认输入法**，否则中文输入无法工作。仅「启用」不够。
> ColorOS/vivo 系统若 `ime set` 被拦截，需 `pm grant` 提权后再 `settings put secure`。

### 3. 使用

```bash
# 两步法发布文章（抓网页→LLM分析→模板生成→ADB发布）
python3 xhs_adb_publisher.py --publish --product-url "https://example.com"

# 仅生成不发布（预览）
python3 xhs_adb_publisher.py --publish --dry-run --product-url "https://example.com"

# 热点自动写长文（TrendRadar热点→LLM生成3000字→ADB发布）
python3 xhs_adb_publisher.py --hotspot-long --product-url "https://example.com"
python3 xhs_adb_publisher.py --hotspot-long --product-url "https://example.com" --dry-run
python3 xhs_adb_publisher.py --hotspot-long --product-url "https://example.com" --max 2

# 图文发布（LLM生成短文+豆包封面图+ADB发布）
python3 xhs_adb_publisher.py --publish-image --topic "AI工具推荐" --product-url "https://example.com"
python3 xhs_adb_publisher.py --publish-image --topic "Python入门教程" --article-type tutorial

# 评论区获客（MCP+LLM搜索→评分→写评论→发表）
python3 xhs_adb_publisher.py --acquire --keyword "AI工具" --product-url "https://example.com"
python3 xhs_adb_publisher.py --acquire --auto --product-url "https://example.com"

# 直接写长文（跳过LLM生成）
python3 xhs_adb_publisher.py --write-long "编辑器正文" --xhs-body "小红书正文" --title "标题"

# 直接写想法
python3 xhs_adb_publisher.py --write-thought "正文" --title "标题"

# 多设备并发发布
python3 batch_publisher.py --devices "SERIAL1,SERIAL2" --product-url "https://example.com"
```

---

## 热点自动写长文

### 流程

```
产品链接
    ↓
步骤1: LLM 分析产品（提取卖点/核心功能/特点/目标用户）
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

### TrendRadar MCP

脚本直连 TrendRadar 的 MCP HTTP 接口（不依赖 Node.js），通过以下工具获取内容：

| 工具 | 用途 |
|------|------|
| `get_latest_rss` | 获取 RSS 订阅源（新智元 filter） |
| `get_latest_news` | 获取新闻热榜（V2EX filter + 技术关键词） |
| `read_article` | 获取文章全文（产品页兜底 + 热点内容补充） |

### 文章格式

LLM 按分隔符格式输出，脚本解析后分渠道发布：

```
===TITLE===
标题（≤40字，含 Emoji）

===BRIEF===
一句话摘要（50-100字）

===BODY===
正文内容（2500-4000字，Emoji 分隔段落，无 Markdown 标题）

===END===
```

---

## LLM 配置

### 配置文件

所有 LLM 配置集中在 `config/llm.json`，不再依赖 `openclaw.json`：

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

优先级：`config/llm.json` > 环境变量 `LLM_API_KEY` / `LLM_MODEL` / `DEEPSEEK_API_KEY`

> 当千帆 API 429 限流时，自动切换到备选 deepseek（需设置 `DEEPSEEK_API_KEY` 环境变量）。

### 两步法文章生成

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

### 提示词模板自定义

文章内容由 `templates/user-article-prompt.md` 控制，可随时编辑无需改代码。模板变量：

- `{{product_name}}` — 产品名称
- `{{positioning}}` — 产品定位
- `{{core_features}}` — 核心功能
- `{{characteristics}}` — 特点列表
- `{{product_url}}` — 产品链接

### 校验规则

| 模式 | 规则 | 值 | 说明 |
|------|------|:--:|------|
| 热点长文 | 正文长度 | 2500-4000字 | `parse_article_output()` 自动校验 |
| 热点长文 | 标题上限 | ≤40字 | 含 Emoji |
| 热点长文 | 发布正文 | ≤1000字 | LLM 精简生成 + 产品 CTA |
| 普通长文 | 正文长度 | 1200-2000字 | `_retry_llm()` 自动重试 |
| 普通长文 | 标题上限 | ≤20字 | 含 Emoji |
| 普通长文 | 发布正文 | ≤1000字 | LLM 精简生成 |
| 图文 | 正文长度 | 500-1000字 | `_run_article_generation()` 自动重试 |
| 图文 | 标题上限 | ≤20字 | 超出截断 |

---

## 评论区获客

### 流程

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
[6. 发送] → MCP API 发表评论
      ↓
[7. 记录] → JSON 持久化已评论笔记，避免重复
```

### 评论风格

| 风格 | 说明 |
|------|------|
| 赞同共鸣型 | 对笔记内容表示强烈认同，引发情感连接 |
| 补充分享型 | 补充自己的相关经验，增加价值 |
| 提问互动型 | 提出开放性问题，引导作者回复 |
| 经验交流型 | 分享自身经历，建立平等交流 |

### 风控策略

- ✅ 反爬策略：活跃时段 + 每日/小时上限 + 抖动延迟
- ✅ 历史去重：JSON 持久化记录，永不重复评论
- ✅ AI 生成关键词：动态换词，避免固定词频特征
- ✅ 评论风格多样化：4种风格 AI 选择，不模板化
- ✅ Dry-run 模式：安全测试，不发真实评论

---

## 多设备并发

```bash
# 指定设备列表
python3 batch_publisher.py --devices "SERIAL1,SERIAL2" \
  --product-url "https://example.com"

# 使用配置文件
python3 batch_publisher.py --config config/devices.json \
  --product-url "https://example.com"

# 自动发现 ADB 设备
python3 batch_publisher.py --auto-discover \
  --product-url "https://example.com"

# 控制并发数（降低风控）
python3 batch_publisher.py --devices "SERIAL1,SERIAL2,SERIAL3" \
  --concurrency 2 --product-url "https://example.com"
```

---

## 发布流程

### 写长文（完整操作流）

```
桌面 → 打开小红书 → 处理草稿弹窗(如有) → 点击底部+号
→ 点击写文字(文本查找) → 点击写长文(文本查找)
→ 输入标题 + 分批发送编辑器正文(每批500字)
→ 点击一键排版(文本查找)
→ 固定等待 24s（确保排版 + 封面渲染完成）
→ 等待"图片生成中"消失
→ 点击下一步(文本查找) → 检测并处理模板选择页
→ 点击下一步(文本查找) → 进入发布确认页
→ 点击"添加正文"/"添加正文或发语音"(文本查找) → 输入小红书本(≤1000字)
→ 确认公开可见 → 点击"发布笔记"(文本查找)
→ 等待 15s（发布动画）→ 3次home键回桌面
```

### 写想法（纯文字）

```
桌面 → 打开小红书 → 点击+号 → 写文字(文本查找) → 输入内容
→ 下一步(文本查找) → 等卡片预览渲染 → 下一步(文本查找)
→ 添加标题 → 公开可见 → 发布 → 回桌面
```

---

## 文件结构

```
xhs-adb-publisher/
├── xhs_adb_publisher.py           ← CLI 入口（发布+获客+热点长文）
├── batch_publisher.py             ← 多设备批量发布
├── SKILL.md                       ← OpenClaw 技能定义
├── scripts/
│   ├── phone_controller.py        ← ADB 手机操控核心（文本查找为主，坐标fallback）
│   ├── xhs_article_publisher.py   ← 文章发布（两步法 LLM→ADB）
│   ├── xhs_image_publisher.py     ← 图文发布（LLM→豆包封面图→ADB）
│   ├── xhs_comment_acquisition.py ← 评论区获客（MCP+LLM）
│   ├── xhs_daily_image_publisher.py ← 图文日常发布
│   ├── xhs_hotspot_long_article.py  ← ★ 热点自动写长文（TrendRadar+LLM+ADB）
│   └── xhs_llm.py                 ← LLM API 封装（千帆主用，deepseek 备选）
├── templates/
│   ├── user-article-prompt.md     ← 用户自定义文章模板（含 {{product_*}} 占位符）
│   ├── short-article-prompt.md    ← 短文章模板（300-1000字）
│   ├── article-prompt.md          ← 文章生成提示词
│   ├── tutorial-prompt.md         ← 教程干货提示词
│   ├── story-prompt.md            ← 故事分享提示词
│   ├── comparison-prompt.md       ← 对比测评提示词
│   ├── list-prompt.md             ← 清单合集提示词
│   ├── cover-prompt-1.md          ← 封面模板1：蓝色手举手机
│   ├── cover-prompt-2.md          ← 封面模板2：卡通小马梗图
│   ├── cover-prompt-daily.md      ← 封面提示词（日常版）
│   ├── comment-prompt.md          ← 评论生成提示词
│   └── hotspot-long-article-prompt.md ← ★ 热点长文生成提示词
├── config/
│   ├── llm.json                   ← LLM 配置（provider/api_key/model）
│   ├── publish.json               ← 发布+获客配置
│   ├── keywords.json              ← 评论区获客关键词
│   └── devices.json.example       ← 多设备配置示例
└── data/                           ← 运行时数据（评论历史 + 发布记录）
```

---

## 技术栈

| 组件 | 用途 |
|------|------|
| `uiautomator2` | Python ↔ 手机 ATX Agent 通信 |
| `ATX Keyboard` | 自定义输入法，支持中文注入 |
| `qianfan-code-latest`（千帆） | AI 生成文章（主用） |
| `deepseek-v4-flash` | AI 生成（429 限流时自动 fallback） |
| `豆包 Seedream 5.0` | AI 生成封面图 |
| `TrendRadar MCP` | 热点数据获取（新智元 RSS / V2EX） |
| `xiaohongshu-mcp` | 小红书 MCP 服务（评论区获客）|
| `ADB` | Android Debug Bridge 连接通道 |

### 元素定位方式

优先使用文本查找，坐标仅作为 fallback：

| 页面 | 操作 | 定位方式 | fallback |
|------|------|:--------:|:--------:|
| 启动 | 处理草稿弹窗 | `textContains`("存草稿"/"不保存") | - |
| 首页 | 点击底部+号 | 坐标(屏幕居中底部) | - |
| +号菜单 | 写文字 | `d(text="写文字")` | 坐标 |
| 二级菜单 | 写长文 | `d(text="写长文")` | textContains |
| 编辑页 | 输入标题 | `d(text="输入标题")` | - |
| 编辑页 | 一键排版 | `d(text="一键排版")` | - |
| 模板选择页 | 选择模板 | `d(text="涂鸦马克")` | - |
| 模板选择页 | 下一步 | `d(text="下一步")` | - |
| 发布确认页 | 添加正文 | `textContains("添加正文")` | 坐标 |
| 发布确认页 | 发布笔记 | `d(text="发布笔记")` | Button遍历+坐标 |

---

## 风控与安全

ADB 操控模拟真人点击，技术层面无 API 特征。风险来自行为模式：

| 因素 | 级别 | 说明 |
|------|:----:|------|
| 操作节奏 | ✅ | 所有延时加入 ±20% 随机抖动 |
| 可见范围 | ✅ | 默认仅自己可见 |
| 内容同质化 | ⚠️ | 提示词要求结构差异化 |
| 发布频率 | ⚠️ | 建议每小时≤2篇 |

### 建议运营策略

- 📅 **频率控制**：每小时最多 1-2 篇
- 🔄 **内容差异化**：每篇换开头/语气/emoji
- 📱 **混合使用**：手机上正常刷小红书
- 🚫 **避免**：评论区高频私信导流

---

## 常见问题

### Q: 无法输入中文？
确保 ATX Keyboard 设为**默认输入法**：
```bash
adb shell settings get secure default_input_method
# 应返回: com.github.uiautomator/.AdbKeyboard
```
ColorOS/vivo 若 `ime set` 被拦截：
```bash
adb shell pm grant com.github.uiautomator android.permission.WRITE_SECURE_SETTINGS
adb shell settings put secure default_input_method com.github.uiautomator/.AdbKeyboardService
```

### Q: 无线 ADB 怎么连接？
```bash
# 手机开启无线调试 → 记录 IP:端口 和 配对码
adb pair 192.168.1.x:配对端口 配对码
adb connect 192.168.1.x:连接端口
# 查看已连接的设备
adb devices
```

### Q: 两台手机并行时报 "more than one device"？
设置环境变量 `ANDROID_SERIAL` 指定目标设备，或使用 `batch_publisher.py` 配合 `--config` 参数。

### Q: 发布确认页卡住？
脚本内置了 24s 固定等待 + "图片生成中"检测，确保预览渲染完成后再操作。如果仍然卡住，可能是小红书版本更新后控件文本变了。

### Q: 模板可以自定义吗？
可以。编辑 `templates/user-article-prompt.md` 即可，支持 `{{product_name}}` 等占位符。修改立即生效，无需重启。

### Q: 如何切换 LLM 模型？
编辑 `config/llm.json`，修改 `provider` 和 `model` 字段。支持 `baiduqianfancodingplan` / `deepseek` / `sensenova`。

### Q: 评论区获客需要手机吗？
不需要。评论区获客只依赖 xiaohongshu-mcp 服务，不需要连接手机。

---

## License

MIT

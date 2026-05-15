# XHS ADB Publisher

通过 ADB 操控 Android 手机，自动化发布小红书笔记。

---

## 快速开始

### 1. 环境准备

```bash
pip install uiautomator2 adbutils requests
export ANDROID_SERIAL=<你的设备序列号>   # adb devices 查看（仅发布需要）
export DEEPSEEK_API_KEY=sk-xxx           # LLM 文章/评论生成
export XHS_MCP_URL=http://localhost:18060  # MCP 服务地址（评论区获客需要）
```

**评论区获客额外依赖：**
- 启动 [xiaohongshu-mcp](https://github.com/yanzengyun/xiaohongshu-mcp) 服务
- 默认监听 `http://localhost:18060`

### 2. 手机端配置

| 步骤 | 操作 |
|------|------|
| ① | 开启「开发者选项」和「USB 调试」 |
| ② | 连接电脑 USB，信任 RSA 指纹 |
| ③ | 安装 ATX Keyboard（`uiautomator2 init` 会自动装） |
| ④ | **设置 → 其他设置 → 键盘与输入法 → 默认输入法 → 选 ATX Keyboard** |

> ⚠️ ATX Keyboard 必须设为**默认输入法**，否则中文输入无法工作。仅「启用」不够。

### 3. 使用

```bash
# 完整发布（推荐）
python3 xhs_adb_publisher.py --publish --product-url "https://example.com"


# 仅生成不发布（预览）
python3 xhs_adb_publisher.py --publish --dry-run --product-url "https://example.com"

# 图文发布（AI生成文章+AI配图）
python3 xhs_adb_publisher.py --publish-image --topic "AI工具推荐"

# 图文发布（指定类型：tutorial/story/comparison/list/general）
python3 xhs_adb_publisher.py --publish-image --topic "Python入门教程" --article-type tutorial

# 图文发布（仅生成，不发布）
python3 xhs_adb_publisher.py --publish-image --topic "效率神器" --dry-run

# 评论区获客
python3 xhs_adb_publisher.py --acquire --keyword "AI工具" --product-url "https://example.com"

# 评论区获客（自动模式）
python3 xhs_adb_publisher.py --acquire --auto --product-url "https://example.com"

# 直接写长文（跳过 LLM）
python3 xhs_adb_publisher.py --write-long "编辑器正文" --xhs-body "小红书正文" --title "标题"

# 直接写想法
python3 xhs_adb_publisher.py --write-thought "正文" --title "标题"
```

---

## 发布流程

### 写长文（完整流程）

```
桌面 → 打开小红书 → 处理草稿弹窗(如有) → 点击底部+号
→ 点击写文字(文本查找) → 点击写长文(文本查找)
→ 输入标题 + 分批发送编辑器正文(每批500字)
→ 点击一键排版(文本查找)
→ 等待 24s（含±20%随机抖动，确保排版渲染完成）
→ 点击下一步(文本查找) → 进入模板选择页
→ 再等待渲染完成 → 再次点击下一步(文本查找) → 进入发布确认页
→ 点击"添加正文"/"添加正文或发语音"(文本查找) → 输入小红书正文(≤1000字)
→ 点击"公开可见"(文本查找) → 选择"仅自己可见"(文本查找)
→ 点击"发布笔记"(文本查找)
→ 等待 8s（发布动画播放）→ 按3次home键回到桌面
```

### 写想法（纯文字）

```
桌面 → 打开小红书 → 点击+号 → 写文字(文本查找) → 输入内容
→ 下一步(文本查找) → 等卡片预览渲染 → 下一步(文本查找)
→ 添加标题 → 仅自己可见 → 发布 → 回桌面
```

### 图文发布（AI生成封面+文章）

```
桌面 → 打开小红书 → 处理草稿弹窗(如有) → 点击底部+号
→ 点击"从相册选择"(文本查找)
→ 选择图片(封面图1张，点击右上角对勾)
→ 点击下一步(文本查找) → 进入图片编辑页(等待5s)
→ 点击下一步(文本查找) → 进入发布确认页
→ EditText[0] 输入标题(≤20字，等待3s)
→ EditText[1] 输入正文(≤1000字)
→ 等待5s → 点击"发布笔记"(文本查找)
→ 等待 15s（发布动画播放）→ 按3次home键回到桌面
```

**图文发布完整流程（后台）：**
```
输入主题/产品链接
  ↓
LLM 生成小红书正文(≤1000字)
  ↓
随机选封面模板 → 填充模板参数(product_slogan + article_title)
  ↓
调用豆包API生成封面图(1张)
  ↓
ADB push 封面图到手机相册
  ↓
ADB 从相册选择 → 输入标题/正文 → 发布
```

---

## 文件结构

```
xhs-adb-publisher/
├── xhs_adb_publisher.py           ← CLI 入口
├── batch_publisher.py             ← 多设备并发发布入口
├── android_ctl.py                 ← 旧版 CLI（兼容）
├── SKILL.md                       ← OpenClaw 技能定义
├── scripts/
│   ├── phone_controller.py        ← ADB 手机操控核心（文本查找为主，坐标fallback）
│   ├── xhs_article_publisher.py   ← 文章发布 (LLM→ADB，写长文)
│   ├── xhs_image_publisher.py     ← 🆕 图文发布 (LLM→豆包封面图→ADB)
│   ├── xhs_comment_acquisition.py ← 评论区获客 (MCP+LLM)
│   ├── xhs_llm.py                 ← LLM API 封装（千帆 qianfan-code-latest）
├── templates/
│   ├── short-article-prompt.md    ← 🆕 短文章模板（标题≤20字，正文300-1000字）
│   ├── article-prompt.md          ← 通用种草提示词
│   ├── tutorial-prompt.md         ← 教程干货提示词
│   ├── story-prompt.md            ← 故事分享提示词
│   ├── comparison-prompt.md       ← 对比测评提示词
│   ├── list-prompt.md             ← 清单合集提示词
│   ├── cover-prompt-1.md          ← 🆕 封面模板1：蓝色手举手机风格
│   ├── cover-prompt-2.md          ← 🆕 封面模板2：卡通小马梗图风格
│   └── comment-prompt.md          ← 评论生成提示词
├── config/
│   ├── publish.json               ← 发布+获客配置
│   ├── keywords.json              ← 评论区获客关键词
│   └── devices.json.example       ← 多设备配置示例
└── data/                           ← 运行时数据（自动创建）
```

---

## 设计

### 架构

```
xhs_adb_publisher.py (CLI)
        │
        ├── xhs_article_publisher.py  (文章发布: LLM生成 + ADB写长文)
        │       │
        │       └── phone_controller.py  (ADB 操控手机)
        │               │
        │               └── Android 手机 · 小红书 App
        │
        ├── xhs_image_publisher.py   (🆕 图文发布: LLM生成 + 豆包封面 + ADB发布)
        │       │
        │       ├── phone_controller.py  (ADB 操控手机)
        │       └── doubao-image-create   (豆包 Seedream 5.0 生图)
        │
        └── xhs_comment_acquisition.py  (MCP API + LLM 评论获客)
                │
                └── xiaohongshu-mcp 服务 (localhost:18060)
``````

### 技术栈

| 组件 | 用途 |
|------|------|
| `uiautomator2` | Python ←→ 手机 ATX Agent 通信 |
| `ATX Keyboard` | 自定义输入法，支持中文注入 |
| `千帆 qianfan-code-latest` | AI 生成小红书风格文章 |
| `豆包 Seedream 5.0` | AI 生成封面图 |
| `ADB` | Android Debug Bridge 连接通道 |
| `xiaohongshu-mcp` | 小红书 MCP 服务（评论区获客）|

### 元素定位方式

**优先使用文本查找**，坐标仅作为 fallback 兜底：

| 页面 | 操作 | 定位方式 | fallback |
|------|------|:--------:|:--------:|
| 启动 | 处理草稿弹窗 | `textContains`("存草稿"/"不保存") | - |
| 首页 | 点击底部+号 | 坐标(屏幕居中底部) | - |
| +号菜单 | 写文字 | `d(text="写文字")` | 坐标 |
| 二级菜单 | 写长文 | `d(text="写长文")` | - |
| 编辑页 | 输入标题 | `d(text="输入标题")` | - |
| 编辑页 | 一键排版 | `d(text="一键排版")` | - |
| 模板选择页 | 下一步 | `d(text="下一步")` | - |
| 发布确认页 | 添加标题 | `EditText[0].click()` | 坐标 |
| 发布确认页 | 添加正文 | `EditText[1].click()` | 坐标 |
| 发布确认页 | 发布笔记 | `d(text="发布笔记")` | Button遍历+坐标 |
| — | — | — | — |
| **图文发布** | **新增** | | |
| 发布确认页 | 标题输入框 | `className=EditText, instance=0` | 坐标 |
| 发布确认页 | 正文输入框 | `className=EditText, instance=1` | 坐标 |
| 发布确认页 | 发布笔记 | `d(text="发布笔记")` / Button遍历 | 坐标 |

---

## LLM 文章生成

### 模型

- `qianfan-code-latest`（千帆编码模型，文章生成）
- 环境变量 `DEEPSEEK_API_KEY` 或 `openclaw.json` 配置 API Key
- 地址从 `openclaw.json` 的 `baiduqianfancodingplan` provider 自动读取

### 校验规则（图文发布）

| 规则 | 值 | 说明 |
|------|:--:|------|
| 正文长度 | 300-1000字 | 图文发布专用短模板 |
| 标题上限 | ≤20字 | 超出截断 |
| xhs正文 | 直接使用LLM输出 | 正文已≤1000字，无需裁剪 |
| 重试机制 | 最多3次 | 不符合范围自动重试 |

### 封面图模板

随机从以下模板中选择一个：
- **模板1（蓝色手）**: 粗线条手绘漫画，蓝色卡通手举手机
- **模板2（小马）**: 两格竖版漫画，棕色小马梗图风格

模板变量：`{{product_slogan}}` → 提取的宣传语
           `{{article_title}}` → 文章标题

---

## 多设备并发

```bash
# 指定设备列表
python3 batch_publisher.py --devices "SERIAL1,SERIAL2" \
  --product-url "https://example.com"

# 使用配置文件
python3 batch_publisher.py --config config/devices.json \
  --product-url "https://example.com"

# 自动发现
python3 batch_publisher.py --auto-discover \
  --product-url "https://example.com"

# 控制并发数
python3 batch_publisher.py --devices "SERIAL1,SERIAL2" \
  --concurrency 2 --product-url "https://example.com"
```

---

## 风控与安全

### 风险分析

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

### Q: 无法输入中文
确保 ATX Keyboard 设为**默认输入法**：
```bash
adb shell settings get secure default_input_method
# 应返回: com.github.uiautomator/.AdbKeyboard
```

### Q: 两台手机并行时报 "more than one device"
设置环境变量 `ANDROID_SERIAL` 指定目标设备，或使用 `batch_publisher.py` 配合 `--config` 参数。

### Q: 发布确认页卡住
脚本内置了 24s 固定等待 +"图片生成中"检测，确保预览渲染完成后再操作。如果仍然卡住，可能是小红书本版更新后控件文本变了，可探查当前页面文本后更新 `phone_controller.py` 中的查找字符串。

### Q: `DEEPSEEK_API_KEY` 在哪里配置？
可通过环境变量设置，或在 `~/.openclaw/openclaw.json` 的 `env` 段配置。

---

## License

MIT

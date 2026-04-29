# XHS ADB Publisher

通过 ADB 操控 Android 手机，自动化发布小红书笔记。

---

## 快速开始

### 1. 环境准备

```bash
pip install uiautomator2 adbutils
export ANDROID_SERIAL=<你的设备序列号>   # adb devices 查看
export DEEPSEEK_API_KEY=sk-xxx           # LLM 文章生成
export PEXELS_API_KEY=xxx                # 自动配图（可选）
```

### 2. 手机端配置

| 步骤 | 操作 |
|------|------|
| ① | 开启「开发者选项」和「USB 调试」 |
| ② | 连接电脑 USB，信任 RSA 指纹 |
| ③ | 安装 ATX Keyboard（`uiautomator2` 会自动装） |
| ④ | **设置 → 其他设置 → 键盘与输入法 → 默认输入法 → 选 ATX Keyboard** |

> ⚠️ ATX Keyboard 必须设为**默认输入法**，否则中文输入无法工作。

### 3. 使用

```bash
# 完整发布（LLM 生成 → Pexels 配图 → ADB 发布）
python3 xhs_adb_publisher.py --publish --product-url "https://example.com" --product-name "产品名"

# 仅生成不发布（预览）
python3 xhs_adb_publisher.py --publish --dry-run --product-url "https://example.com"

# 直接写长文（跳过 LLM）
python3 xhs_adb_publisher.py --write-long "编辑器正文" --xhs-body "小红书正文" --title "标题"

# 直接写想法
python3 xhs_adb_publisher.py --write-thought "正文内容" --title "标题"

# 旧版 CLI（兼容）
python3 android_ctl.py 写长文 "编辑器正文" "小红书正文" "标题"
python3 android_ctl.py 写想法 "内容" "标题"
```

---

## 文件结构

```
xhs-adb-publisher/
├── xhs_adb_publisher.py           ← 统一 CLI 入口
├── android_ctl.py                 ← 旧版 CLI（兼容）
├── SKILL.md                       ← OpenClaw 技能定义
├── scripts/
│   ├── phone_controller.py        ← ADB 手机操控核心（含随机抖动）
│   ├── xhs_article_publisher.py   ← 文章发布模块 (LLM→Pexels→ADB)
│   ├── xhs_comment_acquisition.py ← 评论区获客 (TODO)
│   ├── xhs_llm.py                 ← DeepSeek API 封装
│   └── pexels_images.py           ← Pexels 图片搜索下载
├── templates/
│   ├── article-prompt.md          ← 小红书文章生成提示词
│   └── comment-prompt.md          ← 评论提示词 (TODO)
├── config/
│   ├── publish.json               ← 发布配置
│   └── pexels.json                ← Pexels 配置
└── data/                           ← 运行时数据（自动创建）
```

---

## 设计

### 架构

```
┌─────────────────┐
│  xhs_adb_publisher.py  │ ← CLI 入口
└────────┬────────┘
         │
    ┌────┴────┬──────────┐
    │         │          │
    ▼         ▼          ▼
┌────────┐ ┌────────┐ ┌──────────────┐
│  LLM   │ │ Pexels │ │ 评论区获客    │
│ 生成文章 │ │ 自动配图 │ │ (TODO)       │
└───┬────┘ └───┬────┘ └──────────────┘
    │         │
    └────┬────┘
         │
         ▼
┌─────────────────┐
│  phone_controller.py │ ← ADB 操控手机
│  (uiautomator2)      │
└────────┬────────┘
         │ USB/WiFi
         ▼
┌─────────────────┐
│  Android 手机    │
│  小红书 App      │
└─────────────────┘
```

### 技术选型

| 组件 | 作用 |
|------|------|
| `uiautomator2` | Python ←→ 手机 ATX Agent 通信 |
| `ATX Keyboard` | 自定义输入法，支持中文注入 |
| `DeepSeek API` | AI 生成小红书风格文章 |
| `Pexels API` | 搜索产品相关配图 |

---

## 风控与安全

### 被封风险分析

ADB 操控模拟的是**真人点击事件**，对小红书 App 来说就是普通 touch 事件，**不是 API 调用**，技术层面无特征。风险主要来自**行为模式**：

| 风险因素 | 级别 | 说明 |
|---------|:---:|------|
| 内容同质化 | ⚠️ | AI 生成的文章结构和用词过于相似 |
| 发布频率 | ⚠️ | 一天发几十篇，明显非人类 |
| 操作节奏 | ⚠️ | 每次间隔完全一致，可被时序分析 |
| 缺少互动 | ⚠️ | 只发不刷不点赞，无正常用户行为 |
| 仅自己可见 | ✅ | 发布后设为仅自己可见，不上广场 |

### 脚本自带的安全策略

- **随机抖动** — 所有 `time.sleep` 加了 ±20% 随机值，操作间隔无规律
- **仅自己可见** — 发布后自动设为仅自己可见
- **差异化模板** — 提示词要求每篇结构和用词不一样
- **分段输入** — 长文编辑器正文 + 小红书正文分开录入

### 建议的运营策略

| 策略 | 说明 |
|------|------|
| 📅 **频率控制** | 每小时最多 1-2 篇，每天不超过 10 篇 |
| 🔄 **内容差异化** | 每篇换开头故事、换语气、换 emoji 组合 |
| 📱 **混合使用** | 手机上正常刷小红书、点赞、收藏 |
| ⏳ **延时发布** | 仅自己可见后，过几天再手动改公开 |
| 🚫 **避免高风险操作** | 不要在评论区高频发私信导流，那是重点打击行为 |

---

## 常见问题

### Q: send_keys 无法输入中文
确保 ATX Keyboard 设为**默认输入法**，不光是「启用」。
```bash
adb shell settings get secure default_input_method
# 应返回: com.github.uiautomator/.AdbKeyboard
```

### Q: 坐标不准
当前坐标适配 1080×2400 屏幕（OnePlus PGCM10）。其他分辨率需校准。

### Q: 卡在卡片样式页
脚本会等待「图片生成中」消失后再点击下一步，最多等 15 秒。

---

## License

MIT

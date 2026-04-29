# XHS ADB Publisher

通过 ADB 操控 Android 手机，自动化发布小红书笔记。

---

## 快速开始

### 1. 环境准备

```bash
pip install uiautomator2 adbutils
export ANDROID_SERIAL=<你的设备序列号>   # adb devices 查看
export DEEPSEEK_API_KEY=sk-xxx           # LLM 文章生成
```

### 2. 手机端配置

| 步骤 | 操作 |
|------|------|
| ① | 开启「开发者选项」和「USB 调试」 |
| ② | 连接电脑 USB，信任 RSA 指纹 |
| ③ | 安装 ATX Keyboard（`uiautomator2` 会自动装，或手动装） |
| ④ | **设置 → 其他设置 → 键盘与输入法 → 默认输入法 → 选 ATX Keyboard** |

> ⚠️ ATX Keyboard 必须设为**默认输入法**，否则中文输入无法工作。仅「启用」不够。

### 3. 使用

```bash
# 完整发布（推荐）
python3 xhs_adb_publisher.py --publish --product-url "https://example.com"

# 仅生成不发布（预览）
python3 xhs_adb_publisher.py --publish --dry-run --product-url "https://example.com"

# 直接写长文（跳过 LLM）
python3 xhs_adb_publisher.py --write-long "编辑器正文" --xhs-body "小红书正文" --title "标题"

# 直接写想法
python3 xhs_adb_publisher.py --write-thought "正文" --title "标题"
```

---

## 发布流程

### 写长文（完整流程）

```
桌面 → 打开小红书 → 点击底部+号 → 点击写文字 → 点击写长文
→ 输入标题 + 输入编辑器正文
→ 点击一键排版 → 选默认排版模板
→ 等待 8s（预览渲染）→ 点击下一步 → 进入发布确认页
→ 点击"添加正文"文本框 → 输入小红书正文(≤900字)
→ 公开可见 → 仅自己可见 → 发布笔记
→ 关闭小红书后台 → 回到桌面
```

### 写想法（纯文字）

```
桌面 → 打开小红书 → 点击+号 → 写文字 → 输入内容
→ 下一步 → 等卡片预览渲染 → 下一步
→ 添加标题 → 仅自己可见 → 发布 → 回桌面
```

---

## 文件结构

```
xhs-adb-publisher/
├── xhs_adb_publisher.py           ← CLI 入口
├── android_ctl.py                 ← 旧版 CLI（兼容）
├── SKILL.md                       ← OpenClaw 技能定义
├── scripts/
│   ├── phone_controller.py        ← ADB 手机操控核心（~130行）
│   ├── xhs_article_publisher.py   ← 文章发布 (LLM→ADB)
│   ├── xhs_comment_acquisition.py ← 评论区获客 (TODO)
│   ├── xhs_llm.py                 ← DeepSeek API 封装
│   └── pexels_images.py           ← Pexels 配图（已弃用，保留引用）
├── templates/
│   ├── article-prompt.md          ← 文章生成提示词
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
xhs_adb_publisher.py (CLI)
        │
        ├── xhs_article_publisher.py  (LLM 生成 + 校验)
        │       │
        │       └── phone_controller.py  (ADB 操控手机)
        │               │
        │               └── Android 手机 · 小红书 App
        │
        └── xhs_comment_acquisition.py  (TODO)
```

### 技术栈

| 组件 | 用途 |
|------|------|
| `uiautomator2` | Python ←→ 手机 ATX Agent 通信 |
| `ATX Keyboard` | 自定义输入法，支持中文注入 |
| `DeepSeek V4-Flash` | AI 生成小红书风格文章 |
| `ADB` | Android Debug Bridge 连接通道 |

### 坐标系统

基于 1080×2400 屏幕，自动按比例缩放适配其他分辨率。

| 页面 | 元素 | 参考坐标 |
|------|------|:--------:|
| 主页 | 底部+号 | (540, 2284) |
| 发布页 | 写文字 | (540, 2079) |
| 写长文入口 | 写长文按钮 | (375, 1931) |
| 编辑页 | 一键排版 | (540, 2232) |
| 卡片样式 | 下一步(底) | (897, 2226) |
| 模板选择 | 下一步(底) | (897, 2256) |
| 发布确认 | 添加正文 | (540, 752) |
| 发布确认 | 公开可见 | (204, 1842) |
| 发布确认 | 仅自己可见 | (297, 2232) |
| 发布确认 | 发布笔记 | (687, 2211) |

---

## LLM 文章生成

### 模型

- `deepseek-v4-flash`（V4 系列，输出上限 384K tokens）
- 环境变量 `DEEPSEEK_API_KEY` 配置 API Key

### 校验规则

| 规则 | 值 | 说明 |
|------|:--:|------|
| 最小总字数 | ≥1800 | 含标点/emoji/空格 |
| 标题上限 | ≤20字 | 超出截断 |
| 小红书正文上限 | ≤900字 | 超出截断 |
| 重试机制 | 最多3次 | 不足字数自动重试 |

### 输出分割

LLM 返回的正文自动切分为两部分：
- **编辑器正文**（前半段）→ 写长文编辑器显示
- **小红书正文**（后半段 ≤900字）→ 发布确认页"添加正文"文本框

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

### Q: 换了手机不兼容
脚本会自动按比例缩放坐标，确保 `ANDROID_SERIAL` 设置正确。

### Q: 发布确认页卡住
脚本内置了 8s 固定等待 + 图片生成中检测，确保预览渲染完成后再操作。

---

## License

MIT

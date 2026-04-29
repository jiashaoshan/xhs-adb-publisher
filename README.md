# XHS ADB Publisher

通过 ADB 操控 Android 手机，自动化发布小红书笔记。

---

## 快速开始

### 1. 环境准备

```bash
# 安装 Python 依赖
pip install uiautomator2 adbutils

# 验证手机连接
adb devices
# 确保显示你的设备: FAS84PQ45T8HTOTK    device
```

### 2. 手机端配置

| 步骤 | 操作 |
|------|------|
| ① | 开启「开发者选项」和「USB 调试」 |
| ② | 连接电脑 USB，信任 RSA 指纹 |
| ③ | 安装 ATX Keyboard（`uiautomator2` 会自动装，或应用商店搜 ATX） |
| ④ | **设置 → 其他设置 → 键盘与输入法 → 默认输入法 → 选 ATX Keyboard** |

> ⚠️ ATX Keyboard 必须设为**默认输入法**，否则中文 `send_keys()` 无法工作。仅「启用」不够。

### 3. 快速测试

```bash
# 设置环境变量（每次运行前）
export ANDROID_SERIAL=FAS84PQ45T8HTOTK

# 测试连接
python3 android_ctl.py info
# 输出示例: 设备: 1080x2400, PGCM10, com.android.launcher

# 写想法
python3 android_ctl.py 写想法 "你好，这是自动发布的笔记" "我的标题"

# 写长文
python3 android_ctl.py 写长文 "这是编辑区正文内容" "这是小红书正文" "长文标题"
```

---

## 设计

### 整体架构

```
┌──────────────┐    USB/WiFi    ┌─────────────┐    uiautomator2    ┌──────────┐
│  你的电脑      │ ───────────→  │ Android 手机 │ ────────────────→ │ 小红书App │
│ android_ctl.py │              │ ATX Agent    │   点击/输入/截图  │          │
└──────────────┘               │ ATX Keyboard │                  └──────────┘
                                └─────────────┘
```

### 技术选型

| 组件 | 作用 |
|------|------|
| `uiautomator2` | Python 库，通过 ADB 与手机 ATX Agent 通信 |
| `ATX Agent` | 手机上运行的服务进程，执行 UI 操作 |
| `ATX Keyboard` | 自定义输入法，支持通过 ADB broadcast 注入中文 |
| `ADB` | Android Debug Bridge，USB 连接通道 |

### 核心流程

**写想法：**
```
桌面 → 打开小红书 → 点击底部+号 → 点击写文字
→ 输入正文内容
→ 点击下一步(顶) → 进入卡片样式页
→ 等图片渲染完成 → 点击下一步(底) → 进入发布确认页
→ 录入标题
→ 公开可见 → 仅自己可见
→ 发布笔记 → 回到桌面
```

**写长文：**
```
桌面 → 打开小红书 → 点击底部+号 → 点击写文字 → 点击写长文
→ 输入标题 + 输入编辑区正文
→ 点击一键排版 → 模板选择页
→ 选默认排版模板 → 点击下一步 → 发布确认页
→ 录入小红书正文（标题自动带入）
→ 公开可见 → 仅自己可见
→ 发布笔记 → 回到桌面
```

---

## 实现

### 文件结构

```
xhs-adb-publisher/
├── SKILL.md             # OpenClaw 技能定义
├── README.md            # 本文档
├── android_ctl.py       # 主脚本（~160行）
├── requirements.txt     # Python 依赖
└── install.sh           # 一键安装脚本
```

### 核心函数

| 函数 | 作用 |
|------|------|
| `xie_xie_fa(content, title)` | 写想法 — 纯文字笔记 |
| `xie_chang_wen(editor_body, publish_body, title)` | 写长文 — 排版后发 |
| `_open_xhs()` | 打开小红书 + 点+号 |
| `_card_style_to_publish(d)` | 卡片样式页 → 发布确认页（含等渲染） |
| `_visibility_and_publish(d)` | 设置仅自己可见 → 发布 → 回桌面 |

### 坐标系统

基于 1080×2400 屏幕（OnePlus PGCM10），如需适配其他屏幕需调整坐标：

| 元素 | 坐标 (x, y) |
|------|:-----------:|
| 底部+号 | (540, 2284) |
| 写文字 | (540, 2079) |
| 写长文 | (375, 1931) |
| 下一步(顶) | (920, 176) |
| 下一步(底-卡片页) | (897, 2226) |
| 下一步(底-模板页) | (897, 2256) |
| 添加标题 | (562, 629) |
| 小红书正文 | (540, 752) |
| 公开可见 | (204, 1842) |
| 仅自己可见 | (297, 2232) |
| 发布笔记 | (687, 2211) |

---

## 安装部署

### 方式一：直接使用

```bash
git clone <repo-url>
cd xhs-adb-publisher
pip install -r requirements.txt
export ANDROID_SERIAL=<你的设备序列号>
python3 android_ctl.py 写想法 "测试" "标题"
```

### 方式二：OpenClaw 技能安装

将本目录链接或复制到 `~/.openclaw/workspace/skills/` 下：

```bash
ln -s $(pwd) ~/.openclaw/workspace/skills/xhs-adb-publisher
```

## 常见问题

### Q: send_keys 无法输入中文
确保 ATX Keyboard 设为**默认输入法**，不光是「启用」。
```bash
adb shell settings get secure default_input_method
# 应该返回: com.github.uiautomator/.AdbKeyboard
```

### Q: 坐标不准确
如果你的手机分辨率不是 1080×2400，需要重新校准坐标：
```bash
# 截图 + 查看元素 bounds
python3 -c "
import uiautomator2 as u2
d = u2.connect()
d.screenshot('/tmp/debug.png')
xml = d.dump_hierarchy()
# 解析 xml 找目标元素的 bounds
"
```

### Q: 卡在卡片样式页
等「图片生成中」消失后再点下一步，脚本已内置等待逻辑。

---

## License

MIT

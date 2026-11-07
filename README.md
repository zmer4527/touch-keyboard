# Touch Keyboard

一个面向 Linux 和 Windows 的屏幕键盘。布局取自 DroidDeck 的 PC 键盘，通过 uinput（Windows 上为 SendInput）向当前前台应用输入按键，支持触摸、多点触控、实体键盘联动和 Fcitx5 候选框固定。

Linux 提供 AppImage 和源码；Windows 源码已可运行，便携版由后续维护者打包发布。

## 功能

- **PC 键盘布局**：6 行 82 键，支持 Shift、AltGr、Caps、Super 和方向键。
- **输入注入**：
  - Linux：uinput，兼容 X11、Wayland、XWayland。
  - Windows：SendInput 扫描码。
- **触摸支持**：多点触控、修饰键与字母同时按下、滑动取消、长按重复。
- **修饰键模式**（托盘 → 快捷键操作方式）：
  - 混合：轻点粘滞一次，按住临时生效，双击锁定。
  - 长按：仅按住期间生效。
  - 粘滞：轻点保持，下一次按键后释放，再次点击取消。
- **Super 键**：支持轻点、长按组合键和双击锁定。
- **外观**：可调键盘宽度、背景透明度、圆角半透明窗口；按键按下带渐显/渐隐反馈。
- **语言**：界面支持中文和英文。
- **托盘菜单**：
  - 显示/隐藏键盘（第一项）
  - 大小（30%–100%，每 10% 一档）
  - 透明度（20%–100%，每 10% 一档）
  - 语言
  - 快捷键操作方式
  - F1-F12 行开关
  - Fcitx 候选框固定
  - 退出
- **实体键盘跟踪**：实体键按下时同步高亮屏幕键盘，默认开启。
- **Fcitx5 候选框**：可嵌入屏幕键盘顶部，关闭键盘时自动恢复 Fcitx 原候选窗。
- **单实例**：再次启动会切换已有窗口的显示/隐藏。
- **配置持久化**：语言、位置、尺寸、透明度、跟踪开关、修饰键模式等自动保存。

## 平台要求

### Linux

- Python 3.10+
- PySide6
- X11 或 Wayland 桌面
- 可选：Fcitx5 及 Kimpanel 支持（候选框固定功能）

### Windows

- Python 3.10+
- PySide6

Windows 源码已支持运行，便携版尚未随仓库发布，将由后续维护者打包。Windows 构建不包含 Fcitx5 候选框、uinput/evdev/udev 和 Linux 权限相关功能。

## 快速开始

### 从源码运行

```bash
python3 -m pip install -r requirements.txt
python3 -m osk
```

也可以直接运行：

```bash
python3 touch_keyboard.py
```

### 安装到当前用户目录

```bash
./packaging/install-user.sh
```

脚本会安装启动器和桌面图标，并提示 uinput 权限配置。卸载：

```bash
./packaging/install-user.sh --uninstall
```

### Linux 权限

输入注入需要写入 `/dev/uinput`：

```bash
sudo install -Dm644 packaging/udev/60-droiddeck-touch-keyboard.rules \
  /etc/udev/rules.d/60-droiddeck-touch-keyboard.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --name-match=uinput
```

实体键盘跟踪需要读取 `/dev/input/event*`。默认开启；如果没有权限，启动时或启用时会通过 `pkexec` 请求管理员认证，并使用 `setfacl` 为当前用户授予读取权限。

检查环境：

```bash
python3 -m osk --doctor
```

### Windows

```powershell
python -m pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File packaging\run-windows.ps1
```

## AppImage

构建 Linux AppImage：

```bash
./packaging/build-appimage.sh
```

产物位于 `dist/TouchKeyboard-0.1.0-x86_64.AppImage`，同时生成 SHA256 文件。运行需要系统提供基础 X11/GL 运行库；Wayland 会话默认通过 XWayland 运行。

## Windows 便携版与打包说明

Windows 便携版将由后续维护者发布。当前仓库中的源码可直接运行；如需构建便携版，建议注意以下事项：

- 使用 Windows x64 的 Python 3.10+、PySide6 和 PyInstaller。
- 使用 PyInstaller 的 **onedir** 模式，确保启动速度并方便替换资源。
- 打包时包含：
  - `osk/`
  - `touch_keyboard.py`
  - `layout.json`
  - `assets/`
  - `requirements.txt`（源码包）
- 移除或隐藏以下 Linux 专用功能：
  - Fcitx5 Kimpanel 候选框、顶部候选栏
  - `osk/backends/uinput.py`
  - `osk/platform/evdev_monitor.py`
  - `osk/platform/kimpanel.py`
  - `osk/ui/candidate_bar.py`
  - `packaging/udev`
  - `assets/input-access-helper.sh`
  - AppImage 相关脚本
- 托盘菜单应保留：显示/隐藏、大小、透明度、语言、快捷键操作方式、F1-F12 行、退出。
- 不要把 Fcitx 候选框选项显示在 Windows 托盘中。
- 建议输出结构：

```text
TouchKeyboard-<版本>-win64/
  touch-keyboard.exe
  _internal/
  README-Windows.md
```

- 建议产物命名：`TouchKeyboard-<版本>-windows-x64.zip`。
- 发布前至少验证：程序启动、托盘菜单、SendInput 输入、触摸/鼠标操作、实体键盘高亮、配置保存。

## 配置文件

默认路径：

```text
~/.config/linux-touch-keyboard/config.json
```

Windows：

```text
%APPDATA%\linux-touch-keyboard\config.json
```

示例：

```json
{
  "lang": "zh",
  "width": 1344,
  "x": 51,
  "y": 553,
  "fn_visible": true,
  "palm_limit": 0.0,
  "opacity": 70,
  "pin_candidates": false,
  "track_keyboard": true,
  "modifier_mode": "hybrid"
}
```

## 常用命令行参数

```text
--lang en|zh              界面语言
--width 1200              初始宽度（像素）
--opacity 70              背景透明度（20–100）
--no-fn                   隐藏 F1-F12 行
--no-track-keyboard       关闭实体键盘跟踪
--keyboard-device PATH    只监听指定 /dev/input/event*
--pin-candidates          启用 Fcitx 候选框固定
--restore-fcitx           恢复 Fcitx 原候选界面
--no-tray                 不创建托盘图标
--no-instance             启动独立实例
--quit                    退出已运行的实例
--dry-run                 不创建 uinput 设备
--check                   校验布局
--doctor                  输出环境诊断
```

## Fcitx5 候选框

该功能仅支持 Linux。Windows 没有 Fcitx5/Kimpanel/D-Bus 数据源，候选栏不会显示，构建时应隐藏该托盘选项。

在 Linux 托盘菜单中启用“候选框固定到键盘上方”后：

- 通过 Kimpanel 接管 Fcitx 候选词。
- 候选条嵌入键盘顶部，显示预编辑文本、候选词和翻页按钮。
- 键盘隐藏或退出时恢复 Fcitx 原候选窗。
- 如异常退出导致 Fcitx 候选窗未恢复，可运行：

```bash
python3 -m osk --restore-fcitx
```

## 开发

```bash
python3 -m pytest -q
```

### 项目结构

```text
assets/                    图标等运行资源
osk/
  core/                    布局、状态机、触摸路由
  backends/                uinput / Windows SendInput
  platform/                托盘、Fcitx、实体键盘、权限 helper
  ui/                      Qt 界面
packaging/                 安装脚本、AppImage 打包、udev 规则
tests/                     单元测试
layout.json                键盘布局
extract_layout.py          从 DroidDeck 提取布局的工具
```

## 已知限制

- Wayland 原生 layer-shell 未接入，默认使用 XWayland 保证置顶与不抢焦点。
- 实体键盘跟踪依赖 `/dev/input` 读取权限；授权 ACL 在设备重插或重启后可能失效。
- Fcitx 候选框固定依赖 Fcitx5 Kimpanel 和系统 D-Bus。
- Windows 便携版由后续维护者打包；当前 Windows 支持源码运行和 SendInput 注入。
- Windows 实体键盘跟踪使用约 16ms 轮询。
- Windows 不支持 Fcitx 候选框固定。
- 本程序不内置任何第三方音频文件。

## 致谢

- 键盘布局来自 [DroidDeck](https://github.com/Droid-Deck/DroidDeck)（GPL-3.0）。
- Fcitx5 候选框集成使用 Kimpanel D-Bus 协议。
- 界面基于 Qt / PySide6。

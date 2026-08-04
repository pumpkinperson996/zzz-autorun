# ZZZ-Autorun

**绝区零一条龙的本机无人值守恢复与实机实验工具**

**Local unattended recovery and live-experiment tools for ZenlessZoneZero-OneDragon**

[中文](#中文) · [English](#english)

> [!IMPORTANT]
> 本项目仅支持 Windows，默认安装目录为 `C:\ZZZ-OD`，主脚本使用 AutoHotkey v1.1。
>
> This project is Windows-only, assumes `C:\ZZZ-OD`, and requires AutoHotkey v1.1.

---

## 中文

### 项目简介

ZZZ-Autorun 是 [ZenlessZoneZero-OneDragon](https://github.com/OneDragon-Anything/ZenlessZoneZero-OneDragon) 的外部恢复层。它负责启动一条龙、调用首页的「启动一条龙」、确认任务真正开始，并在进程退出、日志报错或定时刷新时恢复运行。

仓库还包含一套实验性的实机闭环工具，用于收集游戏现场证据、限制自动补丁范围并比较实机结果。该部分仍处于实验阶段，不应直接加入无人值守计划任务。

### 主要功能

| 功能 | 默认行为 |
|---|---|
| 启动按钮定位 | 优先使用 Windows UI Automation；Qt 未暴露按钮时使用 Windows OCR |
| 启动确认 | 等待一条龙新增日志或新的游戏进程，避免“点了但没启动” |
| 失败恢复 | 每 30 秒扫描一条龙日志，检测失败后重启游戏和一条龙 |
| 进程守卫 | 每 10 分钟检查游戏与一条龙进程 |
| 定时刷新 | 每 1 小时重启一次；文件名中的 `90min` 只是历史名称 |
| 顶号冷却 | 读取主程序守护插件写入的冷却标记，冷却结束前不重新登录 |
| 手动暂停 | `F10` 暂停外部恢复监控，`F9` 恢复 |

顶号弹窗的持续检测由一条龙安装目录中的 `plugins/unattended_guardian` 负责，不再由 AHK 持续 OCR。插件可写入以下冷却标记：

```text
C:\ZZZ-OD\.debug\temp\unattended_kicked_until.txt
```

AHK 在每次恢复前读取该标记。冷却未结束时只等待；结束后删除标记并继续启动。

### 启动流程

1. 启动 `C:\ZZZ-OD\OneDragon-Launcher.exe`。
2. 等待 Qt 主窗口，并额外等待 15 秒完成应用注册。
3. UI Automation 按 `AutomationId=start_button` 或名称「启动一条龙」查找按钮。
4. UI Automation 不可用时，OCR 只接受规范化后与「启动一条龙」完全一致、位于客户区右下区域的文字。
5. 调用按钮后，等待 `.log\log.txt` 出现新的顶层一条龙日志，或检测到新游戏进程。
6. 确认成功后才进入失败检测、进程守卫和定时刷新。

窗口移动、缩放或分辨率变化不再依赖历史固定坐标。OCR 点击坐标必须同时位于 Qt 客户区和 Windows 虚拟桌面内，否则助手会拒绝点击。

### 环境与目录

- AutoHotkey v1.1；脚本不是 v2 语法。
- 一条龙启动器：`C:\ZZZ-OD\OneDragon-Launcher.exe`。
- 一条龙内置 Python：`C:\ZZZ-OD\.install\python\cpython-3.11.12-windows-x86_64-none\python.exe`。
- Python 环境需要 `pywin32`、`mss`、`Pillow` 和 Windows Media OCR 对应的 `winrt` 包；一条龙完整环境通常已经包含这些依赖。
- 本仓库应放在 `C:\ZZZ-OD\ZZZ-autorun`。

关键文件：

```text
ZZZ-autorun/
├── OneDragon_FINAL_Restart_90min.ahk
├── scripts/
│   ├── click_start_button.py
│   └── click_start_button_uia.ps1
├── loop/                         # 实验性实机闭环
├── 查看实时日志.bat
├── 清空日志.bat
└── logs/closedloop.log           # 运行时生成，不提交到 Git
```

### 快速开始

1. 安装 [AutoHotkey v1.1](https://www.autohotkey.com/)。
2. 把仓库克隆到固定目录：

   ```powershell
   git clone https://github.com/pumpkinperson996/zzz-autorun.git C:\ZZZ-OD\ZZZ-autorun
   ```

3. 确认一条龙完整环境与上述 Python 依赖已经安装。
4. 双击 `OneDragon_FINAL_Restart_90min.ahk`。
5. 打开 `查看实时日志.bat`，确认日志依次出现：

   ```text
   START: button invoked, result=OK:OCR:x=1376,y=834
   START: confirmed via onedragon_log
   MONITOR: armed
   ```

需要开机自启时，可在 Windows 任务计划程序中用 AutoHotkey v1.1 启动主脚本，并把起始目录设为 `C:\ZZZ-OD\ZZZ-autorun`。脚本本身不会创建每日强制重启电脑的任务。

### 启动定位诊断

只定位、不点击当前 Qt 首页按钮：

```powershell
& "C:\ZZZ-OD\.install\python\cpython-3.11.12-windows-x86_64-none\python.exe" `
  "C:\ZZZ-OD\ZZZ-autorun\scripts\click_start_button.py" --locate-only
```

成功时输出 `OK:UIA:x=...,y=...` 或 `OK:OCR:x=...,y=...`。`RETRY:*` 表示窗口或按钮尚未就绪；`ERROR:*` 表示依赖、截图或坐标校验异常。添加 `--skip-uia` 可单独验证 OCR 兜底。

### 手动控制

- `F10`：暂停外部恢复监控。
- `F9`：恢复外部恢复监控。
- `查看实时日志.bat`：查看 `logs\closedloop.log`。
- `清空日志.bat`：清空运行日志。

### 实验性实机闭环

`loop/` 包含执行方客户端、导航、异常界面必停锁、文件改动安全锁、实机采样和常驻刷菲林工具。它可能修改并回滚 `C:\ZZZ-OD\plugins\lost_void_film` 中的源码，因此只适合了解实现细节并能检查 Git 状态的开发者。

使用前至少需要：

- `plugins/lost_void_film` 有独立、干净的 Git 工作区；
- `C:\ZZZ-OD\.env` 中配置 `FIREWORKS_API_KEY`；
- 游戏窗口可用，且没有其他自动化同时控制游戏；
- 人工审查采样数、判定标准和最终补丁。

当前实现仍是实验工具，不代表完整、可长期无人值守的统计闭环。不要直接把 `python -m loop.run` 加入计划任务。

### 本地验证

```powershell
& "C:\Program Files\AutoHotkey\AutoHotkey.exe" /ErrorStdOut `
  "C:\ZZZ-OD\ZZZ-autorun\OneDragon_FINAL_Restart_90min.ahk" --check

& "C:\ZZZ-OD\.install\python\cpython-3.11.12-windows-x86_64-none\python.exe" `
  -m unittest scripts.test_click_start_button

& "C:\ZZZ-OD\.install\python\cpython-3.11.12-windows-x86_64-none\python.exe" `
  loop\guard.py

& "C:\ZZZ-OD\.install\python\cpython-3.11.12-windows-x86_64-none\python.exe" `
  loop\test_abort.py
```

---

## English

### Overview

ZZZ-Autorun is an external recovery layer for [ZenlessZoneZero-OneDragon](https://github.com/OneDragon-Anything/ZenlessZoneZero-OneDragon). It launches OneDragon, invokes the home-page “Start OneDragon” action, verifies that the run actually started, and recovers from process exits, failure logs, or scheduled refreshes.

The repository also contains experimental live-game loop tools for collecting evidence, restricting automated patches, and comparing results from real game runs. That part is still experimental and should not be added directly to an unattended scheduled task.

### Main features

| Feature | Default behavior |
|---|---|
| Start-button discovery | Uses Windows UI Automation first, then Windows OCR when Qt does not expose the button |
| Start confirmation | Waits for new OneDragon log output or a new game process, preventing false “clicked but not started” states |
| Failure recovery | Scans the OneDragon log every 30 seconds and restarts both processes after a failure |
| Process watchdog | Checks the game and OneDragon processes every 10 minutes |
| Scheduled refresh | Restarts every hour; `90min` in the file name is historical |
| Login-conflict cooldown | Reads the cooldown marker written by the guardian plugin and blocks login until it expires |
| Manual pause | `F10` pauses external recovery monitoring; `F9` resumes it |

Continuous login-conflict detection belongs to `plugins/unattended_guardian` in the OneDragon installation; AHK no longer runs continuous OCR for that popup. The plugin can write this marker:

```text
C:\ZZZ-OD\.debug\temp\unattended_kicked_until.txt
```

AHK reads it before every recovery attempt. It waits while the cooldown is active, then removes the marker and resumes startup.

### Startup flow

1. Launch `C:\ZZZ-OD\OneDragon-Launcher.exe`.
2. Wait for the Qt main window, then allow another 15 seconds for application registration.
3. Search through UI Automation for `AutomationId=start_button` or the name “启动一条龙”.
4. If UI Automation is unavailable, OCR accepts only text that normalizes exactly to “启动一条龙” and appears in the lower-right part of the client area.
5. After invoking the button, wait for new top-level OneDragon output in `.log\log.txt` or a new game process.
6. Arm failure detection, the process watchdog, and scheduled refresh only after startup is confirmed.

Window movement, resizing, and resolution changes no longer depend on a historical fixed coordinate. An OCR click must be inside both the Qt client area and the Windows virtual desktop, or the helper refuses it.

### Requirements and layout

- AutoHotkey v1.1; the script is not compatible with v2 syntax.
- OneDragon launcher: `C:\ZZZ-OD\OneDragon-Launcher.exe`.
- Bundled OneDragon Python: `C:\ZZZ-OD\.install\python\cpython-3.11.12-windows-x86_64-none\python.exe`.
- Python packages: `pywin32`, `mss`, `Pillow`, and the `winrt` packages needed by Windows Media OCR. The OneDragon full environment normally includes them.
- Clone this repository to `C:\ZZZ-OD\ZZZ-autorun`.

Key files:

```text
ZZZ-autorun/
├── OneDragon_FINAL_Restart_90min.ahk
├── scripts/
│   ├── click_start_button.py
│   └── click_start_button_uia.ps1
├── loop/                         # Experimental live-game loop
├── 查看实时日志.bat
├── 清空日志.bat
└── logs/closedloop.log           # Generated at runtime; not committed
```

### Quick start

1. Install [AutoHotkey v1.1](https://www.autohotkey.com/).
2. Clone the repository to the fixed location:

   ```powershell
   git clone https://github.com/pumpkinperson996/zzz-autorun.git C:\ZZZ-OD\ZZZ-autorun
   ```

3. Make sure the full OneDragon environment and the Python dependencies above are installed.
4. Double-click `OneDragon_FINAL_Restart_90min.ahk`.
5. Open `查看实时日志.bat` and confirm that the log reaches:

   ```text
   START: button invoked, result=OK:OCR:x=1376,y=834
   START: confirmed via onedragon_log
   MONITOR: armed
   ```

For startup at sign-in, configure Windows Task Scheduler to run the main script with AutoHotkey v1.1 and set `C:\ZZZ-OD\ZZZ-autorun` as the working directory. The script does not create a daily forced-reboot task.

### Start-button diagnostics

Locate the current Qt home-page button without clicking it:

```powershell
& "C:\ZZZ-OD\.install\python\cpython-3.11.12-windows-x86_64-none\python.exe" `
  "C:\ZZZ-OD\ZZZ-autorun\scripts\click_start_button.py" --locate-only
```

Success returns `OK:UIA:x=...,y=...` or `OK:OCR:x=...,y=...`. `RETRY:*` means that the window or button is not ready; `ERROR:*` reports a dependency, capture, or coordinate-validation failure. Add `--skip-uia` to test the OCR fallback directly.

### Manual controls

- `F10`: pause external recovery monitoring.
- `F9`: resume external recovery monitoring.
- `查看实时日志.bat`: view `logs\closedloop.log`.
- `清空日志.bat`: clear the runtime log.

### Experimental live-game loop

`loop/` contains the executor client, navigation, mandatory-stop checks for unexpected screens, file-write guards, live sampling, and continuous film farming tools. It can modify and roll back source files under `C:\ZZZ-OD\plugins\lost_void_film`, so it is intended only for developers who understand the implementation and can inspect Git state.

Before using it, you need at least:

- an independent, clean Git worktree for `plugins/lost_void_film`;
- `FIREWORKS_API_KEY` in `C:\ZZZ-OD\.env`;
- an available game window with no other automation controlling it;
- human review of the sample size, acceptance criteria, and resulting patch.

The current implementation is an experimental tool, not a complete statistically reliable unattended loop. Do not add `python -m loop.run` directly to Task Scheduler.

### Local verification

```powershell
& "C:\Program Files\AutoHotkey\AutoHotkey.exe" /ErrorStdOut `
  "C:\ZZZ-OD\ZZZ-autorun\OneDragon_FINAL_Restart_90min.ahk" --check

& "C:\ZZZ-OD\.install\python\cpython-3.11.12-windows-x86_64-none\python.exe" `
  -m unittest scripts.test_click_start_button

& "C:\ZZZ-OD\.install\python\cpython-3.11.12-windows-x86_64-none\python.exe" `
  loop\guard.py

& "C:\ZZZ-OD\.install\python\cpython-3.11.12-windows-x86_64-none\python.exe" `
  loop\test_abort.py
```

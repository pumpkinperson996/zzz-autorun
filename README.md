# 无人值守自动运行指南

本指南面向**不会写代码的普通用户**，帮助你在 Windows 10 上配置一套全自动运行一条龙的系统。

配置完成后，电脑可以每天自动重启，重启后自动登录，自动启动一条龙并点击开始，遇到游戏异常自动关闭并重启，全程不需要人工干预。

---

## 目录

1. [整体流程是什么](#1-整体流程是什么)
2. [文件放在哪里](#2-文件放在哪里)
3. [首次配置步骤](#3-首次配置步骤)
   - [3A. 安装 AutoHotkey](#3a-安装-autohotkey)
   - [3B. 安装 Python OCR 依赖](#3b-安装-python-ocr-依赖)
   - [3C. 配置 Windows 自动登录](#3c-配置-windows-自动登录)
   - [3D. 配置任务计划程序](#3d-配置任务计划程序)
4. [日常使用说明](#4-日常使用说明)
   - [启动与停止脚本](#启动与停止脚本)
   - [手动模式（自己玩游戏）](#手动模式自己玩游戏)
   - [查看运行状态](#查看运行状态)
5. [脚本参数说明](#5-脚本参数说明)
6. [测试方法](#6-测试方法)
7. [常见问题排查](#7-常见问题排查)

---

## 1. 整体流程是什么

```
每天凌晨 4 点 → 电脑自动重启
       ↓
  Windows 自动登录
       ↓
  自动启动监控脚本
       ↓
  脚本启动 OneDragon-Launcher.exe
       ↓
  等待一条龙界面加载完成
       ↓
  自动点击「启动一条龙 🚀」按钮
       ↓
  ┌──────────────────────────────────────────────────────────┐
  │  持续监控（四条并行检测线）                                │
  │                                                          │
  │  ① 每 0.5 秒  OCR 识别游戏画面，检测是否出现              │
  │               「其他地方登录」字样（被顶号弹窗）           │
  │               F10 暂停期间此检测仍然持续运行               │
  │  ② 每 30 秒   读取一条龙日志，检测是否出现               │
  │               「指令[ 一条龙 ] 执行失败」                 │
  │  ③ 每 10 分钟 检查两个进程是否都还活着（进程守卫）         │
  │  ④ 每 1 小时  强制重启一条龙（防止长时间运行卡死）         │
  └──────────────────────────────────────────────────────────┘
       ↓ 触发后
  关闭游戏本体 + 关闭一条龙
       ↓
  ① 触发：等待 2 小时再重启（账号被顶号，等待对方用完）
  ②③④ 触发：立即重启（运行出错或进程消失）
       ↓
  重新启动一条龙（游戏由一条龙自动拉起）
       ↓
  回到「持续监控」状态
```

**被顶号检测**：使用 Windows 内置 OCR 引擎识别游戏画面文字，不依赖截图文件，不受分辨率变化影响。

**进程守卫**：启动一条龙后有 3 分钟宽限期，避免游戏还没拉起来就误判。

---

## 2. 文件放在哪里

**所有文件统一放在 `C:\ZZZ-OD\ZZZ-autorun\` 目录下**，与一条龙主程序分开。

```
C:\ZZZ-OD\
├── OneDragon-Launcher.exe      ← 一条龙（不要动）
├── .install\                   ← 一条龙（不要动）
├── .log\                       ← 一条龙运行日志（不要动）
│
└── ZZZ-autorun\                ← 你的自动化脚本目录
    ├── OneDragon_FINAL_Restart_90min.ahk   ← 主监控脚本（双击运行）
    ├── OCR测试工具.bat                      ← 双击打开 OCR 实时检测
    ├── 查看实时日志.bat                     ← 双击实时查看运行日志
    ├── 清空日志.bat                         ← 双击删除日志文件
    ├── logs\
    │   └── closedloop.log                  ← 运行日志（自动生成）
    └── scripts\
        ├── ocrcheck.py                     ← OCR 检测逻辑（不要动）
        └── ocrtest_gui.py                  ← OCR 测试界面（不要动）
```

从 GitHub 下载文件后，按照上面的结构放好即可。**不需要修改任何代码**，直接双击 `.ahk` 文件运行。

---

## 3. 首次配置步骤

### 3A. 安装 AutoHotkey

1. 访问 [https://www.autohotkey.com/](https://www.autohotkey.com/)
2. 点击 **Download** → 选择 **AutoHotkey v1.1**（必须是 v1，不是 v2）
3. 安装完成后 `.ahk` 文件会显示绿色图标

---

### 3B. 安装 Python OCR 依赖

被顶号检测需要安装 Python 包，**只需安装一次**。

打开 PowerShell（搜索栏输入 `powershell`），粘贴以下命令回车：

```powershell
& "C:\ZZZ-OD\.install\python\cpython-3.11.12-windows-x86_64-none\python.exe" -m pip install winrt-runtime "winrt-Windows.Media.Ocr" "winrt-Windows.Graphics.Imaging" "winrt-Windows.Storage.Streams" "winrt-Windows.Security.Cryptography" "winrt-Windows.Foundation" "winrt-Windows.Globalization" "winrt-Windows.Foundation.Collections" mss pywin32 Pillow
```

安装完成后运行一次 OCR 测试工具确认正常（见第 6 节）。

---

### 3C. 配置 Windows 自动登录

电脑重启后需要自动进入桌面，否则脚本无法启动。

1. 按 `Win + R`，输入 `netplwiz`，回车
2. 点击你的账户
3. **取消勾选**「要使用本计算机，用户必须输入用户名和密码」
4. 点「应用」，输入 Windows 登录密码（两次），确定
5. 重启验证：应直接进入桌面

> ⚠️ 自动登录意味着任何人拿到电脑都能进入系统，请确保电脑处于安全环境。

---

### 3D. 配置任务计划程序

设置开机自动启动监控脚本，并每天凌晨 4 点重启电脑。

按 `Win + S` 搜索「任务计划程序」打开。

#### 任务一：每天定时重启

1. 右侧点「**创建基本任务**」
2. 名称填 `Daily Reboot 4AM`
3. 触发器选「每天」，时间填 `04:00:00`
4. 操作选「启动程序」，程序填：
   ```
   C:\Windows\System32\shutdown.exe
   ```
5. 参数填：
   ```
   /r /t 0 /f
   ```
6. 完成

#### 任务二：登录后自动启动脚本

1. 右侧点「**创建任务**」
2. **「常规」选项卡**：
   - 名称填 `OneDragon AutoRun`
   - 勾选「**使用最高权限运行**」
   - 配置选 `Windows 10`
3. **「触发器」选项卡**：新建 → 开始任务选「**登录时**」→ 确定
4. **「操作」选项卡**：新建 → 启动程序：
   - 程序或脚本：
     ```
     C:\Program Files\AutoHotkey\v1.1\AutoHotkey.exe
     ```
   - 添加参数：
     ```
     "C:\ZZZ-OD\ZZZ-autorun\OneDragon_FINAL_Restart_90min.ahk"
     ```
   - 起始于：
     ```
     C:\ZZZ-OD\ZZZ-autorun
     ```
5. **「设置」选项卡**：「如果此任务已经运行」改为「**不启动新实例**」
6. 确定保存

**验证**：注销再重新登录，看任务栏右下角是否出现 AutoHotkey 图标（绿色 H 形）。

---

## 4. 日常使用说明

### 启动与停止脚本

| 操作 | 方法 |
|------|------|
| 启动脚本 | 双击 `OneDragon_FINAL_Restart_90min.ahk` |
| 停止脚本 | 任务管理器 → 找到 AutoHotkey 进程 → 结束任务 |
| 重启脚本 | 先结束任务，再双击 `.ahk` 文件 |

> 修改脚本参数后必须重启脚本才能生效。

---

### 手动模式（自己玩游戏）

| 按键 | 效果 |
|------|------|
| `F10` | 暂停监控（同时停止一条龙） |
| `F9` | 恢复监控（同时恢复一条龙） |

按 F10 后屏幕左上角会弹出**红色「监控已暂停」**提示框，按 F9 弹出**绿色「监控已恢复」**。

**注意**：F10 暂停期间，日志扫描和进程守卫停止，但**被顶号 OCR 检测仍然运行**——手动游玩时被顶号仍会自动处理。

---

### 查看运行状态

| 工具 | 用途 |
|------|------|
| 双击 `查看实时日志.bat` | 实时滚动显示运行日志，有新内容自动刷新 |
| 双击 `OCR测试工具.bat` | 实时查看 OCR 识别内容，验证被顶号检测是否正常 |
| 双击 `清空日志.bat` | 删除旧日志文件（重新测试前用） |

日志文件位于：
```
C:\ZZZ-OD\ZZZ-autorun\logs\closedloop.log
```

**正常运行时日志样例：**
```
2026-05-19 06:00:01  BOOT: closed-loop started.
2026-05-19 06:00:05  START: clicked start button at screen x=2535 y=1535
2026-05-19 06:00:05  MONITOR: armed
2026-05-19 06:05:05  OCR: heartbeat result=NOT_FOUND
```

> `MONITOR: armed` 出现后所有检测才开始工作，看到这行说明脚本运行正常。

**检测到被顶号：**
```
2026-05-19 10:15:33  OCR: state changed -> FOUND
2026-05-19 10:15:33  DETECTED: popup text found by OCR
2026-05-19 10:15:33  CLOSE: force killing OneDragon
2026-05-19 10:15:33  SLEEP: waiting before restart
2026-05-19 12:15:33  RESTART: waking up          ← 2 小时后重启
```

**检测到运行失败：**
```
2026-05-19 08:23:11  FAILDETECT: failure pattern found in OneDragon log
2026-05-19 08:23:12  FAILDETECT: restarting OneDragon
```

---

## 5. 脚本参数说明

用记事本打开 `OneDragon_FINAL_Restart_90min.ahk`，顶部 `===== CONFIG =====` 区域内的参数可以修改：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `btnX` / `btnY` | `1470` / `1055` | 「启动一条龙」按钮坐标，用 Window Spy 测量 |
| `postLaunchSleep` | `1500` | 一条龙启动后等多久再点按钮（毫秒） |
| `ocrInterval` | `500` | 被顶号 OCR 检测间隔（毫秒） |
| `restartDelay` | `7200000` | 被顶号后等多久重启（毫秒），默认 2 小时 |
| `failCheckInterval` | `30000` | 读取一条龙日志间隔（毫秒），默认 30 秒 |
| `periodicRestartInterval` | `3600000` | 定时强制重启间隔（毫秒），默认 1 小时 |

**按钮坐标如何测量：**
1. 打开 AutoHotkey 安装目录，找到 `WindowSpy.ahk` 双击运行
2. 启动一条龙，等界面加载完成
3. 鼠标移到「启动一条龙 🚀」按钮正中心
4. 记录 Window Spy 里 `Client` 那行的两个数字，填入 `btnX` 和 `btnY`

**常用时间换算：**
```
30000  = 30 秒     600000  = 10 分钟
60000  = 1 分钟    3600000 = 1 小时
300000 = 5 分钟    7200000 = 2 小时
```

---

## 6. 测试方法

### 测试一：确认脚本正常启动

1. 双击 `OneDragon_FINAL_Restart_90min.ahk`
2. 双击 `查看实时日志.bat`
3. 等待日志出现 `MONITOR: armed`，出现后说明所有检测已开始工作

### 测试二：测试被顶号 OCR 检测

1. 确认游戏正在运行，日志已出现 `MONITOR: armed`
2. 双击 `OCR测试工具.bat`，窗口显示 `NOT_FOUND` 为正常
3. 打开记事本，输入 `其他地方登录`，字体调大，拖到游戏窗口上
4. OCR 测试工具应变为绿色 `FOUND`
5. 同时查看运行日志，应出现 `OCR: state changed -> FOUND`

### 测试三：测试运行失败检测

> 把 `failCheckInterval` 临时改为 `10000`（10 秒），测试完改回 `30000`。

1. 等日志出现 `MONITOR: armed`
2. 打开 PowerShell，粘贴以下命令回车：

```powershell
$fs = [System.IO.FileStream]::new("C:\ZZZ-OD\.log\log.txt", [System.IO.FileMode]::Append, [System.IO.FileAccess]::Write, [System.IO.FileShare]::ReadWrite)
$sw = [System.IO.StreamWriter]::new($fs, (New-Object System.Text.UTF8Encoding $false))
$sw.WriteLine("指令[ 一条龙 ] 执行失败 返回状态 失败")
$sw.Close(); $fs.Close()
```

3. 约 10 秒后日志应出现 `FAILDETECT`，一条龙被关闭并重启

---

## 7. 常见问题排查

### 脚本双击后没有反应

- 确认 AutoHotkey v1.1 已安装（`.ahk` 文件应显示绿色图标）
- 查看任务管理器，找 AutoHotkey 进程确认是否在运行

### 一条龙启动了但没有点击按钮

1. 把 `postLaunchSleep` 改为 `4000`，等界面完全加载再点
2. 用 Window Spy 重新测量按钮坐标，更新 `btnX` / `btnY`

### 被顶号没有被检测到

- 查看日志里 `OCR: heartbeat result=` 后面的值：
  - 空白 → Python OCR 依赖未安装，重新执行第 3B 节的安装命令
  - `NO_GAME` → 脚本找不到游戏进程，确认游戏正在运行
  - `NOT_FOUND` → OCR 正常运行，等待真实弹窗出现
- 确认 Windows 已安装「中文（简体）」语言包（设置 → 时间和语言 → 语言）

### 日志里没有出现 `MONITOR: armed`

脚本正在等待一条龙窗口出现，可能原因：
- 一条龙启动较慢，等待片刻
- 一条龙界面类名发生变化（一条龙更新后偶发），重启脚本重试

### 电脑重启后脚本没有自动启动

- 打开任务计划程序，检查 `OneDragon AutoRun` 任务是否存在
- 右键任务 → 「运行」，手动触发一次，确认路径配置正确
- 确认任务「常规」选项卡勾选了「使用最高权限运行」

### 任务计划程序里任务一直显示「正在运行」

正常现象，脚本会持续在后台运行。

---

## 附录：文件清单

```
C:\ZZZ-OD\ZZZ-autorun\
├── OneDragon_FINAL_Restart_90min.ahk   主监控脚本
├── OCR测试工具.bat                      双击打开 OCR 实时检测窗口
├── 查看实时日志.bat                     双击实时查看运行日志
├── 清空日志.bat                         双击删除日志文件
├── logs\
│   └── closedloop.log                  运行日志（自动生成，无需手动创建）
└── scripts\
    ├── ocrcheck.py                     OCR 被顶号检测逻辑（勿移动）
    └── ocrtest_gui.py                  OCR 测试工具源码（勿移动）
```

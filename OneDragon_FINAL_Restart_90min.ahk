#NoTrayIcon
#SingleInstance Force
SetTitleMatchMode, 2
DetectHiddenWindows, On
SendMode, Input
CoordMode, Pixel, Screen

; ===== CONFIG =====
autorunDir := A_ScriptDir
launcher := "C:\ZZZ-OD\OneDragon-Launcher.exe"
workdir  := "C:\ZZZ-OD"

logFile  := autorunDir . "\logs\closedloop.log"
kickedMarker := "C:\ZZZ-OD\.debug\temp\unattended_kicked_until.txt"

; 「启动一条龙」按钮定位：UI Automation 优先，Windows OCR 兜底
; 助手只在 GUI 启动阶段单次运行，不承担顶号检测
startClickPython := "C:\ZZZ-OD\.install\python\cpython-3.11.12-windows-x86_64-none\python.exe"
startClickScript := autorunDir . "\scripts\click_start_button.py"
startClickRetryInterval := 2000
startClickTimeout := 60000
startConfirmTimeout := 180000

; 主循环休眠间隔（毫秒），控制各项检测的响应粒度
checkInterval := 500

; 启动 Launcher 后等待 Qt 主窗口出现的超时时间（秒）
startupWaitSec := 60

; Qt 主窗口出现后，等待应用注册与一条龙列表初始化完成再点击（毫秒）
; 过早点击会让一条龙界面缓存空应用组，表现为左侧设置列表全部消失
postLaunchSleep := 15000

; 一条龙自身日志路径（用于检测运行失败）
odLogFile := "C:\ZZZ-OD\.log\log.txt"

; 每隔多久扫描一次 OneDragon 日志（毫秒）：检测运行失败并记录正常完成
; 300000 = 5 分钟 | 60000 = 1 分钟 | 30000 = 30 秒 | 10000 = 10 秒（测试用）
failCheckInterval := 30000

; 每隔多久做一次进程守卫检测（毫秒）：同时检查一条龙和游戏进程是否存活
; 600000 = 10 分钟
watchdogInterval := 600000

; 每隔多久强制重启一条龙（毫秒）：防止长时间运行卡死
; 3600000 = 1 小时
periodicRestartInterval := 3600000

; 启动一条龙后的宽限期（毫秒）：宽限期内不触发进程守卫，避免游戏还没拉起来就误判
; 180000 = 3 分钟
startupGrace := 180000
; ===================

lastFailCheck    := 0   ; 上次扫描 OneDragon 日志的时间戳
lastLogLen       := 0   ; 已处理的日志字符长度，避免重复检测旧内容
lastWatchdog     := 0   ; 上次进程守卫检测的时间戳
lastPeriodicRestart := 0   ; 上次定时强制重启的时间戳
startClickTime   := 0   ; 最近一次点击按钮的时间戳，用于计算宽限期
runCompleted     := false   ; 本轮一条龙是否已经正常完成
manualMode       := false

; --- Log helper ---
Log(msg) {
    global logFile
    FormatTime, ts,, yyyy-MM-dd HH:mm:ss
    FileAppend, %ts%  %msg%`r`n, %logFile%
}

; --- 读取一条龙日志当前字符长度，作为启动确认基线 ---
GetOneDragonLogLen() {
    global odLogFile

    if !FileExist(odLogFile)
        return 0

    FileEncoding, UTF-8
    FileRead, content, %odLogFile%
    FileEncoding, CP0
    if ErrorLevel
        return 0
    return StrLen(content)
}

; --- 返回当前游戏 PID；未运行返回 0 ---
GetGamePid() {
    Process, Exist, ZenlessZoneZero.exe
    return ErrorLevel
}

; --- 单次调用 UIA/OCR 按钮助手，返回助手结果文本 ---
RunStartButtonHelper(hwnd) {
    global startClickPython, startClickScript, workdir

    resultFile := A_Temp . "\zzz_start_button_" . A_TickCount . ".txt"
    FileDelete, %resultFile%
    RunWait, "%startClickPython%" "%startClickScript%" --hwnd %hwnd% --result-file "%resultFile%", %workdir%, Hide
    exitCode := ErrorLevel

    result := ""
    if FileExist(resultFile) {
        FileEncoding, UTF-8
        FileRead, result, %resultFile%
        FileEncoding, CP0
        FileDelete, %resultFile%
    }
    result := Trim(result)
    if (result = "")
        result := "ERROR:HELPER_EXIT_" . exitCode
    return result
}

; --- 等待并调用「启动一条龙」，不使用固定坐标 ---
FindAndInvokeStartButton(hwnd) {
    global startClickRetryInterval, startClickTimeout

    startedAt := A_TickCount
    lastResult := ""
    Loop
    {
        lastResult := RunStartButtonHelper(hwnd)
        if (SubStr(lastResult, 1, 3) = "OK:")
            return lastResult

        if (A_TickCount - startedAt >= startClickTimeout) {
            Log("START: button locator timeout, last=" . lastResult)
            return ""
        }
        Log("START: button locator retry, result=" . lastResult)
        Sleep, %startClickRetryInterval%
    }
}

; --- 按钮调用后必须看到新增一条龙日志或新游戏进程 ---
ConfirmOneDragonStarted(logBaseline, gamePidBefore) {
    global odLogFile, startConfirmTimeout

    startedAt := A_TickCount
    Loop
    {
        if FileExist(odLogFile) {
            FileEncoding, UTF-8
            FileRead, content, %odLogFile%
            FileEncoding, CP0
            if !ErrorLevel {
                currentLen := StrLen(content)
                if (currentLen < logBaseline)
                    logBaseline := 0
                newContent := SubStr(content, logBaseline + 1)
                if (InStr(newContent, "指令[ 一条龙 ] 节点")
                    || InStr(newContent, "指令[ 一条龙 ] 执行"))
                    return "onedragon_log"
            }
        }

        gamePid := GetGamePid()
        if (gamePid && gamePid != gamePidBefore)
            return "game_pid=" . gamePid

        if (A_TickCount - startedAt >= startConfirmTimeout)
            return ""
        Sleep, 1000
    }
}

; --- 顶号检测由主程序插件负责；这里只读取插件写入的冷却时间 ---
WaitForKickedCooldown() {
    global kickedMarker

    if !FileExist(kickedMarker)
        return

    FileRead, resumeAt, %kickedMarker%
    resumeAt := Trim(resumeAt)
    if !RegExMatch(resumeAt, "^\d{14}$") {
        Log("KICKED: invalid cooldown marker, removing")
        FileDelete, %kickedMarker%
        return
    }

    remainingSeconds := resumeAt
    EnvSub, remainingSeconds, %A_Now%, Seconds
    if (remainingSeconds > 0) {
        Log("KICKED: plugin requested cooldown, waiting " . remainingSeconds . " seconds")
        remainingMilliseconds := remainingSeconds * 1000
        Sleep, %remainingMilliseconds%
    }

    FileDelete, %kickedMarker%
    Log("KICKED: cooldown finished, recovery allowed")
}

; --- Force kill OneDragon immediately (B mode) ---
CloseOneDragon_Force() {
    Log("CLOSE: force killing OneDragon")

    if WinExist("ahk_class Qt680QWindowIcon") {
        WinGet, pid, PID, ahk_class Qt680QWindowIcon
        if (pid) {
            Process, Close, %pid%
            Log("CLOSE: Process.Close pid=" . pid)
        } else {
            Log("CLOSE: Qt window found but PID missing")
        }
    } else {
        Log("CLOSE: Qt window not found")
    }
}

; --- 强制关闭游戏本体（一条龙重启后会自己拉起游戏）---
CloseGame() {
    Log("FAILDETECT: closing ZenlessZoneZero.exe via taskkill")
    RunWait, %ComSpec% /c taskkill /F /IM ZenlessZoneZero.exe, , Hide
    Log("FAILDETECT: taskkill done (exit=" . ErrorLevel . ")")
}

; --- 进程守卫：检查一条龙和游戏是否都在运行 ---
; 返回 true 表示需要重启，false 表示一切正常
WatchdogCheck() {
    global startClickTime, startupGrace, runCompleted

    ; 宽限期内不检测，等游戏有时间被一条龙拉起来
    if (startClickTime > 0 && A_TickCount - startClickTime < startupGrace)
        return false

    odRunning := WinExist("ahk_class Qt680QWindowIcon")

    Process, Exist, ZenlessZoneZero.exe
    gameRunning := ErrorLevel   ; 非 0 = 进程存在

    if (!odRunning && !gameRunning) {
        Log("WATCHDOG: both OneDragon and game are gone, restarting")
        return true
    }
    if (!odRunning) {
        Log("WATCHDOG: OneDragon is gone (game still running), restarting both")
        RunWait, %ComSpec% /c taskkill /F /IM ZenlessZoneZero.exe, , Hide
        return true
    }
    if (!gameRunning) {
        if (runCompleted) {
            Log("WATCHDOG: game exited after normal completion, waiting for periodic restart")
            return false
        }
        Log("WATCHDOG: game is gone but OneDragon is running, restarting both")
        CloseOneDragon_Force()
        return true
    }

    return false
}

; --- 扫描本轮新增日志：失败时返回 true，正常完成时记录状态 ---
CheckOneDragonFailed() {
    global odLogFile, lastLogLen, runCompleted

    if !FileExist(odLogFile)
        return false

    FileEncoding, UTF-8
    FileRead, content, %odLogFile%
    FileEncoding, CP0   ; 恢复系统默认编码，避免影响其他文件操作
    if ErrorLevel
        return false

    currentLen := StrLen(content)
    if (currentLen <= lastLogLen) {
        lastLogLen := currentLen
        return false
    }

    newContent := SubStr(content, lastLogLen + 1)
    lastLogLen := currentLen

    ; 只要日志里出现这条就触发，格式形如：
    ; [00:38:07.281] [operation.py 677] [ERROR]: 指令[ 一条龙 ] 执行失败 返回状态 失败
    if InStr(newContent, "指令[ 一条龙 ] 执行失败") {
        Log("FAILDETECT: failure pattern matched")
        return true
    }

    if (!runCompleted
        && InStr(newContent, "指令[ 一条龙 ] 执行成功 返回状态 全部结束")) {
        runCompleted := true
        Log("MONITOR: OneDragon completed normally, waiting for periodic restart")
    }

    return false
}

; --- 启动 GUI，定位按钮，并确认一条龙真正开始 ---
StartAndClick() {
    global launcher, workdir, startupWaitSec, postLaunchSleep
    global lastLogLen, runCompleted

    Log("START: running launcher")
    Run, %launcher%, %workdir%

    WinWait, ahk_class Qt680QWindowIcon, , %startupWaitSec%
    if ErrorLevel {
        Log("START: timeout waiting Qt main window")
        return false
    }

    WinActivate, ahk_class Qt680QWindowIcon
    WinWaitActive, ahk_class Qt680QWindowIcon, , 10
    if ErrorLevel {
        Log("START: timeout activating Qt main window")
        return false
    }
    Sleep, %postLaunchSleep%

    WinGet, hwnd, ID, ahk_class Qt680QWindowIcon
    if (!hwnd) {
        Log("START: hwnd missing after WinWait")
        return false
    }

    logBaseline := GetOneDragonLogLen()
    lastLogLen := logBaseline
    runCompleted := false
    gamePidBefore := GetGamePid()
    locatorResult := FindAndInvokeStartButton(hwnd)
    if (locatorResult = "")
        return false
    Log("START: button invoked, result=" . locatorResult)

    confirmResult := ConfirmOneDragonStarted(logBaseline, gamePidBefore)
    if (confirmResult = "") {
        Log("START: invocation was not confirmed before timeout")
        return false
    }
    Log("START: confirmed via " . confirmResult)

    global startClickTime
    startClickTime := A_TickCount
    return true
}

; --- Basic checks ---
if !FileExist(launcher) {
    Log("ERROR: launcher not found: " . launcher)
    ExitApp
}
if !FileExist(startClickPython) {
    Log("ERROR: start button Python not found: " . startClickPython)
    ExitApp
}
if !FileExist(startClickScript) {
    Log("ERROR: start button helper not found: " . startClickScript)
    ExitApp
}
; 部署自检：完成整份脚本的加载和语法解析后退出，不启动一条龙
if (A_Args.Length() > 0 && A_Args[1] = "--check")
    ExitApp
; 初始化日志位置，跳过脚本启动前已存在的旧日志内容，避免把历史失败记录误判为新事件
if FileExist(odLogFile) {
    FileEncoding, UTF-8
    FileRead, _initContent, %odLogFile%
    FileEncoding, CP0
    lastLogLen := StrLen(_initContent)
}

; 禁止系统进入睡眠（ES_CONTINUOUS | ES_SYSTEM_REQUIRED），防止电脑自动睡眠导致监控中断
DllCall("SetThreadExecutionState", "UInt", 0x80000001)

Log("BOOT: closed-loop started. kicked_detection=plugin fail_check=" . failCheckInterval . "ms")

; ===== MAIN LOOP =====
Loop
{
    while (manualMode)
        Sleep, 3000

    WaitForKickedCooldown()

    ok := StartAndClick()
    if (!ok) {
        Log("START: failed, resetting GUI and game before retry")
        CloseGame()
        CloseOneDragon_Force()
        Sleep, 60000
        Continue
    }

    Log("MONITOR: armed")
    lastPeriodicRestart := A_TickCount   ; 每次启动后重置 1 小时计时

    ; OneDragon 运行期间只负责失败恢复、进程守卫与定时重启；顶号 OCR 由主程序插件负责
    Loop
    {
        nowTick := A_TickCount

        if (manualMode) {
            Sleep, 3000
            Continue
        }

        ; ---- 每 30 秒扫描 OneDragon 日志，检测运行失败或正常完成 ----
        if (nowTick - lastFailCheck >= failCheckInterval) {
            lastFailCheck := nowTick
            if (CheckOneDragonFailed()) {
                Log("FAILDETECT: failure pattern found in OneDragon log")
                CloseGame()
                CloseOneDragon_Force()
                Log("FAILDETECT: restarting OneDragon")
                Break
            }
        }

        ; ---- 每 10 分钟进程守卫：检查两个进程是否都还活着 ----
        if (nowTick - lastWatchdog >= watchdogInterval) {
            lastWatchdog := nowTick
            if (WatchdogCheck()) {
                Log("WATCHDOG: restarting OneDragon")
                Break
            }
        }

        ; ---- 每 1 小时强制重启一条龙 ----
        if (lastPeriodicRestart > 0 && nowTick - lastPeriodicRestart >= periodicRestartInterval) {
            lastPeriodicRestart := nowTick
            Log("PERIODIC: 1h elapsed, force restarting OneDragon")
            CloseGame()
            CloseOneDragon_Force()
            Break
        }

        Sleep, %checkInterval%
    }
}

; --- 手动模式热键 ---
~F10::
    manualMode := true
    Log("MANUAL: monitoring paused")
    SoundBeep, 500, 120
    SoundBeep, 500, 120
    Gui, ManualBanner:New, +AlwaysOnTop -Caption +ToolWindow
    Gui, ManualBanner:Color, CC2200
    Gui, ManualBanner:Font, s16 bold cWhite, Arial
    Gui, ManualBanner:Add, Text, x12 y8, 监控已暂停
    Gui, ManualBanner:Show, NoActivate x10 y10, ManualBanner
    SetTimer, HideBanner, -2000
return

~F9::
    manualMode := false
    ; 跳过暂停期间写入的日志，避免把一条龙手动停止产生的"执行失败"误判为新故障
    if FileExist(odLogFile) {
        FileEncoding, UTF-8
        FileRead, _resumeSnap, %odLogFile%
        FileEncoding, CP0
        lastLogLen := StrLen(_resumeSnap)
    }
    lastFailCheck := A_TickCount   ; 重置失败检测计时，避免恢复时立刻触发
    Log("MANUAL: monitoring resumed")
    SoundBeep, 900, 150
    Gui, ManualBanner:New, +AlwaysOnTop -Caption +ToolWindow
    Gui, ManualBanner:Color, 007700
    Gui, ManualBanner:Font, s16 bold cWhite, Arial
    Gui, ManualBanner:Add, Text, x12 y8, 监控已恢复
    Gui, ManualBanner:Show, NoActivate x10 y10, ManualBanner
    SetTimer, HideBanner, -2000
return

HideBanner:
    Gui, ManualBanner:Destroy
return

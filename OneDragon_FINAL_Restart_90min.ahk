#NoTrayIcon
#SingleInstance Force
SetTitleMatchMode, 2
DetectHiddenWindows, On
SendMode, Input
CoordMode, Pixel, Screen

; ===== CONFIG =====
launcher := "C:\ZZZ-OD\OneDragon-Launcher.exe"
workdir  := "C:\ZZZ-OD"

logFile  := "C:\ZZZ-OD\closedloop.log"

; 「启动一条龙」按钮的 Client 坐标，用 AutoHotkey Window Spy 测量
; 注意：必须用 Window Spy 里的 Client 坐标，不是 Screen 坐标
; 如果按钮点不到，重新用 Window Spy 测并更新这两个值
btnX := 1470
btnY := 1055

; 主循环休眠间隔（毫秒），控制各项检测的响应粒度
checkInterval := 500

; OCR 被顶号检测：识别关键词，每隔多久调用一次（毫秒）
; 500 = 0.5 秒
ocrPython   := "C:\ZZZ-OD\.install\python\cpython-3.11.12-windows-x86_64-none\python.exe"
ocrScript   := "C:\ZZZ-OD\ocrcheck.py"
ocrInterval := 500

; 检测到弹窗后，等待多久再重启（毫秒）
; 7200000 = 2 小时 | 3600000 = 1 小时 | 测试用可改成 60000（1 分钟）
restartDelay  := 7200000

; 启动 Launcher 后等待 Qt 主窗口出现的超时时间（秒）
startupWaitSec := 60

; Qt 主窗口出现后，等待多久再点击按钮（毫秒），太短可能界面还没完全加载
postLaunchSleep := 1500

; 一条龙自身日志路径（用于检测运行失败）
odLogFile := "C:\ZZZ-OD\.log\log.txt"

; 每隔多久扫描一次 OneDragon 日志检测运行失败（毫秒）
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

; Track cooldown end time using tick count
lastOcrCheck     := 0   ; 上次 OCR 检测被顶号弹窗的时间戳
lastOcrLog       := 0   ; 上次记录 OCR 心跳日志的时间戳
prevOcrResult    := ""  ; 上次 OCR 结果，用于检测状态变化
lastFailCheck    := 0   ; 上次扫描 OneDragon 日志的时间戳
lastLogLen       := 0   ; 已处理的日志字符长度，避免重复检测旧内容
lastWatchdog     := 0   ; 上次进程守卫检测的时间戳
lastPeriodicRestart := 0   ; 上次定时强制重启的时间戳
startClickTime   := 0   ; 最近一次点击按钮的时间戳，用于计算宽限期
manualMode       := false

; --- Log helper ---
Log(msg) {
    global logFile
    FormatTime, ts,, yyyy-MM-dd HH:mm:ss
    FileAppend, %ts%  %msg%`r`n, %logFile%
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
    global startClickTime, startupGrace

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
        Log("WATCHDOG: game is gone but OneDragon is running, restarting both")
        CloseOneDragon_Force()
        return true
    }

    return false
}

; --- 检测 OneDragon 日志里是否出现失败四连（只检测上次扫描之后的新内容）---
CheckOneDragonFailed() {
    global odLogFile, lastLogLen

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

    return false
}

; --- Start OneDragon and click the Start button ---
StartAndClick() {
    global launcher, workdir, startupWaitSec, postLaunchSleep, btnX, btnY

    Log("START: running launcher")
    Run, %launcher%, %workdir%

    WinWait, ahk_class Qt680QWindowIcon, , %startupWaitSec%
    if ErrorLevel {
        Log("START: timeout waiting Qt main window")
        return false
    }

    WinActivate, ahk_class Qt680QWindowIcon
    WinWaitActive, ahk_class Qt680QWindowIcon, , 10
    Sleep, %postLaunchSleep%

    WinGet, hwnd, ID, ahk_class Qt680QWindowIcon
    if (!hwnd) {
        Log("START: hwnd missing after WinWait")
        return false
    }

    ; Client -> Screen coords then click
    VarSetCapacity(pt, 8, 0)
    NumPut(btnX, pt, 0, "Int")
    NumPut(btnY, pt, 4, "Int")
    DllCall("ClientToScreen", "Ptr", hwnd, "Ptr", &pt)
    sx := NumGet(pt, 0, "Int")
    sy := NumGet(pt, 4, "Int")

    DllCall("SetCursorPos", "Int", sx, "Int", sy)
    Sleep, 80
    Click

    Log("START: clicked start button at screen x=" . sx . " y=" . sy)
    global startClickTime
    startClickTime := A_TickCount
    return true
}

; --- Basic checks ---
if !FileExist(launcher) {
    Log("ERROR: launcher not found: " . launcher)
    ExitApp
}
; 初始化日志位置，跳过脚本启动前已存在的旧日志内容，避免把历史失败记录误判为新事件
if FileExist(odLogFile) {
    FileEncoding, UTF-8
    FileRead, _initContent, %odLogFile%
    FileEncoding, CP0
    lastLogLen := StrLen(_initContent)
}

; 禁止系统进入睡眠（ES_CONTINUOUS | ES_SYSTEM_REQUIRED），防止电脑自动睡眠导致监控中断
DllCall("SetThreadExecutionState", "UInt", 0x80000001)

Log("BOOT: closed-loop started. ocr_interval=" . ocrInterval . "ms fail_check=" . failCheckInterval . "ms")

; ===== MAIN LOOP =====
Loop
{
    while (manualMode)
        Sleep, 3000

    ok := StartAndClick()
    if (!ok) {
        Sleep, 60000
        Continue
    }

    Log("MONITOR: armed")
    lastPeriodicRestart := A_TickCount   ; 每次启动后重置 1 小时计时

    ; While OneDragon is running, either monitor popup (normal) or ignore during cooldown
    Loop
    {
        nowTick := A_TickCount

        ; ---- 每 0.5 秒 OCR 检测被顶号弹窗（manualMode 期间也继续运行）----
        if (nowTick - lastOcrCheck >= ocrInterval) {
            lastOcrCheck := nowTick
            ocrResultFile := A_Temp . "\zzz_ocr_result.txt"
            RunWait, %ocrPython% "%ocrScript%" "%ocrResultFile%", , Hide
            FileRead, ocrResult, %ocrResultFile%
            FileDelete, %ocrResultFile%
            ocrResult := Trim(ocrResult)

            ; 每 5 分钟心跳 + 状态变化时立即记录
            if (nowTick - lastOcrLog >= 300000) {
                lastOcrLog := nowTick
                Log("OCR: heartbeat result=" . ocrResult)
            }
            if (ocrResult != prevOcrResult) {
                prevOcrResult := ocrResult
                Log("OCR: state changed -> " . ocrResult)
            }

            if (ocrResult = "FOUND") {
                SoundBeep, 900, 200
                Log("DETECTED: popup text found by OCR")
                CloseGame()
                CloseOneDragon_Force()
                Log("SLEEP: waiting before restart")
                Sleep, %restartDelay%
                Log("RESTART: waking up")
                Break
            }
        }

        if (manualMode) {
            Sleep, 3000
            Continue
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

        ; ---- 每 30 秒扫描 OneDragon 日志，检测运行失败 ----
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
    lastOcrCheck  := A_TickCount   ; 重置 OCR 计时
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

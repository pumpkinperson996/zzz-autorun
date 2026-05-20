; ============================================================
; ListPythonWindows.ahk - OneDragon Qt Window Class Inspector
; ============================================================
;
; Purpose:
;   Discovers the Qt window class name used by OneDragon.
;   The AHK monitoring script relies on "ahk_class Qt680QWindowIcon"
;   to detect and interact with the OneDragon window. This class
;   name contains the Qt version number (e.g. Qt 6.8.0 = Qt680).
;   If OneDragon upgrades to a newer Qt version, the class name
;   changes (e.g. Qt690QWindowIcon for Qt 6.9.0), breaking the
;   monitoring script's ability to find the window.
;
; When to run:
;   Run this script when OneDragon_FINAL_Restart_90min.ahk stops
;   working after a OneDragon update (i.e. it never reaches
;   "MONITOR: armed" in the log). The output will show the new
;   class name to put in the monitoring script.
;
; How to use:
;   1. Close OneDragon if it is already running
;   2. Double-click this script - it will launch OneDragon automatically
;   3. Wait for the result file to open (a few seconds)
;   4. Look for the line: Class=[Qt???QWindowIcon]
;   5. Copy that class name into OneDragon_FINAL_Restart_90min.ahk,
;      replacing every occurrence of Qt680QWindowIcon
;
; Output file:
;   logs\python_windows.txt  (created next to this script)
; ============================================================

#NoTrayIcon
DetectHiddenWindows, On
SetTitleMatchMode, 2

; --- CONFIG: adjust this path if OneDragon is installed elsewhere ---
launcher := "C:\ZZZ-OD\OneDragon-Launcher.exe"
outFile  := A_ScriptDir . "\logs\python_windows.txt"
; --------------------------------------------------------------------

if !FileExist(launcher) {
    MsgBox, 48, Error, Launcher not found:`n%launcher%`n`nUpdate the launcher path in this script.
    ExitApp
}

Run, %launcher%, % SubStr(launcher, 1, InStr(launcher, "\", 0, 0) - 1)
Sleep, 3000

WinGet, list, List, ahk_exe python.exe

out := "python.exe window count = " . list . "`r`n`r`n"
Loop, %list%
{
    id := list%A_Index%
    WinGetTitle, t, ahk_id %id%
    WinGetClass, c, ahk_id %id%
    WinGet, style, Style, ahk_id %id%
    out .= A_Index . ". hwnd=" . id . "`r`n"
        .  "  Title=[" . t . "]`r`n"
        .  "  Class=[" . c . "]`r`n"
        .  "  Style=" . style . "`r`n`r`n"
}

FileDelete, %outFile%
FileAppend, %out%, %outFile%
Run, notepad.exe "%outFile%"
ExitApp

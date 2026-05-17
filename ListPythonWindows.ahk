#NoTrayIcon
DetectHiddenWindows, On
SetTitleMatchMode, 2

Run, C:\ZZZ-OD\OneDragon-Launcher.exe, C:\ZZZ-OD
Sleep, 3000

WinGet, list, List, ahk_exe python.exe

out := "python.exe window count = " list "`n`n"
Loop, %list%
{
    id := list%A_Index%
    WinGetTitle, t, ahk_id %id%
    WinGetClass, c, ahk_id %id%
    WinGet, style, Style, ahk_id %id%
    out .= A_Index ". hwnd=" id "`n  Title=[" t "]`n  Class=[" c "]`n  Style=" style "`n`n"
}

; 写到文件，避免 MsgBox 太长
FileDelete, C:\ZZZ-OD\python_windows.txt
FileAppend, %out%, C:\ZZZ-OD\python_windows.txt

MsgBox, 已输出到 C:\ZZZ-OD\python_windows.txt
ExitApp

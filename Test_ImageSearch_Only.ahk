#NoTrayIcon
#SingleInstance Force
CoordMode, Pixel, Screen

popupImg := "C:\ZZZ-OD\popup_banner.png"
tol := 90
log := "C:\ZZZ-OD\img_test.log"

FileAppend, `r`n`r`nSTART %A_Now% tol=%tol%`r`n, %log%

Loop
{
    ImageSearch, fx, fy, 0, 0, A_ScreenWidth, A_ScreenHeight, *%tol% %popupImg%
    if (ErrorLevel = 0) {
        SoundBeep, 900, 200
        FileAppend, FOUND %A_Now% x=%fx% y=%fy%`r`n, %log%
        Sleep, 1000
    } else {
        Sleep, 500
    }
}

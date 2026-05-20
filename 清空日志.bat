@echo off
if exist "C:\ZZZ-OD\ZZZ-autorun\logs\closedloop.log" del /f "C:\ZZZ-OD\ZZZ-autorun\logs\closedloop.log"
echo Log deleted.
ping -n 3 127.0.0.1 >nul

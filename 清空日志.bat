@echo off
set "logFile=%~dp0logs\closedloop.log"
if exist "%logFile%" del /f "%logFile%"
echo Log deleted.
ping -n 3 127.0.0.1 >nul

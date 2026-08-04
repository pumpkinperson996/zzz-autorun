@echo off
powershell -NoExit -Command "Get-Content -LiteralPath '%~dp0logs\closedloop.log' -Wait -Tail 40"

@echo off
powershell -NoExit -Command "Get-Content 'C:\ZZZ-OD\closedloop.log' -Wait -Tail 40"

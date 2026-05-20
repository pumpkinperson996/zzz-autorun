@echo off
powershell -NoExit -Command "Get-Content 'C:\ZZZ-OD\ZZZ-autorun\logs\closedloop.log' -Wait -Tail 40"

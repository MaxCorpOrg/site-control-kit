@echo off
setlocal
call "%~dp0scripts\start_hub.cmd" %*
exit /b %ERRORLEVEL%

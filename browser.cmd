@echo off
setlocal
call "%~dp0scripts\browser.cmd" %*
exit /b %ERRORLEVEL%

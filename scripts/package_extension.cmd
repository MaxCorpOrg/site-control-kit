@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0package_extension.ps1"
exit /b %ERRORLEVEL%

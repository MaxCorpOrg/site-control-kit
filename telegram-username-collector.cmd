@echo off
setlocal EnableExtensions EnableDelayedExpansion
pushd "%~dp0"

where python >nul 2>nul
if %ERRORLEVEL%==0 (
  python -m scripts.telegram_username_collector_launcher %*
  set "CODE=!ERRORLEVEL!"
  popd
  exit /b !CODE!
)

where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3 -m scripts.telegram_username_collector_launcher %*
  set "CODE=!ERRORLEVEL!"
  popd
  exit /b !CODE!
)

popd
echo Python launcher not found. Install Python or add python.exe to PATH. 1>&2
exit /b 1

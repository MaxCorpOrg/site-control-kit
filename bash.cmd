@echo off
setlocal EnableExtensions EnableDelayedExpansion

if exist "C:\Program Files\Git\bin\bash.exe" (
  call "C:\Program Files\Git\bin\bash.exe" %*
  set "CODE=!ERRORLEVEL!"
  exit /b !CODE!
)

if exist "C:\Program Files\Git\usr\bin\bash.exe" (
  call "C:\Program Files\Git\usr\bin\bash.exe" %*
  set "CODE=!ERRORLEVEL!"
  exit /b !CODE!
)

echo Git Bash not found. Install Git for Windows or add bash.exe to PATH. 1>&2
exit /b 1

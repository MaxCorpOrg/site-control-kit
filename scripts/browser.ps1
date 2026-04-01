$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent $scriptDir

if (Get-Command python -ErrorAction SilentlyContinue) {
  Push-Location $rootDir
  try {
    & python -m webcontrol browser @args
    exit $LASTEXITCODE
  } finally {
    Pop-Location
  }
}

if (Get-Command py -ErrorAction SilentlyContinue) {
  Push-Location $rootDir
  try {
    & py -3 -m webcontrol browser @args
    exit $LASTEXITCODE
  } finally {
    Pop-Location
  }
}

throw "Python launcher not found. Install Python or add python.exe to PATH."

$ErrorActionPreference = "Stop"
& "$PSScriptRoot\scripts\start_hub.ps1" @args
exit $LASTEXITCODE

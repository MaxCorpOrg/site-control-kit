$ErrorActionPreference = "Stop"

function Resolve-PythonCommand {
  if (Get-Command python -ErrorAction SilentlyContinue) {
    return @("python")
  }
  if (Get-Command py -ErrorAction SilentlyContinue) {
    return @("py", "-3")
  }
  throw "Python launcher not found. Install Python or add python.exe to PATH."
}

function Invoke-PythonCommand {
  param(
    [string[]]$PythonCommand,
    [string[]]$Arguments
  )

  if ($PythonCommand.Length -le 1) {
    return & $PythonCommand[0] @Arguments
  }

  $prefix = @()
  if ($PythonCommand.Length -gt 1) {
    $prefix = $PythonCommand[1..($PythonCommand.Length - 1)]
  }
  return & $PythonCommand[0] @prefix @Arguments
}

function Get-EnvValue {
  param([string]$Name)
  $value = [System.Environment]::GetEnvironmentVariable($Name)
  if ([string]::IsNullOrWhiteSpace($value)) {
    return $null
  }
  return $value.Trim()
}

function Get-EnvInt {
  param(
    [string]$Name,
    [int]$DefaultValue
  )

  $raw = Get-EnvValue -Name $Name
  if ($null -eq $raw) {
    return $DefaultValue
  }

  $parsed = 0
  if ([int]::TryParse($raw, [ref]$parsed)) {
    return $parsed
  }

  return $DefaultValue
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent $scriptDir
$pythonCmd = Resolve-PythonCommand
$runtimeEnv = Invoke-PythonCommand -PythonCommand $pythonCmd -Arguments @("-m", "webcontrol", "runtime-env", "--format", "powershell")
if (-not [string]::IsNullOrWhiteSpace($runtimeEnv)) {
  Invoke-Expression $runtimeEnv
}
$token = Get-EnvValue -Name "SITECTL_TOKEN"
if ($null -eq $token) {
  throw "SITECTL_TOKEN is not configured. Create .env from .env.example or use the generated local runtime config."
}

$hostName = Get-EnvValue -Name "SITECTL_HOST"
if ($null -eq $hostName) {
  $hostName = "127.0.0.1"
}

$port = Get-EnvInt -Name "SITECTL_PORT" -DefaultValue 8765

$stateFile = Get-EnvValue -Name "SITECTL_STATE_FILE"
if ($null -eq $stateFile) {
  $stateFile = Join-Path $rootDir "var\site-control-kit\state\state.json"
}

$stateDir = Split-Path -Parent $stateFile
if ($stateDir) {
  New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
}

Set-Location $rootDir
Invoke-PythonCommand -PythonCommand $pythonCmd -Arguments @("-m", "webcontrol", "serve", "--host", $hostName, "--port", "$port", "--token", $token, "--state-file", $stateFile)
exit $LASTEXITCODE

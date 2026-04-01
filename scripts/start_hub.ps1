$ErrorActionPreference = "Stop"

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
$token = Get-EnvValue -Name "SITECTL_TOKEN"
if ($null -eq $token) {
  $token = "local-bridge-quickstart-2026"
  Write-Host "SITECTL_TOKEN is not set. Starting in quick local mode." -ForegroundColor Yellow
  Write-Host "Default token: $token" -ForegroundColor Yellow
  Write-Host "Set your own token for anything outside a private local machine:" -ForegroundColor Yellow
  Write-Host '$env:SITECTL_TOKEN = "your-strong-token"' -ForegroundColor Yellow
}

$hostName = Get-EnvValue -Name "SITECTL_HOST"
if ($null -eq $hostName) {
  $hostName = "127.0.0.1"
}

$port = Get-EnvInt -Name "SITECTL_PORT" -DefaultValue 8765

$stateFile = Get-EnvValue -Name "SITECTL_STATE_FILE"
if ($null -eq $stateFile) {
  $stateFile = Join-Path $HOME ".site-control-kit\state.json"
}

$stateDir = Split-Path -Parent $stateFile
if ($stateDir) {
  New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
}

Set-Location $rootDir
& python -m webcontrol serve --host $hostName --port $port --token $token --state-file $stateFile
exit $LASTEXITCODE

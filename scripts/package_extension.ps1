$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent $scriptDir
$distDir = Join-Path $rootDir "dist"
$zipPath = Join-Path $distDir "site-control-bridge-extension.zip"
$extensionDir = Join-Path $rootDir "extension"

New-Item -ItemType Directory -Force -Path $distDir | Out-Null
if (Test-Path $zipPath) {
  Remove-Item -Force $zipPath
}

Compress-Archive -Path (Join-Path $extensionDir "*") -DestinationPath $zipPath -CompressionLevel Optimal
Write-Host "Created: $zipPath"

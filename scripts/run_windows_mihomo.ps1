#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $Root "bin\mihomo-windows-amd64.exe"
$cfg = Join-Path $Root "log\mihomo-windows.yaml"
if (-not (Test-Path $exe)) { throw "missing $exe" }
if (-not (Test-Path $cfg)) { throw "missing $cfg" }
Write-Host "mihomo config=$cfg"
& $exe -d (Split-Path $cfg) -f $cfg

#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { throw "需要 Python 3.10+（python 不在 PATH）" }

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    python -m venv .venv
}
$venvPy = Join-Path $Root ".venv\Scripts\python.exe"
& $venvPy -m pip install --upgrade pip
& $venvPy -m pip install -r requirements.txt
& $venvPy -m camoufox fetch
if (-not (Test-Path "config.json")) {
    Copy-Item "config.example.json" "config.json"
    Write-Host "已创建 config.json，请填写邮箱和代理。"
}
Write-Host "Windows 环境就绪。接下来可用 scripts\run_windows_batch.ps1 1 1"

@echo off
setlocal EnableExtensions
set "HERE=%~dp0"
set "GUARD=%HERE%playwright-epipe-guard.js"
set "NODE=%GROK_PLAYWRIGHT_NODE%"
if not defined NODE (
  where node.exe >nul 2>&1
  if not errorlevel 1 (
    for /f "delims=" %%I in ('where node.exe') do (
      set "NODE=%%I"
      goto :run
    )
  )
)
if not defined NODE (
  echo playwright-node.cmd: no node.exe found >&2
  exit /b 127
)
:run
if exist "%GUARD%" (
  "%NODE%" --require "%GUARD%" %*
) else (
  "%NODE%" %*
)

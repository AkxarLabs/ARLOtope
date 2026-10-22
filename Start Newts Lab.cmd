@echo off
rem Double-click to start ARLOtope (the dashboard) and open it in your browser.
cd /d "%~dp0"
where uv >nul 2>nul
if errorlevel 1 (
  echo ARLOtope needs uv ^(a small Python tool runner^): https://docs.astral.sh/uv/getting-started/installation/
  echo Install it, then double-click this file again.
  pause
  exit /b 1
)
uv run --with pyyaml python newts.py %*
if errorlevel 1 pause

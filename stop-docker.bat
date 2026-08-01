@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Zhihu Summary Workbench
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop-docker.ps1"
if errorlevel 1 (
  echo.
  echo Shutdown failed. Please keep the error message shown above.
  pause
)

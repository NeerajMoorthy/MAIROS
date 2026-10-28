@echo off
rem Start the MAIROS demo now: the API on this PC and the tunnel behind
rem https://mairos.vercel.app. After "publish_demo.py --install-autostart" a
rem scheduled task does this every minute on its own; this file is for
rem when you do not want to wait.
title MAIROS demo
cd /d "%~dp0.."
".venv\Scripts\python.exe" "scripts\publish_demo.py"
echo.
echo You can close this window; MAIROS keeps running in the background.
timeout /t 30

@echo off
rem Start the MAIROS demo after a restart: the API on this PC and the ngrok
rem tunnel behind https://mairos.vercel.app. Double-click this file, or put a
rem shortcut to it in the Startup folder to run it at sign-in.
title MAIROS demo
cd /d "%~dp0.."
".venv\Scripts\python.exe" "scripts\publish_demo.py"
echo.
echo You can close this window; MAIROS keeps running in the background.
timeout /t 30

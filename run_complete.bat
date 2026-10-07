@echo off
cd /d %~dp0
set KAREEM_MAX_STEPS=80
if "%KAREEM_PORT%"=="" set KAREEM_PORT=5000
.\.venv\Scripts\python.exe app_complete.py

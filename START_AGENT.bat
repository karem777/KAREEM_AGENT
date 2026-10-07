@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  echo Starting KAREEM_AGENT with the existing virtual environment...
  ".venv\Scripts\python.exe" app.py
) else (
  echo No local .venv was found. Trying system Python...
  python app.py
)
pause

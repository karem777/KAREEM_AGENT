@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  .venv\Scripts\python.exe -m pytest -q tests
) else if exist "%USERPROFILE%\KAREEM_AGENT\.venv\Scripts\python.exe" (
  "%USERPROFILE%\KAREEM_AGENT\.venv\Scripts\python.exe" -m pytest -q "%USERPROFILE%\KAREEM_AGENT\tests"
) else (
  python -m pytest -q tests
)
if errorlevel 1 (
  echo.
  echo SELF TEST FAILED.
) else (
  echo.
  echo SELF TEST PASSED.
)
pause

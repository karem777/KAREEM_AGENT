@echo off
cd /d "%~dp0"
python -m pytest -q tests
if errorlevel 1 (
  echo V6 self-test FAILED.
  pause
  exit /b 1
)
python -m compileall -q brain core tools tests
if errorlevel 1 (
  echo Python compile check FAILED.
  pause
  exit /b 1
)
echo V6 cognitive self-test PASSED.
pause

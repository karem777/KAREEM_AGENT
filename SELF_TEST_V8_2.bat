@echo off
setlocal EnableExtensions
set "PACKAGE=%~dp0"
set "TARGET=%USERPROFILE%\KAREEM_AGENT"

if not exist "%TARGET%" (
  echo [V8.2] Installed project not found at %TARGET%.
  pause
  exit /b 1
)

copy /Y "%PACKAGE%ENSURE_V8_1_ENV.bat" "%TARGET%\ENSURE_V8_1_ENV.bat" >nul
call "%TARGET%\ENSURE_V8_1_ENV.bat"
if errorlevel 1 (
  echo [V8.2] Environment preparation failed.
  pause
  exit /b 1
)

set "PYEXE=%TARGET%\.venv\Scripts\python.exe"
if not exist "%PYEXE%" (
  echo [V8.2] ERROR: .venv python executable not found.
  pause
  exit /b 1
)

echo [V8.2] Running regression tests from the installed project...
"%PYEXE%" -m pytest -q "%TARGET%\tests"
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
  echo [V8.2] SELF TEST PASSED.
) else (
  echo [V8.2] SELF TEST FAILED. Exit code: %RC%
)
pause
exit /b %RC%

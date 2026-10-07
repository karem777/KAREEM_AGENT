@echo off
setlocal EnableExtensions
set "PACKAGE=%~dp0"
set "TARGET=%USERPROFILE%\KAREEM_AGENT"

if not exist "%TARGET%" (
  echo [V8.1] Installed project not found at %TARGET%.
  pause
  exit /b 1
)

rem Self-test is intentionally self-healing: it never assumes a helper file from
rem an older V8 install is present.
copy /Y "%PACKAGE%ENSURE_V8_1_ENV.bat" "%TARGET%\ENSURE_V8_1_ENV.bat" >nul
call "%TARGET%\ENSURE_V8_1_ENV.bat"
if errorlevel 1 (
  echo [V8.1] Environment preparation failed.
  pause
  exit /b 1
)

set "PYEXE=%TARGET%\.venv\Scripts\python.exe"
if not exist "%PYEXE%" (
  echo [V8.1] ERROR: .venv python executable not found after environment setup.
  pause
  exit /b 1
)

echo [V8.1] Running regression tests from the installed project...
"%PYEXE%" -m pytest -q "%TARGET%\tests"
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
  echo [V8.1] SELF TEST PASSED.
) else (
  echo [V8.1] SELF TEST FAILED. Exit code: %RC%
)
pause
exit /b %RC%

@echo off
setlocal EnableExtensions
cd /d "%USERPROFILE%\KAREEM_AGENT"
set "ROOT=%CD%"
set "PYEXE=%ROOT%\.venv\Scripts\python.exe"

if not exist "%ROOT%" (
  echo [V8.1] ERROR: Project folder not found: %ROOT%
  exit /b 1
)

if not exist "%PYEXE%" (
  echo [V8.1] Local .venv not found. Creating it...
  set "BASEPY="
  if exist "%LocalAppData%\Programs\Python\Python314\python.exe" set "BASEPY=%LocalAppData%\Programs\Python\Python314\python.exe"
  if not defined BASEPY if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set "BASEPY=%LocalAppData%\Programs\Python\Python313\python.exe"
  if not defined BASEPY if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "BASEPY=%LocalAppData%\Programs\Python\Python312\python.exe"
  if not defined BASEPY for /f "delims=" %%P in ('where python 2^>nul') do if not defined BASEPY set "BASEPY=%%P"
  if not defined BASEPY (
    echo [V8.1] ERROR: Python was not found.
    exit /b 1
  )
  "%BASEPY%" -m venv "%ROOT%\.venv"
  if errorlevel 1 (
    echo [V8.1] ERROR: Failed to create .venv.
    exit /b 1
  )
)

if not exist "%PYEXE%" (
  echo [V8.1] ERROR: .venv Python is still missing.
  exit /b 1
)

echo [V8.1] Upgrading pip tooling...
"%PYEXE%" -m pip install --disable-pip-version-check --no-input -q --upgrade pip setuptools wheel

if exist "%ROOT%\requirements.txt" (
  echo [V8.1] Ensuring runtime packages...
  "%PYEXE%" -m pip install --disable-pip-version-check --no-input -q -r "%ROOT%\requirements.txt"
  if errorlevel 1 echo [V8.1] WARNING: runtime package install had a nonzero exit code.
)

echo [V8.1] Ensuring pytest...
"%PYEXE%" -m pip install --disable-pip-version-check --no-input -q pytest
if errorlevel 1 (
  echo [V8.1] ERROR: Could not install pytest into .venv.
  exit /b 1
)

"%PYEXE%" -c "import pytest; print('pytest', pytest.__version__)" || exit /b 1

echo [V8.1] Environment ready.
exit /b 0

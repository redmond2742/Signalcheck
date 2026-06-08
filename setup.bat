@echo off
REM ============================================================
REM  4-Way Flash Checker - one-time setup (Windows)
REM  Double-click this once. It creates a private Python
REM  environment (.venv) and installs the required packages.
REM  After it finishes, use run_app.bat to start the app.
REM ============================================================

cd /d "%~dp0"

echo ============================================================
echo   4-Way Flash Checker - one-time setup
echo ============================================================
echo.

REM --- Find a Python launcher (prefer "python", fall back to "py") ---
set "PYCMD="
python --version >nul 2>&1 && set "PYCMD=python"
if not defined PYCMD (
  py --version >nul 2>&1 && set "PYCMD=py"
)

if not defined PYCMD (
  echo ERROR: Python was not found on this computer.
  echo.
  echo   1. Install Python 3 from:
  echo        https://www.python.org/downloads/windows/
  echo   2. On the FIRST installer screen, tick
  echo        "Add python.exe to PATH"
  echo   3. Then double-click this setup.bat again.
  echo.
  pause
  exit /b 1
)

echo Using Python:
%PYCMD% --version
echo.

REM --- Create the virtual environment (if it doesn't already exist) ---
if exist ".venv\Scripts\python.exe" (
  echo Virtual environment already exists - reusing it.
) else (
  echo Creating virtual environment in .venv ...
  %PYCMD% -m venv .venv
  if errorlevel 1 (
    echo.
    echo ERROR: Could not create the virtual environment.
    pause
    exit /b 1
  )
)
echo.

REM --- Install the required packages into the virtual environment ---
echo Installing required packages ^(this can take a minute^)...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo ERROR: Package installation failed.
  echo Check your internet connection and run this setup again.
  pause
  exit /b 1
)

echo.
echo ============================================================
echo   Setup complete!
echo.
echo   Next step: double-click  run_app.bat  to start the app.
echo ============================================================
echo.
pause

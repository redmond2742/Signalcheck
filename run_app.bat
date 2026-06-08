@echo off
REM ============================================================
REM  4-Way Flash Checker - Windows launcher
REM  Double-click this file, or run it from a Command Prompt.
REM  Serves on all network interfaces so other computers on the
REM  LAN can connect.
REM ============================================================

cd /d "%~dp0"
set PORT=8501

REM Prefer the project virtual environment, then fall back to PATH.
set STREAMLIT=.venv\Scripts\streamlit.exe
if not exist "%STREAMLIT%" set STREAMLIT=streamlit

echo Starting 4-Way Flash Checker...
echo.
echo   On THIS computer, open:    http://localhost:%PORT%
echo   On OTHER computers, open one of the IPv4 addresses below, e.g. http://192.168.x.x:%PORT%
echo.
ipconfig | findstr /c:"IPv4"
echo.
echo   (Press Ctrl+C in this window to stop the app.)
echo.

"%STREAMLIT%" run app.py --server.address 0.0.0.0 --server.port %PORT%

pause

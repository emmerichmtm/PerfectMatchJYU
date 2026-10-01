@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo First double-click setup_windows.bat, or download the ready-to-run Windows ZIP.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" browser_app.py
if errorlevel 1 pause

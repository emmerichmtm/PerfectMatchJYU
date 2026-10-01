@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo First double-click setup_windows.bat to prepare this computer.
    if not defined PERFECTMATCH_NO_PAUSE pause
    exit /b 1
)
".venv\Scripts\python.exe" run_matching.py
if errorlevel 1 (
    echo.
    echo Please correct the error above, save and close the CSV files, and try again.
    echo Old results may still exist. Only use output from a SUCCESS run.
    if not defined PERFECTMATCH_NO_PAUSE pause
    exit /b 1
)
echo.
echo Open output\report.txt first, then output\result.csv.
if not defined PERFECTMATCH_NO_PAUSE pause
exit /b 0

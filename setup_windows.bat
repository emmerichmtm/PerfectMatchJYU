@echo off
setlocal
cd /d "%~dp0"
echo PerfectMatch JYU - first-time setup
echo.
if exist ".venv\Scripts\python.exe" goto install
py -3.12 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    py -3.12 -m venv .venv
    goto check_environment
)
python -c "import sys; assert sys.version_info >= (3, 11)" >nul 2>&1
if errorlevel 1 (
    echo Python was not found. Ask IT to install Python 3.12 from python.org.
    echo During installation, enable Add python.exe to PATH, then run this file again.
    goto failed
)
python -m venv .venv
:check_environment
if not exist ".venv\Scripts\python.exe" goto failed
:install
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
if not exist input mkdir input
if not exist "input\config.csv" copy "examples\config.csv" "input\config.csv" >nul
if not exist "input\problem.csv" copy "examples\problem.csv" "input\problem.csv" >nul
if not exist "input\config.csv" goto failed
if not exist "input\problem.csv" goto failed
echo.
echo Setup complete. Edit the two CSV files in input, then double-click run_matching.bat.
if not defined PERFECTMATCH_NO_PAUSE pause
exit /b 0
:failed
echo.
echo SETUP FAILED. Keep this window open and show the message above to IT.
if not defined PERFECTMATCH_NO_PAUSE pause
exit /b 1

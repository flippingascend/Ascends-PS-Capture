@echo off
rem One-click launcher: sets up a private Python environment the first time, then starts the app.
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    echo First run: setting up Ascends PS Capture program. This takes a minute...
    where py >nul 2>nul && (py -3 -m venv .venv) || (python -m venv .venv)
    if not exist ".venv\Scripts\python.exe" (
        echo.
        echo Python 3.10 or newer is needed. Install it from https://www.python.org/downloads/
        echo and tick "Add python.exe to PATH" during setup, then run this again.
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Installing the requirements failed. Check your internet connection and try again.
        pause
        exit /b 1
    )
)

start "" ".venv\Scripts\pythonw.exe" app.py

@echo off
rem Runs PS5 Toolkit with a console window so any error message stays visible.
cd /d "%~dp0"
".venv\Scripts\python.exe" app.py
echo.
echo The app closed. If there is an error above, copy it and send it to Claude.
pause

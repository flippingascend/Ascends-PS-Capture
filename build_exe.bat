@echo off
rem Builds a standalone AscendToolkit.exe in the dist folder (no Python needed to run it).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run run.bat once first so the environment exists.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install pyinstaller
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --windowed --onedir --name AscendToolkit --icon "assets/ascend.ico" --add-data "assets;assets" app.py
if errorlevel 1 (
    echo Build failed. See errors above.
    pause
    exit /b 1
)
echo.
echo Done. Your app is dist\AscendToolkit\AscendToolkit.exe (keep the whole folder together).
pause

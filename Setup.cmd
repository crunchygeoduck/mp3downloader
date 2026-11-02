@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv
    if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -m pip install --upgrade "yt-dlp[default]" "PySide6-Essentials>=6.8,<7"
if errorlevel 1 goto failed
echo Setup complete. Open Start.cmd to launch the app.
pause
exit /b 0
:failed
echo Setup failed. Check the error above.
pause
exit /b 1

@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0.venv\Scripts\pythonw.exe" (
    start "" "%~dp0.venv\Scripts\pythonw.exe" -m macooii.microphone_check
    exit /b
)
uv run python -m macooii.microphone_check
if errorlevel 1 pause

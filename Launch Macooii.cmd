@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0dist\Macooii\Macooii.exe" (
    start "" "%~dp0dist\Macooii\Macooii.exe"
    exit /b
)
where uv >nul 2>nul
if errorlevel 1 (
    echo Install uv from https://docs.astral.sh/uv/getting-started/installation/
    echo Or use the portable Macooii build in dist.
    pause
    exit /b 1
)
uv run --frozen macooii
if errorlevel 1 pause

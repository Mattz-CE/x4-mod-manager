@echo off
:: Auto-elevate to admin and run X4 Mod Manager

:: Check if already admin
net session >nul 2>&1
if %errorlevel% == 0 (
    echo Running as Administrator...
    cd /d "%~dp0"
    python main.py
    pause
) else (
    echo Requesting Administrator privileges...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    @REM use browser to open the following URL
    start http://127.0.0.1:9480/
    exit /b
)

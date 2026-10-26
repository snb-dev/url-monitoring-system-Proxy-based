@echo off
:: Starts URL Monitor. Administrator rights are not needed.
:: Extra arguments are passed on, e.g. "start.bat update-blocklist".
cd /d "%~dp0"

set "PYTHON=python"
where py >nul 2>&1 && set "PYTHON=py -3"
%PYTHON% --version >nul 2>&1
if errorlevel 1 (
    echo Python 3 was not found. Install it from https://www.python.org/downloads/
    echo and tick "Add python.exe to PATH" during setup.
    pause
    exit /b 1
)

if "%~1"=="" (
    %PYTHON% python_backend.py start
) else (
    %PYTHON% python_backend.py %*
)
pause

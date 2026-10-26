@echo off
:: Starts URL Monitor. Administrator rights are not needed.
:: Extra arguments are passed on, e.g. "start.bat status".
cd /d "%~dp0"

set "PYTHON=python"
where py >nul 2>&1 && set "PYTHON=py -3"
%PYTHON% -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
if errorlevel 1 (
    echo Python 3.11 or newer was not found. Install it from https://www.python.org/downloads/
    echo and tick "Add python.exe to PATH" during setup.
    pause
    exit /b 1
)

%PYTHON% -c "import flask, mitmproxy" >nul 2>&1
if errorlevel 1 (
    echo Installing the packages URL Monitor needs...
    %PYTHON% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Installing the packages failed. See the messages above.
        pause
        exit /b 1
    )
)

if "%~1"=="" (
    %PYTHON% -m urlmonitor start
) else (
    %PYTHON% -m urlmonitor %*
)
pause

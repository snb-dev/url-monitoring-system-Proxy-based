@echo off
:: Check for admin rights
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrative privileges...
    powershell -Command "Start-Process cmd -ArgumentList '/c %~f0' -Verb runAs'"
    exit /b
)

:: Indicate that the script has admin rights
echo Running with administrative privileges...

:: Change to the script directory
cd /d %~dp0

:: Check if Python is installed and available in PATH
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python is not found in PATH. Ensure Python is installed and added to PATH.
    pause
    exit /b
)

:: Run the Python script
echo Starting Python script...
python python_backend.py
if %errorlevel% neq 0 (
    echo Python script failed to execute. Check for errors.
    pause
    exit /b
)

:: Notify success and pause to keep the window open
echo Python script executed successfully.
pause

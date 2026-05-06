@echo off
REM ============================================================
REM  setup.bat - One-time setup for File Converter
REM  Creates a virtual environment and installs dependencies.
REM  Run this ONCE after unzipping the project.
REM ============================================================

setlocal

echo.
echo ============================================================
echo   File Converter - Setup
echo ============================================================
echo.

REM --- Check Python is installed and on PATH ---
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not on PATH.
    echo.
    echo Please install Python 3.11+ from https://www.python.org/downloads/windows/
    echo During install, CHECK the box "Add python.exe to PATH".
    echo.
    pause
    exit /b 1
)

echo [1/3] Python found:
python --version
echo.

REM --- Create virtual environment if it doesn't exist ---
if exist ".venv\" (
    echo [2/3] Virtual environment already exists, skipping creation.
) else (
    echo [2/3] Creating virtual environment in .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)
echo.

REM --- Install dependencies ---
echo [3/3] Installing dependencies (this takes a couple minutes)...
echo.
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] Dependency installation failed. Scroll up for details.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   Setup complete!
echo ============================================================
echo.
echo Next steps:
echo   - Run "run.bat" to launch the app from source
echo   - Run "build.bat" to build a standalone .exe
echo.
pause
endlocal

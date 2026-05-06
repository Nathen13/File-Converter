@echo off
REM ============================================================
REM  run.bat - Launch the app from source (for testing)
REM  Use this to test changes before building the .exe.
REM ============================================================

setlocal

if not exist ".venv\" (
    echo [ERROR] Virtual environment not found.
    echo Please run setup.bat first.
    echo.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
python main.py

endlocal

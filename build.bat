@echo off
REM ============================================================
REM  build.bat - Build the standalone .exe with PyInstaller
REM  Output goes to dist\FileConverter\FileConverter.exe
REM ============================================================

setlocal

echo.
echo ============================================================
echo   File Converter - Build
echo ============================================================
echo.

REM --- Verify venv exists ---
if not exist ".venv\" (
    echo [ERROR] Virtual environment not found.
    echo Please run setup.bat first.
    echo.
    pause
    exit /b 1
)

REM --- Activate venv ---
call .venv\Scripts\activate.bat

REM --- Clean old build artifacts ---
echo [1/2] Cleaning previous build...
if exist "build\" rmdir /s /q "build"
if exist "dist\" rmdir /s /q "dist"
echo Done.
echo.

REM --- Run PyInstaller ---
echo [2/2] Running PyInstaller (takes 1-3 minutes)...
echo.
pyinstaller build.spec --noconfirm
if errorlevel 1 (
    echo.
    echo [ERROR] Build failed. Scroll up for details.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   Build complete!
echo ============================================================
echo.
echo Your app is at:
echo   dist\FileConverter\FileConverter.exe
echo.
echo You can:
echo   - Double-click it to run
echo   - Right-click ^> Send to ^> Desktop (create shortcut)
echo   - Right-click ^> Pin to Start
echo   - Move the ENTIRE dist\FileConverter folder anywhere
echo     (the .exe needs the sibling files next to it)
echo.

REM --- Offer to open the dist folder ---
choice /c YN /m "Open the dist folder now"
if errorlevel 2 goto end
if errorlevel 1 explorer dist\FileConverter

:end
endlocal

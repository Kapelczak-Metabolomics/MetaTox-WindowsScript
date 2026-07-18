@echo off
setlocal enabledelayedexpansion

REM Build MetaToxGUI.exe from the MetaTox repository root or windows_app folder.
cd /d "%~dp0\.."

where python >nul 2>&1
if errorlevel 1 (
    echo Python was not found in PATH. Install Python 3.10+ and try again.
    exit /b 1
)

python -m pip install --upgrade pip
python -m pip install -r windows_app\requirements-build.txt

pyinstaller --noconfirm --clean windows_app\metatox_gui.spec

if errorlevel 1 (
    echo Build failed.
    exit /b 1
)

echo.
echo Build complete.
echo Executable: dist\MetaToxGUI\MetaToxGUI.exe
echo.
echo Copy the full MetaTox repository next to MetaToxGUI.exe, or run the exe
echo from the repository root so Metatox.sh and Scripts\ are available.
echo.
pause

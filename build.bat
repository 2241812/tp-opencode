@echo off
echo ========================================
echo  Building tp-opencode Executable
echo ========================================
echo.

cd /d "%~dp0"

echo Installing build dependencies...
pip install -e ".[build]" -q

echo.
echo Building with PyInstaller...
pyinstaller --clean tp-opencode.spec

echo.
echo ========================================
echo  Build complete!
echo  Executable: dist\tp-opencode\tp-opencode.exe
echo ========================================
pause

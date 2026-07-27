@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo    Build standalone exe - Hajj Season Program
echo ============================================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv not found. Run the setup .bat first.
  pause
  exit /b 1
)

echo [1/2] Ensuring PyInstaller is installed...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pyinstaller
if errorlevel 1 ( echo [ERROR] Could not install PyInstaller - check internet. & pause & exit /b 1 )

echo [2/2] Building ^(may take a few minutes^)...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean HajjApp.spec
if errorlevel 1 ( echo [ERROR] Build failed. & pause & exit /b 1 )

echo.
echo ============================================
echo    Build complete.
echo    Output:  dist\HajjApp\HajjApp.exe
echo    Copy the whole  dist\HajjApp  folder to the new PC.
echo ============================================
pause

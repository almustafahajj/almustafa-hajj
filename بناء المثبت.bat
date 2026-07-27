@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo    Build installer - Hajj Season Program
echo ============================================
echo.

REM 1) Build the exe first (PyInstaller)
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv not found. Run the setup .bat first.
  pause
  exit /b 1
)
echo [1/3] Building app ^(PyInstaller^)...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pyinstaller
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean HajjApp.spec
if errorlevel 1 ( echo [ERROR] exe build failed. & pause & exit /b 1 )

REM 2) Locate the Inno Setup compiler
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"

if "%ISCC%"=="" (
  echo [2/3] Inno Setup not found - installing via winget...
  winget install --id JRSoftware.InnoSetup --accept-source-agreements --accept-package-agreements --silent
  if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
  if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
)
if "%ISCC%"=="" ( echo [ERROR] Could not find or install Inno Setup. & pause & exit /b 1 )

REM 3) Build the installer
echo [3/3] Building installer ^(Inno Setup^)...
"%ISCC%" installer.iss
if errorlevel 1 ( echo [ERROR] Installer build failed. & pause & exit /b 1 )

echo.
echo ============================================
echo    Done.
echo    Installer:  Output\HajjApp-Setup.exe
echo    Copy it to the new PC and run it.
echo ============================================
pause

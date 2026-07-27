@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo    Setup - Hajj Season Program
echo ============================================
echo.

py -3 --version >nul 2>&1
if errorlevel 1 (
  python --version >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] Python is not installed.
    echo Download it from python.org ^(enable "Add to PATH"^) and try again.
    pause
    exit /b 1
  )
  set "PY=python"
) else (
  set "PY=py -3"
)

echo [1/3] Creating virtual environment .venv ...
%PY% -m venv .venv
if errorlevel 1 ( echo [ERROR] Could not create .venv & pause & exit /b 1 )

echo [2/3] Upgrading pip ...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip

echo [3/3] Installing libraries from requirements.txt ...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 ( echo [ERROR] Could not install libraries - check internet. & pause & exit /b 1 )

echo.
echo ============================================
echo    Setup complete.
echo    Run the desktop app, build an exe, or run the web version
echo    using the matching .bat files in this folder.
echo ============================================
pause

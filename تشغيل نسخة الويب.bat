@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo    Al Mustafa - Web version (local)
echo ============================================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv not found. Run the setup .bat first.
  pause
  exit /b 1
)

echo [1/2] Ensuring Flask is installed...
".venv\Scripts\python.exe" -m pip install --quiet flask

echo [2/2] Starting local web server...
echo.
echo    A browser tab will open at:  http://127.0.0.1:5000
echo    Keep THIS window open while using the app.
echo    Close this window to stop the server.
echo.
".venv\Scripts\python.exe" run_web.py

pause

@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo ============================================
echo    Hajj Season Program - Web version
echo ============================================
echo.
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv not found. Run the setup .bat first.
  echo.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -c "import flask, waitress" 2>nul
if errorlevel 1 (
  echo Installing web libraries...
  ".venv\Scripts\python.exe" -m pip install -r requirements-web.txt
)
echo Starting server... your browser will open automatically.
echo Keep this window open. Press Ctrl+C to stop the server.
echo.
".venv\Scripts\python.exe" -m hajj_web
echo.
echo Server stopped.
pause

@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo    برنامج موسم الحج - نسخة الويب
echo ============================================
echo.
if not exist ".venv\Scripts\python.exe" (
  echo [خطأ] لا توجد بيئة .venv. شغّل "إعداد.bat" اولا.
  pause & exit /b 1
)
REM التأكد من مكتبات الويب
".venv\Scripts\python.exe" -c "import flask, waitress" 2>nul
if errorlevel 1 (
  echo تثبيت مكتبات الويب...
  ".venv\Scripts\python.exe" -m pip install -r requirements-web.txt
)
echo تشغيل الخادم... افتح الرابط الظاهر بالاسفل من المتصفّح.
echo (لايقاف الخادم اضغط Ctrl+C ثم اغلق النافذة)
echo.
".venv\Scripts\python.exe" -m hajj_web
pause

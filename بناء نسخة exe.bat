@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo    بناء نسخة exe مستقلة - برنامج موسم الحج
echo ============================================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo [خطأ] لا توجد بيئة .venv. شغّل "إعداد.bat" اولا لتثبيت المكتبات.
  pause
  exit /b 1
)

echo [1/2] التأكد من وجود PyInstaller...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pyinstaller
if errorlevel 1 (
  echo [خطأ] تعذّر تثبيت PyInstaller - تحقّق من اتصال الانترنت.
  pause
  exit /b 1
)

echo [2/2] بناء البرنامج ^(قد ياخذ عدة دقائق^)...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean HajjApp.spec
if errorlevel 1 (
  echo [خطأ] فشل البناء.
  pause
  exit /b 1
)

echo.
echo ============================================
echo    تم البناء بنجاح
echo    الناتج:  dist\HajjApp\HajjApp.exe
echo.
echo    انسخ مجلد  dist\HajjApp  كاملا الى الجهاز الجديد
echo    وشغّل  HajjApp.exe  بداخله.
echo ============================================
pause

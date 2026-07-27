@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo    اعداد بيئة العمل - برنامج موسم الحج
echo ============================================
echo.

py -3 --version >nul 2>&1
if errorlevel 1 (
  python --version >nul 2>&1
  if errorlevel 1 (
    echo [خطأ] Python غير مثبّت. حمّله من python.org ^(فعّل "Add to PATH"^) ثم اعد المحاولة.
    pause
    exit /b 1
  )
  set "PY=python"
) else (
  set "PY=py -3"
)

echo [1/3] انشاء البيئة الافتراضية .venv ...
%PY% -m venv .venv
if errorlevel 1 ( echo [خطأ] تعذّر انشاء البيئة. & pause & exit /b 1 )

echo [2/3] تحديث pip ...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip

echo [3/3] تثبيت المكتبات من requirements.txt ...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 ( echo [خطأ] تعذّر تثبيت المكتبات - تحقّق من الانترنت. & pause & exit /b 1 )

echo.
echo ============================================
echo    تم الاعداد بنجاح
echo    شغّل البرنامج عبر  "تشغيل البرنامج.bat"
echo    او ابنِ نسخة exe عبر  "بناء نسخة exe.bat"
echo ============================================
pause

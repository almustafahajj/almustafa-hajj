@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo    بناء مُثبِّت واحد - برنامج موسم الحج
echo ============================================
echo.

REM 1) بناء الـexe اولا (PyInstaller)
if not exist ".venv\Scripts\python.exe" (
  echo [خطأ] لا توجد بيئة .venv. شغّل "إعداد.bat" اولا.
  pause & exit /b 1
)
echo [1/3] بناء البرنامج ^(PyInstaller^)...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pyinstaller
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean HajjApp.spec
if errorlevel 1 ( echo [خطأ] فشل بناء الـexe. & pause & exit /b 1 )

REM 2) ايجاد مُصرِّف Inno Setup
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"

if "%ISCC%"=="" (
  echo [2/3] Inno Setup غير مثبّت - يُثبَّت الان عبر winget...
  winget install --id JRSoftware.InnoSetup --accept-source-agreements --accept-package-agreements --silent
  if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
  if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
)
if "%ISCC%"=="" ( echo [خطأ] تعذّر ايجاد او تثبيت Inno Setup. & pause & exit /b 1 )

REM 3) بناء المُثبِّت
echo [3/3] بناء المُثبِّت ^(Inno Setup^)...
"%ISCC%" installer.iss
if errorlevel 1 ( echo [خطأ] فشل بناء المُثبِّت. & pause & exit /b 1 )

echo.
echo ============================================
echo    تم بنجاح
echo    المُثبِّت:  Output\HajjApp-Setup.exe
echo    انقله الى الجهاز الجديد وشغّله ^(نقرة مزدوجة^).
echo ============================================
pause

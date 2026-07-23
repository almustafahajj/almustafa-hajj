@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo برنامج الحج - نسخة الويب المحلية
echo يفتح في المتصفح تلقائيا... للايقاف اغلق هذه النافذة او اضغط Ctrl+C
".venv\Scripts\python.exe" -m hajj_app.webapp
pause

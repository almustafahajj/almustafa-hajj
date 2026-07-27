# -*- mode: python ; coding: utf-8 -*-
"""إعداد بناء نسخة exe مستقلة لبرنامج موسم الحج (PyInstaller، وضع مجلد).

    .venv\\Scripts\\python.exe -m PyInstaller --noconfirm --clean HajjApp.spec

الناتج: dist\\HajjApp\\HajjApp.exe  (يُنسخ المجلد كاملاً إلى الجهاز الجديد).
مجلد `data` يُنشأ بجوار الـexe عند أول تشغيل ويبقى دائماً (بيانات المستخدم).
"""

from PyInstaller.utils.hooks import collect_data_files

# الموارد المضمّنة للقراءة فقط: الشعار والأيقونة. تُقرأ لاحقاً من _MEIPASS.
datas = [("hajj_app/assets", "assets")]
# arabic_reshaper يحمل ملف إعداد افتراضي يجب أن يُرافقه
datas += collect_data_files("arabic_reshaper")

a = Analysis(
    ["run_app.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    # مُلقّم tkinter داخل PIL لا يُكتشف تلقائياً أحياناً
    hiddenimports=["PIL._tkinter_finder"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="HajjApp",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                     # نافذة رسومية — بلا نافذة أوامر سوداء
    disable_windowed_traceback=False,
    icon="hajj_app/assets/logo.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="HajjApp",
)

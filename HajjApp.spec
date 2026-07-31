# -*- mode: python ; coding: utf-8 -*-
"""إعداد بناء نسخة exe مستقلة لبرنامج موسم الحج (PyInstaller، وضع مجلد).

    .venv\\Scripts\\python.exe -m PyInstaller --noconfirm --clean HajjApp.spec

الناتج: dist\\HajjApp\\HajjApp.exe  (يُنسخ المجلد كاملاً إلى الجهاز الجديد).
مجلد `data` يُنشأ بجوار الـexe عند أول تشغيل ويبقى دائماً (بيانات المستخدم).
"""

import os
from PyInstaller.utils.hooks import collect_all, collect_data_files

# الموارد المضمّنة للقراءة فقط: الشعار والأيقونة. تُقرأ لاحقاً من _MEIPASS.
datas = [("hajj_app/assets", "assets")]
# arabic_reshaper يحمل ملف إعداد افتراضي يجب أن يُرافقه
datas += collect_data_files("arabic_reshaper")
# tkinterdnd2 يضمّ امتداد tkdnd (مكتبات + Tcl) للسحب والإفلات
_dnd_datas, _dnd_binaries, _dnd_hidden = collect_all("tkinterdnd2")
datas += _dnd_datas
# نسخة الويب: القوالب والأصول (Flask يقرأها من _MEIPASS في وضع exe)
datas += [("hajj_web/templates", "hajj_web/templates"),
          ("hajj_web/static", "hajj_web/static")]
# محرّك Tesseract المضمّن (إن وُجد مجلد vendor/tesseract) — لقراءة الجوازات
if os.path.isdir("vendor/tesseract"):
    datas += [("vendor/tesseract", "tesseract")]

a = Analysis(
    ["run_app.py"],
    pathex=[],
    binaries=_dnd_binaries,
    datas=datas,
    # مُلقّم tkinter داخل PIL + مكتبات نسخة الويب (تُستورد بكسل أحياناً)
    hiddenimports=[
        "PIL._tkinter_finder", "tkinterdnd2", *_dnd_hidden,
        "hajj_web", "hajj_web.app", "hajj_web.server", "hajj_web.sessions",
        "flask", "waitress", "qrcode", "jinja2",
    ],
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

# -*- mode: python ; coding: utf-8 -*-
"""إعداد بناء نسخة macOS مستقلّة لبرنامج موسم الحج (PyInstaller → حزمة .app).

    python3 -m PyInstaller --noconfirm --clean HajjApp-mac.spec

الناتج: dist/HajjApp.app  (يُسحب إلى مجلد Applications، أو يُغلَّف في .dmg).
مجلد `data` يُنشأ في ~/Library/Application Support/HajjApp عند أول تشغيل.

يجب تشغيل الأمر **على جهاز ماك** (PyInstaller يبني لنظام التشغيل الحالي فقط).
"""

import os
from PyInstaller.utils.hooks import collect_all, collect_data_files

datas = [("hajj_app/assets", "assets")]
datas += collect_data_files("arabic_reshaper")
_dnd_datas, _dnd_binaries, _dnd_hidden = collect_all("tkinterdnd2")
datas += _dnd_datas
# محرّك Tesseract المضمّن (إن وُجد مجلد vendor/tesseract فيه tesseract لنظام ماك)
if os.path.isdir("vendor/tesseract"):
    datas += [("vendor/tesseract", "tesseract")]

# أيقونة الحزمة: .icns يُولَّد قبل البناء (build_mac.sh)؛ وإلّا تُستعمل PNG
_icon = "hajj_app/assets/logo.icns"
if not os.path.isfile(_icon):
    _icon = "hajj_app/assets/logo.png"

a = Analysis(
    ["run_app.py"],
    pathex=[],
    binaries=_dnd_binaries,
    datas=datas,
    hiddenimports=["PIL._tkinter_finder", "tkinterdnd2", *_dnd_hidden],
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
    console=False,
    disable_windowed_traceback=False,
    icon=_icon,
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

app = BUNDLE(
    coll,
    name="HajjApp.app",
    icon=_icon,
    bundle_identifier="com.almustafa.hajjapp",
    info_plist={
        "CFBundleName": "HajjApp",
        "CFBundleDisplayName": "برنامج موسم الحج",
        "CFBundleShortVersionString": "2.0.0",
        "CFBundleVersion": "2.0.0",
        "NSHighResolutionCapable": True,          # دعم شاشات Retina
        "NSHumanReadableCopyright": "المصطفى للحج والعمرة",
        "LSMinimumSystemVersion": "11.0",
    },
)

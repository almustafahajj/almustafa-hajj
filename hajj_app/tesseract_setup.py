"""تحديد مسار Tesseract واللغات المتاحة.

وحدة مستقلة يستخدمها كلٌّ من قارئ MRZ وقارئ العربية، تفادياً لاستيراد
دائري بينهما.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytesseract

# اسم الملف التنفيذي حسب النظام (ويندوز يضيف .exe)
_EXE = "tesseract.exe" if os.name == "nt" else "tesseract"

# أماكن التثبيت المعتادة لكل نظام (تُفحص إن لم يُوجد في PATH)
if os.name == "nt":
    _CANDIDATES = (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    )
elif sys.platform == "darwin":
    # ماك: Homebrew (Apple Silicon/Intel) وMacPorts
    _CANDIDATES = (
        "/opt/homebrew/bin/tesseract",
        "/usr/local/bin/tesseract",
        "/opt/local/bin/tesseract",
        "/usr/bin/tesseract",
    )
else:
    _CANDIDATES = ("/usr/bin/tesseract", "/usr/local/bin/tesseract")

_LANG_CACHE: set[str] | None = None


def _bundled_candidates() -> list[Path]:
    """مسارات Tesseract المضمّنة مع النسخة المبنيّة (exe/‏.app إن وُجدت)."""
    out: list[Path] = []
    try:
        from .paths import is_frozen, resource_dir
        if is_frozen():
            out.append(resource_dir() / "tesseract" / _EXE)
            exe_dir = Path(sys.executable).resolve().parent
            out.append(exe_dir / "tesseract" / _EXE)
            out.append(exe_dir / "_internal" / "tesseract" / _EXE)
            # حزمة ماك .app: الموارد في Contents/Resources بجوار MacOS/
            out.append(exe_dir.parent / "Resources" / "tesseract" / _EXE)
    except Exception:                                  # noqa: BLE001
        pass
    return out


def configure_tesseract() -> str | None:
    """يحدد مسار tesseract.exe ويضبطه في pytesseract. يعيد المسار أو None.

    الأولوية للنسخة **المضمّنة** مع البرنامج (نسخة exe)، ثم PATH، ثم أماكن
    التثبيت المعتادة — فيعمل قارئ الجوازات دون تثبيت منفصل.
    """
    current = pytesseract.pytesseract.tesseract_cmd
    if current and Path(current).is_file():
        return current

    found = None
    for bundled in _bundled_candidates():
        if bundled.is_file():
            found = str(bundled)
            break
    if not found:
        found = shutil.which("tesseract")
    if not found:
        for candidate in _CANDIDATES:
            if Path(candidate).is_file():
                found = candidate
                break
    if found:
        pytesseract.pytesseract.tesseract_cmd = found
    return found


def available_languages() -> set[str]:
    """لغات Tesseract المتاحة. تُقرأ مرة واحدة وتُخزَّن عند النجاح فقط."""
    global _LANG_CACHE
    if _LANG_CACHE:
        return _LANG_CACHE
    if not configure_tesseract():
        return set()
    try:
        langs = set(pytesseract.get_languages(config=""))
    except Exception:
        return set()
    _LANG_CACHE = langs
    return langs


def arabic_supported() -> bool:
    """هل حزمة اللغة العربية (ara.traineddata) مثبّتة؟"""
    return "ara" in available_languages()

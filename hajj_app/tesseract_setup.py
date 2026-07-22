"""تحديد مسار Tesseract واللغات المتاحة.

وحدة مستقلة يستخدمها كلٌّ من قارئ MRZ وقارئ العربية، تفادياً لاستيراد
دائري بينهما.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytesseract

_CANDIDATES = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
)

_LANG_CACHE: set[str] | None = None


def configure_tesseract() -> str | None:
    """يحدد مسار tesseract.exe ويضبطه في pytesseract. يعيد المسار أو None."""
    current = pytesseract.pytesseract.tesseract_cmd
    if current and Path(current).is_file():
        return current

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

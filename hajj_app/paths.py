"""تحديد المسارات بوعيٍ لوضع التشغيل: من المصدر أو كنسخة exe مبنيّة.

عند بناء البرنامج بـ PyInstaller يعمل من مجلد استخراج مؤقّت (يُمسح عند
الإغلاق). لذا نفصل نوعين من المسارات:

* **البيانات** (كشف الحجّاج، الحسابات، الإعدادات، النسخ الاحتياطية) يجب أن
  تبقى **دائمة بجوار الملف التنفيذي** — لا داخل المجلد المؤقّت وإلا ضاعت.
* **الموارد المضمّنة** (الشعار...) للقراءة فقط، وتُستخرج مع البرنامج، فتُقرأ
  من مجلد PyInstaller المؤقّت (``sys._MEIPASS``).
"""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    """هل يعمل البرنامج كنسخة exe مبنيّة (PyInstaller)؟"""
    return bool(getattr(sys, "frozen", False))


def data_dir() -> Path:
    """مجلد البيانات الدائم.

    * نسخة exe: بجوار الملف التنفيذي ``HajjApp.exe`` (يبقى بعد الإغلاق).
    * من المصدر: مجلد ``data`` بجانب حزمة ``hajj_app``.
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent / "data"
    return Path(__file__).resolve().parent.parent / "data"


def resource_dir() -> Path:
    """مجلد الموارد المضمّنة (للقراءة فقط).

    * نسخة exe: مجلد الاستخراج المؤقّت ``_MEIPASS``.
    * من المصدر: داخل حزمة ``hajj_app`` (حيث مجلد ``assets``).
    """
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent

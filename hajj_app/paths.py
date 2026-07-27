"""تحديد المسارات بوعيٍ لوضع التشغيل: من المصدر أو كنسخة exe مبنيّة.

عند بناء البرنامج بـ PyInstaller يعمل من مجلد استخراج مؤقّت (يُمسح عند
الإغلاق). لذا نفصل نوعين من المسارات:

* **البيانات** (كشف الحجّاج، الحسابات، الإعدادات، النسخ الاحتياطية) يجب أن
  تبقى **دائمة بجوار الملف التنفيذي** — لا داخل المجلد المؤقّت وإلا ضاعت.
* **الموارد المضمّنة** (الشعار...) للقراءة فقط، وتُستخرج مع البرنامج، فتُقرأ
  من مجلد PyInstaller المؤقّت (``sys._MEIPASS``).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    """هل يعمل البرنامج كنسخة exe مبنيّة (PyInstaller)؟"""
    return bool(getattr(sys, "frozen", False))


def _is_writable(folder: Path) -> bool:
    """هل يمكن الكتابة في هذا المجلد؟ (Program Files غالباً للقراءة فقط)."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def data_dir() -> Path:
    """مجلد البيانات الدائم — يبقى بعد الإغلاق ويحمل كشف الحجّاج والحسابات.

    * **نسخة محمولة** (exe في مجلد يمكن الكتابة فيه، كسطح المكتب أو فلاشة):
      مجلد ``data`` بجوار الملف التنفيذي — يسهل نقله ونسخه.
    * **نسخة مثبّتة** (exe في ``Program Files`` للقراءة فقط): مجلد المستخدم
      ``%LOCALAPPDATA%\\HajjApp\\data`` — لأن الكتابة بجوار البرنامج ممنوعة.
    * **من المصدر**: مجلد ``data`` بجانب حزمة ``hajj_app``.
    """
    if is_frozen():
        exe_dir = Path(sys.executable).resolve().parent
        beside_exe = exe_dir / "data"
        # نسخة محمولة قائمة مسبقاً، أو مجلد يمكن الكتابة فيه -> بجوار البرنامج
        if beside_exe.is_dir() or _is_writable(exe_dir):
            return beside_exe
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        base_dir = Path(base) if base else Path.home()
        return base_dir / "HajjApp" / "data"
    return Path(__file__).resolve().parent.parent / "data"


def resource_dir() -> Path:
    """مجلد الموارد المضمّنة (للقراءة فقط).

    * نسخة exe: مجلد الاستخراج المؤقّت ``_MEIPASS``.
    * من المصدر: داخل حزمة ``hajj_app`` (حيث مجلد ``assets``).
    """
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent

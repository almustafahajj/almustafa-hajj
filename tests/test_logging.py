# -*- coding: utf-8 -*-
"""اختبار نظام تسجيل الأحداث والأخطاء: الكتابة بترميز UTF-8 والتقاط الأخطاء."""
import sys, io
import os as _os
import pathlib as _pl
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_HERE)
_OUTDIR = _os.path.join(_HERE, "_out")
sys.path.insert(0, _ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# عزل: وجّه مجلد البيانات إلى مجلد الاختبار كي لا نلوّث سجلّ المستخدم
_DATA = _pl.Path(_OUTDIR) / "logdata"
if _DATA.exists():
    import shutil
    shutil.rmtree(_DATA)
_DATA.mkdir(parents=True, exist_ok=True)

import hajj_app.paths as paths
paths.data_dir = lambda: _DATA

import importlib
import hajj_app.logging_setup as L
importlib.reload(L)

print("=== التهيئة تنشئ ملف سجلّ في مجلد البيانات ===")
p = L.setup_logging()
assert p == _DATA / "logs" / "hajj_app.log", p
assert p.is_file(), p
print(f"  OK: {p.relative_to(_DATA)}")

print("\n=== الكتابة بالعربية بترميز UTF-8 ===")
L.get_logger("test").info("رسالة عربية للتجربة")
L.get_logger("test").error("خطأ عربي للتجربة")
txt = p.read_text(encoding="utf-8")
assert "رسالة عربية للتجربة" in txt, txt
assert "خطأ عربي للتجربة" in txt
print("  OK: النصّ العربي محفوظ سليماً")

print("\n=== التهيئة مرّة ثانية لا تُكرّر المعالِجات ===")
import logging
before = len(logging.getLogger().handlers)
L.setup_logging()
assert len(logging.getLogger().handlers) == before, "تكرّرت المعالِجات"
print(f"  OK: {before} معالِجات ثابتة")

print("\n=== التقاط خطأ خيط غير مُعالَج ===")
import threading, time
def _boom():
    raise ValueError("انفجار في خيط الاختبار")
t = threading.Thread(target=_boom, name="TWorker")
t.start(); t.join()
time.sleep(0.15)
txt = p.read_text(encoding="utf-8")
assert "انفجار في خيط الاختبار" in txt, "لم يُسجَّل خطأ الخيط"
assert "TWorker" in txt
print("  OK: خطأ الخيط سُجِّل بتتبّعه الكامل")

print("\n=== موجّه Tkinter يُركّب دون تشغيل واجهة ===")
class _FakeTk:
    class Tk:
        pass
L.install_tk_excepthook(_FakeTk)
assert callable(_FakeTk.Tk.report_callback_exception)
print("  OK: report_callback_exception مُركّب")

print("\n*** LOGGING TESTS PASSED ***")

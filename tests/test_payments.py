# -*- coding: utf-8 -*-
"""اختبار سجلّ الدفعات (الأقساط): التخزين، المزامنة، ونافذة الدفعات."""
import sys, io
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_HERE)
_OUTDIR = _os.path.join(_HERE, "_out")
_os.makedirs(_OUTDIR, exist_ok=True)
sys.path.insert(0, _ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from pathlib import Path
from hajj_app import fields, storage
from hajj_app.mrz import PassportData

WORK = Path(_OUTDIR) / "payments"
WORK.mkdir(parents=True, exist_ok=True)
DB = WORK / "d.json"

print("=== المزامنة والحساب ===")
rec = PassportData(full_name_ar="حاج", passport_number="P1", program_value="10000")
rec.payments = [
    {"date": "2026-01-01", "amount": "3,000", "method": "نقد", "note": "أولى"},
    {"date": "2026-02-01", "amount": "2,000", "method": "تحويل", "note": ""},
]
assert fields.payment_total(rec) == 5000.0
fields.sync_paid_amount(rec)
assert rec.paid_amount == "5,000", rec.paid_amount
assert fields.compute_remaining(rec) == "5,000"      # 10000 - 5000
print("  OK: المجموع 5,000 والمتبقّي 5,000")

print("\n=== التخزين يحفظ الدفعات كقائمة قواميس ===")
storage.save_records([rec], DB, None)
back, _ = storage.load_records(DB, None)
p = back[0].payments
assert len(p) == 2 and isinstance(p[0], dict), p
assert p[0]["method"] == "نقد" and p[0]["amount"] == "3,000"
assert back[0].paid_amount == "5,000"
print("  OK: الدفعات تبقى بنيةً بعد الحفظ والتحميل")

print("\n=== قيمة تالفة لا تُعطب التحميل ===")
rec2 = PassportData(passport_number="P2")
rec2.payments = "غير صحيح"                 # نوع خاطئ
storage.save_records([rec2], WORK / "bad.json", None)
b2, _ = storage.load_records(WORK / "bad.json", None)
assert b2[0].payments == []                # عُقّمت إلى قائمة فارغة
print("  OK: قيمة الدفعات التالفة تصبح قائمة فارغة")

print("\n=== نافذة الدفعات: إضافة/حذف ومزامنة المدفوع ===")
import tkinter as tk
from hajj_app.gui import PaymentsDialog
root = tk.Tk(); root.withdraw()
rec3 = PassportData(full_name_ar="ح3", program_value="8000")
fired = []
dlg = PaymentsDialog(root, rec3, lambda: fired.append(1))
dlg._amount.set("1500"); dlg._add()
assert len(rec3.payments) == 1 and rec3.paid_amount == "1,500" and fired
dlg._amount.set("500"); dlg._add()
assert rec3.paid_amount == "2,000", rec3.paid_amount
dlg.tree.selection_set("0"); dlg._delete()
assert len(rec3.payments) == 1 and rec3.paid_amount == "500"
# حذف كل الدفعات يعيد المدفوع إلى صفر
dlg.tree.selection_set(*dlg.tree.get_children()); dlg._delete()
assert rec3.payments == [] and rec3.paid_amount == "0", rec3.paid_amount
root.destroy()
print("  OK: الإضافة والحذف يزامنان «المدفوع»، والتفريغ يعيده صفراً")

print("\n=== تسجيل الحضور (مسح QR/جواز) ===")
from hajj_app.gui import CheckInDialog
recs = [PassportData(full_name_ar="أحمد", passport_number="A1", phone="0501"),
        PassportData(full_name_ar="سالم", passport_number="B2",
                     reference_number="REF9")]
root2 = tk.Tk(); root2.withdraw()
seen = []
ci = CheckInDialog(root2, lambda: recs, lambda: seen.append(1))
ci._scan.set("A1"); ci._submit()                    # مسح بالجواز
assert "المطار" in recs[0].checkins and seen
ci._scan.set("الحاج: سالم  الجواز: B2  الهاتف: 0502"); ci._submit()   # نصّ QR
assert "المطار" in recs[1].checkins
ci._stage.set("الباص"); ci._scan.set("REF9"); ci._submit()   # بالرقم المرجعي
assert "الباص" in recs[1].checkins
assert ci._find("أحمد") == 0                         # مطابقة بالاسم (كتابة يدوية)
assert ci._find("زيد") is None
ci._scan.set("ZZZ"); ci._submit()                   # غير موجود
assert "لم يُعثر" in ci._result.cget("text")
ci._stage.set("المطار"); ci._refresh()              # كلاهما حضر للمطار
assert len(ci.absent.get_children()) == 0
# التخزين يحفظ الحضور قاموساً
CK = WORK / "checkins.json"
storage.save_records(recs, CK, None)
b, _ = storage.load_records(CK, None)
assert isinstance(b[0].checkins, dict) and b[0].checkins.get("المطار")
root2.destroy()
print("  OK: مطابقة بالجواز/QR/المرجعي، الغائبون، والتخزين قاموساً")

print("\n=== تصدير تقرير الحضور PDF (معاينة) ===")
# دالة الـPDF مباشرةً
from hajj_app.pdf_io import export_attendance_pdf
_ATT = WORK / "attendance.pdf"
_recs = [
    PassportData(full_name_ar="أحمد", passport_number="A1", group="م1",
                 checkins={"المطار": "2026-07-01 08:00", "الباص": "2026-07-01 09:00"}),
    PassportData(full_name_ar="سالم", passport_number="B2",
                 checkins={"المطار": "2026-07-01 08:05"}),
    PassportData(full_name_ar="خالد", passport_number="C3"),
]
export_attendance_pdf(_recs, _ATT, stages=["المطار", "الفندق", "الباص", "العودة"],
                      season="1447")
assert _ATT.is_file() and _ATT.read_bytes()[:5] == b"%PDF-"
assert _ATT.stat().st_size > 2000
# do_attendance_report يستدعي المعاينة بامتداد pdf
import hajj_app.gui as _g
_calls = {}
_g.open_preview = lambda parent, fn, name, ext: (fn(str(WORK / "r.pdf")),
                                                 _calls.update(ext=ext),
                                                 str(WORK / "r.pdf"))[-1]
_g.default_data_path = lambda: WORK / "attdb.json"
_ar = tk.Tk(); _ar.withdraw()
_app = _g.HajjApp(_ar, session=None)
_app.records = _recs
_app.season_year.set("1447")
_app.do_attendance_report()
assert _calls.get("ext") == "pdf"
assert (WORK / "r.pdf").read_bytes()[:5] == b"%PDF-"
_ar.destroy()
print("  OK: تقرير الحضور PDF صالح، والمعاينة بامتداد pdf")

print("\n*** PAYMENTS TESTS PASSED ***")

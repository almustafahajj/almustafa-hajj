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

print("\n*** PAYMENTS TESTS PASSED ***")

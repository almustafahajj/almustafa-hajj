# -*- coding: utf-8 -*-
"""اختبار برنامج العمرة: نموذج الفوج، الشاشة الرئيسية، ونافذة معتمري الفوج."""
import sys, io
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_HERE)
_OUTDIR = _os.path.join(_HERE, "_out")
_os.makedirs(_OUTDIR, exist_ok=True)
sys.path.insert(0, _ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import pathlib
import tkinter as tk
import hajj_app.storage as st
from hajj_app import app_mode, umrah
from hajj_app.mrz import PassportData

WORK = pathlib.Path(_OUTDIR) / "umrah"
WORK.mkdir(parents=True, exist_ok=True)
for _f in WORK.glob("*"):
    if _f.is_file():
        _f.unlink()
app_mode.set_mode("umrah")
st.default_data_path = lambda: WORK / app_mode.data_filename()

print("=== نموذج الفوج والتخزين ===")
s = {}
assert umrah.load_trips(s) == []
t1 = umrah.UmrahTrip(code="U1", name="رمضان", makkah_hotel="فندق", capacity="40",
                     services=["تأشيرة العمرة", "تأمين طبّي"])
t2 = umrah.UmrahTrip(code="U2", name="شعبان")
umrah.save_trips(s, [t1, t2])
back = umrah.load_trips(s)
assert [t.code for t in back] == ["U1", "U2"]
assert back[0].services == ["تأشيرة العمرة", "تأمين طبّي"]
assert umrah.next_code(back) == "U3"
print("  OK: حفظ/تحميل الأفواج + اقتراح الرمز التالي")

print("\n=== ربط المعتمر بالفوج ===")
recs = [PassportData(full_name_ar="أ", trip="U1"),
        PassportData(full_name_ar="ب", trip="U2"),
        PassportData(full_name_ar="ج", trip="U1")]
assert len(umrah.trip_pilgrims(recs, "U1")) == 2
assert len(umrah.trip_pilgrims(recs, "U2")) == 1
assert umrah.trip_pilgrims(recs, "U9") == []
print("  OK: ترشيح معتمري كل فوج حسب الحقل trip")

print("\n=== الشاشة الرئيسية ونافذة المعتمرين ===")
import hajj_app.umrah_gui as ug
root = tk.Tk(); root.withdraw()
app = ug.UmrahApp(root, session=None)
assert app.trips == [] and app.records == []
# إضافة فوج عبر منطق الشاشة
tt = umrah.UmrahTrip(code="U1", name="رمضان 1", capacity="30")
app._on_trip_saved(tt)
assert [x.code for x in app.trips] == ["U1"]
assert app.tree.get_children() == ("U1",)                 # ظهر في الجدول
# إضافة معتمرين للفوج والحفظ المشفّر
for nm, val, paid in [("محمد", "5000", "2000"), ("أحمد", "5000", "5000")]:
    r = PassportData(full_name_ar=nm, program_value=val, paid_amount=paid, trip="U1")
    app.records.append(r)
app.save()
recs2, _ = st.load_records()
assert len(recs2) == 2 and all(r.trip == "U1" for r in recs2)   # مُخزَّن مع الفوج
# نافذة معتمري الفوج: العدّ والمالية
win = ug.TripPilgrimsWindow(app, tt)
assert len(win.tree.get_children()) == 2
fin = win.fin.cget("text")
assert "العدد: 2" in fin and "الإجمالي: 10,000" in fin and "المتبقّي: 3,000" in fin
# حذف الفوج يُبقي المعتمرين في البيانات (لا يحذفهم)
win.destroy()
app.trips.remove(tt); app.save_trips(); app._reload()
assert app.tree.get_children() == ()
assert len(st.load_records()[0]) == 2                      # المعتمرون باقون
root.destroy()
print("  OK: الأفواج تُدار، المعتمرون يُحفظون مشفّرين، والمالية تُحسب")

app_mode.set_mode("hajj")
print("\n*** UMRAH TESTS PASSED ***")

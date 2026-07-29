# -*- coding: utf-8 -*-
"""اختبار برنامج العمرة: نموذج البرنامج، التسعير، النقل، الحجز، ونافذة المعتمرين."""
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
from tkinter import messagebox as _mb
# تعطيل الرسائل المنبثقة الحاجبة أثناء الاختبار (تحاكي ضغط المستخدم)
_mb.showinfo = lambda *a, **k: "ok"
_mb.showwarning = lambda *a, **k: "ok"
_mb.showerror = lambda *a, **k: "ok"
_mb.askyesno = lambda *a, **k: True
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

print("=== النموذج والتخزين والترحيل ===")
s = {}
assert umrah.load_trips(s) == []
t1 = umrah.UmrahTrip(code="U1", name="رمضان", makkah_hotel="فندق",
                     price_double="4500",
                     services=[{"name": "تأمين طبّي", "price": "200"}])
umrah.save_trips(s, [t1, umrah.UmrahTrip(code="U2", name="شعبان")])
back = umrah.load_trips(s)
assert [t.code for t in back] == ["U1", "U2"]
assert back[0].services == [{"name": "تأمين طبّي", "price": "200"}]
assert umrah.next_code(back) == "U3"
# ترحيل الصيغة القديمة: services=list[str] و price المفرد القديم
old = umrah.trip_from_dict({"code": "X", "price": "3000",
                            "services": ["زيارة المدينة المنوّرة"]})
assert old.price_double == "3000"                       # رُحّل السعر القديم
assert old.services == [{"name": "زيارة المدينة المنوّرة", "price": ""}]
print("  OK: حفظ/تحميل + ترحيل الأسعار والخدمات القديمة")

print("\n=== التسعير والنقل ===")
t = umrah.UmrahTrip(code="P1", price_single="6000", price_double="4500",
                    price_triple="4000", price_quad="3500",
                    services=[{"name": "تأمين طبّي", "price": "200"},
                              {"name": "زيارة المدينة المنوّرة", "price": "300"}])
assert umrah.room_price(t, "price_double") == 4500
assert umrah.services_map(t)["تأمين طبّي"] == 200
assert umrah.package_per_person(t, "price_double", ["تأمين طبّي"]) == 4700
assert umrah.package_per_person(
    t, "price_single", ["تأمين طبّي", "زيارة المدينة المنوّرة"]) == 6500
assert "فورد" in umrah.suggest_transport(2)
assert "جيمس" in umrah.suggest_transport(3) and "جيمس" in umrah.suggest_transport(6)
assert umrah.suggest_transport(0) == ""
print("  OK: أسعار الغرف + الخدمات لكل شخص + قاعدة النقل حسب العدد")

print("\n=== ربط المعتمر بالبرنامج ===")
recs = [PassportData(trip="U1"), PassportData(trip="U2"), PassportData(trip="U1")]
assert len(umrah.trip_pilgrims(recs, "U1")) == 2
assert umrah.trip_pilgrims(recs, "U9") == []
print("  OK: ترشيح معتمري كل برنامج")

print("\n=== الواجهة: البرامج، الحجز بالتسعير، والمالية ===")
import hajj_app.umrah_gui as ug
root = tk.Tk(); root.withdraw()
app = ug.UmrahApp(root, session=None)
tt = umrah.UmrahTrip(code="P1", name="رمضان ١", price_triple="4000",
                     services=[{"name": "تأمين طبّي", "price": "200"}])
app._on_trip_saved(tt)
assert app.tree.get_children() == ("P1",)
win = ug.TripPilgrimsWindow(app, tt)
# حجز بالتسعير: 3 أشخاص، غرفة ثلاثية، + خدمة تأمين
bd = ug.BookingDialog(win, tt)
bd.persons.set("3"); bd.room.set("ثلاثي")
bd.svc_vars["تأمين طبّي"].set(True)
bd._recalc()
assert getattr(bd, "_per_person") == 4200          # 4000 + 200
assert "جيمس" in bd.transport.get()                # النقل تلقائي (3 أشخاص)
bd._add()
recs2, _ = st.load_records()
assert len(recs2) == 3 and all(r.trip == "P1" for r in recs2)
assert all(r.program_value == "4200" and r.room_type == "ثلاثي" for r in recs2)
fin = win.fin.cget("text")
assert "العدد: 3" in fin and "الإجمالي: 12,600" in fin
root.destroy()
print("  OK: الحجز يضيف الأشخاص بالسعر المحسوب والنقل التلقائي والمالية تُجمَع")

print("\n=== نافذة التعديل في وضع العمرة (بلا حقول الحج) ===")
import hajj_app.gui as _g
r2 = tk.Tk(); r2.withdraw()
dlg = _g.EditDialog(r2, PassportData(), lambda _r: None, umrah=True)
for hajj_key in ("program", "group", "visa_number", "permit_status", "hady",
                 "masar_number", "executive_service"):
    assert hajj_key not in dlg.vars, hajj_key
for keep in ("full_name_ar", "passport_number", "program_value", "hotel"):
    assert keep in dlg.vars, keep
dlg.destroy()
# وضع الحج يُبقي الحقول
dlg2 = _g.EditDialog(r2, PassportData(), lambda _r: None)
assert "visa_number" in dlg2.vars and "program" in dlg2.vars
dlg2.destroy()
r2.destroy()
print("  OK: العمرة تُخفي برنامج الحملة/التأشيرة/التصريح/الهدي، والحج يُبقيها")

app_mode.set_mode("hajj")
print("\n*** UMRAH TESTS PASSED ***")

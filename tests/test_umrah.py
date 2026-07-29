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
tt.capacity = "3"                                  # سعة محدّدة للاختبار
tt.airline = "الطيران السعودي"; tt.flight_out = "SV553"
tt.depart_date = "2026-03-01"; tt.makkah_hotel = "كونراد"
win = ug.TripPilgrimsWindow(app, tt)
# حجز بالتسعير: 3 أشخاص، غرفة ثلاثية، + خدمة تأمين
bd = ug.BookingDialog(win, tt)
bd.persons.set("3"); bd.room.set("ثلاثي")
bd.svc_vars["تأمين طبّي"].set(True)
bd._recalc()
assert getattr(bd, "_per_person") == 4200          # 4000 + 200
assert "جيمس" in bd.transport.get()                # النقل تلقائي (3 أشخاص)
# التسعير + السفر/الإقامة من البرنامج + الرقم المرجعي التلقائي لكل معتمر
for nm in ("محمد", "أحمد", "سالم"):
    r = PassportData(full_name_ar=nm)
    bd._apply_booking(r)
    assert r.program_value == "4200" and r.room_type == "ثلاثي"
    assert "جيمس" in r.transport and r.trip == "P1"
    assert r.airline == "الطيران السعودي" and r.hotel == "كونراد"   # من البرنامج
    assert r.reference_number.startswith("P1-")                     # تلقائي
    bd._commit_person(r)
assert bd._added == 3
refs = [r.reference_number for r in umrah.trip_pilgrims(app.records, "P1")]
assert len(set(refs)) == 3                          # أرقام مرجعية فريدة
recs2, _ = st.load_records()
assert len(recs2) == 3 and all(r.program_value == "4200" for r in recs2)
fin = win.fin.cget("text")
assert "العدد: 3" in fin and "المقاعد المتبقّية: 0 من 3" in fin
# السعة: لا تقبل أكثر من المحدَّد
assert win._seats_left() == 0 and win._check_capacity(1) is False
# رمز البرنامج يُذكر في الكشف
assert win._prog_label() == "P1 — رمضان ١"
# الموسم = سنة ميلادية: تصفية البرامج حسب سنة المغادرة
app._season.set("2026")
app.trips += [umrah.UmrahTrip(code="A", name="أ", depart_date="2026-03-01"),
              umrah.UmrahTrip(code="B", name="ب", depart_date="2027-04-01")]
app._reload()
c26 = set(app.tree.get_children())
assert "A" in c26 and "B" not in c26 and "P1" in c26      # P1 مغادرته 2026
app._season.set("2027"); app._reload()
c27 = set(app.tree.get_children())
assert "B" in c27 and "A" not in c27 and "P1" not in c27
assert "١ يناير" in app._season_text() and "2027" in app._season_text()
root.destroy()
print("  OK: التسعير والسفر والرقم المرجعي، السعة، رمز البرنامج، وموسم السنة")

print("\n=== نافذة التعديل في وضع العمرة ===")
import hajj_app.gui as _g
r2 = tk.Tk(); r2.withdraw()
dlg = _g.EditDialog(r2, PassportData(), lambda _r: None, umrah=True)
# مُستبعَد: حقول الحج + السفر/الفندق (من البرنامج) + الصحة والطوارئ
for gone in ("program", "group", "visa_number", "permit_status", "hady",
             "masar_number", "executive_service", "airline", "flight_number",
             "hotel", "arrival_date", "blood_type", "emergency_name"):
    assert gone not in dlg.vars, gone
# موجود: البيانات + الرقم المرجعي + المالية مع تاريخ الدفع وطريقته
for keep in ("full_name_ar", "passport_number", "reference_number",
             "program_value", "paid_amount", "payment_date", "payment_method",
             "room_type", "transport"):
    assert keep in dlg.vars, keep
dlg.destroy()
# وضع الحج يُبقي كل الحقول
dlg2 = _g.EditDialog(r2, PassportData(), lambda _r: None)
assert "visa_number" in dlg2.vars and "program" in dlg2.vars and "hotel" in dlg2.vars
dlg2.destroy()
r2.destroy()
print("  OK: العمرة تُلغي الحج/السفر/الصحة، وتضيف تاريخ/طريقة الدفع، والحج يُبقيها")

print("\n=== الخدمات الجديدة وكشف المعتمرين ومسمّياته ===")
app_mode.set_mode("umrah")
for extra in ("المطوّف", "خدمة التنفيذي في الاستقبال",
              "خدمة التنفيذي في المغادرة", "خدمة مُرافق"):
    assert extra in umrah.DEFAULT_SERVICES, extra
assert app_mode.label("release_name") == "ميسّر العمرة"      # اسم التطبيق
# صفّ الكشف بالأعمدة المطلوبة
rec = PassportData(full_name_ar="سعيد", passport_number="A9",
                   expiry_date="2030-01-01", nationality_ar="الإمارات",
                   hotel="كونراد", room_type="ثنائي", airline="السعودية",
                   program_value="5000", paid_amount="2000")
row = umrah.report_row(rec, 1, "رمضان")
assert [k for k, _l in umrah.REPORT_COLUMNS] == [
    "serial", "full_name_ar", "passport_number", "expiry_date", "nationality_ar",
    "program", "hotel", "room_type", "airline", "program_value",
    "paid_amount", "remaining"]
# الجنسية قبل البرنامج
_keys = [k for k, _l in umrah.REPORT_COLUMNS]
assert _keys.index("nationality_ar") < _keys.index("program")
assert row["program"] == "رمضان" and row["remaining"] == "3,000"
# تصدير PDF + إكسل بمسمّيات العمرة (لا «حاج» في الكشف)
from hajj_app.pdf_io import export_umrah_pdf
from hajj_app.excel_io import export_umrah_excel
pdf = WORK / "kashf.pdf"
export_umrah_pdf([rec], pdf, program_name="رمضان")
assert pdf.read_bytes()[:5] == b"%PDF-" and pdf.stat().st_size > 3000
xlsx = WORK / "kashf.xlsx"
export_umrah_excel([rec], xlsx, program_name="رمضان")
from openpyxl import load_workbook
ws = load_workbook(xlsx).active
assert [ws.cell(row=2, column=c).value for c in range(1, 13)] == \
    [lbl for _k, lbl in umrah.REPORT_COLUMNS]
cells = [str(c.value) for r in ws.iter_rows() for c in r if c.value is not None]
assert not any("حاج" in t for t in cells), "بقيت كلمة حاج في الكشف"
assert any("المعتمرين" in t for t in cells)                # عنوان الكشف
print("  OK: خدمات جديدة + كشف بأعمدته ومسمّيات العمرة (بلا «حاج») + اسم التطبيق")

print("\n=== التسكين (مكة/المدينة) ===")
app_mode.set_mode("umrah")
rr = [PassportData(full_name_ar=f"م{i}", passport_number=f"P{i}", room_type=rt,
                   trip="R1") for i, rt in enumerate(
                       ["ثنائي", "ثنائي", "ثنائي", "مفرد"])]
assert umrah.auto_assign_rooms(rr, "makkah_room") == 3      # 3 ثنائي→غرفتان + مفرد
rooms, un = umrah.rooming_rooms(rr, "makkah_room")
assert len(rooms) == 3 and not un
assert all(not r.madinah_room for r in rr)                  # المدينة مستقلة عن مكة
umrah.auto_assign_rooms(rr, "madinah_room")
assert all(r.madinah_room and r.makkah_room for r in rr)    # الحقلان مستقلان
from hajj_app.pdf_io import export_umrah_rooming_pdf
p = WORK / "rooms.pdf"
export_umrah_rooming_pdf(rr, p, city_label="مكة المكرّمة", hotel="كونراد",
                         nights="7", program_name="R1 — رمضان",
                         room_field="makkah_room")
assert p.read_bytes()[:5] == b"%PDF-" and p.stat().st_size > 2500
# نافذة التسكين: توزيع، عرض، ومسح
r3 = tk.Tk(); r3.withdraw()
app3 = ug.UmrahApp(r3, session=None)
t3 = umrah.UmrahTrip(code="R1", name="رمضان", makkah_hotel="كونراد",
                     madinah_hotel="دار التقوى")
app3.trips.append(t3)
app3.records.extend([PassportData(full_name_ar=f"س{i}", room_type="ثنائي",
                                  trip="R1") for i in range(4)])
rw = ug.RoomingWindow(app3, t3)
rw._auto("makkah")
assert all(r.makkah_room for r in umrah.trip_pilgrims(app3.records, "R1"))
vals = [rw._trees["makkah"].item(i, "values")
        for i in rw._trees["makkah"].get_children()]
assert all(v[4] not in ("", "—") for v in vals)            # رقم الغرفة ظاهر
rw._clear("makkah")                                        # يؤكّد (مُثبَّت) ويمسح
assert all(not r.makkah_room for r in umrah.trip_pilgrims(app3.records, "R1"))
r3.destroy()
print("  OK: توزيع تلقائي مستقل لكل مدينة + كشف الغرف + نافذة التسكين")

app_mode.set_mode("hajj")
print("\n*** UMRAH TESTS PASSED ***")

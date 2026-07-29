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
# حجز بالتسعير: 3 أشخاص، غرفة ثلاثية، + خدمة تأمين (مسعّرة)
bd = ug.BookingDialog(win, tt)
bd.persons.set("3"); bd.room.set("ثلاثي")
for _r in bd.svc_rows:                              # اختيار خدمة تأمين طبّي
    if _r["name"] == "تأمين طبّي":
        _r["on"].set(True)
bd._recalc()
assert getattr(bd, "_per_person") == 4200          # 4000 + 200
assert "جيمس" in bd.transport.get()                # النقل تلقائي (3 أشخاص)
# إضافة خدمة مخصّصة مسعّرة يدوياً تزيد سعر الفرد
bd._new_svc.set("خدمة خاصة"); bd._new_price.set("500")
bd._add_custom_service()
assert bd._per_person == 4700                       # 4200 + 500
bd.svc_rows[-1]["on"].set(False); bd._recalc()      # نلغيها لبقية الاختبار
assert bd._per_person == 4200
# التسعير + السفر/الإقامة من البرنامج + الرقم المرجعي التلقائي لكل معتمر
for nm in ("محمد", "أحمد", "سالم"):
    r = PassportData(full_name_ar=nm)
    bd._apply_booking(r)
    assert r.program_value == "4200" and r.room_type == "ثلاثي"    # 4000 + 200
    assert r.room_value == "4000"                                   # الأساس
    assert any(s["name"] == "تأمين طبّي" for s in r.umrah_services)  # خدمة مسعّرة
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
    "serial", "full_name_ar", "family_number", "passport_number", "expiry_date",
    "nationality_ar", "program", "hotel", "room_type", "airline",
    "program_value", "paid_amount", "remaining"]
# الجنسية قبل البرنامج، ورقم العائلة مذكور
_keys = [k for k, _l in umrah.REPORT_COLUMNS]
assert _keys.index("nationality_ar") < _keys.index("program")
assert "family_number" in _keys
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
_ncols = len(umrah.REPORT_COLUMNS)
assert [ws.cell(row=2, column=c).value for c in range(1, _ncols + 1)] == \
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
assert umrah.auto_assign_rooms(rr, "makkah_room") == (3, 0)  # 3 ثنائي→غرفتان + مفرد
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

print("\n=== سعر الطفل + خدمات المعتمر + المواصلات والطيران ===")
app_mode.set_mode("umrah")
# سعر الطفل (بدون سرير) ضمن أنواع الغرف، بلا سعة
assert ("price_child", "طفل (بدون سرير)", 0) in umrah.ROOM_TYPES
assert umrah.room_capacity_of("طفل (بدون سرير)") == 0
kids = [PassportData(room_type="طفل (بدون سرير)"), PassportData(room_type="ثنائي"),
        PassportData(room_type="ثنائي")]
umrah.auto_assign_rooms(kids, "makkah_room")
assert kids[0].makkah_room == "" and kids[1].makkah_room     # الطفل بلا غرفة
# المركبات: فورد ≤ شخصين، جيمس حتى ٦ — 8 أشخاص = جيمس(٦) + فورد(٢)
vv = [PassportData() for _ in range(8)]
assert umrah.auto_assign_vehicles(vv) == 2
assert vv[0].vehicle == "جيمس 1" and vv[7].vehicle == "فورد 2"
two = [PassportData(), PassportData()]
assert umrah.auto_assign_vehicles(two) == 1 and two[0].vehicle.startswith("فورد")
# خدمات المعتمر في نافذة التعديل: القيمة = الأساس + الخدمات
import hajj_app.gui as _g
r4 = tk.Tk(); r4.withdraw()
trip4 = umrah.UmrahTrip(code="U1", services=[{"name": "تأمين طبّي", "price": "200"},
                                             {"name": "المطوّف", "price": "150"}])
rec4 = PassportData(full_name_ar="سعيد", room_value="4000", program_value="4000")
d4 = _g.EditDialog(r4, rec4, lambda _r: None, umrah=True, trip=trip4)
d4._svc_widgets["تأمين طبّي"][0].set(True)
d4._recalc_services()
assert d4.vars["program_value"].get() == "4,200"            # 4000 + 200 حيّاً
d4._save()
assert rec4.program_value == "4,200" and rec4.room_value == "4,000"
assert len(rec4.umrah_services) == 1
r4.destroy()
# كشوف PDF: المواصلات والطيران
from hajj_app.pdf_io import export_umrah_transport_pdf, export_airline_pdf
tr = [PassportData(full_name_ar=f"م{i}", passport_number=f"P{i}", vehicle="جيمس 1")
      for i in range(3)]
pt = WORK / "trans.pdf"
export_umrah_transport_pdf(tr, pt, program_name="U1 — رمضان")
assert pt.read_bytes()[:5] == b"%PDF-" and pt.stat().st_size > 2500
pf = WORK / "flight.pdf"
export_airline_pdf(tr, pf, title="Flight Manifest — U1")
assert pf.read_bytes()[:5] == b"%PDF-"
# نافذة المواصلات: توزيع تلقائي
import hajj_app.umrah_gui as _ug
r5 = tk.Tk(); r5.withdraw()
app5 = _ug.UmrahApp(r5, session=None)
t5 = umrah.UmrahTrip(code="U1", name="رمضان")
app5.trips.append(t5)
app5.records.extend([PassportData(full_name_ar=f"س{i}", trip="U1") for i in range(4)])
vw = _ug.TransportWindow(app5, t5)
vw._auto()
assert all(r.vehicle for r in umrah.trip_pilgrims(app5.records, "U1"))
r5.destroy()
print("  OK: سعر الطفل + خدمات المعتمر المسعّرة + المواصلات (فورد/جيمس) + الطيران")

print("\n=== الرضيع + PNR + سعة الغرف + كشف المواصلات بالفندق ===")
# الرضيع ضمن أنواع الغرف بلا سعة
assert ("price_infant", "رضيع", 0) in umrah.ROOM_TYPES
assert umrah.room_capacity_of("رضيع") == 0
# PNR الطيران يُورَّث للمعتمر من البرنامج
tp = umrah.UmrahTrip(code="U1", flight_pnr="ABC123", makkah_hotel="كونراد")
rp = PassportData()
umrah.apply_trip_to_record(tp, rp)
assert rp.pnr == "ABC123"
# سعة الغرف: التوزيع يتجاوز عدد الغرف المتاحة → تنبيه (n > available)
r6 = tk.Tk(); r6.withdraw()
app6 = _ug.UmrahApp(r6, session=None)
t6 = umrah.UmrahTrip(code="RM", name="رمضان", makkah_hotel="كونراد",
                     makkah_rooms="1", madinah_hotel="دار التقوى")
app6.trips.append(t6)
app6.records.extend([PassportData(full_name_ar=f"م{i}", room_type="مفرد",
                                  trip="RM") for i in range(3)])
rw6 = _ug.RoomingWindow(app6, t6)
assert rw6._available("makkah") == 1
# مع تحديد السعة: لا يُتجاوز عدد الغرف؛ يبقى فائض بلا غرفة
n_rooms, overflow = umrah.auto_assign_rooms(
    umrah.trip_pilgrims(app6.records, "RM"), "makkah_room", max_rooms=1)
assert n_rooms == 1 and overflow == 2       # غرفة واحدة فقط، واثنان بلا غرفة
r6.destroy()
# كشف المواصلات: يعرض الفندق ويوضّح الاشتراك (أكثر من راكب)
from hajj_app.pdf_io import export_umrah_transport_pdf
shared = [PassportData(full_name_ar=f"س{i}", passport_number=f"P{i}",
                       hotel="كونراد", vehicle="جيمس 1") for i in range(3)]
pv6 = WORK / "trans2.pdf"
export_umrah_transport_pdf(shared, pv6, program_name="U1", transport_pnr="TR9")
assert pv6.read_bytes()[:5] == b"%PDF-" and pv6.stat().st_size > 2500
print("  OK: الرضيع + توريث PNR + تنبيه سعة الغرف + كشف مواصلات بالفندق")

print("\n=== رابط الدفع + بذر رقم الغرفة + المالية والبطاقات ===")
app_mode.set_mode("umrah")
# «رابط دفع» ضمن طرق الدفع
import hajj_app.gui as _g2
assert "رابط دفع" in _g2.EditDialog.CHOICE_FIELDS["payment_method"]
# التسكين يأخذ رقم الغرفة من «الإقامة والحجز» إن وُجد
r7 = tk.Tk(); r7.withdraw()
app7 = _ug.UmrahApp(r7, session=None)
t7 = umrah.UmrahTrip(code="SD", name="رمضان", makkah_hotel="كونراد")
app7.trips.append(t7)
app7.records.append(PassportData(full_name_ar="سعيد", room_number="512", trip="SD"))
_ug.RoomingWindow(app7, t7)
rec7 = umrah.trip_pilgrims(app7.records, "SD")[0]
assert rec7.makkah_room == "512" and rec7.madinah_room == "512"   # مأخوذ تلقائياً
r7.destroy()
# الملخّص المالي + بطاقات العمرة PDF
from hajj_app.pdf_io import export_umrah_finance_pdf, export_umrah_cards_pdf
fr = [PassportData(full_name_ar=f"م{i}", passport_number=f"A{i}",
                   nationality_ar="الإمارات", hotel="كونراد", room_type="ثنائي",
                   airline="السعودية", pnr="P1", reference_number=f"U1-00{i}",
                   program_value="5000", paid_amount=str(2000 * (i % 3)),
                   payment_method="رابط دفع") for i in range(1, 5)]
pf = WORK / "fin.pdf"
export_umrah_finance_pdf(fr, pf, program_name="U1 — رمضان")
assert pf.read_bytes()[:5] == b"%PDF-" and pf.stat().st_size > 3000
pc = WORK / "cards.pdf"
export_umrah_cards_pdf(fr, pc, program_name="U1 — رمضان",
                       emergency_uae="+971500000000", emergency_ksa="+966500000000")
assert pc.read_bytes()[:5] == b"%PDF-" and pc.stat().st_size > 3000
# تنبيه صلاحية الجواز أقل من ٦ أشهر من تاريخ السفر
assert umrah.passport_expiry_soon(
    PassportData(expiry_date="2026-05-01"), "2026-03-01") is True
assert umrah.passport_expiry_soon(
    PassportData(expiry_date="2027-01-01"), "2026-03-01") is False
print("  OK: رابط الدفع + بذر رقم الغرفة + الملخّص المالي + البطاقات + تنبيه الجواز")

app_mode.set_mode("hajj")
print("\n*** UMRAH TESTS PASSED ***")

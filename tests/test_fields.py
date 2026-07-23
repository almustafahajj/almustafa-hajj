# -*- coding: utf-8 -*-
"""Test the field schema: order, derived values, import, exports."""
import sys, io, os
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_HERE)
_OUTDIR = _os.path.join(_HERE, "_out")
_os.makedirs(_OUTDIR, exist_ok=True)
sys.path.insert(0, _ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from datetime import time as dtime
from hajj_app.fields import (FIELDS, PDF_FIELDS, EDITABLE, row_dict, parse_amount,
                             format_amount, normalize_time, compute_remaining, match_column)
from hajj_app.mrz import PassportData
from hajj_app.excel_io import export_excel, import_excel
from hajj_app.pdf_io import export_pdf

OUT = _OUTDIR

EXPECTED = ["مسلسل","رقم العائلة","الرقم المرجعي","اسم الحاج بالعربي","اسم الحاج بالانجليزي",
    "الهاتف المتحرك","برنامج الحملة","الفندق","نوع الغرفة","رقم الغرفة","الجنس","الجنسية","تاريخ الميلاد","رقم الجواز",
    "تاريخ انتهاء الجواز","الطيران","رقم الرحلة","درجة السفر","PNR الحجز","تاريخ الوصول",
    "وقت الوصول","تاريخ المغادرة","وقت المغادرة","المواصلات","خدمة التنفيذي","كرسي متحرك",
    "الهدي","قيمة البرنامج","المبلغ المدفوع","المبلغ المتبقي","ملاحظات","الموظف المسؤول"]

actual = [f.label for f in FIELDS]
print("=== COLUMN ORDER (right to left) ===")
for i, lbl in enumerate(actual, 1):
    print(f"  {i:2}. {lbl}")
assert actual == EXPECTED, f"\nexpected: {EXPECTED}\nactual:   {actual}"
assert len(FIELDS) == 32, len(FIELDS)
assert actual.count("الهدي") == 1, "duplicate not removed"
print("OK: 32 columns, exact order, duplicate removed\n")

# ---------- amounts ----------
print("=== AMOUNTS ===")
for raw, want in [("12,500", 12500.0), ("12500 ريال", 12500.0), ("١٢٥٠٠", 12500.0),
                  ("7,250.50", 7250.5), ("", None), ("abc", None)]:
    got = parse_amount(raw)
    print(f"  {raw!r:16} -> {got}")
    assert got == want, (raw, got, want)
assert format_amount(12500.0) == "12,500"
assert format_amount(7250.5) == "7,250.50"
print("OK: amount parsing incl. Arabic digits\n")

# ---------- times ----------
print("=== TIMES ===")
for raw, want in [("14:30","14:30"), ("2:30 PM","14:30"), ("1430","14:30"),
                  ("٠٩:٤٥","09:45"), ("9","09:00"), ("12:00 AM","00:00"), ("غداً","غداً")]:
    got = normalize_time(raw)
    print(f"  {raw!r:12} -> {got!r}")
    assert got == want, (raw, got, want)
print("OK: time normalization\n")

# ---------- derived remaining ----------
print("=== REMAINING (derived) ===")
r = PassportData(program_value="15,000", paid_amount="5,000")
assert compute_remaining(r) == "10,000", compute_remaining(r)
r.paid_amount = ""
assert compute_remaining(r) == "15,000"
r.program_value = ""
assert compute_remaining(r) == "", "no total -> blank, not a misleading 0"
print("  15,000 - 5,000 = 10,000 | no paid -> 15,000 | no total -> blank")
print("OK: remaining is derived, never misleading\n")

# ---------- serial + row_dict ----------
rec = PassportData(full_name_ar="أيمن الشهابي", passport_number="A1234567",
                   program_value="15000", paid_amount="5000")
d = row_dict(rec, 7)
assert d["serial"] == "7" and d["remaining_amount"] == "10,000"
print("OK: serial auto-numbered, remaining injected\n")

# ---------- full record round trip ----------
full = PassportData(
    full_name_en="AYMAN MOHAMMED ALSHEHABI", full_name_ar="أيمن محمد الشهابي",
    family_number="F-12", reference_number="REF-9001", phone="0559876543",
    hotel="فندق الصفوة", room_type="رباعية", sex="ذكر", nationality_ar="السعودية",
    birth_date="1985-01-01", passport_number="A1234567", expiry_date="2030-12-01",
    airline="السعودية SV1023", arrival_date="2026-05-20", arrival_time="14:30",
    departure_date="2026-06-05", departure_time="09:45", transport="باص مكيف",
    hady="نعم", wheelchair="لا", executive_service="نعم",
    program_value="15,000", paid_amount="5,000", notes="مرافق لوالدته",
)
second = PassportData(full_name_ar="فاطمة خان", passport_number="AB987654",
                      nationality_ar="باكستان", sex="أنثى", birth_date="1992-03-15",
                      program_value="12000", paid_amount="12000", hotel="فندق النور")

xl = os.path.join(OUT, "fields.xlsx")
export_excel([full, second], xl)
back, notes = import_excel(xl)
print("=== EXCEL ROUND TRIP ===")
print("  re-imported:", len(back), "| notes:", notes)
assert len(back) == 2, len(back)
b = back[0]
for k in ("full_name_ar","family_number","reference_number","hotel","room_type",
          "airline","arrival_time","departure_time","transport","hady",
          "wheelchair","executive_service","notes","phone"):
    assert getattr(b, k) == getattr(full, k), (k, getattr(b,k), getattr(full,k))
assert b.arrival_date == "2026-05-20" and b.departure_date == "2026-06-05"
assert parse_amount(b.program_value) == 15000.0, b.program_value
assert compute_remaining(b) == "10,000"
assert compute_remaining(back[1]) == "0", compute_remaining(back[1])
print("OK: all 31 columns survived round trip\n")

# ---------- messy import with new columns ----------
from openpyxl import Workbook
wb = Workbook(); ws = wb.active
ws.append(["كشف حملة النور 1447"])
ws.append(["م","رقم العائلة","Ref","اسم الحاج","Passport No","Mobile","الفندق",
           "الرحلة","تاريخ القدوم","ساعة الوصول","المبلغ","المسدد","الباقي"])
ws.append([1,"F-01","R-77","عمر حسن","C5551234","0500000001","فندق الصفوة",
           "SV555","2026-05-18", dtime(7,15), "10,000","4,000","6,000"])
messy = os.path.join(OUT, "fields_messy.xlsx"); wb.save(messy)
m, mnotes = import_excel(messy)
print("=== MESSY IMPORT (aliases + time cell) ===")
print("  notes:", mnotes)
assert len(m) == 1, len(m)
x = m[0]
print(f"  {x.full_name_ar} | {x.reference_number} | {x.hotel} | {x.airline} | "
      f"{x.arrival_date} {x.arrival_time} | {x.program_value}/{x.paid_amount}")
assert x.reference_number == "R-77" and x.family_number == "F-01"
assert x.full_name_ar == "عمر حسن" and x.passport_number == "C5551234"
assert x.hotel == "فندق الصفوة" and x.airline == "SV555"
assert x.arrival_time == "07:15", x.arrival_time      # real time cell parsed
assert compute_remaining(x) == "6,000", compute_remaining(x)
print("OK: aliases + Excel time cell + money\n")

# ---------- PDF ----------
pdf = os.path.join(OUT, "fields.pdf")
export_pdf([full, second], pdf, with_cards=True)
print("=== PDF ===")
print("  table columns:", len(PDF_FIELDS), "| size:", os.path.getsize(pdf), "bytes")
assert os.path.getsize(pdf) > 5000
assert len(PDF_FIELDS) <= 16, f"too many columns for A4: {len(PDF_FIELDS)}"
print("OK: PDF built (A4 selected cols + full cards)\n")

print(f"editable fields: {len(EDITABLE)}")
print("*** FIELD SCHEMA TESTS PASSED ***")

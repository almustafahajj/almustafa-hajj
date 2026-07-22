# -*- coding: utf-8 -*-
"""Test MRZ parsing, excel round-trip, and PDF export."""
import sys, io, os
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_HERE)
_OUTDIR = _os.path.join(_HERE, "_out")
_os.makedirs(_OUTDIR, exist_ok=True)
sys.path.insert(0, _ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from hajj_app.mrz import parse_mrz, check_digit, parse_text
from hajj_app.excel_io import export_excel, import_excel
from hajj_app.pdf_io import export_pdf

OUT = _OUTDIR

# --- Build a VALID TD3 MRZ with correct check digits ---
def build(pnum, country, nat, birth, sex, expiry, personal=""):
    p9 = pnum.ljust(9, "<")
    per = personal.ljust(14, "<")
    l2 = (p9 + check_digit(p9) + nat + birth + check_digit(birth) + sex
          + expiry + check_digit(expiry) + per + check_digit(per))
    composite = l2[0:10] + l2[13:20] + l2[21:43]
    return l2 + check_digit(composite)

l1 = "P<SAUALSHEHABI<<AYMAN<MOHAMMED<<<<<<<<<<<<<<"
l2 = build("A1234567", "SAU", "SAU", "850101", "M", "301201")
print("line1 len:", len(l1), "| line2 len:", len(l2))
print("line2:", l2)

d = parse_mrz(l1, l2)
print("\n=== PARSED ===")
print("name_en :", d.full_name_en)
print("surname :", d.surname_en, "| given:", d.given_names_en)
print("passport:", d.passport_number)
print("nat     :", d.nationality, d.nationality_ar)
print("sex     :", d.sex)
print("expiry  :", d.expiry_date)
print("checksum_ok:", d.checksum_ok, "| warnings:", d.warnings)

assert d.checksum_ok, "CHECKSUM FAILED"
assert d.passport_number == "A1234567"
assert d.nationality == "SAU"
assert d.birth_date == "1985-01-01"
assert d.expiry_date == "2030-12-01"
assert d.sex == "ذكر"
assert d.surname_en == "ALSHEHABI"
assert d.given_names_en == "AYMAN MOHAMMED"
print("OK: MRZ parse + checksums")

# --- parse_text: find MRZ inside noisy OCR output ---
noisy = "PASSPORT\nKINGDOM OF SAUDI ARABIA\nsome junk 123\n" + l1 + "\n" + l2 + "\n"
d2 = parse_text(noisy)
assert d2.passport_number == "A1234567" and d2.checksum_ok
print("OK: MRZ located in noisy text")

# --- Second record: female, different country ---
l1b = "P<PAKKHAN<<FATIMA<BIBI<<<<<<<<<<<<<<<<<<<<<<"
l2b = build("AB987654", "PAK", "PAK", "920315", "F", "280630")
db = parse_mrz(l1b, l2b)
assert db.checksum_ok and db.sex == "أنثى" and db.nationality_ar == "باكستان"
db.full_name_ar = "فاطمة بيبي خان"
db.phone = "0501234567"
db.hotel = "فندق الصفوة"
d.full_name_ar = "أيمن محمد الشهابي"
d.phone = "0559876543"
d.hotel = "فندق الصفوة"
print("OK: second record")

# --- Excel export + re-import round trip ---
recs = [d, db]
xlsx = os.path.join(OUT, "test_out.xlsx")
export_excel(recs, xlsx)
print("\nExcel written:", os.path.getsize(xlsx), "bytes")

back, notes = import_excel(xlsx)
print("Re-imported:", len(back), "records | notes:", notes)
assert len(back) == 2, f"expected 2, got {len(back)}"
assert back[0].passport_number == "A1234567", back[0].passport_number
assert back[0].full_name_ar == "أيمن محمد الشهابي", back[0].full_name_ar
assert back[0].birth_date == "1985-01-01", back[0].birth_date
assert back[1].nationality_ar == "باكستان"
assert back[1].phone == "0501234567"
print("OK: Excel round-trip preserved all fields")

# --- Import an Excel with DIFFERENT/messy headers (real-world case) ---
from openpyxl import Workbook
wb = Workbook(); ws = wb.active
ws.append(["كشف حجاج حملة النور"])          # decorative title row
ws.append([])                                 # blank row
ws.append(["Name", "Passport No", "Nationality", "DOB", "Gender", "Mobile"])
ws.append(["OMAR HASSAN", "C5551234", "مصر", "1990-07-22", "ذكر", "01001112233"])
ws.append(["AISHA NOOR", "D7778888", "إندونيسيا", "15/03/1988", "أنثى", "08123456789"])
messy = os.path.join(OUT, "messy.xlsx"); wb.save(messy)

m, mnotes = import_excel(messy)
print("\nMessy import:", len(m), "records | notes:", mnotes)
assert len(m) == 2, f"expected 2, got {len(m)}"
assert m[0].full_name_en == "OMAR HASSAN"
assert m[0].passport_number == "C5551234"
assert m[1].birth_date == "1988-03-15", m[1].birth_date   # dd/mm/yyyy normalized

# --- PDF export ---
pdf = os.path.join(OUT, "test_out.pdf")
export_pdf(recs + m, pdf, with_cards=True)
size = os.path.getsize(pdf)
print("\nPDF written:", size, "bytes")
assert size > 3000, "PDF suspiciously small"
with open(pdf, "rb") as fh:
    head = fh.read(5)
assert head == b"%PDF-", head
print("OK: PDF generated with cards")

print("\n*** ALL CORE TESTS PASSED ***")

# -*- coding: utf-8 -*-
"""Render a synthetic passport page with a real MRZ, then OCR it back."""
import sys, io, os
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_HERE)
_OUTDIR = _os.path.join(_HERE, "_out")
_os.makedirs(_OUTDIR, exist_ok=True)
sys.path.insert(0, _ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from PIL import Image, ImageDraw, ImageFont
from hajj_app.mrz import check_digit
from hajj_app.ocr import extract_passport, configure_tesseract

OUT = _OUTDIR
print("tesseract:", configure_tesseract())

def build2(pnum, nat, birth, sex, expiry):
    p9 = pnum.ljust(9, "<"); per = "".ljust(14, "<")
    l2 = (p9 + check_digit(p9) + nat + birth + check_digit(birth) + sex
          + expiry + check_digit(expiry) + per + check_digit(per))
    return l2 + check_digit(l2[0:10] + l2[13:20] + l2[21:43])

L1 = "P<SAUALSHEHABI<<AYMAN<MOHAMMED<<<<<<<<<<<<<<"
L2 = build2("A1234567", "SAU", "850101", "M", "301201")

# Passport-page proportions: MRZ occupies the bottom strip
W, H = 1400, 980
img = Image.new("RGB", (W, H), "#F6F1E4")
d = ImageDraw.Draw(img)

# Fake upper page content so OCR must actually locate the MRZ strip
try:
    big = ImageFont.truetype("arialbd.ttf", 34)
    med = ImageFont.truetype("arial.ttf", 26)
except Exception:
    big = med = ImageFont.load_default()
d.text((60, 50), "PASSPORT", font=big, fill="#1a2a4a")
d.text((60, 110), "KINGDOM OF SAUDI ARABIA", font=med, fill="#1a2a4a")
for i, line in enumerate([
    "Type: P     Country Code: SAU", "Passport No: A1234567",
    "Surname: ALSHEHABI", "Given Names: AYMAN MOHAMMED",
    "Nationality: SAUDI ARABIAN", "Date of Birth: 01 JAN 1985",
    "Sex: M      Date of Expiry: 01 DEC 2030",
]):
    d.text((60, 190 + i * 46), line, font=med, fill="#222")
d.rectangle([980, 190, 1330, 640], outline="#999", width=2)
d.text((1060, 400), "PHOTO", font=med, fill="#999")

# MRZ strip: white background, monospace, evenly spaced glyphs
mrz_top = 790
d.rectangle([0, mrz_top - 20, W, H], fill="white")
mono = ImageFont.truetype("consola.ttf", 38)
char_w = 30
for row, line in enumerate((L1, L2)):
    y = mrz_top + 20 + row * 62
    for i, ch in enumerate(line):
        d.text((30 + i * char_w, y), ch, font=mono, fill="black")

path = os.path.join(OUT, "fake_passport.png")
img.save(path)
print("image:", path, os.path.getsize(path), "bytes")

print("\n--- running OCR ---")
rec = extract_passport(path)
print("name    :", rec.full_name_en)
print("passport:", rec.passport_number)
print("nat     :", rec.nationality, rec.nationality_ar)
print("sex     :", rec.sex)
print("expiry  :", rec.expiry_date)
print("checksum_ok:", rec.checksum_ok)
print("warnings:", rec.warnings)

errs = []
if rec.passport_number != "A1234567": errs.append(f"passport={rec.passport_number}")
if rec.birth_date != "1985-01-01":    errs.append(f"birth={rec.birth_date}")
if rec.expiry_date != "2030-12-01":   errs.append(f"expiry={rec.expiry_date}")
if rec.nationality != "SAU":          errs.append(f"nat={rec.nationality}")
if "ALSHEHABI" not in rec.full_name_en: errs.append(f"name={rec.full_name_en}")

if errs:
    print("\n*** OCR MISMATCH:", errs)
    sys.exit(1)
print("\n*** OCR TEST PASSED ***")

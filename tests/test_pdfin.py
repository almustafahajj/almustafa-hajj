# -*- coding: utf-8 -*-
"""Test PDF passport import: text-layer, scanned, multi-page, duplicates."""
import sys, io, os
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_HERE)
_OUTDIR = _os.path.join(_HERE, "_out")
_os.makedirs(_OUTDIR, exist_ok=True)
sys.path.insert(0, _ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import fitz
from PIL import Image, ImageDraw, ImageFont
from hajj_app.mrz import check_digit
from hajj_app.pdf_in import extract_from_pdf, PDFError
from hajj_app.mrz import MRZError

OUT = _OUTDIR

def mrz2(pnum, nat, birth, sex, expiry):
    p9 = pnum.ljust(9, "<"); per = "".ljust(14, "<")
    l2 = (p9 + check_digit(p9) + nat + birth + check_digit(birth) + sex
          + expiry + check_digit(expiry) + per + check_digit(per))
    return l2 + check_digit(l2[0:10] + l2[13:20] + l2[21:43])

PEOPLE = [
    ("ALSHEHABI", "AYMAN<MOHAMMED", "A1234567", "SAU", "850101", "M", "301201"),
    ("KHAN",      "FATIMA<BIBI",    "AB987654", "PAK", "920315", "F", "280630"),
    ("HASSAN",    "OMAR",           "C5551234", "EGY", "900722", "M", "290105"),
]
def lines(p):
    sur, giv, num, nat, b, s, e = p
    return f"P<{nat}{sur}<<{giv}".ljust(44, "<"), mrz2(num, nat, b, s, e)

# ---------- 1. TEXT-LAYER PDF (3 passports, one per page) ----------
doc = fitz.open()
for p in PEOPLE:
    l1, l2 = lines(p)
    page = doc.new_page(width=595, height=842)
    page.insert_text((60, 100), "PASSPORT", fontname="helv", fontsize=20)
    page.insert_text((60, 130), f"Passport No: {p[2]}", fontname="helv", fontsize=11)
    page.insert_text((40, 760), l1, fontname="cour", fontsize=11)
    page.insert_text((40, 782), l2, fontname="cour", fontsize=11)
text_pdf = os.path.join(OUT, "passports_text.pdf")
doc.save(text_pdf); doc.close()

recs, notes = extract_from_pdf(text_pdf)
print("=== TEXT-LAYER PDF ===")
for r in recs:
    print(f"  {r.passport_number} | {r.full_name_en} | {r.nationality_ar} | {r.birth_date} | ok={r.checksum_ok}")
print("notes:", notes)
assert len(recs) == 3, f"expected 3, got {len(recs)}"
nums = [r.passport_number for r in recs]
assert nums == ["A1234567", "AB987654", "C5551234"], nums
assert all(r.checksum_ok for r in recs), "checksums must pass on text layer"
assert recs[1].nationality_ar == "باكستان"
assert recs[2].birth_date == "1990-07-22"
assert "صفحة 1" in recs[0].source_file, recs[0].source_file
print("OK: text-layer extraction, 3/3 exact\n")

# ---------- 2. SCANNED (image-only) PDF ----------
def passport_png(p, path):
    l1, l2 = lines(p)
    W, H = 1400, 980
    img = Image.new("RGB", (W, H), "#F6F1E4"); d = ImageDraw.Draw(img)
    med = ImageFont.truetype("arial.ttf", 26)
    d.text((60, 60), "PASSPORT", font=ImageFont.truetype("arialbd.ttf", 34), fill="#1a2a4a")
    d.text((60, 200), f"Passport No: {p[2]}", font=med, fill="#222")
    d.rectangle([0, 770, W, H], fill="white")
    mono = ImageFont.truetype("consola.ttf", 38)
    for row, line in enumerate((l1, l2)):
        for i, ch in enumerate(line):
            d.text((30 + i * 30, 810 + row * 62), ch, font=mono, fill="black")
    img.save(path); return path

doc = fitz.open()
for i, p in enumerate(PEOPLE[:2]):
    png = passport_png(p, os.path.join(OUT, f"scan_{i}.png"))
    page = doc.new_page(width=842, height=595)
    page.insert_image(fitz.Rect(0, 0, 842, 595), filename=png)
scan_pdf = os.path.join(OUT, "passports_scan.pdf")
doc.save(scan_pdf); doc.close()

# confirm it truly has no text layer
d2 = fitz.open(scan_pdf)
assert not d2[0].get_text("text").strip(), "test PDF unexpectedly has text"
d2.close()
print("=== SCANNED PDF (no text layer) ===")
recs2, notes2 = extract_from_pdf(scan_pdf)
for r in recs2:
    print(f"  {r.passport_number} | {r.nationality} | {r.birth_date} | {r.expiry_date} | ok={r.checksum_ok}")
print("notes:", notes2)
assert len(recs2) == 2, f"expected 2, got {len(recs2)}"
assert recs2[0].passport_number == "A1234567", recs2[0].passport_number
assert recs2[0].birth_date == "1985-01-01"
assert recs2[1].passport_number == "AB987654", recs2[1].passport_number
assert recs2[1].nationality == "PAK"
print("OK: scanned PDF fell back to OCR, 2/2 exact\n")

# ---------- 3. DUPLICATE passport across pages ----------
doc = fitz.open()
for _ in range(3):                       # same passport 3 times
    l1, l2 = lines(PEOPLE[0])
    page = doc.new_page(width=595, height=842)
    page.insert_text((40, 760), l1, fontname="cour", fontsize=11)
    page.insert_text((40, 782), l2, fontname="cour", fontsize=11)
dup_pdf = os.path.join(OUT, "dup.pdf"); doc.save(dup_pdf); doc.close()
recs3, _ = extract_from_pdf(dup_pdf)
print("=== DUPLICATES ===")
print("  3 identical pages ->", len(recs3), "record(s)")
assert len(recs3) == 1, f"dedupe failed: {len(recs3)}"
print("OK: deduped to 1\n")

# ---------- 4. PROGRESS callback ----------
seen = []
extract_from_pdf(text_pdf, progress=lambda p, t: seen.append((p, t)))
print("=== PROGRESS ===")
print("  callback fired:", seen)
assert seen == [(1, 3), (2, 3), (3, 3)], seen
print("OK: progress reporting\n")

# ---------- 5. ERROR CASES ----------
print("=== ERROR HANDLING ===")
blank = fitz.open(); blank.new_page(); blank.new_page()
blank_pdf = os.path.join(OUT, "blank.pdf"); blank.save(blank_pdf); blank.close()
try:
    extract_from_pdf(blank_pdf); print("  FAIL: blank PDF should raise"); sys.exit(1)
except MRZError as e:
    print("  blank PDF ->", str(e).split("\n")[0])

bad = os.path.join(OUT, "notapdf.pdf")
open(bad, "wb").write(b"this is not a pdf at all")
try:
    extract_from_pdf(bad); print("  FAIL: corrupt PDF should raise"); sys.exit(1)
except PDFError as e:
    print("  corrupt PDF ->", str(e).split("\n")[0][:60])

enc = fitz.open(); enc.new_page()
enc_pdf = os.path.join(OUT, "enc.pdf")
enc.save(enc_pdf, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u"); enc.close()
try:
    extract_from_pdf(enc_pdf); print("  FAIL: encrypted PDF should raise"); sys.exit(1)
except PDFError as e:
    print("  encrypted PDF ->", str(e))
print("OK: all error cases handled\n")

print("*** PDF IMPORT TESTS PASSED ***")

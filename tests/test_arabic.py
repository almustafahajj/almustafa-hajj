# -*- coding: utf-8 -*-
"""Arabic name extraction: text layer, OCR, and label rejection."""
import sys, io, os
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_HERE)
_OUTDIR = _os.path.join(_HERE, "_out")
_os.makedirs(_OUTDIR, exist_ok=True)
sys.path.insert(0, _ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import fitz, numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display
from hajj_app.arabic_ocr import (best_arabic_name_in_text, extract_arabic_name,
                                 arabic_supported, _score)
from hajj_app.mrz import check_digit
from hajj_app.pdf_in import extract_from_pdf
from hajj_app.ocr import extract_passport

OUT = _OUTDIR
print("arabic supported:", arabic_supported())
assert arabic_supported(), "ara.traineddata missing"

# ---------- 1. picking the name out of passport text, rejecting labels ----------
print("\n=== NAME PICKING (labels must be rejected) ===")
page_text = """المملكة العربية السعودية
جواز سفر
الاسم
أيمن محمد الشهابي
الجنسية
سعودي
تاريخ الميلاد
1985-01-01
رقم الجواز
A1234567
وزارة الداخلية
"""
got = best_arabic_name_in_text(page_text)
print("  picked:", repr(got))
assert got == "أيمن محمد الشهابي", got
for label in ["المملكة العربية السعودية", "وزارة الداخلية", "جواز سفر",
              "تاريخ الميلاد", "الجنسية"]:
    assert _score(label) == 0.0, f"label not rejected: {label}"
print("  OK: name picked, all boilerplate labels scored 0")

# a page with no personal name must yield nothing, not a label
only_labels = "المملكة العربية السعودية\nجواز سفر\nوزارة الداخلية\nالجنسية\n"
assert best_arabic_name_in_text(only_labels) == "", best_arabic_name_in_text(only_labels)
print("  OK: no name -> empty, never a fallback label")

# ---------- 2. text-layer PDF end to end ----------
def mrz2(pnum, nat, birth, sex, expiry):
    p9 = pnum.ljust(9, "<"); per = "".ljust(14, "<")
    l2 = (p9 + check_digit(p9) + nat + birth + check_digit(birth) + sex
          + expiry + check_digit(expiry) + per + check_digit(per))
    return l2 + check_digit(l2[0:10] + l2[13:20] + l2[21:43])

FONT = r"C:\Windows\Fonts\arial.ttf"
def shape(t): return get_display(arabic_reshaper.reshape(t))

doc = fitz.open()
page = doc.new_page(width=595, height=842)
page.insert_font(fontname="ar", fontfile=FONT)
page.insert_text((60, 80),  "PASSPORT / جواز سفر"[:20], fontname="helv", fontsize=14)
for y, t in [(120,"المملكة العربية السعودية"), (150,"الاسم"),
             (180,"أيمن محمد الشهابي"), (210,"الجنسية"), (240,"سعودي")]:
    page.insert_text((300, y), shape(t), fontname="ar", fontsize=13)
page.insert_text((40, 760), "P<SAUALSHEHABI<<AYMAN<MOHAMMED".ljust(44,"<"),
                 fontname="cour", fontsize=11)
page.insert_text((40, 782), mrz2("A1234567","SAU","850101","M","301201"),
                 fontname="cour", fontsize=11)
tpdf = os.path.join(OUT, "ar_text.pdf"); doc.save(tpdf); doc.close()

recs, notes = extract_from_pdf(tpdf)
r = recs[0]
print("\n=== TEXT-LAYER PDF ===")
print(f"  ar: {r.full_name_ar!r}")
print(f"  en: {r.full_name_en!r} | {r.passport_number} | warnings={r.warnings}")
assert r.full_name_ar == "أيمن محمد الشهابي", r.full_name_ar
assert r.passport_number == "A1234567"
# text layer is reliable -> no OCR warning for the Arabic name
assert not any("مقروء ضوئياً" in w for w in r.warnings), r.warnings
print("  OK: Arabic from text layer, no false OCR warning")

# ---------- 3. real Arabic OCR on a rendered passport image ----------
print("\n=== ARABIC OCR (scanned image) ===")
W, H = 1600, 1100
img = Image.new("RGB", (W, H), "#F7F3E8"); d = ImageDraw.Draw(img)
big = ImageFont.truetype(FONT, 44); med = ImageFont.truetype(FONT, 34)
d.text((W-60, 60),  shape("المملكة العربية السعودية"), font=med, fill="#1a2a4a", anchor="ra")
d.text((W-60, 120), shape("جواز سفر"), font=med, fill="#1a2a4a", anchor="ra")
d.text((W-60, 230), shape("الاسم"), font=med, fill="#555", anchor="ra")
d.text((W-60, 285), shape("أيمن محمد الشهابي"), font=big, fill="#111", anchor="ra")
d.text((W-60, 380), shape("الجنسية"), font=med, fill="#555", anchor="ra")
d.text((W-60, 435), shape("سعودي"), font=med, fill="#111", anchor="ra")
d.text((60, 285), "AYMAN MOHAMMED ALSHEHABI", font=med, fill="#111")
d.rectangle([0, 880, W, H], fill="white")
mono = ImageFont.truetype(r"C:\Windows\Fonts\consola.ttf", 40)
for row, line in enumerate(["P<SAUALSHEHABI<<AYMAN<MOHAMMED".ljust(44,"<"),
                            mrz2("A1234567","SAU","850101","M","301201")]):
    for i, ch in enumerate(line):
        d.text((35 + i*33, 920 + row*66), ch, font=mono, fill="black")
ipath = os.path.join(OUT, "ar_passport.png"); img.save(ipath)

arr = cv2.imdecode(np.fromfile(ipath, dtype=np.uint8), cv2.IMREAD_COLOR)
name = extract_arabic_name(arr)
print("  OCR read:", repr(name))
# consensus must strip the OCR noise bled in from the Latin name
assert name == "أيمن محمد الشهابي", f"Arabic OCR: {name!r}"
print("  OK: Arabic name read exactly, noise voted out")

# consensus unit check: stable words survive, unstable ones don't
from hajj_app.arabic_ocr import _consensus
votes = ["أيمن محمد الشهابي اقمناء", "أيمن محمد الشهابي لااخايا لاخ",
         "أيمن محمد الشهابي", "أيمن محمد الشهابي ماعانا"]
assert _consensus(votes) == "أيمن محمد الشهابي", _consensus(votes)
assert _consensus([]) == ""
assert _consensus(["اقمناء ناكام"]) == "اقمناء ناكام"   # single reading: no vote possible
print("  OK: _consensus keeps stable words, drops unstable")

rec = extract_passport(ipath)
print(f"  full record -> ar={rec.full_name_ar!r} en={rec.full_name_en!r} "
      f"pass={rec.passport_number}")
assert "أيمن" in rec.full_name_ar, rec.full_name_ar
assert rec.passport_number == "A1234567"
assert any("مقروء ضوئياً" in w for w in rec.warnings), rec.warnings
print("  OK: image path fills Arabic + flags it for review")

print("\n*** ARABIC NAME TESTS PASSED ***")

# -*- coding: utf-8 -*-
"""Optional-data field cleanup, using the real UAE passport as the case."""
import sys, io
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_HERE)
_OUTDIR = _os.path.join(_HERE, "_out")
_os.makedirs(_OUTDIR, exist_ok=True)
sys.path.insert(0, _ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from hajj_app.mrz import parse_mrz, check_digit, _clean_optional

print("=== _clean_optional ===")
cases = [
    ("KKKK<<<<<<<<<<",  "",         "OCR read filler as K (the real bug)"),
    ("<<<<<<<<<<<<<<",  "",         "genuine empty filler"),
    ("CCC<<<<<<<<<<<",  "",         "filler read as C"),
    ("1234567890<<<<",  "1234784567890".replace("784",""), "real numeric ID kept"),
    ("784199012345<<",  "784199012345", "UAE Emirates ID kept"),
    ("000<<<<<<<<<<<",  "000",      "repeated DIGITS are legitimate"),
    ("AB12345<<<<<<<",  "AB12345",  "alphanumeric ID kept"),
    ("XY<<<<<<<<<<<<",  "XY",       "two letters: too short to judge, kept"),
]
for raw, want, why in cases:
    got = _clean_optional(raw)
    status = "OK " if got == want else "FAIL"
    print(f"  {status} {raw!r:18} -> {got!r:16} ({why})")
    assert got == want, (raw, got, want)

# ---- rebuild the user's actual passport MRZ ----
print("\n=== REAL PASSPORT (AA0693247) ===")
p9 = "AA0693247"
personal_ocr = "KKKK<<<<<<<<<<"          # what OCR produced
l2 = (p9 + check_digit(p9) + "ARE" + "660225" + check_digit("660225") + "M"
      + "340928" + check_digit("340928") + personal_ocr + "0")
l2 = l2 + check_digit(l2[0:10] + l2[13:20] + l2[21:43])
l1 = "P<AREALSHAMSI<<SAEED<RASHED<SAEED<MUBARAK<<<"

d = parse_mrz(l1, l2)
print("  name    :", d.full_name_en)
print("  passport:", d.passport_number)
print("  nat     :", d.nationality, d.nationality_ar)
print("  birth   :", d.birth_date, "| expiry:", d.expiry_date)
print("  personal:", repr(d.personal_number))
assert d.personal_number == "", f"KKKK leaked: {d.personal_number!r}"
assert d.passport_number == "AA0693247"
assert d.nationality_ar == "الإمارات"
assert d.birth_date == "1966-02-25" and d.expiry_date == "2034-09-28"
assert d.full_name_en == "SAEED RASHED SAEED MUBARAK ALSHAMSI", d.full_name_en
print("  OK: KKKK removed, every verified field intact")

print("\n*** OPTIONAL FIELD TESTS PASSED ***")

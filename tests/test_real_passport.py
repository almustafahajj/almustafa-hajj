# -*- coding: utf-8 -*-
"""End-to-end against the user's real UAE passport scan."""
import sys, io, cv2, numpy as np
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_HERE)
_OUTDIR = _os.path.join(_HERE, "_out")
_os.makedirs(_OUTDIR, exist_ok=True)
sys.path.insert(0, _ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from hajj_app.arabic_ocr import extract_arabic_name, _consensus
from hajj_app.ocr import extract_passport

# جواز حقيقي خارج المشروع — لا يُنسخ إلى المستودع حفاظاً على الخصوصية.
# يمكن تجاوز المسار بمتغيّر البيئة HAJJ_REAL_PASSPORT.
P = _os.environ.get("HAJJ_REAL_PASSPORT") or _os.path.join(
    _os.path.expanduser("~"),
    "OneDrive - Nirvana Travel & Tourism", "MHU", "Almustafa Hajj & Umrah",
    "Umrah Packages", "Hajj 2026", "جوازات الحجاج", "New folder",
    "سعيد راشد سعيد مبارك الشامسى.jpg",
)
EXPECTED_AR = "سعيد راشد سعيد مبارك الشامسى"

# --- the consensus bug, isolated: garbage outscores the name ---
print("=== CONSENSUS REGRESSION ===")
votes = [
    "سعيد راشد سعيد مبارك الشامسى",
    "سعيد راشد سعيد مبارك الشامسى",
    "ارلذم باكام امجادر نايا مقطع",     # noise, scores 7.5 > name's 7.4
    "سعيد راشد سعيد مبارك الشامسى",
]
got = _consensus(votes)
print("  votes incl. higher-scoring noise ->", repr(got))
assert got == EXPECTED_AR, got
print("  OK: stable name wins over higher-scoring unstable noise")

# --- the real image ---
print("\n=== REAL PASSPORT IMAGE ===")
if not _os.path.exists(P):
    print(f"  SKIP: الصورة غير موجودة على هذا الجهاز\n  {P}")
    print("  (حدّد مسارها بمتغيّر البيئة HAJJ_REAL_PASSPORT)")
    raise SystemExit(0)
img = cv2.imdecode(np.fromfile(P, dtype=np.uint8), cv2.IMREAD_COLOR)
print(f"  size: {img.shape[1]} x {img.shape[0]}")
name = extract_arabic_name(img)
print("  arabic name:", repr(name))
assert name == EXPECTED_AR, f"got {name!r}, want {EXPECTED_AR!r}"
print("  OK: exact match")

print("\n=== FULL RECORD ===")
rec = extract_passport(P)
for label, value in [
    ("الاسم بالعربي", rec.full_name_ar), ("الاسم بالانجليزي", rec.full_name_en),
    ("رقم الجواز", rec.passport_number), ("الجنسية", rec.nationality_ar),
    ("الجنس", rec.sex), ("تاريخ الميلاد", rec.birth_date),
    ("انتهاء الجواز", rec.expiry_date), ("الرقم الشخصي", rec.personal_number),
]:
    print(f"  {label:22} = {value!r}")
print("  checksum_ok:", rec.checksum_ok)
print("  warnings   :", rec.warnings)

assert rec.full_name_ar == EXPECTED_AR, rec.full_name_ar
assert rec.full_name_en == "SAEED RASHED SAEED MUBARAK ALSHAMSI", rec.full_name_en
assert rec.passport_number == "AA0693247", rec.passport_number
assert rec.nationality_ar == "الإمارات"
assert rec.sex == "ذكر"
assert rec.birth_date == "1966-02-25", rec.birth_date
assert rec.expiry_date == "2034-09-28", rec.expiry_date
assert rec.personal_number == "", f"KKKK leaked: {rec.personal_number!r}"
# the verified identity fields (passport/birth/expiry) must be trusted
assert rec.checksum_ok, "core field check digits should pass"
# composite covers the filler region too, so it may still flag for review
assert any("الجنسية والجنس" in w for w in rec.warnings), rec.warnings
assert not any("قراءة غير مؤكدة" in w for w in rec.warnings), \
    "must not cry 'unreliable' when every field check digit passed"
print("\n*** REAL PASSPORT: ALL FIELDS CORRECT ***")

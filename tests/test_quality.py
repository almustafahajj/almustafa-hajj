# -*- coding: utf-8 -*-
"""اختبار فحوص جودة الكشف: تكرار الجواز، صلاحيته، ونقص البيانات."""
import sys, io
import os as _os
from datetime import date
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from hajj_app.quality import (
    KIND_DUPLICATE, KIND_MISSING, KIND_PASSPORT, MIN_PASSPORT_MONTHS,
    add_months, check_records, duplicate_groups, missing_critical,
    passport_issue, summary_text, travel_date,
)
from hajj_app.mrz import PassportData


def rec(**kw):
    return PassportData(**kw)


TODAY = date(2026, 7, 1)


print("=== add_months مع ضبط نهاية الشهر ===")
assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
assert add_months(date(2026, 12, 15), 1) == date(2027, 1, 15)
assert add_months(date(2026, 7, 1), 6) == date(2027, 1, 1)
print("  OK: 31 يناير +شهر = 28 فبراير، وتجاوز السنة")

print("\n=== صلاحية الجواز مقابل تاريخ السفر ===")
# منتهٍ
assert passport_issue(rec(expiry_date="2026-06-01"), TODAY) == "الجواز منتهٍ"
# صالح طويلاً
assert passport_issue(rec(expiry_date="2030-01-01"), TODAY) is None
# أقل من 6 أشهر من السفر (سفر 2026-08-01، انتهاء 2026-11-01 < 2027-02-01)
r = rec(expiry_date="2026-11-01", departure_date="2026-08-01")
assert passport_issue(r, TODAY) and "6 أشهر" in passport_issue(r, TODAY)
# نفس الجواز لكن صلاحيته 8 أشهر من السفر -> سليم
assert passport_issue(rec(expiry_date="2027-03-01", departure_date="2026-08-01"), TODAY) is None
# بلا تاريخ انتهاء -> لا مشكلة صلاحية (يُعالَج ضمن النواقص)
assert passport_issue(rec(expiry_date=""), TODAY) is None
# تاريخ السفر المرجعي: المغادرة تتقدّم على الوصول
assert travel_date(rec(arrival_date="2026-08-01", departure_date="2026-08-20")) == date(2026, 8, 20)
print("  OK: منتهٍ، أقل من 6 أشهر، سليم، وبلا تاريخ")

print("\n=== المرجع: تاريخ سفر برنامج الحاج لا تاريخ اليوم ===")
from hajj_app.quality import program_travel_date
PDATES = {"البرنامج الأول": date(2026, 8, 1)}
# حاج على «البرنامج الأول» بلا تاريخ سفر مفرد، وجوازه ينتهي 2026-12-15
onprog = rec(expiry_date="2026-12-15", program="البرنامج الأول")
assert program_travel_date(onprog, PDATES) == date(2026, 8, 1)
# من سفر البرنامج (2026-08-01 + 6 = 2027-02-01) -> ناقص الصلاحية
assert passport_issue(onprog, TODAY, PDATES) is not None
# جواز طويل الصلاحية على نفس البرنامج -> سليم
long_pp = rec(expiry_date="2027-06-01", program="البرنامج الأول")
assert passport_issue(long_pp, TODAY, PDATES) is None
# حاج بلا برنامج ولا تاريخ سفر -> يُحسب من اليوم فقط
assert program_travel_date(rec(program=""), PDATES) is None
# تاريخ السفر المفرد في السجل يتقدّم على البرنامج
r_own = rec(expiry_date="2027-06-01", program="البرنامج الأول",
            departure_date="2027-05-01")   # +6 = 2027-11-01 > الانتهاء -> ناقص
assert passport_issue(r_own, TODAY, PDATES) is not None
# يُستخدم في الفحص الكامل أيضاً
rep = check_records([rec(expiry_date="2026-12-15", full_name_ar="أ",
                         passport_number="X1", birth_date="1990-01-01",
                         program="البرنامج الأول")],
                    today=TODAY, program_dates=PDATES)
assert any("تاريخ السفر" in i.detail for i in rep.issues), rep.issues
print("  OK: مرجع سفر البرنامج يُستخدم لكل حاج")

print("\n=== كشف تكرار رقم الجواز ===")
recs = [rec(passport_number="A1", full_name_ar="أ"),
        rec(passport_number="a1", full_name_ar="ب"),   # نفس الجواز بأحرف صغيرة
        rec(passport_number="A2", full_name_ar="ج"),
        rec(passport_number="", full_name_ar="د")]      # فارغ لا يُحسب تكراراً
dups = duplicate_groups(recs)
assert set(dups) == {"A1"} and dups["A1"] == [0, 1], dups
print(f"  OK: A1 مكرّر في السجلين 0 و1 (غير حسّاس لحالة الأحرف)")

print("\n=== نقص البيانات الحرجة ===")
assert missing_critical(rec()) == ["اسم الحاج", "رقم الجواز", "تاريخ الميلاد"]
assert missing_critical(rec(full_name_en="OMAR", passport_number="X", birth_date="1990-01-01")) == []
assert missing_critical(rec(full_name_ar="عمر", passport_number="X1")) == ["تاريخ الميلاد"]
print("  OK: يرصد الاسم/الجواز/الميلاد الناقص")

print("\n=== التقرير الكامل والتجميع ===")
recs = [
    rec(full_name_ar="سالم", passport_number="P1", birth_date="1980-01-01",
        expiry_date="2030-01-01"),                                   # سليم
    rec(full_name_ar="نورة", passport_number="P2", birth_date="1990-01-01",
        expiry_date="2026-05-01"),                                   # منتهٍ
    rec(full_name_ar="خالد", passport_number="P1", birth_date="1975-01-01",
        expiry_date="2031-01-01"),                                   # مكرّر P1
    rec(full_name_ar="", passport_number="", birth_date=""),         # نقص كامل
]
report = check_records(recs, today=TODAY)
assert not report.clean
counts = report.counts()
assert counts.get(KIND_PASSPORT) == 1, counts       # نورة منتهٍ
assert counts.get(KIND_DUPLICATE) == 2, counts      # سالم وخالد (P1)
assert counts.get(KIND_MISSING) == 3, counts        # اسم+جواز+ميلاد للرابع
assert report.flagged_indices == {1, 0, 2, 3}, report.flagged_indices
# الترتيب: الجواز أولاً في التجميع
assert list(report.by_kind().keys())[0] == KIND_PASSPORT
print(f"  OK: {summary_text(report)}")

print("\n=== كشف نظيف ===")
clean = check_records([
    rec(full_name_ar="تام", passport_number="Z9", birth_date="1985-01-01",
        expiry_date="2032-01-01")], today=TODAY)
assert clean.clean and summary_text(clean).startswith("لا مشكلات")
print(f"  OK: {summary_text(clean)}")

print("\n*** QUALITY TESTS PASSED ***")

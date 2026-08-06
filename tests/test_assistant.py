# -*- coding: utf-8 -*-
"""اختبار مساعد «اسأل بياناتك»: تعرّف النيّة وصحّة الأجوبة المحسوبة."""
import sys, io
import os as _os
sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from hajj_app import assistant as A
from hajj_app.umrah import UmrahTrip
from hajj_app.mrz import PassportData

trips = [
    UmrahTrip(code="U1", name="عشر رمضان الأوائل", capacity="10", depart_date="2026-03-01"),
    UmrahTrip(code="U2", name="شعبان الفاخرة", capacity="8", depart_date="2026-02-01"),
]


def rec(code, val, paid, name, exp="2030-01-01"):
    return PassportData(full_name_ar=name, passport_number="P", trip=code,
                        program_value=str(val), paid_amount=str(paid), expiry_date=exp)


recs = [
    rec("U1", 18000, 18000, "أحمد"),
    rec("U1", 18000, 9000, "سالم"),
    rec("U1", 18000, 0, "خالد", exp="2026-04-01"),   # قريب الانتهاء + غير مسدد
    rec("U2", 15000, 15000, "ليلى"),
    rec("U2", 15000, 12000, "نورة"),
]


def ask(q):
    return A.answer(q, trips, recs, season="2026")


print("=== المتأخرون عن السداد ===")
a = ask("مين ما سدّد؟")
assert a["kind"] == "list" and len(a["rows"]) == 3, a
assert "خالد" in a["rows"][0][0], a["rows"]          # الأعلى ديناً أولاً (18,000)
assert "30,000" in a["headline"], a["headline"]       # 9000+18000+3000
print("  OK:", a["headline"])

print("\n=== المتبقّي مع تقييد ببرنامج ===")
a = ask("كم المتبقّي على رمضان؟")
assert a["kind"] == "stat" and "27,000" in a["headline"], a   # 9000+18000
assert "رمضان" in a["title"], a["title"]
print("  OK:", a["title"], a["headline"])

print("\n=== المحصّل والإيراد ===")
assert "54,000" in ask("كم المبلغ المحصّل؟")["headline"]      # 18000+9000+15000+12000
assert "84,000" in ask("كم الإيراد الإجمالي؟")["headline"]    # 5×... = 84,000
print("  OK: محصّل 54,000 / إيراد 84,000")

print("\n=== العدّ والإشغال ===")
assert "5 معتمر" in ask("كم معتمر هذا الموسم؟")["headline"]
assert "2 برنامج" in ask("كم برنامج في الموسم؟")["headline"]
occ = ask("كم مقعد باقٍ؟")
assert "5 / 18" in occ["headline"] and "13 مقعد" in occ["note"], occ
print("  OK: 5 معتمرين · 2 برنامج · 13 مقعداً شاغراً")

print("\n=== أعلى/أضعف برنامج تحصيلاً ===")
top = ask("أعلى برنامج تحصيلاً؟")
assert "شعبان الفاخرة" in top["headline"], top     # 27000/30000=90% > رمضان 50%
low = ask("أقل برنامج تحصيلاً؟")
assert "عشر رمضان الأوائل" in low["headline"], low
print("  OK: أعلى شعبان / أضعف رمضان")

print("\n=== صلاحية الجوازات ===")
a = ask("جوازات تنتهي قريباً؟")
assert a["kind"] == "list" and len(a["rows"]) == 1 and "خالد" in a["rows"][0][0], a
print("  OK: جواز خالد قريب الانتهاء")

print("\n=== سؤال غير مفهوم -> مساعدة بأمثلة ===")
h = ask("طقس مكة اليوم؟")
assert h["kind"] == "help" and h["examples"], h
print("  OK: يعرض أمثلة عند عدم الفهم")

print("\n=== لا يتعثّر مع موسم فارغ ===")
e = A.answer("مين ما سدّد؟", [], [])
assert "لا متأخرات" in e["headline"] or e["kind"] in ("stat", "list", "help"), e
print("  OK: الموسم الفارغ آمن")

print("\n*** ASSISTANT TESTS PASSED ***")

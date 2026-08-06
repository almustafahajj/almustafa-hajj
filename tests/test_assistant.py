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

print("\n=== بطاقة معتمرٍ بالاسم ===")
a = ask("كم دفع سالم؟")
assert a["title"] == "بطاقة المعتمر" and "سالم" in a["headline"], a
assert any(row[0] == "المتبقّي" for row in a["rows"]), a["rows"]
assert a.get("action") == "whatsapp_due", a          # عليه متبقٍّ -> قابل للتذكير
paid_ok = ask("بيانات أحمد")
assert "أحمد" in paid_ok["headline"], paid_ok
print("  OK: بطاقة تفصيلية + تذكير للمتبقّي عليه")

print("\n=== توزيع الجنسيات وتصفية العدّ بالجنسية ===")
natrecs = recs + [rec("U2", 15000, 15000, "محمد", exp="2030-01-01")]
for r, nat in zip(natrecs, ["سعودي", "سعودي", "سعودي", "مصري", "مصري"]):
    r.nationality_ar = nat
dist = A.answer("توزيع الجنسيات", trips, natrecs)
assert dist["kind"] == "list" and dist["rows"][0] == ["سعودي", "3"], dist["rows"]
cnt = A.answer("كم معتمر مصري؟", trips, natrecs)
assert "2 معتمر" in cnt["headline"] and "مصري" in cnt["title"], cnt
# مخطّط أعمدة مرفق بالتوزيع والترتيب
assert dist.get("chart") and dist["chart"]["items"][0][0] == "سعودي", dist.get("chart")
rank = A.answer("أعلى برنامج تحصيلاً؟", trips, natrecs)
assert rank.get("chart") and rank["chart"]["max"] == 100, rank.get("chart")
print("  OK: توزيع صحيح + عدّ الجنسية + مخطّطات مرفقة")

print("\n=== قائمة المتأخرين قابلة للتنفيذ (تذكير واتساب) ===")
a = ask("مين ما سدّد؟")
assert a.get("action") == "whatsapp_due" and a.get("records"), a
assert len(a["records"]) == len(a["rows"]), "الصفوف والسجلّات غير متطابقة"
r0 = a["records"][0]
r0.phone = "0501234567"
msg = A.due_reminder(r0, "عشر رمضان الأوائل", "المصطفى للحج والعمرة")
assert "خالد" in msg and "18,000 AED" in msg and "عشر رمضان الأوائل" in msg, msg
link = A.due_wa_link(r0, "عشر رمضان الأوائل", cc="971")
assert link.startswith("https://wa.me/971501234567?text="), link
# رقم غير صالح -> None
from hajj_app.mrz import PassportData as _PD
assert A.due_wa_link(_PD(full_name_ar="س", program_value="1", paid_amount="0")) is None
print("  OK: رسالة عربية + رابط واتساب دولي + رفض الرقم غير الصالح")

print("\n=== سجلّ التذكير الدائم (متى ذُكِّر كل معتمر) ===")
from hajj_app import umrah as _um
_s = {}
_r = PassportData(full_name_ar="أحمد", passport_number="P900", trip="U1")
assert _um.last_reminded(_s, _r) is None
_um.set_reminded(_s, _r, "2026-08-06")
assert _um.last_reminded(_s, _r) == "2026-08-06"
assert _s["umrah_reminders"]["P900"] == "2026-08-06"
# بلا رقم جواز -> مفتاح الاسم+البرنامج
_r2 = PassportData(full_name_ar="سالم", passport_number="", trip="U2")
_um.set_reminded(_s, _r2, "2026-08-05")
assert _um.last_reminded(_s, _r2) == "2026-08-05"
print("  OK: يُحفظ بالجواز أو بالاسم+البرنامج ويُسترجع")

print("\n=== لا يتعثّر مع موسم فارغ ===")
e = A.answer("مين ما سدّد؟", [], [])
assert "لا متأخرات" in e["headline"] or e["kind"] in ("stat", "list", "help"), e
print("  OK: الموسم الفارغ آمن")

print("\n=== تحصيل اليوم (دفعات مؤرّخة باليوم) ===")
from datetime import date as _date
_today = _date.today().isoformat()
_p1 = rec("U1", 18000, 9000, "أحمد")
_p1.payments = [{"date": _today, "amount": "9000"}]
_p2 = rec("U1", 18000, 18000, "سالم")
_p2.payments = [{"date": _today, "amount": "6000"},
                {"date": "2026-01-01", "amount": "12000"}]   # قديمة تُستبعد
_td = A.answer("من سدّد اليوم؟", trips, [_p1, _p2])
assert "15,000" in _td["headline"] and len(_td["rows"]) == 2, _td   # 9000+6000
_none = A.answer("تحصيل اليوم", trips, [rec("U1", 18000, 0, "خالد")])
assert "لا دفعات" in _none["headline"], _none
print("  OK: يجمع دفعات اليوم فقط، ويتعرّف على عدم وجودها")

print("\n=== وضع الحج: التجميع بـ program + إبدال «معتمر» بـ«حاج» ===")


class _P:
    def __init__(self, name):
        self.code = name; self.name = name; self.capacity = ""
        self.makkah_hotel = ""; self.madinah_hotel = ""; self.depart_date = ""


def hrec(prog, v, p, name, nat="سعودي"):
    return PassportData(full_name_ar=name, passport_number="P", program=prog,
                        program_value=str(v), paid_amount=str(p), nationality_ar=nat)


hprogs = [_P("البرنامج الأول"), _P("البرنامج الثاني")]
hrecs = [hrec("البرنامج الأول", 25000, 25000, "أحمد"),
         hrec("البرنامج الأول", 25000, 12000, "سالم"),
         hrec("البرنامج الثاني", 22000, 0, "خالد", "مصري")]
la = A.answer("مين ما سدّد؟", hprogs, hrecs, group_attr="program")
assert "حاج" in la["headline"] and "معتمر" not in la["headline"], la
assert la["headers"][0] == "الحاج", la["headers"]          # لا «المعتمر»
assert len(la["rows"]) == 2                                 # سالم + خالد بحقل program
ca = A.answer("عدد الحجّاج", hprogs, hrecs, group_attr="program")
assert "3 حاج" in ca["headline"], ca                        # صيغة الحج مفهومة
na = A.answer("كم حاج مصري؟", hprogs, hrecs, group_attr="program")
assert "1 حاج" in na["headline"] and "مصري" in na["title"], na
# العمرة تبقى بمصطلح «معتمر»
ua = A.answer("مين ما سدّد؟", trips, recs)
assert "معتمر" in ua["headline"] and ua["headers"][0] == "المعتمر", ua
print("  OK: الحج يعرض «حاج»/«الحاج» والعمرة تبقى «معتمر»/«المعتمر»")

print("\n*** ASSISTANT TESTS PASSED ***")

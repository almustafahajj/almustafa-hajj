# -*- coding: utf-8 -*-
"""اختبار مطابقة الاسم العربي بالاسم اللاتيني المأخوذ من MRZ."""
import sys, io
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_HERE)
_OUTDIR = _os.path.join(_HERE, "_out")
_os.makedirs(_OUTDIR, exist_ok=True)
sys.path.insert(0, _ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from hajj_app.translit import match_score, reconcile, repair_word

print("=== التمييز الصوتي: خطأ النقاط ب/ي ===")
# `مصبح` قُرئت `مصيح` في كل محاولات OCR. الباء موجودة في MUSABBE فتحسم.
correct = match_score("مصبح", "MUSABBE")
wrong = match_score("مصيح", "MUSABBE")
print(f"  مصبح  vs MUSABBE = {correct:.3f}")
print(f"  مصيح  vs MUSABBE = {wrong:.3f}")
assert correct > wrong + 0.3, (correct, wrong)
print("  OK: الحرف الصحيح يتفوّق بفارق واضح")

assert match_score("الشامسى", "ALSHAMSI") > 0.95
assert match_score("عبدالله", "ABDULLA") > 0.95
assert match_score("محمد", "MOHAMMED") > 0.85
assert match_score("محمد", "ABDULLA") < 0.3
print("  OK: الأسماء الصحيحة تسجّل عالياً، وغير المتطابقة تسجّل منخفضاً")

print("\n=== إصلاح خطأ النقاط ===")
fixed, score = repair_word("مصيح", "MUSABBE")
assert fixed == "مصبح", fixed
print(f"  مصيح -> {fixed} (درجة {score:.3f})")
# لا يُصلح إلا داخل مجموعة الرسم الواحد: الميم لا تصير لاماً
untouched, _ = repair_word("محمد", "ZZZZZZ")
assert untouched == "محمد", untouched
print("  OK: لا يُبدّل الحرف إلا بأخيه في الرسم، ولا يُصلح بلا مكسب واضح")

print("\n=== إعادة البناء من قراءات OCR حقيقية ===")
# قراءات فعلية من جواز AA0319030 — كل واحدة مخطئة في حرف أو حرفين
candidates = [
    "عبداله على محمد مصيج الشاسمس",
    "عيدات على محمد مصيح الشامسى",
    "غعدالل على محمد مصيخ الشامسى",
]
latin = "ABDULLA ALI MOHAMMED MUSABBE ALSHAMSI"
name, score = reconcile(candidates, latin)
print(f"  الناتج : {name}  (درجة {score:.3f})")
words = name.split()
assert len(words) == 5, f"توقعنا 5 كلمات، جاء {len(words)}: {name}"
assert words[1] == "على" and words[2] == "محمد"
assert words[4] == "الشامسى", words[4]
# الكلمة الرابعة تُصلَّح إلى مصبح أو مصبج — الباء صارت صحيحة في الحالتين
assert words[3].startswith("مصب"), words[3]
print("  OK: 5 كلمات بالترتيب، والباء صُحّحت، واللقب أُخذ من قراءة أخرى")

print("\n=== الأمان: لا يخترع اسماً أبداً ===")
junk = ["ا ا ا", "في اذى ديل عر قن ا وجورم", "مقان العلا ابسال مها", "الجنسية الامارات"]
result, result_score = reconcile(junk, latin)
assert result == "", f"اخترع اسماً من ضجيج: {result!r}"
print("  OK: الضجيج -> فراغ")

assert reconcile(candidates, "")[0] == ""
assert reconcile([], latin)[0] == ""
print("  OK: بلا اسم لاتيني أو بلا قراءات -> فراغ")

# كلمة واحدة صحيحة وسط ضجيج لا تكفي لبناء اسم
assert reconcile(["محمد قن وجورم اذى"], latin)[0] == ""
print("  OK: كلمة واحدة مطابقة لا تكفي — يلزم تغطية نصف الاسم على الأقل")

print("\n=== قيد الترتيب يمنع التلفيق ===")
# نفس الكلمات لكن بترتيب معكوس: لا يجوز إعادة ترتيبها لتوافق اللاتيني
scrambled = ["الشامسى مصبح محمد على عبدالله"]
built, _ = reconcile(scrambled, latin)
assert built != "عبدالله على محمد مصبح الشامسى", "أعاد الترتيب — القيد لا يعمل"
print(f"  OK: القراءة المعكوسة لم تُعَد ترتيبها -> {built!r}")

print("\n*** TRANSLITERATION TESTS PASSED ***")

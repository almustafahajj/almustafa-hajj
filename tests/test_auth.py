# -*- coding: utf-8 -*-
"""اختبار الدخول وتشفير ملف البيانات."""
import sys, io, json, shutil
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_HERE)
_OUTDIR = _os.path.join(_HERE, "_out")
_os.makedirs(_OUTDIR, exist_ok=True)
sys.path.insert(0, _ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from pathlib import Path
from hajj_app import auth
from hajj_app.auth import AuthError
from hajj_app.mrz import PassportData
from hajj_app.storage import is_encrypted, load_records, save_records

WORK = Path(_OUTDIR) / "authdata"
shutil.rmtree(WORK, ignore_errors=True)
WORK.mkdir(parents=True, exist_ok=True)
AUTH = WORK / "auth.json"
DATA = WORK / "hajjaj.json"

USER, PASSWORD = "almustafa", "Hajj-2026-Secure"

print("=== الحساب أول مرة ===")
assert not auth.is_configured(AUTH), "لا يجب أن يوجد حساب قبل الإنشاء"
session, recovery = auth.create_account(USER, PASSWORD, AUTH)
assert auth.is_configured(AUTH)
print("  OK: أُنشئ الحساب، is_configured صار True")

print("\n=== كلمة المرور لا تُحفظ في أي صورة ===")
raw = AUTH.read_text(encoding="utf-8")
assert PASSWORD not in raw, "كلمة المرور ظهرت نصاً في ملف الحساب!"
assert recovery not in raw, "مفتاح الاسترداد ظهر نصاً في ملف الحساب!"
stored = json.loads(raw)
assert stored["password_salt"] != stored["recovery_salt"], "الملحان يجب أن يختلفا"
assert stored["iterations"] >= 200_000, stored["iterations"]
assert "password" not in raw.lower().replace("password_salt", "").replace(
    "key_by_password", "")
print(f"  OK: لا كلمة المرور ولا المفتاح محفوظان، {stored['iterations']:,} جولة")
assert PASSWORD not in repr(session), "الجلسة تسرّب كلمة المرور في repr"
print("  OK: repr الجلسة لا يكشف المفتاح ->", repr(session))

print("\n=== ضوابط قوة كلمة المرور ===")
for bad, why in [("short", "قصيرة"), ("12345678", "أرقام فقط")]:
    assert auth.password_problem(bad), f"كان يجب رفض {why}"
    print(f"  OK: رُفضت ({why})")
assert auth.password_problem("Hajj-2026", "Hajj-2027"), "كان يجب رفض عدم التطابق"
print("  OK: رُفض عدم تطابق التأكيد")
assert not auth.password_problem(PASSWORD, PASSWORD)
print("  OK: قُبلت كلمة مرور صالحة")

print("\n=== الدخول ===")
for user, pwd, label in [
    (USER, "wrong-password", "كلمة مرور خاطئة"),
    ("intruder", PASSWORD, "مستخدم خاطئ"),
]:
    try:
        auth.login(user, pwd, AUTH)
        raise AssertionError(f"نجح الدخول رغم {label}!")
    except AuthError as exc:
        assert "غير صحيحة" in str(exc), str(exc)
        print(f"  OK: رُفض ({label}) برسالة لا تُفصح أي الحقلين أخطأ")

again = auth.login(USER, PASSWORD, AUTH)
print("  OK: نجح الدخول ببيانات صحيحة")

print("\n=== التشفير على القرص ===")
rec = PassportData()
rec.full_name_ar = "سعيد راشد سعيد مبارك الشامسى"
rec.full_name_en = "SAEED RASHED SAEED MUBARAK ALSHAMSI"
rec.passport_number = "AA0693247"
rec.birth_date = "1966-02-25"
save_records([rec], DATA, session)

blob = DATA.read_bytes()
assert is_encrypted(DATA), "الملف ليس مشفّراً"
for secret in ["AA0693247", "الشامسى", "1966-02-25", "SAEED"]:
    assert secret.encode("utf-8") not in blob, f"{secret} ظاهر في الملف المشفّر!"
print(f"  OK: {len(blob)} بايت، لا يظهر فيها رقم الجواز ولا الاسم ولا الميلاد")

back, note = load_records(DATA, again)
assert not note, note
assert len(back) == 1 and back[0].passport_number == "AA0693247"
assert back[0].full_name_ar == "سعيد راشد سعيد مبارك الشامسى"
print("  OK: فُكّ التشفير بجلسة أخرى لنفس المستخدم، والحقول سليمة")

print("\n=== كلمة مرور خاطئة لا تُتلف البيانات (الأهم) ===")
before = DATA.read_bytes()
other, _ = auth.create_account("someone", "Another-Pass-99", WORK / "other.json")
try:
    load_records(DATA, other)
    raise AssertionError("فُكّ التشفير بمفتاح خاطئ!")
except AuthError as exc:
    print(f"  OK: رُفض الفك -> {exc}")
assert DATA.read_bytes() == before, "الملف تغيّر بعد محاولة فاشلة!"
assert not list(WORK.glob("*تالف*")), "أُزيح الملف جانباً كأنه تالف!"
print("  OK: الملف لم يتغيّر ولم يُزَح جانباً — لا فقدان بيانات")

print("\n=== تغيير كلمة المرور لا يُعيد تشفير الكشف ===")
snapshot = DATA.read_bytes()
fresh = auth.change_password(USER, PASSWORD, "New-Hajj-Pass-77", AUTH)
assert DATA.read_bytes() == snapshot, "أُعيد تشفير الكشف بلا داعٍ!"
print("  OK: ملف البيانات لم يتغيّر — مفتاح البيانات ثابت، التغليف فقط تبدّل")
try:
    auth.login(USER, PASSWORD, AUTH)
    raise AssertionError("القديمة ما زالت تعمل!")
except AuthError:
    print("  OK: كلمة المرور القديمة لم تعد تعمل")
reopened, _ = load_records(DATA, auth.login(USER, "New-Hajj-Pass-77", AUTH))
assert reopened[0].passport_number == "AA0693247"
print("  OK: الكشف يُفتح بالكلمة الجديدة وبياناته سليمة")

print("\n=== التوافق مع كشف قديم غير مشفّر ===")
legacy = WORK / "legacy.json"
save_records([rec], legacy, None)
assert not is_encrypted(legacy)
old, _ = load_records(legacy, None)
assert old[0].passport_number == "AA0693247"
old_with_session, _ = load_records(legacy, fresh)
assert old_with_session[0].passport_number == "AA0693247"
print("  OK: الملف الصريح يُقرأ بجلسة وبدونها — لا يضيع كشف أُنشئ قبل التشفير")

print("\n*** AUTH + ENCRYPTION TESTS PASSED ***")

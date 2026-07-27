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
acc = stored["accounts"][USER.lower()]
assert acc["role"] == "admin", "أول حساب يجب أن يكون مديراً"
assert session.role == "admin" and session.is_admin and session.can_edit
assert acc["password_salt"] != acc["recovery_salt"], "الملحان يجب أن يختلفا"
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

print("\n=== حسابات متعددة بصلاحيات ===")
MULTI = WORK / "multi.json"
admin, _rk = auth.create_account("mgr", "Admin-Pass-11", MULTI)
# المدير يضيف محرّراً ومطّلعاً — يتشاركان مفتاح البيانات نفسه
rk_ed = auth.add_account(admin, "editor1", "Editor-Pass-1", "editor", MULTI)
rk_vw = auth.add_account(admin, "viewer1", "Viewer-Pass-1", "viewer", MULTI)
s_admin = auth.login("mgr", "Admin-Pass-11", MULTI)
s_editor = auth.login("editor1", "Editor-Pass-1", MULTI)
s_viewer = auth.login("viewer1", "Viewer-Pass-1", MULTI)
assert s_admin.data_key == s_editor.data_key == s_viewer.data_key, "مفتاح البيانات يجب أن يكون مشتركاً"
assert s_editor.role == "editor" and s_editor.can_edit and not s_editor.can_manage_accounts
assert s_viewer.role == "viewer" and not s_viewer.can_edit
print("  OK: 3 حسابات تفتح المفتاح نفسه، والأدوار محفوظة")

# كل حساب يفتح نفس الكشف المشفّر
MDATA = WORK / "multi-data.json"
save_records([rec], MDATA, s_admin)
for who in (s_editor, s_viewer):
    got, _ = load_records(MDATA, who)
    assert got[0].passport_number == "AA0693247"
print("  OK: المحرّر والمطّلع يفتحان نفس الكشف الذي شفّره المدير")

# الصلاحيات تُفرض في طبقة auth
for bad_session, op in [
    (s_editor, lambda: auth.add_account(s_editor, "x", "Xxxxxx-11", "viewer", MULTI)),
    (s_viewer, lambda: auth.remove_account(s_viewer, "editor1", MULTI)),
    (s_editor, lambda: auth.set_role(s_editor, "viewer1", "admin", MULTI)),
]:
    try:
        op(); raise AssertionError("نُفّذت عملية إدارية بلا صلاحية!")
    except AuthError:
        pass
print("  OK: غير المدير لا يضيف/يحذف/يغيّر الأدوار")

# لا حذف للذات ولا لآخر مدير
for op, why in [
    (lambda: auth.remove_account(s_admin, "mgr", MULTI), "حذف الذات"),
    (lambda: auth.set_role(s_admin, "mgr", "viewer", MULTI), "إنزال آخر مدير"),
]:
    try:
        op(); raise AssertionError(f"سُمح بـ{why}!")
    except AuthError:
        print(f"  OK: مُنع ({why})")

# تغيير الدور والحذف يعملان للمدير
auth.set_role(s_admin, "viewer1", "editor", MULTI)
assert {a["username"]: a["role"] for a in auth.list_accounts(MULTI)}["viewer1"] == "editor"
auth.remove_account(s_admin, "editor1", MULTI)
assert "editor1" not in {a["username"] for a in auth.list_accounts(MULTI)}
print("  OK: المدير يغيّر الأدوار ويحذف الحسابات")

# الاسترداد يجد الحساب الصحيح (viewer1 صار محرّراً) ويبقي دوره ومفتاحه
reset = auth.reset_with_recovery_key(rk_vw, "Viewer-New-22", MULTI)
assert reset.username == "viewer1" and reset.role == "editor", reset.role
assert reset.data_key == s_admin.data_key
assert auth.login("viewer1", "Viewer-New-22", MULTI).data_key == s_admin.data_key
print("  OK: مفتاح الاسترداد يفتح حسابه الصحيح ويبقي الدور ومفتاح البيانات")

print("\n=== التوافق مع ملف حساب أحادي قديم (schema 2) ===")
LEGACY_AUTH = WORK / "legacy-auth.json"
# نبني ملف schema-2 أحادي الحساب يدوياً من مدخل حساب الصيغة الجديدة
seed, _ = auth.create_account("solo", "Solo-Pass-123", LEGACY_AUTH)
new_raw = json.loads(LEGACY_AUTH.read_text(encoding="utf-8"))
entry = new_raw["accounts"]["solo"]
LEGACY_AUTH.write_text(json.dumps({
    "schema": 2, "username": "solo", "kdf": "pbkdf2_sha256",
    "iterations": new_raw["iterations"],
    "password_salt": entry["password_salt"], "key_by_password": entry["key_by_password"],
    "recovery_salt": entry["recovery_salt"], "key_by_recovery": entry["key_by_recovery"],
    "updated_at": entry["updated_at"],
}, ensure_ascii=False), encoding="utf-8")
relog = auth.login("solo", "Solo-Pass-123", LEGACY_AUTH)
assert relog.role == "admin" and relog.data_key == seed.data_key
assert auth.list_accounts(LEGACY_AUTH)[0]["role"] == "admin"
print("  OK: ملف أحادي قديم يُقرأ كحساب مدير واحد بلا إعادة كتابة")

print("\n=== الدخول بحساب مُعدّ مسبقاً على جهاز جديد ===")
# ملف حسابات مُعدّ على «جهاز آخر»
PREP = WORK / "prepared-auth.json"
padmin, _ = auth.create_account("MHU", "Prep-Admin-11", PREP)
auth.add_account(padmin, "clerk", "Clerk-Pass-22", "editor", PREP)
# ملف تالف لا يُقبل كملف حسابات
BAD = WORK / "bad.json"
BAD.write_text("{ليس ملف حسابات}", encoding="utf-8")
try:
    bad_accounts = auth.list_accounts(BAD)
except AuthError:
    bad_accounts = []
assert not bad_accounts, "ملف تالف قُبل كملف حسابات!"
# نقل الملف إلى «جهاز جديد» (مسار جديد) ثم الدخول به
NEW = WORK / "device2" / "auth.json"
NEW.parent.mkdir(parents=True, exist_ok=True)
assert auth.list_accounts(PREP), "الملف المُعدّ يجب أن يحوي حسابات"
shutil.copy2(PREP, NEW)
names = {a["username"] for a in auth.list_accounts(NEW)}
assert names == {"MHU", "clerk"}, names
s_new = auth.login("clerk", "Clerk-Pass-22", NEW)
assert s_new.role == "editor" and s_new.can_edit
assert auth.login("MHU", "Prep-Admin-11", NEW).is_admin
print("  OK: ملف حسابات مُعدّ يُنقل لجهاز جديد فيُدخَل به، والتالف يُرفض")

print("\n*** AUTH + ENCRYPTION TESTS PASSED ***")

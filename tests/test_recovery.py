# -*- coding: utf-8 -*-
"""اختبار مفتاح الاسترداد وإعادة تعيين كلمة المرور."""
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
from hajj_app.storage import load_records, save_records

WORK = Path(_OUTDIR) / "recovery"
shutil.rmtree(WORK, ignore_errors=True)
WORK.mkdir(parents=True, exist_ok=True)
AUTH, DATA = WORK / "auth.json", WORK / "hajjaj.json"

USER, PASSWORD = "almustafa", "Hajj-2026-Secure"


def a_record():
    r = PassportData()
    r.full_name_ar = "سعيد راشد سعيد مبارك الشامسى"
    r.passport_number = "AA0693247"
    r.birth_date = "1966-02-25"
    return r


print("=== إنشاء الحساب يعطي مفتاح استرداد ===")
session, recovery = auth.create_account(USER, PASSWORD, AUTH)
print(f"  مفتاح الاسترداد: {recovery}")
assert len(recovery.replace("-", "")) == 30, recovery
assert recovery.count("-") == 5, recovery
# لا يحوي حروفاً ملتبسة عند النسخ اليدوي
assert not set("ILOU01") & set(recovery), recovery
print("  OK: 30 حرفاً في 6 مجموعات، بلا حروف ملتبسة (I L O U 0 1)")

print("\n=== المفتاح لا يمكن استخراجه من ملف الحساب ===")
raw = AUTH.read_text(encoding="utf-8")
assert recovery not in raw and auth.normalize_recovery_key(recovery) not in raw
assert PASSWORD not in raw
stored = json.loads(raw)
assert stored["schema"] == 3
acc = stored["accounts"][USER.lower()]
assert acc["password_salt"] != acc["recovery_salt"]
assert "auth_hash" not in acc, "بقيت بصمة الصيغة القديمة"
print("  OK: لا كلمة المرور ولا مفتاح الاسترداد محفوظان بأي صورة")

save_records([a_record()], DATA, session)
before = DATA.read_bytes()
print(f"  حُفظ الكشف مشفّراً ({len(before)} بايت)")

print("\n=== الاسترداد يفتح الكشف دون المساس به ===")
for bad, why in [
    ("ABCDE-FGHJK-MNPQR-STVWX-YZ234-56789", "مفتاح خاطئ صحيح الصيغة"),
    ("ABC-DEF", "صيغة ناقصة"),
]:
    try:
        auth.reset_with_recovery_key(bad, "Brand-New-Pass-1", AUTH)
        raise AssertionError(f"قُبل {why}!")
    except AuthError as exc:
        print(f"  OK: رُفض ({why}) -> {str(exc).splitlines()[0]}")

recovered = auth.reset_with_recovery_key(recovery, "Brand-New-Pass-1", AUTH)
assert DATA.read_bytes() == before, "ملف البيانات تغيّر أثناء الاسترداد!"
print("  OK: ملف البيانات لم يتغيّر بايتاً واحداً")

records, note = load_records(DATA, recovered)
assert not note and records[0].passport_number == "AA0693247"
assert records[0].full_name_ar == "سعيد راشد سعيد مبارك الشامسى"
print("  OK: الكشف يُفتح بالجلسة المستردة وبياناته سليمة")

print("\n=== كلمة المرور القديمة لم تعد تعمل، والجديدة تعمل ===")
try:
    auth.login(USER, PASSWORD, AUTH)
    raise AssertionError("القديمة ما زالت تعمل!")
except AuthError:
    print("  OK: القديمة رُفضت")
fresh = auth.login(USER, "Brand-New-Pass-1", AUTH)
assert load_records(DATA, fresh)[0][0].passport_number == "AA0693247"
print("  OK: الجديدة تعمل والكشف سليم")

print("\n=== مفتاح الاسترداد يبقى صالحاً بعد الاستخدام ===")
again = auth.reset_with_recovery_key(recovery, "Third-Password-3", AUTH)
assert load_records(DATA, again)[0][0].passport_number == "AA0693247"
print("  OK: نفس الورقة المطبوعة تصلح مرة أخرى — لا حلقة نسيان جديدة")

print("\n=== الصيغة متساهلة مع طريقة الكتابة ===")
messy = recovery.lower().replace("-", " ")
assert auth.normalize_recovery_key(messy) == auth.normalize_recovery_key(recovery)
loose = auth.reset_with_recovery_key(messy, "Fourth-Pass-44", AUTH)
assert load_records(DATA, loose)[0][0].passport_number == "AA0693247"
print("  OK: حروف صغيرة وفراغات بدل الشرطات — يعمل")

print("\n=== تغيير كلمة المرور لا يمسّ الكشف ولا يُبطل الاسترداد ===")
snapshot = DATA.read_bytes()
changed = auth.change_password(USER, "Fourth-Pass-44", "Fifth-Pass-555", AUTH)
assert DATA.read_bytes() == snapshot, "ملف البيانات تغيّر!"
assert load_records(DATA, changed)[0][0].passport_number == "AA0693247"
still = auth.reset_with_recovery_key(recovery, "Sixth-Pass-6666", AUTH)
assert load_records(DATA, still)[0][0].passport_number == "AA0693247"
print("  OK: الكشف كما هو، ومفتاح الاسترداد ما زال صالحاً")

print("\n=== توليد مفتاح استرداد جديد (لمن ضاع مفتاحه) ===")
current_pass = "Sixth-Pass-6666"
snapshot = DATA.read_bytes()
try:
    auth.regenerate_recovery_key(USER, "wrong-password", AUTH)
    raise AssertionError("ولّد مفتاحاً بكلمة مرور خاطئة!")
except AuthError:
    print("  OK: يرفض التوليد بكلمة مرور خاطئة")

new_recovery = auth.regenerate_recovery_key(USER, current_pass, AUTH)
assert new_recovery != recovery, "المفتاح الجديد يطابق القديم!"
assert DATA.read_bytes() == snapshot, "ملف البيانات تغيّر!"
print(f"  OK: مفتاح جديد {new_recovery}، وملف البيانات لم يتغيّر")

try:
    auth.reset_with_recovery_key(recovery, "Should-Not-Work-1", AUTH)
    raise AssertionError("المفتاح القديم ما زال يعمل!")
except AuthError:
    print("  OK: المفتاح القديم بَطل فوراً")

with_new = auth.reset_with_recovery_key(new_recovery, "Seventh-Pass-77", AUTH)
assert load_records(DATA, with_new)[0][0].passport_number == "AA0693247"
# كلمة المرور صارت الجديدة، والقديمة بطلت
assert load_records(DATA, auth.login(USER, "Seventh-Pass-77", AUTH))[0][0].passport_number == "AA0693247"
try:
    auth.login(USER, current_pass, AUTH)
    raise AssertionError("كلمة المرور السابقة ما زالت تعمل!")
except AuthError:
    pass
print("  OK: المفتاح الجديد يفتح الكشف، والكلمة السابقة بطلت")

print("\n=== ترقية حساب قديم (schema 1) دون فقدان الكشف ===")
OLD_AUTH, OLD_DATA = WORK / "old_auth.json", WORK / "old_hajjaj.json"
import base64, hashlib, secrets as _secrets
old_pass = "Legacy-Pass-2025"
auth_salt, data_salt = _secrets.token_bytes(16), _secrets.token_bytes(16)


def derive(secret, salt):
    return hashlib.pbkdf2_hmac("sha256", secret.encode(), salt, auth.ITERATIONS, 32)


OLD_AUTH.write_text(json.dumps({
    "schema": 1, "username": USER, "kdf": "pbkdf2_sha256",
    "iterations": auth.ITERATIONS,
    "auth_salt": base64.b64encode(auth_salt).decode(),
    "auth_hash": base64.b64encode(derive(old_pass, auth_salt)).decode(),
    "data_salt": base64.b64encode(data_salt).decode(),
}, ensure_ascii=False), encoding="utf-8")

legacy_session = auth.Session(USER, derive(old_pass, data_salt))
save_records([a_record()], OLD_DATA, legacy_session)
legacy_blob = OLD_DATA.read_bytes()
print(f"  كشف قديم مشفّر بالصيغة الأولى ({len(legacy_blob)} بايت)")

opened = auth.login(USER, old_pass, OLD_AUTH)
assert opened.needs_recovery_key, "لم يُشَر إلى حاجة الحساب لمفتاح استرداد"
assert load_records(OLD_DATA, opened)[0][0].passport_number == "AA0693247"
print("  OK: الحساب القديم يفتح كشفه، ووُسم بأنه يحتاج مفتاح استرداد")

new_key = auth.upgrade_legacy(USER, old_pass, opened, OLD_AUTH)
assert OLD_DATA.read_bytes() == legacy_blob, "أُعيد تشفير الكشف أثناء الترقية!"
assert not opened.needs_recovery_key
print(f"  OK: رُقّي بلا إعادة تشفير — مفتاح الاسترداد: {new_key}")

upgraded = json.loads(OLD_AUTH.read_text(encoding="utf-8"))
assert upgraded["schema"] == 3
assert upgraded["accounts"][USER.lower()]["role"] == "admin"
after_upgrade = auth.login(USER, old_pass, OLD_AUTH)
assert not after_upgrade.needs_recovery_key
assert load_records(OLD_DATA, after_upgrade)[0][0].passport_number == "AA0693247"
print("  OK: نفس كلمة المرور ما زالت تعمل والكشف سليم")

restored = auth.reset_with_recovery_key(new_key, "Post-Upgrade-Pass", OLD_AUTH)
assert load_records(OLD_DATA, restored)[0][0].passport_number == "AA0693247"
print("  OK: مفتاح الاسترداد الجديد يفتح الكشف القديم")

print("\n*** RECOVERY KEY TESTS PASSED ***")

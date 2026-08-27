"""حساب الدخول، تشفير ملف البيانات، ومفتاح الاسترداد.

يحوي ملف الحجاج جوازات وتواريخ ميلاد لمئات الأشخاص — بيانات شخصية حسّاسة.
لذلك لا نكتفي بشاشة دخول تمنع الفتح العابر، بل **نشفّر الملف نفسه**: من لا
يملك كلمة المرور لا يقرأ شيئاً ولو فتح الملف بالمفكرة.

## التشفير بطبقتين

مفتاح تشفير البيانات (سنسميه *مفتاح البيانات*) **عشوائي**، لا يُشتق من كلمة
المرور. ثم نحفظ منه نسختين مغلّفتين:

    مفتاح البيانات ──┬── مغلَّف بمفتاح مشتق من كلمة المرور
                     └── مغلَّف بمفتاح مشتق من مفتاح الاسترداد

فائدتان:

1. **الاسترداد ممكن دون ثقب في التشفير.** من نسي كلمة المرور يفتح بمفتاح
   الاسترداد المطبوع، ومن لا يملك أياً منهما لا يفتح شيئاً.
2. **تغيير كلمة المرور لا يمسّ ملف البيانات.** نعيد تغليف المفتاح فقط، ولو
   كان المفتاح مشتقاً من كلمة المرور مباشرة لوجب إعادة تشفير الكشف كله —
   وأي انقطاع أثناء ذلك يفقد البيانات.

كلمة المرور ومفتاح الاسترداد **لا يُحفظان أبداً**، لا نصاً ولا مشفّرين. لا
يوجد باب خلفي: من يفقد الاثنين معاً يفقد البيانات نهائياً.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
from datetime import datetime
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

SCHEMA_VERSION = 3

# أدوار الحسابات وصلاحياتها. الدور يحدّد ما يستطيع الحساب فعله في البرنامج:
#   مدير  (admin)  — كل شيء + إضافة/حذف الحسابات وتغيير أدوارها
#   محرّر (editor) — إضافة/تعديل/حذف الحجّاج والاستيراد والاستعادة والتصدير
#   مطّلع (viewer) — عرض وتصدير وطباعة فقط، بلا تعديل أو حذف
ROLES: tuple[str, ...] = ("admin", "editor", "viewer")
ROLE_LABELS = {"admin": "مدير", "editor": "محرّر", "viewer": "مطّلع"}


def role_can_edit(role: str) -> bool:
    """هل يملك الدور صلاحية تعديل البيانات (إضافة/حذف/استيراد)؟"""
    return role in ("admin", "editor")


def role_can_manage_accounts(role: str) -> bool:
    """هل يملك الدور صلاحية إدارة الحسابات؟ (المدير فقط)"""
    return role == "admin"

# جولات PBKDF2. الرقم مرتفع عمداً ليكلّف المهاجم كثيراً ولا يُشعر المستخدم
# بتأخير (نحو ثلث ثانية عند الدخول مرة واحدة).
ITERATIONS = 480_000
_SALT_BYTES = 16
_KEY_BYTES = 32

MIN_PASSWORD_LENGTH = 8

# أبجدية مفتاح الاسترداد: بلا I L O U 0 1 تجنّباً للالتباس عند النسخ اليدوي
_ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ23456789"
_GROUPS, _GROUP_SIZE = 6, 5      # 30 حرفاً ≈ 147 بت — أقوى من أي كلمة مرور


class AuthError(Exception):
    """خطأ في الدخول أو في فك تشفير البيانات."""


def default_auth_path() -> Path:
    """مسار ملف الحساب: بجوار ملف البيانات (يبقى دائماً في نسخة exe)."""
    from .paths import data_dir
    return data_dir() / "auth.json"


# ------------------------------------------------------------------ أدوات
def _derive(secret: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, ITERATIONS, _KEY_BYTES)


def _fernet(key: bytes) -> Fernet:
    return Fernet(base64.urlsafe_b64encode(key))


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


# --------------------------------------------------------- مفتاح الاسترداد
def generate_recovery_key() -> str:
    """يولّد مفتاح استرداد جديداً بصيغة مقروءة: ABCDE-FGHJK-..."""
    groups = [
        "".join(secrets.choice(_ALPHABET) for _ in range(_GROUP_SIZE))
        for _ in range(_GROUPS)
    ]
    return "-".join(groups)


def normalize_recovery_key(text: str) -> str:
    """يوحّد المفتاح المُدخل: حروف كبيرة، بلا شرطات ولا فراغات.

    نتساهل مع طريقة كتابة المستخدم لأن المفتاح يُنسخ يدوياً عن ورقة.
    """
    return "".join(c for c in str(text).upper() if c in _ALPHABET)


def _recovery_is_wellformed(key: str) -> bool:
    return len(normalize_recovery_key(key)) == _GROUPS * _GROUP_SIZE


# ------------------------------------------------------------ كلمة المرور
def password_problem(password: str, confirm: str | None = None) -> str:
    """يفحص قوة كلمة المرور. يعيد نص المشكلة، أو فراغاً إن كانت صالحة."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"كلمة المرور يجب ألا تقل عن {MIN_PASSWORD_LENGTH} خانات."
    if password.isdigit():
        return "كلمة المرور أرقام فقط — أضف حروفاً لتصعب على التخمين."
    if confirm is not None and password != confirm:
        return "كلمتا المرور غير متطابقتين."
    return ""


def is_configured(path: str | Path | None = None) -> bool:
    """هل أُنشئ حساب من قبل؟ إن لا، يعرض البرنامج شاشة الإعداد أول مرة."""
    return Path(path or default_auth_path()).is_file()


# ----------------------------------------------------------- قراءة وكتابة
def _write_json(path: Path, payload: dict) -> None:
    """كتابة ذرّية — نفس أسلوب ملف البيانات حتى لا يتلف الحساب."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    with open(temp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(temp, path)


def _read_json(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        raise AuthError(f"ملف الحساب تالف أو غير صالح: {exc}") from exc


def _wrap_account(username: str, role: str, data_key: bytes, password: str,
                  recovery_key: str) -> dict:
    """يبني مدخل حساب: مفتاح البيانات مغلَّفاً بكلمة المرور وبمفتاح الاسترداد.

    كل الحسابات تتشارك **مفتاح البيانات نفسه** (فملف الحجّاج مشفّر بمفتاح
    واحد)، لكن كلٌّ يغلّفه بسرّه الخاص. هكذا يفتح أي حساب صالح الكشف نفسه.
    """
    password_salt = secrets.token_bytes(_SALT_BYTES)
    recovery_salt = secrets.token_bytes(_SALT_BYTES)
    return {
        "username": username,
        "role": role if role in ROLES else "viewer",
        "password_salt": _b64(password_salt),
        "key_by_password": _fernet(_derive(password, password_salt))
                           .encrypt(data_key).decode("ascii"),
        "recovery_salt": _b64(recovery_salt),
        "key_by_recovery": _fernet(_derive(normalize_recovery_key(recovery_key),
                                           recovery_salt))
                           .encrypt(data_key).decode("ascii"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


def _load(path: str | Path | None) -> tuple[dict, int]:
    """يقرأ ملف الحساب ويعيد (خريطة الحسابات، رقم الصيغة).

    يتساهل مع الصيغ القديمة أحادية الحساب (schema 1/2): يحوّلها ضمناً إلى
    خريطة بحساب واحد دوره «مدير»، فلا يُعاد كتابة الملف إلا عند أول تعديل.
    مفاتيح الخريطة = أسماء المستخدمين بأحرف صغيرة (لتفرّد غير حسّاس للحالة).
    """
    path = Path(path or default_auth_path())
    if not path.is_file():
        return {}, 0
    raw = _read_json(path)
    schema = int(raw.get("schema", 1))
    if schema >= 3 and isinstance(raw.get("accounts"), dict):
        return dict(raw["accounts"]), schema

    username = str(raw.get("username", ""))
    if not username:
        return {}, schema
    if schema >= 2:
        account = {
            "username": username, "role": "admin",
            "password_salt": raw.get("password_salt"),
            "key_by_password": raw.get("key_by_password"),
            "recovery_salt": raw.get("recovery_salt"),
            "key_by_recovery": raw.get("key_by_recovery"),
            "updated_at": raw.get("updated_at"),
        }
    else:
        account = {
            "username": username, "role": "admin", "legacy1": True,
            "auth_salt": raw.get("auth_salt"), "auth_hash": raw.get("auth_hash"),
            "data_salt": raw.get("data_salt"),
        }
    return {username.lower(): account}, schema


def _save_accounts(path: str | Path | None, accounts: dict) -> None:
    """يكتب خريطة الحسابات بالصيغة الحالية (schema 3)."""
    _write_json(Path(path or default_auth_path()), {
        "schema": SCHEMA_VERSION,
        "kdf": "pbkdf2_sha256",
        "iterations": ITERATIONS,
        "accounts": accounts,
    })


def _find(accounts: dict, username: str) -> str | None:
    """يعيد مفتاح الحساب (الاسم بأحرف صغيرة) إن وُجد، وإلا None."""
    key = str(username).strip().lower()
    return key if key in accounts else None


def _count_admins(accounts: dict) -> int:
    return sum(1 for a in accounts.values() if a.get("role") == "admin")


# ------------------------------------------------------------- العمليات
def create_account(
    username: str, password: str, path: str | Path | None = None
) -> tuple["Session", str]:
    """ينشئ الحساب الأول (المسؤول) — يولّد مفتاح البيانات المشترك.

    يعيد (الجلسة، مفتاح الاسترداد). **مفتاح الاسترداد يُعرض مرة واحدة فقط**
    ولا يمكن استخراجه لاحقاً من ملف الحساب — على المُنادي عرضه للمستخدم.
    """
    username = username.strip()
    if not username:
        raise AuthError("اسم المستخدم مطلوب.")
    problem = password_problem(password)
    if problem:
        raise AuthError(problem)

    path = Path(path or default_auth_path())
    data_key = secrets.token_bytes(_KEY_BYTES)
    recovery_key = generate_recovery_key()
    accounts = {username.lower(): _wrap_account(username, "admin", data_key,
                                                password, recovery_key)}
    _save_accounts(path, accounts)
    return Session(username, data_key, role="admin"), recovery_key


def add_account(
    session: "Session", username: str, password: str, role: str = "viewer",
    path: str | Path | None = None,
) -> str:
    """يضيف حساباً جديداً بدور محدّد — للمدير فقط.

    يغلّف **مفتاح البيانات نفسه** (من جلسة المدير) بكلمة مرور الحساب الجديد،
    فيفتح الحساب الجديد الكشف المشفّر ذاته. يعيد مفتاح الاسترداد ليُعرض مرة.
    """
    if session is None or not session.is_admin:
        raise AuthError("إضافة الحسابات للمدير فقط.")
    username = username.strip()
    if not username:
        raise AuthError("اسم المستخدم مطلوب.")
    if role not in ROLES:
        raise AuthError("الدور غير معروف.")
    problem = password_problem(password)
    if problem:
        raise AuthError(problem)

    path = Path(path or default_auth_path())
    accounts, _ = _load(path)
    if _find(accounts, username):
        raise AuthError("اسم المستخدم مستخدم بالفعل — اختر اسماً آخر.")
    recovery_key = generate_recovery_key()
    accounts[username.lower()] = _wrap_account(username, role, session.data_key,
                                               password, recovery_key)
    _save_accounts(path, accounts)
    return recovery_key


def admin_set_password(
    session: "Session", username: str, new_password: str,
    path: str | Path | None = None,
) -> str | None:
    """يعيّن كلمة مرور جديدة لحساب — للمدير فقط، دون الحاجة لكلمة المرور القديمة.

    يعيد تغليف **مفتاح البيانات المشترك** (من جلسة المدير) بالكلمة الجديدة، فيدخل
    صاحب الحساب بها فوراً ويفتح الكشف نفسه. يُبقي مفتاح الاسترداد إن وُجد، وإلا
    يولّد واحداً ويعيده ليُعرض. لحلّ «حساب موجود لا يستطيع الدخول».
    """
    if session is None or not session.is_admin:
        raise AuthError("إعادة تعيين كلمة المرور للمدير فقط.")
    problem = password_problem(new_password)
    if problem:
        raise AuthError(problem)
    path = Path(path or default_auth_path())
    accounts, _ = _load(path)
    key = _find(accounts, username)
    if key is None:
        raise AuthError("لا يوجد حساب بهذا الاسم.")
    account = accounts[key]
    role = account.get("role", "viewer")
    password_salt = secrets.token_bytes(_SALT_BYTES)
    new_acc = {k: v for k, v in account.items()
               if k not in ("legacy1", "auth_salt", "auth_hash", "data_salt")}
    new_acc.update({
        "username": account.get("username", username),
        "role": role,
        "password_salt": _b64(password_salt),
        "key_by_password": _fernet(_derive(new_password, password_salt))
                           .encrypt(session.data_key).decode("ascii"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    })
    recovery_key = None
    if not new_acc.get("key_by_recovery"):
        recovery_key = generate_recovery_key()
        recovery_salt = secrets.token_bytes(_SALT_BYTES)
        new_acc["recovery_salt"] = _b64(recovery_salt)
        new_acc["key_by_recovery"] = _fernet(_derive(
            normalize_recovery_key(recovery_key), recovery_salt)
        ).encrypt(session.data_key).decode("ascii")
    accounts[key] = new_acc
    _save_accounts(path, accounts)
    return recovery_key


def list_accounts(path: str | Path | None = None) -> list[dict]:
    """يعيد قائمة الحسابات: [{username, role, updated_at}] مرتّبة بالاسم."""
    accounts, _ = _load(path)
    rows = [{"username": a.get("username", ""), "role": a.get("role", "admin"),
             "updated_at": a.get("updated_at", "")} for a in accounts.values()]
    return sorted(rows, key=lambda r: r["username"].lower())


def remove_account(
    session: "Session", username: str, path: str | Path | None = None
) -> None:
    """يحذف حساباً — للمدير فقط. لا يحذف حسابه الحالي ولا آخر مدير."""
    if session is None or not session.is_admin:
        raise AuthError("حذف الحسابات للمدير فقط.")
    path = Path(path or default_auth_path())
    accounts, _ = _load(path)
    key = _find(accounts, username)
    if key is None:
        raise AuthError("لا يوجد حساب بهذا الاسم.")
    if key == session.username.strip().lower():
        raise AuthError("لا يمكنك حذف حسابك الحالي.")
    if accounts[key].get("role") == "admin" and _count_admins(accounts) <= 1:
        raise AuthError("لا يمكن حذف آخر مدير — عيّن مديراً آخر أولاً.")
    del accounts[key]
    _save_accounts(path, accounts)


def set_role(
    session: "Session", username: str, role: str, path: str | Path | None = None
) -> None:
    """يغيّر دور حساب — للمدير فقط. لا يُنزل آخر مدير عن الإدارة."""
    if session is None or not session.is_admin:
        raise AuthError("تغيير الأدوار للمدير فقط.")
    if role not in ROLES:
        raise AuthError("الدور غير معروف.")
    path = Path(path or default_auth_path())
    accounts, _ = _load(path)
    key = _find(accounts, username)
    if key is None:
        raise AuthError("لا يوجد حساب بهذا الاسم.")
    if (accounts[key].get("role") == "admin" and role != "admin"
            and _count_admins(accounts) <= 1):
        raise AuthError("لا يمكن إنزال آخر مدير — عيّن مديراً آخر أولاً.")
    accounts[key]["role"] = role
    accounts[key]["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _save_accounts(path, accounts)


def login(username: str, password: str, path: str | Path | None = None) -> "Session":
    """يتحقق من بيانات الدخول ويعيد جلسة تحمل مفتاح البيانات ودور الحساب."""
    path = Path(path or default_auth_path())
    accounts, schema = _load(path)
    if not accounts:
        raise AuthError("لا يوجد حساب بعد — أنشئ حساباً أولاً.")

    key = _find(accounts, username)
    account = accounts.get(key) if key else None

    data_key = None
    if account is not None:
        try:
            data_key = _unwrap_with_password(account, password)
        except (AuthError, KeyError, ValueError, InvalidToken):
            data_key = None

    # لا نُفصح أي الحقلين أخطأ — وإلا صار تخمين أسماء المستخدمين أسهل
    if account is None or data_key is None:
        raise AuthError("اسم المستخدم أو كلمة المرور غير صحيحة.")

    role = account.get("role", "admin")
    # حساب قديم بلا مفتاح استرداد — يرقّيه `upgrade_legacy` بعد الدخول
    needs_recovery = bool(account.get("legacy1")) or not account.get("key_by_recovery")
    return Session(account["username"], data_key, role=role,
                   needs_recovery_key=needs_recovery)


def _unwrap_with_password(account: dict, password: str) -> bytes:
    """يستخرج مفتاح البيانات من مدخل حساب بكلمة المرور.

    يدعم الصيغة القديمة (schema 1) حيث كان المفتاح مشتقاً من كلمة المرور
    مباشرة — فالكشوف المشفّرة بها تبقى مقروءة بعد الترقية.
    """
    if account.get("legacy1"):
        # قديم: المفتاح نفسه = اشتقاق كلمة المرور. نتحقق عبر بصمة منفصلة.
        expected = _unb64(account["auth_hash"])
        if not hmac.compare_digest(_derive(password, _unb64(account["auth_salt"])), expected):
            raise AuthError("كلمة المرور غير صحيحة.")
        return _derive(password, _unb64(account["data_salt"]))

    salt = _unb64(account["password_salt"])
    return _fernet(_derive(password, salt)).decrypt(
        account["key_by_password"].encode("ascii")
    )


def upgrade_legacy(
    username: str, password: str, session: "Session", path: str | Path | None = None
) -> str:
    """يرقّي حساباً قديماً إلى الصيغة ذات مفتاح الاسترداد.

    يبقي **نفس مفتاح البيانات**، فالكشف المشفّر سابقاً يظل مقروءاً بلا
    إعادة تشفير. يعيد مفتاح الاسترداد الجديد ليُعرض للمستخدم.
    """
    path = Path(path or default_auth_path())
    accounts, _ = _load(path)
    key = _find(accounts, username)
    if key is None:
        raise AuthError("لا يوجد حساب بهذا الاسم.")
    role = accounts[key].get("role", "admin")
    recovery_key = generate_recovery_key()
    accounts[key] = _wrap_account(session.username, role, session.data_key,
                                  password, recovery_key)
    _save_accounts(path, accounts)
    session.needs_recovery_key = False
    return recovery_key


def regenerate_recovery_key(
    username: str, password: str, path: str | Path | None = None
) -> str:
    """يولّد مفتاح استرداد جديداً بدل الحالي، بمعرفة كلمة المرور.

    المفتاح القديم **يبطل فوراً**، وملف البيانات لا يُمسّ — نعيد تغليف
    مفتاح البيانات لا غير.
    """
    path = Path(path or default_auth_path())
    session = login(username, password, path)          # يرفع AuthError إن أخطأ
    accounts, _ = _load(path)
    key = _find(accounts, username)
    role = accounts[key].get("role", "admin")
    recovery_key = generate_recovery_key()
    accounts[key] = _wrap_account(session.username, role, session.data_key,
                                  password, recovery_key)
    _save_accounts(path, accounts)
    return recovery_key


def reset_with_recovery_key(
    recovery_key: str, new_password: str, path: str | Path | None = None,
    allowed_roles: "tuple[str, ...] | None" = None,
) -> "Session":
    """يعيد تعيين كلمة المرور بمفتاح الاسترداد.

    يبحث عن الحساب الذي يفتحه هذا المفتاح، ثم يعيد تغليف مفتاح البيانات
    بكلمة المرور الجديدة. **ملف البيانات لا يُمسّ**، ومفتاح الاسترداد يبقى
    صالحاً بعد العملية.
    """
    path = Path(path or default_auth_path())
    accounts, _ = _load(path)
    if not accounts:
        raise AuthError("لا يوجد حساب بعد.")
    if not _recovery_is_wellformed(recovery_key):
        raise AuthError(
            f"صيغة مفتاح الاسترداد غير صحيحة — "
            f"يتكوّن من {_GROUPS * _GROUP_SIZE} حرفاً في {_GROUPS} مجموعات."
        )
    problem = password_problem(new_password)
    if problem:
        raise AuthError(problem)

    normalized = normalize_recovery_key(recovery_key)
    for key, account in accounts.items():
        if account.get("legacy1") or not account.get("key_by_recovery"):
            continue
        try:
            data_key = _fernet(
                _derive(normalized, _unb64(account["recovery_salt"]))
            ).decrypt(account["key_by_recovery"].encode("ascii"))
        except (InvalidToken, KeyError, ValueError):
            continue
        role = account.get("role", "admin")
        if allowed_roles is not None and role not in allowed_roles:
            raise AuthError("الاسترداد الذاتي متاح للمدير فقط — "
                            "اطلب من المدير إعادة تعيين كلمة مرورك.")
        username = account.get("username", "")
        accounts[key] = _wrap_account(username, role, data_key,
                                      new_password, normalized)
        _save_accounts(path, accounts)
        return Session(username, data_key, role=role)

    raise AuthError("مفتاح الاسترداد غير صحيح.")


def change_password(
    username: str, old_password: str, new_password: str,
    path: str | Path | None = None,
) -> "Session":
    """يغيّر كلمة المرور مع الإبقاء على مفتاح البيانات وملف الكشف كما هما."""
    path = Path(path or default_auth_path())
    session = login(username, old_password, path)
    problem = password_problem(new_password)
    if problem:
        raise AuthError(problem)

    accounts, _ = _load(path)
    key = _find(accounts, username)
    account = accounts[key]
    role = account.get("role", "admin")

    # نُبقي مفتاح الاسترداد الحالي إن وُجد — الورقة المطبوعة تبقى صالحة
    if account.get("key_by_recovery") and not account.get("legacy1"):
        password_salt = secrets.token_bytes(_SALT_BYTES)
        accounts[key] = {
            **account,
            "role": role,
            "password_salt": _b64(password_salt),
            "key_by_password": _fernet(_derive(new_password, password_salt))
                               .encrypt(session.data_key).decode("ascii"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        _save_accounts(path, accounts)
        return Session(session.username, session.data_key, role=role)

    # حساب قديم: نرقّيه ونولّد مفتاح استرداد — على المُنادي عرضه
    recovery_key = generate_recovery_key()
    accounts[key] = _wrap_account(session.username, role, session.data_key,
                                  new_password, recovery_key)
    _save_accounts(path, accounts)
    new_session = Session(session.username, session.data_key, role=role)
    new_session.fresh_recovery_key = recovery_key
    return new_session


class Session:
    """جلسة مفتوحة: تحمل مفتاح البيانات في الذاكرة فقط، لا على القرص."""

    def __init__(self, username: str, data_key: bytes, *,
                 role: str = "admin", needs_recovery_key: bool = False) -> None:
        self.username = username
        self.data_key = data_key
        self.role = role if role in ROLES else "viewer"
        # حساب قديم دخل بنجاح لكنه بلا مفتاح استرداد بعد
        self.needs_recovery_key = needs_recovery_key
        # يُملأ عند توليد مفتاح استرداد أثناء الجلسة، ليعرضه المُنادي مرة
        self.fresh_recovery_key: str | None = None
        self._fernet = _fernet(data_key)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def can_edit(self) -> bool:
        """صلاحية تعديل البيانات (إضافة/تعديل/حذف/استيراد)."""
        return role_can_edit(self.role)

    @property
    def can_manage_accounts(self) -> bool:
        return role_can_manage_accounts(self.role)

    @property
    def role_label(self) -> str:
        return ROLE_LABELS.get(self.role, self.role)

    def encrypt(self, plaintext: bytes) -> bytes:
        return self._fernet.encrypt(plaintext)

    def decrypt(self, token: bytes) -> bytes:
        try:
            return self._fernet.decrypt(token)
        except InvalidToken as exc:
            raise AuthError(
                "تعذّر فك تشفير البيانات — الملف لا يطابق كلمة المرور الحالية."
            ) from exc

    def __repr__(self) -> str:      # لا نكشف المفتاح في أي سجل أو تتبّع خطأ
        return f"<Session {self.username!r} ({self.role})>"

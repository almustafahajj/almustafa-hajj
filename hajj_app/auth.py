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

SCHEMA_VERSION = 2

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
    """مسار ملف الحساب: بجوار ملف البيانات."""
    return Path(__file__).resolve().parent.parent / "data" / "auth.json"


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


def _store(path: Path, username: str, data_key: bytes, password: str,
           recovery_key: str) -> None:
    """يكتب ملف الحساب: مفتاح البيانات مغلَّفاً بكلمة المرور وبالاسترداد."""
    password_salt = secrets.token_bytes(_SALT_BYTES)
    recovery_salt = secrets.token_bytes(_SALT_BYTES)
    _write_json(path, {
        "schema": SCHEMA_VERSION,
        "username": username,
        "kdf": "pbkdf2_sha256",
        "iterations": ITERATIONS,
        "password_salt": _b64(password_salt),
        "key_by_password": _fernet(_derive(password, password_salt))
                           .encrypt(data_key).decode("ascii"),
        "recovery_salt": _b64(recovery_salt),
        "key_by_recovery": _fernet(_derive(normalize_recovery_key(recovery_key),
                                           recovery_salt))
                           .encrypt(data_key).decode("ascii"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    })


# ------------------------------------------------------------- العمليات
def create_account(
    username: str, password: str, path: str | Path | None = None
) -> tuple["Session", str]:
    """ينشئ الحساب أول مرة.

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
    _store(path, username, data_key, password, recovery_key)
    return Session(username, data_key), recovery_key


def login(username: str, password: str, path: str | Path | None = None) -> "Session":
    """يتحقق من بيانات الدخول ويعيد جلسة تحمل مفتاح البيانات."""
    path = Path(path or default_auth_path())
    if not path.is_file():
        raise AuthError("لا يوجد حساب بعد — أنشئ حساباً أولاً.")

    stored = _read_json(path)
    stored_user = str(stored.get("username", ""))
    user_ok = hmac.compare_digest(username.strip().lower(), stored_user.lower())

    try:
        data_key = _unwrap_with_password(stored, password)
    except (AuthError, KeyError, ValueError, InvalidToken):
        data_key = None

    # لا نُفصح أي الحقلين أخطأ — وإلا صار تخمين أسماء المستخدمين أسهل
    if not user_ok or data_key is None:
        raise AuthError("اسم المستخدم أو كلمة المرور غير صحيحة.")

    if int(stored.get("schema", 1)) < SCHEMA_VERSION:
        # حساب قديم بلا مفتاح استرداد — يرقّيه `upgrade_legacy` بعد الدخول
        return Session(stored_user, data_key, needs_recovery_key=True)
    return Session(stored_user, data_key)


def _unwrap_with_password(stored: dict, password: str) -> bytes:
    """يستخرج مفتاح البيانات من ملف الحساب بكلمة المرور.

    يدعم الصيغة القديمة (schema 1) حيث كان المفتاح مشتقاً من كلمة المرور
    مباشرة — فالكشوف المشفّرة بها تبقى مقروءة بعد الترقية.
    """
    if int(stored.get("schema", 1)) < 2:
        # قديم: المفتاح نفسه = اشتقاق كلمة المرور. نتحقق عبر بصمة منفصلة.
        expected = _unb64(stored["auth_hash"])
        if not hmac.compare_digest(_derive(password, _unb64(stored["auth_salt"])), expected):
            raise AuthError("كلمة المرور غير صحيحة.")
        return _derive(password, _unb64(stored["data_salt"]))

    salt = _unb64(stored["password_salt"])
    return _fernet(_derive(password, salt)).decrypt(
        stored["key_by_password"].encode("ascii")
    )


def upgrade_legacy(
    username: str, password: str, session: "Session", path: str | Path | None = None
) -> str:
    """يرقّي حساباً قديماً إلى الصيغة ذات مفتاح الاسترداد.

    يبقي **نفس مفتاح البيانات**، فالكشف المشفّر سابقاً يظل مقروءاً بلا
    إعادة تشفير. يعيد مفتاح الاسترداد الجديد ليُعرض للمستخدم.
    """
    path = Path(path or default_auth_path())
    recovery_key = generate_recovery_key()
    _store(path, username, session.data_key, password, recovery_key)
    session.needs_recovery_key = False
    return recovery_key


def regenerate_recovery_key(
    username: str, password: str, path: str | Path | None = None
) -> str:
    """يولّد مفتاح استرداد جديداً بدل الحالي، بمعرفة كلمة المرور.

    يلزم في ثلاث حالات: ضياع الورقة المطبوعة، أو انكشاف المفتاح لغير صاحبه،
    أو إغلاق نافذة العرض قبل حفظه.

    المفتاح القديم **يبطل فوراً**، وملف البيانات لا يُمسّ — نعيد تغليف
    مفتاح البيانات لا غير.
    """
    path = Path(path or default_auth_path())
    session = login(username, password, path)          # يرفع AuthError إن أخطأ
    recovery_key = generate_recovery_key()
    _store(path, session.username, session.data_key, password, recovery_key)
    return recovery_key


def reset_with_recovery_key(
    recovery_key: str, new_password: str, path: str | Path | None = None
) -> "Session":
    """يعيد تعيين كلمة المرور بمفتاح الاسترداد.

    **ملف البيانات لا يُمسّ**: نفتح مفتاح البيانات بالاسترداد ثم نعيد
    تغليفه بكلمة المرور الجديدة. الكشف يبقى كما هو بحرف واحد.

    مفتاح الاسترداد **يبقى صالحاً** بعد العملية، فالورقة المطبوعة لا تحتاج
    استبدالاً ولا يقع المستخدم في حلقة نسيان جديدة.
    """
    path = Path(path or default_auth_path())
    if not path.is_file():
        raise AuthError("لا يوجد حساب بعد.")
    if not _recovery_is_wellformed(recovery_key):
        raise AuthError(
            f"صيغة مفتاح الاسترداد غير صحيحة — "
            f"يتكوّن من {_GROUPS * _GROUP_SIZE} حرفاً في {_GROUPS} مجموعات."
        )
    problem = password_problem(new_password)
    if problem:
        raise AuthError(problem)

    stored = _read_json(path)
    if int(stored.get("schema", 1)) < 2 or "key_by_recovery" not in stored:
        raise AuthError(
            "هذا الحساب أُنشئ قبل تفعيل مفتاح الاسترداد.\n"
            "ادخل بكلمة المرور الحالية مرة واحدة ليُنشئ البرنامج مفتاح استرداد."
        )

    normalized = normalize_recovery_key(recovery_key)
    try:
        data_key = _fernet(_derive(normalized, _unb64(stored["recovery_salt"]))).decrypt(
            stored["key_by_recovery"].encode("ascii")
        )
    except (InvalidToken, KeyError, ValueError) as exc:
        raise AuthError("مفتاح الاسترداد غير صحيح.") from exc

    username = str(stored.get("username", ""))
    _store(path, username, data_key, new_password, normalized)
    return Session(username, data_key)


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

    stored = _read_json(path)
    # نُبقي مفتاح الاسترداد الحالي إن وُجد — الورقة المطبوعة تبقى صالحة
    if int(stored.get("schema", 1)) >= 2:
        recovery_wrapped = stored["key_by_recovery"]
        recovery_salt = stored["recovery_salt"]
        password_salt = secrets.token_bytes(_SALT_BYTES)
        _write_json(path, {
            **stored,
            "schema": SCHEMA_VERSION,
            "password_salt": _b64(password_salt),
            "key_by_password": _fernet(_derive(new_password, password_salt))
                               .encrypt(session.data_key).decode("ascii"),
            "recovery_salt": recovery_salt,
            "key_by_recovery": recovery_wrapped,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        return Session(session.username, session.data_key)

    # حساب قديم: نرقّيه ونولّد مفتاح استرداد — على المُنادي عرضه
    recovery_key = generate_recovery_key()
    _store(path, session.username, session.data_key, new_password, recovery_key)
    new_session = Session(session.username, session.data_key)
    new_session.fresh_recovery_key = recovery_key
    return new_session


class Session:
    """جلسة مفتوحة: تحمل مفتاح البيانات في الذاكرة فقط، لا على القرص."""

    def __init__(self, username: str, data_key: bytes, *,
                 needs_recovery_key: bool = False) -> None:
        self.username = username
        self.data_key = data_key
        # حساب قديم دخل بنجاح لكنه بلا مفتاح استرداد بعد
        self.needs_recovery_key = needs_recovery_key
        # يُملأ عند توليد مفتاح استرداد أثناء الجلسة، ليعرضه المُنادي مرة
        self.fresh_recovery_key: str | None = None
        self._fernet = _fernet(data_key)

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
        return f"<Session {self.username!r}>"

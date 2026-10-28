# -*- coding: utf-8 -*-
"""رموز الدخول بخطوتين (TOTP — RFC 6238) بالمكتبة القياسية فقط.

تعمل مع تطبيقات المصادقة المعروفة (Google Authenticator، Microsoft
Authenticator…): رمز من ٦ أرقام يتغيّر كل ٣٠ ثانية، مشتقّ من سرّ مشترك.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

STEP = 30
DIGITS = 6
ISSUER = "المصطفى للحج والعمرة"
# الأرقام العربية/الفارسية كما تُكتب من لوحة مفاتيح عربية → أرقام لاتينية
_DIGITS_MAP = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def new_secret() -> str:
    """سرّ جديد عشوائي (١٦٠ بت) بترميز Base32 كما تطلبه تطبيقات المصادقة."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _key(secret: str) -> bytes:
    s = str(secret or "").strip().replace(" ", "").upper()
    return base64.b32decode(s + "=" * (-len(s) % 8))


def code_at(secret: str, step: int) -> str:
    """الرمز المكوّن من ٦ أرقام لخطوة زمنية معيّنة."""
    digest = hmac.new(_key(secret), struct.pack(">Q", step), hashlib.sha1).digest()
    off = digest[-1] & 0x0F
    num = struct.unpack(">I", digest[off:off + 4])[0] & 0x7FFFFFFF
    return str(num % 10 ** DIGITS).zfill(DIGITS)


def now_step(t: float | None = None) -> int:
    return int((time.time() if t is None else t) // STEP)


def clean_code(code) -> str:
    """يوحّد الرمز المُدخل: أرقام عربية → لاتينية، ويحذف المسافات والشرطات."""
    return "".join(ch for ch in str(code or "").translate(_DIGITS_MAP)
                   if ch.isascii() and ch.isdigit())


def verify(secret: str, code, *, t: float | None = None, window: int = 1,
           last_step: int | None = None) -> int | None:
    """يتحقّق من الرمز (مع سماحية ±٣٠ ثانية لفرق ساعة الجوال).

    يعيد رقم الخطوة المطابقة — يُحفظ ويُمرَّر لاحقاً كـ ``last_step`` كي لا
    يُقبل الرمز نفسه مرّتين — أو None إن لم يطابق."""
    code = clean_code(code)
    if not secret or len(code) != DIGITS:
        return None
    cur = now_step(t)
    for step in range(cur - window, cur + window + 1):
        if last_step is not None and step <= last_step:
            continue
        if hmac.compare_digest(code_at(secret, step), code):
            return step
    return None


def otpauth_uri(secret: str, account: str, issuer: str = ISSUER) -> str:
    """رابط ‎otpauth://‎ الذي يُعرض كرمز QR ليمسحه تطبيق المصادقة."""
    label = quote(f"{issuer}:{account}")
    return (f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}"
            f"&algorithm=SHA1&digits={DIGITS}&period={STEP}")


def pretty(secret: str) -> str:
    """السرّ مقسّماً مجموعات من ٤ أحرف لإدخاله يدوياً بسهولة."""
    return " ".join(secret[i:i + 4] for i in range(0, len(secret), 4))

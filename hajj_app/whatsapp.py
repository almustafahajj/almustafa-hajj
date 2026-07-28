"""رسائل واتساب الجماعية عبر روابط wa.me الرسمية (بلا أتمتة تخالف الشروط).

لكل حاج مختار يُفتح رابط ``https://wa.me/<رقم دولي>?text=<رسالة>`` في واتساب
(سطح المكتب أو الويب) برسالة مخصّصة باسمه، ويضغط المستخدم «إرسال» بنفسه.
"""

from __future__ import annotations

import re
from urllib.parse import quote

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

# العناصر النائبة المدعومة في قالب الرسالة
PLACEHOLDERS = ("{الاسم}", "{الفندق}", "{البرنامج}", "{الهاتف}", "{المتبقّي}")

DEFAULT_TEMPLATE = ("السلام عليكم {الاسم}،\n"
                    "نودّ تذكيركم بتفاصيل برنامج الحج. للاستفسار تواصلوا معنا.\n"
                    "مع تحيات المصطفى للحج والعمرة.")

# قوالب جاهزة (الاسم المعروض -> نصّ القالب)
TEMPLATES: dict[str, str] = {
    "عام (افتراضي)": DEFAULT_TEMPLATE,
    "تذكير دفعة": (
        "السلام عليكم {الاسم}،\n"
        "نذكّركم بوجود مبلغ متبقٍّ على برنامج الحج قدره {المتبقّي} ريال.\n"
        "نرجو سداده في أقرب وقت. مع تحيات المصطفى للحج والعمرة."),
    "تعليمات ما قبل السفر": (
        "السلام عليكم {الاسم}،\n"
        "اقترب موعد السفر لأداء الحج. يُرجى إحضار الجواز وبطاقة الحاج، "
        "والالتزام بموعد التجمّع. فندقكم: {الفندق}.\n"
        "مع تحيات المصطفى للحج والعمرة."),
    "ترحيب وتأكيد التسجيل": (
        "السلام عليكم {الاسم}،\n"
        "نرحّب بكم في برنامج {البرنامج}، ونؤكّد اكتمال تسجيلكم بإذن الله.\n"
        "للاستفسار تواصلوا معنا. مع تحيات المصطفى للحج والعمرة."),
}


def to_intl(phone, default_cc: str = "971") -> str | None:
    """يحوّل رقماً محلياً إلى صيغة دولية (أرقام فقط بلا +) صالحة لـ wa.me.

    - يبدأ بـ ``+`` أو ``00`` → دولي مسبقاً.
    - يبدأ بـ ``0`` → يُستبدل الصفر برمز الدولة.
    - يبدأ برمز الدولة → يُترك.
    - محلي بلا صفر → يُسبَق برمز الدولة.
    يعيد None إن كان الرقم فارغاً أو أقصر من أن يكون صحيحاً.
    """
    raw = str(phone or "").translate(_AR_DIGITS).strip()
    if not raw:
        return None
    cc = re.sub(r"\D", "", str(default_cc)) or "971"
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None
    if raw.startswith("00"):
        num = digits[2:]
    elif raw.startswith("+"):
        num = digits
    elif digits.startswith("0"):
        num = cc + digits[1:]
    elif digits.startswith(cc):
        num = digits
    else:
        num = cc + digits
    return num if len(num) >= 10 else None      # أقصر من ذلك = رقم غير صالح


def render_message(template: str, rec) -> str:
    """يملأ العناصر النائبة في القالب من بيانات الحاج."""
    name = (getattr(rec, "full_name_ar", "") or getattr(rec, "full_name_en", "")
            or "").strip()
    try:
        from .fields import compute_remaining
        remaining = compute_remaining(rec)
    except Exception:                              # noqa: BLE001
        remaining = str(getattr(rec, "remaining_amount", "") or "")
    repl = {
        "{الاسم}": name,
        "{الفندق}": str(getattr(rec, "hotel", "") or "").strip(),
        "{البرنامج}": str(getattr(rec, "program", "") or "").strip(),
        "{الهاتف}": str(getattr(rec, "phone", "") or "").strip(),
        "{المتبقّي}": remaining or "0",
    }
    out = str(template or "")
    for key, val in repl.items():
        out = out.replace(key, val)
    return out


def wa_link(phone, message: str, default_cc: str = "971") -> str | None:
    """يبني رابط wa.me برسالة مُرمّزة، أو None إن كان الرقم غير صالح."""
    num = to_intl(phone, default_cc)
    if not num:
        return None
    return f"https://wa.me/{num}?text={quote(message)}"

"""تعريف موحّد لأعمدة الحجاج — يستخدمه الجدول والإكسل وPDF معاً.

ترتيب الحقول هنا هو الترتيب من اليمين إلى اليسار كما في الكشف الورقي:
مسلسل أقصى اليمين، وملاحظات أقصى اليسار.
"""

from __future__ import annotations

import re
import unicodedata
from typing import NamedTuple


class Field(NamedTuple):
    key: str        # اسم الحقل في PassportData
    label: str      # العنوان العربي المعروض
    width: int      # عرض العمود في الجدول والإكسل
    editable: bool  # هل يمكن للمستخدم تعديله يدوياً
    in_pdf: bool    # هل يظهر في جدول PDF (المساحة محدودة على A4)


FIELDS: tuple[Field, ...] = (
    Field("serial",            "مسلسل",                  6,  False, True),
    Field("family_number",     "رقم العائلة",            11, True,  True),
    Field("reference_number",  "الرقم المرجعي",          13, True,  True),
    Field("full_name_ar",      "اسم الحاج بالعربي",      28, True,  True),
    Field("full_name_en",      "اسم الحاج بالانجليزي",   30, True,  True),
    Field("phone",             "الهاتف المتحرك",         15, True,  False),
    Field("hotel",             "الفندق",                 18, True,  True),
    Field("room_type",         "نوع الغرفة",             11, True,  True),
    Field("room_number",       "رقم الغرفة",             10, True,  True),
    Field("sex",               "الجنس",                  8,  True,  True),
    Field("nationality_ar",    "الجنسية",                13, True,  True),
    Field("birth_date",        "تاريخ الميلاد",          13, True,  True),
    Field("passport_number",   "رقم الجواز",             14, True,  True),
    Field("expiry_date",       "تاريخ انتهاء الجواز",    14, True,  False),
    Field("airline",           "الطيران",                14, True,  True),
    Field("flight_number",     "رقم الرحلة",             12, True,  False),
    Field("travel_class",      "درجة السفر",             12, True,  False),
    Field("pnr",               "PNR الحجز",              12, True,  False),
    Field("arrival_date",      "تاريخ الوصول",           13, True,  True),
    Field("arrival_time",      "وقت الوصول",             10, True,  False),
    Field("departure_date",    "تاريخ المغادرة",         13, True,  True),
    Field("departure_time",    "وقت المغادرة",           10, True,  False),
    Field("transport",         "المواصلات",              13, True,  True),
    Field("executive_service", "خدمة التنفيذي",          12, True,  False),
    Field("wheelchair",        "كرسي متحرك",             11, True,  False),
    Field("hady",              "الهدي",                  10, True,  False),
    Field("program_value",     "قيمة البرنامج",          13, True,  False),
    Field("paid_amount",       "المبلغ المدفوع",         13, True,  False),
    Field("remaining_amount",  "المبلغ المتبقي",         13, False, False),
    Field("notes",             "ملاحظات",                24, True,  False),
    Field("staff",             "الموظف المسؤول",         18, True,  False),
)

# حقول تشخيصية تظهر في جدول البرنامج فقط، ولا تُصدَّر إلى الإكسل أو PDF.
DIAG_FIELDS: tuple[Field, ...] = (
    Field("warnings",    "تنبيهات",      34, False, False),
    Field("source_file", "الملف المصدر", 22, False, False),
)

# الحقول التي تُملأ تلقائياً من الجواز — البقية يدوية.
MRZ_FILLED = frozenset({
    "full_name_en", "sex", "nationality_ar", "birth_date",
    "passport_number", "expiry_date",
})

BY_KEY = {f.key: f for f in FIELDS}
KEYS = [f.key for f in FIELDS]
PDF_FIELDS = tuple(f for f in FIELDS if f.in_pdf)
EDITABLE = tuple(f for f in FIELDS if f.editable)

DATE_KEYS = frozenset({"birth_date", "expiry_date", "arrival_date", "departure_date"})
TIME_KEYS = frozenset({"arrival_time", "departure_time"})
MONEY_KEYS = frozenset({"program_value", "paid_amount", "remaining_amount"})

# الأرقام العربية-الهندية والفارسية إلى الأرقام اللاتينية
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


# --------------------------------------------------------------- أرقام ومبالغ
def parse_amount(text) -> float | None:
    """يحوّل نص مبلغ إلى رقم، أو None إن تعذّر.

    يقبل الفواصل والأرقام العربية وأسماء العملات: "12,500 ريال" -> 12500.0
    """
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    s = str(text).translate(_DIGITS).strip()
    if not s:
        return None
    s = re.sub(r"[^\d.\-]", "", s.replace(",", ""))
    if not s or s in ("-", ".", "-."):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def format_amount(value: float | None) -> str:
    """ينسّق مبلغاً بفواصل الآلاف، ويحذف الكسر إن كان صفراً."""
    if value is None:
        return ""
    if abs(value - round(value)) < 0.005:
        return f"{round(value):,}"
    return f"{value:,.2f}"


_ONES = ["", "one", "two", "three", "four", "five", "six", "seven", "eight",
         "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
         "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
         "eighty", "ninety"]
_SCALES = ["", "thousand", "million", "billion", "trillion"]


def num_to_words_en(value) -> str:
    """يحوّل مبلغاً إلى كلمات إنجليزية (لخانة «المبلغ كتابةً» في الإيصال).

    مثال: 460000 → "four hundred sixty thousand".
    """
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        return ""
    if n == 0:
        return "zero"
    neg = n < 0
    n = abs(n)

    def _under_thousand(x: int) -> str:
        parts = []
        if x >= 100:
            parts.append(_ONES[x // 100] + " hundred")
            x %= 100
        if x >= 20:
            parts.append(_TENS[x // 10])
            if x % 10:
                parts.append(_ONES[x % 10])
        elif x > 0:
            parts.append(_ONES[x])
        return " ".join(parts)

    chunks, i = [], 0
    while n > 0:
        c = n % 1000
        if c:
            chunk = _under_thousand(c)
            if _SCALES[i]:
                chunk += " " + _SCALES[i]
            chunks.append(chunk)
        n //= 1000
        i += 1
    words = " ".join(reversed(chunks))
    return ("minus " + words) if neg else words


VAT_RATE = 0.05                 # ضريبة القيمة المضافة في الإمارات


def vat_breakdown(total, *, rate: float = VAT_RATE, mode: str = "inclusive"):
    """يفكّك مبلغاً إلى (صافي، ضريبة، إجمالي شامل).

    - ``inclusive``: المبلغ شامل الضريبة → الصافي = المبلغ ÷ (1+المعدل).
    - ``exclusive``: المبلغ صافٍ → الضريبة تُضاف فوقه.
    - ``none``: بلا ضريبة.
    """
    try:
        amt = float(total or 0.0)
    except (TypeError, ValueError):
        amt = 0.0
    if mode == "none" or not rate:
        return (amt, 0.0, amt)
    if mode == "exclusive":
        vat = amt * rate
        return (amt, vat, amt + vat)
    net = amt / (1.0 + rate)          # inclusive (الافتراضي)
    return (net, amt - net, amt)


def normalize_time(text) -> str:
    """يوحّد الوقت إلى صيغة HH:MM.

    يقبل: "14:30" و"2:30 PM" و"1430" و"٠٩:٤٥".
    يُعيد النص كما هو إن تعذّر الفهم، حتى لا نُتلف إدخال المستخدم.
    """
    if not text:
        return ""
    s = str(text).translate(_DIGITS).strip().upper()
    s = s.replace("ص", "AM").replace("م", "PM")

    pm = "PM" in s
    am = "AM" in s
    s = s.replace("AM", "").replace("PM", "").strip()

    m = re.fullmatch(r"(\d{1,2})[:.\s]?(\d{2})", s)
    if not m:
        m = re.fullmatch(r"(\d{1,2})", s)
        if not m:
            return str(text).strip()
        hour, minute = int(m.group(1)), 0
    else:
        hour, minute = int(m.group(1)), int(m.group(2))

    if pm and hour < 12:
        hour += 12
    if am and hour == 12:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return str(text).strip()
    return f"{hour:02d}:{minute:02d}"


def compute_remaining(record) -> str:
    """يحسب المبلغ المتبقي = قيمة البرنامج − المبلغ المدفوع.

    يعيد نصاً فارغاً إن لم تكن القيمتان رقمين، فلا نعرض رقماً مضللاً.
    """
    total = parse_amount(getattr(record, "program_value", ""))
    paid = parse_amount(getattr(record, "paid_amount", ""))
    if total is None:
        return ""
    return format_amount(total - (paid or 0))


def row_dict(record, serial: int) -> dict:
    """يبني صف عرض/تصدير واحداً: بيانات السجل + المسلسل + المتبقي المحسوب.

    مركزية هذه الدالة تضمن تطابق الجدول والإكسل وPDF دائماً.
    """
    d = record.to_dict()
    d["serial"] = str(serial)
    d["remaining_amount"] = compute_remaining(record)
    return d


# ------------------------------------------------------- مطابقة أعمدة الاستيراد
IMPORT_ALIASES: dict[str, str] = {}


def _norm(text: str) -> str:
    """يوحّد العنوان للمقارنة: حروف صغيرة، بلا فراغات أو رموز أو تشكيل."""
    text = unicodedata.normalize("NFKC", str(text)).strip().lower()
    text = text.replace("ـ", "")
    text = re.sub(r"[ً-ْ]", "", text)
    text = re.sub(r"[أإآ]", "ا", text)
    text = re.sub(r"[ىي]", "ي", text)
    text = text.replace("ة", "ه")
    text = re.sub(r"[\s_\-/\\.:()]+", "", text)
    return text


def _alias(key: str, *names: str) -> None:
    for n in names:
        IMPORT_ALIASES[_norm(n)] = key


for _f in FIELDS:
    _alias(_f.key, _f.label, _f.key)

_alias("serial", "م", "ت", "no", "s/n", "sn", "رقم مسلسل", "تسلسل", "الرقم")
_alias("family_number", "family no", "family number", "رقم العايله", "العائلة",
       "رقم الاسره", "الاسرة")
_alias("reference_number", "ref", "ref no", "reference", "المرجع", "رقم المرجع",
       "الرقم المرجعى", "booking ref", "رقم المرجعي", "المرجعي", "مرجع",
       "رقم الطلب", "reference no")
_alias("full_name_ar", "arabic name", "الاسم بالعربي", "الاسم العربي",
       "اسم الحاج", "الاسم", "اسم الحاج بالعربى",
       # كشوف الجهات الرسمية تسمّيه بعدد أجزائه
       "الاسم الرباعي", "الاسم الثلاثي", "الاسم الكامل", "الاسم كاملا",
       "اسم الحاج الرباعي", "الاسم رباعي")
_alias("full_name_en", "name", "full name", "english name", "passport name",
       "الاسم بالانجليزي", "الاسم اللاتيني", "اسم الحاج بالانجليزى",
       # بلا حرف الجر — شائع في كشوف الطيران والفنادق
       "الاسم الانجليزي", "الاسم الإنجليزي", "الاسم بالإنجليزية",
       "الاسم اللاتينى", "name in english", "english full name",
       "name as in passport", "passenger name", "guest name")

# الاسم اللاتيني كثيراً ما يُقسَّم عمودين في كشوف الطيران والفنادق.
# نقرأ كلاً منهما على حدة ثم يدمجهما `import_excel` في الاسم الكامل.
_alias("given_names_en", "first name", "firstname", "given name", "given names",
       "الاسم الاول", "الاسم الأول", "الاسم الشخصي")
_alias("surname_en", "last name", "lastname", "surname", "family name",
       "اسم العائلة", "اسم العائله", "اللقب", "لقب العائلة")
_alias("phone", "mobile", "phone", "phone number", "الجوال", "الهاتف",
       "رقم الجوال", "رقم الهاتف", "الجوال المتحرك", "المتحرك",
       "هاتف الامارات", "هاتف الإمارات", "هاتف السعودية", "mobile no",
       "contact", "contact no")
_alias("hotel", "hotel name", "الفندق", "اسم الفندق", "السكن")
_alias("room_type", "room type", "نوع الغرفه", "التسكين", "فئة الغرفة",
       "نوع السكن", "درجة الغرفة")
_alias("room_number", "room no", "room number", "room", "الغرفه", "رقم الغرفه",
       "رقم الغرفة", "غرفة", "رقم السكن")
_alias("sex", "gender", "النوع", "الجنس")
_alias("nationality_ar", "nationality", "الجنسيه", "الدولة", "البلد", "country")
_alias("birth_date", "dob", "date of birth", "birthdate", "الميلاد",
       "تاريخ الولاده", "تاريخ الميلاد")
_alias("passport_number", "passport", "passport no", "passport number",
       "رقم جواز السفر", "جواز السفر", "الجواز")
_alias("expiry_date", "expiry", "date of expiry", "expiration",
       "تاريخ الانتهاء", "انتهاء الجواز", "صلاحية الجواز",
       "passport expiry", "pass validity", "passport validity",
       "تاريخ انتهاء جواز السفر")
_alias("airline", "flight", "airline", "carrier", "الطيران", "شركة الطيران",
       "الرحلة")
_alias("flight_number", "flight no", "flight number", "رقم الرحلة", "رقم الرحله",
       "رقم رحلة الطيران")
_alias("travel_class", "class", "cabin", "درجة السفر", "درجه السفر", "الدرجة",
       "درجة الرحلة", "فئة السفر", "class (j or y)")
_alias("pnr", "pnr", "record locator", "booking ref", "booking reference",
       "رقم الحجز", "الحجز", "بي ان ار")
_alias("staff", "الموظف المسؤول", "المسؤول", "الموظف", "staff", "responsible",
       "agent", "handler", "مسؤول المجموعة", "المشرف")
_alias("arrival_date", "arrival", "arrival date", "الوصول", "تاريخ القدوم")
_alias("arrival_time", "arrival time", "وقت القدوم", "ساعة الوصول")
_alias("departure_date", "departure", "departure date", "المغادره",
       "تاريخ السفر", "تاريخ العوده")
_alias("departure_time", "departure time", "وقت السفر", "ساعة المغادرة")
_alias("transport", "transportation", "bus", "النقل", "المواصلات", "الباص",
       "سيارة خاصة", "سياره خاصه", "نقل خاص", "المواصلة")
_alias("hady", "hadi", "sacrifice", "الهدى", "الاضحيه", "الهدي")
_alias("wheelchair", "wheel chair", "كرسي متحرك", "الكرسي المتحرك", "عربة")
_alias("executive_service", "executive", "vip", "خدمة تنفيذيه", "التنفيذي",
       "خدمه التنفيذي", "تنفيذي", "خدمة VIP")
_alias("program_value", "program value", "package", "price", "total",
       "قيمة البرنامج", "قيمه البرنامج", "سعر البرنامج", "الاجمالي", "المبلغ",
       "قيمة البرنامج مع الهدي", "قيمة البرنامج والهدي", "قيمه البرنامج مع الهدي")
_alias("paid_amount", "paid", "amount paid", "المدفوع", "المبلغ المدفوع",
       "الدفعات", "المسدد")
_alias("remaining_amount", "remaining", "balance", "due", "المتبقي",
       "المبلغ المتبقى", "الباقي", "الرصيد")
_alias("notes", "note", "remarks", "comment", "ملاحظه", "ملاحظات", "البيان")


def match_column(header: str) -> str | None:
    """يطابق عنوان عمود من ملف إكسل مع مفتاح حقل معروف، أو None.

    يتسامح مع اللواحق التوضيحية بين قوسين وبعد الشرطة، فكثير من الكشوف
    تكتب `DOB (DD-MM-YYYY)` أو `الجنسية - Nationality`.
    """
    text = str(header)
    direct = IMPORT_ALIASES.get(_norm(text))
    if direct:
        return direct

    # نجرّب النص بعد إزالة ما بين الأقواس، ثم كل شطر حول الفاصل
    stripped = re.sub(r"[(\[{].*?[)\]}]", " ", text)
    if stripped.strip() and stripped != text:
        found = IMPORT_ALIASES.get(_norm(stripped))
        if found:
            return found

    for part in re.split(r"[-–—/|]", stripped):
        part = part.strip()
        if len(part) < 2:
            continue
        found = IMPORT_ALIASES.get(_norm(part))
        if found:
            return found
    return None

"""قراءة وتحليل سطري MRZ من الجواز (المواصفة ICAO 9303 - نوع TD3).

سطرا MRZ في أسفل الجواز، كل سطر 44 حرفاً:

    P<SAUALSHEHABI<<AYMAN<MOHAMMED<<<<<<<<<<<<<<<
    A1234567<8SAU8501015M3001012<<<<<<<<<<<<<<04

هذا الملف لا يعتمد على أي خدمة خارجية — تحليل نصي بحت.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, asdict
from datetime import date, datetime

# خريطة رموز الدول (ISO 3166 alpha-3) إلى الاسم العربي.
# نغطي الدول الأكثر وروداً في مواسم الحج، وما عداها يظهر بالرمز كما هو.
COUNTRY_AR = {
    "SAU": "السعودية", "EGY": "مصر", "PAK": "باكستان", "IND": "الهند",
    "IDN": "إندونيسيا", "BGD": "بنغلاديش", "TUR": "تركيا", "NGA": "نيجيريا",
    "IRN": "إيران", "MAR": "المغرب", "DZA": "الجزائر", "TUN": "تونس",
    "LBY": "ليبيا", "SDN": "السودان", "YEM": "اليمن", "SYR": "سوريا",
    "JOR": "الأردن", "LBN": "لبنان", "IRQ": "العراق", "PSE": "فلسطين",
    "KWT": "الكويت", "BHR": "البحرين", "QAT": "قطر", "ARE": "الإمارات",
    "OMN": "عُمان", "MYS": "ماليزيا", "AFG": "أفغانستان", "SOM": "الصومال",
    "MRT": "موريتانيا", "SEN": "السنغال", "MLI": "مالي", "NER": "النيجر",
    "TCD": "تشاد", "ETH": "إثيوبيا", "KEN": "كينيا", "TZA": "تنزانيا",
    "UZB": "أوزبكستان", "KAZ": "كازاخستان", "AZE": "أذربيجان", "ALB": "ألبانيا",
    "BIH": "البوسنة والهرسك", "GBR": "بريطانيا", "USA": "أمريكا",
    "FRA": "فرنسا", "DEU": "ألمانيا", "CAN": "كندا", "AUS": "أستراليا",
    "CHN": "الصين", "RUS": "روسيا", "ZAF": "جنوب أفريقيا", "THA": "تايلاند",
    "PHL": "الفلبين", "LKA": "سريلانكا", "MDV": "المالديف", "BRN": "بروناي",
    "SGP": "سنغافورة", "GIN": "غينيا", "CIV": "ساحل العاج", "GHA": "غانا",
    "CMR": "الكاميرون", "UGA": "أوغندا", "DJI": "جيبوتي", "COM": "جزر القمر",
}

# الأوزان الدورية المستخدمة في حساب خانة التحقق حسب ICAO 9303.
_WEIGHTS = (7, 3, 1)

# تصحيح الخلط الشائع في OCR بين الأرقام والحروف داخل الحقول الرقمية البحتة.
_TO_DIGIT = str.maketrans({"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1",
                           "Z": "2", "S": "5", "B": "8", "G": "6"})
# والعكس داخل حقول الحروف البحتة (رمز الدولة مثلاً).
_TO_ALPHA = str.maketrans({"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B"})


class MRZError(Exception):
    """يُرفع عندما يتعذّر العثور على سطري MRZ صالحين أو تحليلهما."""


@dataclass
class PassportData:
    """بيانات الحاج. كل الحقول نصية لتسهيل التصدير والتحرير."""

    # ---- تُملأ تلقائياً من الجواز ----
    full_name_en: str = ""
    passport_number: str = ""
    nationality_ar: str = ""
    sex: str = ""
    birth_date: str = ""
    expiry_date: str = ""

    # ---- يملؤها المستخدم: بيانات الحاج ----
    family_number: str = ""
    reference_number: str = ""
    full_name_ar: str = ""
    phone: str = ""

    # ---- برنامج الحملة والمجموعة ----
    program: str = ""
    group: str = ""

    # ---- الإقامة والخدمات ----
    hotel: str = ""
    room_type: str = ""
    room_number: str = ""
    transport: str = ""
    hady: str = ""
    wheelchair: str = ""
    executive_service: str = ""

    # ---- السفر ----
    airline: str = ""
    flight_number: str = ""
    travel_class: str = ""
    pnr: str = ""
    arrival_date: str = ""
    arrival_time: str = ""
    departure_date: str = ""
    departure_time: str = ""

    # ---- المالية ----
    program_value: str = ""
    paid_amount: str = ""

    notes: str = ""
    staff: str = ""

    # ---- التأشيرة وتصريح الحج ----
    visa_number: str = ""
    visa_status: str = ""
    permit_status: str = ""          # تصريح الحج (نُسُك/مسار)
    masar_number: str = ""
    # ---- المحرم ----
    mahram_name: str = ""
    mahram_relation: str = ""
    # ---- الصحة والطوارئ ----
    blood_type: str = ""
    medical_conditions: str = ""
    medications: str = ""
    vaccination: str = ""
    insurance: str = ""
    emergency_name: str = ""
    emergency_phone: str = ""
    emergency_relation: str = ""

    # ---- حقول داخلية: تُقرأ من الجواز لكنها لا تظهر في الكشف ----
    surname_en: str = ""
    given_names_en: str = ""
    nationality: str = ""
    issuing_country: str = ""
    personal_number: str = ""

    # معرّف صور الحاج (الجواز والصورة الشخصية) المخزّنة مشفّرة داخلياً
    image_id: str = ""

    # ---- بيانات تشخيصية ----
    source_file: str = ""
    checksum_ok: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["warnings"] = " | ".join(self.warnings)
        return d


def _char_value(ch: str) -> int:
    """قيمة الحرف في حساب خانة التحقق: رقم=قيمته، A=10..Z=35، '<'=0."""
    if ch.isdigit():
        return int(ch)
    if "A" <= ch <= "Z":
        return ord(ch) - 55
    return 0


def check_digit(data: str) -> str:
    """يحسب خانة التحقق لسلسلة حسب ICAO 9303."""
    total = sum(_char_value(ch) * _WEIGHTS[i % 3] for i, ch in enumerate(data))
    return str(total % 10)


def _parse_date(yymmdd: str, *, future_window: bool) -> str:
    """يحوّل YYMMDD إلى YYYY-MM-DD.

    MRZ لا يخزّن القرن، فنستنتجه: تواريخ الانتهاء تقع في المستقبل القريب،
    وتواريخ الميلاد في الماضي.
    """
    if not re.fullmatch(r"\d{6}", yymmdd):
        return ""
    yy, mm, dd = int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6])
    current_yy = date.today().year % 100
    if future_window:
        # الانتهاء: نفترض خلال ~ 80 سنة قادمة
        century = 2000 if yy <= current_yy + 80 else 1900
    else:
        # الميلاد: أي سنة أكبر من السنة الحالية تعني القرن الماضي
        century = 1900 if yy > current_yy else 2000
    try:
        return date(century + yy, mm, dd).isoformat()
    except ValueError:
        return ""


def _clean_line(line: str) -> str:
    """يوحّد السطر: حروف كبيرة، إزالة الفراغات، تحويل الرموز الشبيهة بـ '<'."""
    line = unicodedata.normalize("NFKC", line).upper()
    line = line.replace("«", "<<").replace("‹", "<")
    # OCR كثيراً ما يقرأ '<' كـ K أو ( أو ﹤
    line = re.sub(r"[«‹（(\[{]", "<", line)
    line = re.sub(r"[^A-Z0-9<]", "", line)
    return line


def find_mrz_lines(text: str) -> tuple[str, str]:
    """يستخرج سطري MRZ من نص OCR كامل.

    يبحث عن سطرين متتاليين طولهما ~44 حرفاً من مجموعة أحرف MRZ،
    ويقبل انحرافاً بسيطاً في الطول لأن OCR قد يبتلع أو يضيف حرفاً.
    """
    candidates = []
    for raw in text.splitlines():
        cleaned = _clean_line(raw)
        # سطر MRZ الحقيقي طويل وغني بالرمز '<'
        if len(cleaned) >= 30 and cleaned.count("<") >= 2:
            candidates.append(cleaned)

    for i in range(len(candidates) - 1):
        first, second = candidates[i], candidates[i + 1]
        # السطر الأول من TD3 يبدأ بـ P
        if first.startswith("P") and 38 <= len(first) <= 50 and 38 <= len(second) <= 50:
            return _pad(first), _pad(second)

    # محاولة أخيرة: آخر سطرين مرشحين
    if len(candidates) >= 2:
        return _pad(candidates[-2]), _pad(candidates[-1])

    raise MRZError("لم يتم العثور على سطري MRZ في الصورة")


def _pad(line: str) -> str:
    """يضبط طول السطر على 44 حرفاً بالقص أو الحشو بـ '<'."""
    return line[:44].ljust(44, "<")


# تكرار حرف واحد 3 مرات فأكثر: لا يوجد في أسماء حقيقية، وهو في الغالب
# رمز الحشو '<' قرأه OCR حرفاً (K أو C أو I).
# ملاحظة: '<' نفسه مستثنى — تكراره حشو مشروع في جوازات ذات اسم واحد.
_REPEAT_RUN = re.compile(r"([A-Z0-9])\1{2,}")
# تكرار 6 مرات فأكثر دليل قاطع على قراءة فاسدة لا تُصلَح
_GARBAGE_RUN = re.compile(r"([A-Z0-9])\1{5,}")


def _is_plausible_name(name: str) -> bool:
    """فحص معقولية الاسم اللاتيني.

    حقل الاسم في MRZ لا يملك خانة تحقق، فلا سبيل للتأكد رياضياً.
    نكتفي بفحوص بنيوية: وجود حرف علة، وعدم سيطرة حرف واحد على الاسم.
    """
    letters = name.replace(" ", "")
    if len(letters) < 2:
        return False
    if not set(letters) & set("AEIOU"):
        return False
    # حرف واحد يشكّل أكثر من نصف الاسم = قراءة فاسدة
    most_common = max(letters.count(c) for c in set(letters))
    return most_common / len(letters) <= 0.5


def _clean_name(part: str) -> tuple[str, str]:
    """ينظّف جزءاً من حقل الاسم. يعيد (الاسم، الجودة).

    الجودة: "ok" أو "noisy" (يحتاج مراجعة) أو "garbage" (غير قابل للاستعمال).
    """
    if _GARBAGE_RUN.search(part):
        return "", "garbage"

    normalized = _REPEAT_RUN.sub("<", part)
    noisy = normalized != part

    kept = []
    for t in (t for t in normalized.split("<") if t):
        if len(t) == 1:
            # حرف مفرد بين الأسماء: شبه مؤكد أنه فاصل '<' أُسيئت قراءته
            noisy = True
            continue
        kept.append(t)

    name = " ".join(kept).strip()
    if not name:
        # الجزء كان حشواً خالصاً (طبيعي في اسم بلا أوسط) أو فاسداً
        return "", "ok" if not part.replace("<", "").strip() else "garbage"
    if not _is_plausible_name(name):
        return "", "garbage"
    return name, "noisy" if noisy else "ok"


def _clean_optional(field: str) -> str:
    """ينظّف حقل البيانات الاختياري (الرقم الشخصي).

    هذا الحقل فارغ في أغلب الجوازات، أي حشو '<' خالص. حين يقرأ OCR الحشو
    حرفاً يخرج شيء مثل "KKKK" — وهو ليس رقماً شخصياً بل ضجيج. نحذفه لأن
    حقل الحشو المقروء خطأً لا يحمل معلومة أصلاً.
    """
    value = field.replace("<", "").strip()
    if not value:
        return ""
    # كله حرف واحد مكرر (بلا أرقام) = حشو أُسيئت قراءته
    if len(value) >= 3 and len(set(value)) == 1 and value.isalpha():
        return ""
    return value


def parse_mrz(line1: str, line2: str) -> PassportData:
    """يحلّل سطري MRZ (TD3) إلى بيانات منظّمة."""
    line1, line2 = _pad(_clean_line(line1)), _pad(_clean_line(line2))
    data = PassportData()

    # ---- السطر الأول: النوع، الدولة المصدرة، الاسم ----
    data.issuing_country = line1[2:5].translate(_TO_ALPHA)
    name_field = line1[5:44]
    surname_part, _, given_part = name_field.partition("<<")
    data.surname_en, s_quality = _clean_name(surname_part)
    data.given_names_en, g_quality = _clean_name(given_part)

    if "garbage" in (s_quality, g_quality):
        # قراءة فاسدة: تركها يزرع اسماً خاطئاً في الكشف قد لا ينتبه له أحد.
        # نتركه فارغاً مع تنبيه صريح — الفراغ أوضح من نص مشوّه.
        data.surname_en = data.given_names_en = data.full_name_en = ""
        data.warnings.append("تعذّرت قراءة الاسم من الجواز — أدخله يدوياً")
    else:
        data.full_name_en = " ".join(
            p for p in (data.given_names_en, data.surname_en) if p
        )
        if "noisy" in (s_quality, g_quality):
            data.warnings.append("الاسم قد يحتوي أخطاء قراءة — يُرجى مراجعته")

    # ---- السطر الثاني: الرقم، الجنسية، الميلاد، الجنس، الانتهاء ----
    data.passport_number = line2[0:9].replace("<", "").strip()
    num_cd = line2[9]
    data.nationality = line2[10:13].translate(_TO_ALPHA)
    birth_raw = line2[13:19].translate(_TO_DIGIT)
    birth_cd = line2[19]
    sex_raw = line2[20]
    expiry_raw = line2[21:27].translate(_TO_DIGIT)
    expiry_cd = line2[27]
    personal = line2[28:42]
    personal_cd = line2[42]
    final_cd = line2[43]

    data.nationality_ar = COUNTRY_AR.get(data.nationality, data.nationality)
    data.sex = {"M": "ذكر", "F": "أنثى"}.get(sex_raw, "غير محدد")
    data.birth_date = _parse_date(birth_raw, future_window=False)
    data.expiry_date = _parse_date(expiry_raw, future_window=True)
    data.personal_number = _clean_optional(personal)

    # ---- التحقق من خانات التدقيق ----
    checks = {
        "رقم الجواز": (line2[0:9], num_cd),
        "تاريخ الميلاد": (birth_raw, birth_cd),
        "تاريخ الانتهاء": (expiry_raw, expiry_cd),
    }
    if personal_cd.isdigit():
        checks["الرقم الشخصي"] = (personal, personal_cd)

    checksum_failures = []
    for label, (value, expected) in checks.items():
        if not expected.isdigit() or check_digit(value) != expected:
            checksum_failures.append(f"خانة التحقق لا تطابق: {label}")

    # checksum_ok يعكس خانات الحقول وحدها (الجواز، الميلاد، الانتهاء).
    # تحذيرات الاسم منفصلة لأن حقل الاسم لا يملك خانة تحقق أصلاً.
    data.checksum_ok = not checksum_failures
    data.warnings.extend(checksum_failures)

    # الخانة الإجمالية تغطي السطر كله بما فيه منطقة الحشو، فهي أكثر
    # الخانات عرضة لضجيج OCR. فشلها وحده لا يعني أن الحقول المتحقَّقة
    # خاطئة، لكنه يعني أن الجنسية والجنس — ولا خانة تحقق لهما — قد
    # تكونان مقروءتين خطأً، فننبّه دون إلغاء التحقق الناجح.
    composite = line2[0:10] + line2[13:20] + line2[21:43]
    if not final_cd.isdigit() or check_digit(composite) != final_cd:
        data.warnings.append(
            "خانة التحقق الإجمالية لا تطابق — راجع الجنسية والجنس"
            if data.checksum_ok
            else "خانة التحقق الإجمالية لا تطابق"
        )

    if not data.birth_date:
        data.warnings.append("تعذّر قراءة تاريخ الميلاد")
    if not data.expiry_date:
        data.warnings.append("تعذّر قراءة تاريخ الانتهاء")
    if not data.passport_number:
        data.warnings.append("تعذّر قراءة رقم الجواز")

    return data


def parse_text(text: str) -> PassportData:
    """يستخرج سطري MRZ من نص OCR ثم يحلّلهما."""
    line1, line2 = find_mrz_lines(text)
    return parse_mrz(line1, line2)

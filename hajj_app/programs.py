"""برامج الحملة: ثلاثة برامج (الأول/الثاني/الثالث) لكلٍّ بيانات رحلته
وتكاليف غرفه وخدماته الإضافية. تُحفَظ في الإعدادات ويحدّدها المستخدم.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from dataclasses import fields as dc_fields

PROGRAM_NAMES = ("البرنامج الأول", "البرنامج الثاني", "البرنامج الثالث")
TRANSPORT_OPTIONS = ("باص", "جيمس")


@dataclass
class Program:
    """برنامج حملة واحد — بيانات الرحلة والتكاليف والخدمات."""

    travel_date: str = ""
    departure_airport: str = ""
    return_date: str = ""
    arrival_airport: str = ""
    carrier: str = ""
    hotel: str = ""
    cost_single: str = ""
    cost_double: str = ""
    cost_triple: str = ""
    cost_quad: str = ""
    transport: str = "باص"
    svc_jeems: str = "40000"
    svc_wheelchair: str = "1000"
    svc_wheelchair_escort: str = "5000"
    svc_hady: str = "1000"
    svc_business_ticket: str = "7000"
    # أرقام وأوقات الرحلة (ذهاب/عودة)
    flight_out: str = ""
    report_out: str = ""
    takeoff_out: str = ""
    land_out: str = ""
    flight_ret: str = ""
    report_ret: str = ""
    takeoff_ret: str = ""
    land_ret: str = ""


# مجموعات الحقول للعرض: (عنوان المجموعة، [(المفتاح، التسمية، النوع)])
FIELD_GROUPS = (
    ("بيانات الرحلة", (
        ("travel_date", "تاريخ السفر", "text"),
        ("departure_airport", "مطار المغادرة", "text"),
        ("return_date", "تاريخ العودة", "text"),
        ("arrival_airport", "مطار الوصول", "text"),
        ("carrier", "الناقل", "text"),
        ("hotel", "اسم الفندق", "text"),
    )),
    ("أرقام وأوقات الرحلة", (
        ("flight_out", "رقم رحلة الذهاب", "text"),
        ("report_out", "الحضور للمطار (ذهاب)", "text"),
        ("takeoff_out", "وقت الإقلاع (ذهاب)", "text"),
        ("land_out", "وقت الوصول (ذهاب)", "text"),
        ("flight_ret", "رقم رحلة العودة", "text"),
        ("report_ret", "التحرّك للمطار (عودة)", "text"),
        ("takeoff_ret", "وقت الإقلاع (عودة)", "text"),
        ("land_ret", "وقت الوصول (عودة)", "text"),
    )),
    ("تكلفة الشخص في الغرفة", (
        ("cost_single", "المفردة", "money"),
        ("cost_double", "الثنائية", "money"),
        ("cost_triple", "الثلاثية", "money"),
        ("cost_quad", "الرباعية", "money"),
    )),
    ("المواصلات", (
        ("transport", "المواصلات (باص/جيمس)", "transport"),
    )),
    ("الخدمات الإضافية", (
        ("svc_jeems", "جيمس", "money"),
        ("svc_wheelchair", "كرسي متحرك", "money"),
        ("svc_wheelchair_escort", "كرسي متحرك مع مرافق", "money"),
        ("svc_hady", "الهدي", "money"),
        ("svc_business_ticket", "تذكرة سفر رجال أعمال", "money"),
    )),
)

PROGRAM_KEYS = tuple(f.name for f in dc_fields(Program))


def default_programs() -> list[Program]:
    """ثلاثة برامج بالقيم الافتراضية (أسعار الخدمات الإضافية القياسية)."""
    return [Program() for _ in PROGRAM_NAMES]


def load_programs(settings: dict) -> list[Program]:
    """يحمّل البرامج الثلاثة من الإعدادات، مع إكمال الناقص بالافتراضي."""
    progs = default_programs()
    raw = settings.get("programs") if isinstance(settings, dict) else None
    if isinstance(raw, list):
        for i, item in enumerate(raw[:len(progs)]):
            if isinstance(item, dict):
                progs[i] = Program(**{
                    k: str(item.get(k, getattr(progs[i], k))) for k in PROGRAM_KEYS
                })
    return progs


def programs_to_dicts(progs) -> list[dict]:
    """يحوّل البرامج إلى قوائم قواميس للحفظ في الإعدادات (JSON)."""
    return [asdict(p) for p in progs]


def program_by_name(progs, name: str):
    """يعيد البرنامج بالاسم (البرنامج الأول/الثاني/الثالث) أو None."""
    name = str(name or "").strip()
    for idx, pname in enumerate(PROGRAM_NAMES):
        if name == pname and idx < len(progs):
            return progs[idx]
    return None


# خريطة التعبئة التلقائية: حقل البرنامج -> حقل سجل الحاج
AUTOFILL_MAP = (
    ("hotel", "hotel"),
    ("carrier", "airline"),
    ("travel_date", "arrival_date"),
    ("return_date", "departure_date"),
    ("transport", "transport"),
)


def _service_on(value) -> bool:
    """هل الخدمة مفعّلة؟ (قيمة غير فارغة وليست نفياً)."""
    s = str(value or "").strip().lower()
    return bool(s) and s not in (
        "لا", "بدون", "0", "0.0", "-", "none", "no", "false", "لا يوجد")


def program_cost(prog, *, room_type: str = "", wheelchair: str = "",
                 hady: str = "", executive_service: str = "",
                 travel_class: str = "", transport: str = ""):
    """يحسب تكلفة الحاج من البرنامج: سعر الغرفة (حسب نوعها) + الخدمات المفعّلة.

    يعيد (الإجمالي، [(الوصف، المبلغ)]). الخدمات تُستنتج من حقول السجل:
    كرسي متحرك (مع/بلا مرافق)، الهدي، جيمس (خدمة التنفيذي/المواصلات)،
    وتذكرة رجال الأعمال (درجة السفر).
    """
    from .fields import parse_amount
    from .rooming import room_capacity

    lines: list[tuple[str, float]] = []

    def price(key: str) -> float:
        return parse_amount(getattr(prog, key, "")) or 0.0

    if str(room_type or "").strip():
        cap = room_capacity(room_type)
        room = {1: ("cost_single", "غرفة مفردة"),
                2: ("cost_double", "غرفة ثنائية"),
                3: ("cost_triple", "غرفة ثلاثية"),
                4: ("cost_quad", "غرفة رباعية")}.get(cap)
        if room:
            amt = price(room[0])
            if amt:
                lines.append((room[1], amt))

    wl = str(wheelchair or "").strip()
    if _service_on(wl):
        if "مرافق" in wl:
            amt = price("svc_wheelchair_escort")
            if amt:
                lines.append(("كرسي متحرك مع مرافق", amt))
        else:
            amt = price("svc_wheelchair")
            if amt:
                lines.append(("كرسي متحرك", amt))

    if _service_on(hady):
        amt = price("svc_hady")
        if amt:
            lines.append(("الهدي", amt))

    if "جيمس" in f"{executive_service} {transport}":
        amt = price("svc_jeems")
        if amt:
            lines.append(("جيمس", amt))

    tc = str(travel_class or "").lower()
    if any(w in tc for w in ("business", "أعمال", "رجال", "j", "c")):
        amt = price("svc_business_ticket")
        if amt:
            lines.append(("تذكرة رجال أعمال", amt))

    total = sum(a for _l, a in lines)
    return total, lines

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

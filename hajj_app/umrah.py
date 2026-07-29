"""نموذج **برنامج العمرة** (فوج/رحلة) وتخزينه وتسعيره.

برنامج العمرة يُنظَّم حسب البرامج: كل برنامج له تواريخ سفر وعودة، وفندقا
مكة والمدينة، ورحلتا الطيران (بأرقامهما وأوقاتهما)، وأسعار الفرد حسب نوع
الغرفة (مفرد/ثنائي/ثلاثي/رباعي)، وباقة خدمات إضافية لكلٍّ سعره، والنقل
الداخلي. كل معتمر يرتبط ببرنامج عبر الحقل ``trip`` في سجلّه.

تُحفظ البرامج في إعدادات وضع العمرة (``settings_umrah.json``) تحت المفتاح
``umrah_trips`` — ليست بيانات حسّاسة فلا تُشفَّر.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields as _dc_fields

# أنواع الغرف: (مفتاح السعر، الاسم، عدد الأشخاص في الغرفة)
ROOM_TYPES = (
    ("price_single", "مفرد", 1),
    ("price_double", "ثنائي", 2),
    ("price_triple", "ثلاثي", 3),
    ("price_quad", "رباعي", 4),
)

# باقة الخدمات الإضافية المتاحة (يُدخل لكلٍّ سعرها في البرنامج)
DEFAULT_SERVICES = (
    "زيارة المدينة المنوّرة",
    "تأمين طبّي",
    "استقبال وتوديع بالمطار",
    "الوجبات (إفطار/عشاء)",
    "جولات وزيارات مكة المكرّمة",
    "عربة كهربائية / كرسي متحرّك",
    "باقة الإحرام والهدايا",
    "شريحة اتصال / إنترنت",
)


def _num(value) -> float:
    """يحوّل نصّاً إلى رقم (يتجاهل الفواصل)، ويعيد 0 عند التعذّر."""
    try:
        return float(str(value).replace(",", "").replace("درهم", "").strip() or 0)
    except (ValueError, TypeError):
        return 0.0


@dataclass
class UmrahTrip:
    """برنامج عمرة واحد بكل تفاصيله وأسعاره."""

    code: str = ""                 # رمز البرنامج (فريد) — يربط المعتمرين به
    name: str = ""                 # اسم البرنامج
    depart_date: str = ""
    return_date: str = ""
    makkah_hotel: str = ""
    makkah_nights: str = ""
    madinah_hotel: str = ""
    madinah_nights: str = ""
    airline: str = ""
    # رحلة الذهاب: رقم الرحلة ووقت المغادرة ووقت الوصول
    flight_out: str = ""
    out_depart_time: str = ""
    out_arrive_time: str = ""
    # رحلة العودة
    flight_ret: str = ""
    ret_depart_time: str = ""
    ret_arrive_time: str = ""
    # أسعار الفرد حسب نوع الغرفة
    price_single: str = ""
    price_double: str = ""
    price_triple: str = ""
    price_quad: str = ""
    transport: str = ""            # ملاحظة النقل الداخلي الافتراضية
    capacity: str = ""             # السعة (عدد المقاعد)
    # الخدمات المتاحة: قائمة {"name":..., "price":...}
    services: list = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


_TRIP_FIELDS = {f.name for f in _dc_fields(UmrahTrip)}


def _norm_services(raw) -> list:
    """يوحّد الخدمات إلى قائمة {name, price} (يدعم الصيغة القديمة list[str])."""
    out = []
    for it in raw if isinstance(raw, list) else []:
        if isinstance(it, dict):
            out.append({"name": str(it.get("name", "")),
                        "price": str(it.get("price", ""))})
        else:
            out.append({"name": str(it), "price": ""})
    return out


def trip_from_dict(data: dict) -> UmrahTrip:
    """يبني برنامجاً من قاموس محفوظ (يتجاهل المفاتيح الغريبة ويرحّل القديم)."""
    data = data or {}
    clean = {k: v for k, v in data.items() if k in _TRIP_FIELDS}
    # ترحيل السعر القديم المفرد إلى سعر الثنائي إن لم تكن الأسعار الجديدة موجودة
    if "price" in data and not any(clean.get(k) for k, _n, _c in ROOM_TYPES):
        clean["price_double"] = str(data.get("price", ""))
    clean["services"] = _norm_services(clean.get("services", []))
    return UmrahTrip(**clean)


def load_trips(settings: dict) -> list[UmrahTrip]:
    """يحمّل برامج العمرة من الإعدادات."""
    raw = settings.get("umrah_trips", [])
    if not isinstance(raw, list):
        return []
    return [trip_from_dict(d) for d in raw if isinstance(d, dict)]


def save_trips(settings: dict, trips: list[UmrahTrip]) -> None:
    """يحفظ برامج العمرة في الإعدادات."""
    settings["umrah_trips"] = [t.to_dict() for t in trips]


def next_code(trips: list[UmrahTrip]) -> str:
    """يقترح رمزاً جديداً غير مستعمل للبرنامج (U1، U2…)."""
    used = {t.code for t in trips}
    i = 1
    while f"U{i}" in used:
        i += 1
    return f"U{i}"


def trip_pilgrims(records: list, code: str) -> list:
    """يرشّح المعتمرين المنتمين لبرنامجٍ معيّن (حسب الحقل ``trip``)."""
    return [r for r in records if str(getattr(r, "trip", "") or "") == code]


# ---- التسعير والنقل ----

def room_price(trip: UmrahTrip, key: str) -> float:
    """سعر الفرد لنوع غرفة (بالمفتاح price_single…)."""
    return _num(getattr(trip, key, ""))


def services_map(trip: UmrahTrip) -> dict:
    """قاموس اسم الخدمة ← سعرها (رقماً) للبرنامج."""
    return {s.get("name", ""): _num(s.get("price", ""))
            for s in (trip.services or []) if s.get("name")}


def suggest_transport(persons: int) -> str:
    """يقترح مركبة النقل الداخلي حسب عدد الأشخاص.

    شخصان → سيارة فورد؛ 3 فأكثر → سيارة جيمس (بحدّ أقصى 6 في السيارة).
    """
    if persons <= 0:
        return ""
    if persons <= 2:
        return "سيارة خاصة — فورد (حتى شخصين)"
    return "سيارة خاصة — جيمس (٣–٦ أشخاص)"


def package_per_person(trip: UmrahTrip, room_key: str,
                       service_names: list) -> float:
    """سعر الفرد = سعر الغرفة + مجموع أسعار الخدمات المختارة."""
    smap = services_map(trip)
    extra = sum(smap.get(n, 0.0) for n in (service_names or []))
    return room_price(trip, room_key) + extra

"""نموذج **فوج/رحلة العمرة** وتخزينه.

برنامج العمرة يُنظَّم حسب الأفواج: كل فوج له تواريخ سفر وعودة، وفندقا مكة
والمدينة وعدد لياليهما، ورحلات الطيران، والنقل، وباقة الخدمات، والسعر.
كل معتمر يرتبط بفوج عبر رمز الفوج (الحقل ``trip`` في سجلّ المعتمر).

تُحفظ الأفواج في إعدادات وضع العمرة (``settings_umrah.json``) تحت مفتاح
``umrah_trips`` — لا في ملفّ البيانات المشفّر (ليست بيانات حسّاسة).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields as _dc_fields

# باقة الخدمات الإضافية المتاحة لكل فوج (تُختار بمربّعات اختيار)
SERVICES = (
    "زيارة المدينة المنوّرة",
    "تأشيرة العمرة",
    "تأمين طبّي",
    "استقبال وتوديع بالمطار",
    "النقل الداخلي (الفنادق/الحرمين)",
    "الوجبات (إفطار/عشاء)",
    "جولات وزيارات مكة المكرّمة",
    "عربة كهربائية / كرسي متحرّك",
    "باقة الإحرام والهدايا",
    "شريحة اتصال / إنترنت",
)


@dataclass
class UmrahTrip:
    """فوج عمرة واحد بكل تفاصيله."""

    code: str = ""                 # رمز الفوج (فريد) — يربط المعتمرين به
    name: str = ""                 # اسم/عنوان الفوج
    depart_date: str = ""          # تاريخ المغادرة
    return_date: str = ""          # تاريخ العودة
    makkah_hotel: str = ""
    makkah_nights: str = ""
    madinah_hotel: str = ""
    madinah_nights: str = ""
    airline: str = ""
    flight_out: str = ""           # رقم رحلة الذهاب
    flight_ret: str = ""           # رقم رحلة العودة
    transport: str = ""            # وسيلة النقل الداخلي
    capacity: str = ""             # السعة (عدد المقاعد)
    price: str = ""                # سعر الباقة للفرد (درهم)
    services: list = field(default_factory=list)   # الخدمات المختارة
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


_TRIP_FIELDS = {f.name for f in _dc_fields(UmrahTrip)}


def trip_from_dict(data: dict) -> UmrahTrip:
    """يبني فوجاً من قاموس محفوظ (يتجاهل المفاتيح الغريبة)."""
    clean = {k: v for k, v in (data or {}).items() if k in _TRIP_FIELDS}
    trip = UmrahTrip(**clean)
    if not isinstance(trip.services, list):
        trip.services = []
    return trip


def load_trips(settings: dict) -> list[UmrahTrip]:
    """يحمّل أفواج العمرة من الإعدادات."""
    raw = settings.get("umrah_trips", [])
    if not isinstance(raw, list):
        return []
    return [trip_from_dict(d) for d in raw if isinstance(d, dict)]


def save_trips(settings: dict, trips: list[UmrahTrip]) -> None:
    """يحفظ أفواج العمرة في الإعدادات."""
    settings["umrah_trips"] = [t.to_dict() for t in trips]


def next_code(trips: list[UmrahTrip]) -> str:
    """يقترح رمزاً جديداً غير مستعمل للفوج (U1، U2…)."""
    used = {t.code for t in trips}
    i = 1
    while f"U{i}" in used:
        i += 1
    return f"U{i}"


def trip_pilgrims(records: list, code: str) -> list:
    """يرشّح المعتمرين المنتمين لفوجٍ معيّن (حسب الحقل ``trip``)."""
    return [r for r in records if str(getattr(r, "trip", "") or "") == code]

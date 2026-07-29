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
    "المطوّف",
    "خدمة التنفيذي في الاستقبال",
    "خدمة التنفيذي في المغادرة",
    "خدمة مُرافق",
)

# أعمدة كشف المعتمرين (بمسمّيات العمرة): (المفتاح، العنوان)
# الجنسية قبل البرنامج، والبرنامج يذكر رمزه.
REPORT_COLUMNS = (
    ("serial", "التسلسل"),
    ("full_name_ar", "الاسم"),
    ("passport_number", "رقم الجواز"),
    ("expiry_date", "تاريخ انتهاء الجواز"),
    ("nationality_ar", "الجنسية"),
    ("program", "البرنامج"),
    ("hotel", "الفندق"),
    ("room_type", "نوع الغرفة"),
    ("airline", "الطيران"),
    ("program_value", "القيمة"),
    ("paid_amount", "المبلغ المدفوع"),
    ("remaining", "المتبقّي"),
)
# أعمدة المبالغ في الكشف (تُعامَل أرقاماً في إكسل)
REPORT_MONEY_KEYS = frozenset({"program_value", "paid_amount", "remaining"})


def report_row(rec, serial: int, program_name: str = "") -> dict:
    """يبني صفّ كشف معتمر واحد (المفتاح ← القيمة المعروضة)."""
    from .fields import format_amount, parse_amount
    val = parse_amount(rec.program_value) or 0.0
    paid = parse_amount(rec.paid_amount) or 0.0
    return {
        "serial": str(serial),
        "full_name_ar": rec.full_name_ar or rec.full_name_en or "",
        "passport_number": rec.passport_number or "",
        "expiry_date": rec.expiry_date or "",
        "program": program_name or str(getattr(rec, "trip", "") or ""),
        "nationality_ar": rec.nationality_ar or "",
        "hotel": rec.hotel or "",
        "room_type": rec.room_type or "",
        "airline": rec.airline or "",
        "program_value": format_amount(val) if val else "",
        "paid_amount": format_amount(paid) if paid else "",
        "remaining": format_amount(val - paid) if val else "",
    }


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


def trip_year(trip: UmrahTrip) -> str:
    """سنة البرنامج الميلادية (من تاريخ المغادرة)، أو "" إن لم تُحدَّد.

    الموسم في العمرة سنة ميلادية كاملة (١ يناير – ٣١ ديسمبر)، فالبرنامج
    ينتمي لموسمِ سنةِ مغادرته.
    """
    import re
    m = re.search(r"(20\d\d)", str(trip.depart_date or ""))
    return m.group(1) if m else ""


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


# مدن التسكين: (المفتاح، الاسم، حقل رقم الغرفة، حقل الفندق، حقل الليالي)
CITIES = (
    ("makkah", "مكة المكرّمة", "makkah_room", "makkah_hotel", "makkah_nights"),
    ("madinah", "المدينة المنوّرة", "madinah_room", "madinah_hotel",
     "madinah_nights"),
)

_ROOM_CAP = {"مفرد": 1, "ثنائي": 2, "ثلاثي": 3, "رباعي": 4}


def room_capacity_of(room_type: str) -> int:
    """سعة نوع الغرفة (مفرد=1 … رباعي=4)، أو 0 إن لم يُحدَّد."""
    return _ROOM_CAP.get(str(room_type or "").strip(), 0)


def auto_assign_rooms(records: list, room_field: str) -> int:
    """يوزّع المعتمرين على غرف حسب نوع الغرفة (يملؤها حتى السعة) ويرقّمها.

    يعيد عدد الغرف الموزّعة. الترتيب حسب سعة الغرفة تصاعدياً لثبات النتيجة.
    """
    from collections import defaultdict
    groups: dict = defaultdict(list)
    for r in records:
        groups[str(r.room_type or "").strip()].append(r)
    num = 0
    for rtype in sorted(groups, key=lambda t: (room_capacity_of(t), t)):
        cap = room_capacity_of(rtype) or 1
        recs = groups[rtype]
        for i in range(0, len(recs), cap):
            num += 1
            for r in recs[i:i + cap]:
                setattr(r, room_field, str(num))
    return num


def rooming_rooms(records: list, room_field: str):
    """يجمع المعتمرين حسب رقم الغرفة. يعيد (غرف مرتّبة، بلا غرفة)."""
    rooms: dict = {}
    unassigned = []
    for r in records:
        no = str(getattr(r, room_field, "") or "").strip()
        if no:
            rooms.setdefault(no, []).append(r)
        else:
            unassigned.append(r)

    def _key(no: str):
        return (0, int(no)) if no.isdigit() else (1, no)

    ordered = sorted(rooms.items(), key=lambda kv: _key(kv[0]))
    return ordered, unassigned


def apply_trip_to_record(trip: UmrahTrip, rec) -> None:
    """يأخذ معلومات السفر والإقامة من البرنامج ويضعها في سجلّ المعتمر.

    فهذه المعلومات مشتركة لكل معتمري البرنامج، فتُملأ منه بدل إدخالها يدوياً
    لكل شخص (شركة الطيران، رقم الرحلة، تواريخ وأوقات السفر، والفندق).
    """
    if trip is None:
        return
    rec.airline = trip.airline
    rec.flight_number = trip.flight_out
    rec.arrival_date = trip.depart_date        # الوصول إلى مكة (المغادرة من الوطن)
    rec.arrival_time = trip.out_arrive_time
    rec.departure_date = trip.return_date      # العودة إلى الوطن
    rec.departure_time = trip.ret_depart_time
    hotels = " / ".join(h for h in (trip.makkah_hotel, trip.madinah_hotel) if h)
    if hotels:
        rec.hotel = hotels


def next_reference(trip: UmrahTrip, records: list) -> str:
    """يبني رقماً مرجعياً تلقائياً فريداً للمعتمر (رمز البرنامج + تسلسل)."""
    used = {str(getattr(r, "reference_number", "") or "") for r in records}
    i = 1
    while f"{trip.code}-{i:03d}" in used:
        i += 1
    return f"{trip.code}-{i:03d}"

"""نموذج **برنامج العمرة** (فوج/رحلة) وتخزينه وتسعيره.

برنامج العمرة يُنظَّم حسب البرامج: كل برنامج له تواريخ سفر وعودة، وفندقا
مكة والمدينة، ورحلتا الطيران (بأرقامهما وأوقاتهما)، وأسعار الفرد حسب نوع
الغرفة (مفرد/ثنائي/ثلاثي/رباعي)، وباقة خدمات إضافية لكلٍّ سعره، والنقل
الداخلي. كل معتمر يرتبط ببرنامج عبر الحقل ``trip`` في سجلّه.

تُحفظ البرامج في إعدادات وضع العمرة (``settings_umrah.json``) تحت المفتاح
``umrah_trips`` — ليست بيانات حسّاسة فلا تُشفَّر.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, fields as _dc_fields

# أنواع الغرف: (مفتاح السعر، الاسم، عدد الأشخاص في الغرفة)
# الطفل بدون سرير والرضيع لا يشغلان مقعداً في الغرفة (السعة 0).
ROOM_TYPES = (
    ("price_single", "مفرد", 1),
    ("price_double", "ثنائي", 2),
    ("price_triple", "ثلاثي", 3),
    ("price_quad", "رباعي", 4),
    ("price_child", "طفل (بدون سرير)", 0),
    ("price_infant", "رضيع", 0),
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
    ("family_number", "رقم العائلة"),
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
# «الموظف المسؤول» (من بيانات المعتمر) يُضاف عموداً أخيراً في معاينة الكشف
# والملخّص المالي فقط — لا في إكسل ولا كشوف الغرف/المواصلات.
REPORT_STAFF_COLUMN = ("staff", "الموظف المسؤول")
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
        "family_number": rec.family_number or "",
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
        "staff": rec.staff or "",
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
    manager: str = ""              # الشخص المسؤول عن البرنامج
    depart_date: str = ""
    return_date: str = ""
    makkah_hotel: str = ""
    makkah_nights: str = ""
    makkah_rooms: str = ""         # عدد الغرف المتاحة في فندق مكة
    madinah_hotel: str = ""
    madinah_nights: str = ""
    madinah_rooms: str = ""        # عدد الغرف المتاحة في فندق المدينة
    airline: str = ""
    # رحلة الذهاب: رقم الرحلة ووقت المغادرة ووقت الوصول
    flight_out: str = ""
    out_depart_time: str = ""
    out_arrive_time: str = ""
    # رحلة العودة
    flight_ret: str = ""
    ret_depart_time: str = ""
    ret_arrive_time: str = ""
    flight_pnr: str = ""           # رمز حجز الطيران (PNR)
    transport_pnr: str = ""        # رمز حجز النقل (PNR)
    # أسعار الفرد حسب نوع الغرفة
    price_single: str = ""
    price_double: str = ""
    price_triple: str = ""
    price_quad: str = ""
    price_child: str = ""          # سعر الطفل (بدون سرير)
    price_infant: str = ""         # سعر الرضيع
    transport: str = ""            # ملاحظة النقل الداخلي الافتراضية
    capacity: str = ""             # سعة الطيران (عدد المقاعد)
    emergency_uae: str = ""        # هاتف الطوارئ في الإمارات
    emergency_ksa: str = ""        # هاتف الطوارئ في السعودية
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


def next_voucher_number(settings: dict) -> str:
    """يخصّص رقم فاوتشر تسلسلياً (MA0001, MA0002…) ويحدّث العدّاد في الإعدادات.
    كل استدعاء يُرجع رقماً جديداً، فيأخذ كل فاوتشر رقمه الفريد تلقائياً."""
    try:
        seq = int(settings.get("voucher_seq", 0) or 0)
    except (TypeError, ValueError):
        seq = 0
    seq += 1
    settings["voucher_seq"] = seq
    return f"MA{seq:04d}"


_AMADEUS_CARRIERS = {
    "SV": "السعودية", "EY": "الاتحاد", "EK": "الإمارات", "FZ": "فلاي دبي",
    "XY": "فلاي ناس", "G9": "العربية", "F3": "أديل", "J9": "الجزيرة",
}
_AMADEUS_AIRPORTS = {
    "AUH": "أبوظبي", "DXB": "دبي", "DWC": "دبي", "SHJ": "الشارقة",
    "RKT": "رأس الخيمة", "JED": "جدة", "MED": "المدينة", "RUH": "الرياض",
    "TIF": "الطائف", "DMM": "الدمام",
}
_AMADEUS_MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
                   "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11,
                   "DEC": 12}
# سطر رحلة أماديوس: EY 611 M 04AUG 2 AUHJED DK1 1405 1610 …
# متسامح: الدرجة قد تُدمج/تُفقد في OCR، وزوج المدينتين قد يُفصل بمسافة.
_AMADEUS_RE = re.compile(
    r"([A-Z][A-Z0-9])\s*(\d{2,4})\s+[A-Z0-9]{0,2}\s*(\d{1,2})([A-Z]{3})"
    r"\s+\d?\s*([A-Z]{3})\s*([A-Z]{3})\s+[A-Z0-9]{2,4}\s+(\d{3,4})\s+(\d{3,4})")


def _hhmm(t: str) -> str:
    t = str(t).zfill(4)[-4:]
    return f"{t[:2]}:{t[2:]}"


def _amadeus_line_row(line: str, year: int):
    """محلّل متسامح لسطر أماديوس واحد: يبحث عن التاريخ وزوج المطارين ووقتين
    والناقل بمرونة، فيصمد أمام أخطاء الـ OCR التي تكسر التعبير النمطي."""
    toks = re.split(r"[\s/]+", line.upper().strip())
    date_i = next((i for i, t in enumerate(toks)
                   if re.fullmatch(r"\d{1,2}[A-Z]{3}", t)), None)
    if date_i is None:
        return None
    dt = toks[date_i]
    mnum = _AMADEUS_MONTHS.get(dt[-3:], 0)
    day = int(dt[:-3] or 0)
    if not mnum or not (1 <= day <= 31):
        return None
    # زوج المطارين: رمز سداسي، أو رمزان ثلاثيان معروفان
    frm3 = to3 = None
    for t in toks:
        if re.fullmatch(r"[A-Z]{6}", t):
            frm3, to3 = t[:3], t[3:]
            break
    if frm3 is None:
        threes = [t for t in toks if re.fullmatch(r"[A-Z]{3}", t)]
        known = [t for t in threes if t in _AMADEUS_AIRPORTS]
        pick = known if len(known) >= 2 else threes
        if len(pick) >= 2:
            frm3, to3 = pick[0], pick[1]
    if frm3 is None:
        return None
    pair_i = next((i for i, t in enumerate(toks) if t in (frm3 + to3, frm3)),
                  date_i)
    # وقتان بأربع خانات بعد زوج المطارين (تفادياً لرقم الرحلة)
    times = [t for i, t in enumerate(toks) if i > pair_i
             and re.fullmatch(r"\d{4}", t)
             and int(t[:2]) < 24 and int(t[2:]) < 60]
    if len(times) < 2:
        return None
    dep, arr = times[0], times[1]
    # الناقل: رمز معروف، أو رمز مكوّن من حرفين قبل التاريخ
    carrier = next((t for t in toks if t in _AMADEUS_CARRIERS), None)
    if carrier is None:
        carrier = next((t for t in toks[:date_i]
                        if re.fullmatch(r"[A-Z][A-Z0-9]", t)), "")
    iso = f"{year:04d}-{mnum:02d}-{day:02d}"
    return (iso, carrier, frm3, to3, dep, arr)


def parse_amadeus_flights(text: str, year: int | None = None) -> list:
    """يحلّل نصّ حجز أماديوس ويعيد صفوف رحلات جاهزة لجدول الطيران في عرض السعر:
    ``[التاريخ ISO، الناقل، الإقلاع، من، الوصول، إلى]`` لكل رحلة.

    يجمع بين تعبير نمطي دقيق ومحلّل سطري متسامح، ويُزيل التكرار (نمرّر عدّة نسخ
    من النصّ عادةً)."""
    from datetime import date as _date

    if year is None:
        year = _date.today().year
    text = (text or "").upper()

    def _emit(rows, seen, iso, carrier, frm3, to3, dep, arr):
        key = (iso, frm3, to3, dep, arr)
        if key in seen:
            return
        seen.add(key)
        rows.append([iso, _AMADEUS_CARRIERS.get(carrier, carrier),
                     _hhmm(dep), _AMADEUS_AIRPORTS.get(frm3, frm3),
                     _hhmm(arr), _AMADEUS_AIRPORTS.get(to3, to3)])

    rows, seen = [], set()
    # 1) التعبير النمطي الدقيق
    for m in _AMADEUS_RE.finditer(text):
        carrier, _flight, day, mon, frm3, to3, dep, arr = m.groups()
        mnum = _AMADEUS_MONTHS.get(mon, 0)
        if mnum and 1 <= int(day) <= 31 and int(dep[-2:]) < 60 \
                and int(arr[-2:]) < 60:
            _emit(rows, seen, f"{year:04d}-{mnum:02d}-{int(day):02d}",
                  carrier, frm3, to3, dep, arr)
    # 2) محلّل سطري متسامح (يلتقط ما فات التعبير النمطي)
    for line in text.splitlines():
        parsed = _amadeus_line_row(line, year)
        if parsed:
            _emit(rows, seen, *parsed)
    return rows


def load_quotes(settings: dict, code: str) -> list:
    """يعيد عروض الأسعار المحفوظة لبرنامجٍ معيّن (بحسب رمزه)."""
    store = settings.get("umrah_quotes")
    if not isinstance(store, dict):
        return []
    lst = store.get(str(code or "_manual"))
    return list(lst) if isinstance(lst, list) else []


def save_quote(settings: dict, code: str, quote: dict) -> None:
    """يحفظ عرض سعر ضمن قائمة «عروض الأسعار» للبرنامج؛ يحدّث الموجود بنفس الرقم."""
    store = settings.get("umrah_quotes")
    if not isinstance(store, dict):
        store = {}
        settings["umrah_quotes"] = store
    key = str(code or "_manual")
    lst = store.get(key)
    if not isinstance(lst, list):
        lst = []
        store[key] = lst
    num = str(quote.get("number") or "")
    for i, q in enumerate(lst):
        if str(q.get("number") or "") == num and num:
            lst[i] = dict(quote)
            return
    lst.append(dict(quote))


def delete_quote(settings: dict, code: str, number: str) -> None:
    """يحذف عرض سعر من قائمة البرنامج بحسب رقمه."""
    store = settings.get("umrah_quotes")
    if not isinstance(store, dict):
        return
    key = str(code or "_manual")
    lst = store.get(key)
    if isinstance(lst, list):
        store[key] = [q for q in lst
                      if str(q.get("number") or "") != str(number)]


def next_quote_number(settings: dict) -> str:
    """يخصّص رقم عرض سعر تسلسلياً (MA-Q0001…) ويحدّث العدّاد في الإعدادات."""
    try:
        seq = int(settings.get("quote_seq", 0) or 0)
    except (TypeError, ValueError):
        seq = 0
    seq += 1
    settings["quote_seq"] = seq
    return f"MA-Q{seq:04d}"


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


# مدن التسكين: (المفتاح، الاسم، حقل رقم الغرفة، حقل الفندق، حقل الليالي،
# حقل عدد الغرف المتاحة)
CITIES = (
    ("makkah", "مكة المكرّمة", "makkah_room", "makkah_hotel", "makkah_nights",
     "makkah_rooms"),
    ("madinah", "المدينة المنوّرة", "madinah_room", "madinah_hotel",
     "madinah_nights", "madinah_rooms"),
)

_ROOM_CAP = {"مفرد": 1, "ثنائي": 2, "ثلاثي": 3, "رباعي": 4,
             "طفل (بدون سرير)": 0, "رضيع": 0}


def room_capacity_of(room_type: str) -> int:
    """سعة نوع الغرفة (مفرد=1 … رباعي=4، الطفل بدون سرير=0)."""
    return _ROOM_CAP.get(str(room_type or "").strip(), 0)


def auto_assign_rooms(records: list, room_field: str, max_rooms: int = 0):
    """يوزّع المعتمرين على غرف حسب نوع الغرفة (يملؤها حتى السعة) ويرقّمها.

    الأطفال والرضّع (سعة 0) لا يُخصَّص لهم رقم غرفة. عند تحديد ``max_rooms``
    لا يُتجاوز عدد الغرف المتاحة، ويبقى الفائض بلا غرفة (منع تجاوز السعة).
    يعيد (عدد الغرف الموزّعة، عدد المعتمرين بلا غرفة بسبب امتلاء الفندق).
    """
    from collections import defaultdict
    for r in records:                      # تصفير قبل إعادة التوزيع
        setattr(r, room_field, "")
    groups: dict = defaultdict(list)
    for r in records:
        groups[str(r.room_type or "").strip()].append(r)
    num = 0
    overflow = 0
    for rtype in sorted(groups, key=lambda t: (room_capacity_of(t), t)):
        cap = room_capacity_of(rtype)
        if cap <= 0:                       # طفل/رضيع بلا سرير — بلا غرفة
            continue
        recs = groups[rtype]
        for i in range(0, len(recs), cap):
            chunk = recs[i:i + cap]
            if max_rooms and num >= max_rooms:
                overflow += len(chunk)     # الفندق ممتلئ — يبقى بلا غرفة
                continue
            num += 1
            for r in chunk:
                setattr(r, room_field, str(num))
    return num, overflow


def _parse_date(text: str):
    """يحلّل تاريخاً بصيغة YYYY-M-D (يتجاهل ما بعد اليوم). يعيد date أو None."""
    import re
    from datetime import date as _date
    m = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", str(text or ""))
    if not m:
        return None
    try:
        return _date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _add_months(d, months: int):
    """يضيف عدداً من الأشهر إلى تاريخ (مع ضبط نهاية الشهر)."""
    import calendar
    from datetime import date as _date
    y = d.year + (d.month - 1 + months) // 12
    mo = (d.month - 1 + months) % 12 + 1
    day = min(d.day, calendar.monthrange(y, mo)[1])
    return _date(y, mo, day)


def passport_expiry_soon(rec, depart_date: str, months: int = 6) -> bool:
    """هل تنتهي صلاحية الجواز قبل ``months`` أشهر من تاريخ السفر؟

    شرط دخول العمرة: صلاحية الجواز ≥ ٦ أشهر من تاريخ السفر.
    """
    exp = _parse_date(getattr(rec, "expiry_date", ""))
    dep = _parse_date(depart_date)
    if not exp or not dep:
        return False
    return exp < _add_months(dep, months)


def passport_expired(rec) -> bool:
    """هل انتهت صلاحية الجواز فعلاً (قبل اليوم)؟"""
    from datetime import date as _date
    exp = _parse_date(getattr(rec, "expiry_date", ""))
    return bool(exp) and exp < _date.today()


def passport_flag(rec, depart_date: str) -> bool:
    """علامة تحذير على الجواز: منتهٍ أو تنتهي صلاحيته قبل ٦ أشهر من السفر."""
    return passport_expired(rec) or passport_expiry_soon(rec, depart_date)


def auto_assign_vehicles(records: list, max_per: int = 6) -> int:
    """يوزّع المعتمرين على مركبات النقل (فورد ≤ شخصين، جيمس حتى ٦). يعيد العدد."""
    num = 0
    for i in range(0, len(records), max_per):
        chunk = records[i:i + max_per]
        num += 1
        kind = "فورد" if len(chunk) <= 2 else "جيمس"
        for r in chunk:
            r.vehicle = f"{kind} {num}"
    return num


def record_services_total(rec) -> float:
    """مجموع أسعار خدمات المعتمر."""
    return sum(_num(s.get("price", "")) for s in (getattr(rec, "umrah_services", None)
                                                  or []))


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
    if trip.flight_pnr:
        rec.pnr = trip.flight_pnr              # رمز حجز الطيران للفوج
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

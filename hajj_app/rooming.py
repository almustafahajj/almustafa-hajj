"""كشف التسكين: توزيع الحجاج على الغرف حسب نوع الغرفة ورقمها والعائلة.

القواعد المعتمدة (باختيار المستخدم):
- أفراد العائلة الواحدة (نفس رقم العائلة) في غرفة واحدة ما أمكن.
- الغرفة **المشتركة** تُملأ ببقية الأماكن من عائلات أخرى **بنفس الجنس** فقط.
- الغرفة غير المشتركة تبقى للعائلة وحدها ولو نقصت.
- من كان له **رقم غرفة** محدّد يُحترم كما هو؛ ومن لا رقم له يُوزّع تلقائياً.
- التوزيع لكل فندق على حدة.

قيم "نوع الغرفة" في الكشوف غير موحّدة (ثلاثي، ثلاثية، رباعي مشترك، Quad،
مفرد، بدون...) فنستخلص منها السعة وصفة الاشتراك بمرونة.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .fields import row_dict
from .mrz import PassportData

# سعة كل نوع غرفة. المفاتيح كلمات نبحث عنها داخل نص نوع الغرفة بعد توحيده.
_CAPACITY_WORDS: tuple[tuple[tuple[str, ...], int], ...] = (
    (("مفرد", "فردي", "فردية", "single", "sgl"), 1),
    (("ثنائي", "ثنائية", "مزدوج", "مزدوجة", "double", "twin", "dbl"), 2),
    (("ثلاثي", "ثلاثية", "triple", "trpl", "tpl"), 3),
    (("رباعي", "رباعية", "quad", "quadruple", "qd"), 4),
    (("خماسي", "خماسية", "quint", "quintuple"), 5),
    (("سداسي", "سداسية", "sextuple"), 6),
)

# أرقام مكتوبة قد ترد بدل الكلمات: "غرفة 4 أشخاص"
_DIGIT_CAP = re.compile(r"(\d+)\s*(?:أشخاص|اشخاص|شخص|pax|person|people|beds?|أسرة|اسرة)")

_SHARED_WORDS = ("مشترك", "مشتركة", "share", "shared", "sharing")

_DEFAULT_CAPACITY = 4        # حين يتعذّر تحديد السعة — الرباعية أشيع في الكشوف


def _normalize(text: str) -> str:
    """يوحّد نص نوع الغرفة للبحث: حروف صغيرة، بلا تشكيل ولا صور ألف/ياء."""
    text = unicodedata.normalize("NFKC", str(text)).strip().lower()
    text = re.sub(r"[ً-ْـ]", "", text)
    text = re.sub(r"[أإآ]", "ا", text).replace("ى", "ي").replace("ة", "ه")
    return text


def room_capacity(room_type: str) -> int:
    """يستخلص سعة الغرفة من نصّ نوعها. يعيد الافتراضي إن تعذّر."""
    norm = _normalize(room_type)
    if not norm:
        return _DEFAULT_CAPACITY
    for words, cap in _CAPACITY_WORDS:
        if any(_normalize(w) in norm for w in words):
            return cap
    match = _DIGIT_CAP.search(norm)
    if match:
        value = int(match.group(1))
        if 1 <= value <= 12:
            return value
    # رقم مفرد صريح داخل النص (نادر): "غرفة 3"
    lone = re.fullmatch(r"\D*(\d)\D*", norm)
    if lone and 1 <= int(lone.group(1)) <= 9:
        return int(lone.group(1))
    return _DEFAULT_CAPACITY


# فئات الغرف مرتّبة تصاعدياً بالسعة — تُستعمل في فلتر النوع
ROOM_CATEGORIES: tuple[str, ...] = ("مفرد", "ثنائي", "ثلاثي", "رباعي", "خماسي", "سداسي")
_CATEGORY_BY_CAP = dict(enumerate(ROOM_CATEGORIES, start=1))


def room_category(room_type: str) -> str:
    """يعيد فئة الغرفة من نوعها بلا رقم: 'رباعية 2' -> 'رباعي'، 'ثلاثي' -> 'ثلاثي'.

    يعيد نصاً فارغاً إن لم يكن هناك نوع غرفة فعلي (بدون/فراغ).
    """
    if not _has_room_type(room_type):
        return ""
    return _CATEGORY_BY_CAP.get(room_capacity(room_type), "")


def is_shared(room_type: str) -> bool:
    """هل الغرفة مشتركة (تُملأ بعائلات أخرى)؟"""
    norm = _normalize(room_type)
    return any(_normalize(w) in norm for w in _SHARED_WORDS)


def _has_room_type(room_type: str) -> bool:
    """هل يوجد نوع غرفة فعلي (لا 'بدون' ولا فراغ)؟"""
    norm = _normalize(room_type)
    return bool(norm) and norm not in ("بدون", "لا يوجد", "none", "-", "na")


@dataclass
class Occupant:
    """ساكن غرفة: يحمل السجل الأصلي مع بيانات العرض الجاهزة."""
    serial: int
    record: PassportData

    @property
    def name(self) -> str:
        return self.record.full_name_ar or self.record.full_name_en or "—"

    @property
    def sex(self) -> str:
        return self.record.sex or ""

    @property
    def family(self) -> str:
        return str(self.record.family_number or "").strip()


@dataclass
class Room:
    """غرفة في كشف التسكين."""
    hotel: str
    number: str
    room_type: str
    capacity: int
    shared: bool
    occupants: list[Occupant] = field(default_factory=list)
    auto_numbered: bool = False      # هل رقّمها البرنامج تلقائياً؟

    @property
    def count(self) -> int:
        return len(self.occupants)

    @property
    def families(self) -> list[str]:
        seen: list[str] = []
        for occ in self.occupants:
            fam = occ.family or "—"
            if fam not in seen:
                seen.append(fam)
        return seen

    @property
    def sexes(self) -> set[str]:
        return {occ.sex for occ in self.occupants if occ.sex}

    def warnings(self) -> list[str]:
        """مشكلات تستدعي مراجعة يدوية."""
        issues = []
        if self.count > self.capacity:
            issues.append(f"عدد السكان {self.count} يتجاوز السعة {self.capacity}")
        # اختلاط الجنسين لعائلات مختلفة في غرفة واحدة
        if len(self.families) > 1 and len(self.sexes) > 1:
            issues.append("عائلات مختلطة الجنس في غرفة واحدة")
        return issues


@dataclass
class RoomingPlan:
    """نتيجة التوزيع: الغرف مرتّبة، والحجاج المتعذّر تسكينهم، والتنبيهات."""
    rooms: list[Room]
    unplaced: list[Occupant]
    notes: list[str]


def _room_sort_key(number: str) -> tuple:
    """يرتّب أرقام الغرف: الرقمي عددياً، والنصّي أبجدياً."""
    text = str(number).strip()
    match = re.match(r"^(\d+)", text)
    if match:
        return (0, int(match.group(1)), text)
    return (1, 0, text)


def _next_number(used: set[str], counter: list[int]) -> str:
    """يولّد رقم غرفة تلقائياً غير مستعمل، يبدأ من 1 ويقفز فوق المستعمل."""
    while True:
        counter[0] += 1
        candidate = str(counter[0])
        if candidate not in used:
            used.add(candidate)
            return candidate


def room_number_in_type(room_type: str) -> str:
    """يستخرج رقم الغرفة المدمج في نوعها: 'رباعي 2' -> '2'، 'ثلاثي 3' -> '3'.

    هكذا يحدّد المستخدم التسكين مباشرة في خانة نوع الغرفة: كل من كتب له
    'رباعي 2' في نفس الغرفة.
    """
    match = re.search(r"\d+", str(room_type))
    return match.group(0) if match else ""


def common_room_type(records: list[PassportData]) -> str:
    """أشيع نص لنوع الغرفة بين مجموعة سجلات (للعرض في عنوان الغرفة)."""
    counts: dict[str, int] = {}
    for rec in records:
        rt = str(rec.room_type or "").strip()
        if rt:
            counts[rt] = counts.get(rt, 0) + 1
    return max(counts, key=counts.get) if counts else ""


def group_records_by_room(
    records: list[PassportData],
) -> tuple[list[tuple[str, int, str, list[PassportData]]], list[PassportData]]:
    """يجمع السجلات في غرف حسب (الفندق، السعة، الرقم)، مرتّبة تصاعدياً.

    كل غرفة = (الفندق، السعة، الرقم، السكان). من لا نوع غرفة ولا رقم له
    يُجمع في قائمة "بلا غرفة" المُعادة ثانياً. الترتيب: الفندق، ثم السعة
    (مفرد ← رباعي)، ثم رقم الغرفة داخل كل نوع.
    """
    groups: dict[tuple[str, int, str], list[PassportData]] = {}
    unplaced: list[PassportData] = []
    for rec in records:
        rtype = str(rec.room_type or "")
        number = str(rec.room_number or "").strip() or room_number_in_type(rtype)
        category = room_category(rtype)
        if not category and not number:
            unplaced.append(rec)
            continue
        key = (str(rec.hotel or "").strip(), room_capacity(rtype), number)
        groups.setdefault(key, []).append(rec)

    def sort_key(key: tuple) -> tuple:
        hotel, cap, number = key
        match = re.match(r"^(\d+)", number)
        num = (0, int(match.group(1)), number) if match else (1, 0, number)
        return (hotel, cap, num)

    rooms = [
        (hotel, cap, number, groups[(hotel, cap, number)])
        for hotel, cap, number in sorted(groups, key=sort_key)
    ]
    return rooms, unplaced


def build_rooming_plan(records: list[PassportData]) -> RoomingPlan:
    """يبني كشف التسكين بالاعتماد على نوع الغرفة.

    كل من له نفس **رقم الغرفة** في نفس الفندق يُجمع في غرفة واحدة. ورقم
    الغرفة يؤخذ من خانة 'رقم الغرفة' إن مُلئت، وإلا من الرقم المدمج في نوع
    الغرفة ('رباعي 2' -> غرفة رقمها 2). من لا رقم له يُوزّع حسب العائلة
    في غرف بحجم سعة نوعها، بأرقام تلقائية.
    """
    notes: list[str] = []
    occupants = [Occupant(i + 1, r) for i, r in enumerate(records)]

    # بلا نوع غرفة ولا رقم — لا يدخل كشف التسكين أصلاً
    housed, unplaced = [], []
    for occ in occupants:
        if _has_room_type(occ.record.room_type) or str(occ.record.room_number).strip():
            housed.append(occ)
        else:
            unplaced.append(occ)

    rooms: list[Room] = []
    # نجمع لكل فندق على حدة (ترتيب الظهور محفوظ)
    by_hotel: dict[str, list[Occupant]] = {}
    for occ in housed:
        by_hotel.setdefault((occ.record.hotel or "").strip(), []).append(occ)

    for hotel, group in by_hotel.items():
        rooms.extend(_plan_hotel(hotel, group))

    # الترتيب: الفندق، ثم النوع تصاعدياً (مفرد ثم ثنائي ثم ثلاثي ثم رباعي)،
    # ثم رقم الغرفة داخل كل نوع.
    rooms.sort(key=lambda r: (
        (r.hotel or "").strip(), r.capacity, _room_sort_key(r.number)
    ))

    if unplaced:
        notes.append(f"{len(unplaced)} حاجاً بلا نوع غرفة — لم يدرجوا في كشف التسكين")
    over = sum(1 for r in rooms if r.count > r.capacity)
    if over:
        notes.append(f"{over} غرفة تجاوزت سعتها — راجع نوع الغرفة أو رقمها")

    return RoomingPlan(rooms=rooms, unplaced=unplaced, notes=notes)


def _plan_hotel(hotel: str, occupants: list[Occupant]) -> list[Room]:
    """يوزّع سكان فندق واحد على غرف، معتمداً على (النوع + الرقم).

    مفتاح الغرفة هو السعة مع الرقم معاً، لا الرقم وحده: «مفرد 1» و«ثنائية 1»
    و«رباعية 1» ثلاث غرف مختلفة رغم أن رقمها واحد — لأن الترقيم يبدأ من
    جديد مع كل نوع.
    """
    numbered: dict[tuple[int, str], list[Occupant]] = {}   # (سعة، رقم) -> سكان
    bare: dict[str, list[Occupant]] = {}                   # نوع بلا رقم -> سكان
    for occ in occupants:
        rtype = str(occ.record.room_type or "")
        number = str(occ.record.room_number or "").strip() or room_number_in_type(rtype)
        if number:
            numbered.setdefault((room_capacity(rtype), number), []).append(occ)
        else:
            bare.setdefault(_normalize(rtype) or "بدون", []).append(occ)

    rooms: list[Room] = []
    used_numbers = {number for _cap, number in numbered}

    # كل (نوع، رقم) = غرفة واحدة تجمع كل من يحملها ('رباعي 2' كلهم معاً)
    for (cap, number), members in numbered.items():
        rtype = _dominant_room_type(members)
        rooms.append(Room(
            hotel=hotel, number=number, room_type=rtype,
            capacity=cap, shared=is_shared(rtype), occupants=members,
        ))

    # من لهم نوع بلا رقم: نوزّعهم حسب العائلة في غرف بحجم السعة، بأرقام تلقائية
    counter = [0]
    for members in bare.values():
        rooms.extend(_split_bare(hotel, members, used_numbers, counter))
    return rooms


def _dominant_room_type(members: list[Occupant]) -> str:
    """أشيع نوع غرفة بين مجموعة (قد يختلف قليلاً بين أفراد الغرفة)."""
    counts: dict[str, int] = {}
    for occ in members:
        rt = str(occ.record.room_type or "").strip()
        if rt:
            counts[rt] = counts.get(rt, 0) + 1
    return max(counts, key=counts.get) if counts else ""


def _split_bare(
    hotel: str, occupants: list[Occupant], used: set[str], counter: list[int]
) -> list[Room]:
    """يوزّع من لهم نوع غرفة بلا رقم: كل عائلة معاً في غرف بحجم السعة.

    لا تُخلط عائلة بأخرى هنا — الاشتراك يُعبَّر عنه بإعطائهم نفس رقم الغرفة.
    """
    rtype = _dominant_room_type(occupants) or "رباعي"
    cap = room_capacity(rtype)
    shared = is_shared(rtype)

    families: dict[str, list[Occupant]] = {}
    for occ in occupants:
        families.setdefault(occ.family or f"_{occ.serial}", []).append(occ)

    rooms: list[Room] = []
    for members in families.values():
        for start in range(0, len(members), cap):
            chunk = members[start:start + cap]
            number = _next_number(used, counter)
            rooms.append(Room(
                hotel=hotel, number=number, room_type=rtype,
                capacity=cap, shared=shared, occupants=list(chunk),
                auto_numbered=True,
            ))
    return rooms


def plan_rows(plan: RoomingPlan) -> list[dict]:
    """يحوّل الخطة إلى صفوف عرض مسطّحة (غرفة ثم سكانها)، للجدول والتصدير."""
    rows: list[dict] = []
    for room in plan.rooms:
        for position, occ in enumerate(room.occupants, start=1):
            data = row_dict(occ.record, occ.serial)
            rows.append({
                "hotel": room.hotel,
                "room_number": room.number,
                "room_type": room.room_type,
                "capacity": room.capacity,
                "position": position,
                "count": room.count,
                "family_number": occ.family,
                "full_name_ar": data.get("full_name_ar", ""),
                "full_name_en": data.get("full_name_en", ""),
                "sex": occ.sex,
                "phone": data.get("phone", ""),
                "transport": data.get("transport", ""),
                "auto": room.auto_numbered,
                "warnings": room.warnings(),
            })
    return rows

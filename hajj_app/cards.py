"""محتوى رمز QR لبطاقة الحاج (هوية مختصرة قابلة للقراءة عند المسح)."""

from __future__ import annotations

from .mrz import PassportData
from .rooming import room_number_in_type


def room_of(rec: PassportData) -> str:
    return (str(rec.room_number or "").strip()
            or room_number_in_type(str(rec.room_type or "")))


def badge_name(rec: PassportData) -> str:
    """اسم البطاقة: الأول والثاني والأخير فقط (يُسقط الأوسط إن زاد عن ثلاثة)."""
    full = (rec.full_name_ar or rec.full_name_en or "").strip()
    parts = full.split()
    if len(parts) <= 3:
        return " ".join(parts)
    return " ".join([parts[0], parts[1], parts[-1]])


def is_woman(rec: PassportData) -> bool:
    """هل الحاجّة أنثى؟ (لتحديد رمز المرأة المحجّبة بدل الصورة)."""
    s = str(rec.sex or "").strip()
    return s.startswith("أنثى") or s.startswith("انثى") or s.upper().startswith("F")


def qr_payload(rec: PassportData) -> str:
    """نصّ رمز QR لبطاقة الحاج — أسطر مقروءة تُعرّف الحاج عند المسح."""
    name = rec.full_name_ar or rec.full_name_en or "—"
    lines = [f"الحاج: {name}"]
    passport = str(rec.passport_number or "").strip().upper()
    if passport:
        lines.append(f"الجواز: {passport}")
    phone = str(rec.phone or "").strip()
    if phone:
        lines.append(f"الهاتف: {phone}")
    hotel = str(rec.hotel or "").strip()
    room = room_of(rec)
    if hotel or room:
        lines.append("الإقامة: " + hotel + (f" - غرفة {room}" if room else ""))
    family = str(rec.family_number or "").strip()
    if family:
        lines.append(f"العائلة: {family}")
    return "\n".join(lines)

"""ترجمة الواجهة (عربي/إنجليزي) مع إمكانية الاختيار.

اللغة الافتراضية العربية. ``tr(ar)`` يعيد النصّ العربي كما هو في وضع العربية،
وترجمته الإنجليزية في وضع الإنجليزية (وإن لم تُوجد ترجمة يعيد العربي).

يُطبَّق على عناصر الواجهة الرئيسية: القوائم والأزرار والترويسة ورؤوس الجدول.
النوافذ الفرعية تبقى عربية حالياً ويمكن توسيع القاموس لاحقاً.
"""

from __future__ import annotations

LANGS = ("ar", "en")
LANG_LABELS = {"ar": "العربية", "en": "English"}

_lang = "ar"


def set_lang(lang: str) -> None:
    global _lang
    _lang = lang if lang in LANGS else "ar"


def get_lang() -> str:
    return _lang


def tr(ar: str) -> str:
    """يترجم نصّاً عربياً حسب اللغة الحالية (يعيد العربي إن لا ترجمة)."""
    if _lang == "ar":
        return ar
    return _EN.get(ar, ar)


def field_label(key: str, ar_label: str) -> str:
    """عنوان عمود/حقل حسب اللغة (إنجليزي من الخريطة، وإلا العربي)."""
    if _lang == "ar":
        return ar_label
    return _FIELD_EN.get(key, ar_label)


# ------------------------------------------------ ترجمة عناصر الواجهة
_EN = {
    # عناوين القوائم السبع
    "البرامج  ▾": "Programs  ▾",
    "الحجوزات  ▾": "Pilgrims  ▾",
    "إدارة التسكين  ▾": "Housing  ▾",
    "المالية والمحاسبة  ▾": "Finance  ▾",
    "التقارير  ▾": "Reports  ▾",
    "لوحة الإدارة  ▾": "Admin  ▾",
    "استيراد البيانات  ▾": "Import  ▾",
    # البرامج
    "🌙  بدء موسم جديد": "🌙  New Season",
    "🗂  برامج الحملة (الأول/الثاني/الثالث)": "🗂  Campaign Programs (1/2/3)",
    "👥  المجموعات والمرشدون": "👥  Groups & Guides",
    "🗓  جدول المناسك": "🗓  Rites Schedule",
    # الحجوزات
    "➕  إضافة حاج يدوياً": "➕  Add Pilgrim Manually",
    "✏️  تعديل السجل": "✏️  Edit Record",
    "✏️  تعديل جماعي للمحدّدين": "✏️  Bulk Edit Selected",
    "🗑  حذف المحدد": "🗑  Delete Selected",
    "↩  تراجع  (Ctrl+Z)": "↩  Undo  (Ctrl+Z)",
    "📱  رسالة واتساب للمحدّدين": "📱  WhatsApp Selected",
    "🩺  فحص جاهزية الكشف": "🩺  Data Quality Check",
    "✅  قائمة تحقّق الجاهزية": "✅  Readiness Checklist",
    "🎫  تسجيل الحضور (مسح QR/جواز)": "🎫  Check-in (QR/Passport)",
    "🧹  مسح الكل": "🧹  Clear All",
    # إدارة التسكين
    "🛏  إشغال الغرف": "🛏  Room Occupancy",
    "🏨  تسكين إكسل": "🏨  Rooming (Excel)",
    "🏨  تسكين PDF": "🏨  Rooming (PDF)",
    "⛺  خيام المخيمات": "⛺  Camp Tents",
    # المالية
    "📊  إحصاءات وملخّص مالي": "📊  Statistics & Financials",
    "📈  الرسوم البيانية": "📈  Charts",
    "📄  تصدير الإحصاءات والمالية PDF": "📄  Export Statistics PDF",
    "💵  سجلّ دفعات الحاج (الأقساط)": "💵  Payments (Installments)",
    "🧮  المصروفات والمحاسبة": "🧮  Expenses & Accounting",
    "📄  كشف المتأخّرات المالية (معاينة)": "📄  Outstanding Report (Preview)",
    "🧾  سند قبض (معاينة)": "🧾  Receipt (Preview)",
    "🧾  فاتورة ضريبية (معاينة)": "🧾  Tax Invoice (Preview)",
    "💳  فاتورة إلكترونية PEPPOL (معاينة)": "💳  PEPPOL e-Invoice (Preview)",
    "📜  عقد خدمات حج (معاينة)": "📜  Service Contract (Preview)",
    "🧾  توليد جماعي للمستندات (للمعروضين)": "🧾  Bulk Documents (Shown)",
    # التقارير
    "📊  تصدير إكسل": "📊  Export Excel",
    "📄  تصدير PDF": "📄  Export PDF",
    "🖨  طباعة المعروض": "🖨  Print Shown",
    "✈  كشف الطيران وأماديوس": "✈  Flight Manifest & Amadeus",
    "🚌  كشف المواصلات": "🚌  Transport Manifest",
    "🪪  بطاقات الحجّاج": "🪪  Pilgrim Badges",
    "🏷  طباعة الاستيكرات (حقائب/غرف/أظرف)": "🏷  Stickers (Bags/Rooms/Envelopes)",
    "🖼  طباعة الجوازات والتصاريح": "🖼  Print Passports & Permits",
    # لوحة الإدارة
    "🛡  نسخة احتياطية الآن": "🛡  Backup Now",
    "↩  استعادة نسخة احتياطية": "↩  Restore Backup",
    "📝  سجلّ التدقيق": "📝  Audit Log",
    "👥  إدارة الحسابات": "👥  Manage Accounts",
    "🔑  تغيير كلمة المرور": "🔑  Change Password",
    "🗝  مفتاح استرداد جديد": "🗝  New Recovery Key",
    "🔒  القفل التلقائي عند الخمول": "🔒  Auto-lock on Idle",
    "🌐  اللغة / Language": "🌐  Language / اللغة",
    "🚪  تسجيل الخروج": "🚪  Sign Out",
    # استيراد
    "📁  استيراد من إكسل": "📁  Import from Excel",
    "📷  إضافة جوازات (صور / PDF)": "📷  Add Passports (Images/PDF)",
    # الترويسة والأزرار
    "برنامج الحج موسم": "Hajj Season",
    "🏠  لوحة التحكم": "🏠  Dashboard",
    "🔒 البيانات مشفّرة": "🔒 Data encrypted",
    "تغيير كلمة المرور": "Change password",
    "مفتاح استرداد جديد": "New recovery key",
    "🚪  تسجيل الخروج ": "🚪  Sign Out ",   # زر الترويسة (بمسافة)
    "🔓 وضع مفتوح — بلا رقم سري": "🔓 Open mode — no password",
    "البيانات غير مشفّرة (مؤقتاً)": "Data not encrypted (temp)",
    # شريط الفلاتر
    "🔍 بحث": "🔍 Search",
    "الفلاتر  ▾": "Filters  ▾",
    "⭐ فلاتر محفوظة": "⭐ Saved Filters",
    "مسح الفلاتر": "Clear Filters",
    "إغلاق": "Close",
}

# عناوين أعمدة الجدول بالإنجليزية (حسب مفتاح الحقل)
_FIELD_EN = {
    "serial": "No.", "family_number": "Family No.", "reference_number": "Ref.",
    "full_name_ar": "Name (AR)", "full_name_en": "Name (EN)",
    "phone": "Phone", "program": "Program", "group": "Group", "status": "Status",
    "hotel": "Hotel", "room_type": "Room Type", "room_number": "Room No.",
    "sex": "Sex", "nationality_ar": "Nationality", "birth_date": "Birth Date",
    "passport_number": "Passport No.", "expiry_date": "Passport Expiry",
    "airline": "Airline", "flight_number": "Flight No.", "travel_class": "Class",
    "pnr": "PNR", "arrival_date": "Arrival Date", "arrival_time": "Arrival Time",
    "departure_date": "Departure Date", "departure_time": "Departure Time",
    "transport": "Transport", "executive_service": "VIP Service",
    "wheelchair": "Wheelchair", "hady": "Hady",
    "program_value": "Program Value", "paid_amount": "Paid",
    "remaining_amount": "Remaining",
    "visa_number": "Visa No.", "visa_status": "Visa Status",
    "permit_status": "Hajj Permit", "masar_number": "Masar No.",
    "mahram_name": "Mahram", "mahram_relation": "Mahram Relation",
    "blood_type": "Blood Type", "medical_conditions": "Medical Conditions",
    "medications": "Medications", "vaccination": "Vaccination",
    "insurance": "Insurance", "emergency_name": "Emergency Contact",
    "emergency_phone": "Emergency Phone", "emergency_relation": "Emergency Relation",
    "notes": "Notes", "staff": "Staff", "warnings": "Warnings",
    "source_file": "Source File",
}

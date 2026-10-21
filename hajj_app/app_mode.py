"""وضع تشغيل البرنامج: **الحج** أو **العمرة**.

يُختار الوضع عند البدء (بعد الدخول)، ويمكن التبديل بينهما من داخل البرنامج.
لكل وضع:

* **ملفّ بيانات وإعدادات مستقلّ** (مشفّر بنفس مفتاح الحساب) فلا تختلط
  قوائم الحجّاج بالمعتمرين.
* **مسمّياته الخاصة** (العنوان، اسم البرنامج…).

واجهة العمرة هي نفس واجهة الحج القوية، لكن تُخفى فيها ميزات الحج الخاصة
(جدول المناسك، خيام المشاعر) لأنها لا تلزم العمرة.
"""

from __future__ import annotations

HAJJ = "hajj"
UMRAH = "umrah"
MODES = (HAJJ, UMRAH)

_current = HAJJ


def set_mode(mode: str) -> None:
    """يضبط الوضع الحالي (يتجاهل أي قيمة غير معروفة ويعود للحج)."""
    global _current
    _current = mode if mode in MODES else HAJJ


def get_mode() -> str:
    """الوضع الحالي: ``'hajj'`` أو ``'umrah'``."""
    return _current


def is_umrah() -> bool:
    return _current == UMRAH


def is_hajj() -> bool:
    return _current == HAJJ


# أسماء ملفّات البيانات والإعدادات لكل وضع.
# الحج يحتفظ بالأسماء القديمة حفاظاً على توافق البيانات الموجودة مسبقاً.
_DATA_FILE = {HAJJ: "hajjaj.json", UMRAH: "umrah.json"}
_SETTINGS_FILE = {HAJJ: "settings.json", UMRAH: "settings_umrah.json"}


def data_filename() -> str:
    """اسم ملفّ بيانات الوضع الحالي."""
    return _DATA_FILE.get(_current, _DATA_FILE[HAJJ])


def settings_filename() -> str:
    """اسم ملفّ إعدادات الوضع الحالي."""
    return _SETTINGS_FILE.get(_current, _SETTINGS_FILE[HAJJ])


# المسمّيات المعروضة لكل وضع.
_LABELS = {
    HAJJ: {
        "noun": "الحج",
        "program": "برنامج الحج",
        "program_season": "برنامج الحج موسم",
        "window_title": "برنامج الحج — إدارة بيانات الحجاج",
        "splash": "برنامج الحج",
        "release_name": "ميسّر الحج",
        "pilgrim": "حاج",
        "pilgrims": "الحجّاج",
    },
    UMRAH: {
        "noun": "العمرة",
        "program": "برنامج العمرة",
        "program_season": "برنامج العمرة موسم",
        "window_title": "برنامج العمرة — إدارة بيانات المعتمرين",
        "splash": "برنامج العمرة",
        "release_name": "ميسّر العمرة",
        "pilgrim": "معتمر",
        "pilgrims": "المعتمرون",
    },
}


def label(key: str, default: str = "") -> str:
    """مسمّى حسب الوضع الحالي (يعود لمسمّى الحج ثم إلى ``default``)."""
    cur = _LABELS.get(_current, _LABELS[HAJJ])
    return cur.get(key, _LABELS[HAJJ].get(key, default))


def mode_label(mode: str) -> str:
    """الاسم المعروض لوضعٍ معيّن (لأزرار شاشة الاختيار)."""
    return _LABELS.get(mode, _LABELS[HAJJ])["noun"]


# لون مميّز لكل وضع في واجهات الويب، ليعرف المستخدم فوراً في أيّ نظام هو:
# الحج برونزي (لون الهوية المعتاد) والعمرة أخضر. نفس القيَم في
# ``webapp/static/style.css`` (body.mode-…) — تُعدَّل معاً.
_THEME = {
    HAJJ: {"accent": "#8A6E4B", "deep": "#6E543A", "icon": "🕋", "letter": "ح"},
    UMRAH: {"accent": "#13795B", "deep": "#0D5A43", "icon": "🌙", "letter": "ع"},
}


def theme(mode: str) -> dict:
    """ألوان الوضع وأيقونته واسمه: accent/deep/icon/letter/noun."""
    t = dict(_THEME.get(mode, _THEME[HAJJ]))
    t["noun"] = mode_label(mode)
    return t


def favicon_href(mode: str) -> str:
    """أيقونة تبويب بلون الوضع وحرفه (ع/ح) — تميّز تبويبات الحج والعمرة."""
    from urllib.parse import quote
    t = theme(mode)
    svg = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>"
           f"<rect width='32' height='32' rx='8' fill='{t['accent']}'/>"
           "<text x='16' y='23' font-size='19' font-weight='700' "
           "text-anchor='middle' fill='white' font-family='Tahoma,sans-serif'>"
           f"{t['letter']}</text></svg>")
    return "data:image/svg+xml," + quote(svg, safe="/:='")

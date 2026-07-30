"""تصدير كشف الحجاج إلى ملف PDF بدعم كامل للعربية.

العربية تحتاج خطوتين قبل الرسم في ReportLab:
  1. تشكيل الحروف (وصلها ببعضها حسب موضعها) عبر arabic_reshaper
  2. ترتيب ثنائي الاتجاه (RTL) عبر python-bidi
بدونهما تظهر الحروف منفصلة ومقلوبة.
"""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image as RLImage, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
    TableStyle,
)

from .fields import FIELDS, PDF_FIELDS, row_dict
from .mrz import PassportData
from .rooming import ROOM_CATEGORIES, common_room_type, group_records_by_room

# خطوط ويندوز التي تدعم العربية، بالترتيب المفضّل
_FONT_CANDIDATES = (
    ("Amiri", r"C:\Windows\Fonts\amiri-regular.ttf", None),
    ("Tahoma", r"C:\Windows\Fonts\tahoma.ttf", r"C:\Windows\Fonts\tahomabd.ttf"),
    ("Arial", r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
    ("Segoe UI", r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\segoeuib.ttf"),
)

_FONT = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"
_registered = False

# عرض أعمدة جدول PDF بالنقاط (تقريبي — يُقاس نسبياً على عرض الصفحة).
# مضبوط على المحتوى الفعلي: التواريخ تحتاج سطراً واحداً بلا التفاف،
# والأسماء وحدها هي المسموح لها بالالتفاف على سطرين.
_PDF_WIDTHS = {
    "serial": 40,
    "family_number": 46,
    "reference_number": 52,
    "full_name_ar": 90,
    "full_name_en": 96,
    "hotel": 66,
    "room_type": 44,
    "room_number": 40,
    "sex": 32,
    "nationality_ar": 52,
    "birth_date": 50,
    "passport_number": 56,
    "airline": 54,
    "arrival_date": 50,
    "departure_date": 50,
    "transport": 52,
}

# ألوان علامة المصطفى للحج والعمرة: الأسود للعناوين، البرونزي للتمييز
_INK = colors.HexColor("#1A1A1A")
_ACCENT = colors.HexColor("#8A6E4B")        # البرونزي — العناوين والرؤوس
_ROOM_HEAD = colors.HexColor("#3A342B")     # داكن دافئ لرأس الغرفة

# لون مميّز لكل نوع غرفة حسب السعة (خلفية رأس الغرفة، والنص أبيض فوقها).
# ألوان داكنة كفاية ليُقرأ النص الأبيض، ومنسجمة مع هوية العلامة.
_ROOM_TYPE_COLORS = {
    1: colors.HexColor("#2F6F76"),   # مفرد — أزرق مخضرّ
    2: colors.HexColor("#3F6C46"),   # ثنائي — أخضر
    3: colors.HexColor("#6D5480"),   # ثلاثي — بنفسجي
    4: colors.HexColor("#8A6E4B"),   # رباعي — برونزي (العلامة)
    5: colors.HexColor("#4C5A78"),   # خماسي — أزرق رمادي
    6: colors.HexColor("#8A4B52"),   # سداسي — وردي داكن
}


def _room_type_color(capacity: int):
    """لون رأس الغرفة حسب سعتها؛ افتراضي داكن للأنواع غير المعروفة."""
    return _ROOM_TYPE_COLORS.get(capacity, _ROOM_HEAD)
_HEADER_TEXT = colors.white
_ALT_ROW = colors.HexColor("#F7F3EE")
_WARN_ROW = colors.HexColor("#FBF0DC")
_GRID = colors.HexColor("#D8CFC2")


def _register_fonts() -> None:
    """يسجّل أول خط عربي متاح. يتراجع إلى Helvetica إن لم يوجد أي خط."""
    global _FONT, _FONT_BOLD, _registered
    if _registered:
        return
    _registered = True

    for name, regular, bold in _FONT_CANDIDATES:
        if not Path(regular).is_file():
            continue
        try:
            pdfmetrics.registerFont(TTFont(name, regular))
            _FONT = name
            if bold and Path(bold).is_file():
                bold_name = f"{name}-Bold"
                pdfmetrics.registerFont(TTFont(bold_name, bold))
                _FONT_BOLD = bold_name
            else:
                _FONT_BOLD = name
            return
        except Exception:
            continue


from .paths import resource_dir

_LOGO_PATH = resource_dir() / "assets" / "logo.png"
_NIRVANA_PATH = resource_dir() / "assets" / "nirvana.png"


def _logo_flowable(max_width_pt: float = 118):
    """شعار الشركة كعنصر يُدرج أعلى الكشف، أو None إن تعذّر."""
    if not _LOGO_PATH.is_file():
        return None
    try:
        iw, ih = ImageReader(str(_LOGO_PATH)).getSize()
        width = min(max_width_pt, float(iw))
        logo = RLImage(str(_LOGO_PATH), width=width, height=width * ih / iw)
        logo.hAlign = "CENTER"
        return logo
    except Exception:
        return None


def ar(text) -> str:
    """يجهّز نصاً عربياً للعرض في PDF (تشكيل + ترتيب RTL)."""
    text = "" if text is None else str(text)
    if not text:
        return ""
    try:
        shaped = get_display(arabic_reshaper.reshape(text))
    except Exception:
        shaped = text
    # علامات التوجيه تؤدي دورها أثناء الترتيب فقط؛ نحذفها بعده لأن
    # الخطوط لا تملك رسماً لها فتظهر كمربعات فارغة.
    return shaped.replace("‎", "").replace("‏", "")


def ltr(text) -> str:
    """يحمي نصاً لاتينياً داخل جملة عربية من إعادة الترتيب.

    خوارزمية bidi تقلب مجموعات الأرقام المفصولة بشرطات داخل سياق عربي،
    فيصبح 2026-07-20 هكذا 20-07-2026. علامتا LRM تثبّتان الاتجاه.
    """
    return f"‎{text}‎" if text else ""


def _ar_para(text, style, maxw: float) -> "Paragraph":
    """فقرة عربية بلفٍّ يدوي يحافظ على ترتيب الأسطر رأسياً.

    ``ar`` تطبّق bidi على النص كاملاً فيصير بترتيب بصري معكوس؛ فلو تُرك اللفّ
    لـ reportlab لَقسّم النص المعكوس فجاءت الأسطر بترتيب رأسي مقلوب (آخر سطر
    يظهر أولاً). لذا نلفّ الكلمات منطقياً حسب العرض، ثم نطبّق ``ar`` على كل
    سطر ونصلها بـ ``<br/>`` فلا يعيد reportlab اللفّ ويبقى الترتيب سليماً.
    """
    font, size = style.fontName, style.fontSize
    lines: list[str] = []
    for para in str(text).split("\n"):
        words = para.split()
        if not words:
            lines.append("")
            continue
        cur = ""
        for w in words:
            trial = (cur + " " + w).strip()
            if not cur or pdfmetrics.stringWidth(ar(trial), font, size) <= maxw:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
    html = "<br/>".join(ar(ln) for ln in lines) or " "
    return Paragraph(html, style)


def _ar_cells(values, style, colw, pad: float = 2) -> list:
    """يبني صفّ خلايا عربية بلفٍّ يدوي سليم، كلٌّ حسب عرض عمودها.

    ``colw`` عرض الأعمدة (نقاط)، و``pad`` حشو الجانبين في الجدول. يمنع قلب
    ترتيب الأسطر رأسياً في أي خلية قد تلتفّ على أكثر من سطر (انظر ``_ar_para``).
    """
    return [_ar_para(v, style, colw[i] - 2 * pad - 1)
            for i, v in enumerate(values)]


def _styles() -> dict[str, ParagraphStyle]:
    return {
        "title": ParagraphStyle(
            "title", fontName=_FONT_BOLD, fontSize=17, alignment=1,
            textColor=_INK, leading=23, spaceAfter=7,
        ),
        "subtitle": ParagraphStyle(
            "subtitle", fontName=_FONT, fontSize=9.5, alignment=1,
            textColor=colors.HexColor("#666666"), leading=13, spaceAfter=11,
        ),
        "cell": ParagraphStyle(
            "cell", fontName=_FONT, fontSize=7.5, alignment=1, leading=9.5,
        ),
        "head": ParagraphStyle(
            "head", fontName=_FONT_BOLD, fontSize=8, alignment=1,
            textColor=_HEADER_TEXT, leading=10,
        ),
    }


def _footer(canvas, doc, title_text: str) -> None:
    """يرسم الترويسة السفلية مع رقم الصفحة."""
    canvas.saveState()
    canvas.setFont(_FONT, 7.5)
    canvas.setFillColor(colors.HexColor("#888888"))
    w, _ = landscape(A4)
    canvas.drawCentredString(w / 2, 10 * mm, ar(f"صفحة {doc.page}"))
    canvas.drawRightString(w - 12 * mm, 10 * mm, ar(title_text))
    canvas.drawString(12 * mm, 10 * mm, ar(date.today().isoformat()))
    canvas.restoreState()


def _footer_portrait(canvas, doc, title_text: str) -> None:
    """ترويسة سفلية لصفحات A4 العمودية (عرض مختلف عن العرضية)."""
    canvas.saveState()
    canvas.setFont(_FONT, 7.5)
    canvas.setFillColor(colors.HexColor("#888888"))
    w, _ = A4
    canvas.drawCentredString(w / 2, 10 * mm, ar(f"صفحة {doc.page}"))
    canvas.drawRightString(w - 12 * mm, 10 * mm, ar(title_text))
    canvas.drawString(12 * mm, 10 * mm, ar(date.today().isoformat()))
    canvas.restoreState()


def _grouped_rooms(
    records: list[PassportData],
) -> list[tuple[str, int, list[PassportData]]]:
    """يجمع السجلات في غرف مرتّبة (النوع تصاعدياً ثم الرقم)، للطباعة المفصولة.

    كل غرفة كتلة مستقلة يسبقها سطر عنوان. من لا غرفة له يُجمعون في كتلة
    أخيرة. يعيد قائمة (عنوان الغرفة، سعتها، سكانها) — السعة لتلوين النوع.
    """
    rooms, unroomed = group_records_by_room(records)
    show_hotel = len({hotel for hotel, *_ in rooms if hotel}) > 1

    result: list[tuple[str, int, list[PassportData]]] = []
    for hotel, cap, number, occ in rooms:
        rtype_disp = common_room_type(occ) or "غرفة"
        if number:
            label = f"غرفة {ltr(number)} — {rtype_disp} ({ltr(len(occ))}/{ltr(cap)})"
        else:
            label = f"{rtype_disp} ({ltr(len(occ))})"
        if show_hotel and hotel:
            label = f"{hotel} — {label}"
        result.append((label, cap, occ))

    if unroomed:
        result.append((f"بدون غرفة ({ltr(len(unroomed))})", 0, unroomed))
    return result


def _room_legend(grouped: list[tuple[str, int, list]]):
    """مفتاح ألوان أنواع الغرف — صف خلايا ملوّنة بأسماء الأنواع الموجودة فعلاً."""
    present = sorted({cap for _label, cap, _occ in grouped if cap in _ROOM_TYPE_COLORS})
    if not present:
        return None
    style = ParagraphStyle(
        "legend", fontName=_FONT_BOLD, fontSize=8, textColor=colors.white,
        alignment=1, leading=10,
    )
    cells = _ar_cells([ROOM_CATEGORIES[cap - 1] for cap in present],
                      style, [58] * len(present), pad=6)
    table = Table([cells], colWidths=[58] * len(present))
    ts = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("INNERGRID", (0, 0), (-1, -1), 1.5, colors.white),
    ]
    for index, cap in enumerate(present):
        ts.append(("BACKGROUND", (index, 0), (index, 0), _room_type_color(cap)))
    table.setStyle(TableStyle(ts))
    table.hAlign = "CENTER"
    return table


def export_pdf(
    records: list[PassportData],
    path: str | Path,
    *,
    title: str = "كشف الحجاج",
    with_cards: bool = False,
    group_by_room: bool = False,
) -> Path:
    """يصدّر السجلات إلى PDF.

    with_cards: يضيف صفحة بطاقة مفصّلة لكل حاج بعد الجدول.
    group_by_room: يجمع صفوف كل غرفة معاً ويفصل بينها بسطر عنوان، فتظهر
        كل غرفة ككتلة مستقلة — مفيد للطباعة بعد الفلترة حسب نوع الغرفة.
    """
    _register_fonts()
    path = Path(path)
    st = _styles()

    doc = SimpleDocTemplate(
        str(path), pagesize=landscape(A4),
        rightMargin=10 * mm, leftMargin=10 * mm,
        topMargin=12 * mm, bottomMargin=16 * mm,
        title=title, author="برنامج الحج",
    )

    story = []
    logo = _logo_flowable()
    if logo is not None:
        story.append(logo)
        story.append(Spacer(1, 5))
    story += [
        Paragraph(ar(title), st["title"]),
        Paragraph(
            ar(f"عدد الحجاج: {ltr(len(records))}  •  التاريخ: {ltr(date.today().isoformat())}"),
            st["subtitle"],
        ),
    ]

    # ---- الجدول الرئيسي ----
    # الأعمدة معكوسة لأن التخطيط من اليمين لليسار: مسلسل أقصى اليمين
    cols = list(reversed(PDF_FIELDS))
    weights = [_PDF_WIDTHS.get(f.key, f.width * 4) for f in cols]
    scale = doc.width / sum(weights)
    col_widths = [w * scale for w in weights]
    table_data = [_ar_cells([f.label for f in cols], st["head"], col_widths)]
    warn_rows: list[int] = []
    room_rows: list[tuple[int, int]] = []      # (رقم السطر، سعة الغرفة للتلوين)

    room_head = ParagraphStyle(
        "room_group", parent=st["cell"], fontName=_FONT_BOLD,
        textColor=colors.white, alignment=2, fontSize=8.5, leading=11,
    )

    def _add_occupant(rec: PassportData, serial: int) -> None:
        data = row_dict(rec, serial)
        if data.get("warnings"):
            warn_rows.append(len(table_data))
        table_data.append(
            _ar_cells([data.get(f.key, "") for f in cols], st["cell"], col_widths))

    grouped = _grouped_rooms(records) if group_by_room else []
    if group_by_room:
        # مفتاح ألوان أنواع الغرف أعلى الكشف (فقط الأنواع الموجودة)
        legend = _room_legend(grouped)
        if legend is not None:
            story.append(legend)
            story.append(Spacer(1, 7))

        # سطر عنوان يفصل كل غرفة عمّا قبلها، والمسلسل متسلسل عبر الكشف كله
        serial = 0
        for label, capacity, occupants in grouped:
            row = ["" for _ in cols]
            # سطر العنوان يمتدّ على كامل عرض الجدول (SPAN)
            row[0] = _ar_para(label, room_head, sum(col_widths) - 6)
            room_rows.append((len(table_data), capacity))
            table_data.append(row)
            for rec in occupants:
                serial += 1
                _add_occupant(rec, serial)
    else:
        for idx, rec in enumerate(records, start=1):
            _add_occupant(rec, idx)

    style = [
        ("BACKGROUND", (0, 0), (-1, 0), _ACCENT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]
    # التظليل المتناوب يربك الكتل المجمّعة، فنكتفي بأسطر العناوين للفصل
    if not group_by_room:
        style.append(("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ALT_ROW]))
    for r in warn_rows:
        style.append(("BACKGROUND", (0, r), (-1, r), _WARN_ROW))
    for r, capacity in room_rows:
        style.append(("SPAN", (0, r), (-1, r)))
        # لون رأس الغرفة حسب نوعها (سعتها) — تمييز بصري لأنواع الغرف
        style.append(("BACKGROUND", (0, r), (-1, r), _room_type_color(capacity)))

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle(style))
    story.append(table)

    # ---- بطاقات مفصّلة (اختياري) ----
    if with_cards and records:
        for idx, rec in enumerate(records, start=1):
            story.append(PageBreak())
            story.extend(_card(rec, idx, st, doc.width))

    doc.build(
        story,
        onFirstPage=lambda c, d: _footer(c, d, title),
        onLaterPages=lambda c, d: _footer(c, d, title),
    )
    return path


# البطاقة التفصيلية مقسّمة إلى مجموعات منطقية بدل قائمة طويلة واحدة
_CARD_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("بيانات الحاج", (
        "serial", "family_number", "reference_number", "full_name_ar",
        "full_name_en", "phone",
    )),
    ("بيانات الجواز", (
        "passport_number", "nationality_ar", "sex", "birth_date", "expiry_date",
    )),
    ("السفر", (
        "airline", "flight_number", "travel_class", "arrival_date",
        "arrival_time", "departure_date", "departure_time", "transport",
    )),
    ("الإقامة والخدمات", (
        "hotel", "room_type", "room_number", "executive_service",
        "wheelchair", "hady",
    )),
    ("المالية", ("program_value", "paid_amount", "remaining_amount")),
    ("أخرى", ("notes", "staff")),
)


def _card(rec: PassportData, serial: int, st: dict, width: float) -> list:
    """يبني بطاقة تفصيلية لحاج واحد تعرض كل الحقول مجمّعة."""
    data = row_dict(rec, serial)
    name = data.get("full_name_ar") or data.get("full_name_en") or "—"

    label_style = ParagraphStyle(
        "lbl", parent=st["cell"], fontName=_FONT_BOLD,
        textColor=_ACCENT, alignment=2,
    )
    group_style = ParagraphStyle(
        "grp", parent=st["cell"], fontName=_FONT_BOLD,
        textColor=colors.white, alignment=2, fontSize=8.5,
    )

    labels = {f.key: f.label for f in FIELDS}

    # عرض العمودين (القيمة 0.58، العنوان 0.42) لضبط اللفّ اليدوي مسبقاً
    col_w = (width - 8 * mm) / 2
    val_w = col_w * 0.58 - 13
    lbl_w = col_w * 0.42 - 13

    # نبني كل مجموعة ككتلة صفوف مستقلة، ثم نوزّعها على عمودين
    blocks: list[list] = []
    for group_title, keys in _CARD_GROUPS:
        present = [k for k in keys if data.get(k)]
        if not present:
            continue
        block = [(True, [_ar_para(group_title, group_style, col_w - 13), ""])]
        for k in present:
            # القيمة يساراً والعنوان يميناً (تخطيط RTL)
            block.append((False, [
                _ar_para(data[k], st["cell"], val_w),
                _ar_para(labels.get(k, k), label_style, lbl_w),
            ]))
        blocks.append(block)

    # نوزّع المجموعات على عمودين متوازنين في عدد الصفوف،
    # لأن صفحة A4 العرضية قصيرة ولا تتسع للبطاقة في عمود واحد.
    total_rows = sum(len(b) for b in blocks)
    left, right, count = [], [], 0
    for b in blocks:
        if count < total_rows / 2:
            right.append(b)
        else:
            left.append(b)
        count += len(b)

    elements = [Paragraph(ar(name), st["title"]), Spacer(1, 3 * mm)]

    def build(column_blocks, col_width: float):
        rows, group_rows = [], []
        for block in column_blocks:
            for is_group, cells in block:
                if is_group:
                    group_rows.append(len(rows))
                rows.append(cells)
        if not rows:
            return None
        style = [
            ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        for r in range(len(rows)):
            if r in group_rows:
                style.append(("SPAN", (0, r), (1, r)))
                style.append(("BACKGROUND", (0, r), (1, r), _ACCENT))
            else:
                style.append(("BACKGROUND", (1, r), (1, r), _ALT_ROW))
        t = Table(rows, colWidths=[col_width * 0.58, col_width * 0.42])
        t.setStyle(TableStyle(style))
        return t

    col_w = (width - 8 * mm) / 2
    right_t, left_t = build(right, col_w), build(left, col_w)

    if right_t is not None:
        # العمود الأيمن أولاً لأن التخطيط من اليمين لليسار
        outer = Table([[left_t or "", right_t]], colWidths=[col_w, col_w])
        outer.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
        ]))
        elements.append(outer)

    if data.get("warnings"):
        elements.append(Spacer(1, 4 * mm))
        elements.append(Paragraph(
            ar("تنبيه: " + data["warnings"]),
            ParagraphStyle("warn", parent=st["cell"], alignment=2,
                           textColor=colors.HexColor("#B26A00")),
        ))

    return elements


def export_attendance_pdf(records: list, path: str | Path, *,
                          stages: list, season: str = "",
                          title: str = "تقرير الحضور") -> Path:
    """يصدّر تقرير الحضور PDF: مصفوفة كل حاج × كل مرحلة (وقت الحضور أو «غائب»).

    A4 عرضي، مع ملخّص الحاضرين لكل مرحلة، وتلوين الحاضر أخضر والغائب أحمر.
    """
    _register_fonts()
    path = Path(path)
    st = _styles()
    stages = list(stages)

    doc = SimpleDocTemplate(
        str(path), pagesize=landscape(A4),
        rightMargin=10 * mm, leftMargin=10 * mm,
        topMargin=12 * mm, bottomMargin=16 * mm,
        title=title, author="برنامج الحج",
    )
    story = []
    logo = _logo_flowable()
    if logo is not None:
        story.append(logo)
        story.append(Spacer(1, 5))

    n = len(records)
    present = {s: sum(1 for r in records if s in (getattr(r, "checkins", {}) or {}))
               for s in stages}
    head_title = f"{title} — موسم {ltr(season)}هـ" if season else title
    summary = "    •    ".join(f"{s}: {ltr(present[s])}/{ltr(n)}" for s in stages)
    story += [Paragraph(ar(head_title), st["title"]),
              Paragraph(ar(summary), st["subtitle"])]

    base_heads = ["م", "اسم الحاج", "رقم الجواز", "الهاتف", "المجموعة"]
    heads = base_heads + stages
    ncols = len(heads)

    logical_rows = [heads]
    for i, r in enumerate(records, start=1):
        ck = getattr(r, "checkins", {}) or {}
        name = r.full_name_ar or r.full_name_en or r.passport_number or "—"
        row = [str(i), name, str(r.passport_number or ""), str(r.phone or ""),
               str(r.group or "")]
        row += [ck.get(s, "غائب") for s in stages]
        logical_rows.append(row)

    weights = list(reversed([22, 90, 55, 55, 45] + [58] * len(stages)))
    scale = doc.width / sum(weights)
    col_widths = [w * scale for w in weights]

    table_data = []
    for ridx, lrow in enumerate(logical_rows):
        style = st["head"] if ridx == 0 else st["cell"]
        table_data.append(
            _ar_cells([str(v) for v in reversed(lrow)], style, col_widths))

    style = [
        ("BACKGROUND", (0, 0), (-1, 0), _ACCENT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ALT_ROW]),
    ]
    green, red = colors.HexColor("#E3F3E8"), colors.HexColor("#FADFDD")
    for ridx in range(1, len(logical_rows)):
        for s_i in range(len(stages)):
            logical_col = 5 + s_i
            disp_col = (ncols - 1) - logical_col
            color = red if logical_rows[ridx][logical_col] == "غائب" else green
            style.append(("BACKGROUND", (disp_col, ridx), (disp_col, ridx), color))

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle(style))
    story.append(table)

    doc.build(story,
              onFirstPage=lambda c, d: _footer(c, d, title),
              onLaterPages=lambda c, d: _footer(c, d, title))
    return path


def export_travel_pdf(path: str | Path, *, program_name: str = "البرنامج الأول",
                      data: dict | None = None, itinerary: list | None = None,
                      season: str = "",
                      title: str = "مواعيد وتعليمات السفر") -> Path:
    """يصدّر وثيقة «مواعيد وتعليمات السفر» لرحلة برنامج: جدول الرحلة (ذهاب/عودة)
    + تعليمات السفر والحقائب + برنامج المناسك + ملاحظات + أرقام التواصل.
    """
    _register_fonts()
    path = Path(path)
    data = data or {}
    itinerary = itinerary or []

    doc = SimpleDocTemplate(
        str(path), pagesize=A4, rightMargin=15 * mm, leftMargin=15 * mm,
        topMargin=14 * mm, bottomMargin=16 * mm, title=title, author="برنامج الحج")

    h2 = ParagraphStyle("h2", fontName=_FONT_BOLD, fontSize=12.5, alignment=2,
                        textColor=_ACCENT, leading=17, spaceBefore=12, spaceAfter=5)
    body = ParagraphStyle("body", fontName=_FONT, fontSize=9.5, alignment=2,
                          textColor=_INK, leading=15)
    kv = ParagraphStyle("kv", fontName=_FONT, fontSize=9, alignment=2, leading=13)
    st = _styles()

    story = []
    logo = _logo_flowable()
    if logo is not None:
        story.append(logo)
        story.append(Spacer(1, 4))
    sub = f"رحلة الحج — {program_name}"
    if season:
        sub += f"   ·   موسم {ltr(season)}هـ"
    story += [Paragraph(ar(title), st["title"]),
              Paragraph(ar(sub), st["subtitle"])]

    # ---- جدول الرحلة (ذهاب/عودة) كأزواج مقروءة ----
    flight = data.get("flight", {}) if isinstance(data.get("flight"), dict) else {}

    kvh = ParagraphStyle("kvh", parent=kv, fontName=_FONT_BOLD)
    leg_cw = [doc.width * 0.66, doc.width * 0.34]

    def leg_block(head, prefix, fields):
        rows = []
        for label, key in fields:
            val = str(flight.get(prefix + key, "") or "").strip()
            if val:
                rows.append([_ar_para(val, kv, leg_cw[0] - 13),
                             _ar_para(label, kvh, leg_cw[1] - 13)])
        if not rows:
            return
        story.append(Paragraph(ar(head), h2))
        t = Table(rows, colWidths=leg_cw)
        t.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
            ("BACKGROUND", (1, 0), (1, -1), colors.HexColor("#F3EFE8")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t)

    legs = (("اليوم والتاريخ", "day"), ("مطار المغادرة", "dep"),
            ("رقم الرحلة", "flight"), ("الحضور/التحرّك للمطار", "report"),
            ("وقت الإقلاع", "takeoff"), ("مطار الوصول", "arr"),
            ("وقت الوصول", "land"))
    leg_block("✈ رحلة الذهاب", "out_", legs)
    leg_block("✈ رحلة العودة", "ret_", legs)

    # ---- الأقسام النصّية ----
    def section(head, text):
        text = str(text or "").strip()
        if not text:
            return
        story.append(Paragraph(ar(head), h2))
        for line in text.splitlines():
            line = line.strip()
            if line:
                story.append(Paragraph(ar(line), body))

    section("📋 تعليمات هامة للسفر", data.get("instructions"))
    section("🧳 تعليمات الأمتعة والحقائب", data.get("luggage"))

    # ---- برنامج المناسك (من جدول المناسك إن وُجد) ----
    if itinerary:
        story.append(Paragraph(ar("🗓 برنامج المناسك"), h2))
        heads = ["اليوم", "التاريخ", "النشاط/المنسك", "المكان"]
        weights = list(reversed([26, 26, 90, 30]))
        scale = doc.width / sum(weights)
        colw = [w * scale for w in weights]
        PAD = 4
        avail = [w - 2 * PAD - 1 for w in colw]
        table_data = [[_ar_para(h, st["head"], avail[i])
                       for i, h in enumerate(reversed(heads))]]
        for row in itinerary:
            row = list(row) + ["", "", "", ""]
            cells = list(reversed([row[0], row[1], row[2], row[3]]))
            table_data.append([_ar_para(str(v), st["cell"], avail[i])
                               for i, v in enumerate(cells)])
        t = Table(table_data, colWidths=colw, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _ACCENT),
            ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ALT_ROW]),
            ("LEFTPADDING", (0, 0), (-1, -1), PAD),
            ("RIGHTPADDING", (0, 0), (-1, -1), PAD),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t)

    section("📝 ملاحظات", data.get("notes"))
    section("📞 أرقام التواصل", data.get("contacts"))

    doc.build(story,
              onFirstPage=lambda c, d: _footer_portrait(c, d, title),
              onLaterPages=lambda c, d: _footer_portrait(c, d, title))
    return path


def export_itinerary_pdf(path: str | Path, *, rows: list | None = None,
                         season: str = "", title: str = "جدول المناسك") -> Path:
    """يصدّر جدول المناسك الزمني إلى PDF (A4 عمودي): يوم/تاريخ/نشاط/مكان/ملاحظة."""
    _register_fonts()
    path = Path(path)
    rows = rows or []
    doc = SimpleDocTemplate(
        str(path), pagesize=A4, rightMargin=13 * mm, leftMargin=13 * mm,
        topMargin=14 * mm, bottomMargin=16 * mm, title=title, author="برنامج الحج")
    st = _styles()
    story = []
    logo = _logo_flowable()
    if logo is not None:
        story.append(logo)
        story.append(Spacer(1, 4))
    sub = f"موسم {ltr(season)}هـ" if season else ""
    story.append(Paragraph(ar(title), st["title"]))
    if sub:
        story.append(Paragraph(ar(sub), st["subtitle"]))

    heads = ["اليوم", "التاريخ", "النشاط/المنسك", "المكان", "ملاحظة"]
    weights = list(reversed([28, 24, 78, 26, 40]))
    scale = doc.width / sum(weights)
    colw = [w * scale for w in weights]
    PAD = 4
    # العرض المتاح للنص داخل كل خلية (بعد حشو الجانبين) لِلَفٍّ يدوي سليم
    avail = [w - 2 * PAD - 1 for w in colw]
    table_data = [[_ar_para(h, st["head"], avail[i])
                   for i, h in enumerate(reversed(heads))]]
    for row in rows:
        row = list(row) + ["", "", "", "", ""]
        cells = list(reversed([row[0], row[1], row[2], row[3], row[4]]))
        table_data.append([_ar_para(str(v), st["cell"], avail[i])
                           for i, v in enumerate(cells)])
    t = Table(table_data, colWidths=colw, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _ACCENT),
        ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ALT_ROW]),
        ("LEFTPADDING", (0, 0), (-1, -1), PAD),
        ("RIGHTPADDING", (0, 0), (-1, -1), PAD),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    doc.build(story,
              onFirstPage=lambda c, d: _footer_portrait(c, d, title),
              onLaterPages=lambda c, d: _footer_portrait(c, d, title))
    return path


def export_umrah_pdf(records: list, path: str | Path, *, program_name: str = "",
                     title: str = "كشف المعتمرين", depart_date: str = "") -> Path:
    """يصدّر كشف معتمري برنامج عمرة إلى PDF (A4 عرضي) بمسمّيات العمرة.

    الأعمدة: التسلسل، الاسم، رقم العائلة، رقم الجواز، تاريخ الانتهاء، الجنسية،
    البرنامج، الفندق، نوع الغرفة، الطيران، القيمة، المدفوع، المتبقّي.
    الجوازات المنتهية أو التي تنتهي قبل ٦ أشهر تُعلَّم بعلامة ⚠ وخلفية تحذير.
    """
    from .umrah import (REPORT_COLUMNS, REPORT_STAFF_COLUMN, passport_flag,
                        report_row)
    # المعاينة تُظهر «الموظف المسؤول» عموداً أخيراً (من بيانات المعتمر)
    columns = list(REPORT_COLUMNS) + [REPORT_STAFF_COLUMN]

    _register_fonts()
    path = Path(path)
    doc = SimpleDocTemplate(
        str(path), pagesize=landscape(A4), rightMargin=10 * mm, leftMargin=10 * mm,
        topMargin=12 * mm, bottomMargin=16 * mm, title=title, author="ميسّر العمرة")
    st = _styles()
    story = []
    logo = _logo_flowable()
    if logo is not None:
        story.append(logo)
        story.append(Spacer(1, 4))
    full_title = f"{title} — {program_name}" if program_name else title
    story.append(Paragraph(ar(full_title), st["title"]))
    story.append(Paragraph(ar(
        f"عدد المعتمرين: {ltr(len(records))}  •  {ltr(date.today().isoformat())}"),
        st["subtitle"]))

    heads = [lbl for _k, lbl in columns]
    # أوزان الأعمدة (بالترتيب المنطقي) ثم تُعكس للعرض من اليمين لليسار
    weights = list(reversed(
        [34, 68, 42, 52, 52, 46, 60, 64, 42, 50, 44, 46, 46, 62]))
    scale = doc.width / sum(weights)
    colw = [w * scale for w in weights]
    PAD = 3
    avail = [w - 2 * PAD - 1 for w in colw]
    table_data = [_ar_cells(list(reversed(heads)), st["head"], avail)]
    warn_rows = []
    for i, rec in enumerate(records, start=1):
        row = report_row(rec, i, program_name)
        if passport_flag(rec, depart_date):        # جواز منتهٍ/قارب الانتهاء
            row["expiry_date"] = ("! " + row["expiry_date"]).strip()
            warn_rows.append(len(table_data))
        vals = [row[k] for k, _l in columns]
        table_data.append(_ar_cells(list(reversed(vals)), st["cell"], avail))
    t = Table(table_data, colWidths=colw, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), _ACCENT),
        ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ALT_ROW]),
        ("LEFTPADDING", (0, 0), (-1, -1), PAD),
        ("RIGHTPADDING", (0, 0), (-1, -1), PAD),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for r in warn_rows:
        style.append(("BACKGROUND", (0, r), (-1, r), _WARN_ROW))
    t.setStyle(TableStyle(style))
    story.append(t)
    doc.build(story,
              onFirstPage=lambda c, d: _footer(c, d, full_title),
              onLaterPages=lambda c, d: _footer(c, d, full_title))
    return path


def export_umrah_rooming_pdf(records: list, path: str | Path, *,
                             city_label: str = "", hotel: str = "",
                             nights: str = "", program_name: str = "",
                             room_field: str = "makkah_room") -> Path:
    """كشف تسكين معتمري برنامج في مدينة (مكة/المدينة) — مجموعاً بالغرف."""
    from .umrah import rooming_rooms

    _register_fonts()
    path = Path(path)
    doc = SimpleDocTemplate(
        str(path), pagesize=A4, rightMargin=13 * mm, leftMargin=13 * mm,
        topMargin=14 * mm, bottomMargin=16 * mm, title="كشف التسكين",
        author="ميسّر العمرة")
    st = _styles()
    story = []
    logo = _logo_flowable()
    if logo is not None:
        story.append(logo)
        story.append(Spacer(1, 4))
    title = f"كشف تسكين {city_label}"
    if program_name:
        title += f" — {program_name}"
    story.append(Paragraph(ar(title), st["title"]))
    sub = []
    if hotel:
        sub.append(f"الفندق: {hotel}")
    if nights:
        sub.append(f"الليالي: {ltr(nights)}")
    sub.append(f"المعتمرون: {ltr(len(records))}")
    story.append(Paragraph(ar("  •  ".join(sub)), st["subtitle"]))

    rooms, unassigned = rooming_rooms(records, room_field)
    heads = ["م", "الاسم", "رقم العائلة", "رقم الجواز", "نوع الغرفة", "الهاتف"]
    weights = list(reversed([24, 140, 66, 84, 58, 92]))
    scale = doc.width / sum(weights)
    colw = [w * scale for w in weights]
    PAD = 4
    avail = [w - 2 * PAD - 1 for w in colw]

    def room_block(label, occ):
        story.append(Spacer(1, 6))
        story.append(Paragraph(ar(label), st["subtitle"]))
        data = [_ar_cells(list(reversed(heads)), st["head"], avail)]
        for i, r in enumerate(occ, 1):
            vals = [str(i), r.full_name_ar or r.full_name_en or "",
                    r.family_number or "", r.passport_number or "",
                    r.room_type or "", r.phone or ""]
            data.append(_ar_cells(list(reversed(vals)), st["cell"], avail))
        t = Table(data, colWidths=colw, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _ACCENT),
            ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ALT_ROW]),
            ("LEFTPADDING", (0, 0), (-1, -1), PAD),
            ("RIGHTPADDING", (0, 0), (-1, -1), PAD),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t)

    for no, occ in rooms:
        cap = occ[0].room_type if occ else ""
        room_block(f"🛏 غرفة {ltr(no)}"
                   + (f" — {cap} ({ltr(len(occ))})" if cap else ""), occ)
    if unassigned:
        room_block(f"بلا غرفة ({ltr(len(unassigned))})", unassigned)

    doc.build(story,
              onFirstPage=lambda c, d: _footer_portrait(c, d, "كشف التسكين"),
              onLaterPages=lambda c, d: _footer_portrait(c, d, "كشف التسكين"))
    return path


def export_umrah_transport_pdf(records: list, path: str | Path, *,
                               program_name: str = "",
                               transport_pnr: str = "") -> Path:
    """كشف مواصلات معتمري برنامج — مجموعاً بالمركبات (فورد/جيمس)، مع الفندق."""
    from .umrah import rooming_rooms

    _register_fonts()
    path = Path(path)
    doc = SimpleDocTemplate(
        str(path), pagesize=A4, rightMargin=13 * mm, leftMargin=13 * mm,
        topMargin=14 * mm, bottomMargin=16 * mm, title="كشف المواصلات",
        author="ميسّر العمرة")
    st = _styles()
    story = []
    logo = _logo_flowable()
    if logo is not None:
        story.append(logo)
        story.append(Spacer(1, 4))
    title = "كشف المواصلات"
    if program_name:
        title += f" — {program_name}"
    story.append(Paragraph(ar(title), st["title"]))
    sub = [f"المعتمرون: {ltr(len(records))}"]
    if transport_pnr:
        sub.append(f"PNR النقل: {ltr(transport_pnr)}")
    story.append(Paragraph(ar("  •  ".join(sub)), st["subtitle"]))

    groups, unassigned = rooming_rooms(records, "vehicle")
    heads = ["م", "الاسم", "رقم العائلة", "رقم الجواز", "الهاتف", "الفندق"]
    weights = list(reversed([24, 138, 64, 84, 92, 104]))
    scale = doc.width / sum(weights)
    colw = [w * scale for w in weights]
    PAD = 4
    avail = [w - 2 * PAD - 1 for w in colw]

    def block(label, occ):
        story.append(Spacer(1, 6))
        story.append(Paragraph(ar(label), st["subtitle"]))
        data = [_ar_cells(list(reversed(heads)), st["head"], avail)]
        for i, r in enumerate(occ, 1):
            vals = [str(i), r.full_name_ar or r.full_name_en or "",
                    r.family_number or "", r.passport_number or "", r.phone or "",
                    r.hotel or ""]
            data.append(_ar_cells(list(reversed(vals)), st["cell"], avail))
        t = Table(data, colWidths=colw, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _ACCENT),
            ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ALT_ROW]),
            ("LEFTPADDING", (0, 0), (-1, -1), PAD),
            ("RIGHTPADDING", (0, 0), (-1, -1), PAD),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t)

    # نوع السيارة يُذكر في العنوان، ويوضَّح الاشتراك عند وجود أكثر من راكب
    for name, occ in groups:
        shared = "  —  مشتركة" if len(occ) > 1 else ""
        block(f"🚐 {name}  ({ltr(len(occ))} راكب){shared}", occ)
    if unassigned:
        block(f"بلا مركبة ({ltr(len(unassigned))})", unassigned)

    doc.build(story,
              onFirstPage=lambda c, d: _footer_portrait(c, d, "كشف المواصلات"),
              onLaterPages=lambda c, d: _footer_portrait(c, d, "كشف المواصلات"))
    return path


def export_umrah_finance_pdf(records: list, path: str | Path, *,
                             program_name: str = "") -> Path:
    """الملخّص المالي لبرنامج عمرة: الإجماليات، توزيع طرق الدفع، والمتأخّرات."""
    from .fields import format_amount, parse_amount

    _register_fonts()
    path = Path(path)
    doc = SimpleDocTemplate(
        str(path), pagesize=A4, rightMargin=14 * mm, leftMargin=14 * mm,
        topMargin=13 * mm, bottomMargin=16 * mm, title="الملخّص المالي",
        author="ميسّر العمرة")
    st = _styles()
    story = []
    logo = _logo_flowable(max_width_pt=120)
    if logo is not None:
        story.append(logo)
        story.append(Spacer(1, 4))
    title = "الملخّص المالي" + (f" — {program_name}" if program_name else "")
    story.append(Paragraph(ar(title), st["title"]))
    story.append(Paragraph(ar(
        f"عدد المعتمرين: {ltr(len(records))}  •  {ltr(date.today().isoformat())}"),
        st["subtitle"]))

    total = sum(parse_amount(r.program_value) or 0 for r in records)
    paid = sum(parse_amount(r.paid_amount) or 0 for r in records)
    remaining = total - paid
    pct = f"{(paid / total * 100):.0f}%" if total else "0%"

    sect = ParagraphStyle("uf", fontName=_FONT_BOLD, fontSize=12, alignment=2,
                          textColor=_ACCENT, spaceBefore=10, spaceAfter=5)
    lbl = ParagraphStyle("ufl", parent=st["cell"], fontName=_FONT_BOLD,
                         textColor=_ACCENT, alignment=2)
    val = ParagraphStyle("ufv", parent=st["cell"], alignment=1)

    story.append(Paragraph(ar("الإجماليات"), sect))
    rows = [("عدد المعتمرين", ltr(len(records))),
            ("إجمالي قيمة البرامج", format_amount(total)),
            ("المحصّل", format_amount(paid)),
            ("المتبقّي", format_amount(remaining)),
            ("نسبة التحصيل", pct)]
    fin_cw = [doc.width * 0.55, doc.width * 0.45]
    fdata = [[_ar_para(v, val, fin_cw[0] - 13), _ar_para(k, lbl, fin_cw[1] - 13)]
             for k, v in rows]
    ft = Table(fdata, colWidths=fin_cw)
    ft.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("BACKGROUND", (1, 0), (1, -1), _ALT_ROW),
    ]))
    story.append(ft)

    # توزيع طرق الدفع
    methods: dict = {}
    for r in records:
        if parse_amount(r.paid_amount):
            m = str(getattr(r, "payment_method", "") or "").strip() or "غير محدّد"
            methods[m] = methods.get(m, 0) + 1
    if methods:
        story.append(Paragraph(ar("توزيع طرق الدفع"), sect))
        mrows = [(m, ltr(c)) for m, c in methods.items()]
        mdata = [[_ar_para(str(c), val, fin_cw[0] - 13),
                  _ar_para(m, lbl, fin_cw[1] - 13)] for m, c in mrows]
        mt = Table(mdata, colWidths=fin_cw)
        mt.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("BACKGROUND", (1, 0), (1, -1), _ALT_ROW),
        ]))
        story.append(mt)

    # تفاصيل الدفع لكل معتمر (كم دفع ونوع الغرفة وطريقة الدفع والموظف المسؤول)
    story.append(Paragraph(ar("تفاصيل الدفع"), sect))
    dheads = ["م", "اسم المعتمر", "رقم العائلة", "نوع الغرفة", "القيمة",
              "المدفوع", "المتبقّي", "طريقة الدفع", "الموظف المسؤول"]
    dweights = list(reversed([20, 104, 48, 54, 50, 50, 50, 58, 62]))
    dscale = doc.width / sum(dweights)
    dcolw = [w * dscale for w in dweights]
    davail = [w - 9 for w in dcolw]
    ddata = [_ar_cells(list(reversed(dheads)), st["head"], davail)]
    for i, r in enumerate(records, 1):
        v = parse_amount(r.program_value) or 0
        p = parse_amount(r.paid_amount) or 0
        vals = [str(i), r.full_name_ar or r.full_name_en or "—",
                r.family_number or "—", r.room_type or "—", format_amount(v),
                format_amount(p), format_amount(v - p),
                str(getattr(r, "payment_method", "") or "—"), r.staff or "—"]
        ddata.append(_ar_cells(list(reversed(vals)), st["cell"], davail))
    dt = Table(ddata, colWidths=dcolw, repeatRows=1)
    dt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _ACCENT),
        ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ALT_ROW]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(dt)

    # المتأخّرات
    owe = [(r, (parse_amount(r.program_value) or 0) - (parse_amount(r.paid_amount) or 0))
           for r in records]
    owe = [(r, a) for r, a in owe if a > 0]
    story.append(Paragraph(
        ar(f"المتأخّرات ({ltr(len(owe))})"), sect))
    if owe:
        heads = ["م", "اسم المعتمر", "رقم العائلة", "الهاتف", "القيمة",
                 "المدفوع", "المتبقّي"]
        weights = list(reversed([22, 128, 56, 80, 62, 62, 62]))
        scale = doc.width / sum(weights)
        colw = [w * scale for w in weights]
        avail = [w - 9 for w in colw]
        data = [_ar_cells(list(reversed(heads)), st["head"], avail)]
        for i, (r, a) in enumerate(owe, 1):
            vals = [str(i), r.full_name_ar or r.full_name_en or "—",
                    r.family_number or "—", r.phone or "—",
                    format_amount(parse_amount(r.program_value) or 0),
                    format_amount(parse_amount(r.paid_amount) or 0),
                    format_amount(a)]
            data.append(_ar_cells(list(reversed(vals)), st["cell"], avail))
        t = Table(data, colWidths=colw, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _ACCENT),
            ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ALT_ROW]),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t)
    else:
        story.append(Paragraph(ar("لا متأخّرات — كل المبالغ محصّلة ✓"),
                               st["subtitle"]))

    doc.build(story,
              onFirstPage=lambda c, d: _footer_portrait(c, d, "الملخّص المالي"),
              onLaterPages=lambda c, d: _footer_portrait(c, d, "الملخّص المالي"))
    return path


_FAINT_LOGO_CACHE: dict = {}


def _faint_logo_reader():
    """نسخة باهتة من الشعار (على خلفية بيضاء) للاستعمال كعلامة مائية."""
    if "r" in _FAINT_LOGO_CACHE:
        return _FAINT_LOGO_CACHE["r"]
    reader = None
    try:
        if _LOGO_PATH.is_file():
            from PIL import Image as _PImage
            im = _PImage.open(str(_LOGO_PATH)).convert("RGBA")
            white = _PImage.new("RGBA", im.size, (255, 255, 255, 255))
            comp = _PImage.alpha_composite(white, im).convert("RGB")
            faded = _PImage.blend(white.convert("RGB"), comp, 0.08)
            bio = io.BytesIO()
            faded.save(bio, format="PNG")
            bio.seek(0)
            reader = ImageReader(bio)
    except Exception:
        reader = None
    _FAINT_LOGO_CACHE["r"] = reader
    return reader


def _passport_reader(rec, session):
    """قارئ صورة الجواز (كصورة شخصية) للمعتمر، أو None."""
    if session is None or not getattr(rec, "image_id", ""):
        return None
    try:
        from . import images as imgmod
        raw = imgmod.load_image(rec.image_id, imgmod.PASSPORT, session)
        img = imgmod.to_pil_image(raw) if raw else None
        if img is None:
            return None
        bio = io.BytesIO()
        img.convert("RGB").save(bio, format="PNG")
        bio.seek(0)
        return ImageReader(bio)
    except Exception:
        return None


def export_umrah_cards_pdf(records: list, path: str | Path, *,
                           program_name: str = "", company=None, session=None,
                           emergency_uae: str = "", emergency_ksa: str = "") -> Path:
    """بطاقات عمرة طولية بمقاس موحّد ٥٫٢سم×٨سم للطباعة والقصّ لاحقاً.

    كل بطاقة: شعار الشركة (خلفية موحّدة)، أيقونة رجل/امرأة حسب الجنس، الاسم،
    الهاتف، الفندق، الطيران (بلا رقم رحلة/PNR)، وأرقام طوارئ الإمارات والسعودية.
    """
    from reportlab.pdfgen.canvas import Canvas

    _register_fonts()
    path = Path(path)
    co = company_info(company)
    pw, ph = A4
    c = Canvas(str(path), pagesize=A4)

    CW, CH = 52 * mm, 80 * mm                 # مقاس البطاقة الموحّد (طولي)
    mx, my = 10 * mm, 10 * mm
    gx, gy = 5 * mm, 5 * mm
    cols = max(1, int((pw - 2 * mx + gx) // (CW + gx)))
    per_page = cols * max(1, int((ph - 2 * my + gy) // (CH + gy)))
    wm = _faint_logo_reader()
    red = colors.HexColor("#8A2E2E")

    def draw_card(x, y, rec):
        # x,y = الركن السفلي الأيسر للبطاقة
        if wm is not None:
            try:
                iw, ih = wm.getSize()
                ww = CW * 0.78
                hh = ww * ih / iw
                if hh > CH * 0.5:
                    hh = CH * 0.5
                    ww = hh * iw / ih
                c.drawImage(wm, x + (CW - ww) / 2, y + (CH - hh) / 2, ww, hh,
                            mask="auto")
            except Exception:
                pass
        c.setStrokeColor(_ACCENT)
        c.setLineWidth(0.9)
        c.roundRect(x, y, CW, CH, 5, stroke=1, fill=0)
        # شريط العنوان العلوي
        bar_h = 15
        c.setFillColor(_ACCENT)
        c.rect(x, y + CH - bar_h, CW, bar_h, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont(_FONT_BOLD, 7.5)
        c.drawCentredString(x + CW / 2, y + CH - bar_h + 4,
                            ar(f"{co['name_ar']} — بطاقة عمرة"))
        # أيقونة رجل/امرأة حسب الجنس (بدل الصورة)
        ibw, ibh = 22 * mm, 26 * mm
        ibx = x + (CW - ibw) / 2
        iby = y + CH - bar_h - 6 - ibh
        woman = str(getattr(rec, "sex", "") or "").strip() in (
            "أنثى", "انثى", "F", "f", "Female", "female")
        c.setStrokeColor(_GRID)
        c.setLineWidth(0.5)
        c.rect(ibx, iby, ibw, ibh, stroke=1, fill=0)
        try:
            _draw_person_icon(c, ibx, iby, ibw, ibh, woman=woman)
        except Exception:
            pass

        cx = x + CW / 2
        ty = iby - 12
        c.setFillColor(_INK)
        c.setFont(_FONT_BOLD, 9)
        c.drawCentredString(cx, ty, ar(rec.full_name_ar or rec.full_name_en or "—"))

        rx = x + CW - 6

        def line(label, value, yy, color=_INK, size=7.5):
            c.setFillColor(color)
            c.setFont(_FONT, size)
            c.drawRightString(rx, yy, ar(f"{label}: {ltr(str(value or '—'))}"))

        line("الهاتف", rec.phone, ty - 16)
        line("الفندق", rec.hotel, ty - 30)
        line("الطيران", rec.airline, ty - 44)     # الطيران فقط بلا رقم رحلة/PNR
        if emergency_uae:
            line("طوارئ الإمارات", emergency_uae, y + 16, red, 7)
        if emergency_ksa:
            line("طوارئ السعودية", emergency_ksa, y + 6, red, 7)

    for i, rec in enumerate(records):
        if i and i % per_page == 0:
            c.showPage()
        idx = i % per_page
        r, col = divmod(idx, cols)
        x = mx + col * (CW + gx)
        y = ph - my - (r + 1) * CH - r * gy
        draw_card(x, y, rec)
    c.showPage()
    c.save()
    return path


def export_airline_pdf(
    records: list, path: str | Path, *, title: str = "Flight Manifest"
) -> Path:
    """يصدّر كشف الطيران إلى PDF — إنجليزي، من اليسار لليمين (LTR)."""
    from .airline import AIRLINE_COLUMNS, airline_rows

    _register_fonts()
    path = Path(path)

    doc = SimpleDocTemplate(
        str(path), pagesize=landscape(A4),
        rightMargin=10 * mm, leftMargin=10 * mm,
        topMargin=12 * mm, bottomMargin=16 * mm,
        title=title, author="برنامج الحج",
    )
    head = ParagraphStyle("ahead", fontName=_FONT_BOLD, fontSize=8.5,
                          alignment=1, textColor=_HEADER_TEXT, leading=11)
    cell = ParagraphStyle("acell", fontName=_FONT, fontSize=8, alignment=1, leading=10)
    title_style = ParagraphStyle("atitle", fontName=_FONT_BOLD, fontSize=16,
                                 alignment=1, textColor=_INK, spaceAfter=6)

    story: list = []
    logo = _logo_flowable()
    if logo is not None:
        story.append(logo)
        story.append(Spacer(1, 5))
    story.append(Paragraph(title, title_style))
    story.append(Paragraph(f"Passengers: {len(records)}  •  {date.today().isoformat()}",
                           ParagraphStyle("asub", fontName=_FONT, fontSize=9,
                                          alignment=1, textColor=colors.HexColor("#666666"),
                                          spaceAfter=10)))

    data = [[Paragraph(str(h), head) for h in AIRLINE_COLUMNS]]
    for row in airline_rows(records):
        data.append([Paragraph(str(v), cell) for v in row])

    weights = [20, 78, 96, 62, 48, 48, 34, 46, 46, 40, 52]
    scale = doc.width / sum(weights)
    table = Table(data, colWidths=[w * scale for w in weights], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _INK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ALT_ROW]),
    ]))
    story.append(table)
    doc.build(
        story,
        onFirstPage=lambda c, d: _footer(c, d, title),
        onLaterPages=lambda c, d: _footer(c, d, title),
    )
    return path


# لون رأس الخيمة حسب التصنيف (رجال/نساء) — تمييز بصري في كشف المخيمات
_CLASS_COLORS = {
    "رجال": colors.HexColor("#2F6F76"),
    "نساء": colors.HexColor("#8A4B52"),
    "غير محدد": colors.HexColor("#3A342B"),
}


def export_camp_pdf(plan, path: str | Path,
                    *, title: str = "كشف تسكين المخيمات") -> Path:
    """يصدّر خطة المخيّم إلى PDF — مجموعاً بالخيام، كل خيمة كتلة ملوّنة بالتصنيف."""
    from .camps import tent_label

    _register_fonts()
    path = Path(path)
    st = _styles()

    doc = SimpleDocTemplate(
        str(path), pagesize=landscape(A4),
        rightMargin=10 * mm, leftMargin=10 * mm,
        topMargin=12 * mm, bottomMargin=16 * mm,
        title=title, author="برنامج الحج",
    )

    full_title = f"{title} — مخيّم {plan.camp}" if plan.camp else title
    story: list = []
    logo = _logo_flowable()
    if logo is not None:
        story.append(logo)
        story.append(Spacer(1, 5))
    story.append(Paragraph(ar(full_title), st["title"]))
    story.append(Paragraph(ar(
        f"القطاع: {ltr(plan.sector or '—')}  •  عدد الأشخاص في الخيمة: {ltr(plan.capacity)}"
        f"  •  عدد الخيام: {ltr(len(plan.tents))}  •  المجموع: {ltr(plan.total)}"
        f"  •  التاريخ: {ltr(date.today().isoformat())}"
    ), st["subtitle"]))

    # الأعمدة معكوسة لأن التخطيط من اليمين لليسار: «م» أقصى اليمين
    labels = ["م", "اسم الحاج", "رقم العائلة", "الفندق", "الغرفة", "الجنس", "الهاتف"]
    draw_labels = list(reversed(labels))
    weights = list(reversed([22, 122, 46, 74, 44, 40, 68]))
    scale = doc.width / sum(weights)
    col_widths = [w * scale for w in weights]
    table_data = [_ar_cells(draw_labels, st["head"], col_widths)]
    class_rows: list[tuple[int, str]] = []

    tent_head = ParagraphStyle(
        "tent_group", parent=st["cell"], fontName=_FONT_BOLD,
        textColor=colors.white, alignment=2, fontSize=8.5, leading=11,
    )

    def _room_of(rec) -> str:
        from .rooming import room_number_in_type
        return (str(rec.room_number or "").strip()
                or room_number_in_type(str(rec.room_type or "")))

    serial = 0
    for tent in plan.tents:
        row = ["" for _ in labels]
        row[0] = _ar_para(tent_label(tent), tent_head, sum(col_widths) - 6)
        class_rows.append((len(table_data), tent.classification))
        table_data.append(row)
        for occ in tent.occupants:
            serial += 1
            values = [
                ltr(serial), occ.name, ltr(occ.family),
                str(occ.record.hotel or "").strip(), ltr(_room_of(occ.record)),
                occ.sex, ltr(str(occ.record.phone or "").strip()),
            ]
            table_data.append(
                _ar_cells([v for v in reversed(values)], st["cell"], col_widths))

    style = [
        ("BACKGROUND", (0, 0), (-1, 0), _ACCENT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]
    for r, cls in class_rows:
        style.append(("SPAN", (0, r), (-1, r)))
        style.append(("BACKGROUND", (0, r), (-1, r),
                      _CLASS_COLORS.get(cls, _ROOM_HEAD)))

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle(style))
    story.append(table)

    doc.build(
        story,
        onFirstPage=lambda c, d: _footer(c, d, full_title),
        onLaterPages=lambda c, d: _footer(c, d, full_title),
    )
    return path


def export_tents_pdf(plan, path: str | Path,
                     *, campaign: str = "", title: str = "كشف المخيمات") -> Path:
    """يصدّر **كل خيمة في صفحة مستقلة**، بالأعمدة المبسّطة فقط.

    الأعمدة: التسلسل • اسم الحاج • القطاع • التصنيف • اسم الحملة.
    رقم الخيمة يظهر في عنوان الصفحة. مناسب لطباعة ورقة لكل خيمة وتسليمها.
    """
    _register_fonts()
    path = Path(path)
    st = _styles()
    campaign = str(campaign or "").strip()

    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        rightMargin=12 * mm, leftMargin=12 * mm,
        topMargin=14 * mm, bottomMargin=16 * mm,
        title=title, author="برنامج الحج",
    )
    heading = f"{title} — مخيّم {plan.camp}" if plan.camp else title

    # الأعمدة معكوسة للتخطيط من اليمين لليسار: «التسلسل» أقصى اليمين
    labels = ["التسلسل", "اسم الحاج", "القطاع", "التصنيف", "اسم الحملة"]
    draw_labels = list(reversed(labels))
    weights = list(reversed([30, 190, 60, 60, 130]))
    scale = doc.width / sum(weights)
    col_widths = [w * scale for w in weights]

    story: list = []
    for index, tent in enumerate(plan.tents):
        if index:
            story.append(PageBreak())
        logo = _logo_flowable()
        if logo is not None:
            story.append(logo)
            story.append(Spacer(1, 4))
        story.append(Paragraph(ar(heading), st["title"]))
        sub = f"خيمة رقم {ltr(tent.number)}  •  {tent.classification}"
        if tent.sector:
            sub += f"  •  قطاع {ltr(tent.sector)}"
        if campaign:
            sub += f"  •  {campaign}"
        sub += f"  •  العدد: {ltr(tent.count)}"
        story.append(Paragraph(ar(sub), st["subtitle"]))

        table_data = [_ar_cells(draw_labels, st["head"], col_widths)]
        for position, occ in enumerate(tent.occupants, start=1):
            values = [ltr(position), occ.name, tent.sector,
                      tent.classification, campaign]
            table_data.append(
                _ar_cells([v for v in reversed(values)], st["cell"], col_widths))

        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _ACCENT),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ALT_ROW]),
        ]))
        story.append(table)

    if not plan.tents:
        story.append(Paragraph(ar("لا توجد خيام."), st["subtitle"]))

    doc.build(
        story,
        onFirstPage=lambda c, d: _footer_portrait(c, d, heading),
        onLaterPages=lambda c, d: _footer_portrait(c, d, heading),
    )
    return path


def export_stats_pdf(records: list, path: str | Path, *,
                     title: str = "الإحصاءات والملخّص المالي",
                     season: str = "") -> Path:
    """يصدّر لوحة الإحصاءات والملخّص المالي إلى PDF (A4 عمودي)."""
    from .fields import format_amount
    from .stats import GROUPINGS, distribution, financial_summary, outstanding

    _register_fonts()
    path = Path(path)
    st = _styles()
    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        rightMargin=14 * mm, leftMargin=14 * mm,
        topMargin=12 * mm, bottomMargin=16 * mm,
        title=title, author="برنامج الحج",
    )
    head = ParagraphStyle("sh", fontName=_FONT_BOLD, fontSize=9, alignment=1,
                          textColor=_HEADER_TEXT, leading=12)
    cell = ParagraphStyle("sc", fontName=_FONT, fontSize=9, alignment=2, leading=12)
    cellc = ParagraphStyle("scc", parent=cell, alignment=1)
    sect = ParagraphStyle("ss", fontName=_FONT_BOLD, fontSize=12, alignment=2,
                          textColor=_ACCENT, spaceBefore=10, spaceAfter=5)

    story: list = []
    logo = _logo_flowable(max_width_pt=120)
    if logo is not None:
        story.append(logo)
        story.append(Spacer(1, 4))
    full_title = f"{title} — موسم {ltr(season)}هـ" if season else title
    story.append(Paragraph(ar(full_title), st["title"]))
    story.append(Paragraph(ar(
        f"عدد الحجّاج: {ltr(len(records))}  •  التاريخ: {ltr(date.today().isoformat())}"),
        st["subtitle"]))

    def table(header, rows, weights, aligns=None):
        w = list(reversed(weights))
        scale = doc.width / sum(w)
        cw = [x * scale for x in w]
        data = [_ar_cells(list(reversed(header)), head, cw, pad=6)]
        for row in rows:
            data.append(_ar_cells([str(v) for v in reversed(list(row))],
                                  cellc, cw, pad=6))
        t = Table(data, colWidths=cw, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _ACCENT),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ALT_ROW]),
        ]))
        return t

    # ---- الملخّص المالي ----
    fin = financial_summary(records)
    story.append(Paragraph(ar("الملخّص المالي"), sect))
    lblst = ParagraphStyle("fl", parent=cell, fontName=_FONT_BOLD, textColor=_ACCENT)
    valst = ParagraphStyle("fv", parent=cell, alignment=1)
    colors_by = {"المحصّل": colors.HexColor("#2E6B45"),
                 "المتبقّي": colors.HexColor("#B23A3A")}
    fin_cw = [doc.width * 0.55, doc.width * 0.45]
    fdata = []
    for label, value in fin.as_rows():
        vs = ParagraphStyle("fx", parent=valst, textColor=colors_by.get(label, _INK),
                            fontName=_FONT_BOLD if label in colors_by else _FONT)
        fdata.append([_ar_para(value, vs, fin_cw[0] - 13),
                      _ar_para(label, lblst, fin_cw[1] - 13)])
    ft = Table(fdata, colWidths=fin_cw)
    ft.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("BACKGROUND", (1, 0), (1, -1), _ALT_ROW),
    ]))
    story.append(ft)

    # ---- التوزيع ----
    for key, label in GROUPINGS:
        buckets = distribution(records, key)
        if not buckets:
            continue
        story.append(Paragraph(ar(f"التوزيع حسب: {label}"), sect))
        rows = [[b.label, ltr(b.count), f"{b.percent}%"] for b in buckets]
        story.append(table(["القيمة", "العدد", "النسبة"], rows, [200, 70, 70]))

    # ---- المتأخّرات ----
    owe = outstanding(records)
    total = sum(a for _r, a in owe)
    story.append(Paragraph(
        ar(f"المتأخّرات  ({ltr(len(owe))}، الإجمالي: {ltr(format_amount(total))})"), sect))
    if owe:
        rows = [[r.full_name_ar or r.full_name_en or "—",
                 ltr(str(r.phone or "").strip() or "—"), ltr(format_amount(a))]
                for r, a in owe]
        story.append(table(["اسم الحاج", "الهاتف", "المتبقّي"], rows, [200, 90, 80]))
    else:
        story.append(Paragraph(ar("لا متأخّرات — كل المبالغ محصّلة ✓"), st["subtitle"]))

    doc.build(story,
              onFirstPage=lambda c, d: _footer_portrait(c, d, title),
              onLaterPages=lambda c, d: _footer_portrait(c, d, title))
    return path


def build_receipt_description(rec, *, season: str = "", amount: float = 0.0) -> str:
    """نصّ افتراضي لخانة «وذلك عن» في الإيصال، يُبنى من بيانات الحاج."""
    from .fields import format_amount
    head = "وذلك عن: برنامج الحج"
    if season:
        head += f" موسم {season}هـ"
    parts = [head]
    if rec.hotel:
        hp = f"الإقامة في {rec.hotel}"
        if rec.room_type:
            hp += f" في غرفة {rec.room_type}"
        parts.append(hp)
    if amount:
        parts.append(f"والبالغ قيمته: {format_amount(amount)}")
    parts.append("وتم دفع المبلغ، والدفعات غير مستردة لاستخدامها في دفع الحجوزات.")
    return "، ".join(parts)


def export_receipt_pdf(rec, path: str | Path, *,
                       company: str = "المصطفى للحج والعمرة",
                       company_en: str = "Al Mustafa Hajj & Umrah",
                       season: str = "", number: str = "",
                       date_str: str = "", amount=None,
                       amount_words: str = "", description: str = "",
                       bank: str = "Bank Transfer") -> Path:
    """يبني **سند قبض (Receipt Voucher)** ثنائي اللغة لحاج واحد على صفحة A4
    عرضية، بنفس تخطيط النموذج الرسمي: ترويسة بالشعار، رقم السند، المستلَم منه،
    التاريخ، المبلغ رقماً وكتابةً، بيان «وذلك عن»، الإجمالي، والتواقيع."""
    from reportlab.pdfgen import canvas as _canvas
    from .fields import num_to_words_en, parse_amount

    _register_fonts()
    path = Path(path)

    name = rec.full_name_ar or rec.full_name_en or "—"
    if amount is None:
        amount = parse_amount(rec.paid_amount)
        if amount is None:
            amount = parse_amount(rec.program_value)
    amount = float(amount or 0.0)
    if not amount_words:
        amount_words = num_to_words_en(amount)
    number = str(number or "0001")
    if not date_str:
        date_str = date.today().strftime("%B %d, %Y")
    if not description:
        description = build_receipt_description(rec, season=season, amount=amount)
    amount_disp = f"AED {amount:,.2f}"
    total_disp = f"{amount:,.2f}"

    W, H = landscape(A4)
    c = _canvas.Canvas(str(path), pagesize=landscape(A4), pageCompression=1)
    c.setTitle("سند قبض")
    c.setAuthor("برنامج الحج")

    AF, AFB = _FONT, _FONT_BOLD
    EF, EFB = "Helvetica", "Helvetica-Bold"
    ink = _INK

    mx, my = 24, 26
    x0, x1 = mx, W - mx
    yt = H - my
    bw = x1 - x0

    def hline(yv):
        c.setLineWidth(0.9); c.setStrokeColor(ink); c.line(x0, yv, x1, yv)

    def vline(xv, ya, yc):
        c.setLineWidth(0.9); c.setStrokeColor(ink); c.line(xv, ya, xv, yc)

    # ارتفاعات الأقسام؛ الفراغ الأوسط يتمدّد ليملأ الصفحة تماماً
    h_head, h_title, h_rf, h_sum = 82, 46, 40, 40
    h_desc, h_total, h_chq, h_sig = 104, 30, 26, 66
    fixed = h_head + h_title + h_rf + h_sum + h_desc + h_total + h_chq + h_sig
    yb = my
    h_gap = (yt - yb) - fixed

    # الإطار الخارجي
    c.setLineWidth(1.2); c.setStrokeColor(ink)
    c.rect(x0, yb, bw, yt - yb, stroke=1, fill=0)

    logo_reader = None
    if _LOGO_PATH.is_file():
        try:
            logo_reader = ImageReader(str(_LOGO_PATH))
        except Exception:
            logo_reader = None

    # ----- الترويسة: الشعار | اسم الشركة بالإنجليزية -----
    y = yt
    yb_head = y - h_head
    logo_cell = 152
    if logo_reader is not None:
        iw, ih = logo_reader.getSize()
        lh = h_head - 20
        lw = lh * iw / ih
        if lw > logo_cell - 16:
            lw = logo_cell - 16; lh = lw * ih / iw
        c.drawImage(logo_reader, x0 + (logo_cell - lw) / 2,
                    yb_head + (h_head - lh) / 2, lw, lh,
                    preserveAspectRatio=True, mask="auto")
    vline(x0 + logo_cell, yb_head, y)
    c.setFillColor(ink); c.setFont(EFB, 27)
    c.drawCentredString((x0 + logo_cell + x1) / 2, yb_head + h_head / 2 - 9,
                        company_en)
    hline(yb_head)

    # ----- سطر العنوان: Receipt Voucher | No. -----
    y = yb_head
    yb_title = y - h_title
    no_div = x1 - bw * 0.24
    vline(no_div, yb_title, y)
    c.setFont(EFB, 20)
    c.drawCentredString((x0 + no_div) / 2, yb_title + h_title / 2 - 7,
                        "Receipt Voucher")
    c.setFont(EFB, 17)
    c.drawCentredString((no_div + x1) / 2, yb_title + h_title / 2 - 6,
                        f"No. {number}")
    hline(yb_title)

    # ----- الفراغ الأوسط -----
    y = yb_title
    yb_gap = y - h_gap
    hline(yb_gap)

    # حقل «تسمية: قيمة» فوق خطّ سفلي
    def field_line(lx, rx, label_en, value, *, value_ar, baseline):
        c.setFillColor(ink); c.setFont(EFB, 11)
        c.drawString(lx, baseline, label_en)
        us = lx + pdfmetrics.stringWidth(label_en, EFB, 11) + 8
        c.setLineWidth(0.8); c.setStrokeColor(ink)
        c.line(us, baseline - 3, rx, baseline - 3)
        if value:
            if value_ar:
                c.setFont(AFB, 12)
                c.drawCentredString((us + rx) / 2, baseline + 1, ar(value))
            else:
                c.setFont(EF, 11)
                c.drawString(us + 6, baseline + 1, str(value))

    xmid = x0 + bw * 0.60

    # ----- Received From / Date -----
    y = yb_gap
    yb_rf = y - h_rf
    base = yb_rf + 13
    field_line(x0 + 10, xmid - 14, "Received From:", name, value_ar=True, baseline=base)
    field_line(xmid + 12, x1 - 12, "Date:", date_str, value_ar=False, baseline=base)
    hline(yb_rf)

    # ----- THE SUM OF DHS / AMOUNT -----
    y = yb_rf
    yb_sum = y - h_sum
    base = yb_sum + 13
    field_line(x0 + 10, xmid - 14, "THE SUM OF DHS:", amount_words,
               value_ar=False, baseline=base)
    field_line(xmid + 12, x1 - 12, "AMOUNT:", amount_disp,
               value_ar=False, baseline=base)
    hline(yb_sum)

    # ----- البيان «وذلك عن» -----
    y = yb_sum
    yb_desc = y - h_desc

    def wrap_ar(text, font, size, maxw):
        lines, cur = [], ""
        for w in str(text).split():
            trial = (cur + " " + w).strip()
            if not cur or pdfmetrics.stringWidth(ar(trial), font, size) <= maxw:
                cur = trial
            else:
                lines.append(cur); cur = w
        if cur:
            lines.append(cur)
        return lines

    c.setFillColor(ink); c.setFont(AF, 11)
    ytxt = y - 22
    for ln in wrap_ar(description, AF, 11, bw - 24):
        c.drawRightString(x1 - 12, ytxt, ar(ln))
        ytxt -= 15.5
    hline(yb_desc)

    # ----- Total -----
    y = yb_desc
    yb_total = y - h_total
    vline(no_div, yb_total, y)
    c.setFillColor(ink); c.setFont(EFB, 12)
    c.drawRightString(no_div - 12, yb_total + h_total / 2 - 5, "Total :")
    c.setFont(EFB, 13)
    c.drawCentredString((no_div + x1) / 2, yb_total + h_total / 2 - 5, total_disp)
    hline(yb_total)

    # ----- Chq No / Chq Date / Bank -----
    y = yb_total
    yb_chq = y - h_chq
    segs = [("Chq No", 0.13, EFB), ("-", 0.09, EF), ("Chq Date :", 0.15, EFB),
            ("-", 0.09, EF), (f"Bank: {bank}", 0.54, EFB)]
    cx = x0
    cb = yb_chq + h_chq / 2 - 4
    for i, (txt, frac, fnt) in enumerate(segs):
        if i > 0:
            vline(cx, yb_chq, y)
        c.setFillColor(ink); c.setFont(fnt, 10)
        c.drawString(cx + 6, cb, txt)
        cx += bw * frac
    hline(yb_chq)

    # ----- التواقيع -----
    y = yb_chq
    xmid2 = (x0 + x1) / 2
    vline(xmid2, yb, y)
    c.setFillColor(ink); c.setFont(EFB, 11)
    c.drawString(x0 + 14, y - 22, "Accountant:")
    c.drawString(x0 + 14, yb + 12, "Signature :")
    if logo_reader is not None:
        iw, ih = logo_reader.getSize()
        sh = 34; sw = sh * iw / ih
        c.drawImage(logo_reader, x0 + 130, yb + 15, sw, sh,
                    preserveAspectRatio=True, mask="auto")
    c.drawString(xmid2 + 14, y - 22, "Receiver Name :")
    c.setLineWidth(0.8); c.setStrokeColor(ink)
    c.line(xmid2 + 120, y - 24, x1 - 14, y - 24)
    c.drawString(xmid2 + 14, yb + 12, "Signature :")
    c.line(xmid2 + 84, yb + 10, x1 - 14, yb + 10)

    c.showPage()
    c.save()
    return path


# ======================================================================
#  الفواتير والعقود (فاتورة ضريبية / فاتورة إلكترونية / عقد خدمات)
# ======================================================================

_COMPANY_DEFAULTS = {
    "name_ar": "المصطفى للحج والعمرة",
    "name_en": "Al Mustafa Hajj & Umrah",
    "trn": "", "address": "", "phone": "",
}


def merge_pdfs(paths, out_path: str | Path) -> Path:
    """يدمج عدّة ملفات PDF في ملف واحد بالترتيب. يتجاهل المتعذّر منها."""
    import fitz

    out_path = Path(out_path)
    merged = fitz.open()
    try:
        for p in paths:
            if not p or not Path(p).is_file():
                continue
            try:
                with fitz.open(str(p)) as src:
                    merged.insert_pdf(src)
            except Exception:
                continue
        merged.save(str(out_path))
    finally:
        merged.close()
    return out_path


def company_info(company=None) -> dict:
    """يكمّل بيانات الشركة بالقيم الافتراضية للحقول الناقصة."""
    d = dict(_COMPANY_DEFAULTS)
    if company:
        d.update({k: v for k, v in company.items() if v})
    return d


def build_invoice_item(rec, *, season: str = "") -> str:
    """وصف بند الفاتورة الافتراضي، يُبنى من بيانات الحاج."""
    desc = "برنامج الحج" + (f" موسم {season}هـ" if season else "")
    extra = []
    if rec.hotel:
        h = f"الإقامة في {rec.hotel}"
        if rec.room_type:
            h += f" - غرفة {rec.room_type}"
        extra.append(h)
    if extra:
        desc += " (" + "، ".join(extra) + ")"
    return desc


def export_invoice_pdf(rec, path: str | Path, *, company=None,
                       number: str = "INV-0001", date_str: str = "",
                       electronic: bool = False, vat_mode: str = "none",
                       season: str = "", item_desc: str = "",
                       notes: str = "") -> Path:
    """يبني **فاتورة ضريبية** (أو **فاتورة إلكترونية** بصيغة PEPPOL عند
    ``electronic=True``) لحاج واحد على صفحة A4 عمودية، ثنائية اللغة.

    الفاتورة الإلكترونية هنا هي التمثيل البشري المرافق لملف الـ XML الرسمي
    (UBL 2.1 / PINT AE) الذي يُبنى عبر :mod:`hajj_app.einvoice`."""
    from .fields import parse_amount, vat_breakdown

    _register_fonts()
    path = Path(path)
    st = _styles()
    co = company_info(company)

    gross = parse_amount(rec.program_value)
    if gross is None:
        gross = parse_amount(rec.paid_amount)
    gross = float(gross or 0.0)
    net, vat, total = vat_breakdown(gross, mode=vat_mode)
    paid = parse_amount(rec.paid_amount) or 0.0
    remaining = max(0.0, total - paid)

    if not date_str:
        date_str = date.today().isoformat()
    if not item_desc:
        item_desc = build_invoice_item(rec, season=season)

    title_ar = "فاتورة إلكترونية" if electronic else "فاتورة ضريبية"
    title_en = "E-Invoice (PEPPOL)" if electronic else "Tax Invoice"

    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        rightMargin=15 * mm, leftMargin=15 * mm,
        topMargin=13 * mm, bottomMargin=18 * mm,
        title=title_ar, author="برنامج الحج",
    )

    def money(v):
        return f"{v:,.2f}"

    lbl = ParagraphStyle("ilbl", parent=st["cell"], fontName=_FONT_BOLD,
                         textColor=_ACCENT, alignment=2, fontSize=9)
    val = ParagraphStyle("ival", parent=st["cell"], alignment=2, fontSize=9)
    comp = ParagraphStyle("comp", parent=st["subtitle"], fontSize=9,
                          leading=13, spaceAfter=1)

    story: list = []
    logo = _logo_flowable(max_width_pt=120)
    if logo is not None:
        story.append(logo)
        story.append(Spacer(1, 3))
    story.append(Paragraph(ar(co["name_ar"]), ParagraphStyle(
        "cn", parent=st["title"], fontSize=14, spaceAfter=1)))
    idbits = []
    if co["trn"]:
        idbits.append(ar("الرقم الضريبي (TRN): ") + co["trn"])
    if co["phone"]:
        idbits.append(ar("هاتف: ") + co["phone"])
    if idbits:
        story.append(Paragraph("  •  ".join(idbits), comp))
    if co["address"]:
        story.append(Paragraph(ar(co["address"]), comp))
    story.append(Spacer(1, 7))

    # شريط العنوان (بخلفية برونزية)
    tbar = Table([[Paragraph(
        ar(title_ar) + "   /   " + title_en,
        ParagraphStyle("tbar", parent=st["cell"], fontName=_FONT_BOLD,
                       textColor=colors.white, alignment=1, fontSize=14))]],
        colWidths=[doc.width])
    tbar.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _ACCENT),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(tbar)
    story.append(Spacer(1, 8))

    # بيانات الفاتورة | بيانات الحاج (عمودان)
    def kv(pairs):
        kv_cw = [doc.width * 0.30, doc.width * 0.20]
        rows = [[_ar_para(str(v) or "—", val, kv_cw[0] - 13),
                 _ar_para(k, lbl, kv_cw[1] - 13)] for k, v in pairs]
        t = Table(rows, colWidths=kv_cw)
        t.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("BACKGROUND", (1, 0), (1, -1), _ALT_ROW),
        ]))
        return t

    meta = kv([("رقم الفاتورة", number), ("التاريخ", date_str)])
    billto = kv([("المستفيد", rec.full_name_ar or rec.full_name_en or "—"),
                 ("الهاتف", rec.phone or ""),
                 ("رقم الجواز", rec.passport_number or ""),
                 ("الجنسية", rec.nationality_ar)])
    hdr = Table([[billto, meta]],
                colWidths=[doc.width * 0.5, doc.width * 0.5])
    hdr.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(hdr)
    story.append(Spacer(1, 10))

    # جدول البنود
    head = ParagraphStyle("ihd", parent=st["cell"], fontName=_FONT_BOLD,
                          textColor=colors.white, alignment=1, fontSize=9)
    cell = ParagraphStyle("icl", parent=st["cell"], alignment=1, fontSize=9,
                          leading=12)
    rcell = ParagraphStyle("ircl", parent=cell, alignment=2)
    it_cw = [doc.width * 0.17, doc.width * 0.17, doc.width * 0.10,
             doc.width * 0.50, doc.width * 0.06]
    items = [[_ar_para("المبلغ (د.إ)", head, it_cw[0] - 13),
              _ar_para("سعر الوحدة", head, it_cw[1] - 13),
              _ar_para("الكمية", head, it_cw[2] - 13),
              _ar_para("البيان", head, it_cw[3] - 13),
              Paragraph("#", head)]]
    items.append([Paragraph(money(net), cell), Paragraph(money(net), cell),
                  Paragraph("1", cell), _ar_para(item_desc, rcell, it_cw[3] - 13),
                  Paragraph("1", cell)])
    it = Table(items, colWidths=it_cw)
    it.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, _GRID),
        ("BACKGROUND", (0, 0), (-1, 0), _ACCENT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(it)
    story.append(Spacer(1, 10))

    # الإجماليات — عند «بدون استخراج» يُعرض السعر كاملاً شاملاً الضريبة بلا تقسيم
    if vat_mode == "none":
        tot_rows = [
            ("الإجمالي", money(total)),
            ("المدفوع", money(paid)),
            ("المتبقّي", money(remaining)),
        ]
        big_idx = 0
    else:
        tot_rows = [
            ("المجموع الفرعي (غير شامل الضريبة)", money(net)),
            ("ضريبة القيمة المضافة 5%", money(vat)),
            ("الإجمالي شامل الضريبة", money(total)),
            ("المدفوع", money(paid)),
            ("المتبقّي", money(remaining)),
        ]
        big_idx = 2
    trows = []
    for i, (k, v) in enumerate(tot_rows):
        big = (i == big_idx)
        vs = ParagraphStyle("tv", parent=val, alignment=0,
                            fontName=_FONT_BOLD if big else _FONT,
                            fontSize=11 if big else 9.5)
        ks = ParagraphStyle("tk", parent=lbl, fontSize=10 if big else 9,
                            textColor=colors.white if big else _ACCENT)
        trows.append([Paragraph(v, vs), _ar_para(k, ks, doc.width * 0.34 - 13)])
    tot = Table(trows, colWidths=[doc.width * 0.18, doc.width * 0.34])
    tstyle = [
        ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("BACKGROUND", (0, big_idx), (-1, big_idx), _ACCENT),
        ("TEXTCOLOR", (0, big_idx), (0, big_idx), colors.white),
    ]
    tot.setStyle(TableStyle(tstyle))

    side_cell = ""
    if electronic:
        from .einvoice import PINT_AE_CUSTOMIZATION
        info = ParagraphStyle("pep", parent=st["cell"], alignment=2,
                              fontSize=8.3, leading=12,
                              textColor=colors.HexColor("#555555"))
        side_cell = [
            Paragraph(ar("فاتورة إلكترونية بصيغة PEPPOL (PINT AE)"),
                      ParagraphStyle("peph", parent=info, fontName=_FONT_BOLD,
                                     textColor=_ACCENT, fontSize=9.5)),
            Spacer(1, 4),
            Paragraph(ar("معرّف التخصيص:"), info),
            Paragraph(PINT_AE_CUSTOMIZATION, ParagraphStyle(
                "pepid", parent=info, alignment=0, fontSize=7.8)),
            Spacer(1, 4),
            Paragraph(ar("الملف الرسمي المُرسَل عبر شبكة PEPPOL هو ملف "
                         "XML (UBL 2.1) المرافق لهذه الصفحة."), info),
        ]
    band = Table([[side_cell, tot]],
                 colWidths=[doc.width * 0.48, doc.width * 0.52])
    band.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                              ("ALIGN", (0, 0), (0, 0), "RIGHT")]))
    story.append(band)

    story.append(Spacer(1, 12))
    default_note = ("هذه فاتورة إلكترونية بصيغة PEPPOL (PINT AE). جميع المبالغ "
                    "بالدرهم الإماراتي (AED)." if electronic else
                    "هذه فاتورة ضريبية معتمدة. جميع المبالغ بالدرهم الإماراتي (AED).")
    note_txt = notes or default_note
    story.append(Paragraph(ar(note_txt), ParagraphStyle(
        "note", parent=st["cell"], alignment=2, fontSize=8.5,
        textColor=colors.HexColor("#666666"))))

    story.append(Spacer(1, 22))
    sign = ParagraphStyle("sg", parent=st["cell"], alignment=1, fontSize=9.5)
    srow = Table([[Paragraph(ar("توقيع المستلم"), sign),
                   Paragraph(ar("المحاسب / الختم"), sign)]],
                 colWidths=[doc.width / 2, doc.width / 2])
    srow.setStyle(TableStyle([("LINEABOVE", (0, 0), (0, 0), 0.6, _GRID),
                              ("LINEABOVE", (1, 0), (1, 0), 0.6, _GRID),
                              ("TOPPADDING", (0, 0), (-1, -1), 8)]))
    story.append(srow)

    ttl = title_ar
    doc.build(story,
              onFirstPage=lambda c, dd: _footer_portrait(c, dd, ttl),
              onLaterPages=lambda c, dd: _footer_portrait(c, dd, ttl))
    return path


def build_contract_body(rec, *, company=None, season: str = "",
                        vat_mode: str = "none") -> str:
    """نصّ بنود العقد الافتراضي (قابل للتحرير في النافذة)، مبنيّ من بيانات الحاج.

    كل بند فقرة تبدأ بسطر عنوان ثم سطر المحتوى، والفقرات يفصلها سطر فارغ.
    """
    from .fields import format_amount, parse_amount, vat_breakdown

    gross = parse_amount(rec.program_value) or parse_amount(rec.paid_amount) or 0.0
    net, vat, total = vat_breakdown(gross, mode=vat_mode)
    paid = parse_amount(rec.paid_amount) or 0.0
    remaining = max(0.0, total - paid)
    prog = "برنامج الحج" + (f" موسم {season}هـ" if season else "")
    hotel = rec.hotel or "—"
    room = f" في غرفة {rec.room_type}" if rec.room_type else ""
    # عند استخراج الضريبة فقط يُذكر مبلغها؛ وإلا تُعرَض القيمة كاملةً بلا عبارة
    vat_part = (f" (منها ضريبة القيمة المضافة {format_amount(vat)} درهماً)"
                if vat > 0 else "")

    clauses = [
        ("البند الأول: موضوع العقد",
         f"يقدّم الطرف الأول للطرف الثاني {prog}، ويشمل الإقامة في {hotel}{room} "
         "والإعاشة والتنقّلات الداخلية وتذاكر الطيران والهدي وفق البرنامج المعتمد."),
        ("البند الثاني: قيمة العقد",
         f"القيمة الإجمالية {format_amount(total)} درهماً{vat_part}. "
         f"المدفوع {format_amount(paid)} درهماً، والمتبقّي "
         f"{format_amount(remaining)} درهماً."),
        ("البند الثالث: الدفعات",
         "جميع الدفعات المسدّدة غير مستردّة وتُستخدَم في تأكيد الحجوزات والخدمات."),
        ("البند الرابع: التزامات الطرف الثاني",
         "يلتزم الطرف الثاني بصحّة بياناته، وبالمواعيد والتعليمات المنظّمة للرحلة، "
         "وبالأنظمة المعمول بها في المملكة العربية السعودية."),
        ("البند الخامس: القوة القاهرة",
         "لا يُسأل أيّ طرف عن الإخلال الناتج عن ظروف قاهرة خارجة عن الإرادة."),
        ("البند السادس: القانون والاختصاص",
         "يخضع هذا العقد لأنظمة دولة الإمارات العربية المتحدة، وتختصّ محاكمها "
         "المختصّة بالفصل في أيّ نزاع ينشأ عنه."),
    ]
    return "\n\n".join(f"{t}\n{b}" for t, b in clauses)


def export_contract_pdf(rec, path: str | Path, *, company=None,
                        number: str = "CON-0001", date_str: str = "",
                        season: str = "", body: str = "",
                        vat_mode: str = "none",
                        title_ar: str = "عقد خدمات حج",
                        title_en: str = "Hajj Services Agreement",
                        preamble: str = ("تمهيد: رغبةً من الطرف الثاني في أداء "
                                         "فريضة الحج، اتّفق الطرفان — وهما بكامل "
                                         "الأهلية — على ما يلي:")) -> Path:
    """يبني **عقد خدمات** بين الشركة (الطرف الأول) والمستفيد (الطرف الثاني)
    على صفحة A4 عمودية، مع بنود قابلة للتحرير وتوقيعَي الطرفين."""
    _register_fonts()
    path = Path(path)
    st = _styles()
    co = company_info(company)
    if not date_str:
        date_str = date.today().isoformat()
    if not body:
        body = build_contract_body(rec, company=co, season=season,
                                   vat_mode=vat_mode)

    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        rightMargin=17 * mm, leftMargin=17 * mm,
        topMargin=13 * mm, bottomMargin=18 * mm,
        title=title_ar, author="المصطفى للحج والعمرة",
    )

    comp = ParagraphStyle("ccomp", parent=st["subtitle"], fontSize=9,
                          leading=13, spaceAfter=1)
    lbl = ParagraphStyle("clbl", parent=st["cell"], fontName=_FONT_BOLD,
                         textColor=_ACCENT, alignment=2, fontSize=9)
    val = ParagraphStyle("cval", parent=st["cell"], alignment=2, fontSize=9)
    ptitle = ParagraphStyle("pt", parent=st["cell"], fontName=_FONT_BOLD,
                            textColor=_ACCENT, alignment=2, fontSize=10.5,
                            spaceBefore=8, spaceAfter=2, leading=15)
    pbody = ParagraphStyle("pb", parent=st["cell"], alignment=2, fontSize=9.5,
                           leading=15, spaceAfter=3)

    story: list = []
    logo = _logo_flowable(max_width_pt=115)
    if logo is not None:
        story.append(logo)
        story.append(Spacer(1, 3))
    story.append(Paragraph(ar(co["name_ar"]), ParagraphStyle(
        "ccn", parent=st["title"], fontSize=13, spaceAfter=1)))
    story.append(Paragraph(ar(title_ar) + f"  /  {title_en}",
                           ParagraphStyle("ct", parent=st["title"], fontSize=15,
                                          spaceBefore=4, spaceAfter=6)))
    meta_cw = [doc.width * 0.25, doc.width * 0.15,
               doc.width * 0.35, doc.width * 0.25]
    meta = Table([[Paragraph(date_str, val),
                   _ar_para("التاريخ", lbl, meta_cw[1] - 13),
                   Paragraph(number, val),
                   _ar_para("رقم العقد", lbl, meta_cw[3] - 13)]],
                 colWidths=meta_cw)
    meta.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, _GRID),
                              ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                              ("TOPPADDING", (0, 0), (-1, -1), 4),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                              ("BACKGROUND", (1, 0), (1, 0), _ALT_ROW),
                              ("BACKGROUND", (3, 0), (3, 0), _ALT_ROW)]))
    story.append(meta)
    story.append(Spacer(1, 8))

    # الطرفان
    p1 = (f"الطرف الأول (المزوّد): {co['name_ar']}"
          + (f" — الرقم الضريبي {co['trn']}" if co["trn"] else "")
          + (f" — هاتف {co['phone']}" if co["phone"] else "") + ".")
    who = rec.full_name_ar or rec.full_name_en or "—"
    p2 = (f"الطرف الثاني (المستفيد): {who}"
          + (f" — جواز رقم {rec.passport_number}" if rec.passport_number else "")
          + (f" — هاتف {rec.phone}" if rec.phone else "") + ".")
    story.append(Paragraph(ar(p1), pbody))
    story.append(Paragraph(ar(p2), pbody))
    story.append(Paragraph(ar(preamble), pbody))
    story.append(Spacer(1, 4))

    for para in body.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        lines = para.split("\n", 1)
        story.append(Paragraph(ar(lines[0]), ptitle))
        if len(lines) > 1 and lines[1].strip():
            story.append(Paragraph(ar(lines[1].strip()), pbody))

    story.append(Spacer(1, 24))
    sign = ParagraphStyle("csg", parent=st["cell"], fontName=_FONT_BOLD,
                          alignment=1, fontSize=10)
    subsign = ParagraphStyle("css", parent=st["cell"], alignment=1, fontSize=8.5,
                             textColor=colors.HexColor("#777777"))
    srow = Table([[Paragraph(ar("الطرف الثاني (المستفيد)"), sign),
                   Paragraph(ar("الطرف الأول (المزوّد)"), sign)],
                 [Paragraph(ar("التوقيع: ____________"), subsign),
                  Paragraph(ar("التوقيع والختم: ____________"), subsign)]],
                 colWidths=[doc.width / 2, doc.width / 2])
    srow.setStyle(TableStyle([("LINEABOVE", (0, 0), (0, 0), 0.6, _GRID),
                              ("LINEABOVE", (1, 0), (1, 0), 0.6, _GRID),
                              ("TOPPADDING", (0, 0), (-1, 0), 8),
                              ("TOPPADDING", (0, 1), (-1, 1), 14)]))
    story.append(srow)

    doc.build(story,
              onFirstPage=lambda c, dd: _footer_portrait(c, dd, title_ar),
              onLaterPages=lambda c, dd: _footer_portrait(c, dd, title_ar))
    return path


# ======================================================================
#  مستندات العمرة لكل معتمر: سند قبض، فاتورة، وعقد
# ======================================================================

def _umrah_services_text(rec) -> str:
    names = [s.get("name", "") for s in (getattr(rec, "umrah_services", None) or [])
             if s.get("name")]
    return "، ".join(names)


def export_umrah_receipt_pdf(rec, path: str | Path, *, program_name: str = "",
                             company=None, number: str = "",
                             date_str: str = "") -> Path:
    """سند قبض عمرة لمعتمر واحد (بمسمّيات العمرة وبيانات البرنامج)."""
    from .fields import format_amount, parse_amount

    co = company_info(company)
    amount = parse_amount(rec.paid_amount)
    if amount is None:
        amount = parse_amount(rec.program_value)
    amount = float(amount or 0.0)
    parts = [f"وذلك عن: برنامج {program_name}".strip()]
    if rec.hotel:
        hp = f"الإقامة في {rec.hotel}"
        if rec.room_type:
            hp += f" في غرفة {rec.room_type}"
        parts.append(hp)
    svc = _umrah_services_text(rec)
    if svc:
        parts.append(f"الخدمات: {svc}")
    if amount:
        parts.append(f"والبالغ قيمته: {format_amount(amount)}")
    parts.append("والدفعات غير مستردّة لاستخدامها في تأكيد الحجوزات.")
    return export_receipt_pdf(
        rec, path, company=co["name_ar"], company_en=co["name_en"],
        number=number or "0001", date_str=date_str, amount=amount,
        description="، ".join(parts))


def export_umrah_invoice_pdf(rec, path: str | Path, *, program_name: str = "",
                             company=None, number: str = "INV-0001") -> Path:
    """فاتورة عمرة لمعتمر واحد (بند البرنامج والخدمات والقيمة/المدفوع/المتبقّي)."""
    desc = f"برنامج {program_name}".strip()
    extra = []
    if rec.hotel:
        h = f"الإقامة في {rec.hotel}"
        if rec.room_type:
            h += f" - غرفة {rec.room_type}"
        extra.append(h)
    svc = _umrah_services_text(rec)
    if svc:
        extra.append(f"خدمات: {svc}")
    if extra:
        desc += " (" + "، ".join(extra) + ")"
    return export_invoice_pdf(rec, path, company=company, number=number,
                              item_desc=desc, vat_mode="none")


def export_umrah_contract_pdf(rec, path: str | Path, *, program_name: str = "",
                              company=None, number: str = "CON-0001") -> Path:
    """عقد خدمات عمرة بين الشركة والمعتمر (بنود العمرة والقيمة والدفعات)."""
    from .fields import format_amount, parse_amount

    total = parse_amount(rec.program_value) or parse_amount(rec.paid_amount) or 0.0
    paid = parse_amount(rec.paid_amount) or 0.0
    remaining = max(0.0, total - paid)
    hotel = rec.hotel or "—"
    room = f" في غرفة {rec.room_type}" if rec.room_type else ""
    svc = _umrah_services_text(rec)
    svc_part = f" والخدمات ({svc})" if svc else ""
    clauses = [
        ("البند الأول: موضوع العقد",
         f"يقدّم الطرف الأول للطرف الثاني برنامج {program_name}، ويشمل "
         f"الإقامة في {hotel}{room} والتنقّلات الداخلية وتذاكر الطيران{svc_part} "
         "وفق البرنامج المعتمد."),
        ("البند الثاني: قيمة العقد",
         f"القيمة الإجمالية {format_amount(total)} درهماً. المدفوع "
         f"{format_amount(paid)} درهماً، والمتبقّي {format_amount(remaining)} درهماً."),
        ("البند الثالث: الدفعات",
         "جميع الدفعات المسدّدة غير مستردّة وتُستخدَم في تأكيد الحجوزات والخدمات."),
        ("البند الرابع: التزامات الطرف الثاني",
         "يلتزم الطرف الثاني بصحّة بياناته وصلاحية جوازه (٦ أشهر فأكثر من تاريخ "
         "السفر)، وبالمواعيد والتعليمات المنظّمة للرحلة، وبالأنظمة المعمول بها في "
         "المملكة العربية السعودية."),
        ("البند الخامس: القوة القاهرة",
         "لا يُسأل أيّ طرف عن الإخلال الناتج عن ظروف قاهرة خارجة عن الإرادة."),
        ("البند السادس: القانون والاختصاص",
         "يخضع هذا العقد لأنظمة دولة الإمارات العربية المتحدة، وتختصّ محاكمها "
         "المختصّة بالفصل في أيّ نزاع ينشأ عنه."),
    ]
    body = "\n\n".join(f"{t}\n{b}" for t, b in clauses)
    return export_contract_pdf(
        rec, path, company=company, number=number, body=body, vat_mode="none",
        title_ar="عقد خدمات عمرة", title_en="Umrah Services Agreement",
        preamble=("تمهيد: رغبةً من الطرف الثاني في أداء العمرة، اتّفق الطرفان "
                  "— وهما بكامل الأهلية — على ما يلي:"))


# شروط وأحكام فاوتشر الفندق (نصّ الحملة — مُدقَّق إملائياً ولغوياً)
_VOUCHER_TERMS = (
    "عند استلام الضيف برنامج الرحلة، يُعدّ ذلك إقراراً وموافقةً منه على كل ما جاء "
    "فيه من شروط وأحكام.",
    "على الضيف التواجد في المطار قبل ساعتين ونصف على الأقل من موعد الرحلة، "
    "والالتزام بشروط الوزن المحدَّدة من شركة الطيران؛ وأيّ تأخير في مواعيد الرحلات "
    "أو إلغائها يقع على مسؤولية شركة الطيران وإدارتها، ولا تتحمّل {company} أيّ "
    "مسؤولية بهذا الخصوص.",
    "في حال تعديل التذكرة أو إلغائها، تُحتسب رسوم التعديل أو الإلغاء وفق شروط "
    "وقوانين شركات الطيران، وما يترتّب على ذلك من تغيير في درجة الطيران؛ وفي رحلات "
    "المجموعات (Groups) تكون قيمة التذكرة غير مسترَدّة وغير قابلة للتعديل أو "
    "الإلغاء، وتُحتسب كامل قيمتها.",
    "بعض شركات الطيران (مثل طيران العربية وفلاي دبي) لا تُلغي التذكرة ولا تُعيد "
    "قيمتها نقداً، ويمكن في بعض الحالات تعديل الحجز قبل موعد الإقلاع بمدّة لا تقلّ "
    "عن 24 ساعة، على أن تبقى قيمة التذكرة في حساب الضيف لاستخدامها خلال سنة من "
    "تاريخ الإصدار مع احتساب رسوم التعديل، ولا ينطبق ذلك على رحلات المجموعات.",
    "موعد دخول الغرف في الفندق الساعة 5:00 عصراً، وموعد المغادرة الساعة "
    "12:00 ظهراً.",
    "في حال إلغاء الحجز خلال المواسم المرتفعة (نهاية الأسبوع، رمضان، الإجازات) "
    "تُحتسب قيمة حجز الفندق كاملةً؛ أمّا في باقي أيام السنة فتُحتسب قيمة ليلة "
    "واحدة، على أن يتمّ الإلغاء قبل 72 ساعة من تاريخ السفر.",
    "أيّ تعديل في أنواع الغرف يكون حسب الإمكانية المتاحة في الفندق، ويخضع لسعر "
    "جديد.",
    "الغرف الثنائية عبارة عن سرير كبير أو سريرين منفصلين، والغرف الثلاثية عبارة عن "
    "سريرين منفصلين وسرير إضافي صغير (متحرّك) أو صوفا (Sofa bed)، وذلك حسب نظام "
    "الفندق.",
    "طلب الغرف المتجاورة والمتّصلة يكون من استقبال الفندق عند الدخول، وحسب "
    "الإمكانية المتاحة في الفندق.",
)


def build_voucher_data(rec, *, trip=None, program_name: str = "", company=None,
                       number: str = "", date_str: str = "",
                       booking_no: str = "",
                       office_manager: str = "أيمن الشهابي",
                       office_phone: str = "+971 54 996 4801",
                       makkah_ops: str = "خالد",
                       makkah_phone: str = "+966 54 300 3388") -> dict:
    """يبني بيانات فاوتشر الفندق (قاموس قابل للتعديل) من بيانات المعتمر والبرنامج.
    يُستخدم كقيَم افتراضية في محرّر الفاوتشر، ثم يُمرَّر إلى
    :func:`export_umrah_voucher_pdf` عبر الوسيط ``data``."""
    from datetime import timedelta

    from .umrah import _parse_date

    co = company_info(company)
    number = str(number or "MA0001")
    if not date_str:
        date_str = date.today().isoformat()

    def fmt(d):
        return d.isoformat() if d else ""

    # الإقامات: الدخول/المغادرة محسوبة تسلسلياً من تاريخ مغادرة البرنامج
    stays: list[list[str]] = []
    cur = _parse_date(getattr(trip, "depart_date", "")) if trip else None
    for label, hotel_f, nights_f in (
            ("مكة المكرّمة", "makkah_hotel", "makkah_nights"),
            ("المدينة المنوّرة", "madinah_hotel", "madinah_nights")):
        hotel = str(getattr(trip, hotel_f, "") or "") if trip else ""
        if not hotel:            # لا تسكين في هذه المدينة → تُلغى تلقائياً
            continue
        try:
            n = int(float(str(getattr(trip, nights_f, "") or "").strip() or 0))
        except ValueError:
            n = 0
        ci = cur
        cout = (cur + timedelta(days=n)) if (cur and n) else None
        stays.append([label, hotel, rec.room_type or "", "",
                      fmt(ci), fmt(cout), str(n or ""), "إفطار (B.B.)"])
        cur = cout or cur

    transport = str(getattr(rec, "vehicle", "") or "")
    if not transport and trip:
        transport = str(getattr(trip, "transport", "") or "")
    if not transport:
        transport = ("سيارة خاصة — استقبال من مطار جدة، والتنقّل بين الفنادق "
                     "والحرمين، والتوصيل إلى مطار المغادرة")

    terms = [t.format(company=co["name_ar"]) for t in _VOUCHER_TERMS]

    return {
        "title_ar": "فاوتشر الفندق",
        "title_en": "Hotel Voucher",
        "number": number,
        "date": date_str,
        "guest_ar": rec.full_name_ar or "",
        "guest_en": (rec.full_name_en or "").upper(),
        "booking_no": booking_no or "",
        "program": program_name or "",
        # كل صف: [المدينة، الفندق، نوع الغرفة، الإطلالة، الدخول، المغادرة،
        #          الليالي، الوجبات]
        "stays": stays,
        "transport": transport,
        "status": "مؤكّد / CONFIRMED",
        # كل جهة: [الصفة، الاسم، الهاتف]
        "contacts": [["مدير المكتب", office_manager, office_phone],
                     ["مدير العمليات في مكة", makkah_ops, makkah_phone]],
        "terms": terms,
    }


VOUCHER_STAY_HEADS = ("المدينة", "الفندق", "نوع الغرفة", "الإطلالة", "الدخول",
                      "المغادرة", "الليالي", "الوجبات")


def export_umrah_voucher_pdf(rec, path: str | Path, *, trip=None,
                             program_name: str = "", company=None,
                             number: str = "", date_str: str = "",
                             booking_no: str = "",
                             office_manager: str = "أيمن الشهابي",
                             office_phone: str = "+971 54 996 4801",
                             makkah_ops: str = "خالد",
                             makkah_phone: str = "+966 54 300 3388",
                             data: dict | None = None) -> Path:
    """فاوتشر فندق عمرة لمعتمر واحد بشعارَي الحملة، بيانات الضيف، إقامات
    مكة/المدينة (فندق، نوع الغرفة، الإطلالة، الدخول/المغادرة، الليالي، الوجبات)،
    خطة النقل، جهات التواصل، والشروط والأحكام.

    عند تمرير ``data`` (قاموس من :func:`build_voucher_data`، وقد عُدِّل يدوياً)
    يُبنى المستند من محتواه بالكامل؛ وإلّا يُبنى تلقائياً من ``rec`` و``trip``."""
    _register_fonts()
    path = Path(path)
    if data is None:
        data = build_voucher_data(
            rec, trip=trip, program_name=program_name, company=company,
            number=number, date_str=date_str, booking_no=booking_no,
            office_manager=office_manager, office_phone=office_phone,
            makkah_ops=makkah_ops, makkah_phone=makkah_phone)
    number = str(data.get("number") or "MA0001")
    date_str = str(data.get("date") or date.today().isoformat())

    doc = SimpleDocTemplate(
        str(path), pagesize=A4, rightMargin=12 * mm, leftMargin=12 * mm,
        topMargin=12 * mm, bottomMargin=15 * mm, title="فاوتشر الفندق",
        author="ميسّر العمرة")
    st = _styles()
    story = []

    def _logo_cell(pathobj, h):
        """شعار بارتفاع موحّد (للتناسق بين الشعارين)."""
        if not pathobj.is_file():
            return ""
        try:
            iw, ih = ImageReader(str(pathobj)).getSize()
            return RLImage(str(pathobj), width=h * iw / ih, height=h)
        except Exception:
            return ""

    # الشعاران بارتفاع موحّد: Nirvana (يسار) والمصطفى (يمين)
    al = _logo_cell(_LOGO_PATH, 62)
    nv = _logo_cell(_NIRVANA_PATH, 62)
    header = Table([[nv, al]], colWidths=[doc.width / 2, doc.width / 2])
    header.setStyle(TableStyle([
        ("ALIGN", (0, 0), (0, 0), "LEFT"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header)
    story.append(Spacer(1, 4))
    title_ar = str(data.get("title_ar") or "فاوتشر الفندق")
    title_en = str(data.get("title_en") or "")
    title_txt = ar(title_ar) + (("  /  " + title_en) if title_en else "")
    story.append(Paragraph(title_txt,
                           ParagraphStyle("vt", parent=st["title"], fontSize=16,
                                          spaceAfter=4)))
    lbl = ParagraphStyle("vlbl", parent=st["cell"], fontName=_FONT_BOLD,
                         textColor=_ACCENT, alignment=2, fontSize=9)
    val = ParagraphStyle("vval", parent=st["cell"], alignment=2, fontSize=9)
    val_l = ParagraphStyle("vvall", parent=val, alignment=0)     # يسار (إنجليزي)

    guest = data.get("guest_ar") or "—"
    guest_en = data.get("guest_en") or "—"
    cw = [doc.width * 0.28, doc.width * 0.22, doc.width * 0.28, doc.width * 0.22]
    meta = Table(
        [[_ar_para(number, val, cw[0] - 12),
          _ar_para("رقم الفاوتشر / Voucher No.", lbl, cw[1] - 12),
          _ar_para(ltr(date_str), val, cw[2] - 12),
          _ar_para("التاريخ / Date", lbl, cw[3] - 12)],
         # اسم الضيف: العربي يميناً والإنجليزي يساراً
         [_ar_para(guest_en, val_l, cw[0] - 12),
          _ar_para("Guest name", lbl, cw[1] - 12),
          _ar_para(guest, val, cw[2] - 12),
          _ar_para("اسم الضيف", lbl, cw[3] - 12)],
         [_ar_para(data.get("booking_no") or "—", val, cw[0] - 12),
          _ar_para("رقم الحجز", lbl, cw[1] - 12),
          _ar_para(data.get("program") or "—", val, cw[2] - 12),
          _ar_para("البرنامج", lbl, cw[3] - 12)]],
        colWidths=cw)
    meta.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BACKGROUND", (1, 0), (1, -1), _ALT_ROW),
        ("BACKGROUND", (3, 0), (3, -1), _ALT_ROW),
    ]))
    story.append(meta)
    story.append(Spacer(1, 8))

    # جدول الإقامات — القيَم من data["stays"] (قابلة للتعديل يدوياً)
    heads = list(VOUCHER_STAY_HEADS)
    weights = list(reversed([62, 108, 56, 52, 52, 52, 34, 46]))
    scale = doc.width / sum(weights)
    colw = [w * scale for w in weights]
    avail = [w - 9 for w in colw]
    rows = [_ar_cells(list(reversed(heads)), st["head"], avail)]
    for row in data.get("stays", []):
        vals = [str(x or "—") for x in list(row)[:8]]
        vals += ["—"] * (8 - len(vals))
        # الأرقام (الدخول/المغادرة/الليالي) تُلفّ بعلامات LTR
        vals = [vals[0], vals[1], vals[2], vals[3],
                ltr(vals[4]), ltr(vals[5]), ltr(vals[6]), vals[7]]
        rows.append(_ar_cells(list(reversed(vals)), st["cell"], avail))
    if len(rows) == 1:
        rows.append(_ar_cells([""] * len(heads), st["cell"], avail))
    stay_t = Table(rows, colWidths=colw)
    stay_t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _ACCENT),
        ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ALT_ROW]),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(stay_t)
    story.append(Spacer(1, 6))

    # خطة النقل والحالة (قابلة للتعديل من محرّر الفاوتشر)
    transport = str(data.get("transport") or "")
    info = ParagraphStyle("vinfo", parent=st["cell"], alignment=2, fontSize=9.5,
                          leading=15)
    if transport:
        story.append(Paragraph(ar(f"خطة النقل / Transportation: {transport}"),
                               info))
    status = str(data.get("status") or "")
    if status:
        story.append(Paragraph(ar(f"حالة الحجز: {status}"),
                               ParagraphStyle("vconf", parent=info,
                                              fontName=_FONT_BOLD,
                                              textColor=colors.HexColor("#2E6B45"))))

    # جهات التواصل (قابلة للإضافة/الحذف/التعديل)
    ccw = [doc.width * 0.30, doc.width * 0.42, doc.width * 0.28]

    def contact_row(role, name, phone):
        return [_ar_para(ltr(phone), val_l, ccw[0] - 10),
                _ar_para(name, val, ccw[1] - 10),
                _ar_para(role, lbl, ccw[2] - 10)]

    contact_data = [c for c in data.get("contacts", [])
                    if any(str(x or "").strip() for x in c)]
    if contact_data:
        story.append(Spacer(1, 6))
        contacts = Table([contact_row(str(c[0]), str(c[1]), str(c[2]))
                          for c in contact_data], colWidths=ccw)
        contacts.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("BACKGROUND", (2, 0), (2, -1), _ALT_ROW),
        ]))
        story.append(contacts)

    terms = [t for t in data.get("terms", []) if str(t or "").strip()]
    if terms:
        story.append(Spacer(1, 8))
        story.append(Paragraph(ar("الشروط والأحكام"), ParagraphStyle(
            "vth", parent=st["title"], fontSize=12, alignment=2,
            textColor=_ACCENT, spaceAfter=4)))
        term = ParagraphStyle("vterm", parent=st["cell"], alignment=2,
                              fontSize=8.5, leading=13, spaceAfter=2)
        for i, t in enumerate(terms, 1):
            story.append(Paragraph(ar(f"{i}- " + str(t)), term))

    doc.build(story,
              onFirstPage=lambda c, d: _footer_portrait(c, d, "فاوتشر الفندق"),
              onLaterPages=lambda c, d: _footer_portrait(c, d, "فاوتشر الفندق"))
    return path


# ======================================================================
#  الاستيكرات (للحقائب / للغرف / للأظرف)
# ======================================================================

STICKER_KINDS = ("bag", "room", "envelope")
STICKER_LABELS = {
    "bag": "استيكرات الحقائب",
    "room": "استيكرات الغرف",
    "envelope": "استيكرات الأظرف",
}
_STICKER_GRID = {"bag": (2, 4), "room": (2, 4), "envelope": (2, 5)}


def _sticker_items(records, kind: str, company: str) -> list[dict]:
    """يبني بطاقات الاستيكرات لكل نوع: حاج للحقائب/الأظرف، وغرفة للغرف."""
    items: list[dict] = []
    if kind == "room":
        groups, _unassigned = group_records_by_room(records)
        for hotel, _cap, number, recs in groups:
            names = [r.full_name_ar or r.full_name_en or "—" for r in recs]
            items.append({
                "header": company,
                "big": f"غرفة {number}",
                "big2": hotel or "",
                "lines": names,
                "footer": f"عدد النزلاء: {len(recs)}",
            })
    elif kind == "envelope":
        for rec in records:
            lines = []
            if rec.passport_number:
                lines.append(f"جواز: {rec.passport_number}")
            if rec.phone:
                lines.append(f"هاتف: {rec.phone}")
            if rec.hotel:
                lines.append(rec.hotel)
            items.append({
                "header": company,
                "big": rec.full_name_ar or rec.full_name_en or "—",
                "lines": lines,
                "footer": "المحتويات: الجواز • التذكرة • التصريح",
            })
    else:  # bag
        for rec in records:
            lines = []
            if rec.phone:
                lines.append(f"هاتف: {rec.phone}")
            loc = rec.hotel or ""
            if rec.room_number:
                loc += (f" - غرفة {rec.room_number}" if loc
                        else f"غرفة {rec.room_number}")
            if loc:
                lines.append(loc)
            trip = []
            if rec.flight_number:
                trip.append(f"رحلة {rec.flight_number}")
            if rec.transport:
                trip.append(f"باص {rec.transport}")
            if trip:
                lines.append(" • ".join(trip))
            items.append({
                "header": company,
                "big": rec.full_name_ar or rec.full_name_en or "—",
                "lines": lines,
                "footer": None,
            })
    return items


def export_stickers_pdf(records: list, path: str | Path, *, kind: str = "bag",
                        company: str = "المصطفى للحج والعمرة",
                        season: str = "", title: str | None = None) -> Path:
    """يبني **استيكرات** على ورق A4 عمودي في شبكة، لكلٍّ إطار وشريط علوي
    بالحملة: **للحقائب** و**للأظرف** استيكر لكل حاج، و**للغرف** استيكر لكل
    غرفة بأسماء نزلائها."""
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as _canvas

    _register_fonts()
    path = Path(path)
    if kind not in STICKER_KINDS:
        kind = "bag"
    items = _sticker_items(records, kind, company)
    title = title or STICKER_LABELS[kind]

    PW, PH = A4
    c = _canvas.Canvas(str(path), pagesize=A4, pageCompression=1)
    c.setTitle(title)
    logo_reader = ImageReader(str(_LOGO_PATH)) if _LOGO_PATH.is_file() else None
    gray = colors.HexColor("#555555")

    COLS, ROWS = _STICKER_GRID[kind]
    PER = COLS * ROWS
    MX, MY, GX, GY = 26, 30, 12, 12
    cw = (PW - 2 * MX - (COLS - 1) * GX) / COLS
    ch = (PH - 2 * MY - (ROWS - 1) * GY) / ROWS

    def cell_origin(idx):
        col, row = idx % COLS, idx // COLS
        ox = PW - MX - (col + 1) * cw - col * GX      # RTL: أوّل استيكر يميناً
        oy = PH - MY - (row + 1) * ch - row * GY
        return ox, oy

    def fit(text, font, base, maxw, floor=7.0):
        size = base
        while size > floor and pdfmetrics.stringWidth(ar(text), font, size) > maxw:
            size -= 0.5
        return size

    def draw_cell(ox, oy, item):
        c.setLineWidth(1.1); c.setStrokeColor(_ACCENT)
        c.rect(ox, oy, cw, ch, stroke=1, fill=0)
        # شريط علوي بالحملة + شعار صغير
        band_h = 22
        c.setFillColor(_ACCENT)
        c.rect(ox, oy + ch - band_h, cw, band_h, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont(_FONT_BOLD, fit(item["header"], _FONT_BOLD, 9.5, cw - 42, 6))
        c.drawCentredString(ox + cw / 2, oy + ch - band_h + 7, ar(item["header"]))
        if logo_reader is not None:
            iw, ih = logo_reader.getSize()
            lh = band_h - 6
            lw = lh * iw / ih
            c.drawImage(logo_reader, ox + 4, oy + ch - band_h + 3, lw, lh,
                        mask="auto", preserveAspectRatio=True)

        y = oy + ch - band_h - 8
        size = fit(item["big"], _FONT_BOLD, 15, cw - 16, 9)
        c.setFillColor(_INK); c.setFont(_FONT_BOLD, size)
        y -= size
        c.drawCentredString(ox + cw / 2, y, ar(item["big"]))
        if item.get("big2"):
            y -= 14
            c.setFillColor(gray)
            c.setFont(_FONT, fit(item["big2"], _FONT, 10.5, cw - 16))
            c.drawCentredString(ox + cw / 2, y, ar(item["big2"]))
        y -= 10

        floor_y = oy + (16 if item.get("footer") else 8)
        line_h = 13
        avail = max(0, int((y - floor_y) / line_h))
        shown = item["lines"][:avail]
        extra = len(item["lines"]) - len(shown)
        if extra > 0 and shown:          # اترك سطراً للإشارة إلى الباقي
            shown = shown[:-1]
            extra = len(item["lines"]) - len(shown)
        c.setFillColor(_INK)
        for ln in shown:
            y -= line_h
            c.setFont(_FONT, fit(ln, _FONT, 9.5, cw - 16))
            c.drawRightString(ox + cw - 8, y, ar(ln))
        if extra > 0:
            y -= line_h
            c.setFillColor(gray); c.setFont(_FONT, 8.5)
            c.drawRightString(ox + cw - 8, y, ar(f"+ {extra} آخرين"))

        if item.get("footer"):
            c.setFillColor(gray)
            c.setFont(_FONT, fit(item["footer"], _FONT, 8.2, cw - 12, 6))
            c.drawCentredString(ox + cw / 2, oy + 7, ar(item["footer"]))

    if not items:
        c.setFont(_FONT, 13); c.setFillColor(_INK)
        c.drawCentredString(PW / 2, PH / 2, ar("لا توجد بيانات للاستيكرات"))
        c.showPage(); c.save()
        return path

    for i, item in enumerate(items):
        if i > 0 and i % PER == 0:
            c.showPage()
        ox, oy = cell_origin(i % PER)
        draw_cell(ox, oy, item)
    c.showPage()
    c.save()
    return path


def export_transport_pdf(records: list, path: str | Path,
                         *, title: str = "كشف المواصلات") -> Path:
    """يصدّر كشف المواصلات إلى PDF **طولي**، **كل باص في صفحة واحدة** بخط كبير.

    حجم الخط يُضبط تلقائياً لكل باص ليتّسع ركّابه في صفحة واحدة فقط: خطّ
    كبير للباصات الصغيرة، ويصغر تدريجياً كلما زاد العدد — مع الالتزام
    بالصفحة الواحدة دائماً.
    """
    from .transport import executive_display, group_by_transport

    _register_fonts()
    path = Path(path)
    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        rightMargin=12 * mm, leftMargin=12 * mm,
        topMargin=12 * mm, bottomMargin=16 * mm,
        title=title, author="برنامج الحج",
    )

    groups, unassigned = group_by_transport(records)
    blocks = list(groups) + ([("بلا مواصلات", unassigned)] if unassigned else [])

    labels = ["م", "اسم الحاج", "رقم العائلة", "الهاتف", "الفندق",
              "خدمة التنفيذي", "كرسي متحرك"]
    draw_labels = list(reversed(labels))
    # الأعمدة تملأ عرض الصفحة كاملاً (المجموع = عرض المحتوى)
    weights = list(reversed([40, 178, 66, 88, 104, 92, 78]))
    scale = doc.width / sum(weights)
    col_widths = [w * scale for w in weights]

    title_style = ParagraphStyle("trt", fontName=_FONT_BOLD, fontSize=19,
                                 alignment=1, textColor=_INK, spaceAfter=4)
    sub_style = ParagraphStyle("trs", fontName=_FONT, fontSize=10.5, alignment=1,
                               textColor=colors.HexColor("#666666"), spaceAfter=8)
    # رأس العمود يسمح بسطرين (لعنوان طويل مثل «كرسي متحرك»)
    head_style = ParagraphStyle("trh", fontName=_FONT_BOLD, fontSize=11,
                                alignment=1, textColor=_HEADER_TEXT, leading=13)
    HPAD = 4
    HEAD_ROW_H = 30
    NAME_COL = len(labels) - 2          # موضع عمود الاسم في الترتيب المرسوم

    story: list = []
    for index, (name, occ) in enumerate(blocks):
        if index:
            story.append(PageBreak())

        logo = _logo_flowable(max_width_pt=100)
        title_p = Paragraph(ar(f"{title} — {name}"), title_style)
        sub_p = Paragraph(ar(
            f"عدد الركّاب: {ltr(len(occ))}  •  التاريخ: {ltr(date.today().isoformat())}"),
            sub_style)

        # نصوص الصفوف مُشكّلة كنصّ لا يلتفّ — كل حاج في سطر واحد
        body = []
        for serial, rec in enumerate(occ, start=1):
            values = [ltr(serial), rec.full_name_ar or rec.full_name_en or "—",
                      ltr(str(rec.family_number or "").strip() or "—"),
                      ltr(str(rec.phone or "").strip() or "—"),
                      str(rec.hotel or "").strip() or "—",
                      executive_display(rec) or "—",
                      str(rec.wheelchair or "").strip() or "—"]
            body.append([ar(v) for v in reversed(values)])

        # قياس ارتفاع الترويسة فعلياً
        header_h = (title_p.wrap(doc.width, doc.height)[1] + 4
                    + sub_p.wrap(doc.width, doc.height)[1] + 8)
        if logo is not None:
            header_h += logo.wrap(doc.width, doc.height)[1] + 4
        n_body = max(1, len(occ))
        body_avail = doc.height - header_h - HEAD_ROW_H - 12
        row_h = min(34, body_avail / n_body)

        # الخط: يفي بارتفاع السطر **وبعرض كل عمود** فلا يلتفّ نصّ أبداً
        font_v = row_h / 1.32
        font_h = 99.0
        for c in range(len(draw_labels)):
            widest = max((pdfmetrics.stringWidth(r[c], _FONT, 1.0) for r in body),
                         default=0.0)
            if widest > 0:
                font_h = min(font_h, (col_widths[c] - 2 * HPAD) / widest)
        font_size = max(5.0, min(15.0, font_v, font_h))
        row_h = min(34, body_avail / n_body)         # يملأ الارتفاع المتاح

        if logo is not None:
            story.append(logo)
            story.append(Spacer(1, 4))
        story.append(title_p)
        story.append(sub_p)

        data = [_ar_cells(draw_labels, head_style, col_widths, pad=HPAD)] + body
        row_heights = [HEAD_ROW_H] + [row_h] * n_body
        table = Table(data, colWidths=col_widths, rowHeights=row_heights, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _ACCENT),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, _GRID),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ALT_ROW]),
            ("FONTNAME", (0, 1), (-1, -1), _FONT),
            ("FONTSIZE", (0, 1), (-1, -1), font_size),
            ("LEFTPADDING", (0, 0), (-1, -1), HPAD),
            ("RIGHTPADDING", (0, 0), (-1, -1), HPAD),
            ("ALIGN", (0, 1), (-1, -1), "CENTER"),
            ("ALIGN", (NAME_COL, 1), (NAME_COL, -1), "RIGHT"),
            ("RIGHTPADDING", (NAME_COL, 1), (NAME_COL, -1), 8),
        ]))
        story.append(table)

    if not blocks:
        story.append(Paragraph(ar("لا حجّاج."), _styles()["subtitle"]))

    doc.build(story,
              onFirstPage=lambda c, d: _footer_portrait(c, d, title),
              onLaterPages=lambda c, d: _footer_portrait(c, d, title))
    return path


def _draw_person_icon(c, x0, y0, w, h, *, woman: bool) -> None:
    """يرسم رمز شخص داخل الإطار: امرأة محجّبة أو رجل (ظلّي)."""
    from reportlab.lib import colors as _c
    c.saveState()
    p = c.beginPath()                          # قصّ داخل الإطار
    p.rect(x0, y0, w, h)
    c.clipPath(p, stroke=0, fill=0)
    cx = x0 + w / 2
    fill = _c.HexColor("#9B8E79")
    face = _c.HexColor("#D9CEBC")
    c.setFillColor(fill)
    if woman:
        head_r = w * 0.30
        hy = y0 + h * 0.60
        # عباءة/جسم يتّسع للأسفل
        body = c.beginPath()
        body.moveTo(cx - head_r - w * 0.05, hy)
        body.lineTo(cx - w * 0.42, y0 + h * 0.04)
        body.lineTo(cx + w * 0.42, y0 + h * 0.04)
        body.lineTo(cx + head_r + w * 0.05, hy)
        body.close()
        c.drawPath(body, fill=1, stroke=0)
        # حجاب حول الرأس
        c.circle(cx, hy, head_r + w * 0.05, fill=1, stroke=0)
        # الوجه (بيضاوي فاتح)
        c.setFillColor(face)
        fr = head_r * 0.78
        c.ellipse(cx - fr * 0.82, hy - fr, cx + fr * 0.82, hy + fr, fill=1, stroke=0)
    else:
        head_r = w * 0.23
        hy = y0 + h * 0.66
        # الأكتاف (بيضاوي عريض منخفض)
        c.ellipse(cx - w * 0.45, y0 + h * 0.05, cx + w * 0.45, y0 + h * 0.05 + h * 0.40,
                  fill=1, stroke=0)
        # الرأس
        c.circle(cx, hy, head_r, fill=1, stroke=0)
    c.restoreState()


def export_badges_pdf(records: list, path: str | Path, *,
                      company: str = "المصطفى للحج والعمرة",
                      session=None, preacher: str = "", admins: str = "",
                      emergency: str = "", title: str = "بطاقات الحجّاج") -> Path:
    """يبني بطاقات الحجّاج بمقاس ثابت 5.2×8سم على ورق A4 **عرضي** — أكبر عدد
    ممكن لكل ورقة (10)، والخلفية في ورقة واحدة فيها الخلفيات نفسها متطابقة.

    الوجه: شعار الحملة + الصورة الشخصية (للرجال) أو رمز امرأة محجّبة (للنساء)
    + الاسم (الأول والثاني والأخير) + الهاتف + الفندق.
    الخلفية: شعار الحملة + رقم واعظ الحملة + الإداريون + رقم الطوارئ.
    """
    from reportlab.lib.units import cm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as _canvas

    from . import images as imgmod
    from .cards import badge_name, is_woman

    _register_fonts()
    path = Path(path)
    PW, PH = landscape(A4)
    c = _canvas.Canvas(str(path), pagesize=landscape(A4), pageCompression=1)
    c.setTitle(title)
    logo_reader = ImageReader(str(_LOGO_PATH)) if _LOGO_PATH.is_file() else None
    gray = colors.HexColor("#333333")

    # قياس البطاقة ثابت 5.2×8سم، وأكبر عدد يتّسع في صفحة A4 **عرضية** (5×2=10)
    bw, bh = 5.2 * cm, 8.0 * cm
    s = 1.0
    MX, MY, GX, GY = 20, 18, 6, 8
    COLS = max(1, int((PW - 2 * MX + GX) / (bw + GX)))
    ROWS = max(1, int((PH - 2 * MY + GY) / (bh + GY)))
    PER = COLS * ROWS
    grid_w = COLS * bw + (COLS - 1) * GX
    grid_h = ROWS * bh + (ROWS - 1) * GY
    off_x = (PW - grid_w) / 2
    off_top = (PH + grid_h) / 2

    def cell_origin(idx):
        col, row = idx % COLS, idx // COLS
        ox = off_x + grid_w - (col + 1) * bw - col * GX   # RTL: أول بطاقة يميناً
        oy = off_top - (row + 1) * bh - row * GY
        return ox, oy

    # الرسم داخل بطاقة بإحداثيات محلّية (0,0)..(bw,bh) بعد الإزاحة
    def center(text, y, font, size, color=_INK):
        c.setFillColor(color)
        c.setFont(font, size)
        c.drawCentredString(bw / 2, y, ar(str(text)))

    def right(text, y, font, size, color=_INK):
        c.setFillColor(color)
        c.setFont(font, size)
        c.drawRightString(bw - 6 * s, y, ar(str(text)))

    def draw_logo(top_y, max_w, max_h):
        if logo_reader is None:
            return top_y - 2
        iw, ih = logo_reader.getSize()
        w = min(max_w, iw)
        h = w * ih / iw
        if h > max_h:
            h = max_h
            w = h * iw / ih
        c.drawImage(logo_reader, bw / 2 - w / 2, top_y - h, w, h,
                    mask="auto", preserveAspectRatio=True)
        return top_y - h

    def photo_reader(rec):
        """صورة شخصية للرجل إن وُجدت، وإلا None (يُرسم الرمز)."""
        if is_woman(rec) or not getattr(rec, "image_id", ""):
            return None
        blob = imgmod.load_image(rec.image_id, imgmod.PHOTO, session)
        if not blob:
            return None
        pil = imgmod.to_pil_image(blob)
        return ImageReader(pil) if pil is not None else None

    def draw_front(rec):
        c.setStrokeColor(_ACCENT)
        c.setLineWidth(1)
        c.rect(2, 2, bw - 4, bh - 4, fill=0, stroke=1)
        y = draw_logo(bh - 6 * s, bw * 0.6, 28 * s)
        if company:
            y -= 11 * s
            center(company, y, _FONT_BOLD, 8 * s, _ACCENT)
        box_w, box_h = bw * 0.56, bh * 0.40
        boxx, boxy = (bw - box_w) / 2, y - 7 * s - box_h
        c.setStrokeColor(_GRID)
        c.setLineWidth(0.8)
        c.rect(boxx, boxy, box_w, box_h, fill=0, stroke=1)
        pr = photo_reader(rec)
        if pr is not None:
            c.drawImage(pr, boxx + 1, boxy + 1, box_w - 2, box_h - 2,
                        preserveAspectRatio=True, anchor="c", mask="auto")
        else:
            _draw_person_icon(c, boxx + 1, boxy + 1, box_w - 2, box_h - 2,
                              woman=is_woman(rec))
        ty = boxy - 15 * s
        center(badge_name(rec) or "—", ty, _FONT_BOLD, 11 * s, _INK)
        phone = str(rec.phone or "").strip()
        if phone:
            ty -= 14 * s
            center(phone, ty, _FONT, 10 * s, gray)
        hotel = str(rec.hotel or "").strip()
        if hotel:
            ty -= 13 * s
            center(hotel, ty, _FONT, 9 * s, gray)

    def draw_back():
        c.setStrokeColor(_ACCENT)
        c.setLineWidth(1)
        c.rect(2, 2, bw - 4, bh - 4, fill=0, stroke=1)
        y = draw_logo(bh - 6 * s, bw * 0.62, 30 * s)
        if company:
            y -= 12 * s
            center(company, y, _FONT_BOLD, 9 * s, _ACCENT)
        y -= 18 * s
        right("واعظ الحملة:", y, _FONT_BOLD, 9 * s, _ACCENT)
        y -= 12 * s
        right(preacher or "................", y, _FONT, 9 * s)
        y -= 17 * s
        right("الإداريون:", y, _FONT_BOLD, 9 * s, _ACCENT)
        y -= 12 * s
        admin_lines = [ln for ln in str(admins or "").splitlines() if ln.strip()]
        if not admin_lines:
            admin_lines = ["................", "................"]
        for ln in admin_lines[:3]:
            right(ln, y, _FONT, 9 * s)
            y -= 12 * s
        yb = 20 * s
        c.setStrokeColor(_GRID)
        c.setLineWidth(0.6)
        c.line(6 * s, yb + 11 * s, bw - 6 * s, yb + 11 * s)
        right(f"للطوارئ: {emergency or '................'}", yb, _FONT_BOLD, 9.5 * s,
              colors.HexColor("#B23A3A"))

    def in_cell(idx, draw_fn):
        ox, oy = cell_origin(idx)
        c.saveState()
        c.translate(ox, oy)
        draw_fn()
        c.restoreState()

    if not records:
        c.setFont(_FONT, 14)
        c.setFillColor(_INK)
        c.drawCentredString(PW / 2, PH / 2, ar("لا حجّاج"))
        c.showPage()
        c.save()
        return path

    # صفحات الوجوه: 8 لكل ورقة A4
    for i, rec in enumerate(records):
        if i and i % PER == 0:
            c.showPage()
        in_cell(i % PER, lambda r=rec: draw_front(r))
    c.showPage()

    # ورقة خلفية واحدة: 8 خلفيات متطابقة (عامّة لا تخصّ فرداً)
    for idx in range(PER):
        in_cell(idx, draw_back)
    c.showPage()

    c.save()
    return path


def export_passports_pdf(
    entries: list[tuple[str, str]], path: str | Path, *, title: str = "جوازات الحجاج"
) -> Path:
    """يبني PDF لصور الجوازات — صفحة لكل جواز بعنوان اسم الحاج.

    entries: قائمة (اسم الحاج، مسار صورة الجواز). الصور تُقاس لتملأ الصفحة
    دون تشويه. يُستعمل لطباعة كل الجوازات بأمر واحد.
    """
    _register_fonts()
    path = Path(path)
    st = _styles()

    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        rightMargin=12 * mm, leftMargin=12 * mm,
        topMargin=14 * mm, bottomMargin=16 * mm,
        title=title, author="برنامج الحج",
    )

    story: list = []
    for index, (caption, image_path) in enumerate(entries):
        if index:
            story.append(PageBreak())
        story.append(Paragraph(ar(caption or "—"), st["title"]))
        story.append(Spacer(1, 6))
        try:
            iw, ih = ImageReader(image_path).getSize()
            width = doc.width
            height = width * ih / iw
            max_height = doc.height - 60      # نترك مكاناً للعنوان
            if height > max_height:
                height = max_height
                width = height * iw / ih
            picture = RLImage(image_path, width=width, height=height)
            picture.hAlign = "CENTER"
            story.append(picture)
        except Exception:
            story.append(Paragraph(ar("تعذّر عرض صورة الجواز"), st["subtitle"]))

    doc.build(
        story,
        onFirstPage=lambda c, d: _footer(c, d, title),
        onLaterPages=lambda c, d: _footer(c, d, title),
    )
    return path

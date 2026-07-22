"""تصدير كشف الحجاج إلى ملف PDF بدعم كامل للعربية.

العربية تحتاج خطوتين قبل الرسم في ReportLab:
  1. تشكيل الحروف (وصلها ببعضها حسب موضعها) عبر arabic_reshaper
  2. ترتيب ثنائي الاتجاه (RTL) عبر python-bidi
بدونهما تظهر الحروف منفصلة ومقلوبة.
"""

from __future__ import annotations

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


_LOGO_PATH = Path(__file__).resolve().parent / "assets" / "logo.png"


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
    cells = [Paragraph(ar(ROOM_CATEGORIES[cap - 1]), style) for cap in present]
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
    table_data = [[Paragraph(ar(f.label), st["head"]) for f in cols]]
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
        table_data.append([Paragraph(ar(data.get(f.key, "")), st["cell"]) for f in cols])

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
            row[0] = Paragraph(ar(label), room_head)
            room_rows.append((len(table_data), capacity))
            table_data.append(row)
            for rec in occupants:
                serial += 1
                _add_occupant(rec, serial)
    else:
        for idx, rec in enumerate(records, start=1):
            _add_occupant(rec, idx)

    weights = [_PDF_WIDTHS.get(f.key, f.width * 4) for f in cols]
    scale = doc.width / sum(weights)
    col_widths = [w * scale for w in weights]

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

    # نبني كل مجموعة ككتلة صفوف مستقلة، ثم نوزّعها على عمودين
    blocks: list[list] = []
    for group_title, keys in _CARD_GROUPS:
        present = [k for k in keys if data.get(k)]
        if not present:
            continue
        block = [(True, [Paragraph(ar(group_title), group_style), ""])]
        for k in present:
            # القيمة يساراً والعنوان يميناً (تخطيط RTL)
            block.append((False, [
                Paragraph(ar(data[k]), st["cell"]),
                Paragraph(ar(labels.get(k, k)), label_style),
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
    table_data = [[Paragraph(ar(lbl), st["head"]) for lbl in draw_labels]]
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
        row[0] = Paragraph(ar(tent_label(tent)), tent_head)
        class_rows.append((len(table_data), tent.classification))
        table_data.append(row)
        for occ in tent.occupants:
            serial += 1
            values = [
                ltr(serial), occ.name, ltr(occ.family),
                str(occ.record.hotel or "").strip(), ltr(_room_of(occ.record)),
                occ.sex, ltr(str(occ.record.phone or "").strip()),
            ]
            table_data.append([Paragraph(ar(v), st["cell"]) for v in reversed(values)])

    weights = list(reversed([22, 122, 46, 74, 44, 40, 68]))
    scale = doc.width / sum(weights)
    col_widths = [w * scale for w in weights]

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

        table_data = [[Paragraph(ar(lbl), st["head"]) for lbl in draw_labels]]
        for position, occ in enumerate(tent.occupants, start=1):
            values = [ltr(position), occ.name, tent.sector,
                      tent.classification, campaign]
            table_data.append([Paragraph(ar(v), st["cell"]) for v in reversed(values)])

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


def export_receipt_pdf(rec, path: str | Path, *,
                       company: str = "المصطفى للحج والعمرة",
                       season: str = "") -> Path:
    """يبني إيصال دفع لحاج واحد (صفحة A4 عمودية) بشعار الحملة."""
    from .fields import compute_remaining, format_amount, parse_amount

    _register_fonts()
    path = Path(path)
    st = _styles()

    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        rightMargin=16 * mm, leftMargin=16 * mm,
        topMargin=16 * mm, bottomMargin=18 * mm,
        title="إيصال دفع", author="برنامج الحج",
    )
    name = rec.full_name_ar or rec.full_name_en or "—"
    total = parse_amount(rec.program_value)
    paid = parse_amount(rec.paid_amount)
    remaining = compute_remaining(rec)

    story: list = []
    logo = _logo_flowable(max_width_pt=150)
    if logo is not None:
        story.append(logo)
        story.append(Spacer(1, 4))
    story.append(Paragraph(ar("إيصال دفع"), st["title"]))
    sub = company + (f"  •  موسم {ltr(season)}هـ" if season else "")
    sub += f"  •  {ltr(date.today().isoformat())}"
    story.append(Paragraph(ar(sub), st["subtitle"]))

    lbl = ParagraphStyle("rlbl", parent=st["cell"], fontName=_FONT_BOLD,
                         textColor=_ACCENT, alignment=2, fontSize=9.5)
    val = ParagraphStyle("rval", parent=st["cell"], alignment=2, fontSize=9.5)
    head = ParagraphStyle("rhead", parent=st["cell"], fontName=_FONT_BOLD,
                          textColor=colors.white, alignment=2, fontSize=9.5)

    def section(title_text, rows, big_last=False):
        data = [[Paragraph(ar(title_text), head), ""]]
        for i, (k, v) in enumerate(rows):
            vstyle = val
            if big_last and i == len(rows) - 1:
                vstyle = ParagraphStyle("rbig", parent=val, fontName=_FONT_BOLD,
                                        textColor=_ACCENT, fontSize=11)
            data.append([Paragraph(ar(str(v) or "—"), vstyle),
                         Paragraph(ar(k), lbl)])
        t = Table(data, colWidths=[doc.width * 0.6, doc.width * 0.4])
        style = [
            ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("SPAN", (0, 0), (1, 0)),
            ("BACKGROUND", (0, 0), (1, 0), _ACCENT),
        ]
        for r in range(1, len(data)):
            style.append(("BACKGROUND", (1, r), (1, r), _ALT_ROW))
        t.setStyle(TableStyle(style))
        return t

    story.append(section("بيانات الحاج", [
        ("الاسم", name),
        ("رقم الجواز", rec.passport_number),
        ("الجنسية", rec.nationality_ar),
        ("الهاتف", rec.phone),
        ("الفندق", rec.hotel),
        ("رقم العائلة", rec.family_number),
    ]))
    story.append(Spacer(1, 10))
    story.append(section("التفاصيل المالية", [
        ("قيمة البرنامج", format_amount(total) if total is not None else rec.program_value),
        ("المبلغ المدفوع", format_amount(paid) if paid is not None else rec.paid_amount),
        ("المبلغ المتبقّي", remaining or "—"),
    ], big_last=True))

    story.append(Spacer(1, 26))
    sign = ParagraphStyle("sign", parent=st["cell"], alignment=1, fontSize=10)
    sign_row = Table([[Paragraph(ar("توقيع المستلم"), sign),
                       Paragraph(ar("توقيع المحاسب"), sign)]],
                     colWidths=[doc.width / 2, doc.width / 2])
    sign_row.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (0, 0), 0.6, _GRID),
        ("LINEABOVE", (1, 0), (1, 0), 0.6, _GRID),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(sign_row)

    doc.build(
        story,
        onFirstPage=lambda c, d: _footer_portrait(c, d, "إيصال دفع"),
        onLaterPages=lambda c, d: _footer_portrait(c, d, "إيصال دفع"),
    )
    return path


def export_transport_pdf(records: list, path: str | Path,
                         *, title: str = "كشف المواصلات") -> Path:
    """يصدّر كشف المواصلات إلى PDF، مجموعاً بوسيلة النقل (رأس ملوّن لكل مجموعة)."""
    from .cards import room_of
    from .transport import group_by_transport

    _register_fonts()
    path = Path(path)
    st = _styles()
    doc = SimpleDocTemplate(
        str(path), pagesize=landscape(A4),
        rightMargin=10 * mm, leftMargin=10 * mm,
        topMargin=12 * mm, bottomMargin=16 * mm,
        title=title, author="برنامج الحج",
    )
    story: list = []
    logo = _logo_flowable()
    if logo is not None:
        story.append(logo)
        story.append(Spacer(1, 5))
    story.append(Paragraph(ar(title), st["title"]))
    story.append(Paragraph(ar(
        f"عدد الحجّاج: {ltr(len(records))}  •  التاريخ: {ltr(date.today().isoformat())}"),
        st["subtitle"]))

    labels = ["م", "اسم الحاج", "الهاتف", "الفندق", "الغرفة"]
    draw_labels = list(reversed(labels))
    table_data = [[Paragraph(ar(lbl), st["head"]) for lbl in draw_labels]]
    group_rows: list[int] = []
    group_head = ParagraphStyle("tr_group", parent=st["cell"], fontName=_FONT_BOLD,
                                textColor=colors.white, alignment=2, fontSize=8.5, leading=11)

    groups, unassigned = group_by_transport(records)
    blocks = list(groups) + ([("بلا مواصلات", unassigned)] if unassigned else [])
    serial = 0
    for name, occ in blocks:
        row = ["" for _ in labels]
        row[0] = Paragraph(ar(f"{name}  ({ltr(len(occ))})"), group_head)
        group_rows.append(len(table_data))
        table_data.append(row)
        for rec in occ:
            serial += 1
            values = [ltr(serial), rec.full_name_ar or rec.full_name_en or "—",
                      ltr(str(rec.phone or "").strip()),
                      str(rec.hotel or "").strip(), ltr(room_of(rec))]
            table_data.append([Paragraph(ar(v), st["cell"]) for v in reversed(values)])

    weights = list(reversed([24, 170, 90, 100, 48]))
    scale = doc.width / sum(weights)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), _ACCENT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for r in group_rows:
        style.append(("SPAN", (0, r), (-1, r)))
        style.append(("BACKGROUND", (0, r), (-1, r), _ROOM_HEAD))
    table = Table(table_data, colWidths=[w * scale for w in weights], repeatRows=1)
    table.setStyle(TableStyle(style))
    story.append(table)
    doc.build(story, onFirstPage=lambda c, d: _footer(c, d, title),
              onLaterPages=lambda c, d: _footer(c, d, title))
    return path


def export_badges_pdf(records: list, path: str | Path, *,
                      company: str = "المصطفى للحج والعمرة",
                      title: str = "بطاقات الحجّاج") -> Path:
    """يبني بطاقات هوية للحجّاج (10 لكل صفحة) بها رمز QR وبيانات الحاج."""
    from reportlab.graphics.barcode import qr
    from reportlab.graphics.shapes import Drawing

    from .cards import qr_payload

    _register_fonts()
    path = Path(path)
    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        rightMargin=12 * mm, leftMargin=12 * mm,
        topMargin=12 * mm, bottomMargin=14 * mm,
        title=title, author="برنامج الحج",
    )
    name_style = ParagraphStyle("bname", fontName=_FONT_BOLD, fontSize=11,
                                alignment=2, textColor=_INK, leading=14)
    small = ParagraphStyle("bsmall", fontName=_FONT, fontSize=8, alignment=2,
                           leading=11, textColor=colors.HexColor("#333333"))
    comp = ParagraphStyle("bcomp", fontName=_FONT, fontSize=7.5, alignment=2,
                          textColor=_ACCENT)

    per_row, rows_per_page = 2, 4          # 8 بطاقات/صفحة — ترقيم نظيف بلا انقسام
    per_page = per_row * rows_per_page
    card_w = (doc.width - 10) / per_row
    card_h = (doc.height - 34) / rows_per_page

    def qr_draw(text: str, size: float = 74):
        widget = qr.QrCodeWidget(text)
        b = widget.getBounds()
        bw, bh = b[2] - b[0], b[3] - b[1]
        d = Drawing(size, size, transform=[size / bw, 0, 0, size / bh, 0, 0])
        d.add(widget)
        return d

    def make_card(rec):
        payload = qr_payload(rec)
        name = rec.full_name_ar or rec.full_name_en or "—"
        details = payload.split("\n")[1:]
        cell = [Paragraph(ar(name), name_style)]
        cell += [Paragraph(ar(d), small) for d in details]
        if company:
            cell.append(Spacer(1, 3))
            cell.append(Paragraph(ar(company), comp))
        card = Table([[qr_draw(payload), cell]],
                     colWidths=[80, card_w - 86], rowHeights=[card_h - 8])
        card.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.9, _ACCENT),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return card

    cards = [make_card(r) for r in records]
    story: list = []
    for start in range(0, len(cards), per_page):
        if start:
            story.append(PageBreak())
        page = cards[start:start + per_page]
        grid_rows = []
        for i in range(0, len(page), per_row):
            pair = page[i:i + per_row]
            while len(pair) < per_row:
                pair.append("")
            grid_rows.append(list(reversed(pair)))    # RTL: أول بطاقة يميناً
        grid = Table(grid_rows, colWidths=[card_w] * per_row,
                     rowHeights=[card_h] * len(grid_rows))
        grid.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(grid)

    if not cards:
        story.append(Paragraph(ar("لا حجّاج."), _styles()["subtitle"]))
    doc.build(story)
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

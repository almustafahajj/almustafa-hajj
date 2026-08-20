"""تصدير كشف الحجاج إلى ملف PDF بدعم كامل للعربية.

العربية تحتاج خطوتين قبل الرسم في ReportLab:
  1. تشكيل الحروف (وصلها ببعضها حسب موضعها) عبر arabic_reshaper
  2. ترتيب ثنائي الاتجاه (RTL) عبر python-bidi
بدونهما تظهر الحروف منفصلة ومقلوبة.
"""

from __future__ import annotations

import io
import re
from datetime import date
from pathlib import Path

_re_iso = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def _dmy(s) -> str:
    """يحوّل ISO (YYYY-MM-DD) إلى DD/MM/YYYY، وإلا يعيد النص كما هو."""
    m = _re_iso.match(str(s or "").strip())
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else str(s or "")

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
    Image as RLImage, KeepInFrame, PageBreak, Paragraph, SimpleDocTemplate,
    Spacer, Table, TableStyle,
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
    """يسجّل أول خط عربي متاح. يتراجع إلى Helvetica إن لم يوجد أي خط.

    ملاحظة: نعتمد خطوط النظام (Amiri/Tahoma/Arial) عمداً لأنها تحوي أشكال
    العرض العربية (Presentation Forms-B) التي يخرجها ``arabic_reshaper``؛
    الخطوط الحديثة كـ Tajawal تعتمد تشكيل OpenType (GSUB) الذي لا يطبّقه
    reportlab، فتظهر بعض الحروف مبعثرة أو ناقصة. لذا لا نستعملها للطباعة."""
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


def _qr_drawing(data: str, size: float):
    """يبني رمز QR كعنصر رسمٍ (Drawing) قابل للإدراج في المستندات — للتحقّق.

    يعيد ``None`` إن تعذّر (فلا يكسر بناء المستند)."""
    try:
        from reportlab.graphics.barcode import qr
        from reportlab.graphics.shapes import Drawing
        widget = qr.QrCodeWidget(str(data or "-"))
        b = widget.getBounds()
        bw, bh = (b[2] - b[0]) or 1, (b[3] - b[1]) or 1
        d = Drawing(size, size, transform=[size / bw, 0, 0, size / bh, 0, 0])
        d.add(widget)
        return d
    except Exception:                                  # noqa: BLE001
        return None


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


def _umrah_page(canvas, doc, title_text: str) -> None:
    """خلفية مائية خفيفة بشعار الشركة + الترويسة السفلية — لمستندات العمرة.

    الشعار الباهت يُرسَم خلف المحتوى (يظهر بلطف في الفراغات والهوامش) فيمنح
    المستند طابعاً رسمياً أنيقاً دون التشويش على القراءة."""
    wm = _faint_logo_reader()
    if wm is not None:
        try:
            W, H = A4
            iw, ih = wm.getSize()
            ww = W * 0.52
            hh = ww * ih / iw
            canvas.saveState()
            canvas.drawImage(wm, (W - ww) / 2, (H - hh) / 2, ww, hh,
                             preserveAspectRatio=True, mask="auto")
            canvas.restoreState()
        except Exception:                              # noqa: BLE001
            pass
    _footer_portrait(canvas, doc, title_text)


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
        story.append(Spacer(1, 4))
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
        story.append(Spacer(1, 4))
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
              onFirstPage=lambda c, d: _umrah_page(c, d, "الملخّص المالي"),
              onLaterPages=lambda c, d: _umrah_page(c, d, "الملخّص المالي"))
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


def export_season_report_pdf(trips: list, records: list, path, *,
                             season: str = "", company=None,
                             group_attr: str = "trip",
                             kind: str = "العمرة") -> Path:
    """تقرير موسم فاخر بصيغة PDF بتصميم لوحة الموسم — للطباعة والأرشفة.

    ``group_attr``/``kind``: «trip»/«العمرة» أو «program»/«الحج»."""
    from reportlab.pdfgen import canvas as _canvas
    from . import dashboard_html as _dash
    from .fields import format_amount

    rows, totals = _dash.season_dashboard_stats(trips, records, group_attr)
    n_gen = "الحجّاج" if kind == "الحج" else "المعتمرين"
    n_nom = "الحجّاج" if kind == "الحج" else "المعتمرون"
    # الإشغال يُعرض فقط حين تتوفّر سعة؛ وإلّا نعرض العدد/البرامج
    has_cap = (totals.get("capacity", 0) or 0) > 0
    name_ar, name_en = _dash._company_names(company)
    _register_fonts()

    KISWAH = colors.HexColor("#141009")
    GOLD = colors.HexColor("#C8A44A")
    GOLD_DK = colors.HexColor("#B8912E")
    BRONZE = colors.HexColor("#8A6E4B")
    BRONZE_DK = colors.HexColor("#6F5738")
    INK = colors.HexColor("#211A11")
    MUTED = colors.HexColor("#6E6355")
    LINE = colors.HexColor("#E7DCCA")
    SURF2 = colors.HexColor("#F4EEE3")
    SUCCESS = colors.HexColor("#2E7D5B")
    DANGER = colors.HexColor("#BC4A43")
    ON_DK = colors.HexColor("#F2E9D6")
    ON_DK_MUTED = colors.HexColor("#B9A985")

    W, H = A4
    ML = 40
    c = _canvas.Canvas(str(path), pagesize=A4)
    c.setTitle(f"تقرير موسم {season} — {name_ar}")

    def _bar(x, y, w, h, frac, color, track=SURF2):
        c.setFillColor(track)
        c.roundRect(x, y, w, h, h / 2, stroke=0, fill=1)
        fw = max(0.0, min(frac, 1.0)) * w
        if fw > 1:
            c.setFillColor(color)
            c.roundRect(x + w - fw, y, fw, h, h / 2, stroke=0, fill=1)  # RTL

    def _status_color(cls):
        return {"ok": SUCCESS, "mid": BRONZE, "low": DANGER}.get(cls, BRONZE)

    def _header_band():
        bh = 208
        c.setFillColor(KISWAH)
        c.rect(0, H - bh, W, bh, stroke=0, fill=1)
        c.setStrokeColor(GOLD)
        c.setLineWidth(0.6)
        c.line(0, H - bh, W, H - bh)
        # خاتم هندسي (مربعان متقاطعان) على اليسار
        c.saveState()
        c.setStrokeColor(GOLD)
        c.setLineWidth(0.7)
        cx, cy, s = 92, H - 96, 52
        c.rect(cx - s / 2, cy - s / 2, s, s, stroke=1, fill=0)
        c.translate(cx, cy)
        c.rotate(45)
        c.rect(-s / 2, -s / 2, s, s, stroke=1, fill=0)
        c.restoreState()
        # اسم الشركة والعنوان (يمين)
        c.setFillColor(ON_DK)
        c.setFont(_FONT_BOLD, 14)
        c.drawRightString(W - ML, H - 44, ar(name_ar))
        c.setFillColor(ON_DK_MUTED)
        c.setFont(_FONT, 8)
        c.drawRightString(W - ML, H - 58, name_en)
        c.setFillColor(colors.HexColor("#F7EFDD"))
        c.setFont(_FONT_BOLD, 24)
        c.drawRightString(W - ML, H - 92, ar(f"لوحة موسم {kind} {season}"))
        c.setFillColor(ON_DK_MUTED)
        c.setFont(_FONT, 10)
        c.drawRightString(W - ML, H - 110,
                          ar("نظرة شاملة على البرامج والإشغال والتحصيل"))
        # مؤشّرات الأداء (٤ خلايا) — الإشغال أو عدد البرامج حسب توفّر السعة
        occ_k = ("نسبة الإشغال", f"{totals['occ_pct']:.0f}%") if has_cap \
            else ("عدد البرامج", f"{totals['programs']}")
        kpis = [(f"إجمالي {n_gen}", f"{totals['pilgrims']}"), occ_k,
                ("إجمالي الإيراد", f"{_dash._compact(totals['total'])} AED"),
                ("نسبة التحصيل", f"{totals['col_pct']:.0f}%")]
        kx, kw = ML, (W - 2 * ML) / 4
        ky = H - 188
        c.setStrokeColor(colors.HexColor("#3A3020"))
        for i, (lbl, val) in enumerate(kpis):
            x = kx + i * kw
            if i:
                c.line(x, ky, x, ky + 46)
            c.setFillColor(ON_DK_MUTED)
            c.setFont(_FONT, 8.5)
            c.drawCentredString(x + kw / 2, ky + 34, ar(lbl))
            c.setFillColor(GOLD)
            c.setFont(_FONT_BOLD, 20)
            c.drawCentredString(x + kw / 2, ky + 12, val)
        return H - bh

    def _watermark():
        reader = _faint_logo_reader()
        if reader is None:
            return
        ww = W * 0.5
        try:
            c.drawImage(reader, (W - ww) / 2, 240, width=ww,
                        preserveAspectRatio=True, mask="auto")
        except Exception:
            pass

    def _footer():
        c.setStrokeColor(LINE)
        c.setLineWidth(0.5)
        c.line(ML, 44, W - ML, 44)
        c.setFillColor(MUTED)
        c.setFont(_FONT, 8)
        c.drawRightString(W - ML, 32, ar(f"{name_ar} · تقرير الموسم"))
        c.drawString(ML, 32, date.today().strftime("%Y-%m-%d"))
        c.drawCentredString(W / 2, 32, ar(f"صفحة {c.getPageNumber()}"))

    _watermark()                          # خلف المحتوى
    y = _header_band() - 26

    # ---- الملخّص المالي ----
    def _fin_cell(x, w, label, value, vcolor):
        c.setFillColor(colors.white)
        c.setStrokeColor(LINE)
        c.roundRect(x, y - 54, w, 54, 8, stroke=1, fill=1)
        c.setFillColor(MUTED)
        c.setFont(_FONT, 8.5)
        c.drawRightString(x + w - 12, y - 20, ar(label))
        c.setFillColor(vcolor)
        c.setFont(_FONT_BOLD, 16)
        c.drawRightString(x + w - 12, y - 42, value)

    cw3 = (W - 2 * ML - 2 * 10) / 3
    _fin_cell(ML, cw3, "الإيراد المتوقّع", f"{format_amount(totals['total'])} AED", INK)
    _fin_cell(ML + cw3 + 10, cw3, "المحصّل", format_amount(totals['paid']), SUCCESS)
    _fin_cell(ML + 2 * (cw3 + 10), cw3, "المتبقّي",
              format_amount(totals['remaining']), DANGER)
    y -= 54 + 12
    # شريط تقدّم التحصيل
    c.setFillColor(INK)
    c.setFont(_FONT_BOLD, 11)
    c.drawRightString(W - ML, y - 12, f"{totals['col_pct']:.0f}%")
    _bar(ML, y - 16, W - 2 * ML - 46, 11, totals['col_pct'] / 100,
         GOLD_DK)
    y -= 34

    # ---- عنوان القسم ----
    def _section(title, yy):
        c.setFillColor(BRONZE)
        c.setFont(_FONT_BOLD, 13)
        c.drawRightString(W - ML, yy, ar(title))
        c.setStrokeColor(LINE)
        c.setLineWidth(0.7)
        c.line(ML, yy - 6, W - ML - 120, yy - 6)
        return yy - 24

    y = _section("برامج الموسم", y)

    # ---- بطاقات البرامج ----
    CARD_H = 76
    for r in rows:
        if y - CARD_H < 70:               # صفحة جديدة عند الحاجة
            _footer()
            c.showPage()
            _watermark()
            y = H - 60
            y = _section("برامج الموسم (تابع)", y)
        x0, x1 = ML, W - ML
        c.setFillColor(SURF2)
        c.setStrokeColor(LINE)
        c.roundRect(x0, y - CARD_H, x1 - x0, CARD_H, 9, stroke=1, fill=1)
        # الاسم يميناً
        c.setFillColor(INK)
        c.setFont(_FONT_BOLD, 12)
        c.drawRightString(x1 - 12, y - 20, ar(r["name"]))
        # شارة الحالة يساراً
        sc = _status_color(r["status_cls"])
        c.setFillColor(sc)
        c.setFont(_FONT_BOLD, 8.5)
        pill_w = c.stringWidth(ar(r["status"]), _FONT_BOLD, 8.5) + 16
        c.roundRect(x0 + 12, y - 24, pill_w, 15, 7, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.drawCentredString(x0 + 12 + pill_w / 2, y - 20, ar(r["status"]))
        # خانتا المعلومات (فنادق مكة/المدينة أو مطار المغادرة/الناقل)
        c.setFillColor(MUTED)
        c.setFont(_FONT, 8.5)
        c.drawRightString(x1 - 12, y - 35, ar(
            f"{r['info1_label']}: {r['info1']}  ·  {r['info2_label']}: {r['info2']}"))
        # التواريخ (المغادرة – العودة) إن وُجدت
        _dr = " – ".join(x for x in (str(r.get("depart") or ""),
                                     str(r.get("return") or "")) if x)
        if _dr:
            c.drawString(x0 + 12, y - 35, _dr)
        # شريطان: الإشغال والتحصيل
        blx = x0 + 12
        blw = (x1 - x0) - 24 - 150
        c.setFillColor(INK)
        c.setFont(_FONT, 8.5)
        if has_cap:
            c.drawRightString(x1 - 12, y - 51,
                              ar(f"الإشغال  {r['count']}/{r['capacity'] or '—'}"))
            _bar(blx, y - 53, blw, 6, (r["occ_pct"] or 0) / 100, BRONZE_DK)
        else:
            c.drawRightString(x1 - 12, y - 51, ar(f"{n_nom}: {r['count']}"))
        c.drawRightString(x1 - 12, y - 63,
                          ar(f"التحصيل  {r['col_pct']:.0f}٪"))
        _bar(blx, y - 65, blw, 6, r["col_pct"] / 100, GOLD_DK)
        y -= CARD_H + 10

    if not rows:
        c.setFillColor(MUTED)
        c.setFont(_FONT, 11)
        c.drawCentredString(W / 2, y - 30, ar("لا توجد برامج في هذا الموسم بعد."))

    _footer()
    c.showPage()
    c.save()
    return Path(path)


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
    # رمز تحقّق QR في يسار الفراغ الأوسط (طابع توثيق) — لا يزاحم أي محتوى
    try:
        from reportlab.graphics import renderPDF
        qd = _qr_drawing(f"{company} | سند {number} | {name} | "
                         f"AED {amount:,.2f} | {date_str}", 62)
        if qd is not None and h_gap > 70:
            qx = x0 + 26
            qy = (y + yb_gap) / 2 - 31
            renderPDF.draw(qd, c, qx, qy)
            c.setFont(AF, 8)
            c.setFillColor(colors.HexColor("#888888"))
            c.drawCentredString(qx + 31, qy - 11, ar("رمز التحقّق"))
            c.setFillColor(ink)
    except Exception:                                  # noqa: BLE001
        pass
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

    # رمز تحقّق QR بجانب الإجماليات (كما في فواتير الضريبة الرسمية)
    _name = rec.full_name_ar or rec.full_name_en or "—"
    _qr = _qr_drawing(f"{co['name_ar']} | فاتورة {number} | {_name} | "
                      f"{money(total)} AED | {date_str}", 66)
    if _qr is not None:
        _qr.hAlign = "CENTER"
    _qcap = ParagraphStyle("iqc", parent=st["cell"], alignment=1, fontSize=7.5,
                           textColor=colors.HexColor("#888888"), leading=10)
    side_cell = ([_qr, Spacer(1, 3), Paragraph(ar("رمز التحقّق"), _qcap)]
                 if _qr is not None else "")
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

# النسخة الإنجليزية من الشروط والأحكام (للفاوتشر باللغة الإنجليزية)
_VOUCHER_TERMS_EN = (
    "By receiving the trip itinerary, the guest acknowledges and agrees to all "
    "the terms and conditions stated herein.",
    "The guest must arrive at the airport at least two and a half hours before "
    "the flight and comply with the baggage rules set by the airline. Any delay "
    "or cancellation of flights is the responsibility of the airline and its "
    "management; {company} bears no responsibility in this regard.",
    "In case of ticket modification or cancellation, modification/cancellation "
    "fees apply according to the airlines' rules and any resulting change in the "
    "flight class. For group flights (Groups), the ticket is non-refundable and "
    "non-changeable, and its full value is charged.",
    "Some airlines (such as Air Arabia and flydubai) do not cancel the ticket "
    "or refund its value in cash. In some cases the booking may be modified no "
    "later than 24 hours before departure, provided the ticket value remains in "
    "the guest's account for use within one year from the issue date, with "
    "modification fees applied; this does not apply to group flights.",
    "Hotel check-in time is 5:00 PM and check-out time is 12:00 noon.",
    "In case of cancellation during high seasons (weekends, Ramadan, holidays) "
    "the full hotel booking value is charged; during the rest of the year one "
    "night is charged, provided cancellation is made at least 72 hours before "
    "the travel date.",
    "Any change in room types is subject to availability at the hotel and to a "
    "new price.",
    "Double rooms consist of one large bed or two separate beds; triple rooms "
    "consist of two separate beds and an extra small (rollaway) bed or a sofa "
    "bed, according to the hotel's system.",
    "Adjacent and connecting rooms are requested from the hotel reception upon "
    "check-in, subject to availability at the hotel.",
)


def build_voucher_data(rec, *, trip=None, program_name: str = "", company=None,
                       number: str = "", date_str: str = "",
                       booking_no: str = "", lang: str = "ar",
                       office_manager: str = "أيمن الشهابي",
                       office_phone: str = "+971 54 996 4801",
                       makkah_ops: str = "خالد",
                       makkah_phone: str = "+966 54 300 3388") -> dict:
    """يبني بيانات فاوتشر الفندق (قاموس قابل للتعديل) من بيانات المعتمر والبرنامج.
    يُستخدم كقيَم افتراضية في محرّر الفاوتشر، ثم يُمرَّر إلى
    :func:`export_umrah_voucher_pdf` عبر الوسيط ``data``.

    ``lang`` يحدّد لغة القيَم الافتراضية (المدن، الوجبات، الحالة، صفات جهات
    التواصل، والشروط): ``"ar"`` عربي أو ``"en"`` إنجليزي."""
    from datetime import timedelta

    from .umrah import _parse_date

    co = company_info(company)
    number = str(number or "MA0001")
    if not date_str:
        date_str = date.today().isoformat()
    en = lang == "en"

    def fmt(d):
        return d.isoformat() if d else ""

    cities = (("Makkah", "makkah_hotel", "makkah_nights"),
              ("Madinah", "madinah_hotel", "madinah_nights")) if en else \
             (("مكة المكرّمة", "makkah_hotel", "makkah_nights"),
              ("المدينة المنوّرة", "madinah_hotel", "madinah_nights"))
    meals = "Breakfast (B.B.)" if en else "إفطار (B.B.)"

    # الإقامات: الدخول/المغادرة محسوبة تسلسلياً من تاريخ مغادرة البرنامج
    stays: list[list[str]] = []
    cur = _parse_date(getattr(trip, "depart_date", "")) if trip else None
    for label, hotel_f, nights_f in cities:
        hotel = str(getattr(trip, hotel_f, "") or "") if trip else ""
        if not hotel:            # لا تسكين في هذه المدينة → تُلغى تلقائياً
            continue
        try:
            n = int(float(str(getattr(trip, nights_f, "") or "").strip() or 0))
        except ValueError:
            n = 0
        ci = cur
        cout = (cur + timedelta(days=n)) if (cur and n) else None
        # [المدينة، الفندق، نوع الغرفة، عدد الغرف، الإطلالة، الدخول، المغادرة،
        #  الليالي، الوجبات]
        stays.append([label, hotel, rec.room_type or "", "1", "",
                      fmt(ci), fmt(cout), str(n or ""), meals])
        cur = cout or cur

    # خطة النقل المفصّلة: كل صف [نوع السيارة، الموديل، الوجهة]
    car = str(getattr(rec, "vehicle", "") or "")
    if not car and trip:
        car = str(getattr(trip, "transport", "") or "")
    dest = ("Airport pickup at Jeddah, transfers between the two holy mosques "
            "and the hotels, then drop-off at the departure airport") if en else \
           ("استقبال من مطار جدة والتنقّل بين الحرمين والفنادق ثم التوصيل إلى "
            "مطار المغادرة")
    transport_rows = [[car or "GMC", "", dest]]

    terms_src = _VOUCHER_TERMS_EN if en else _VOUCHER_TERMS
    cname = co["name_en"] if en else co["name_ar"]
    terms = [t.format(company=cname) for t in terms_src]

    contacts = ([["Office Manager", office_manager, office_phone],
                 ["Makkah Operations Manager", makkah_ops, makkah_phone]]
                if en else
                [["مدير المكتب", office_manager, office_phone],
                 ["مدير العمليات في مكة", makkah_ops, makkah_phone]])

    return {
        "lang": lang,
        "number": number,
        "date": date_str,
        "guest_ar": rec.full_name_ar or "",
        "guest_en": (rec.full_name_en or "").upper(),
        "booking_no": booking_no or "",
        "program": program_name or "",
        # كل صف: [المدينة، الفندق، نوع الغرفة، الإطلالة، الدخول، المغادرة،
        #          الليالي، الوجبات]
        "stays": stays,
        # كل صف نقل: [نوع السيارة، الموديل، الوجهة]
        "transport_rows": transport_rows,
        "status": "CONFIRMED" if en else "مؤكّد / CONFIRMED",
        # كل جهة: [الصفة، الاسم، الهاتف]
        "contacts": contacts,
        "terms": terms,
    }


VOUCHER_STAY_HEADS = ("المدينة", "الفندق", "نوع الغرفة", "عدد الغرف", "الإطلالة",
                      "الدخول", "المغادرة", "الليالي", "الوجبات")
VOUCHER_STAY_HEADS_EN = ("City", "Hotel", "Room Type", "Rooms", "View",
                         "Check-in", "Check-out", "Nights", "Meals")
VOUCHER_TRANSPORT_HEADS = ("نوع السيارة", "الموديل", "الوجهة")
VOUCHER_TRANSPORT_HEADS_EN = ("Car Type", "Model", "Destination")
# خيارات القوائم المنسدلة في محرّر الفاوتشر
VOUCHER_VIEW_OPTIONS = ("", "City", "Haram", "P. Haram", "Kaaba", "P. Kaaba")
VOUCHER_CAR_TYPES = ("FORD", "GMC", "BMW")
VOUCHER_ROOM_TYPES = ("", "مفرد", "ثنائي", "ثلاثي", "رباعي",
                      "جناح غرفة وصالة", "جناح غرفتين وصالة")
VOUCHER_ROOM_TYPES_EN = ("", "Single", "Double", "Triple", "Quad",
                         "1BR Suite", "2BR Suite")
VOUCHER_ROOM_COUNTS = ("",) + tuple(str(i) for i in range(1, 21))
VOUCHER_CITY_OPTIONS = ("", "مكة المكرّمة", "المدينة المنوّرة")
VOUCHER_CITY_OPTIONS_EN = ("", "Makkah", "Madinah")

# ترتيب أعمدة الإقامة الجديد: أُدرج «عدد الغرف» بعد «نوع الغرفة» (الفهرس 3).
# الصفوف القديمة (٨ أعمدة) تُرحَّل بإدراج خانة فارغة في موضع عدد الغرف.
_VOUCHER_STAY_COLS = 9


def normalize_voucher_stay(row) -> list:
    """يوحّد صفّ إقامة إلى ٩ أعمدة، مُرحّلاً الصفوف القديمة (٨ أعمدة)."""
    row = [str(x or "") for x in list(row or [])]
    if len(row) == 8:                     # صيغة قديمة بلا «عدد الغرف»
        row = row[:3] + [""] + row[3:]    # أدرج عدد الغرف بعد نوع الغرفة
    if len(row) < _VOUCHER_STAY_COLS:
        row = row + [""] * (_VOUCHER_STAY_COLS - len(row))
    return row[:_VOUCHER_STAY_COLS]


def voucher_car_models() -> list:
    """موديلات السيارة: من 2025 وما فوق (حتى السنة القادمة)."""
    top = max(2027, date.today().year + 1)
    return [str(y) for y in range(top, 2024, -1)]


# ---- طلب/تأكيد حجز المواصلات (خطاب رسمي لشركة النقل) ----
# جدول الطيران بمخطّط متوافق مع قراءة الأماديوس: [التاريخ، الناقل، الإقلاع، من،
# الوصول، إلى] — فيُملأ مباشرةً من قارئ صورة حجز الأماديوس.
TREQ_FLIGHT_HEADS = ("التاريخ", "الناقل", "الإقلاع", "من", "الوصول", "إلى")
TREQ_MOVE_HEADS = ("التاريخ", "خط السير", "عدد", "نوع السيارة", "موديل", "الوقت")
TREQ_BOOK_HEADS = ("المدينة", "الفندق", "نوع الغرفة", "الإطلالة")
TREQ_HONORIFICS = ("السيد", "السيدة", "السادة", "الأخ", "الأخت")
TREQ_THANKS = "ولكم جزيل الشكر ،،"


def build_transport_request_data(rec, *, trip=None, program_name="",
                                 company=None, number="", date_str="",
                                 recipient=""):
    """يبني بيانات طلب حجز المواصلات (قاموس قابل للتعديل) من المعتمر والبرنامج."""
    company_info(company)
    number = str(number or "MA-T0001")
    if not date_str:
        date_str = date.today().isoformat()

    def T(field):
        return str(getattr(trip, field, "") or "") if trip else ""

    room = str(getattr(rec, "room_type", "") or "")
    # الحجوزات: صفّ لكل مدينة [المدينة، الفندق، نوع الغرفة، الإطلالة]
    bookings = []
    for label, hf in (("مكة المكرّمة", "makkah_hotel"),
                      ("المدينة المنوّرة", "madinah_hotel")):
        hotel = T(hf)
        if hotel:
            bookings.append([label, hotel, room, ""])

    dep, ret = T("depart_date"), T("return_date")
    airline = T("airline")
    flights = []
    if trip:
        flights = [
            [dep, airline, T("out_depart_time"), "", T("out_arrive_time"), ""],
            [ret, airline, T("ret_depart_time"), "", T("ret_arrive_time"), ""],
        ]

    car = next((c for c in VOUCHER_CAR_TYPES
                if c.lower() in T("transport").lower()), "FORD")
    model = voucher_car_models()[0]
    movements = [
        [dep, "من مطار جدة إلى فندق مكة", "1", car, model, ""],
        ["", "من فندق مكة إلى محطة قطار مكة", "1", car, model, ""],
        ["", "من محطة قطار المدينة إلى فندق المدينة", "1", car, model, ""],
        [ret, "من فندق المدينة إلى مطار المدينة", "1", car, model, ""],
    ]
    return {
        "number": number,
        "date": date_str,
        "recipient": recipient or "",
        "honorific": "السيد",
        "guest_ar": str(getattr(rec, "full_name_ar", "") or ""),
        "nationality": str(getattr(rec, "nationality_ar", "") or ""),
        "phone": str(getattr(rec, "phone", "") or ""),
        "persons": "",
        "bookings": bookings,
        "flights": flights,
        "movements": movements,
        "office_manager": QUOTE_OFFICE_NAME,
        "office_title": QUOTE_OFFICE_TITLE,
    }


def _treq_fmt_date(v):
    """يعرض التاريخ ISO بصيغة DD/MM/YYYY (وإلّا يبقى كما كُتب)."""
    s = str(v or "").strip()
    try:
        y, m, d = s.split("-")
        return f"{int(d):02d}/{int(m):02d}/{y}"
    except (ValueError, AttributeError):
        return s


def export_umrah_transport_request_pdf(rec, path, *, trip=None, program_name="",
                                       company=None, number="", date_str="",
                                       recipient="", data=None):
    """طلب/تأكيد حجز مواصلات: خطاب رسمي (A4 عمودي، عربي) موجّه لشركة النقل،
    يضمّ الجهة والضيف والحجوزات (مكة/المدينة) وجدولَي الطيران والحركة وعبارة
    الشكر وتوقيع مدير المكتب. عند تمرير ``data`` يُبنى المستند من محتواه."""
    _register_fonts()
    path = Path(path)
    if data is None:
        data = build_transport_request_data(
            rec, trip=trip, program_name=program_name, company=company,
            number=number, date_str=date_str, recipient=recipient)
    number = str(data.get("number") or "")
    date_str = str(data.get("date") or date.today().isoformat())
    co = company_info(company)

    doc = SimpleDocTemplate(
        str(path), pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm,
        topMargin=9 * mm, bottomMargin=18 * mm, title="طلب حجز مواصلات",
        author="ميسّر العمرة")
    st = _styles()
    story = []
    W = doc.width
    _DEEP = colors.HexColor("#6E543A")

    def _logo(pathobj, h):
        if not pathobj.is_file():
            return ""
        try:
            iw, ih = ImageReader(str(pathobj)).getSize()
            return RLImage(str(pathobj), width=h * iw / ih, height=h)
        except Exception:
            return ""

    header = Table([[_logo(_NIRVANA_PATH, 50), _logo(_LOGO_PATH, 40)]],
                   colWidths=[W / 2, W / 2])
    header.setStyle(TableStyle([
        ("ALIGN", (0, 0), (0, 0), "LEFT"), ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(header)
    story.append(Spacer(1, 6))

    # شريط العنوان (بلون الهوية) + سطر إنجليزي أنيق
    band = Table([[Paragraph(ar("طلب حجز مواصلات"), ParagraphStyle(
                       "tbt", fontName=_FONT_BOLD, fontSize=16, alignment=1,
                       textColor=colors.white, leading=20))],
                  [Paragraph(co["name_en"].upper() + "   ·   TRANSPORTATION "
                             "REQUEST", ParagraphStyle(
                       "tbs", fontName=_FONT, fontSize=8, alignment=1,
                       textColor=colors.HexColor("#EFE6D8"), leading=11))]],
                 colWidths=[W])
    band.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _ACCENT),
        ("LINEABOVE", (0, 0), (-1, 0), 1.6, _DEEP),
        ("LINEBELOW", (0, -1), (-1, -1), 1.6, _DEEP),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 0),
        ("TOPPADDING", (0, 1), (-1, 1), 0),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 5)]))
    story.append(band)
    story.append(Spacer(1, 7))

    lbl = ParagraphStyle("tl", parent=st["cell"], fontName=_FONT_BOLD,
                         textColor=_ACCENT, alignment=2, fontSize=9.5)
    valc = ParagraphStyle("tvc", parent=st["cell"], alignment=1, fontSize=9.5)
    # بطاقة الرقم والتاريخ (يمين→يسار: رقم الطلب | القيمة | التاريخ | القيمة)
    meta = Table([[_ar_para(ltr(_treq_fmt_date(date_str)), valc, W * 0.34 - 12),
                   _ar_para("التاريخ", lbl, W * 0.16 - 12),
                   _ar_para(number, valc, W * 0.34 - 12),
                   _ar_para("رقم الطلب", lbl, W * 0.16 - 12)]],
                 colWidths=[W * 0.34, W * 0.16, W * 0.34, W * 0.16])
    meta.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, _ACCENT),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, _GRID),
        ("BACKGROUND", (1, 0), (1, 0), _ALT_ROW),
        ("BACKGROUND", (3, 0), (3, 0), _ALT_ROW),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story.append(meta)
    story.append(Spacer(1, 8))

    rp = ParagraphStyle("trp", parent=st["cell"], alignment=2, fontSize=10.5,
                        leading=19)
    rpb = ParagraphStyle("trpb", parent=rp, fontName=_FONT_BOLD)

    def line(text, bold=False):
        return Paragraph(ar(text), rpb if bold else rp)

    story.append(line(f"السادة / {data.get('recipient') or '—'}    المحترمين",
                      bold=True))
    story.append(line("تحية طيبة وبعد ،،"))
    story.append(Spacer(1, 3))
    # الموضوع في شريط مميّز
    subj = Table([[Paragraph(ar("الموضوع:  تأكيد حجز مواصلات"), ParagraphStyle(
                       "tsub", fontName=_FONT_BOLD, fontSize=11, alignment=2,
                       textColor=_DEEP, leading=15))]], colWidths=[W])
    subj.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _ALT_ROW),
        ("LINEBEFORE", (0, 0), (0, -1), 3, _ACCENT),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8)]))
    story.append(subj)
    story.append(Spacer(1, 6))

    hon = str(data.get("honorific") or "").strip()
    guest = str(data.get("guest_ar") or "—").strip()
    nat = str(data.get("nationality") or "").strip()
    who = (hon + " " if hon else "") + guest + (f"  ({nat})" if nat else "")
    story.append(line("اسم الضيف:  " + who, bold=True))
    info_bits = []
    if str(data.get("phone") or "").strip():
        info_bits.append(f"جوال رقم: {ltr(data.get('phone'))}")
    if str(data.get("persons") or "").strip():
        info_bits.append(f"عدد الأشخاص: ( {ltr(data.get('persons'))} ) أشخاص")
    if info_bits:
        story.append(line("     ·     ".join(info_bits)))
    story.append(Spacer(1, 8))

    def sec(title):
        p = Paragraph(ar(title), ParagraphStyle(
            "tsec", fontName=_FONT_BOLD, fontSize=11, alignment=2,
            textColor=_DEEP, leading=14))
        t = Table([[p]], colWidths=[W])
        t.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, -1), 1.0, _ACCENT),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        return t

    def table(heads, rows, weights, date_col=None):
        scale = W / sum(weights)
        # الأوزان بترتيب العناوين الطبيعي؛ نعكس العرض ليطابق الترتيب البصري RTL
        colw = list(reversed([w * scale for w in weights]))
        avail = [w - 6 for w in colw]           # يطابق حشو الخلية (3+3)
        body = [_ar_cells(list(reversed(heads)), st["head"], avail)]
        for r in rows:
            r = [str(x or "") for x in (list(r) + [""] * len(heads))[:len(heads)]]
            if date_col is not None:
                r[date_col] = _treq_fmt_date(r[date_col])
            body.append(_ar_cells(list(reversed(r)), st["cell"], avail))
        t = Table(body, colWidths=colw, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _ACCENT),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
            ("BOX", (0, 0), (-1, -1), 0.8, _ACCENT),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ALT_ROW]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("ROUNDEDCORNERS", [4, 4, 4, 4])]))
        return t

    bookings = [b for b in (data.get("bookings") or [])
                if any(str(x or "").strip() for x in b)]
    if bookings:
        story.append(sec("الحجوزات"))
        story.append(Spacer(1, 3))
        story.append(table(TREQ_BOOK_HEADS, bookings, [76, 168, 62, 64]))
        story.append(Spacer(1, 8))

    flights = [f for f in (data.get("flights") or [])
               if any(str(x or "").strip() for x in f)]
    if flights:
        story.append(sec("جدول الطيران"))
        story.append(Spacer(1, 3))
        story.append(table(TREQ_FLIGHT_HEADS, flights,
                           [72, 78, 60, 78, 60, 78], date_col=0))
        story.append(Spacer(1, 8))

    moves = [m for m in (data.get("movements") or [])
             if any(str(x or "").strip() for x in m)]
    story.append(sec("جدول الحركة  —  المواصلات المطلوبة"))
    story.append(Spacer(1, 3))
    story.append(table(TREQ_MOVE_HEADS, moves or [["", "", "", "", "", ""]],
                       [66, 214, 26, 80, 38, 46], date_col=0))
    story.append(Spacer(1, 14))

    story.append(Paragraph(ar(TREQ_THANKS), ParagraphStyle(
        "tthx", parent=rpb, alignment=2, fontSize=11)))
    story.append(Spacer(1, 14))

    # التوقيع (يميناً) + رمز تحقّق QR (يساراً) — لمسة توثيق عصرية
    sig = ParagraphStyle("tsig", parent=st["cell"], alignment=1, fontSize=11,
                         fontName=_FONT_BOLD, leading=17)
    cap = ParagraphStyle("tqc", parent=st["cell"], alignment=1, fontSize=7.5,
                         textColor=colors.HexColor("#888888"), leading=10)
    sig_cell = [Paragraph(ar(data.get("office_title") or "مدير المكتب"), sig),
                Spacer(1, 2),
                Paragraph(ar(data.get("office_manager") or ""), sig)]
    guest = str(data.get("guest_ar") or "").strip()
    qr = _qr_drawing(f"{co['name_ar']} | مواصلات {number} | {guest} | "
                     f"{date_str}", 58)
    qr_cell = [qr, Spacer(1, 2), Paragraph(ar("رمز التحقّق"), cap)] if qr else ""
    sig_tbl = Table([[qr_cell, sig_cell]], colWidths=[W * 0.32, W * 0.68])
    sig_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, 0), "CENTER"),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(sig_tbl)

    doc.build(
        story,
        onFirstPage=lambda c, d: _umrah_page(c, d, "طلب حجز مواصلات"),
        onLaterPages=lambda c, d: _umrah_page(c, d, "طلب حجز مواصلات"))
    return path


def export_umrah_voucher_pdf(rec, path: str | Path, *, trip=None,
                             program_name: str = "", company=None,
                             number: str = "", date_str: str = "",
                             booking_no: str = "", lang: str = "ar",
                             office_manager: str = "أيمن الشهابي",
                             office_phone: str = "+971 54 996 4801",
                             makkah_ops: str = "خالد",
                             makkah_phone: str = "+966 54 300 3388",
                             data: dict | None = None) -> Path:
    """فاوتشر فندق عمرة لمعتمر واحد على صفحة **عرضية** (Landscape) بشعارَي
    الحملة، بيانات الضيف، إقامات مكة/المدينة، خطة النقل المفصّلة، جهات التواصل،
    الختم الرسمي، والشروط والأحكام. يدعم اللغتين العربية والإنجليزية (``lang``).

    عند تمرير ``data`` (قاموس من :func:`build_voucher_data`، وقد عُدِّل يدوياً)
    يُبنى المستند من محتواه بالكامل؛ وإلّا يُبنى تلقائياً من ``rec`` و``trip``."""
    _register_fonts()
    path = Path(path)
    if data is None:
        data = build_voucher_data(
            rec, trip=trip, program_name=program_name, company=company,
            number=number, date_str=date_str, booking_no=booking_no, lang=lang,
            office_manager=office_manager, office_phone=office_phone,
            makkah_ops=makkah_ops, makkah_phone=makkah_phone)
    number = str(data.get("number") or "MA0001")
    date_str = str(data.get("date") or date.today().isoformat())
    lang = str(data.get("lang") or "ar")
    L = lang == "en"                 # إنجليزي ⇒ اتجاه من اليسار لليمين
    ALN = 0 if L else 2              # محاذاة القيَم/العناوين حسب اتجاه القراءة

    def rev(seq):
        """ترتيب الأعمدة بصرياً: كما هو للإنجليزية، ومعكوس للعربية (RTL)."""
        return list(seq) if L else list(reversed(seq))

    co = company_info(company)
    doc = SimpleDocTemplate(
        str(path), pagesize=landscape(A4), rightMargin=13 * mm,
        leftMargin=13 * mm, topMargin=7 * mm, bottomMargin=10 * mm,
        title="Hotel Voucher", author="ميسّر العمرة")
    st = _styles()
    story = []
    W = doc.width
    _DEEP = colors.HexColor("#6E543A")          # بنّي غامق للتدرّج والحدود

    def _logo_cell(pathobj, h):
        """شعار بارتفاع محدّد."""
        if not pathobj.is_file():
            return ""
        try:
            iw, ih = ImageReader(str(pathobj)).getSize()
            return RLImage(str(pathobj), width=h * iw / ih, height=h)
        except Exception:
            return ""

    # ترويسة: شعار نيرفانا أكبر قليلاً ليتناسب بصرياً مع شعار المصطفى
    al = _logo_cell(_LOGO_PATH, 46)
    nv = _logo_cell(_NIRVANA_PATH, 58)
    header = Table([[nv, al]], colWidths=[W / 2, W / 2])
    header.setStyle(TableStyle([
        ("ALIGN", (0, 0), (0, 0), "LEFT"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header)
    story.append(Spacer(1, 4))

    # شريط العنوان بالإنجليزية فقط (احترافي، بلون الهوية)
    band_title = ParagraphStyle("vbt", fontName=_FONT_BOLD, fontSize=18,
                                alignment=1, textColor=colors.white, leading=21)
    band_sub = ParagraphStyle("vbs", fontName=_FONT, fontSize=8.5, alignment=1,
                              textColor=colors.HexColor("#EFE6D8"), leading=12,
                              spaceBefore=1)
    band = Table([[Paragraph("HOTEL VOUCHER", band_title)],
                  [Paragraph(co["name_en"].upper(), band_sub)]],
                 colWidths=[W])
    band.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _ACCENT),
        ("LINEABOVE", (0, 0), (-1, 0), 2.0, _DEEP),
        ("LINEBELOW", (0, -1), (-1, -1), 2.0, _DEEP),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 5),
        ("TOPPADDING", (0, 1), (-1, 1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 1),
    ]))
    story.append(band)
    story.append(Spacer(1, 4))

    lbl = ParagraphStyle("vlbl", parent=st["cell"], fontName=_FONT_BOLD,
                         textColor=_ACCENT, alignment=ALN, fontSize=9)
    val = ParagraphStyle("vval", parent=st["cell"], alignment=ALN, fontSize=9)

    # ---- بطاقة البيانات: أزواج (عنوان، قيمة) بترتيب القراءة ----
    guest_ar = data.get("guest_ar") or "—"
    guest_en = data.get("guest_en") or "—"
    if L:
        LB = {"vno": "Voucher No.", "date": "Date", "guest": "Guest Name",
              "booking": "Booking No.", "program": "Program", "name2": "الاسم"}
        g_main, g_second = guest_en, guest_ar
    else:
        LB = {"vno": "رقم الفاوتشر", "date": "التاريخ", "guest": "اسم الضيف",
              "booking": "رقم الحجز", "program": "البرنامج", "name2": "Guest name"}
        g_main, g_second = guest_ar, guest_en
    # أزواج (عنوان، قيمة) — يُدرَج «البرنامج» فقط إن لم يكن فارغاً (قابل للإلغاء)
    pairs = [(LB["vno"], number), (LB["date"], ltr(date_str)),
             (LB["guest"], g_main),
             (LB["booking"], data.get("booking_no") or "—")]
    _prog = str(data.get("program") or "").strip()
    if _prog:
        pairs.append((LB["program"], _prog))
    pairs.append((LB["name2"], g_second))
    meta_rows = [pairs[i:i + 2] for i in range(0, len(pairs), 2)]
    if meta_rows and len(meta_rows[-1]) == 1:
        meta_rows[-1].append(("", ""))
    lw = [W * 0.16, W * 0.34, W * 0.16, W * 0.34]     # عرض منطقي (عنوان/قيمة)
    mcw = rev(lw)
    meta_data = []
    for pairs in meta_rows:
        flat = []
        for label, value in pairs:
            flat.append((label, lbl))
            flat.append((str(value), val))
        flat = rev(flat)
        meta_data.append([_ar_para(t, s, mcw[i] - 12)
                          for i, (t, s) in enumerate(flat)])
    meta = Table(meta_data, colWidths=mcw)
    meta.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, _ACCENT),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, _GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(meta)
    story.append(Spacer(1, 4))

    def section(title_ar, title_en):
        """عنوان قسم: إنجليزي فقط في الوضع الإنجليزي، وثنائي اللغة في العربي."""
        txt = title_en if L else (ar(title_ar) + f"  /  {title_en}")
        p = Paragraph(txt, ParagraphStyle(
            "vsec", fontName=_FONT_BOLD, fontSize=9.5, alignment=ALN,
            textColor=_DEEP, leading=12))
        t = Table([[p]], colWidths=[W])
        t.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, -1), 1.0, _ACCENT),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        return t

    def data_table(heads, weights, rows_vals, num_cols=()):
        """يبني جدولاً بترويسة بلون الهوية، مع ترتيب أعمدة حسب اتجاه اللغة.
        ``num_cols`` فهارس منطقية لأعمدة أرقام تُلفّ بـ LTR."""
        vw = rev(weights)
        scale = W / sum(vw)
        cw = [w * scale for w in vw]
        av = [w - 9 for w in cw]
        table = [_ar_cells(rev(heads), st["head"], av)]
        for row in rows_vals:
            vals = [str(x if x not in (None, "") else "—") for x in row]
            vals = [ltr(v) if i in num_cols else v for i, v in enumerate(vals)]
            table.append(_ar_cells(rev(vals), st["cell"], av))
        if len(table) == 1:
            table.append(_ar_cells([""] * len(heads), st["cell"], av))
        t = Table(table, colWidths=cw)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _ACCENT),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.8, _ACCENT),
            ("INNERGRID", (0, 0), (-1, -1), 0.4, _GRID),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ALT_ROW]),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ]))
        return t

    # ---- الإقامة ----
    story.append(section("تفاصيل الإقامة", "Accommodation"))
    story.append(Spacer(1, 4))
    stay_heads = list(VOUCHER_STAY_HEADS_EN if L else VOUCHER_STAY_HEADS)

    def _fmt_stay_date(s):
        s = str(s or "").strip()
        m = _re_iso.match(s)
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else s

    stay_vals = []
    for r in data.get("stays", []):
        row = normalize_voucher_stay(r)
        row[5] = _fmt_stay_date(row[5])       # الدخول
        row[6] = _fmt_stay_date(row[6])       # المغادرة
        stay_vals.append(row)
    # الأعمدة الرقمية (تُلفّ LTR): عدد الغرف، الدخول، المغادرة، الليالي
    story.append(data_table(stay_heads, [56, 104, 54, 36, 46, 56, 56, 32, 46],
                            stay_vals, num_cols=(3, 5, 6, 7)))
    story.append(Spacer(1, 4))

    # ---- خطة النقل (مفصّلة: نوع السيارة/الموديل/الوجهة) ----
    story.append(section("خطة النقل", "Transportation"))
    story.append(Spacer(1, 4))
    transport_rows = [list(r)[:3] + [""] * (3 - len(r))
                      for r in data.get("transport_rows", [])
                      if any(str(x or "").strip() for x in r)]
    if not transport_rows and str(data.get("transport") or "").strip():
        transport_rows = [["", "", str(data["transport"])]]   # توافق خلفي
    tr_heads = list(VOUCHER_TRANSPORT_HEADS_EN if L else VOUCHER_TRANSPORT_HEADS)
    story.append(data_table(tr_heads, [80, 60, 320],
                            transport_rows or [["", "", ""]]))

    status = str(data.get("status") or "")
    if status:
        story.append(Spacer(1, 4))
        label = "Booking status" if L else "حالة الحجز / Booking status"
        story.append(_ar_para(
            f"{label}: {status}",
            ParagraphStyle("vconf", parent=st["cell"], alignment=ALN,
                           fontSize=9.5, fontName=_FONT_BOLD, leading=14,
                           textColor=colors.HexColor("#2E6B45")),
            W - 12))
    story.append(Spacer(1, 4))

    # ---- التواصل والاستفسار + الختم جنباً إلى جنب، كلٌّ بعنوانه فوقه ----
    ttl = ParagraphStyle("vttl", parent=st["cell"], alignment=1, fontSize=9.5,
                         textColor=_ACCENT, fontName=_FONT_BOLD, leading=13)
    contact_data = [c for c in data.get("contacts", [])
                    if any(str(x or "").strip() for x in c)]
    if contact_data:
        story.append(Spacer(1, 2))
        cwv = 0.66      # عرض عمود التواصل، والباقي للختم
        cw_logic = [cwv * W * 0.26, cwv * W * 0.40, cwv * W * 0.34]
        ccw = rev(cw_logic)
        val_num = ParagraphStyle("vnum", parent=val, fontName=_FONT_BOLD,
                                 alignment=ALN)

        def contact_row(role, name, phone):
            cells = [(role, lbl), (name, val), (ltr(phone), val_num)]
            cells = rev(cells)
            return [_ar_para(t, s, ccw[i] - 10)
                    for i, (t, s) in enumerate(cells)]

        contacts = Table([contact_row(str(c[0]), str(c[1]), str(c[2]))
                          for c in contact_data], colWidths=ccw)
        contacts.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.8, _ACCENT),
            ("INNERGRID", (0, 0), (-1, -1), 0.4, _GRID),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        # عمود التواصل: عنوان «للتواصل والاستفسار» فوق جدول الأرقام
        c_title = "Contact & Inquiries" if L else "للتواصل والاستفسار"
        contact_col = Table([[_ar_para(c_title, ttl, cwv * W - 6)], [contacts]],
                            colWidths=[cwv * W])
        contact_col.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 3),
            ("TOPPADDING", (0, 1), (-1, 1), 0),
        ]))
        # عمود الختم: كلمة «الختم» فوق مربّع الشعار (بلا نصّ إنجليزي)
        s_title = "Stamp" if L else "الختم"
        stamp_logo = _logo_cell(_LOGO_PATH, 46)
        stamp_box = Table([[stamp_logo]], colWidths=[(1 - cwv) * W * 0.9])
        stamp_box.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.8, _ACCENT),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FCFAF6")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        stamp_col = Table([[_ar_para(s_title, ttl, (1 - cwv) * W - 6)],
                           [stamp_box]], colWidths=[(1 - cwv) * W])
        stamp_col.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 3),
            ("TOPPADDING", (0, 1), (-1, 1), 0),
        ]))
        combo = Table([rev([contact_col, stamp_col])],
                      colWidths=rev([cwv * W, (1 - cwv) * W]))
        combo.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(combo)
        story.append(Spacer(1, 4))

    # ---- الشروط والأحكام (ثابتة) — عمودان لتوفير الارتفاع (صفحة واحدة) ----
    terms = [t for t in data.get("terms", []) if str(t or "").strip()]
    if terms:
        story.append(section("الشروط والأحكام", "Terms & Conditions"))
        story.append(Spacer(1, 3))
        term = ParagraphStyle("vterm", parent=st["cell"], alignment=ALN,
                              fontSize=7.2, leading=9.5, spaceAfter=4)
        ncols = 3
        colw = W / ncols
        # لفٌّ يدوي قبل bidi كي تبقى الأسطر مرتّبة رأسياً داخل كل عمود
        flow = [_ar_para(f"{i}. " + str(t), term, colw - 16)
                for i, t in enumerate(terms, 1)]
        per = (len(flow) + ncols - 1) // ncols
        cols = [flow[i * per:(i + 1) * per] for i in range(ncols)]
        cols = rev([c or [""] for c in cols])        # ترتيب بصري حسب اللغة
        tt = Table([cols], colWidths=[colw] * ncols)
        tt.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOX", (0, 0), (-1, -1), 0.6, _GRID),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, _GRID),   # فواصل بين الأعمدة
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FCFAF6")),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))
        story.append(tt)

    def _vfooter(canvas, d):
        canvas.saveState()
        canvas.setFont(_FONT, 7.5)
        canvas.setFillColor(colors.HexColor("#888888"))
        pw = landscape(A4)[0]
        page_lbl = f"Page {d.page}" if L else ar(f"صفحة {d.page}")
        canvas.drawCentredString(pw / 2, 8 * mm, page_lbl)
        canvas.drawRightString(pw - 13 * mm, 8 * mm, "Hotel Voucher")
        canvas.drawString(13 * mm, 8 * mm, date.today().isoformat())
        canvas.restoreState()

    doc.build(story, onFirstPage=_vfooter, onLaterPages=_vfooter)
    return path


# ======================================================================
#  عرض السعر (Quotation)
# ======================================================================

QUOTE_STAY_HEADS = ("المدينة", "الليالي", "الفندق", "نوع الغرفة", "عدد الغرف",
                    "الإطلالة", "الوجبات")
QUOTE_FLIGHT_HEADS = ("اليوم", "الناقل", "الإقلاع", "من", "الوصول", "إلى")

# خيارات القوائم المنسدلة في محرّر عرض السعر
QUOTE_GUEST_TYPES = ("كبار", "صغار", "أطفال", "رضّع")
QUOTE_CITY_OPTIONS = ("مكة المكرّمة", "المدينة المنوّرة")
QUOTE_NIGHTS = tuple(str(i) for i in range(1, 11))
QUOTE_ROOM_TYPES = ("مفرد", "ثنائي", "ثلاثي", "رباعي", "جناح غرفة وصالة",
                    "جناح غرفتين وصالة", "جناح 3 غرف وصالة", "جناح 4 غرف وصالة")
QUOTE_ROOM_COUNTS = tuple(str(i) for i in range(1, 11))
QUOTE_VIEWS = ("غير مطلّة", "مطلّة مدينة", "مطلّة كعبة")
QUOTE_MEALS = ("إفطار", "غداء", "عشاء", "وجبات كاملة", "غداء وعشاء")
QUOTE_FLIGHT_CLASSES = ("سياحية", "رجال أعمال", "درجة أولى")
QUOTE_CARRIERS = ("السعودية", "الاتحاد", "الإمارات", "فلاي دبي", "فلاي ناس",
                  "العربية", "أديل")
QUOTE_AIRPORT_CITIES = ("أبوظبي", "دبي", "جدة", "المدينة", "الرياض", "الطائف",
                        "رأس الخيمة")
QUOTE_CAR_TYPES = ("GMC", "FORD", "BMW", "Mercedes", "VAN", "Mini Bus", "Satria")
QUOTE_CAR_MODELS = ("2025", "2026", "2027", "2028")
QUOTE_CAR_COUNTS = tuple(str(i) for i in range(1, 11))
QUOTE_LOCATIONS = ("مطار جدة", "مطار المدينة", "فندق مكة", "فندق المدينة",
                   "محطة قطار مكة", "محطة قطار المدينة", "مطار الرياض",
                   "مطار الطائف")
QUOTE_HOTELS = ("جميرا مكة جبل عمر", "فيرمونت مكة", "هيلتون مكة الضيافة",
                "سويس أوتيل مكة", "دار الإيمان الحرم", "دار التقوى",
                "أنوار المدينة موفنبيك", "شذا المدينة")
QUOTE_GREETING = "السلام عليكم ورحمة الله وبركاته،"
QUOTE_CLOSING = ("آملين أن تنال برامجنا رضاكم وكريم استحسانكم، وبانتظار "
                 "ردّكم الكريم.")
# بنود مختصرة تُذيَّل بها عروض الأسعار (ثابتة، تُعرض بلغة العرض)
QUOTE_TERMS = (
    "الأسعار قابلة للتغيّر حسب توفّر الغرف والمقاعد وقت تأكيد الحجز.",
    "لا يشمل العرض ما لم يُذكر صراحةً فيه من خدمات أو رسوم.",
    "يُعتمد الحجز بعد دفع العربون وتأكيد التوفّر، وتخضع التعديلات "
    "والإلغاء لشروط الفنادق وشركات الطيران.",
)
QUOTE_TERMS_EN = (
    "Prices are subject to change based on room and seat availability at the "
    "time of booking confirmation.",
    "The quotation excludes any services or fees not explicitly stated herein.",
    "Booking is confirmed after paying the deposit and confirming availability; "
    "amendments and cancellations are subject to hotel and airline policies.",
)
# ملاحظات جاهزة (تُترجم آلياً عند تحويل العرض للإنجليزية)
QUOTE_NOTES = (
    "جميع الحجوزات غير قابلة للإلغاء أو التعديل.",
    "الأسعار قابلة للتغيير حسب التوفّر وقت التأكيد.",
    "الأسعار شاملة الضرائب والرسوم.",
    "التأشيرات حسب أنظمة الجهات المختصّة.",
    "يُرجى تزويدنا بصور الجوازات لإتمام الحجز.",
)
# خانة توقيع ثابتة (غير قابلة للتعديل)
QUOTE_OFFICE_TITLE = "مدير المكتب"
QUOTE_OFFICE_NAME = "أيمن الشهابي"
QUOTE_OFFICE_PHONE = "0549964801"

# ترجمة المفردات الثابتة لعرض السعر بالإنجليزية (النصوص الحرّة تبقى كما هي)
_QTR = {
    "cities": {"مكة المكرّمة": "Makkah", "المدينة المنوّرة": "Madinah"},
    "rooms": {"مفرد": "Single", "ثنائي": "Double", "ثلاثي": "Triple",
              "رباعي": "Quad", "جناح غرفة وصالة": "1-BR Suite",
              "جناح غرفتين وصالة": "2-BR Suite",
              "جناح 3 غرف وصالة": "3-BR Suite",
              "جناح 4 غرف وصالة": "4-BR Suite"},
    "views": {"غير مطلّة": "No View", "مطلّة مدينة": "City View",
              "مطلّة كعبة": "Kaaba View"},
    "meals": {"إفطار": "Breakfast", "غداء": "Lunch", "عشاء": "Dinner",
              "وجبات كاملة": "Full Board", "غداء وعشاء": "Lunch & Dinner"},
    "persons": {"كبار": "Adults", "صغار": "Minors", "أطفال": "Children",
                "رضّع": "Infants"},
    "classes": {"سياحية": "Economy", "رجال أعمال": "Business",
                "درجة أولى": "First"},
    "carriers": {"السعودية": "Saudia", "الإتحاد": "Etihad",
                 "الاتحاد": "Etihad", "الإمارات": "Emirates",
                 "فلاي دبي": "flydubai", "فلاي ناس": "flynas",
                 "العربية": "Air Arabia", "أديل": "flyadeal",
                 "الجزيرة": "Jazeera"},
    "airports": {"أبوظبي": "Abu Dhabi", "دبي": "Dubai", "الشارقة": "Sharjah",
                 "رأس الخيمة": "Ras Al Khaimah", "جدة": "Jeddah",
                 "المدينة": "Madinah", "الرياض": "Riyadh", "الطائف": "Taif",
                 "الدمام": "Dammam", "مكة": "Makkah"},
    "locations": {"مطار جدة": "Jeddah Airport", "مطار المدينة": "Madinah Airport",
                  "فندق مكة": "Makkah Hotel", "فندق المدينة": "Madinah Hotel",
                  "محطة قطار مكة": "Makkah Train Station",
                  "محطة قطار المدينة": "Madinah Train Station",
                  "مطار الرياض": "Riyadh Airport", "مطار الطائف": "Taif Airport"},
    "visa": {"سياحية": "Tourist", "عمرة": "Umrah"},
    "hotels": {"جميرا مكة جبل عمر": "Jumeirah Makkah Jabal Omar",
               "فيرمونت مكة": "Fairmont Makkah",
               "هيلتون مكة الضيافة": "Hilton Makkah Convention",
               "سويس أوتيل مكة": "Swissotel Makkah",
               "دار الإيمان الحرم": "Dar Al Iman Haram",
               "دار التقوى": "Dar Al Taqwa",
               "أنوار المدينة موفنبيك": "Anwar Al Madinah Movenpick",
               "شذا المدينة": "Shaza Madinah", "جميرا مكة": "Jumeirah Makkah",
               "دار الإيمان": "Dar Al Iman"},
    "office": {"أيمن الشهابي": "AYMAN ALSHEHABI",
               "مدير المكتب": "Office Manager"},
    "titles": {"السيد": "Mr.", "السيدة": "Mrs.", "الآنسة": "Ms."},
    "notes": {
        "جميع الحجوزات غير قابلة للإلغاء أو التعديل.":
            "All bookings are non-refundable and non-changeable.",
        "الأسعار قابلة للتغيير حسب التوفّر وقت التأكيد.":
            "Prices are subject to change based on availability at confirmation.",
        "الأسعار شاملة الضرائب والرسوم.":
            "Prices are inclusive of taxes and fees.",
        "التأشيرات حسب أنظمة الجهات المختصّة.":
            "Visas are subject to the regulations of the competent authorities.",
        "يُرجى تزويدنا بصور الجوازات لإتمام الحجز.":
            "Please provide passport copies to complete the booking.",
    },
    "phrases": {"عرض سعر رحلة عمرة": "Umrah Trip Quotation",
                QUOTE_GREETING: "Greetings,",
                QUOTE_CLOSING: ("We hope our programs meet your satisfaction; "
                                "awaiting your kind reply."),
                "درهم": "AED", "ريال": "SAR", "دولار": "USD"},
}
# خرائط عكسية (إنجليزي ← عربي) للتحويل في الاتجاهين
_QTR_REV = {cat: {v: k for k, v in m.items()} for cat, m in _QTR.items()}


def _qtr(val, cat: str, en: bool):
    """يترجم مفردة ثابتة إلى الإنجليزية عند ``en`` وإلّا يعيدها كما هي."""
    if not en:
        return val
    return _QTR.get(cat, {}).get(str(val or "").strip(), val)


def _tr_val(val, cat: str, to_en: bool):
    """يحوّل مفردة ثابتة في الاتجاهين حسب الهدف (إنجليزي/عربي)."""
    v = str(val or "").strip()
    table = _QTR.get(cat, {}) if to_en else _QTR_REV.get(cat, {})
    return table.get(v, val)


def translate_quotation_data(data: dict, lang: str) -> dict:
    """يترجم بيانات عرض سعر محفوظ إلى اللغة الهدف مع الحفاظ على محتوى المستخدم
    (النصوص الحرّة وأسماء الفنادق المعروفة تُترجم، وغير المعروف يبقى كما هو)."""
    d = dict(data)
    en = lang == "en"
    d["lang"] = lang

    def tv(val, cat):
        return _tr_val(val, cat, en)

    d["title"] = tv(data.get("title"), "phrases")
    d["greeting"] = tv(data.get("greeting"), "phrases")
    d["closing"] = tv(data.get("closing"), "phrases")
    d["currency"] = tv(data.get("currency"), "phrases")
    # الملاحظات: تُترجم إن كانت من الجاهزة (سطراً سطراً)، وإلّا تبقى كما هي
    d["note"] = "\n".join(tv(ln, "notes")
                          for ln in str(data.get("note") or "").split("\n"))
    d["flight_class"] = tv(data.get("flight_class"), "classes")
    d["visa_type"] = tv(data.get("visa_type"), "visa")
    d["addressed_title"] = tv(data.get("addressed_title"), "titles")
    # الإقامات
    d["stays"] = []
    for r in data.get("stays", []):
        r = list(r) + [""] * (9 - len(r))
        d["stays"].append([tv(r[0], "cities"), r[1], tv(r[2], "hotels"),
                           tv(r[3], "rooms"), r[4], tv(r[5], "views"),
                           tv(r[6], "meals"), r[7], r[8]])
    # الطيران
    d["flights"] = [[r[0], tv(r[1], "carriers"), r[2], tv(r[3], "airports"),
                     r[4], tv(r[5], "airports")]
                    for r in (list(x) + [""] * (6 - len(x))
                              for x in data.get("flights", []))]
    # بنود التنقّل
    d["transport_lines"] = [[r[0], tv(r[1], "locations"), tv(r[2], "locations")]
                            for r in (list(x) + [""] * (3 - len(x))
                                      for x in data.get("transport_lines", []))]
    # القطار
    d["trains"] = [[r[0], tv(r[1], "classes"), tv(r[2], "airports"),
                    tv(r[3], "airports"), r[4], r[5], r[6]]
                   for r in (list(x) + [""] * (7 - len(x))
                             for x in data.get("trains", []))]
    # الضيوف والتسعير
    d["guests"] = [[g[0], tv(g[1], "persons")]
                   for g in (list(x) + [""] * (2 - len(x))
                             for x in data.get("guests", []))]
    d["pricing"] = [[tv(p[0], "persons"), tv(p[1], "rooms"), p[2], p[3]]
                    for p in (list(x) + [""] * (4 - len(x))
                              for x in data.get("pricing", []))]
    # نصّ التأشيرات يُعاد بناؤه من العدد والنوع
    vc = str(data.get("visa_count") or "").strip()
    if vc:
        vt = d["visa_type"]
        d["visas"] = f"{vc} {vt} visa(s)" if en else f"عدد ({vc}) تأشيرة {vt}"
    return d


def quote_times() -> list:
    """أوقات بفواصل خمس دقائق (00:00 … 23:55) لقوائم الطيران — والحقل قابل
    للكتابة اليدوية لأي دقيقة."""
    return [f"{h:02d}:{m:02d}" for h in range(24) for m in range(0, 60, 5)]


def _money_num(x) -> float:
    try:
        return float(str(x).replace(",", "").replace("،", "").strip() or 0)
    except (TypeError, ValueError):
        return 0.0


def fmt_money(x) -> str:
    """تنسيق مبلغ بفواصل الآلاف، دون كسور إن كان صحيحاً."""
    x = _money_num(x)
    return f"{int(x):,}" if x == int(x) else f"{x:,.2f}"


def quotation_pricing(pricing) -> tuple:
    """يحسب الإجمالي الفرعي لكل صفّ تسعير (العدد × سعر الفرد) والإجمالي الكلي.

    كل صفّ: ``[نوع الشخص، نوع الغرفة، العدد، سعر الفرد]``. يعيد
    ``(rows, total)`` حيث كل عنصر في ``rows`` هو
    ``(نوع الشخص، نوع الغرفة، العدد، سعر الفرد، الإجمالي)``."""
    rows, total = [], 0.0
    for row in pricing or []:
        ptype, rtype, count, price = (list(row) + ["", "", "", ""])[:4]
        sub = _money_num(count) * _money_num(price)
        total += sub
        rows.append((str(ptype or ""), str(rtype or ""), str(count or ""),
                     str(price or ""), sub))
    return rows, total


def build_quotation_data(rec, *, trip=None, company=None, number: str = "",
                         date_str: str = "", pax: str = "",
                         lang: str = "ar") -> dict:
    """يبني بيانات عرض السعر (قاموس قابل للتعديل) من بيانات البرنامج/المعتمر،
    على غرار نموذج العرض المعتمد. يُمرَّر إلى :func:`export_umrah_quotation_pdf`
    عبر الوسيط ``data``. ``lang`` يحدّد لغة القيَم الافتراضية (ar/en)."""
    from datetime import timedelta

    from .umrah import _parse_date

    company_info(company)
    if not date_str:
        date_str = date.today().isoformat()
    en = lang == "en"

    def T(ar_txt, en_txt):
        return en_txt if en else ar_txt

    room = str(getattr(rec, "room_type", "") or "ثنائي")
    if room not in QUOTE_ROOM_TYPES:
        room = "ثنائي"
    room = _qtr(room, "rooms", en)

    # الإقامات: [المدينة، الليالي، الفندق، نوع الغرفة، عدد الغرف، الإطلالة،
    #            الوجبات، الدخول، المغادرة] — الدخول/المغادرة محسوبان مبدئياً
    stays: list[list[str]] = []
    _cur = _parse_date(getattr(trip, "depart_date", "")) if trip else None
    view0 = _qtr("غير مطلّة", "views", en)
    meals0 = _qtr("إفطار", "meals", en)
    for label, hotel_f, nights_f in (
            ("المدينة المنوّرة", "madinah_hotel", "madinah_nights"),
            ("مكة المكرّمة", "makkah_hotel", "makkah_nights")):
        hotel = str(getattr(trip, hotel_f, "") or "") if trip else ""
        if not hotel:
            continue
        try:
            n = int(float(str(getattr(trip, nights_f, "") or "").strip() or 0))
        except ValueError:
            n = 0
        cin = _cur.isoformat() if _cur else ""
        cout = (_cur + timedelta(days=n)).isoformat() if (_cur and n) else ""
        stays.append([_qtr(label, "cities", en), str(n or ""),
                      _qtr(hotel, "hotels", en), room, "1",
                      view0, meals0, cin, cout])
        if _cur and n:
            _cur = _cur + timedelta(days=n)

    # الطيران: رحلتا الذهاب والعودة من بيانات البرنامج (المطارات تُملأ يدوياً)
    airline = str(getattr(trip, "airline", "") or "") if trip else ""
    if airline not in QUOTE_CARRIERS:
        airline = ""
    dep = str(getattr(trip, "depart_date", "") or "") if trip else ""
    ret = str(getattr(trip, "return_date", "") or "") if trip else ""
    flights = [
        [dep, airline, str(getattr(trip, "out_depart_time", "") or ""), "",
         str(getattr(trip, "out_arrive_time", "") or ""), ""],
        [ret, airline, str(getattr(trip, "ret_depart_time", "") or ""), "",
         str(getattr(trip, "ret_arrive_time", "") or ""), ""],
    ] if trip else []

    car = str(getattr(trip, "transport", "") or "") if trip else ""
    car_type = next((c for c in QUOTE_CAR_TYPES if c.lower() in car.lower()),
                    "GMC")
    transport_lines = [[dep, _qtr("مطار جدة", "locations", en),
                        _qtr("فندق مكة", "locations", en)],
                       ["", _qtr("فندق مكة", "locations", en),
                        _qtr("فندق المدينة", "locations", en)],
                       [ret, _qtr("فندق المدينة", "locations", en),
                        _qtr("مطار المدينة", "locations", en)]]

    # التسعير الافتراضي: صفّ لكل فئة ضيوف، بسعر الفرد حسب نوع الغرفة
    def _tprice(field):
        return str(getattr(trip, field, "") or "") if trip else ""

    room_price = {"مفرد": _tprice("price_single"), "ثنائي": _tprice("price_double"),
                  "ثلاثي": _tprice("price_triple"), "رباعي": _tprice("price_quad")}
    price_by_type = {"أطفال": _tprice("price_child"),
                     "رضّع": _tprice("price_infant")}
    _def_price = (price_by_type.get("كبار") or room_price.get("ثنائي")
                  or _tprice("price_double"))
    guests_default = [["2", _qtr("كبار", "persons", en)]]
    # كل صفّ تسعير: [نوع الشخص، نوع الغرفة، العدد، سعر الفرد]
    pricing = [[_qtr("كبار", "persons", en), room, "2", _def_price]]

    return {
        "lang": lang,
        "number": str(number or ""),
        "date": date_str,
        "title": T("عرض سعر رحلة عمرة", "Umrah Trip Quotation"),
        "greeting": T(QUOTE_GREETING, "Greetings,"),
        # توجيه العرض باسم الضيف (فارغ = بدون توجيه) + اللقب (السيد/السيدة)
        "addressed_to": str(getattr(rec, "full_name_ar", "") or ""),
        "addressed_title": T("السيد", "Mr."),
        # الضيوف: كل عنصر [العدد، النوع]
        "guests": guests_default,
        "period_from": dep,
        "period_to": ret,
        # كل صف: [المدينة، الليالي، الفندق، نوع الغرفة، عدد الغرف، الإطلالة، الوجبات]
        "stays": stays,
        "flight_class": _qtr("سياحية", "classes", en),
        # كل صف: [اليوم، الناقل، الإقلاع، من، الوصول، إلى]
        "flights": flights,
        "car_type": car_type,
        "car_model": "2025",
        "car_count": "1",
        # كل بند تنقّل: [التاريخ، من، إلى]
        "transport_lines": transport_lines,
        # قطار الحرمين: قائمة بنود، كل بند
        # [التذاكر، الدرجة، من، إلى، التاريخ، الإقلاع، الوصول]
        "trains": [],
        # التأشيرات: العدد والنوع (سياحية/عمرة) — يُبنى منهما نصّ البند
        "visas": "",
        "visa_count": "",
        "visa_type": _qtr("عمرة", "visa", en),
        # التسعير: [[نوع الشخص، نوع الغرفة، العدد، سعر الفرد], …] والإجمالي تلقائي
        "pricing": pricing,
        "currency": T("درهم", "AED"),
        # صلاحية العرض الافتراضية: ٣ أيام من تاريخ الإصدار (قابلة للتعديل)
        "validity": (_parse_date(date_str) + timedelta(days=3)).isoformat()
        if _parse_date(date_str) else "",
        "validity_time": "",
        "note": "",
        "closing": T(QUOTE_CLOSING,
                     "We hope our programs meet your satisfaction; awaiting "
                     "your kind reply."),
        # عرض/إخفاء بنود العرض
        "show_stays": True,
        "show_flights": True,
        "show_transport": True,
        "show_costs": True,
        # الخانة القابلة للتعديل (الصفة/الاسم/الهاتف) — تبدأ فارغة ليملأها المستخدم
        "gm_title": "",
        "gm_name": "",
        "gm_phone": "",
        # الخانة الثابتة (مدير المكتب) تُؤخذ من ثوابت المكتب في المستند
        "office_title": QUOTE_OFFICE_TITLE,
        "office_name": QUOTE_OFFICE_NAME,
        "office_phone": QUOTE_OFFICE_PHONE,
    }


def export_umrah_quotation_pdf(rec, path: str | Path, *, trip=None, company=None,
                               number: str = "", date_str: str = "",
                               pax: str = "", lang: str = "ar",
                               data: dict | None = None) -> Path:
    """عرض سعر رحلة عمرة (Quotation) على صفحة A4 عمودية، بشعارَي الحملة،
    التحيّة، تفاصيل الإقامة والطيران والمواصلات، والتكلفة وصلاحية العرض،
    وتوقيعَي المدير العام ومدير المكتب — يدعم العربية والإنجليزية (``lang``).

    عند تمرير ``data`` (من :func:`build_quotation_data`، وقد عُدّل يدوياً) يُبنى
    المستند من محتواه؛ وإلّا يُبنى تلقائياً من ``rec`` و``trip``."""
    _register_fonts()
    path = Path(path)
    if data is None:
        data = build_quotation_data(rec, trip=trip, company=company,
                                    number=number, date_str=date_str, pax=pax,
                                    lang=lang)
    number = str(data.get("number") or "")
    date_str = str(data.get("date") or date.today().isoformat())
    L = str(data.get("lang") or "ar") == "en"    # إنجليزي ⇒ LTR
    ALN = 0 if L else 2

    def T(ar_txt, en_txt):
        return en_txt if L else ar_txt

    def rev(seq):
        return list(seq) if L else list(reversed(seq))

    co = company_info(company)
    doc = SimpleDocTemplate(
        str(path), pagesize=A4, rightMargin=9 * mm, leftMargin=9 * mm,
        topMargin=9 * mm, bottomMargin=14 * mm, title="عرض سعر",
        author="ميسّر العمرة")
    st = _styles()
    story = []
    W = doc.width
    _DEEP = colors.HexColor("#6E543A")

    def _logo_cell(pathobj, h):
        if not pathobj.is_file():
            return ""
        try:
            iw, ih = ImageReader(str(pathobj)).getSize()
            return RLImage(str(pathobj), width=h * iw / ih, height=h)
        except Exception:
            return ""

    al = _logo_cell(_LOGO_PATH, 52)
    nv = _logo_cell(_NIRVANA_PATH, 62)
    header = Table([[nv, al]], colWidths=[W / 2, W / 2])
    header.setStyle(TableStyle([
        ("ALIGN", (0, 0), (0, 0), "LEFT"), ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header)
    story.append(Spacer(1, 6))

    lbl = ParagraphStyle("qlbl", parent=st["cell"], fontName=_FONT_BOLD,
                         textColor=_ACCENT, alignment=ALN, fontSize=9.5)
    val = ParagraphStyle("qval", parent=st["cell"], alignment=ALN, fontSize=9.5,
                         leading=14)
    val_l = ParagraphStyle("qvall", parent=val, alignment=0)     # يسار دائماً
    val_r = ParagraphStyle("qvalr", parent=val, alignment=2)     # يمين دائماً

    # رقم العرض (يسار) والتاريخ (يمين) على الطرفين — التاريخ بصيغة يوم/شهر/سنة
    date_lbl = T("التاريخ", "Date")
    meta = Table([[_ar_para(ltr(number), val_l, W * 0.5 - 6),
                   _ar_para(f"{date_lbl}: {ltr(_dmy(date_str))}", val_r,
                            W * 0.5 - 6)]],
                 colWidths=[W * 0.5, W * 0.5])
    meta.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(meta)
    story.append(_ar_para(str(data.get("greeting") or ""), val, W - 8))
    # توجيه العرض باسم الضيف (اختياري) مع اللقب (السيد/السيدة أو Mr./Mrs.)
    addressed = str(data.get("addressed_to") or "").strip()
    if addressed:
        atitle = str(data.get("addressed_title") or T("السيد", "Mr.")).strip()
        if L:
            atxt = f"Attention: {atitle} {addressed},"
        else:
            respect = "المحترمة" if atitle in ("السيدة", "الآنسة") \
                else "المحترم"
            atxt = f"عناية {atitle}/ {addressed} {respect}،"
        story.append(_ar_para(
            atxt, ParagraphStyle("qaddr", parent=val, fontName=_FONT_BOLD,
                                 textColor=_DEEP), W - 8))
    story.append(Spacer(1, 6))

    # شريط العنوان بلون الهوية
    band = Table([[Paragraph(ar(str(data.get("title") or "عرض سعر")),
                             ParagraphStyle("qbt", fontName=_FONT_BOLD,
                                            fontSize=16, alignment=1,
                                            textColor=colors.white,
                                            leading=20))]], colWidths=[W])
    band.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _ACCENT),
        ("LINEABOVE", (0, 0), (-1, 0), 2.0, _DEEP),
        ("LINEBELOW", (0, -1), (-1, -1), 2.0, _DEEP),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(band)
    story.append(Spacer(1, 8))

    def qpara(text, style, maxw):
        """للنصّ الإنجليزي الخالص (بلا حروف عربية) نبني فقرة LTR مباشرة بلا
        إعادة تشكيل/bidi — فلا يمكن أن تنعكس التواريخ أو الأرقام مطلقاً."""
        s = str(text)
        if L and not any("؀" <= c <= "ۿ" for c in s):
            s = (s.replace("‎", "").replace("‏", "")
                 .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
            return Paragraph(s, style)
        return _ar_para(text, style, maxw)

    def bullet(text, bold=False):
        style = ParagraphStyle("qbul", parent=val, fontName=(
            _FONT_BOLD if bold else _FONT), alignment=ALN)
        return qpara("• " + text, style, W - 16)

    def section(title):
        p = qpara(title, ParagraphStyle(
            "qsec", fontName=_FONT_BOLD, fontSize=11, alignment=ALN,
            textColor=_DEEP, leading=15), W - 12)
        # علامة لونية صغيرة قبل العنوان (على جهة بداية القراءة)
        mark = Table([[""]], colWidths=[7], rowHeights=[12])
        mark.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), _ACCENT),
            ("LINEBEFORE", (0, 0), (0, -1), 2, _DEEP),
        ]))
        cells = rev([mark, p])
        t = Table([cells], colWidths=rev([12, W - 12]))
        t.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, -1), 1.0, _ACCENT),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        return t

    def _cells(values, style, av):
        vv = rev(values)
        return [qpara(v, style, av[i] - 3) for i, v in enumerate(vv)]

    def data_table(heads, weights, rows_vals):
        vw = rev(weights)
        scale = W / sum(vw)
        cw = [w * scale for w in vw]
        av = [w - 9 for w in cw]
        table = [_cells(heads, st["head"], av)]
        for row in rows_vals:
            vals = [str(x if x not in (None, "") else "—") for x in row]
            table.append(_cells(vals, st["cell"], av))
        if len(table) == 1:
            table.append(_cells([""] * len(heads), st["cell"], av))
        t = Table(table, colWidths=cw)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _ACCENT),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.8, _ACCENT),
            ("INNERGRID", (0, 0), (-1, -1), 0.4, _GRID),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ALT_ROW]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("ROUNDEDCORNERS", [4, 4, 4, 4]),          # زوايا ناعمة
        ]))
        return t

    # الضيوف والفترة — في بطاقة معلومات أنيقة
    sep = ", " if L else "، "
    guests_txt = sep.join(
        f"{ltr(str(c).strip())} {_qtr(str(t).strip(), 'persons', L)}"
        for c, t in [g[:2] + [""] * (2 - len(g))
                     for g in data.get("guests", [])]
        if str(c).strip() or str(t).strip())
    pf, pt = str(data.get("period_from") or ""), str(data.get("period_to") or "")
    info_st = ParagraphStyle("qinfo", parent=val, fontName=_FONT_BOLD,
                             fontSize=10, leading=15, alignment=ALN)
    info_lines = []
    if guests_txt:
        info_lines.append(qpara(f"{T('الضيوف', 'Guests')}: {guests_txt}",
                                info_st, W - 24))
    if pf or pt:
        ptxt = (f"Period: from {ltr(_dmy(pf))} to {ltr(_dmy(pt))}" if L
                else f"الفترة: من {ltr(_dmy(pf))} إلى {ltr(_dmy(pt))}")
        info_lines.append(qpara(ptxt, info_st, W - 24))
    if info_lines:
        card = Table([[info_lines]], colWidths=[W])
        card.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FBF8F3")),
            ("BOX", (0, 0), (-1, -1), 0.6, _GRID),
            # الشريط اللوني على جهة بداية القراءة (يمين العربي/يسار الإنجليزي)
            ("LINEAFTER" if not L else "LINEBEFORE", (0, 0), (0, -1), 3,
             _ACCENT),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("ROUNDEDCORNERS", [5, 5, 5, 5]),
        ]))
        story.append(card)
    story.append(Spacer(1, 8))

    # الإقامة — مع تاريخ الإقامة (من – إلى) لكل مدينة (يدوي أو محسوب من الفترة)
    from datetime import timedelta as _td

    from .umrah import _parse_date as _pd
    stays_raw = [list(r)[:9] + [""] * (9 - len(r)) for r in data.get("stays", [])
                 if any(str(x or "").strip() for x in r)]
    if stays_raw and data.get("show_stays", True):
        cur = _pd(pf)

        def _sh(iso):
            d = _pd(iso)
            return f"{d.day:02d}/{d.month:02d}" if d else ""      # يوم/شهر

        disp = []
        for row in stays_raw:
            city, nights, hotel, room, rooms, view, meals, cin, cout = row[:9]
            try:
                n = int(float(str(nights).strip() or 0))
            except ValueError:
                n = 0
            # التواريخ اليدوية إن وُجدت، وإلّا تُحسب تسلسلياً من الفترة
            if not cin and cur:
                cin = cur.isoformat()
            if not cout and cur and n:
                cout = (cur + _td(days=n)).isoformat()
            # المدى «الدخول – المغادرة» بصيغة يوم/شهر: الدخول أولاً في النصّ
            # فيظهر في جهة بداية القراءة (يمين العربي/يسار الإنجليزي)
            if cin or cout:
                core = f"{_sh(cin)} – {_sh(cout)}"
                rng = ltr(core) if L else core
            else:
                rng = ""
            nxt = _pd(cout)
            cur = nxt or (cur + _td(days=n) if (cur and n) else cur)
            disp.append([_qtr(city, "cities", L), rng, nights,
                         _qtr(hotel, "hotels", L), _qtr(room, "rooms", L), rooms,
                         _qtr(view, "views", L), _qtr(meals, "meals", L)])
        heads = ([T("المدينة", "City"), T("من – إلى", "From – To"),
                  T("الليالي", "Nights"), T("الفندق", "Hotel"),
                  T("نوع الغرفة", "Room Type"), T("عدد الغرف", "Rooms"),
                  T("الإطلالة", "View"), T("الوجبات", "Meals")])
        story.append(section(T("تفاصيل الإقامة", "Accommodation")))
        story.append(Spacer(1, 4))
        story.append(data_table(heads, [54, 66, 52, 98, 74, 44, 52, 48], disp))
        story.append(Spacer(1, 8))

    # الطيران
    if data.get("show_flights", True):
        story.append(section(T("الطيران", "Flights")))
        story.append(Spacer(1, 3))
        fclass = str(data.get("flight_class") or "")
        if fclass:
            story.append(bullet(f"{T('الدرجة', 'Class')}: "
                                f"{_qtr(fclass, 'classes', L)}"))
            story.append(Spacer(1, 3))
        fheads = ([T("اليوم", "Day"), T("الناقل", "Carrier"),
                   T("الإقلاع", "Departure"), T("من", "From"),
                   T("الوصول", "Arrival"), T("إلى", "To")])
        flights = []
        for r in data.get("flights", []):
            if not any(str(x or "").strip() for x in r):
                continue
            day, carrier, dep_t, frm, arr_t, to = (list(r)[:6] +
                                                   [""] * (6 - len(r)))[:6]
            flights.append([ltr(_dmy(day)), _qtr(carrier, "carriers", L),
                            ltr(dep_t), _qtr(frm, "airports", L), ltr(arr_t),
                            _qtr(to, "airports", L)])
        story.append(data_table(fheads, [70, 70, 50, 60, 50, 60], flights))
        story.append(Spacer(1, 8))

    # المواصلات والتنقّلات (سيارة + بنود تنقّل)
    show_tr = data.get("show_transport", True)
    if show_tr:
        story.append(section(T("المواصلات والتنقّلات", "Transportation")))
        story.append(Spacer(1, 3))
        ctype = str(data.get("car_type") or "")
        cmodel = str(data.get("car_model") or "")
        ccount = str(data.get("car_count") or "")
        if ctype or ccount:
            if L:
                note = f"{ltr(ccount or '1')} car(s) ({ctype})"
                if cmodel:
                    note += f" model {ltr(cmodel)}"
            else:
                note = f"عدد ({ltr(ccount or '1')}) سيارة ({ctype})"
                if cmodel:
                    note += f" موديل {ltr(cmodel)}"
            story.append(bullet(note, bold=True))
        for line in data.get("transport_lines", []):
            row = list(line)[:3] + [""] * (3 - len(line)) if isinstance(
                line, (list, tuple)) else ["", "", str(line)]
            d, frm, to = (str(x or "").strip() for x in row)
            if not (d or frm or to):
                continue
            parts = []
            if d:
                parts.append(f"{T('يوم', 'Day')} {ltr(_dmy(d))}")
            if frm:
                parts.append(f"{T('من', 'from')} {_qtr(frm, 'locations', L)}")
            if to:
                parts.append(f"{T('إلى', 'to')} {_qtr(to, 'locations', L)}")
            story.append(qpara("– " + " ".join(parts), ParagraphStyle(
                "qsub", parent=val, fontSize=9, leading=13, alignment=ALN),
                W - 24))
        story.append(Spacer(1, 8))

    # قطار الحرمين — جدول ببنود متعددة
    trains = [t for t in data.get("trains", [])
              if any(str(x or "").strip() for x in t)]
    if not trains and str(data.get("train_tickets") or "").strip():
        trains = [[data.get("train_tickets"), data.get("train_class"),
                   data.get("train_from"), data.get("train_to"),
                   data.get("train_date"), data.get("train_dep"),
                   data.get("train_arr")]]
    trains = [t for t in trains if str((list(t) + [""])[0] or "").strip()]
    if trains:
        story.append(section(T("قطار الحرمين", "Haramain Train")))
        story.append(Spacer(1, 4))
        theads = ([T("التذاكر", "Tickets"), T("الدرجة", "Class"),
                   T("من", "From"), T("إلى", "To"), T("التاريخ", "Date"),
                   T("الإقلاع", "Departure"), T("الوصول", "Arrival")])
        trows = []
        for tr in trains:
            tk_n, tc, tf, tt, tdate, tdep, tarr = (
                [str(x or "").strip() for x in list(tr)[:7]] + [""] * 7)[:7]
            trows.append([tk_n, _qtr(tc, "classes", L),
                          _qtr(tf, "airports", L), _qtr(tt, "airports", L),
                          ltr(_dmy(tdate)), ltr(tdep), ltr(tarr)])
        story.append(data_table(theads, [40, 58, 54, 54, 60, 48, 48], trows))
        story.append(Spacer(1, 8))

    # التأشيرات
    visas = str(data.get("visas") or "").strip()
    vcount = str(data.get("visa_count") or "").strip()
    vtype = str(data.get("visa_type") or "").strip()
    if L and vcount:      # أعِد بناء نصّ التأشيرات بالإنجليزية
        visas = f"{ltr(vcount)} {_qtr(vtype, 'visa', L)} visa(s)"
    if visas:
        story.append(bullet(f"{T('التأشيرات', 'Visas')}: {visas}"))
        story.append(Spacer(1, 6))

    # التكلفة — جدول تسعير: العدد × سعر الفرد لكل فئة/غرفة، والإجمالي تلقائي
    if data.get("show_costs", True):
        story.append(section(T("التكلفة", "Cost")))
        story.append(Spacer(1, 4))
        cur = str(data.get("currency") or T("درهم", "AED"))
        prows, grand = quotation_pricing(data.get("pricing", []))
        prows = [r for r in prows if r[2].strip() or r[3].strip()
                 or r[0].strip() or r[1].strip()]
        if prows:
            heads = [T("نوع الشخص", "Person"), T("نوع الغرفة", "Room Type"),
                     T("العدد", "Count"), T("سعر الفرد", "Unit Price"),
                     f"{T('الإجمالي', 'Total')} ({cur})"]
            rows_vals = []
            for ptype, rtype, count, price, sub in prows:
                rows_vals.append([_qtr(ptype, "persons", L) or "—",
                                  _qtr(rtype, "rooms", L) or "—", count or "—",
                                  fmt_money(price) if price.strip() else "—",
                                  fmt_money(sub)])
            story.append(data_table(heads, [70, 90, 44, 66, 78], rows_vals))
            story.append(Spacer(1, 3))
        # صفّ الإجمالي الكلي (محسوب تلقائياً)
        tot = Table([[_ar_para(f"{fmt_money(grand)} {cur}", ParagraphStyle(
            "qtv", parent=val, fontName=_FONT_BOLD, alignment=1, fontSize=12),
            W * 0.5 - 10),
            _ar_para(T("التكلفة الإجمالية", "Total Cost"), ParagraphStyle(
                "qtk", parent=val, fontName=_FONT_BOLD, alignment=1,
                fontSize=12, textColor=colors.white), W * 0.5 - 10)]],
            colWidths=[W * 0.5, W * 0.5])
        tot.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.8, _ACCENT),
            ("INNERGRID", (0, 0), (-1, -1), 0.4, _GRID),
            ("BACKGROUND", (1, 0), (1, -1), _ACCENT),
            ("TEXTCOLOR", (1, 0), (1, -1), colors.white),
            ("BACKGROUND", (0, 0), (0, -1), _ALT_ROW),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("ROUNDEDCORNERS", [6, 6, 6, 6]),
        ]))
        story.append(tot)
        story.append(Spacer(1, 4))
    validity = str(data.get("validity") or "")
    if validity:
        vtime = str(data.get("validity_time") or "").strip()
        _vm = _re_iso.match(validity.strip())
        vdisp = (f"{_vm.group(3)}/{_vm.group(2)}/{_vm.group(1)}"
                 if _vm else validity)
        if L:
            vtxt = f"This offer is valid until {ltr(vdisp)}"
            if vtime:
                vtxt += f" at {ltr(vtime)}"
        else:
            vtxt = f"هذا العرض صالح لغاية يوم {ltr(vdisp)}"
            if vtime:
                vtxt += f" الساعة {ltr(vtime)}"
        vpar = qpara(vtxt + ".", ParagraphStyle(
            "qvld", parent=val, fontName=_FONT_BOLD, fontSize=10.5,
            alignment=ALN, textColor=colors.HexColor("#7A5C00")), W - 16)
        # تظليل أصفر ليبرز للضيف
        vbox = Table([[vpar]], colWidths=[W])
        vbox.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF3B0")),
            ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#E0B400")),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(vbox)
    story.append(Spacer(1, 6))

    # ملاحظات (اختيارية)
    note = str(data.get("note") or "").strip()
    if note:
        story.append(section(T("ملاحظات", "Notes")))
        story.append(Spacer(1, 3))
        story.append(qpara(note, ParagraphStyle("qnote", parent=val,
                                                fontSize=9.5, leading=14,
                                                alignment=ALN), W - 8))
        story.append(Spacer(1, 8))

    # بند شروط مختصر (ثابت، بلغة العرض) — قبل عبارة الختام
    if data.get("show_terms", True):
        qterms = QUOTE_TERMS_EN if L else QUOTE_TERMS
        story.append(section(T("شروط العرض", "Offer Terms")))
        story.append(Spacer(1, 3))
        tstyle = ParagraphStyle("qterm", parent=val, fontSize=8, leading=11,
                                alignment=ALN, spaceAfter=2)
        tflow = [qpara(f"{i}. {t}", tstyle, W - 18)
                 for i, t in enumerate(qterms, 1)]
        tbox = Table([[tflow]], colWidths=[W])
        tbox.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FBF8F3")),
            ("BOX", (0, 0), (-1, -1), 0.6, _GRID),
            ("LEFTPADDING", (0, 0), (-1, -1), 9),
            ("RIGHTPADDING", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("ROUNDEDCORNERS", [4, 4, 4, 4]),
        ]))
        story.append(tbox)
        story.append(Spacer(1, 8))

    closing = str(data.get("closing") or "")
    if closing:
        story.append(qpara(closing, val, W - 8))
        story.append(Spacer(1, 6))

    # زخرفة فاصلة أنيقة قبل التوقيعات (خطّان بمعيّن في الوسط)
    from reportlab.graphics.shapes import Drawing, Line, Polygon
    flo = Drawing(W, 14)
    cy = 7
    flo.add(Line(W * 0.18, cy, W / 2 - 10, cy, strokeColor=_ACCENT,
                 strokeWidth=0.8))
    flo.add(Line(W / 2 + 10, cy, W * 0.82, cy, strokeColor=_ACCENT,
                 strokeWidth=0.8))
    flo.add(Polygon([W / 2, cy + 5, W / 2 + 6, cy, W / 2, cy - 5, W / 2 - 6, cy],
                    fillColor=_ACCENT, strokeColor=_DEEP, strokeWidth=0.5))
    flo.add(Polygon([W / 2 - 14, cy + 3, W / 2 - 11, cy, W / 2 - 14, cy - 3,
                     W / 2 - 17, cy], fillColor=_DEEP, strokeWidth=0))
    flo.add(Polygon([W / 2 + 14, cy + 3, W / 2 + 17, cy, W / 2 + 14, cy - 3,
                     W / 2 + 11, cy], fillColor=_DEEP, strokeWidth=0))
    story.append(flo)
    story.append(Spacer(1, 8))

    # التوقيعات: خانة قابلة للتعديل (يمين) وخانة المكتب الثابتة (يسار)
    sig_t = ParagraphStyle("qst", parent=lbl, alignment=1, fontSize=10)
    sig_n = ParagraphStyle("qsn", parent=val, alignment=1, fontName=_FONT_BOLD)
    sig_p = ParagraphStyle("qsp", parent=val, alignment=1, fontSize=9,
                           textColor=colors.HexColor("#555555"))

    def sig_box(title, name, phone):
        cells = [[_ar_para(str(title or ""), sig_t, W * 0.5 - 12)],
                 [_ar_para(str(name or ""), sig_n, W * 0.5 - 12)]]
        if str(phone or "").strip():
            cells.append([_ar_para(ltr(str(phone)), sig_p, W * 0.5 - 12)])
        tb = Table(cells, colWidths=[W * 0.5])
        tb.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"),
                                ("TOPPADDING", (0, 0), (-1, -1), 2)]))
        return tb

    gm = sig_box(data.get("gm_title"), data.get("gm_name"),
                 data.get("gm_phone"))
    office = sig_box(_qtr(QUOTE_OFFICE_TITLE, "office", L),
                     _qtr(QUOTE_OFFICE_NAME, "office", L), QUOTE_OFFICE_PHONE)
    sig = Table([[office, gm]], colWidths=[W * 0.5, W * 0.5])
    sig.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEABOVE", (0, 0), (-1, 0), 0.4, _GRID),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(sig)

    foot = T("عرض سعر", "Quotation")

    def _bg(canvas, d):
        canvas.saveState()
        # إطار زخرفيّ مزدوج أنيق بلون الهوية قرب حواف الصفحة
        canvas.setStrokeColor(_ACCENT)
        canvas.setLineWidth(1.3)
        m1 = 6 * mm
        canvas.roundRect(m1, m1, A4[0] - 2 * m1, A4[1] - 2 * m1, 10,
                         stroke=1, fill=0)
        canvas.setLineWidth(0.4)
        m2 = 7.4 * mm
        canvas.roundRect(m2, m2, A4[0] - 2 * m2, A4[1] - 2 * m2, 8,
                         stroke=1, fill=0)
        canvas.restoreState()
        # علامة مائية باهتة (شعار المصطفى) في وسط الصفحة
        wm = _faint_logo_reader()
        if wm is not None:
            try:
                iw, ih = wm.getSize()
                ww = doc.width * 0.5
                wh = ww * ih / iw
                canvas.drawImage(
                    wm, (A4[0] - ww) / 2, (A4[1] - wh) / 2, width=ww,
                    height=wh, mask="auto")
            except Exception:
                pass
        _footer_portrait(canvas, d, foot)

    # عرض السعر في صفحة واحدة مهما طال المحتوى (تصغير تلقائي عند الحاجة)
    fitted = KeepInFrame(doc.width, doc.height, story, mode="shrink",
                         hAlign="CENTER", vAlign="TOP")
    doc.build([fitted], onFirstPage=_bg, onLaterPages=_bg)
    return path


def export_group_pricing_pdf(data: dict, path: str | Path, *,
                             company=None) -> Path:
    """مسعّر المجموعات: جدول تفصيل كلفة الفرد وسعر البيع لكل نوع غرفة
    (مفرد/ثنائي/ثلاثي/رباعي/طفل) — بنود الفنادق والوجبات والخدمات والربح."""
    from .umrah import GROUP_ROOM_TYPES, _gnum, group_pricing

    _register_fonts()
    path = Path(path)
    co = company_info(company)
    rows = group_pricing(data)
    cur = str(data.get("currency") or "درهم")

    doc = SimpleDocTemplate(
        str(path), pagesize=A4, rightMargin=12 * mm, leftMargin=12 * mm,
        topMargin=10 * mm, bottomMargin=14 * mm, title="مسعّر المجموعات",
        author="ميسّر العمرة")
    st = _styles()
    W = doc.width
    _DEEP = colors.HexColor("#6E543A")
    story = []

    def logo_cell(pathobj, h):
        if not pathobj.is_file():
            return ""
        try:
            iw, ih = ImageReader(str(pathobj)).getSize()
            return RLImage(str(pathobj), width=h * iw / ih, height=h)
        except Exception:
            return ""

    header = Table([[logo_cell(_NIRVANA_PATH, 60), logo_cell(_LOGO_PATH, 52)]],
                   colWidths=[W / 2, W / 2])
    header.setStyle(TableStyle([
        ("ALIGN", (0, 0), (0, 0), "LEFT"), ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header)
    story.append(Spacer(1, 5))
    title = str(data.get("title") or "").strip() or "مسعّر المجموعات — تفصيل التكلفة"
    band = Table([[Paragraph(ar(title),
                             ParagraphStyle("gt", fontName=_FONT_BOLD,
                                            fontSize=15, alignment=1,
                                            textColor=colors.white,
                                            leading=19))]], colWidths=[W])
    band.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _ACCENT),
        ("LINEABOVE", (0, 0), (-1, 0), 2, _DEEP),
        ("LINEBELOW", (0, -1), (-1, -1), 2, _DEEP),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(band)
    story.append(Spacer(1, 6))

    val = ParagraphStyle("gv", parent=st["cell"], alignment=2, fontSize=9.5,
                         leading=14)

    def line(text, bold=False):
        s = ParagraphStyle("gl", parent=val, fontName=(
            _FONT_BOLD if bold else _FONT))
        return _ar_para("• " + text, s, W - 16)

    pf, pt = str(data.get("period_from") or ""), str(data.get("period_to") or "")
    if pf or pt:
        story.append(line(f"الفترة: من {ltr(pf)} إلى {ltr(pt)}", bold=True))
    inc_md = str(data.get("include_madinah", "1")).strip() not in (
        "", "0", "False", "false")
    mk_h = str(data.get("makkah_hotel") or "")
    md_h = str(data.get("madinah_hotel") or "")
    mk_n = str(data.get("makkah_nights") or "")
    md_n = str(data.get("madinah_nights") or "")
    if mk_h:
        story.append(line(f"مكة المكرّمة: {mk_h} ({ltr(mk_n)} ليالٍ)"))
    if inc_md and md_h:
        story.append(line(f"المدينة المنوّرة: {md_h} ({ltr(md_n)} ليالٍ)"))
    story.append(Spacer(1, 8))

    # جدول التفصيل: البيان + عمود لكل نوع غرفة (المحدَّد فقط)
    types = [r["type"] for r in rows]
    ncol = len(types)
    heads = ["البيان"] + types
    weights = list(reversed([150] + [62] * ncol))
    scale = W / sum(weights)
    colw = [w * scale for w in weights]
    avail = [w - 8 for w in colw]

    def cell_row(vals, style):
        return _ar_cells(list(reversed(vals)), style, avail)

    body = [cell_row(heads, st["head"])]

    def money_row(label, key_or_vals, bold=False, raw=False):
        if isinstance(key_or_vals, str):
            vals = [fmt_money(_gnum(data.get(key_or_vals)))] * ncol
        elif raw:
            vals = [str(v) for v in key_or_vals]
        else:
            vals = [fmt_money(v) for v in key_or_vals]
        cs = ParagraphStyle("gc", parent=st["cell"],
                            fontName=(_FONT_BOLD if bold else _FONT))
        return cell_row([label] + vals, cs)

    body.append(money_row("كلفة مكة للفرد", [r["makkah"] for r in rows]))
    if inc_md:
        body.append(money_row("كلفة المدينة للفرد", [r["madinah"] for r in rows]))
    # البنود: ديناميكية إن وُجدت، وإلّا الحقول الثابتة
    items = data.get("items")
    if items is not None:
        for it in items:
            name, amt = (list(it) + ["", ""])[:2]
            if str(name or "").strip() and _gnum(amt):
                body.append(money_row(str(name), [_gnum(amt)] * ncol))
    else:
        for label, key in (("النقل الداخلي", "transport"),
                           ("نقل المطار", "transport_air"),
                           ("التأشيرة", "visa"), ("تذكرة الطيران", "ticket"),
                           ("ماء وعصير وتمر", "water"), ("الهدايا", "gifts"),
                           ("المصاريف الإدارية", "admin")):
            if _gnum(data.get(key)):
                body.append(money_row(label, key))
    body.append(money_row("التكلفة الصافية", [r["net"] for r in rows],
                          bold=True))
    if any(r["margin"] for r in rows):
        body.append(money_row("الربح والمصاريف", [r["margin"] for r in rows]))
        # النسبة المئوية للربح (تلقائية)
        pct_vals = [ltr(f"{r['margin_pct']:.1f}%") for r in rows]
        body.append(money_row("نسبة الربح %", pct_vals, raw=True))
    body.append(money_row("سعر البيع للفرد", [r["selling"] for r in rows],
                          bold=True))

    t = Table(body, colWidths=colw)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.8, _ACCENT),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, _GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, _ALT_ROW]),
        # صفّ سعر البيع مميّز بلون الهوية
        ("BACKGROUND", (0, -1), (-1, -1), _ACCENT),
        ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROUNDEDCORNERS", [5, 5, 5, 5]),
    ]))
    story.append(t)
    story.append(Spacer(1, 6))
    story.append(_ar_para(f"العملة: {cur}", ParagraphStyle(
        "gcur", parent=val, fontSize=9, textColor=colors.HexColor("#666666")),
        W - 8))

    doc.build(
        story,
        onFirstPage=lambda c, d: _umrah_page(c, d, "مسعّر المجموعات"),
        onLaterPages=lambda c, d: _umrah_page(c, d, "مسعّر المجموعات"))
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
        story.append(Spacer(1, 4))
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


# ============================ برنامج/عرض سعر الحج ============================
# مستند رسمي متعدّد البنود (على غرار «برنامج الحج لكبار الشخصيات»): الفترة،
# مكة والمشاعر، المواصلات، الخدمات، الطيران، الهدايا، وجدول الأسعار حسب الغرفة.
# كل النصوص قابلة للتعديل، ويدعم العربية والإنجليزية (lang).

HAJJ_PROGRAM_DEFAULT: dict = {
    "lang": "ar",
    "title": "برنامج الحج لكبار الشخصيات 1448 هـ - 2027 م",
    "date": "",
    "number": "",
    "addressed_to": "",
    "addressed_title": "السيد",
    "salutation": "السلام عليكم ورحمة الله وبركاته،،",
    "greeting": ("تتقدم أسرة المصطفى للحج والعمرة، لسعادتكم بأطيب وأرق التحيات "
                 "راجين من الله تعالى لكم دوام التوفيق والرفعة، ونستهل هذه الفرصة "
                 "لنتوجه لكم بالشكر والامتنان على الثقة الكبيرة لننال شرف خدمة "
                 "ضيوف الرحمن الكرام في أطهر بقاع الأرض."),
    "intro2": "ولسعادتكم البرنامج الخاص بكم كالتالي:",
    "period_hijri": "من 06 – 14 / ذو الحجة 1448هـ",
    "period_greg": "المُوافق من 2027/05/12 – 2027/05/20 م",
    "makkah_title": "أولاً : مكة المُكرمة",
    "makkah_period": "من 2027/05/12 إلى 2027/05/20 م (08 أيام)",
    "makkah_hotel": "كونراد مكة – فندق خمسة نجوم فاخر مقابل للحرم.",
    "makkah_rooms": "حسب الاختيار.",
    "makkah_meals": ("الإقامة شاملة الوجبات الثلاث طوال الفترة بنظام البوفيه "
                     "المفتوح F.B."),
    "sections": [
        ["ثانياً : منى", [
            "الإقامة في مخيمات بعثة دولة الإمارات العربية المتحدة وذلك في الخيام "
            "المخصصة لدولة الإمارات وتكون خيام خاصة بكبار الشخصيات للرجال والنساء، "
            "وحسب توزيع مكتب شؤون حجاج دولة الإمارات.",
            "تبدأ المشاعر من يوم 08 / ذو الحجة وحتى يوم 12 / ذو الحجة."]],
        ["ثالثاً : عرفات", [
            "فترة المُكوث في عرفات تكون في مخيمات بعثة دولة الإمارات العربية "
            "المتحدة وذلك في الخيام المخصصة لدولة الإمارات، وحسب توزيع مكتب شؤون "
            "حجاج الدولة."]],
        ["رابعاً : مزدلفة", [
            "المكوث في مزدلفة في مخيمات بعثة دولة الإمارات العربية المتحدة، "
            "والاستراحة أو المبيت لقضاء ساعات الليل، ويكون مبيت الضيوف حسب توزيع "
            "مكتب شؤون حجاج دولة الإمارات."]],
        ["خامساً : المواصلات", [
            "جميع التنقلات بواسطة سيارات جيمس حديثة موديل (2027).",
            "سيارة خاصة من المنزل إلى المطار والعكس.",
            "بالإضافة لقطار المشاعر."]],
        ["سادساً : نظام الوجبات وخدمات الطعام", [
            "الوجبات الثلاث بنظام البوفيه المفتوح.",
            "تقدم الوجبات في المشاعر حسب النظام المتبع في المخيمات."]],
        ["سابعاً : الخدمات الخاصة المُقدمة", [
            "واعظ ديني معتمد من الهيئة العامة للشؤون الإسلامية والأوقاف.",
            "البرنامج شامل الهدي.",
            "خدمة مسافر بلا حقيبة في الذهاب والعودة.",
            "خدمة الأمن على مدار الساعة.",
            "الكراسي المتحركة في جميع التنقلات عند الطلب.",
            "يُرافق الحملة طبيب خاص، وتوجد عيادة خاصة مجهزة بالمستلزمات الضرورية.",
            "في المُخيم، والفندق خدمة الشاي والقهوة والمرطبات والعصائر والمياه "
            "المعدنية إضافةً إلى أجود أنواع التمور.",
            "وجود كادر إداري مرافق مُحترف، مُدرب على أعلى درجات التعاون، لخدمة "
            "الضيوف على مدار الساعة."]],
        ["تاسعاً : خدمة التنفيذي", [
            "خدمة صالة التنفيذي في مطار جدة في الإستقبال والمغادرة."]],
    ],
    "flights_title": "ثامناً : الطيران",
    "flight_intro": "على متن الخطوط الجوية السعودية من أبوظبي درجة رجال الأعمال،",
    "flights": [
        ["2027/05/12", "SAUDIA", "", "أبوظبي", "", "جدة"],
        ["2027/05/20", "SAUDIA", "", "جدة", "", "أبوظبي"],
    ],
    "gifts_title": "عاشراً : هدايا ومستلزمات الحاج",
    "gifts": [
        "عبوة ماء زمزم سعة 5 ليتر لكل حاج وحسب القوانين.",
        "شنطة السفر وتحتوي على (حزام – إحرام).",
        "شنطة المشاعر وتحتوي على (منشفة الجسم – منشفة اليدين – مجموعة العناية "
        "الشخصية – مروحة – مظلة – كيس الجمرات المعقمة – معدات الراحة – سجادة "
        "الصلاة).",
    ],
    "currency": "درهم",
    "prices_title": "إحدى عشر : الأسعار",
    "prices_caption": "التكلفة للشخص حسب نوع الغرفة",
    "prices": {"single": "185,000", "double": "124,000",
               "triple": "107,000", "quad": "97,000"},
    "notes_title": "مُلاحظات هامة",
    "notes": [
        "يمكن إضافة خدمة رمي الجمرات من نفق كبار الشخصيات عند توفرها وبرسوم "
        "إضافية.",
        "التقويم الهجري هو المُعتمد في البرامج وحجوزات الفنادق، والسفر على "
        "التاريخ الميلادي.",
        "حسب نظام الفنادق والمواصلات تكون المبالغ المدفوعة للبرنامج غير مستردة.",
    ],
    "closing": ("آملين أن تنال برامجنا رضاكم وكريم استحسانكم، وبانتظار ردكم "
                "الكريم،،، وتفضلوا بقبول فائق الاحترام والتقدير ..."),
    "manager_title": "المدير العام",
    "manager": "محمد شعبار",
    "manager_phone": "056 219 2666",
}

HAJJ_PROGRAM_DEFAULT_EN: dict = {
    "lang": "en",
    "title": "Hajj VIP Program 1448 AH - 2027",
    "date": "",
    "number": "",
    "addressed_to": "",
    "addressed_title": "Mr.",
    "salutation": "Peace, mercy and blessings of Allah be upon you,",
    "greeting": ("Al Mustafa Hajj & Umrah is honored to extend to you its "
                 "warmest greetings, wishing you continued success. We seize "
                 "this opportunity to thank you for your great trust, to have "
                 "the honor of serving the guests of the Most Merciful in the "
                 "holiest of places."),
    "intro2": "We are pleased to present your program as follows:",
    "period_hijri": "6 – 14 Dhul-Hijjah 1448 AH",
    "period_greg": "Corresponding to 2027/05/12 – 2027/05/20",
    "makkah_title": "First: Makkah",
    "makkah_period": "2027/05/12 to 2027/05/20 (08 days)",
    "makkah_hotel": "Conrad Makkah – a five-star luxury hotel facing the Haram.",
    "makkah_rooms": "As selected.",
    "makkah_meals": ("Full board including all three meals throughout the stay "
                     "(open buffet, F.B)."),
    "sections": [
        ["Second: Mina", [
            "Accommodation in the UAE mission camps, in tents dedicated to the "
            "UAE — VIP tents for men and women — as per the UAE Hajj Affairs "
            "Office allocation.",
            "The rituals begin on the 8th of Dhul-Hijjah until the 12th."]],
        ["Third: Arafat", [
            "The stay in Arafat is in the UAE mission camps, in tents "
            "dedicated to the UAE, as per the UAE Hajj Affairs Office "
            "allocation."]],
        ["Fourth: Muzdalifah", [
            "Staying in Muzdalifah in the UAE mission camps, resting or "
            "spending the night, as per the UAE Hajj Affairs Office "
            "allocation."]],
        ["Fifth: Transport", [
            "All transfers by modern GMC vehicles (2027 model).",
            "Private car from home to the airport and back.",
            "In addition to the Mashaer train."]],
        ["Sixth: Meals & Catering", [
            "Three meals with an open buffet system.",
            "Meals at the holy sites as per the system followed in the "
            "camps."]],
        ["Seventh: Special Services", [
            "A religious guide approved by the General Authority of Islamic "
            "Affairs and Endowments.",
            "The program includes the Hady (sacrifice).",
            "Baggage-free traveler service on departure and return.",
            "24/7 security service.",
            "Wheelchairs available on all transfers upon request.",
            "A private physician accompanies the campaign, with a private "
            "clinic equipped with essential supplies.",
            "In the camp and hotel: tea, coffee, refreshments, juices and "
            "mineral water, plus the finest dates.",
            "A professional administrative team, trained to the highest "
            "standards, serving guests around the clock."]],
        ["Ninth: Executive Service", [
            "Executive lounge service at Jeddah airport on arrival and "
            "departure."]],
    ],
    "flights_title": "Eighth: Flights",
    "flight_intro": "On board Saudi Arabian Airlines from Abu Dhabi, Business Class,",
    "flights": [
        ["2027/05/12", "SAUDIA", "", "Abu Dhabi", "", "Jeddah"],
        ["2027/05/20", "SAUDIA", "", "Jeddah", "", "Abu Dhabi"],
    ],
    "gifts_title": "Tenth: Pilgrim gifts & essentials",
    "gifts": [
        "A 5-liter Zamzam water container per pilgrim, as per regulations.",
        "Travel bag containing (belt – Ihram).",
        "Mashaer bag containing (body towel – hand towel – personal care set – "
        "fan – umbrella – sterilized pebbles bag – comfort equipment – prayer "
        "mat).",
    ],
    "currency": "AED",
    "prices_title": "Eleventh: Prices",
    "prices_caption": "Cost per person by room type",
    "prices": {"single": "185,000", "double": "124,000",
               "triple": "107,000", "quad": "97,000"},
    "notes_title": "Important Notes",
    "notes": [
        "The Jamarat stoning service via the VIP tunnel can be added when "
        "available for an additional fee.",
        "The Hijri calendar is the reference for programs and hotel bookings; "
        "travel is on the Gregorian date.",
        "As per the hotels and transport system, amounts paid for the program "
        "are non-refundable.",
    ],
    "closing": ("We hope our programs meet your satisfaction, and we look "
                "forward to your kind reply. Please accept our highest respect "
                "and appreciation..."),
    "manager_title": "General Manager",
    "manager": "Mohammed Shabbar",
    "manager_phone": "056 219 2666",
}


def hajj_program_defaults(lang: str = "ar") -> dict:
    """نسخة عميقة من القيم الافتراضية لبرنامج الحج (عربي/إنجليزي)."""
    import copy
    base = HAJJ_PROGRAM_DEFAULT_EN if str(lang) == "en" else HAJJ_PROGRAM_DEFAULT
    return copy.deepcopy(base)


def export_hajj_program_pdf(path, data: dict | None = None) -> Path:
    """يبني «برنامج/عرض سعر الحج» — A4 عمودي، كل النصوص من ``data``، ويدعم
    العربية (RTL) والإنجليزية (LTR) عبر ``data['lang']``."""
    _register_fonts()
    path = Path(path)
    lang = str((data or {}).get("lang") or "ar")
    d = hajj_program_defaults(lang)
    if data:
        d.update({k: v for k, v in data.items() if v is not None})
    L = str(d.get("lang") or "ar") == "en"
    ALN = 0 if L else 2
    st = _styles()
    _DEEP = colors.HexColor("#6E543A")

    def T(ar_txt, en_txt):
        return en_txt if L else ar_txt

    def rev(seq):
        return list(seq) if L else list(reversed(seq))

    doc = SimpleDocTemplate(
        str(path), pagesize=A4, rightMargin=13 * mm, leftMargin=13 * mm,
        topMargin=10 * mm, bottomMargin=15 * mm, title="Hajj Program",
        author="Al Mustafa Hajj & Umrah")
    W = doc.width
    story: list = []

    val = ParagraphStyle("hp_val", parent=st["cell"], alignment=ALN,
                         fontSize=10, leading=15)
    val_r = ParagraphStyle("hp_vr", parent=val, alignment=2)
    val_l = ParagraphStyle("hp_vl", parent=val, alignment=0)

    def P(text, style, maxw):
        s = str(text)
        if L and not any("؀" <= c <= "ۿ" for c in s):
            s = (s.replace("‎", "").replace("‏", "").replace("&", "&amp;")
                 .replace("<", "&lt;").replace(">", "&gt;"))
            return Paragraph(s, style)
        return _ar_para(text, style, maxw)

    def para(text, style=None, maxw=None):
        return P(text, style or val, (maxw if maxw is not None else W - 8))

    def bullet(text, bold=False):
        s = ParagraphStyle("hp_bul", parent=val,
                           fontName=(_FONT_BOLD if bold else _FONT),
                           leading=15)
        return P(("• " if L else "•  ") + str(text), s, W - 20)

    def section(title):
        p = P(title, ParagraphStyle(
            "hp_sec", fontName=_FONT_BOLD, fontSize=12, alignment=ALN,
            textColor=_DEEP, leading=16), W - 14)
        mark = Table([[""]], colWidths=[8], rowHeights=[14])
        mark.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), _ACCENT),
            ("LINEBEFORE", (0, 0), (0, -1), 2, _DEEP)]))
        cells = rev([mark, p])
        t = Table([cells], colWidths=rev([14, W - 14]))
        t.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, -1), 1.0, _ACCENT),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        return t

    def _logo_cell(pathobj, h):
        if not pathobj.is_file():
            return ""
        try:
            iw, ih = ImageReader(str(pathobj)).getSize()
            return RLImage(str(pathobj), width=h * iw / ih, height=h)
        except Exception:
            return ""
    header = Table([[_logo_cell(_NIRVANA_PATH, 58), _logo_cell(_LOGO_PATH, 50)]],
                   colWidths=[W / 2, W / 2])
    header.setStyle(TableStyle([
        ("ALIGN", (0, 0), (0, 0), "LEFT"), ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(header)

    def _ymd(iso):
        try:
            y, m, dd = str(iso).split("-")
            return f"{y}/{int(m):02d}/{int(dd):02d}"
        except Exception:
            return str(iso)
    _doc_date = _ymd(str(d.get("date") or date.today().isoformat()))
    _num = str(d.get("number") or "").strip()
    _numtxt = (f"{T('رقم العرض', 'Quote No.')}: {ltr(_num)}" if _num else "")
    _datetxt = f"{T('التاريخ', 'Date')} : {ltr(_doc_date)}" + T(" م.", "")
    left_cell = _numtxt if not L else _datetxt
    right_cell = _datetxt if not L else _numtxt
    meta = Table([[P(left_cell, val_l, W * 0.5 - 6),
                   P(right_cell, val_r, W * 0.5 - 6)]],
                 colWidths=[W * 0.5, W * 0.5])
    meta.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story.append(meta)
    story.append(Spacer(1, 4))
    story.append(P(d.get("salutation", ""),
                   ParagraphStyle("hp_slm", parent=val, fontName=_FONT_BOLD),
                   W - 8))
    _addr = str(d.get("addressed_to") or "").strip()
    if _addr:
        _atitle = str(d.get("addressed_title") or T("السيد", "Mr.")).strip()
        if L:
            _atxt = f"Attention: {_atitle} {_addr},"
        else:
            _respect = "المحترمة" if _atitle in ("السيدة", "الآنسة") \
                else "المحترم"
            _atxt = f"عناية {_atitle}/ {_addr} {_respect}،"
        story.append(P(_atxt, ParagraphStyle("hp_addr", parent=val,
                                              fontName=_FONT_BOLD,
                                              textColor=_DEEP), W - 8))
    story.append(Spacer(1, 6))

    band = Table([[Paragraph(ar(str(d.get("title") or "")) if not L
                             else str(d.get("title") or ""),
                             ParagraphStyle("hp_bt", fontName=_FONT_BOLD,
                                            fontSize=15, alignment=1,
                                            textColor=colors.white,
                                            leading=20))]], colWidths=[W])
    band.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _ACCENT),
        ("LINEABOVE", (0, 0), (-1, 0), 2.0, _DEEP),
        ("LINEBELOW", (0, -1), (-1, -1), 2.0, _DEEP),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story.append(band)
    story.append(Spacer(1, 8))

    story.append(para(d.get("greeting", "")))
    story.append(Spacer(1, 4))
    story.append(P(d.get("intro2", ""),
                   ParagraphStyle("hp_i2", parent=val, fontName=_FONT_BOLD),
                   W - 8))
    story.append(bullet(f"{T('الفترة', 'Period')} : {d.get('period_hijri','')}"
                        f"، {d.get('period_greg','')}" if not L else
                        f"Period: {d.get('period_hijri','')}, "
                        f"{d.get('period_greg','')}", bold=True))
    story.append(Spacer(1, 6))

    story.append(section(d.get("makkah_title", "")))
    story.append(bullet(f"{T('الفترة', 'Period')} : {d.get('makkah_period','')}"))
    story.append(bullet(f"{T('الفندق', 'Hotel')} : {d.get('makkah_hotel','')}"))
    story.append(bullet(f"{T('الغرف', 'Rooms')} : {d.get('makkah_rooms','')}"))
    story.append(bullet(f"{T('الوجبات', 'Meals')} : {d.get('makkah_meals','')}"))
    story.append(Spacer(1, 4))

    for sec in d.get("sections", []):
        try:
            title, bullets = sec[0], sec[1]
        except Exception:
            continue
        story.append(section(title))
        for b in bullets:
            if str(b).strip():
                story.append(bullet(b))
        story.append(Spacer(1, 4))

    story.append(section(d.get("flights_title", "")))
    story.append(bullet(d.get("flight_intro", ""), bold=True))
    fheads = T(["اليوم", "الناقل", "الإقلاع", "من", "الوصول", "إلى"],
               ["Day", "Carrier", "Departure", "From", "Arrival", "To"])
    fweights = [1.3, 1.2, 1.0, 1.0, 1.0, 1.0]
    fw = rev(fweights)
    scale = W / sum(fw)
    fcw = [x * scale for x in fw]
    fav = [x - 9 for x in fcw]

    def _fcells(values, style):
        vv = rev(values)
        return [P(str(v) if str(v).strip() else "—", style, fav[i] - 3)
                for i, v in enumerate(vv)]
    ftab = [_fcells(fheads, st["head"])]
    for row in d.get("flights", []):
        ftab.append(_fcells((list(row) + [""] * 6)[:6], st["cell"]))
    tflt = Table(ftab, colWidths=fcw)
    tflt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.8, _ACCENT),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, _GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ALT_ROW]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story.append(Spacer(1, 3))
    story.append(tflt)
    story.append(Spacer(1, 6))

    story.append(section(d.get("gifts_title", "")))
    for g in d.get("gifts", []):
        if str(g).strip():
            story.append(bullet(g))
    story.append(Spacer(1, 6))

    story.append(section(d.get("prices_title", "")))
    cur = str(d.get("currency", ""))
    pr = d.get("prices", {})
    pheads = T(["المفردة", "الثنائية", "الثلاثية", "الرباعية"],
               ["Single", "Double", "Triple", "Quad"])
    pvals = [pr.get("single", ""), pr.get("double", ""),
             pr.get("triple", ""), pr.get("quad", "")]
    pcw = [W / 4] * 4
    pav = [W / 4 - 9] * 4

    def _pcells(values, style):
        vv = rev(values)
        return [P(str(v) if str(v).strip() else "—", style, pav[i] - 3)
                for i, v in enumerate(vv)]
    _capt = str(d.get("prices_caption", "")) + (f" ({cur})" if cur else "")
    cap = Table([[Paragraph(ar(_capt) if not L else _capt,
                            ParagraphStyle("hp_cap", fontName=_FONT_BOLD,
                                           fontSize=10, alignment=1,
                                           textColor=colors.white))]],
                colWidths=[W])
    cap.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), _DEEP),
                             ("TOPPADDING", (0, 0), (-1, -1), 5),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    ptab = Table([_pcells(pheads, st["head"]), _pcells(pvals, st["cell"])],
                 colWidths=pcw)
    ptab.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 1), (-1, 1), 13),
        ("FONTNAME", (0, 1), (-1, 1), _FONT_BOLD),
        ("BOX", (0, 0), (-1, -1), 0.8, _ACCENT),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, _ACCENT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#FBF8F3")),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    story.append(Spacer(1, 3))
    story.append(cap)
    story.append(ptab)
    story.append(Spacer(1, 8))

    story.append(section(d.get("notes_title", "")))
    for n in d.get("notes", []):
        if str(n).strip():
            story.append(bullet(n))
    story.append(Spacer(1, 10))

    story.append(P(d.get("closing", ""),
                   ParagraphStyle("hp_cls", parent=val, alignment=1,
                                  fontName=_FONT_BOLD), W - 8))
    story.append(Spacer(1, 16))
    # التوقيع ككتلة متناسقة محاذاة لليسار في أسفل الصفحة
    sig_l = ParagraphStyle("hp_sig", parent=val, alignment=0, leading=16)
    sig_w = W * 0.42
    sig_rows = [[P(d.get("manager_title", ""),
                   ParagraphStyle("hp_sg1", parent=sig_l, fontName=_FONT_BOLD),
                   sig_w - 6)],
                [P(d.get("manager", ""),
                   ParagraphStyle("hp_sg2", parent=sig_l, fontName=_FONT_BOLD,
                                  fontSize=13), sig_w - 6)]]
    if str(d.get("manager_phone", "")).strip():
        sig_rows.append([P(ltr(d.get("manager_phone")),
                           ParagraphStyle("hp_sg3", parent=sig_l), sig_w - 6)])
    sig_inner = Table(sig_rows, colWidths=[sig_w])
    sig_inner.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    # مُزاح قليلاً عن أقصى اليسار (لا يلتصق بالحافة) بعمود فراغ يساري
    _indent = W * 0.12
    sig_tbl = Table([["", sig_inner]], colWidths=[_indent, W - _indent])
    sig_tbl.hAlign = "LEFT"
    sig_tbl.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(sig_tbl)

    _ttl = "Hajj Program" if L else "برنامج الحج"
    doc.build(
        story,
        onFirstPage=lambda c, dd: _umrah_page(c, dd, _ttl),
        onLaterPages=lambda c, dd: _umrah_page(c, dd, _ttl))
    return path

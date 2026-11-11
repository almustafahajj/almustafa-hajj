# -*- coding: utf-8 -*-
"""هوية مستندات العميل (سند القبض، الفاتورة، العقد…): ترويسة رسمية بالشعار وخطّ
ذهبي مزدوج، لوحة عنوان بنقش النجمة الثمانية، تذييل بجهات التواصل، علامة مائية
باهتة، ختم «مدفوع بالكامل»، ومربّعات توقيع — عناصر مشتركة كي تبدو المستندات
كلّها من بيت واحد.

ترسم بـ reportlab مباشرة على الصفحة (canvas) وتُستدعى من :mod:`hajj_app.pdf_io`.
الخطّ العربي هو ما يسجّله ``pdf_io._register_fonts`` (Amiri) لأن reportlab لا
يطبّق تشكيل OpenType للخطوط الحديثة.
"""
from __future__ import annotations

import math
import re

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import Flowable

# ---- الألوان: برونزي العلامة + ذهبي للخطوط والزخرفة + حبر دافئ ----
INK = colors.HexColor("#1F1B16")
BRONZE = colors.HexColor("#8A6E4B")
GOLD = colors.HexColor("#B39257")
GOLD_LT = colors.HexColor("#DCCAA4")
CREAM = colors.HexColor("#FAF6EE")
HAIR = colors.HexColor("#E6DCCB")
MUTED = colors.HexColor("#7B7265")
PAID = colors.HexColor("#2E7D5B")

EF, EFB, EFI = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"
_AR_RE = re.compile(r"[؀-ۿ]")


def _io():
    from . import pdf_io
    pdf_io._register_fonts()
    return pdf_io


def AF() -> str:
    return _io()._FONT


def AFB() -> str:
    return _io()._FONT_BOLD


def has_ar(text) -> bool:
    return bool(_AR_RE.search(str(text or "")))


def vis(text) -> str:
    """النصّ جاهزاً للرسم: عربي ⇐ تشكيل وترتيب، لاتيني كما هو."""
    t = str(text or "")
    return _io().ar(t) if has_ar(t) else t


def font_for(text, bold=False) -> str:
    if has_ar(text):
        return AFB() if bold else AF()
    return EFB if bold else EF


def width(text, size, bold=False) -> float:
    from reportlab.pdfbase import pdfmetrics
    return pdfmetrics.stringWidth(vis(text), font_for(text, bold), size)


def draw(c, x, y, text, size, *, bold=False, color=INK, align="right",
         space=0.0):
    """يرسم نصاً (عربياً أو لاتينياً) بمحاذاة right/left/center عند x."""
    t = vis(text)
    if not t:
        return
    c.setFont(font_for(text, bold), size)
    c.setFillColor(color)
    if align == "right":
        c.drawRightString(x, y, t, charSpace=space)
    elif align == "center":
        c.drawCentredString(x, y, t, charSpace=space)
    else:
        c.drawString(x, y, t, charSpace=space)


def wrap(text, size, maxw, bold=False) -> list:
    """لفّ منطقي للكلمات حسب العرض (قبل تطبيق الاتجاه على كل سطر)."""
    lines = []
    for para in str(text or "").split("\n"):
        cur = ""
        for w in para.split():
            trial = (cur + " " + w).strip()
            if not cur or width(trial, size, bold) <= maxw:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
    return lines


def runs_width(runs, size, sep="  ·  ") -> float:
    if not runs:
        return 0.0
    return sum(width(r, size) for r in runs) + width(sep, size) * (len(runs) - 1)


def draw_runs(c, x_right, y, runs, size, *, color=MUTED, sep="  ·  "):
    """يرسم مقاطع مختلطة (عربي/لاتيني) من اليمين لليسار تفصلها نقطة — فلا
    تُخلط أرقام الهواتف بالنص العربي في ترتيب bidi واحد."""
    x = x_right
    for i, r in enumerate(runs):
        if i:
            draw(c, x, y, sep, size, color=GOLD)
            x -= width(sep, size)
        draw(c, x, y, r, size, color=color)
        x -= width(r, size)


# ---- الزخرفة: النجمة الثمانية (مربّعان متراكبان) ----
def star_path(c, cx, cy, r):
    """مسار نجمة ثمانية: ١٦ رأساً بالتناوب بين نصف قطر خارجي وداخلي."""
    ri = r * math.cos(math.pi / 4) / math.cos(math.pi / 8)
    p = c.beginPath()
    for k in range(16):
        a = math.pi / 2 + k * math.pi / 8
        rr = r if k % 2 == 0 else ri
        x, y = cx + rr * math.cos(a), cy + rr * math.sin(a)
        if k == 0:
            p.moveTo(x, y)
        else:
            p.lineTo(x, y)
    p.close()
    return p


def pattern(c, x, y, w, h, *, step=15.0, alpha=0.22, color=GOLD, lw=0.45):
    """نقش نجوم ثمانية متكرّر داخل مستطيل (يُقصّ عليه)."""
    c.saveState()
    clip = c.beginPath()
    clip.rect(x, y, w, h)
    c.clipPath(clip, stroke=0, fill=0)
    col = colors.Color(color.red, color.green, color.blue, alpha=alpha)
    c.setStrokeColor(col)
    c.setLineWidth(lw)
    row = 0
    yy = y - step
    while yy < y + h + step:
        off = (step / 2) if row % 2 else 0.0
        xx = x - step + off
        while xx < x + w + step:
            c.drawPath(star_path(c, xx, yy, step * 0.36), stroke=1, fill=0)
            xx += step
        yy += step * 0.5
        row += 1
    c.restoreState()


def ornament_rule(c, x0, x1, y, *, color=GOLD):
    """خطّ ذهبي رفيع تتوسّطه نجمة صغيرة."""
    mid = (x0 + x1) / 2
    c.saveState()
    c.setStrokeColor(color)
    c.setLineWidth(0.5)
    c.line(x0, y, mid - 9, y)
    c.line(mid + 9, y, x1, y)
    c.setFillColor(color)
    c.drawPath(star_path(c, mid, y, 4.2), stroke=0, fill=1)
    c.restoreState()


def _logo_reader():
    from reportlab.lib.utils import ImageReader
    pio = _io()
    if not pio._LOGO_PATH.is_file():
        return None
    try:
        return ImageReader(str(pio._LOGO_PATH))
    except Exception:                                  # noqa: BLE001
        return None


def watermark(c, W, H, *, frac=0.40, alpha=0.38, cy=None):
    """الشعار باهتاً في وسط الصفحة خلف المحتوى."""
    wm = _io()._faint_logo_reader()
    if wm is None:
        return
    try:
        iw, ih = wm.getSize()
        ww = W * frac
        hh = ww * ih / iw
        cy = H / 2 - 10 if cy is None else cy
        c.saveState()
        c.setFillAlpha(alpha)
        c.drawImage(wm, (W - ww) / 2, cy - hh / 2, ww, hh,
                    preserveAspectRatio=True, mask="auto")
        c.restoreState()
    except Exception:                                  # noqa: BLE001
        pass


def company(co) -> dict:
    """بيانات الشركة مكتملة بالقيم الافتراضية (قاموس، أو اسم عربي نصّي)."""
    pio = _io()
    if isinstance(co, str):
        co = {"name_ar": co}
    return pio.company_info(co)


def contact_runs(co) -> list:
    out = []
    for k in ("phone", "email", "website", "address"):
        v = str(co.get(k) or "").strip()
        if v:
            out.append(v)
    return out


# ---- الترويسة ----
HEADER_H = 74          # ارتفاع الترويسة (دون الخطّ الذهبي)


def letterhead(c, W, H, *, co, title_ar, title_en="", number="", date_txt="",
               mx=15 * mm, top=11 * mm, panel_w=None) -> float:
    """يرسم الترويسة ويعيد الإحداثي الرأسي أسفلها (حيث يبدأ المحتوى).

    يمين الصفحة: الشعار ثم اسم الشركة بالعربية والإنجليزية وجهات التواصل.
    يسارها: لوحة العنوان بنقش النجمة الثمانية (عنوان المستند ورقمه وتاريخه)."""
    co = company(co)
    yt = H - top
    yb = yt - HEADER_H
    x1 = W - mx

    # الشعار
    lr = _logo_reader()
    lw = 0.0
    if lr is not None:
        iw, ih = lr.getSize()
        lh = HEADER_H - 6
        lw = lh * iw / ih
        if lw > 96:
            lw = 96
            lh = lw * ih / iw
        c.drawImage(lr, x1 - lw, yb + (HEADER_H - lh) / 2, lw, lh,
                    preserveAspectRatio=True, mask="auto")
    # فاصل رأسي ذهبي بين الشعار والاسم
    tx = x1 - lw - (12 if lw else 0)
    if lw:
        c.setStrokeColor(GOLD_LT)
        c.setLineWidth(0.6)
        c.line(tx + 6, yb + 10, tx + 6, yt - 10)
        tx -= 6
    pw = panel_w or (W * 0.30)
    avail = tx - (mx + pw + 14)              # المساحة حتى لوحة العنوان
    name_ar = str(co.get("name_ar") or "")
    name_en = str(co.get("name_en") or "")
    ns = 14.5
    while ns > 10 and width(name_ar, ns, bold=True) > avail:
        ns -= 0.5
    draw(c, tx, yt - 22, name_ar, ns, bold=True, color=INK)
    if name_en:
        draw(c, tx, yt - 35, name_en.upper(), 7.2, bold=True, color=GOLD,
             space=1.3)
    # جهات التواصل: تُرصّ في أسطر حسب المساحة المتاحة (حتى ثلاثة)
    runs = [str(co.get(k) or "").strip() for k in ("phone", "email")]
    trn = str(co.get("trn") or "").strip()
    runs += [f"TRN {trn}" if trn else "",
             str(co.get("address") or "").strip(),
             str(co.get("website") or "").strip()]
    lines, cur = [], []
    for r in (x for x in runs if x):
        if cur and runs_width(cur + [r], 8) > avail:
            lines.append(cur)
            cur = []
        cur.append(r)
    if cur:
        lines.append(cur)
    ly = yt - 48
    for row in lines[:3]:
        draw_runs(c, tx, ly, row, 8)
        ly -= 11

    # لوحة العنوان
    px, py, ph = mx, yb, HEADER_H
    c.saveState()
    c.setFillColor(CREAM)
    c.setStrokeColor(GOLD_LT)
    c.setLineWidth(0.6)
    c.roundRect(px, py, pw, ph, 7, stroke=1, fill=1)
    clip = c.beginPath()
    clip.roundRect(px, py, pw, ph, 7)
    c.clipPath(clip, stroke=0, fill=0)
    pattern(c, px, py, pw, ph, step=16, alpha=0.32)
    # وسط اللوحة صافٍ ليُقرأ العنوان
    c.setFillColor(CREAM)
    c.roundRect(px + 10, py + 8, pw - 20, ph - 16, 5, stroke=0, fill=1)
    c.restoreState()
    cx = px + pw / 2
    draw(c, cx, yt - 29, title_ar, 17, bold=True, color=BRONZE, align="center")
    if title_en:
        te = title_en.upper()
        sp, fs = 1.6, 7.4                     # تباعد الحروف يضيق للعناوين الطويلة
        while sp > 0.4 and width(te, fs, bold=True) + sp * (len(te) - 1) > pw - 34:
            sp -= 0.2
        draw(c, cx, yt - 42, te, fs, bold=True, color=GOLD, align="center", space=sp)
    meta = [x for x in (f"No. {number}" if number else "", date_txt) if x]
    if meta:
        mt = "   |   ".join(meta)
        draw(c, cx, yt - 58, mt, 9, bold=False, color=INK, align="center")

    # الخطّ الذهبي المزدوج
    y = yb - 9
    c.setStrokeColor(GOLD)
    c.setLineWidth(1.3)
    c.line(mx, y, W - mx, y)
    c.setLineWidth(0.4)
    c.line(mx, y - 2.8, W - mx, y - 2.8)
    return y - 14


def header_space(top=11 * mm) -> float:
    """المسافة من أعلى الصفحة حتى بداية المحتوى (هامش علوي للقوالب)."""
    return top + HEADER_H + 9 + 14


FOOTER_H = 22 * mm


def footer(c, W, *, co, label="", page=None, mx=15 * mm, y=9 * mm):
    """تذييل: خطّ ذهبي بنجمة، جهات التواصل، واسم المستند ورقم الصفحة."""
    co = company(co)
    ornament_rule(c, mx, W - mx, y + 19)
    runs = contact_runs(co) or [x for x in (co.get("name_ar"), co.get("name_en")) if x]
    tw = runs_width(runs, 7.8)
    draw_runs(c, W / 2 + tw / 2, y + 7, runs, 7.8)
    if label:
        draw(c, W - mx, y - 4, label, 7.2, color=MUTED)
    if page:
        draw(c, mx, y - 4, f"{page}", 7.2, color=MUTED, align="left")
        draw(c, mx + width(f"{page}", 7.2) + 3, y - 4, "صفحة", 7.2,
             color=MUTED, align="left")


def page_decor(c, doc, *, co, title_ar, title_en="", number="", date_txt="",
               label="", mark=True):
    """onPage لقوالب platypus: علامة مائية + ترويسة + تذييل."""
    W, H = doc.pagesize
    c.saveState()
    if mark:
        watermark(c, W, H)
    letterhead(c, W, H, co=co, title_ar=title_ar, title_en=title_en,
               number=number, date_txt=date_txt, mx=doc.leftMargin)
    footer(c, W, co=co, label=label or title_ar, page=doc.page,
           mx=doc.leftMargin)
    c.restoreState()


def paid_stamp(c, cx, cy, *, angle=-12, scale=1.0, ar_text="مدفوع بالكامل",
               en_text="PAID IN FULL"):
    """ختم أخضر مائل «مدفوع بالكامل» بإطار مزدوج."""
    w, h = 132 * scale, 46 * scale
    col = colors.Color(PAID.red, PAID.green, PAID.blue, alpha=0.85)
    c.saveState()
    c.translate(cx, cy)
    c.rotate(angle)
    c.setStrokeColor(col)
    c.setLineWidth(1.6 * scale)
    c.roundRect(-w / 2, -h / 2, w, h, 7 * scale, stroke=1, fill=0)
    c.setLineWidth(0.6 * scale)
    c.roundRect(-w / 2 + 3.5 * scale, -h / 2 + 3.5 * scale, w - 7 * scale,
                h - 7 * scale, 5 * scale, stroke=1, fill=0)
    draw(c, 0, 2 * scale, ar_text, 14 * scale, bold=True, color=col,
         align="center")
    draw(c, 0, -13 * scale, en_text, 7.5 * scale, bold=True, color=col,
         align="center", space=1.8 * scale)
    c.restoreState()


class Stamp(Flowable):
    """ختم «مدفوع بالكامل» كعنصر في تدفّق platypus."""

    def __init__(self, w=150, h=70):
        super().__init__()
        self.width, self.height = w, h

    def draw(self):
        paid_stamp(self.canv, self.width / 2, self.height / 2)


class SignBlock(Flowable):
    """مربّع توقيع أنيق: العنوان بالعربية والإنجليزية، الاسم، وخطّا التوقيع
    والتاريخ — مع دائرة منقّطة للختم عند الطلب."""

    def __init__(self, w, title_ar, title_en="", name="", stamp=False, h=92):
        super().__init__()
        self.width, self.height = w, h
        self.t_ar, self.t_en, self.name, self.stamp = title_ar, title_en, name, stamp

    def draw(self):
        c = self.canv
        w, h = self.width, self.height
        c.saveState()
        c.setStrokeColor(HAIR)
        c.setFillColor(colors.white)
        c.setLineWidth(0.7)
        c.roundRect(0, 0, w, h, 6, stroke=1, fill=1)
        c.setFillColor(GOLD)
        c.rect(w - 3, 10, 3, h - 20, stroke=0, fill=1)
        x1 = w - 14
        draw(c, x1, h - 20, self.t_ar, 11, bold=True, color=BRONZE)
        if self.t_en:
            draw(c, x1, h - 31, self.t_en.upper(), 6.6, bold=True, color=GOLD,
                 space=1.2)
        if self.name:
            draw(c, x1, h - 47, self.name, 10.5, color=INK)
        lx0 = 14 + (64 if self.stamp else 0)
        for i, lab in enumerate(("التوقيع", "التاريخ")):
            yy = 30 - i * 18
            draw(c, x1, yy, lab, 8.5, color=MUTED)
            c.setStrokeColor(GOLD_LT)
            c.setLineWidth(0.6)
            c.setDash(1, 2)
            c.line(lx0, yy - 2, x1 - width(lab, 8.5) - 6, yy - 2)
            c.setDash()
        if self.stamp:
            c.setStrokeColor(GOLD_LT)
            c.setDash(2, 2)
            c.circle(44, h / 2 - 6, 27, stroke=1, fill=0)
            c.setDash()
            draw(c, 44, h / 2 - 9, "الختم", 8.5, color=GOLD_LT, align="center")
        c.restoreState()


def card_head(t_ar, t_en, w, st_ar, st_en):
    """رأس بطاقة بيانات: العنوان العربي يميناً والإنجليزي يساراً (بعرض البطاقة
    كاملاً — تُدمج خليّتا الصفّ الأول)."""
    from reportlab.platypus import Paragraph, Table, TableStyle
    from .pdf_io import _ar_para
    inner = w - 16
    t = Table([[Paragraph(str(t_en or "").upper(), st_en),
                _ar_para(t_ar, st_ar, inner * 0.62 - 2)]],
              colWidths=[inner * 0.38, inner * 0.62])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                           ("TOPPADDING", (0, 0), (-1, -1), 0),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return t


def footer_compact(c, W, *, co, label="", page_txt="", mx=13 * mm, y=5 * mm):
    """تذييل بسطر واحد للمستندات المزدحمة (الفاوتشر): خطّ ذهبي بنجمة، ثم
    اسم المستند يميناً وجهات التواصل وسطاً ورقم الصفحة يساراً."""
    co = company(co)
    ornament_rule(c, mx, W - mx, y + 10)
    runs = contact_runs(co) or [x for x in (co.get("name_ar"), co.get("name_en")) if x]
    tw = runs_width(runs, 7.2)
    draw_runs(c, W / 2 + tw / 2, y, runs, 7.2)
    if label:
        draw(c, W - mx, y, label, 7, color=MUTED)
    if page_txt:
        draw(c, mx, y, page_txt, 7, color=MUTED, align="left")


class TitleBand(Flowable):
    """شريط عنوان أنيق بدل الشريط البنّي المصمت: لوحة كريمية بإطار من نقش
    النجمة الثمانية، والعنوان بالبرونزي وسطر فرعي ذهبي متباعد الحروف."""

    def __init__(self, w, title, sub="", h=42):
        super().__init__()
        self.width, self.height = w, h
        self.title, self.sub = title, sub

    def draw(self):
        c = self.canv
        w, h = self.width, self.height
        c.saveState()
        c.setFillColor(CREAM)
        c.setStrokeColor(GOLD_LT)
        c.setLineWidth(0.7)
        c.roundRect(0, 0, w, h, 6, stroke=1, fill=1)
        clip = c.beginPath()
        clip.roundRect(0, 0, w, h, 6)
        c.clipPath(clip, stroke=0, fill=0)
        pattern(c, 0, 0, w, h, step=15, alpha=0.30)
        c.setFillColor(CREAM)
        c.roundRect(w * 0.22, 5, w * 0.56, h - 10, 5, stroke=0, fill=1)
        c.restoreState()
        c.setStrokeColor(GOLD)
        c.setLineWidth(1.1)
        c.line(w * 0.22 + 14, h - 5.5, w * 0.78 - 14, h - 5.5)
        c.line(w * 0.22 + 14, 5.5, w * 0.78 - 14, 5.5)
        ty = h / 2 + (1 if self.sub else -5)
        t = str(self.title or "")
        draw(c, w / 2, ty, t if has_ar(t) else t.upper(), 16, bold=True,
             color=BRONZE, align="center", space=0 if has_ar(t) else 2.2)
        if self.sub:
            draw(c, w / 2, h / 2 - 11, str(self.sub).upper(), 7, bold=True,
                 color=GOLD, align="center", space=1.6)

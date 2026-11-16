# -*- coding: utf-8 -*-
"""البطاقات المصوّرة بشعار المصطفى (تُرسم في الخادم بـ Pillow على خلفيات جاهزة تولّدها
tools/make_share_images.py):

- story(): بطاقة حالة الواتساب للمعتمر (١٠٨٠×١٩٢٠) — «باقي ١٢ يوماً على عمرتي»، وأثناء
  الرحلة، وبعد العودة بطاقة تذكارية باسمه وتاريخ رحلته بالهجري — وعليها رمز يوصل لصفحة
  البرامج (مصدر «بطاقات المعتمرين»).
- greeting(): بطاقة تهنئة بالمناسبة (١٠٨٠×١٣٥٠) باسم الشركة ورقمها والسنة الهجرية.
- day_card(): بطاقة ختام اليوم للمدير (١٠٨٠×١٣٥٠) — أعداد ومبالغ بلا أسماء.

النصّ العربي يُشكَّل ويُرتَّب مسبقاً (reshaper + bidi) ويُرسم بالتخطيط البسيط — على
الخادم يتوفّر libraqm فيعيد ترتيبه ويقلبه لو تُرك له."""
import io
import os
from functools import lru_cache

import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(_ROOT, "hajj_app", "assets", "fonts")
SHARE = os.path.join(_ROOT, "webapp", "static", "share")
INK = (6, 43, 35)
GOLD = (242, 201, 106)
CREAM = (252, 231, 176)
WHITE = (255, 255, 255)
SOFT = (214, 232, 222)
MUTED = (105, 112, 100)
GREEN = (19, 121, 91)
VERSION = 1          # يُضاف لروابط الصور: تغييره يتجاوز النسخ المحفوظة في المتصفّحات


def ar(text: str) -> str:
    return get_display(arabic_reshaper.reshape(str(text or "")))


@lru_cache(maxsize=64)
def font(px: int, bold: bool = False):
    name = "Amiri-Bold.ttf" if bold else "Amiri-Regular.ttf"
    return ImageFont.truetype(os.path.join(FONTS, name), px, layout_engine=ImageFont.Layout.BASIC)


def _fit(d, text, size, min_size, max_w, bold=False):
    t = ar(text)
    for s in range(size, min_size - 1, -4):
        f = font(s, bold)
        if d.textlength(t, font=f) <= max_w:
            return t, f
    return t, font(min_size, bold)


def center(d, text, cx, y, size, fill, bold=False, max_w=960, min_size=24):
    """يكتب سطراً في الوسط أفقياً (يصغّر الخطّ حتى يتّسع لـ max_w)؛ يعيد عرضه."""
    t, f = _fit(d, text, size, min_size, max_w, bold)
    w = d.textlength(t, font=f)
    d.text((cx - w / 2, y), t, font=f, fill=fill)
    return w


def right(d, text, xr, y, size, fill, bold=False, max_w=900, min_size=20):
    """سطر يبدأ من اليمين (xr) كما تُقرأ العربية."""
    t, f = _fit(d, text, size, min_size, max_w, bold)
    d.text((xr - d.textlength(t, font=f), y), t, font=f, fill=fill)


def qr(img, data: str, x: int, y: int, size: int, fg=INK, bg=WHITE) -> None:
    """رمز QR مربّع (بهامش أبيض) في (x, y) بعرض size."""
    from reportlab.graphics.barcode import qrencoder
    q = qrencoder.QRCode(None, qrencoder.QRErrorCorrectLevel.M)
    q.addData(data)
    q.make()
    n = q.getModuleCount()
    d = ImageDraw.Draw(img)
    pad = 2
    cell = size / (n + 2 * pad)
    d.rectangle((x, y, x + size, y + size), fill=bg)
    for r in range(n):
        for c in range(n):
            if q.isDark(r, c):
                x0, y0 = x + (c + pad) * cell, y + (r + pad) * cell
                d.rectangle((round(x0), round(y0), round(x0 + cell) - 1, round(y0 + cell) - 1), fill=fg)


def _jpeg(img, q=88) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=q, optimize=True, progressive=True)
    return buf.getvalue()


def _pill(d, text, cx, y, size=34, fg=GOLD, outline=GOLD):
    t = ar(text)
    f = font(size, True)
    w = d.textlength(t, font=f)
    pw, ph = w + 64, size * 1.9
    d.rounded_rectangle((cx - pw / 2, y, cx + pw / 2, y + ph), ph / 2, outline=outline, width=3)
    d.text((cx - w / 2, y + ph * 0.12), t, font=f, fill=fg)


# ============================== بطاقة الحالة ==============================
@lru_cache(maxsize=96)
def story(state: str, noun: str, n: int, trip: str, when: str, first: str,
          hijri: str, company: str, qr_url: str, day_k: int = 0, day_n: int = 0) -> bytes:
    """state: before/today/during/after — noun: «عمرتي» أو «حجّي»."""
    img = Image.open(os.path.join(SHARE, "story-base.jpg")).convert("RGB")
    d = ImageDraw.Draw(img)
    cx = 540
    rite = "العمرة" if "عمرت" in noun else "فريضة الحج"
    if state == "before":
        _pill(d, "بإذن الله", cx, 410)
        num = str(n)
        f = font(300, True)
        w = d.textlength(num, font=f)
        d.text((cx - w / 2, 440), num, font=f, fill=GOLD)
        unit = "يوم" if n == 1 else "يومان" if n == 2 else "أيام" if 3 <= n <= 10 else "يوماً"
        center(d, f"باقي {unit} على {noun}", cx, 820, 92, WHITE, bold=True)
        center(d, trip, cx, 1000, 48, CREAM, max_w=900)
        if when:
            center(d, when, cx, 1070, 38, SOFT, max_w=900)
    elif state == "today":
        _pill(d, "بسم الله توكّلنا على الله", cx, 410)
        center(d, "اليوم", cx, 530, 190, GOLD, bold=True)
        center(d, f"أنطلق إلى {noun}", cx, 790, 104, WHITE, bold=True)
        center(d, trip, cx, 940, 50, CREAM, max_w=900)
        center(d, "دعواتكم بالقبول والتيسير", cx, 1020, 42, SOFT)
    elif state == "during":
        _pill(d, f"{'عمرتي' if 'عمرت' in noun else 'حجّي'} · اليوم {day_k} من {day_n}" if day_n else trip,
              cx, 410)
        center(d, "في رحاب", cx, 520, 130, WHITE, bold=True)
        center(d, "الحرمين الشريفين", cx, 700, 120, GOLD, bold=True)
        center(d, trip, cx, 900, 50, CREAM, max_w=900)
        center(d, "لا تنسونا من صالح دعائكم", cx, 980, 44, SOFT)
    elif state == "soon":                            # الرحلة بلا مواعيد مؤكّدة بعد
        _pill(d, "بإذن الله", cx, 410)
        center(d, "قريباً", cx, 520, 190, GOLD, bold=True)
        center(d, f"أنطلق إلى {noun}", cx, 790, 104, WHITE, bold=True)
        center(d, trip, cx, 940, 50, CREAM, max_w=900)
        center(d, "دعواتكم بالقبول والتيسير", cx, 1020, 42, SOFT)
    else:                                            # بعد العودة: بطاقة تذكارية
        _pill(d, "ذكرى رحلة إيمانية", cx, 410)
        center(d, "تقبّل الله", cx, 500, 160, GOLD, bold=True)
        if first:
            center(d, first, cx, 790, 104, WHITE, bold=True, max_w=880)
        center(d, f"أدّى {rite} — {hijri}" if hijri else f"أدّى {rite}", cx, 960, 50, CREAM, max_w=920)
        center(d, f"مع {company}", cx, 1040, 40, SOFT, max_w=900)
    # بطاقة الرمز: «رحلتك القادمة؟ امسح واحجز» — توصل لصفحة البرامج (مصدر البطاقات)
    if qr_url:
        x0, y0, x1, y1 = 250, 1150, 830, 1340
        d.rounded_rectangle((x0, y0, x1, y1), 30, fill=(255, 253, 247))
        qr(img, qr_url, x1 - 172, y0 + 14, 162)
        right(d, "رحلتك القادمة؟", x1 - 200, y0 + 30, 50, INK, bold=True, max_w=360)
        right(d, "امسح الرمز واحجز مقعدك", x1 - 200, y0 + 100, 34, MUTED, max_w=360)
    return _jpeg(img)


# ============================== بطاقة التهنئة ==============================
GREET = {
    "ramadan": ("رمضان كريم", "أعاده الله علينا وعليكم بالخير واليُمن والبركات", "تهنئة بالشهر الفضيل"),
    "fitr": ("عيد فطر مبارك", "تقبّل الله منّا ومنكم صالح الأعمال", "تهنئة بالعيد"),
    "arafah": ("يوم عرفة", "خير الدعاء دعاء يوم عرفة — تقبّل الله منّا ومنكم", "أفضل أيام الدنيا"),
    "adha": ("عيد أضحى مبارك", "كل عام وأنتم بخير، وحجّاً مبروراً لضيوف الرحمن", "تهنئة بالعيد"),
    "newyear": ("عام هجري سعيد", "أعاده الله علينا وعليكم باليُمن والبركات", "رأس السنة الهجرية"),
}


@lru_cache(maxsize=32)
def greeting(key: str, hy: int, company: str, phone: str) -> bytes:
    title, line, kicker = GREET.get(key, GREET["fitr"])
    img = Image.open(os.path.join(SHARE, "greet-base.jpg")).convert("RGB")
    d = ImageDraw.Draw(img)
    cx = 540
    _pill(d, kicker, cx, 300, size=30)
    center(d, title, cx, 366, 150, GOLD, bold=True, max_w=900)
    center(d, line, cx, 628, 44, WHITE, max_w=880)
    center(d, f"{hy} هـ", cx, 698, 40, CREAM)
    center(d, company, cx, 782, 46, WHITE, bold=True, max_w=640)
    if phone:
        t = phone
        f = font(36)
        w = d.textlength(t, font=f)
        d.text((cx - w / 2, 848), t, font=f, fill=SOFT)
    return _jpeg(img)


# ============================== بطاقة ختام اليوم ==============================
def day_card(data: dict) -> bytes:
    """data: title_date, hijri, mode_label, paid, n_pays, bookings, checkins, late,
    trip_name, trip_when, trip_n, stamp — كلها نصوص/أعداد جاهزة (بلا أسماء أشخاص)."""
    img = Image.open(os.path.join(SHARE, "day-base.jpg")).convert("RGB")
    d = ImageDraw.Draw(img)
    xr = 760                                         # يمين كتلة الترويسة (الشعار في أقصى اليمين)
    right(d, "ختام اليوم", xr, 40, 88, WHITE, bold=True, max_w=700)
    right(d, data.get("title_date", ""), xr, 206, 38, CREAM, max_w=700)
    right(d, data.get("hijri", ""), xr, 262, 32, SOFT, max_w=700)
    if data.get("mode_label"):
        t = ar(data["mode_label"])
        f = font(28, True)
        w = d.textlength(t, font=f)
        d.rounded_rectangle((60, 270, 60 + w + 44, 318), 24, fill=(212, 169, 76))
        d.text((82, 272), t, font=f, fill=INK)
    # المحصّل اليوم
    d.rounded_rectangle((60, 400, 1020, 640), 34, fill=WHITE, outline=(232, 222, 198), width=2)
    right(d, "المحصّل اليوم", 980, 420, 40, MUTED)
    if data.get("pays_txt"):
        t = ar(data["pays_txt"])
        fp = font(30)
        d.rounded_rectangle((100, 430, 100 + d.textlength(t, font=fp) + 40, 478), 24, fill=(232, 244, 238))
        d.text((120, 430), t, font=fp, fill=GREEN)
    amt = data.get("paid", "0")
    f = font(120, True)
    w = d.textlength(amt, font=f)
    unit = ar("درهم")
    fu = font(46)
    wu = d.textlength(unit, font=fu)
    d.text((980 - w, 450), amt, font=f, fill=GREEN)
    d.text((980 - w - 24 - wu, 540), unit, font=fu, fill=MUTED)
    # المربّعات الأربعة
    tiles = data.get("tiles") or []
    for i, (label, val, sub) in enumerate(tiles[:4]):
        col, row = i % 2, i // 2
        x1 = 1020 - col * 490
        x0 = x1 - 470
        y0 = 670 + row * 200
        d.rounded_rectangle((x0, y0, x1, y0 + 180), 28, fill=WHITE, outline=(232, 222, 198), width=2)
        right(d, label, x1 - 30, y0 + 22, 34, MUTED, max_w=410)
        f = font(76, True)
        v = str(val)
        d.text((x1 - 30 - d.textlength(v, font=f), y0 + 62), v, font=f, fill=INK)
        if sub:
            right(d, sub, x1 - 50 - d.textlength(v, font=f), y0 + 96, 28, MUTED, max_w=300)
    # أقرب رحلة
    if data.get("trip_name"):
        d.rounded_rectangle((60, 1080, 1020, 1230), 30, fill=(14, 82, 62))
        right(d, "أقرب رحلة", 980, 1098, 32, CREAM)
        right(d, data["trip_name"], 980, 1140, 46, WHITE, bold=True, max_w=620)
        if data.get("trip_when"):
            t = ar(data["trip_when"])
            f = font(40, True)
            d.text((100, 1150), t, font=f, fill=GOLD)
    right(d, data.get("stamp", ""), 1020, 1270, 28, MUTED, max_w=960)
    return _jpeg(img, 90)

# -*- coding: utf-8 -*-
"""صورة معاينة الروابط (واتساب وغيره): خلفية جاهزة — الكعبة والحرم وشعار المصطفى
(تولّدها tools/make_share_images.py) — يُكتب عليها النصّ حسب البرامج المنشورة،
مثل «برامج عمرة رمضان» أو «برامج الحج». تُحفظ الصور الناتجة في الذاكرة."""
import io
import os
from functools import lru_cache

import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(_ROOT, "hajj_app", "assets", "fonts")
BASE = os.path.join(_ROOT, "webapp", "static", "share", "og-base.jpg")
INK = (6, 43, 35)
GOLD = (242, 201, 106)
CREAM = (252, 231, 176)
FEAT = (214, 232, 222)


def ar(text: str) -> str:
    return get_display(arabic_reshaper.reshape(text))


VERSION = 2          # يُضاف لرابط الصورة: تغييره يجعل واتساب يجلب الصورة من جديد


def _font(name: str, px: int):
    # التخطيط البسيط دائماً: النصّ مُشكَّل ومرتّب مسبقاً (reshaper + bidi)، وعلى الخادم
    # (لينكس) يتوفّر libraqm الذي يعيد ترتيبه فتنقلب الحروف وتنفصل.
    return ImageFont.truetype(os.path.join(FONTS, name), px, layout_engine=ImageFont.Layout.BASIC)


def _fit(d, text, name, size, min_size, max_w, k):
    """أكبر خطّ (حتى size) يتّسع فيه النصّ لعرض max_w."""
    t = ar(text)
    for s in range(size, min_size - 1, -2):
        f = _font(name, s * k)
        if d.textlength(t, font=f) <= max_w:
            return t, f
    return t, _font(name, min_size * k)


def draw_text(img, title, sub, feat, cta, k=1) -> None:
    """يكتب النصوص يمين الصورة (RTL) — k مقياس الرسم (2 للرسم بضعف الحجم)."""
    d = ImageDraw.Draw(img)
    xr, max_w = 1150 * k, 560 * k
    for text, name, size, mn, y, fill in ((title, "Amiri-Bold.ttf", 62, 36, 248, (255, 255, 255)),
                                          (sub, "Amiri-Regular.ttf", 31, 22, 348, CREAM),
                                          (feat, "Amiri-Regular.ttf", 24, 18, 406, FEAT)):
        if not text:
            continue
        t, f = _fit(d, text, name, size, mn, max_w, k)
        d.text((xr - d.textlength(t, font=f), y * k), t, font=f, fill=fill)
    if cta:
        f = _font("Amiri-Bold.ttf", 27 * k)
        t = ar(cta)
        pw, ph = d.textlength(t, font=f) + 64 * k, 60 * k
        x0, y0 = xr - pw, 482 * k
        d.rounded_rectangle((x0, y0, xr, y0 + ph), ph // 2, fill=GOLD)
        d.text((x0 + 32 * k, y0 + 6 * k), t, font=f, fill=INK)


@lru_cache(maxsize=48)
def render(title: str, sub: str = "", feat: str = "", cta: str = "") -> bytes:
    """صورة JPEG ‏1200×630 بالنصّ المطلوب على الخلفية الجاهزة."""
    img = Image.open(BASE).convert("RGB")
    draw_text(img, title, sub, feat, cta)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=87, optimize=True, progressive=True)
    return buf.getvalue()

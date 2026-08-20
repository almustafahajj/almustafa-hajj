"""أيقونات مولّدة برمجياً (PIL) — مسطّحة بألوان العلامة، بلا أصول خارجية.

تُرسم بدقّة عالية ثم تُصغَّر (مانعة التسنّن)، وتُحوَّل إلى PhotoImage عند
الطلب داخل الواجهة. تُخزَّن مراجعها في الواجهة لمنع جمع القمامة.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

_SCALE = 4                      # نرسم مكبّراً ثم نصغّر لحواف ناعمة


def _canvas(size):
    px = size * _SCALE
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img), px


def _finish(img, size):
    return img.resize((size, size), Image.LANCZOS)


def _rr(d, box, r, fill=None, outline=None, width=1):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def button_bg(fill: str, light: str, dark: str, *, size: int = 46,
              radius: int = 12, pressed: bool = False) -> Image.Image:
    """خلفية زرّ بحواف دائرية + شطف ثلاثي الأبعاد (للـ 9-slice)."""
    S = 4
    P, R = size * S, radius * S
    inset = 2 * S
    img = Image.new("RGBA", (P, P), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    box = [inset, inset, P - inset, P - inset]
    d.rounded_rectangle(box, radius=R, fill=fill)
    lw = max(2, int(P * 0.028))
    top, bot = (dark, light) if pressed else (light, dark)
    # قوس علوي مضيء وسفلي داكن يعطي إحساس البروز داخل الحواف الدائرية
    d.arc(box, 130, 310, fill=top, width=lw)
    d.arc(box, 310, 360, fill=bot, width=lw)
    d.arc(box, 0, 130, fill=bot, width=lw)
    return img.resize((size, size), Image.LANCZOS)


def make_icon(name: str, color: str, size: int = 18) -> Image.Image:
    """يعيد أيقونة PIL بالاسم واللون المطلوبين."""
    img, d, P = _canvas(size)
    c = color
    m = P * 0.16                          # هامش
    S = P * _SCALE / _SCALE               # (P)
    cx = cy = P / 2
    lw = max(2, int(P * 0.09))

    if name == "add":                     # + داخل دائرة
        d.ellipse([m, m, P - m, P - m], outline=c, width=lw)
        d.line([cx, P * 0.32, cx, P * 0.68], fill=c, width=lw)
        d.line([P * 0.32, cy, P * 0.68, cy], fill=c, width=lw)
    elif name == "report":                # مستند بأسطر
        _rr(d, [P * 0.24, m, P * 0.76, P - m], P * 0.06, outline=c, width=lw)
        for i, yy in enumerate((0.36, 0.5, 0.64)):
            d.line([P * 0.34, P * yy, P * (0.66 - i * 0.06), P * yy], fill=c, width=lw)
    elif name == "shield":                # درع
        d.polygon([(cx, m), (P - m, P * 0.3), (P - m, P * 0.58),
                   (cx, P - m), (m, P * 0.58), (m, P * 0.3)],
                  outline=c, width=lw)
        d.line([P * 0.4, P * 0.5, P * 0.47, P * 0.6], fill=c, width=lw)
        d.line([P * 0.47, P * 0.6, P * 0.62, P * 0.4], fill=c, width=lw)
    elif name == "edit":                  # قلم
        d.line([m, P - m, P * 0.68, P * 0.32], fill=c, width=lw)
        d.polygon([(P * 0.68, P * 0.32), (P * 0.82, P * 0.18),
                   (P - m, P * 0.32), (P * 0.82, P * 0.46)], outline=c, width=lw)
        d.polygon([(m, P - m), (m + P * 0.1, P - m - P * 0.02),
                   (m + P * 0.02, P - m - P * 0.1)], fill=c)
    elif name == "trash":                 # سلّة
        d.line([P * 0.28, P * 0.3, P * 0.72, P * 0.3], fill=c, width=lw)
        _rr(d, [P * 0.32, P * 0.3, P * 0.68, P - m], P * 0.05, outline=c, width=lw)
        d.rectangle([P * 0.42, P * 0.22, P * 0.58, P * 0.3], outline=c, width=lw)
        for xx in (0.44, 0.56):
            d.line([P * xx, P * 0.4, P * xx, P * 0.78], fill=c, width=max(2, lw - 1))
    elif name == "print":                 # طابعة
        _rr(d, [P * 0.22, P * 0.4, P * 0.78, P * 0.66], P * 0.05, outline=c, width=lw)
        d.rectangle([P * 0.32, m, P * 0.68, P * 0.4], outline=c, width=lw)
        _rr(d, [P * 0.34, P * 0.6, P * 0.66, P - m], P * 0.04, outline=c, width=lw)
    elif name == "filter":                # قمع
        d.polygon([(m, P * 0.26), (P - m, P * 0.26), (P * 0.6, P * 0.54),
                   (P * 0.6, P - m), (P * 0.4, P * 0.82), (P * 0.4, P * 0.54)],
                  outline=c, width=lw)
    elif name == "columns":               # شبكة برامج (2×2) — مظهر عصري ممتلئ
        for ox, oy in ((0.16, 0.16), (0.54, 0.16), (0.16, 0.54), (0.54, 0.54)):
            _rr(d, [P * ox, P * oy, P * (ox + 0.30), P * (oy + 0.30)],
                P * 0.06, fill=c)
    elif name == "gear":                  # ترس عصري ممتلئ بأسنان مستديرة
        import math
        body_r = P * 0.25
        tw = max(3, int(P * 0.15))         # سمك السنّ
        for a in range(0, 360, 45):        # ثمانية أسنان
            rad = math.radians(a)
            x0 = cx + math.cos(rad) * body_r * 0.5
            y0 = cy + math.sin(rad) * body_r * 0.5
            x1 = cx + math.cos(rad) * (body_r + P * 0.13)
            y1 = cy + math.sin(rad) * (body_r + P * 0.13)
            d.line([x0, y0, x1, y1], fill=c, width=tw)
            d.ellipse([x1 - tw / 2, y1 - tw / 2, x1 + tw / 2, y1 + tw / 2],
                      fill=c)               # طرف مستدير للسنّ
        d.ellipse([cx - body_r, cy - body_r, cx + body_r, cy + body_r], fill=c)
        hole = P * 0.10
        d.ellipse([cx - hole, cy - hole, cx + hole, cy + hole],
                  fill=(0, 0, 0, 0))        # تفريغ المركز
    elif name == "clear":                 # مسح (x)
        d.ellipse([m, m, P - m, P - m], outline=c, width=lw)
        d.line([P * 0.36, P * 0.36, P * 0.64, P * 0.64], fill=c, width=lw)
        d.line([P * 0.64, P * 0.36, P * 0.36, P * 0.64], fill=c, width=lw)
    elif name == "search":                # عدسة
        d.ellipse([m, m, P * 0.62, P * 0.62], outline=c, width=lw)
        d.line([P * 0.58, P * 0.58, P - m, P - m], fill=c, width=lw + 1)
    elif name == "tent":                  # سرير (تسكين) — عصري ممتلئ
        _rr(d, [m, P * 0.46, P - m, P * 0.7], P * 0.06, fill=c)       # الفراش
        _rr(d, [P * 0.18, P * 0.34, P * 0.46, P * 0.5], P * 0.06,
            fill=c)                                                   # الوسادة
        d.line([m, P * 0.7, m, P * 0.84], fill=c, width=lw)
        d.line([P - m, P * 0.7, P - m, P * 0.84], fill=c, width=lw)
    elif name == "plane":                 # طائرة
        d.polygon([(m, cy), (P - m, P * 0.4), (P - m, P * 0.6)], outline=c, width=lw)
    elif name == "chart":                 # أعمدة مالية ممتلئة (عصري)
        d.line([m, P - m, P - m, P - m], fill=c, width=lw)
        for xx, hh in ((0.28, 0.50), (0.5, 0.34), (0.72, 0.20)):
            _rr(d, [P * xx - P * 0.07, P * hh, P * xx + P * 0.07, P - m],
                P * 0.03, fill=c)
    elif name == "id":                    # شخص (بديل عصري ممتلئ للبطاقة)
        d.ellipse([P * 0.37, P * 0.18, P * 0.63, P * 0.44], fill=c)   # الرأس
        d.pieslice([P * 0.24, P * 0.5, P * 0.76, P * 1.02], 180, 360,
                   fill=c)                                            # الكتفان
    elif name == "caret_down":            # سهم للأسفل (قسم موسَّع)
        d.line([P * 0.30, P * 0.40, cx, P * 0.62], fill=c, width=lw)
        d.line([cx, P * 0.62, P * 0.70, P * 0.40], fill=c, width=lw)
    elif name == "caret_left":            # سهم لليسار (قسم مطويّ — RTL)
        d.line([P * 0.60, P * 0.30, P * 0.38, cy], fill=c, width=lw)
        d.line([P * 0.38, cy, P * 0.60, P * 0.70], fill=c, width=lw)
    elif name == "caret_right":           # سهم لليمين
        d.line([P * 0.40, P * 0.30, P * 0.62, cy], fill=c, width=lw)
        d.line([P * 0.62, cy, P * 0.40, P * 0.70], fill=c, width=lw)
    elif name == "menu":                  # ثلاثة أسطر (قائمة/همبرغر)
        for yy in (0.34, 0.5, 0.66):
            d.line([P * 0.26, P * yy, P * 0.74, P * yy], fill=c, width=lw)
    elif name == "home":                  # منزل (لوحة التحكم)
        d.line([m, P * 0.5, cx, m], fill=c, width=lw)
        d.line([cx, m, P - m, P * 0.5], fill=c, width=lw)
        _rr(d, [P * 0.24, P * 0.5, P * 0.76, P - m], P * 0.04,
            outline=c, width=lw)
        _rr(d, [P * 0.42, P * 0.66, P * 0.58, P - m], P * 0.02,
            outline=c, width=max(2, lw - 1))
    elif name == "swap":                  # سهمان متعاكسان (التبديل)
        d.line([P * 0.28, P * 0.38, P * 0.72, P * 0.38], fill=c, width=lw)
        d.polygon([(P * 0.72, P * 0.38), (P * 0.60, P * 0.30),
                   (P * 0.60, P * 0.46)], fill=c)
        d.line([P * 0.28, P * 0.62, P * 0.72, P * 0.62], fill=c, width=lw)
        d.polygon([(P * 0.28, P * 0.62), (P * 0.40, P * 0.54),
                   (P * 0.40, P * 0.70)], fill=c)
    elif name == "moon":                  # هلال (الوضع الداكن)
        d.arc([m, m, P - m, P - m], 40, 320, fill=c, width=int(P * 0.16))
    elif name == "quote":                 # مستند عرض سعر (ورقة بأسطر + وسم)
        _rr(d, [P * 0.22, P * 0.14, P * 0.70, P - m], P * 0.06,
            outline=c, width=lw)
        for yy in (0.34, 0.48, 0.62):
            d.line([P * 0.30, P * yy, P * 0.60, P * yy], fill=c, width=lw)
        d.ellipse([P * 0.60, P * 0.60, P * 0.86, P * 0.86], outline=c, width=lw)
        d.line([P * 0.66, P * 0.79, P * 0.73, P * 0.73], fill=c, width=lw)
        d.line([P * 0.73, P * 0.73, P * 0.80, P * 0.79], fill=c, width=lw)
    else:                                 # نقطة افتراضية
        d.ellipse([P * 0.35, P * 0.35, P * 0.65, P * 0.65], fill=c)

    return _finish(img, size)

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
    elif name == "columns":               # أعمدة
        for xx in (0.24, 0.44, 0.64):
            _rr(d, [P * xx, m, P * (xx + 0.12), P - m], P * 0.03,
                outline=c, width=lw)
    elif name == "gear":                  # ترس
        d.ellipse([P * 0.3, P * 0.3, P * 0.7, P * 0.7], outline=c, width=lw)
        d.ellipse([P * 0.42, P * 0.42, P * 0.58, P * 0.58], outline=c, width=lw)
        import math
        for a in range(0, 360, 45):
            rad = math.radians(a)
            x0 = cx + math.cos(rad) * P * 0.36
            y0 = cy + math.sin(rad) * P * 0.36
            x1 = cx + math.cos(rad) * P * 0.46
            y1 = cy + math.sin(rad) * P * 0.46
            d.line([x0, y0, x1, y1], fill=c, width=lw)
    elif name == "clear":                 # مسح (x)
        d.ellipse([m, m, P - m, P - m], outline=c, width=lw)
        d.line([P * 0.36, P * 0.36, P * 0.64, P * 0.64], fill=c, width=lw)
        d.line([P * 0.64, P * 0.36, P * 0.36, P * 0.64], fill=c, width=lw)
    elif name == "search":                # عدسة
        d.ellipse([m, m, P * 0.62, P * 0.62], outline=c, width=lw)
        d.line([P * 0.58, P * 0.58, P - m, P - m], fill=c, width=lw + 1)
    elif name == "tent":                  # خيمة
        d.polygon([(cx, m), (P - m, P - m), (m, P - m)], outline=c, width=lw)
        d.line([cx, m, cx, P - m], fill=c, width=max(2, lw - 1))
    elif name == "plane":                 # طائرة
        d.polygon([(m, cy), (P - m, P * 0.4), (P - m, P * 0.6)], outline=c, width=lw)
    elif name == "id":                    # بطاقة
        _rr(d, [m, P * 0.28, P - m, P * 0.72], P * 0.06, outline=c, width=lw)
        d.ellipse([P * 0.2, P * 0.4, P * 0.36, P * 0.56], outline=c, width=lw)
        d.line([P * 0.44, P * 0.44, P * 0.78, P * 0.44], fill=c, width=lw)
        d.line([P * 0.44, P * 0.56, P * 0.68, P * 0.56], fill=c, width=lw)
    else:                                 # نقطة افتراضية
        d.ellipse([P * 0.35, P * 0.35, P * 0.65, P * 0.65], fill=c)

    return _finish(img, size)

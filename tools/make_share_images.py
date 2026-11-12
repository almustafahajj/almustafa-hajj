# -*- coding: utf-8 -*-
"""يولّد صور معاينة الروابط (Open Graph) التي تظهر في واتساب وغيره عند إرسال
رابط صفحة البرامج أو رابط «رحلتي» للعملاء: مشهد الكعبة والمآذن وقت الفجر مع
شعار المصطفى. og-base.jpg خلفية بلا نصّ يكتب عليها الخادم عنوان البرامج المنشورة
(webapp/share_image.py)، وtrip-og.jpg جاهزة لرابط «رحلتي».

التشغيل (مرّة عند تغيير التصميم — الصور الناتجة تُحفظ في webapp/static/share):
    python tools/make_share_images.py
"""
import math
import os
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, "hajj_app", "assets", "fonts")
LOGO = os.path.join(ROOT, "webapp", "static", "logo.png")
OUT = os.path.join(ROOT, "webapp", "static", "share")

S = 2                          # نرسم بضعف الحجم ثم نصغّر لحواف ناعمة
W, H = 1200 * S, 630 * S
INK = (6, 43, 35)
GOLD = (242, 201, 106)
CREAM = (252, 231, 176)

VARIANTS = {
    "trip": {"title": "رحلتي",
             "sub": "تفاصيل رحلتك إلى الحرمين في رابط واحد",
             "feat": "الطيران  ·  الفنادق  ·  المرشد  ·  الطوارئ",
             "cta": "افتح تفاصيل رحلتك"},
}


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def _grid():
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    return xx, yy


def sky():
    """سماء الفجر: أخضر داكن في الأعلى يدفأ نحو الأفق — مصفوفة ألوان عشرية."""
    t = np.linspace(0, 1, H, dtype=np.float32)
    stops = [0.0, 0.55, 0.8, 1.0]
    cols = np.array([(5, 36, 29), (11, 72, 56), (33, 98, 72), (92, 112, 70)], dtype=np.float32)
    col = np.stack([np.interp(t, stops, cols[:, i]) for i in range(3)], axis=1)
    return np.repeat(col[:, None, :], W, axis=1)


def glow(arr, cx, cy, r, color, strength):
    xx, yy = _grid()
    a = np.clip(1 - np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / r, 0, 1) ** 2 * strength
    arr *= (1 - a[..., None])
    arr += np.array(color, dtype=np.float32) * a[..., None]


def right_shade(arr):
    xx, _yy = _grid()
    a = np.clip((xx - 0.50 * W) / (0.36 * W), 0, 1) * 0.78
    arr *= (1 - a[..., None])
    arr += np.array(INK, dtype=np.float32) * a[..., None]


def to_img(arr):
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


def star_lattice(img, cell, alpha):
    """نقش النجمة الثمانية الخفيف (كخلفية الصفحة العامة)."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    rr = cell * 0.36
    for gy in range(-1, H // cell + 2):
        for gx in range(-1, W // cell + 2):
            cx, cy = gx * cell + cell / 2, gy * cell + cell / 2
            fade = max(0.0, 1 - cy / (H * 0.9))
            a = int(alpha * fade)
            if a <= 0:
                continue
            for rot in (0, 45):
                pts = [(cx + rr * math.cos(math.radians(rot + 45 + 90 * k)),
                        cy + rr * math.sin(math.radians(rot + 45 + 90 * k))) for k in range(4)]
                d.polygon(pts, outline=(255, 255, 255, a), width=S)
    img.paste(layer, (0, 0), layer)


def crescent(img, cx, cy, r):
    m = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(m)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    o = int(r * 0.42)
    d.ellipse((cx - r + o, cy - r - o * 0.55, cx + r + o, cy + r - o * 0.55), fill=0)
    img.paste(Image.new("RGB", (W, H), CREAM), (0, 0), m)


def sparkles(img, rnd, n, box):
    d = ImageDraw.Draw(img)
    for _ in range(n):
        x, y = rnd.uniform(box[0], box[2]), rnd.uniform(box[1], box[3])
        s = rnd.choice((2, 3, 3, 5)) * S
        c = lerp((255, 255, 255), CREAM, rnd.random())
        d.polygon([(x, y - s), (x + s * 0.28, y - s * 0.28), (x + s, y), (x + s * 0.28, y + s * 0.28),
                   (x, y + s), (x - s * 0.28, y + s * 0.28), (x - s, y), (x - s * 0.28, y - s * 0.28)], fill=c)


def minaret(d, x, top, base, col):
    """مئذنة بشرفتين وقبّة مدبّبة وهلال."""
    w = 10 * S
    h = base - top
    d.rectangle((x - w, top + 46 * S, x + w, base), fill=col)
    for f in (0.30, 0.55):
        yb = top + h * f
        d.rectangle((x - w - 6 * S, yb, x + w + 6 * S, yb + 6 * S), fill=col)
        d.polygon([(x - w - 6 * S, yb + 6 * S), (x + w + 6 * S, yb + 6 * S), (x + w, yb + 17 * S), (x - w, yb + 17 * S)], fill=col)
    d.rectangle((x - w * 0.7, top + 20 * S, x + w * 0.7, top + 48 * S), fill=col)
    d.polygon([(x - w * 0.85, top + 22 * S), (x, top - 6 * S), (x + w * 0.85, top + 22 * S)], fill=col)
    d.line((x, top - 6 * S, x, top - 18 * S), fill=col, width=2 * S)
    d.arc((x - 5 * S, top - 28 * S, x + 5 * S, top - 18 * S), 200, 520, fill=col, width=2 * S)


def haram(img, x0, x1, ground):
    """واجهة الحرم البعيدة: رواق بأقواس مضاءة ومآذن، وصحن المطاف أمامه."""
    col = (8, 42, 33, 255)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    span = x1 - x0
    for f, top in ((0.06, 205), (0.24, 168), (0.76, 168), (0.94, 205)):
        minaret(d, x0 + span * f, top * S, ground, col)
    top = ground - 74 * S
    d.rectangle((x0, top, x1, ground), fill=col)
    d.rectangle((x0, top - 9 * S, x1, top), fill=(10, 52, 40, 255))
    aw = 30 * S
    x = x0 + 10 * S
    while x + aw < x1:
        d.rectangle((x + 6 * S, top + 26 * S, x + aw - 6 * S, top + 64 * S), fill=(222, 178, 92, 165))
        d.pieslice((x + 6 * S, top + 12 * S, x + aw - 6 * S, top + 40 * S), 180, 360, fill=(222, 178, 92, 165))
        x += aw
    img.paste(layer, (0, 0), layer)
    # الصحن الرخامي المضيء
    floor = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(floor).rectangle((0, ground, W, H), fill=(196, 196, 170, 255))
    fade = Image.linear_gradient("L").resize((W, H)).point(lambda v: 0 if v < ground * 255 // H else int(min(255, (v - ground * 255 / H) * 2.2)))
    floor.putalpha(fade.point(lambda v: int(v * 0.42)))
    img.paste(floor, (0, 0), floor)


def kaaba(img, cx, by, rnd):
    """الكعبة (منظور جانبي) بحزامها الذهبي وبابها، يحيط بها الطائفون."""
    d = ImageDraw.Draw(img)
    # صحن المطاف
    mat = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(mat).ellipse((cx - 330 * S, by - 80 * S, cx + 290 * S, by + 70 * S), fill=(240, 234, 214, 90))
    mat = mat.filter(ImageFilter.GaussianBlur(10 * S))
    img.paste(mat, (0, 0), mat)

    rings = []
    for _ in range(1100):
        a = rnd.uniform(0, 2 * math.pi)
        k = rnd.uniform(0.55, 1.0)
        x = cx - 22 * S + math.cos(a) * 285 * S * k
        y = by - 14 * S + math.sin(a) * 58 * S * k
        rings.append((y, x, rnd.choice((1.5, 2, 2, 2.5)) * S, rnd.random()))
    back = [r for r in rings if r[0] < by - 30 * S]
    front = [r for r in rings if r[0] >= by - 30 * S]

    def dots(items):
        for y, x, r, t in items:
            c = lerp((255, 255, 255), (230, 220, 196), t)
            d.ellipse((x - r, y - r, x + r, y + r), fill=c)
    dots(back)
    wl, wr, hh = 150 * S, 104 * S, 196 * S
    L, C, R = (cx - wl, by - 29 * S), (cx, by), (cx + wr, by - 21 * S)
    Lt, Ct, Rt = (L[0], L[1] - hh), (C[0], C[1] - hh), (R[0], R[1] - hh)
    Bt = (Lt[0] + (Rt[0] - Ct[0]), Lt[1] + (Rt[1] - Ct[1]))
    d.polygon([L, C, Ct, Lt], fill=(20, 20, 22))
    d.polygon([C, R, Rt, Ct], fill=(34, 34, 37))
    d.polygon([Lt, Ct, Rt, Bt], fill=(48, 48, 52))

    def band(p, q, f0, f1, col):
        a0 = (p[0], p[1] - hh * f0); b0 = (q[0], q[1] - hh * f0)
        a1 = (p[0], p[1] - hh * f1); b1 = (q[0], q[1] - hh * f1)
        d.polygon([a0, b0, b1, a1], fill=col)
    for p, q, shade in ((L, C, (205, 160, 70)), (C, R, (226, 182, 90))):
        band(p, q, 0.70, 0.79, shade)
        n = 9
        for i in range(n):              # زخرفة الحزام
            t0, t1 = (i + 0.2) / n, (i + 0.8) / n
            x0, y0 = p[0] + (q[0] - p[0]) * t0, p[1] + (q[1] - p[1]) * t0 - hh * 0.745
            x1, y1 = p[0] + (q[0] - p[0]) * t1, p[1] + (q[1] - p[1]) * t1 - hh * 0.745
            d.line((x0, y0, x1, y1), fill=(120, 88, 30), width=2 * S)
    # الباب الذهبي على الوجه الأيسر قرب الركن
    t0, t1 = 0.62, 0.86
    p0 = (L[0] + (C[0] - L[0]) * t0, L[1] + (C[1] - L[1]) * t0)
    p1 = (L[0] + (C[0] - L[0]) * t1, L[1] + (C[1] - L[1]) * t1)
    d.polygon([(p0[0], p0[1] - hh * 0.16), (p1[0], p1[1] - hh * 0.16),
               (p1[0], p1[1] - hh * 0.55), (p0[0], p0[1] - hh * 0.55)], fill=(212, 170, 80))
    d.polygon([(p0[0] + 7 * S, p0[1] - hh * 0.16 - 2 * S), (p1[0] - 7 * S, p1[1] - hh * 0.16 - 2 * S),
               (p1[0] - 7 * S, p1[1] - hh * 0.52), (p0[0] + 7 * S, p0[1] - hh * 0.52)], outline=(140, 102, 40), width=2 * S)
    dots(front)


def logo_card(img, x, y, w, h):
    card = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    cd = ImageDraw.Draw(card)
    cd.rounded_rectangle((x + 6 * S, y + 10 * S, x + w + 6 * S, y + h + 10 * S), 26 * S, fill=(0, 0, 0, 90))
    card = card.filter(ImageFilter.GaussianBlur(10 * S))
    img.paste(card, (0, 0), card)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((x, y, x + w, y + h), 26 * S, fill=(255, 253, 247))
    logo = Image.open(LOGO).convert("RGBA")
    pad = 22 * S
    lw, lh = w - 2 * pad, h - 2 * pad
    k = min(lw / logo.width, lh / logo.height)
    logo = logo.resize((int(logo.width * k), int(logo.height * k)), Image.LANCZOS)
    img.paste(logo, (x + (w - logo.width) // 2, y + (h - logo.height) // 2), logo)


def scene():
    """المشهد بلا نصوص (بضعف الحجم): السماء والنقش والهلال والحرم والكعبة والظلّ والشعار."""
    rnd = random.Random(7)
    arr = sky()
    glow(arr, 420 * S, 470 * S, 470 * S, GOLD, 0.42)
    glow(arr, 140 * S, 105 * S, 120 * S, CREAM, 0.22)
    img = to_img(arr)
    star_lattice(img, 92 * S, 22)
    crescent(img, 140 * S, 105 * S, 34 * S)
    sparkles(img, rnd, 24, (30 * S, 25 * S, 700 * S, 230 * S))
    ground = 520 * S
    haram(img, 30 * S, 790 * S, ground)
    kaaba(img, 425 * S, 588 * S, rnd)
    arr = np.asarray(img, dtype=np.float32).copy()
    right_shade(arr)
    img = to_img(arr)
    xr = 1150 * S
    logo_card(img, xr - 250 * S, 38 * S, 250 * S, 196 * S)
    return img


def save(img, name, quality):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    img.resize((W // S, H // S), Image.LANCZOS).save(path, "JPEG", quality=quality, optimize=True, progressive=True)
    return path


def main():
    import sys
    sys.path.insert(0, ROOT)
    from webapp import share_image
    base = scene()
    # الخلفية: يكتب الخادم عليها عنوان البرامج المنشورة (برامج عمرة رمضان…)
    yield save(base, "og-base.jpg", 93)
    for kind, v in VARIANTS.items():
        img = base.copy()
        share_image.draw_text(img, v["title"], v["sub"], v["feat"], v["cta"], k=S)
        yield save(img, f"{kind}-og.jpg", 86)


if __name__ == "__main__":
    for p in main():
        print(p, os.path.getsize(p) // 1024, "KB")

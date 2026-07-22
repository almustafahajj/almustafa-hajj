# -*- coding: utf-8 -*-
"""يحضّر شعار الشركة للاستخدام داخل البرنامج.

    .venv\\Scripts\\python.exe tools\\refresh_logo.py "hajj_app\\assets\\شعار.png"

يقصّ الفراغ المحيط، ويجعل الخلفية شفافة، ويولّد:

- `hajj_app/assets/logo.png` — يظهر في شاشة الدخول وترويسة النافذة
- `hajj_app/assets/logo.ico` — أيقونة النافذة وشريط المهام

لماذا نولّدهما بدل استعمال الملف الأصلي مباشرة؟ لأن Tk يصغّر الصور بأعداد
صحيحة وبأسلوب خشن، فشعار بعرض 3000 بكسل يظهر مسنّناً. التصغير هنا بأسلوب
LANCZOS الناعم مرة واحدة.

يطبع أيضاً ألوان الشعار الأكثر شيوعاً — استعملها في `login.py` و`gui.py`
ليبقى البرنامج متناغماً مع العلامة.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from PIL import Image

ASSETS = Path(__file__).resolve().parent.parent / "hajj_app" / "assets"
TARGET_WIDTH = 520          # ضعف أكبر عرض معروض، ليبقى حاداً بعد تصغير Tk
ICON_SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def find_source(argument: str | None) -> Path:
    """يحدد ملف الشعار: من سطر الأوامر، أو أحدث صورة في مجلد assets."""
    if argument:
        source = Path(argument)
        if not source.is_file():
            raise SystemExit(f"الملف غير موجود: {source}")
        return source

    candidates = [
        p for p in ASSETS.glob("*.png")
        if p.stem not in {"logo"}
    ] + list(ASSETS.glob("*.jpg")) + list(ASSETS.glob("*.jpeg"))
    if not candidates:
        raise SystemExit(
            f"لم أجد صورة شعار في {ASSETS}\n"
            "ضع ملف الشعار هناك، أو مرّر مساره كوسيط."
        )
    return max(candidates, key=lambda p: p.stat().st_mtime)


def trim(image: Image.Image) -> Image.Image:
    """يقصّ الهوامش البيضاء أو الشفافة المحيطة بالشعار."""
    flat = Image.new("RGB", image.size, (255, 255, 255))
    flat.paste(image, mask=image.split()[3])
    box = flat.convert("L").point(lambda p: 255 if p < 245 else 0).getbbox()
    return image.crop(box) if box else image


def make_transparent(image: Image.Image) -> Image.Image:
    """يحوّل الأبيض إلى شفاف مع تنعيم الحواف بدل قصّها حادة."""
    pixels = []
    for r, g, b, a in image.getdata():
        lightness = (r + g + b) / 3
        if a == 0 or lightness > 245:
            pixels.append((r, g, b, 0))
        elif lightness > 205:
            pixels.append((r, g, b, int((245 - lightness) / 40 * 255)))
        else:
            pixels.append((r, g, b, a))
    out = image.copy()
    out.putdata(pixels)
    return out


def report_colors(image: Image.Image) -> None:
    """يطبع ألوان الشعار الأكثر شيوعاً لتُستعمل في ألوان الواجهة."""
    solid = [p[:3] for p in image.getdata() if p[3] > 200]
    print("\nألوان الشعار الأكثر شيوعاً:")
    for (r, g, b), count in Counter(solid).most_common(5):
        print(f"  #{r:02X}{g:02X}{b:02X}   {count:>9,} بكسل")


def main() -> None:
    source = find_source(sys.argv[1] if len(sys.argv) > 1 else None)
    print("المصدر:", source.name)

    logo = make_transparent(trim(Image.open(source).convert("RGBA")))
    print("بعد القصّ:", logo.size)
    report_colors(logo)

    height = max(1, round(logo.height * TARGET_WIDTH / logo.width))
    logo.resize((TARGET_WIDTH, height), Image.LANCZOS).save(ASSETS / "logo.png")
    print(f"\nكُتب: logo.png  ({TARGET_WIDTH}x{height})")

    side = max(logo.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(logo, ((side - logo.width) // 2, (side - logo.height) // 2))
    square.save(ASSETS / "logo.ico", sizes=ICON_SIZES)
    print("كُتب: logo.ico")


if __name__ == "__main__":
    main()

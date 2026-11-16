# -*- coding: utf-8 -*-
"""يجهّز بطاقات التهنئة بالصور الحقيقية (مرّة عند تغيير التصميم):

١) يُنزّل صورة كل مناسبة من مصدرها (كلها ملكية عامة CC0 — انظر SOURCES)، ويقصّها
   على ١٠٨٠×١٣٥٠ حول موضع الموضوع، ويحفظها في webapp/static/share/greet/<key>.jpg.
٢) يرسم «طبقة الزينة» لكل مناسبة في متصفّح كروم (خطّ الرقعة بتدرّج ذهبي، الإطار،
   التظليل، سطر الدعاء) صورةً شفّافة <key>-layer.png — الخطوط العربية الزخرفية تحتاج
   محرّك تشكيل لا يتوفّر لـ Pillow، فتُرسم هنا مرّة واحدة.

ويركّب الخادم (webapp/cards.py) البطاقة: الصورة (أو صورة يرفعها الموظفون) + الطبقة +
الشعار + السنة الهجرية واسم الشركة ورقمها.

التشغيل:  python tools/make_greet_cards.py        (يتطلّب Google Chrome)
"""
import os
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request

from PIL import Image, ImageEnhance

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "webapp", "static", "share", "greet")
CACHE = os.path.join(tempfile.gettempdir(), "greet-photos")
FONT = os.path.join(ROOT, "tools", "fonts", "ArefRuqaa-Bold.ttf")
PLEX = os.path.join(ROOT, "webapp", "static", "fonts")
CHROME = os.environ.get("CHROME", r"C:\Program Files\Google\Chrome\Application\chrome.exe")
W, H = 1080, 1350

# المصدر، موضع الموضوع (fx, fy)، والنصّ أعلى البطاقة أم أسفلها — كلها CC0 (ملكية عامة)
SOURCES = {
    "ramadan": ("https://pd.w.org/2026/04/35069e115086af128.01414646-1153x2048.jpg", .5, .26, "bottom",
                "فانوس رمضان — Faisal Ahammad, wordpress.org/photos/photo/35069e1150 (CC0)"),
    "fitr": ("https://pd.w.org/2023/05/8496472ea74c4e302.88775883-1536x2048.jpeg", .5, .36, "bottom",
             "جامع الشيخ زايد الكبير — Nazmul Hassan, wordpress.org/photos/photo/8496472ea7 (CC0)"),
    "arafah": ("https://upload.wikimedia.org/wikipedia/commons/5/5a/Mount_Arafat%28Jabal_ar-Ra%E1%B8%A5mah%29.jpg",
               .5, .42, "bottom", "جبل الرحمة بعرفات — Edibiz, Wikimedia Commons (CC0)"),
    "adha": ("https://upload.wikimedia.org/wikipedia/commons/3/3b/Kiswah_of_the_Golden_Door_of_Kaaba_-_2016.jpg",
             .5, .30, "bottom", "باب الكعبة وكسوتها — Abdullah Shakoor, Wikimedia Commons (CC0)"),
    "newyear": ("https://pd.w.org/2025/08/5146890aa21b6f2c3.75735081-1536x2048.jpg", .5, .9, "top",
                "المسجد النبوي وقت الغروب — Rubel Miah, wordpress.org/photos/photo/5146890aa2 (CC0)"),
}

# تظليل خلف النصّ حسب ازدحام الصورة، وتعتيم الصورة نفسها (١ = كما هي)
SHADE = {"bottom": "rgba(3,18,14,.97) 0%, rgba(3,18,14,.9) 34%, rgba(3,18,14,.5) 60%, rgba(3,18,14,0) 100%",
         "heavy": "rgba(3,18,14,.98) 0%, rgba(3,18,14,.95) 40%, rgba(3,18,14,.8) 57%, rgba(3,18,14,.35) 78%, rgba(3,18,14,0) 100%",
         "top": "rgba(3,18,14,.95) 0%, rgba(3,18,14,.88) 36%, rgba(3,18,14,.55) 56%, rgba(3,18,14,0) 72%"}
# موضع كتلة النصّ أفقياً وحجم العنوان (بعض الصور فيها مئذنة في الوسط)
BLOCK = {"newyear": ("left:52px;right:400px", 124)}
LOOK = {"ramadan": ("heavy", 1.0), "fitr": ("bottom", 1.0), "arafah": ("bottom", .96),
        "adha": ("heavy", .78), "newyear": ("top", 1.0)}

TEXT = {   # (التمهيد، العنوان بخطّ الرقعة، سطر الدعاء)
    "ramadan": ("تهنئة بالشهر الفضيل", "رمضان كريم", "أعاده الله علينا وعليكم بالخير واليُمن والبركات"),
    "fitr": ("تهنئة بالعيد", "عيد فطر مبارك", "تقبّل الله منّا ومنكم صالح الأعمال"),
    "arafah": ("خير يوم طلعت فيه الشمس", "يوم عرفة", "خير الدعاء دعاء يوم عرفة — تقبّل الله منّا ومنكم"),
    "adha": ("تهنئة بالعيد", "عيد أضحى مبارك", "كل عام وأنتم بخير، وحجّاً مبروراً لضيوف الرحمن"),
    "newyear": ("رأس السنة الهجرية", "عام هجري سعيد", "أعاده الله علينا وعليكم باليُمن والبركات"),
}


def fetch(key: str, url: str) -> str:
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, key + os.path.splitext(url.split("?")[0])[1].lower().replace(".jpeg", ".jpg"))
    if not os.path.exists(p) or not os.path.getsize(p):
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={"User-Agent": "GreetingCards/1.0 (one-off download)"})
        try:
            data = urllib.request.urlopen(req, timeout=180, context=ctx).read()
        except ssl.SSLError:
            ctx = ssl._create_unverified_context()          # شبكات تفحص الشهادات
            data = urllib.request.urlopen(req, timeout=180, context=ctx).read()
        open(p, "wb").write(data)
        time.sleep(2)
    return p


def cover(img: Image.Image, fx: float, fy: float) -> Image.Image:
    """قصّ «يغطّي» ١٠٨٠×١٣٥٠ حول (fx, fy) ثم تصغير."""
    img = img.convert("RGB")
    sw, sh = img.size
    k = max(W / sw, H / sh)
    cw, ch = W / k, H / k
    x0 = min(max(fx * sw - cw / 2, 0), sw - cw)
    y0 = min(max(fy * sh - ch / 2, 0), sh - ch)
    return img.crop((round(x0), round(y0), round(x0 + cw), round(y0 + ch))).resize((W, H), Image.LANCZOS)


def photo(key: str) -> str:
    url, fx, fy, _pos, _credit = SOURCES[key]
    img = cover(Image.open(fetch(key, url)), fx, fy)
    img = ImageEnhance.Contrast(img).enhance(1.06)
    img = ImageEnhance.Color(img).enhance(1.06)
    img = ImageEnhance.Brightness(img).enhance(LOOK[key][1])
    out = os.path.join(OUT, key + ".jpg")
    img.save(out, "JPEG", quality=88, optimize=True, progressive=True)
    return out


def _uri(p: str) -> str:
    return "file:///" + p.replace("\\", "/")


def layer_html(key: str) -> str:
    kick, title, line = TEXT[key]
    pos = SOURCES[key][3]
    star = ('<svg viewBox="-12 -12 24 24" width="26" height="26"><path d="M0-11L3-3L11 0L3 3L0 11L-3 3L-11 0L-3-3Z" '
            'fill="#E8C46E"/></svg>')
    block_css = ("top:250px" if pos == "top" else "bottom:265px")
    stops = SHADE[LOOK[key][0]]
    shade = f"linear-gradient({stops})" if pos == "top" else f"linear-gradient(to top, {stops})"
    shade_box = "inset:0 0 auto 0;height:900px" if pos == "top" else "inset:auto 0 0 0;height:900px"
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face{{font-family:Ruqaa;src:url({_uri(FONT)})}}
@font-face{{font-family:Plex;font-weight:500;src:url({_uri(os.path.join(PLEX, 'plex-arabic-500-arabic.woff2'))})}}
@font-face{{font-family:Plex;font-weight:600;src:url({_uri(os.path.join(PLEX, 'plex-arabic-600-arabic.woff2'))})}}
@font-face{{font-family:Plex;font-weight:500;src:url({_uri(os.path.join(PLEX, 'plex-arabic-500-latin.woff2'))});unicode-range:U+0000-00FF,U+2000-206F}}
html,body{{margin:0;width:{W}px;height:{H}px;background:transparent;overflow:hidden}}
.c{{position:relative;width:{W}px;height:{H}px;direction:rtl;font-family:Plex}}
.top{{position:absolute;inset:0 0 auto 0;height:330px;background:linear-gradient(rgba(3,18,14,.55),rgba(3,18,14,0))}}
.shade{{position:absolute;{shade_box};background:{shade}}}
.foot{{position:absolute;inset:auto 0 0 0;height:300px;background:linear-gradient(to top,rgba(3,18,14,.96),rgba(3,18,14,.75) 55%,rgba(3,18,14,0))}}
.f1{{position:absolute;inset:28px;border:2px solid rgba(232,196,110,.9);border-radius:8px}}
.f2{{position:absolute;inset:40px;border:1px solid rgba(232,196,110,.45);border-radius:5px}}
.cn{{position:absolute;width:26px;height:26px}}
.block{{position:absolute;{BLOCK.get(key, ("left:70px;right:70px", 156))[0]};{block_css};text-align:center}}
.kick{{display:inline-flex;align-items:center;gap:18px;color:#F1D394;font:600 31px Plex;letter-spacing:.3px}}
.kick i{{display:block;width:84px;height:2px;background:linear-gradient(90deg,rgba(232,196,110,0),#E8C46E)}}
.kick i:last-child{{transform:scaleX(-1)}}
.title{{font:{BLOCK.get(key, ("", 156))[1]}px/1.3 Ruqaa;margin:20px 0 0;background:linear-gradient(180deg,#FFF3CF 8%,#F3D185 46%,#C99A45 88%);
  -webkit-background-clip:text;background-clip:text;color:transparent;filter:drop-shadow(0 8px 22px rgba(0,0,0,.55))}}
.line{{color:rgba(255,255,255,.94);font:500 36px/1.65 Plex;text-shadow:0 2px 12px rgba(0,0,0,.6)}}
.orn{{display:flex;align-items:center;justify-content:center;gap:12px;margin-top:22px}}
.orn i{{display:block;width:120px;height:1.5px;background:linear-gradient(90deg,rgba(232,196,110,0),#E8C46E)}}
.orn i:last-child{{transform:scaleX(-1)}}
</style></head><body><div class="c">
<div class="top"></div><div class="shade"></div><div class="foot"></div>
<div class="f1"></div><div class="f2"></div>
<div class="cn" style="top:15px;right:15px">{star}</div><div class="cn" style="top:15px;left:15px">{star}</div>
<div class="cn" style="bottom:15px;right:15px">{star}</div><div class="cn" style="bottom:15px;left:15px">{star}</div>
<div class="block"><div class="kick"><i></i>{kick}<i></i></div>
<div class="title">{title}</div><div class="line">{line}</div>
<div class="orn"><i></i>{star}<i></i></div></div>
</div></body></html>"""


def layer(key: str) -> str:
    html = os.path.join(CACHE, f"{key}-layer.html")
    os.makedirs(CACHE, exist_ok=True)
    open(html, "w", encoding="utf-8").write(layer_html(key))
    out = os.path.join(OUT, f"{key}-layer.png")
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--allow-file-access-from-files",
                    "--default-background-color=00000000", f"--window-size={W},{H}", "--virtual-time-budget=3000",
                    f"--screenshot={out}", _uri(html)], capture_output=True, timeout=120)
    img = Image.open(out).convert("RGBA")
    if img.size != (W, H):
        img = img.resize((W, H), Image.LANCZOS)
    img.save(out, optimize=True)
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    keys = sys.argv[1:] or list(SOURCES)
    credits = ["# مصادر صور بطاقات التهنئة — كلها ملكية عامة (CC0)، لا يلزم ذكر المصوّر", ""]
    for k in keys:
        print(photo(k))
        print(layer(k))
    for k, v in SOURCES.items():
        credits.append(f"- {k}: {v[4]} — {v[0]}")
    credits.append("")
    credits.append("الخطّ: Aref Ruqaa (رخصة SIL OFL — tools/fonts/OFL-ArefRuqaa.txt)، يُرسم في الطبقة فقط.")
    open(os.path.join(OUT, "CREDITS.md"), "w", encoding="utf-8").write("\n".join(credits) + "\n")


if __name__ == "__main__":
    main()

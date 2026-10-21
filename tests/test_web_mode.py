# -*- coding: utf-8 -*-
"""البورتال: الدخول الافتراضي إلى العمرة، وتمييز كل نظام بلونه وشارته
(القائمة/الشريط العلوي/العنوان/أيقونة التبويب/صفحات المحرّر)."""
import io
import os
import re
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["HAJJ_DATA_DIR"] = tempfile.mkdtemp(prefix="web_mode_")

from hajj_app import app_mode, webdoc, webpricer  # noqa: E402

GREEN, BRONZE = "#13795B", "#8A6E4B"

# ---- 1) ألوان الأوضاع ----
assert app_mode.theme("umrah")["accent"] == GREEN
assert app_mode.theme("hajj")["accent"] == BRONZE
assert app_mode.theme("umrah")["noun"] == "العمرة"
assert app_mode.theme("hajj")["noun"] == "الحج"
assert app_mode.theme("???")["accent"] == BRONZE        # غير معروف → قيَم الحج
fav = app_mode.favicon_href("umrah")
assert fav.startswith("data:image/svg+xml,") and "%2313795B" in fav
assert "#" not in fav                                    # # مُرمَّز داخل data URI
print("[ok] ألوان الأوضاع وأيقونة التبويب")

# ---- 2) صفحات المحرّر المستقلّة ----
plain = webdoc._doc_html({"number": "X"}, [], "مستند", "📄")
assert "mode-chip\">" not in plain and "__MODE" not in plain   # سطح المكتب كما هو
um = webdoc._doc_html({"number": "X"}, [], "مستند", "📄", mode="umrah")
assert f"--bronze:{GREEN}" in um and "🌙 نظام العمرة" in um and "__MODE" not in um
hj = webpricer._pricer_html({"number": "P"}, "مسعّر", mode="hajj")
assert f"--bronze:{BRONZE}" in hj and "🕋 نظام الحج" in hj and "__MODE" not in hj
assert "__MODE" not in webpricer._pricer_html({"number": "P"}, "مسعّر")
# نصّ كتبه المستخدم يشبه علامة القالب يبقى كما هو
odd = webdoc._doc_html({"note": "__MODE_CHIP__"}, [], "م", "📄", mode="umrah")
assert '"note": "__MODE_CHIP__"' in odd
print("[ok] رأس صفحات المحرّر والمسعّر بلون الوضع وشارته")

# ---- 3) مسارات الويب ----
try:
    from webapp import server
except ImportError as exc:                   # Flask غير مثبّت
    print(f"[skip] مسارات الويب: {exc}")
    print("ALL OK")
    sys.exit(0)

css = io.open(os.path.join(ROOT, "webapp", "static", "style.css"),
              encoding="utf-8").read()
assert "body.mode-umrah{" in css and f"--bronze:{GREEN}" in css
assert "--bronze:#8A6E4B; --bronze-d:#6E543A; --bg:#F4F1EC;" in css  # الحج كما كان


def body_class(html):
    m = re.search(r'<body class="([^"]*)"', html)
    return m.group(1) if m else ""


def checked_mode(html):
    m = re.search(r'value="(\w+)"[^>]*\n?\s*checked', html)
    return m.group(1) if m else ""


c = server.app.test_client()
# التهيئة الأولى (حساب المالك) تدخل العمرة
r = c.post("/setup", data={"username": "owner", "password": "Passw0rd!x",
                           "confirm": "Passw0rd!x"})
assert r.status_code == 302, r.status_code
with c.session_transaction() as s:
    assert s["mode"] == "umrah", s.get("mode")
c.get("/logout")

# شاشة الدخول: العمرة مختارة افتراضياً والصفحة خضراء
r = c.get("/login")
html = r.get_data(as_text=True)
assert r.status_code == 200 and body_class(html) == "mode-umrah"
assert checked_mode(html) == "umrah", checked_mode(html)
assert html.index('value="umrah"') < html.index('value="hajj"')   # العمرة أولاً
assert "<select" not in html.split("mode-pick")[1].split("</div>")[0]

# دخول بلا اختيار → العمرة
r = c.post("/login", data={"username": "owner", "password": "Passw0rd!x"})
assert r.status_code == 302
with c.session_transaction() as s:
    assert s["mode"] == "umrah"
dash = c.get("/dashboard").get_data(as_text=True)
assert body_class(dash) == "mode-umrah"
assert "🌙 نظام العمرة" in dash                           # شارة الشريط العلوي
assert '<div class="mode-band"><small>النظام الحالي</small>🌙 العمرة</div>' in dash
assert re.search(r"<title>🌙 العمرة · ", dash)             # عنوان التبويب
assert 'rel="icon" href="data:image/svg+xml,' in dash and "%2313795B" in dash
assert "--other:#8A6E4B" in dash and "التبديل إلى 🕋 الحج" in dash
# صفحات المحرّر من البورتال بلون العمرة
q = c.get("/quotes/new").get_data(as_text=True)
assert f"--bronze:{GREEN}" in q and "🌙 نظام العمرة" in q
p = c.get("/pricer").get_data(as_text=True)
assert f"--bronze:{GREEN}" in p and "🌙 نظام العمرة" in p

# التبديل إلى الحج → كل شيء برونزي
c.get("/switch/hajj")
dash = c.get("/dashboard").get_data(as_text=True)
assert body_class(dash) == "mode-hajj" and "🕋 نظام الحج" in dash
assert re.search(r"<title>🕋 الحج · ", dash)
assert "--other:#13795B" in dash and "التبديل إلى 🌙 العمرة" in dash
p = c.get("/pricer").get_data(as_text=True)
assert f"--bronze:{BRONZE}" in p and "🕋 نظام الحج" in p
c.get("/logout")

# اختيار الحج صراحةً يُحترم، وقيمة غير معروفة → العمرة
c.post("/login", data={"username": "owner", "password": "Passw0rd!x",
                       "mode": "hajj"})
with c.session_transaction() as s:
    assert s["mode"] == "hajj"
c.get("/logout")
c.post("/login", data={"username": "owner", "password": "Passw0rd!x",
                       "mode": "<b>x</b>"})
with c.session_transaction() as s:
    assert s["mode"] == "umrah"
assert body_class(c.get("/dashboard").get_data(as_text=True)) == "mode-umrah"
# جلسة بلا وضع محفوظ → العمرة
with c.session_transaction() as s:
    s.pop("mode", None)
assert body_class(c.get("/dashboard").get_data(as_text=True)) == "mode-umrah"
c.get("/logout")

# فشل الدخول يُبقي الوضع الذي اختاره المستخدم
r = c.post("/login", data={"username": "owner", "password": "wrong",
                           "mode": "hajj"})
html = r.get_data(as_text=True)
assert "غير صحيحة" in html and body_class(html) == "mode-hajj"
assert checked_mode(html) == "hajj"

# الاسترداد: العمرة افتراضياً كذلك
html = c.get("/recover").get_data(as_text=True)
assert body_class(html) == "mode-umrah" and checked_mode(html) == "umrah"
print("[ok] الدخول الافتراضي للعمرة + تمييز النظامين في البورتال")

print("ALL OK")

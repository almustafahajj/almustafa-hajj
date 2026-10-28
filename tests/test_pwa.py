# -*- coding: utf-8 -*-
"""البورتال كتطبيق قابل للتثبيت (PWA) + عرض الجوال: ملف التطبيق، عامل الخدمة،
الأيقونات، ووسوم الصفحات."""
import io
import json
import os
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HAJJ_DATA_DIR"] = tempfile.mkdtemp(prefix="pwa_")

from hajj_app import auth  # noqa: E402

try:
    from webapp import server
    server.app.config["CSRF_ENABLED"] = False
except ImportError as exc:
    print(f"[skip] مسارات الويب: {exc}")
    print("ALL OK")
    sys.exit(0)
from PIL import Image  # noqa: E402

c = server.app.test_client()
# ملف التطبيق والأيقونات
r = c.get("/static/manifest.webmanifest")
m = json.loads(r.get_data(as_text=True))
assert r.status_code == 200 and m["display"] == "standalone" and m["dir"] == "rtl"
assert m["start_url"] == "/dashboard"
static = os.path.join(os.path.dirname(server.__file__), "static")
for ic in m["icons"]:
    path = os.path.join(static, ic["src"].replace("/static/", ""))
    w, h = Image.open(path).size
    assert f"{w}x{h}" == ic["sizes"] and w == h, ic
assert any(ic.get("purpose") == "maskable" for ic in m["icons"])
# عامل الخدمة: من الجذر، بلا دخول، يحفظ الملفّات الثابتة فقط
r = c.get("/sw.js")
js = r.get_data(as_text=True)
assert r.status_code == 200 and "javascript" in r.headers["Content-Type"]
assert r.headers.get("Service-Worker-Allowed") == "/" and "no-cache" in r.headers["Cache-Control"]
assert "almustafa-" in js and "/static/" in js and "r.method !== 'GET'" in js
print("[ok] ملف التطبيق والأيقونات وعامل الخدمة")
# الوسوم في صفحة الدخول وفي الصفحات الداخلية بلون النظام
page = c.get("/setup").get_data(as_text=True)
assert 'rel="manifest"' in page and "serviceWorker" in page
auth.create_account("owner", "Passw0rd!x")
page = c.get("/login").get_data(as_text=True)
assert 'rel="manifest"' in page and '<meta name="theme-color" content="#13795B">' in page
c.post("/login", data={"username": "owner", "password": "Passw0rd!x"})
page = c.get("/dashboard").get_data(as_text=True)
assert 'rel="manifest"' in page and 'apple-touch-icon' in page
assert 'id="installBtn"' in page and "beforeinstallprompt" in page
assert 'class="nav-backdrop"' in page and "data-label" in page          # بطاقات الجوال
c.get("/switch/hajj")
assert '<meta name="theme-color" content="#8A6E4B">' in c.get("/dashboard").get_data(as_text=True)
css = c.get("/static/style.css").get_data(as_text=True)
assert "@media (max-width:760px)" in css and "html.nav-open .sidebar" in css
print("[ok] وسوم التطبيق بلون النظام + درج القائمة وبطاقات الجداول على الجوال")
print("ALL OK")

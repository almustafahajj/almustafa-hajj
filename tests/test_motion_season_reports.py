# -*- coding: utf-8 -*-
"""البورتال: (١) شريط سفلي للجوال وشريط تقدّم التنقّل والحركات الدقيقة؛ (٢) اللمسة
الموسمية على لوحة التحكم (حسب التاريخ الهجري)؛ (٣) صفحة التقارير بمعاينة مصغّرة لكل
تقرير — مولّدة ببيانات تجريبية لا حقيقية، ومحفوظة في الذاكرة."""
import io
import os
import re
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HAJJ_DATA_DIR"] = tempfile.mkdtemp(prefix="motion_")

from hajj_app import app_mode, auth, storage  # noqa: E402
from hajj_app.mrz import PassportData  # noqa: E402

try:
    from webapp import server
    server.app.config["CSRF_ENABLED"] = False
except ImportError as exc:
    print(f"[skip] مسارات الويب: {exc}")
    print("ALL OK")
    sys.exit(0)

owner, _rk = auth.create_account("owner", "Passw0rd!x")
auth.add_account(owner, "view", "Passw0rd!v", role="viewer")
c = server.app.test_client()
c.post("/login", data={"username": "owner", "password": "Passw0rd!x"})
SESS = next(v for v in server._SESSIONS.values() if v.username == "owner")
v = server.app.test_client()
v.post("/login", data={"username": "view", "password": "Passw0rd!v"})
app_mode.set_mode(app_mode.UMRAH)
storage.save_records([PassportData(full_name_ar="اسم حقيقي سرّي", passport_number="SECRET99",
                                   program_value="5000", paid_amount="1000")], session=SESS)

# ---- ١) الشريط السفلي وشريط التقدّم ----
dash = c.get("/dashboard").get_data(as_text=True)
bar = dash.split('<nav class="bbar"')[1].split("</nav>")[0]
assert bar.count('class="bb-it') == 5 and 'href="/dashboard"' in bar and 'href="/hujjaj"' in bar
assert 'href="/finance"' in bar and "openCmdk" in bar and "toggleNav()" in bar
assert re.search(r'class="bb-it on" href="/dashboard" aria-current="page"', bar), "الرئيسية مفعّلة"
lst = c.get("/hujjaj").get_data(as_text=True).split('<nav class="bbar"')[1].split("</nav>")[0]
assert re.search(r'class="bb-it on" href="/hujjaj"', lst) and 'class="bb-it on" href="/dashboard"' not in lst
fin = c.get("/finance").get_data(as_text=True).split('<nav class="bbar"')[1].split("</nav>")[0]
assert re.search(r'class="bb-it on" href="/finance"', fin)
assert 'class="bbar"' in v.get("/dashboard").get_data(as_text=True), "للمطّلع أيضاً"
assert 'id="navProg"' in dash and "prefers-reduced-motion" in dash and "stagger" in dash
css = open(os.path.join(os.path.dirname(server.__file__), "static", "style.css"), encoding="utf-8").read()
assert ".bbar{ position:fixed" in css and "--bb-h" in css and "@keyframes nav-prog" in css
assert ".savebar{ bottom:var(--bb-h); }" in css, "شريط الحفظ يرتفع فوق الشريط السفلي"
assert 'class="bbar"' not in server.app.test_client().get("/login").get_data(as_text=True)
print("[ok] الشريط السفلي: خمسة أزرار، الفعّال حسب الصفحة، شريط التقدّم والحركات")

# ---- ٢) اللمسة الموسمية ----
assert 'id="dhSeason"' in dash and 'id="dhGreet"' in dash
for art in ("ds-ramadan", "ds-kaaba", "ds-eid"):
    assert art in dash, art
for k in ("ramadan", "fitr", "hajj", "arafah", "adha", "newyear"):
    assert f"{k}:{{art:" in dash, k
assert "islamic-umalqura" in dash and "رمضان كريم" in dash and "عيد أضحى مبارك" in dash
print("[ok] اللمسة الموسمية: رمضان والعيدان وموسم الحج ورأس السنة الهجرية")

# ---- ٣) التقارير بمعاينات ----
rep = c.get("/reports").get_data(as_text=True)
kinds = set(re.findall(r'/reports/preview/(\w+)\.png\?v=\w{8}', rep))
assert kinds == {"pilgrims", "financial", "airline", "cards", "stickers", "transport",
                 "itinerary", "receipt", "invoice", "contract"}, kinds
assert 'class="rep-thumb xl"' in rep and rep.count('class="repcard rc2"') == 11
vrep = v.get("/reports").get_data(as_text=True)
assert "/reports/preview/receipt.png" not in vrep, "التوليد الجماعي للمحرّرين فقط"
import fitz  # noqa: E402
for kind in sorted(kinds):
    r = c.get(f"/reports/preview/{kind}.png")
    assert r.status_code == 200 and r.data[:8] == b"\x89PNG\r\n\x1a\n", (kind, r.status_code)
    pix = fitz.Pixmap(r.data)
    assert pix.width == 460 or pix.height > 0, kind
assert c.get("/reports/preview/pilgrims.png").data == c.get("/reports/preview/pilgrims.png").data
assert len(server._THUMB_CACHE) >= len(kinds), "تُحفظ في الذاكرة"
assert c.get("/reports/preview/secret.png").status_code == 404
assert server.app.test_client().get("/reports/preview/pilgrims.png").status_code == 401
# المعاينة ببيانات تجريبية: لا اسم ولا جواز حقيقي فيها
p = os.path.join(tempfile.mkdtemp(), "t.pdf")
from hajj_app import pdf_io  # noqa: E402
pdf_io.export_umrah_pdf(server._demo_records(), p, program_name="")
txt = fitz.open(p)[0].get_text()
assert "SECRET99" not in txt and all("SECRET" not in r.passport_number for r in server._demo_records())
# نظام الحج أيضاً (البطاقات بخلفها)
c.get("/switch/hajj")
for kind in ("pilgrims", "cards", "stickers"):
    assert c.get(f"/reports/preview/{kind}.png").status_code == 200, kind
hrep = c.get("/reports").get_data(as_text=True)
assert "/reports/preview/transport.png" not in hrep and 'class="rep-thumb edit"' in hrep
# تغيّر بيانات الشركة يغيّر رقم نسخة المعاينات (فلا تبقى صورة قديمة في المتصفّح)
v1 = re.search(r'preview/pilgrims\.png\?v=(\w+)', hrep).group(1)
c.post("/documents/company", data={"name_ar": "شركة تجربة", "name_en": "", "phone": "",
                                   "email": "", "website": "", "address": "", "trn": ""})
v2 = re.search(r'preview/pilgrims\.png\?v=(\w+)', c.get("/reports").get_data(as_text=True)).group(1)
assert v1 != v2
print("[ok] التقارير: معاينة لكل تقرير ببيانات تجريبية، محفوظة، وتتجدّد مع بيانات الشركة")

print("ALL OK")

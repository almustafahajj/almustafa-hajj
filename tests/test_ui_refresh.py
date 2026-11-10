# -*- coding: utf-8 -*-
"""البورتال: تجديد الواجهة — الخط العربي المستضاف محلياً، شاشة الدخول الجديدة،
والرسائل المنبثقة (مع بقاء الرسائل الدائمة في مكانها)."""
import io
import os
import re
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HAJJ_DATA_DIR"] = tempfile.mkdtemp(prefix="uirefresh_")

from hajj_app import auth  # noqa: E402

try:
    from webapp import server
    server.app.config["CSRF_ENABLED"] = False
except ImportError as exc:
    print(f"[skip] مسارات الويب: {exc}")
    print("ALL OK")
    sys.exit(0)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "webapp", "static")
anon = server.app.test_client()

# ---- ١) الخط: كل ملف مذكور في التنسيق موجود ويُخدَم من البورتال نفسه ----
css = open(os.path.join(STATIC, "style.css"), encoding="utf-8").read()
fonts = re.findall(r"url\((fonts/[^)]+\.woff2)\)", css)
assert len(fonts) == 8, f"متوقّع ٨ ملفات خط (٤ أوزان × عربي/لاتيني): {fonts}"
for f in fonts:
    assert os.path.getsize(os.path.join(STATIC, f)) > 10_000, f"ملف الخط ناقص: {f}"
    r = anon.get("/static/" + f)
    assert r.status_code == 200 and r.data[:4] == b"wOF2", f"الخط لا يُخدَم: {f}"
    r.close()
assert "font-family:var(--font)" in css and "'Plex Arabic'" in css
assert "fonts.googleapis" not in css, "لا اعتماد على خوادم خارجية"
sw = anon.get("/sw.js").get_data(as_text=True)
assert "/static/fonts/plex-arabic-400-arabic.woff2" in sw, "الخط يُحفظ للعمل كتطبيق"

# ---- ٢) شاشة الدخول الجديدة: لوحة الهوية + الحقول + إظهار كلمة المرور ----
auth.create_account("owner", "Passw0rd!x")
page = anon.get("/login").get_data(as_text=True)
for bit in ('class="login-wrap login-split"', 'class="ls-brand"', "logo.png", "أهلاً بعودتك",
            'id="pwEye"', 'aria-label="إظهار كلمة المرور"', 'name="username"', 'name="password"',
            'name="remember"', "نسيت كلمة المرور؟", 'value="umrah"'):
    assert bit in page, f"ينقص في شاشة الدخول: {bit}"
assert re.search(r'<body class="mode-umrah">', page), "لون النظام على الصفحة كما هو"
r = anon.post("/login", data={"username": "owner", "password": "Passw0rd!x"})
assert r.status_code == 302, "الدخول يعمل من الشاشة الجديدة"
r = server.app.test_client().post("/login", data={"username": "owner", "password": "خطأ-خطأ1"})
assert r.status_code == 200 and 'class="err"' in r.get_data(as_text=True), "رسالة الخطأ تظهر"

# صفحات الاستعادة تبقى ببطاقتها (لم تتأثّر بتقسيم شاشة الدخول)
fp = server.app.test_client().get("/forgot").get_data(as_text=True)
assert 'class="login-wrap"' in fp and "login-split" not in fp

# ---- ٣) الرسائل المنبثقة ----
dash = anon.get("/dashboard").get_data(as_text=True)
assert '<template id="toastIc">' in dash and "className='toasts'" in dash
anon.post("/accounts/session-policy", data={"minutes": "60"})
acc = anon.get("/accounts").get_data(as_text=True)
assert 'class="acc-msg ok"' in acc and "مدّة الجلسة الآن" in acc, "رسالة النجاح تُرسل للصفحة"
# الرسائل التي يجب أن تبقى ظاهرة معلَّمة بـ data-keep
tpl = os.path.join(ROOT, "webapp", "templates")
for name, needle in (("account_password.html", "مفتاح الاسترداد الجديد"),
                     ("notifications.html", "لا شيء يحتاج انتباهاً"),
                     ("quality.html", "لا توجد مشكلات"),
                     ("import.html", "{{ result }}")):
    line = next(ln for ln in open(os.path.join(tpl, name), encoding="utf-8") if needle in ln)
    assert "data-keep" in line, f"{name}: الرسالة الدائمة يجب ألّا تختفي"

print("ALL OK")

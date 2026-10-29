# -*- coding: utf-8 -*-
"""البورتال — الأمان: رموز TOTP (RFC 6238)، حفظ سرّ الدخول بخطوتين في الحساب،
إيقاف الدخول بعد محاولات خاطئة، حماية النماذج (CSRF)، ومسار الدخول بخطوتين."""
import io
import os
import re
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HAJJ_DATA_DIR"] = tempfile.mkdtemp(prefix="security_")

from hajj_app import auth, totp  # noqa: E402

# ---- 1) TOTP: متّجهات RFC 6238 (SHA1) ----
S = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"            # "12345678901234567890"
assert totp.code_at(S, 59 // 30) == "287082"
assert totp.code_at(S, 1111111109 // 30) == "081804"
assert totp.code_at(S, 1234567890 // 30) == "005924"
t0 = 1234567890
assert totp.verify(S, "005924", t=t0) == t0 // 30
assert totp.verify(S, "٠٠٥٩٢٤", t=t0) == t0 // 30             # أرقام عربية
assert totp.verify(S, "005 924", t=t0 + 30) == t0 // 30         # سماحية خطوة
assert totp.verify(S, "005924", t=t0 + 95) is None              # انتهت مدّته
assert totp.verify(S, "005924", t=t0, last_step=t0 // 30) is None   # لا يُكرَّر
assert totp.verify(S, "12345", t=t0) is None and totp.verify("", "005924") is None
sec = totp.new_secret()
assert len(sec) == 32 and totp.verify(sec, totp.code_at(sec, totp.now_step()))
uri = totp.otpauth_uri(sec, "owner")
assert uri.startswith("otpauth://totp/") and f"secret={sec}" in uri
print("[ok] TOTP: متّجهات RFC 6238 + أرقام عربية + منع التكرار")

# ---- 2) السرّ في الحساب: مشفّر، يبقى بعد تغيير كلمة المرور، ويُلغى بالاسترداد ----
owner, owner_rk = auth.create_account("owner", "Passw0rd!x")
auth.add_account(owner, "sara", "Passw0rd!s", role="editor")
assert not auth.has_totp("owner")
auth.set_totp(owner, sec)
assert auth.has_totp("OWNER") and auth.get_totp(owner) == sec
raw = open(auth.default_auth_path(), encoding="utf-8").read()
assert sec not in raw                                  # مشفّر بمفتاح البيانات
assert [a["totp"] for a in auth.list_accounts()] == [True, False]
auth.set_policy(owner, require_totp=True)
auth.add_account(owner, "ali", "Passw0rd!a")           # كتابة الملف تُبقي السياسة
assert auth.get_policy() == {"require_totp": True}
auth.change_password("owner", "Passw0rd!x", "Passw0rd!z")
auth.regenerate_recovery_key("owner", "Passw0rd!z")
owner = auth.login("owner", "Passw0rd!z")
assert auth.get_totp(owner) == sec                     # بقي بعد التغييرات
try:
    auth.admin_clear_totp(auth.login("sara", "Passw0rd!s"), "owner")
    raise AssertionError("المحرّر لا يلغي خطوتي غيره")
except auth.AuthError:
    pass
auth.set_policy(owner, require_totp=False)
rk = auth.regenerate_recovery_key("owner", "Passw0rd!z")
auth.reset_with_recovery_key(rk, "Passw0rd!r")
assert not auth.has_totp("owner")                       # الاسترداد يلغيه
owner = auth.login("owner", "Passw0rd!r")
print("[ok] السرّ مشفّر في الحساب ويبقى عبر تغيير كلمة المرور والسياسة محفوظة")

try:
    from webapp import server
except ImportError as exc:
    print(f"[skip] مسارات الويب: {exc}")
    print("ALL OK")
    sys.exit(0)

server.app.config["CSRF_ENABLED"] = True


def token(html):
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else None


# ---- 3) CSRF: الرمز يُضاف للنماذج، وPOST بلا رمز يُرفض ----
c = server.app.test_client()
page = c.get("/login").get_data(as_text=True)
tok = token(page)
assert tok and '<meta name="csrf-token"' in page
r = c.post("/login", data={"username": "owner", "password": "Passw0rd!r"})
assert r.status_code == 400 and "انتهت صلاحية الصفحة" in r.get_data(as_text=True)
r = c.post("/login", data={"username": "owner", "password": "Passw0rd!r",
                           "csrf_token": "مزوّر"})
assert r.status_code == 400
r = c.post("/login", data={"username": "owner", "password": "Passw0rd!r",
                           "csrf_token": tok})
assert r.status_code == 302 and r.headers["Location"].endswith("/dashboard")
# الرمز نفسه بعد الدخول (الصفحات المفتوحة تبقى صالحة للحفظ)
acc = c.get("/accounts").get_data(as_text=True)
tok2 = token(acc)
assert tok2 == tok
assert len(re.findall(r'name="csrf_token"', acc)) == acc.count('method="post"')
# طلبات fetch: الرمز في الترويسة
r = c.post("/accounts/add", data={"username": "x1", "password": "Passw0rd!1"},
           headers={"X-CSRF-Token": tok2})
assert r.status_code == 302 and "x1" in [a["username"] for a in auth.list_accounts()]
# صفحة رفض الطلب لا تُعيد إلى موقع خارجي
r = c.post("/accounts/add", data={}, headers={"Referer": "https://evil.example/x"})
assert "evil.example" not in r.get_data(as_text=True)
print("[ok] CSRF: الرمز في كل نموذج وترويسة fetch، ورفض الطلبات بدونه")

# ---- 4) إيقاف الدخول بعد ٥ محاولات خاطئة (لكل حساب) ----
c2 = server.app.test_client()
t = token(c2.get("/login").get_data(as_text=True))
for _ in range(5):
    html = c2.post("/login", data={"username": "sara", "password": "خطأ!",
                                   "csrf_token": t}).get_data(as_text=True)
    assert "غير صحيحة" in html
html = c2.post("/login", data={"username": "sara", "password": "Passw0rd!s",
                               "csrf_token": t}).get_data(as_text=True)
assert "أُوقف الدخول مؤقّتاً" in html                     # حتى بكلمة المرور الصحيحة
from hajj_app import audit  # noqa: E402
assert sum(1 for e in audit.read_entries() if e["action"] == "محاولة دخول فاشلة") >= 5
# حساب آخر من عنوان آخر غير متأثّر
c3 = server.app.test_client()
t3 = token(c3.get("/login", environ_base={"REMOTE_ADDR": "10.0.0.9"}).get_data(as_text=True))
r = c3.post("/login", data={"username": "ali", "password": "Passw0rd!a", "csrf_token": t3},
            environ_base={"REMOTE_ADDR": "10.0.0.9"})
assert r.status_code == 302
server._FAILS.clear()
r = c2.post("/login", data={"username": "sara", "password": "Passw0rd!s", "csrf_token": t})
assert r.status_code == 302
print("[ok] إيقاف الدخول بعد ٥ محاولات خاطئة + تسجيلها في سجلّ التدقيق")

# ---- 5) تفعيل الدخول بخطوتين من البورتال ثم الدخول به ----
server._TOTP_LAST.clear()
page = c.get("/account/2fa").get_data(as_text=True)
assert "<svg" in page and "تفعيل الدخول بخطوتين" in page
sid = c.get_cookie("session")
setup_secret = next(iter(server._TOTP_SETUP.values()))
assert totp.pretty(setup_secret) in page
t = token(page)
r = c.post("/account/2fa", data={"action": "enable", "code": "000000", "csrf_token": t})
assert "الرمز غير صحيح" in r.get_data(as_text=True) and not auth.has_totp("owner")
code = totp.code_at(setup_secret, totp.now_step())
r = c.post("/account/2fa", data={"action": "enable", "code": code, "csrf_token": t})
assert "فُعِّل الدخول بخطوتين" in r.get_data(as_text=True) and auth.has_totp("owner")
# دخول جديد: بعد كلمة المرور يُطلب الرمز
d = server.app.test_client()
t = token(d.get("/login").get_data(as_text=True))
r = d.post("/login", data={"username": "owner", "password": "Passw0rd!r", "csrf_token": t})
assert r.headers["Location"].endswith("/login/2fa")
assert d.get("/dashboard").status_code == 302                 # لم يدخل بعد
p2 = d.get("/login/2fa").get_data(as_text=True)
t = token(p2)
html = d.post("/login/2fa", data={"code": "111111", "csrf_token": t}).get_data(as_text=True)
assert "الرمز غير صحيح" in html
server._TOTP_LAST.clear()
r = d.post("/login/2fa", data={"code": totp.code_at(setup_secret, totp.now_step()),
                               "csrf_token": t})
assert r.status_code == 302 and r.headers["Location"].endswith("/dashboard")
assert d.get("/dashboard").status_code == 200
# الرمز نفسه لا يُقبل مرّة أخرى (دخول ثانٍ بالرمز ذاته)
e = server.app.test_client()
t = token(e.get("/login").get_data(as_text=True))
e.post("/login", data={"username": "owner", "password": "Passw0rd!r", "csrf_token": t})
t = token(e.get("/login/2fa").get_data(as_text=True))
html = e.post("/login/2fa", data={"code": totp.code_at(setup_secret, totp.now_step()),
                                  "csrf_token": t}).get_data(as_text=True)
assert "الرمز غير صحيح" in html
print("[ok] الدخول بخطوتين: تفعيل بالرمز ثم طلبه عند الدخول ومنع تكراره")

# ---- 6) إلزام المدير + إلغاؤه لحساب ضاع جواله ----
server._FAILS.clear()
acc = c.get("/accounts").get_data(as_text=True)
assert "✅ تطبيق" in acc
t = token(acc)
c.post("/accounts/2fa-policy", data={"require": "1", "csrf_token": t})
assert auth.get_policy().get("require_totp") is True
f = server.app.test_client()
t = token(f.get("/login").get_data(as_text=True))
assert f.post("/login", data={"username": "ali", "password": "Passw0rd!a",
                              "csrf_token": t}).status_code == 302
r = f.get("/dashboard")
assert r.status_code == 302 and "/account/2fa" in r.headers["Location"]
assert "إلزامي" in f.get("/account/2fa?need=1").get_data(as_text=True)
t = token(c.get("/accounts").get_data(as_text=True))
c.post("/accounts/2fa-policy", data={"csrf_token": t})          # اختياري
c.post("/accounts/owner/2fa-reset", data={"csrf_token": t})
assert not auth.has_totp("owner") and auth.get_policy().get("require_totp") is False
assert f.get("/dashboard").status_code == 200
acts = [e["action"] for e in audit.read_entries()]
assert "تفعيل الدخول بخطوتين" in acts and "إلغاء الدخول بخطوتين (المدير)" in acts
print("[ok] إلزام الدخول بخطوتين وإلغاؤه من المدير")

# ---- 7) إصلاحات المراجعة الأمنية ----
import time as _t  # noqa: E402
from flask import Flask  # noqa: E402
# الحقل لا يُحقن داخل <script> (بيانات المحرّرات)، والوقت خطّي مع نصوص خبيثة
with server.app.test_request_context("/"):
    from flask import session as _s
    _s["csrf"] = "TOKEN"
    big = "<html><head></head><body><script>const D={\"a\":\"<form method=post>\"};</script>" \
          + "<form method=\"post\" action=\"/x\"></form>" + "&lt;" + "<form method " * 40000 + "</body></html>"
    resp = server.app.response_class(big, mimetype="text/html")
    t1 = _t.time()
    out = server._csrf_inject(resp).get_data(as_text=True)
    assert _t.time() - t1 < 2, "بطيء"
    assert 'const D={"a":"<form method=post>"}' in out              # لم يُمسّ
    assert '<form method="post" action="/x"><input type="hidden" name="csrf_token" value="TOKEN">' in out
# روابط التبديل والخروج تحتاج رمز الجلسة
g = server.app.test_client()
t = token(g.get("/login").get_data(as_text=True))
g.post("/login", data={"username": "ali", "password": "Passw0rd!a", "csrf_token": t})
with g.session_transaction() as sx:
    mode0, tk = sx.get("mode"), sx["csrf"]
other = "hajj" if mode0 != "hajj" else "umrah"
g.get(f"/switch/{other}")
with g.session_transaction() as sx:
    assert sx["mode"] == mode0                                      # بلا رمز: لا تبديل
g.get(f"/switch/{other}?t={tk}")
with g.session_transaction() as sx:
    assert sx["mode"] == other
assert f"t={tk}" in g.get("/dashboard").get_data(as_text=True)
g.get("/logout")
assert g.get("/dashboard").status_code == 200                       # بلا رمز: لا خروج
# اسم مستخدم غير موجود لا يُكتب في السجلّ كما هو، والطويل يُقصّ
server._FAILS.clear()
h = server.app.test_client()
t = token(h.get("/login").get_data(as_text=True))
h.post("/login", data={"username": "كلمة-سرّ-كُتبت-خطأ" + "x" * 5000, "password": "a",
                       "csrf_token": t})
assert all(len(k[1]) <= 64 for k in server._FAILS)
last = audit.read_entries()[0]                     # الأحدث أولاً
assert "كلمة-سرّ" not in last["details"] and "اسم غير معروف" in last["details"]
# المدير يفكّ إيقاف حساب
server._FAILS.clear()
for _ in range(5):
    h.post("/login", data={"username": "sara", "password": "خطأ", "csrf_token": t})
acc = c.get("/accounts").get_data(as_text=True)
assert "⛔ موقوف مؤقّتاً" in acc
c.post("/accounts/sara/unlock", data={"csrf_token": token(acc)})
assert h.post("/login", data={"username": "sara", "password": "Passw0rd!s",
                              "csrf_token": t}).status_code == 302
# رموز صفحة التفعيل/الإلغاء محدودة المحاولات أيضاً
server._FAILS.clear()
k = server.app.test_client()
t = token(k.get("/login").get_data(as_text=True))
k.post("/login", data={"username": "sara", "password": "Passw0rd!s", "csrf_token": t})
t = token(k.get("/account/2fa").get_data(as_text=True))
for _ in range(5):
    k.post("/account/2fa", data={"action": "enable", "code": "000000", "csrf_token": t})
assert "أُوقف الدخول مؤقّتاً" in k.post("/account/2fa", data={
    "action": "enable", "code": "000000", "csrf_token": t}).get_data(as_text=True)
server._FAILS.clear()
print("[ok] إصلاحات المراجعة: لا حقن داخل السكربت، روابط بالرمز، فكّ الإيقاف، حدود الرموز")

# ---- 8) قائمة الإدارة للمدير فقط، وتغيير الدور يسري فوراً ----
server._FAILS.clear()
owner = auth.login("owner", "Passw0rd!r")
auth.add_account(owner, "boss2", "Passw0rd!b", role="admin")
b = server.app.test_client()
t = token(b.get("/login").get_data(as_text=True))
b.post("/login", data={"username": "boss2", "password": "Passw0rd!b", "csrf_token": t})
assert "النسخ الاحتياطي" in b.get("/dashboard").get_data(as_text=True)
auth.set_role(owner, "boss2", "editor")                      # إنزال أثناء جلسته
page = b.get("/dashboard").get_data(as_text=True)
assert "النسخ الاحتياطي" not in page and "إدارة الحسابات" not in page
assert b.get("/backup").status_code == 302
assert "للمدير فقط" in b.get("/accounts").get_data(as_text=True)
auth.remove_account(owner, "boss2")                          # حذف الحساب يُخرجه
assert b.get("/dashboard").status_code == 302
print("[ok] الإدارة للمدير فقط، وتغيير الدور/حذف الحساب يسري فوراً")
print("ALL OK")

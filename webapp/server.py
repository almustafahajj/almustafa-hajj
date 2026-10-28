"""خادم Flask لتطبيق الويب — المرحلة الأولى: تسجيل الدخول + لوحة التحكم.

يعيد استخدام منطق ``hajj_app`` كما هو (المصادقة، التخزين، الإحصاءات). الجلسات
تُحفظ في الذاكرة على الخادم (كافٍ للتطوير؛ للنشر السحابي يُضاف تخزين جلسات آمن
وHTTPS)."""

from __future__ import annotations

import hashlib
import io
import os
import secrets
import re
import tempfile
import threading
import hmac
import time

from flask import (Flask, redirect, render_template, request, send_file,
                   session, url_for)
from werkzeug.middleware.proxy_fix import ProxyFix

from hajj_app import app_mode, auth, stats, storage
from hajj_app.fields import BY_KEY, format_amount
from hajj_app.stats import remaining_amount

_PAGE = 50
_STATUS_CLS = {"نشط": "good", "ملغى": "crit", "قائمة انتظار": "warn"}
_CHOICES = {"status": ["", "نشط", "ملغى", "قائمة انتظار"],
            "sex": ["", "ذكر", "أنثى"], "wheelchair": ["", "نعم"]}
# قوائم خاصّة بالعمرة (في الحج «المواصلات» رقم الباص فتبقى نصّاً حرّاً)
_UMRAH_CHOICES = {
    "staff": ["", "أيمن الشهابي", "أحمد الشبراوي", "علاء بريخان",   # الموظف المسؤول
              "رامي الشلبي", "مريم الحوسني", "محمد صابر"],
    "transport": ["", "GMC", "FORD"],                              # المواصلات
}
_DATE_FIELDS = {"birth_date", "expiry_date", "arrival_date", "departure_date"}
_UMRAH_DROP = {"program", "group", "hady", "executive_service", "wheelchair",
               "airline", "flight_number", "travel_class", "pnr",
               "arrival_date", "arrival_time", "departure_date",
               "departure_time", "hotel"}
_GROUPS = [
    ("بيانات {n}", ["family_number", "reference_number", "full_name_ar",
                    "full_name_en", "phone", "program", "group", "status",
                    "mahram_name", "mahram_relation"]),
    ("الجواز", ["passport_number", "nationality_ar", "sex", "birth_date",
                "expiry_date"]),
    ("السفر", ["airline", "flight_number", "travel_class", "pnr",
               "arrival_date", "arrival_time", "departure_date",
               "departure_time", "transport"]),
    ("الإقامة والخدمات", ["hotel", "room_type", "room_number",
                          "executive_service", "wheelchair", "hady"]),
    ("المالية", ["program_value", "paid_amount"]),
    ("ملاحظات", ["notes", "staff"]),
]

app = Flask(__name__)
# خلف وكيل Railway: عنوان الزائر الحقيقي (لإيقاف محاولات الدخول) وبروتوكول https
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
# حماية النماذج من الطلبات المزوّرة (تُعطَّل في الاختبارات فقط)
app.config["CSRF_ENABLED"] = True
# أكبر رفع مسموح (نسخة احتياطية مع الصور)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024
# صفحة تعديل التسكين ترسل كل الصفوف (مع رمز كل سجلّ): نرفع حدّ النموذج
# الافتراضي (500KB) كي لا يُرفض حفظ كشفٍ كبير (~2000 شخص)
app.config["MAX_FORM_MEMORY_SIZE"] = 32 * 1024 * 1024


def _session_secret() -> str:
    """مفتاح توقيع الجلسات — لا يُخزَّن في الشيفرة أبداً.

    الأولوية: متغيّر البيئة ``SECRET_KEY``؛ وإلّا مفتاح ثابت يُولَّد **على الخادم**
    ويُحفظ في مجلّد البيانات (يبقي الجلسات صالحة عبر إعادات التشغيل بلا تضمين
    أي سرّ في المستودع)."""
    env = os.environ.get("SECRET_KEY")
    if env:
        return env
    try:
        from hajj_app.paths import data_dir
        p = data_dir() / "web_secret.key"
        if p.exists():
            got = p.read_text(encoding="utf-8").strip()
            if got:
                return got
        key = secrets.token_hex(32)
        p.write_text(key, encoding="utf-8")
        return key
    except Exception:
        return secrets.token_hex(16)


app.secret_key = _session_secret()
# أمان ملفّات الارتباط — يُفعَّل Secure تلقائياً خلف HTTPS في النشر السحابي.
from datetime import timedelta as _timedelta
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=(os.environ.get("HTTPS", "").lower()
                           in ("1", "true", "yes")),
    PERMANENT_SESSION_LIFETIME=_timedelta(days=14),   # مدّة «تذكّرني»
)

# جلسات hajj_app الحيّة (المفكوكة التشفير) مفهرسة برمز جلسة المتصفّح
_SESSIONS: dict = {}


def _sess():
    return _SESSIONS.get(session.get("sid"))


def _mode() -> str:
    """وضع الجلسة؛ الافتراضي (وأيّ قيمة غير معروفة) هو العمرة."""
    m = session.get("mode")
    return m if m in app_mode.MODES else app_mode.UMRAH


# خيارات الوضع في شاشتَي الدخول والاسترداد — العمرة أولاً وهي الافتراضية
_MODE_CHOICES = [(m, app_mode.theme(m)["noun"], app_mode.theme(m)["icon"])
                 for m in (app_mode.UMRAH, app_mode.HAJJ)]


def _form_mode() -> str:
    """الوضع المختار في نموذج الدخول (العمرة إن لم يُختر أو كان غير معروف)."""
    m = request.form.get("mode")
    return m if m in app_mode.MODES else app_mode.UMRAH


def _noun() -> str:
    return "الحجّاج" if _mode() == app_mode.HAJJ else "المعتمرون"


def _group_attr() -> str:
    return "program" if _mode() == app_mode.HAJJ else "trip"


def _ensure_uids(records) -> bool:
    """يمنح كل سجلّ بلا معرّف (أو بمعرّف مكرّر) معرّفاً ثابتاً فريداً."""
    return storage.ensure_uids(records)


_UID_LOCK = threading.Lock()


def _load_records():
    app_mode.set_mode(_mode())
    try:
        records, _note = storage.load_records(session=_sess())
    except Exception:
        return []
    uids = [str(getattr(r, "uid", "") or "") for r in records]
    if not all(uids) or len(set(uids)) != len(uids):
        # ترحيل لمرّة واحدة: إعادة التحميل تحت القفل كي لا يمنح طلبان متزامنان
        # معرّفات مختلفة للسجلّ نفسه
        with _UID_LOCK:
            try:
                records, _note = storage.load_records(session=_sess())
                if _ensure_uids(records):
                    storage.save_records(records, session=_sess())
            except Exception:                      # noqa: BLE001
                pass
    return records


def _by_group(records):
    attr = _group_attr()
    groups: dict = {}
    for r in records:
        key = str(getattr(r, attr, "") or "").strip() or "—"
        groups.setdefault(key, []).append(r)
    out = [(name, stats.financial_summary(rs))
           for name, rs in sorted(groups.items(), key=lambda kv: kv[0])]
    return out


@app.get("/")
def index():
    if _sess() is None:
        return redirect(url_for("login"))
    return redirect(url_for("dashboard"))


@app.route("/setup", methods=["GET", "POST"])
def setup():
    """التهيئة الأولى عند النشر: إنشاء حساب المالك (المدير) من المتصفّح."""
    if auth.is_configured():
        return redirect(url_for("login"))
    error = ""
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""
        problem = auth.password_problem(password, confirm)
        if not username:
            error = "اسم المستخدم مطلوب."
        elif problem:
            error = problem
        else:
            try:
                sess, key = auth.create_account(username, password)
                sid = secrets.token_hex(16)
                _SESSIONS[sid] = sess
                session["sid"] = sid
                session["mode"] = app_mode.UMRAH      # الدخول الافتراضي: العمرة
                session["username"] = username
                session["role"] = sess.role_label
                session["acc_key"] = key           # يُعرض مرّة في صفحة الحسابات
                session["acc_added"] = username
                session["acc_msg"] = "تمّت التهيئة — هذا حساب المالك (مدير)."
                return redirect(url_for("accounts"))
            except Exception as exc:
                error = str(exc)
    return render_template("setup.html", error=error)


# ---- حماية الدخول: إيقاف مؤقّت بعد محاولات خاطئة متكرّرة ----
_FAILS: dict = {}                  # (نوع، قيمة) → أوقات المحاولات الخاطئة
_LOCK_WINDOW = 15 * 60             # نافذة العدّ ومدّة الإيقاف (ثانية)
_LOCK_LIMITS = {"user": 5, "ip": 20}
_PENDING: dict = {}                # دخول ينتظر رمز الخطوة الثانية
_TOTP_LAST: dict = {}              # آخر خطوة زمنية قُبلت لكل مستخدم (منع التكرار)
_TOTP_SETUP: dict = {}             # سرّ قيد التفعيل لكل جلسة


def _client_ip() -> str:
    return request.remote_addr or "?"


def _ukey(username: str) -> str:
    return (username or "").strip().lower()[:64]


def _fail_keys(username: str) -> list:
    keys = [("ip", _client_ip())]
    if _ukey(username):
        keys.append(("user", _ukey(username)))
    return keys


def _lock_wait(username: str = "") -> int:
    """الثواني المتبقّية حتى يُفكّ الإيقاف (0 = الدخول مسموح)."""
    now, wait = time.time(), 0
    if len(_FAILS) > 5000:                     # تنظيف عناوين قديمة
        for k in [k for k, v in _FAILS.items() if not v or now - v[-1] > _LOCK_WINDOW]:
            _FAILS.pop(k, None)
    for k in _fail_keys(username):
        times = [t for t in _FAILS.get(k, []) if now - t < _LOCK_WINDOW]
        if times:
            _FAILS[k] = times
        else:
            _FAILS.pop(k, None)
        limit = _LOCK_LIMITS[k[0]]
        if len(times) >= limit:
            wait = max(wait, int(_LOCK_WINDOW - (now - times[-limit])) + 1)
    return wait


def _note_fail(username: str, what: str = "محاولة دخول فاشلة") -> None:
    now = time.time()
    for k in _fail_keys(username):
        _FAILS.setdefault(k, []).append(now)
    try:
        from hajj_app import audit
        # اسم غير موجود لا يُكتب كما هو (قد يكون كلمة مرور كُتبت في خانة الاسم)
        known = {a["username"].lower() for a in auth.list_accounts()}
        who = username.strip() if _ukey(username) in known else "اسم غير معروف"
        audit.record(what, f"{who} — من {_client_ip()}", user=who)
    except Exception:                              # noqa: BLE001
        pass


def _lock_msg(wait: int) -> str:
    return (f"محاولات خاطئة كثيرة — أُوقف الدخول مؤقّتاً. "
            f"حاول بعد {max(1, -(-wait // 60))} دقيقة.")


def _finish_login(hs, username: str, mode: str, remember: bool) -> None:
    """يفتح الجلسة بعد نجاح كلمة المرور (والرمز إن لزم)."""
    sid = secrets.token_hex(16)
    _SESSIONS[sid] = hs
    session["sid"] = sid
    session["mode"] = mode
    session["username"] = hs.username or username
    session["role"] = getattr(hs, "role_label", "")
    _csrf_token()               # (لا يُبدَّل: تبقى الصفحات المفتوحة صالحة للحفظ)
    session.permanent = bool(remember)                 # تذكّرني
    _FAILS.pop(("user", _ukey(username)), None)
    try:
        from hajj_app import audit
        audit.record("دخول", f"من {_client_ip()}", user=hs.username or username)
    except Exception:                              # noqa: BLE001
        pass


@app.route("/login", methods=["GET", "POST"])
def login():
    if not auth.is_configured():           # نشر جديد بلا حسابات → تهيئة المالك
        return redirect(url_for("setup"))
    error = ""
    mode = app_mode.UMRAH                  # الدخول الافتراضي: العمرة
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()[:64]
        password = request.form.get("password") or ""
        mode = _form_mode()
        remember = bool(request.form.get("remember"))
        wait = _lock_wait(username)
        if wait:
            error = _lock_msg(wait)
        else:
            try:
                app_mode.set_mode(mode)
                hs = auth.login(username, password)
            except Exception:                      # noqa: BLE001
                hs = None
            if hs is None:
                _note_fail(username)
                error = "اسم المستخدم أو كلمة المرور غير صحيحة."
            elif auth.has_totp(hs.username):       # الخطوة الثانية: رمز الجوال
                now = time.time()
                for k in [k for k, v in _PENDING.items() if v["exp"] < now]:
                    _PENDING.pop(k, None)
                pid = secrets.token_hex(16)
                _PENDING[pid] = {"hs": hs, "user": username, "mode": mode,
                                 "remember": remember, "exp": now + 300}
                session["p2fa"] = pid
                return redirect(url_for("login_2fa"))
            else:
                _finish_login(hs, username, mode, remember)
                return redirect(url_for("dashboard"))
    return render_template("login.html", error=error, modes=_MODE_CHOICES,
                           selected_mode=mode)


@app.route("/login/2fa", methods=["GET", "POST"])
def login_2fa():
    """الخطوة الثانية: رمز من تطبيق المصادقة في الجوال (٦ أرقام)."""
    from hajj_app import totp
    pid = session.get("p2fa")
    p = _PENDING.get(pid) if pid else None
    if not p or p["exp"] < time.time():
        _PENDING.pop(pid, None)
        session.pop("p2fa", None)
        return redirect(url_for("login"))
    error = ""
    if request.method == "POST":
        hs = p["hs"]
        wait = _lock_wait(p["user"])
        if wait:
            error = _lock_msg(wait)
        elif not auth.has_totp(hs.username):       # أُلغي أثناء الانتظار أو حُذف
            _PENDING.pop(pid, None)
            session.pop("p2fa", None)
            return redirect(url_for("login"))         # يُعاد الدخول بكلمة المرور
        else:
            ukey = hs.username.lower()
            step = totp.verify(auth.get_totp(hs) or "", request.form.get("code"),
                               last_step=_TOTP_LAST.get(ukey))
            if step is None:
                _note_fail(p["user"], "رمز دخول بخطوتين خاطئ")
                error = "الرمز غير صحيح أو انتهت مدّته — اكتب الرمز الظاهر الآن في التطبيق."
            else:
                _TOTP_LAST[ukey] = step
                _PENDING.pop(pid, None)
                session.pop("p2fa", None)
                _finish_login(hs, p["user"], p["mode"], p["remember"])
                return redirect(url_for("dashboard"))
    return render_template("login_2fa.html", error=error,
                           selected_mode=p["mode"], username=p["hs"].username)


@app.route("/recover", methods=["GET", "POST"])
def recover():
    """نسيت كلمة المرور (للمدير): إعادة تعيين عبر مفتاح الاسترداد ثم الدخول."""
    if not auth.is_configured():
        return redirect(url_for("setup"))
    error = ""
    mode = app_mode.UMRAH                  # الدخول الافتراضي: العمرة
    if request.method == "POST":
        rk = (request.form.get("recovery") or "").strip()
        pw = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""
        mode = _form_mode()
        wait = _lock_wait()
        if wait:
            error = _lock_msg(wait)
        elif pw != confirm:
            error = "كلمتا المرور غير متطابقتين."
        else:
            try:
                app_mode.set_mode(mode)
                hs = auth.reset_with_recovery_key(rk, pw,
                                                  allowed_roles=("admin",))
                sid = secrets.token_hex(16)
                _SESSIONS[sid] = hs
                session["sid"] = sid
                session["mode"] = mode
                session["username"] = hs.username
                session["role"] = getattr(hs, "role_label", "")
                _csrf_token()
                _audit("استرداد كلمة مرور (المدير)", hs.username)
                return redirect(url_for("dashboard"))
            except Exception as exc:
                if "مفتاح الاسترداد غير صحيح" in str(exc):
                    _note_fail("", "محاولة استرداد بمفتاح خاطئ")
                error = str(exc)
    return render_template("recover.html", error=error, modes=_MODE_CHOICES,
                           selected_mode=mode)


def _link_ok() -> bool:
    """روابط GET التي تغيّر الحالة (التبديل/الخروج) تحمل رمز الجلسة ‎?t=‎."""
    if not app.config.get("CSRF_ENABLED", True):
        return True
    good = session.get("csrf") or ""
    sent = request.args.get("t") or ""
    return bool(good) and hmac.compare_digest(sent.encode("utf-8"),
                                              good.encode("utf-8"))


@app.get("/logout")
def logout():
    if _sess() is not None and not _link_ok():     # رابط من موقع خارجي
        return redirect(url_for("dashboard"))
    _SESSIONS.pop(session.get("sid"), None)
    session.clear()
    return redirect(url_for("login"))


@app.get("/switch/<mode>")
def switch(mode):
    if mode in (app_mode.HAJJ, app_mode.UMRAH) and _link_ok():
        session["mode"] = mode
    return redirect(url_for("dashboard"))


@app.get("/dashboard")
def dashboard():
    if _sess() is None:
        return redirect(url_for("login"))
    records = _load_records()
    fin = stats.financial_summary(records)
    owe = stats.outstanding(records)
    kpis = [
        {"icon": "👤", "label": _noun(), "value": f"{fin.count:,}",
         "sub": "", "color": "#8A6E4B"},
        {"icon": "💰", "label": "المحصّل", "value": format_amount(fin.paid) or "0",
         "sub": f"{fin.collected_percent}% من الإجمالي", "color": "#2E7D5B"},
        {"icon": "⏳", "label": "المتبقّي",
         "value": format_amount(fin.remaining) or "0", "sub": "AED",
         "color": "#2C5AA0"},
        {"icon": "⚠", "label": "المتأخّرون عن السداد", "value": f"{len(owe):,}",
         "sub": "بحاجة متابعة", "color": "#C0392B"},
    ]
    progs = [{"name": name, "count": pf.count,
              "paid": format_amount(pf.paid) or "0",
              "remaining": format_amount(pf.remaining) or "0",
              "pct": pf.collected_percent}
             for name, pf in _by_group(records)]
    pcards = (_package_cards(records, storage.load_settings())
              if _mode() == app_mode.UMRAH else [])
    alerts_top = [dict(a, link=_alert_link(a)) for a in _alerts()[:6]]
    return render_template(
        "dashboard.html", kpis=kpis, progs=progs, pcards=pcards,
        alerts_top=alerts_top, active="dashboard", **_ctx())


# الحج: سنة هجرية (هـ) — العمرة: سنة ميلادية (م)
_HIJRI_YEARS = [str(y) for y in range(1445, 1456)]     # 1445..1455هـ
_GREG_YEARS = [str(y) for y in range(2025, 2036)]      # 2025..2035م
_DEFAULT_HIJRI = "1447"
_DEFAULT_GREG = "2026"


def _season_years() -> list:
    """قائمة سنوات الموسم حسب الوضع (هجرية للحج، ميلادية للعمرة)."""
    return _HIJRI_YEARS if _mode() == app_mode.HAJJ else _GREG_YEARS


def _season_suffix() -> str:
    return "هـ" if _mode() == app_mode.HAJJ else "م"


def _audit(action: str, details: str = "") -> None:
    """يسجّل «من فعل ماذا ومتى» في سجلّ التدقيق (يُعرض للمدير فقط).

    لا يرفع استثناءً كي لا يُعطّل العملية الأصلية.
    """
    try:
        from hajj_app import audit
        s = _sess()
        audit.record(action, details, user=(s.username if s else "—"))
    except Exception:                              # noqa: BLE001
        pass


@app.before_request
def _refresh_role():
    """الصلاحية تُقرأ من ملف الحسابات مع كل طلب: تغيير دور مستخدم (مثل إنزاله من
    «مدير») يسري فوراً على جلسته المفتوحة، وحذف حسابه يُخرجه."""
    s = _sess()
    if s is None:
        return None
    try:
        acc = next((a for a in auth.list_accounts()
                    if a["username"].lower() == s.username.lower()), None)
    except Exception:                              # noqa: BLE001
        return None
    if acc is None:                                # حُذف الحساب
        _SESSIONS.pop(session.get("sid"), None)
        session.clear()
        return redirect(url_for("login"))
    if acc["role"] != s.role:
        s.role = acc["role"] if acc["role"] in auth.ROLES else "viewer"
        session["role"] = s.role_label
    return None


@app.before_request
def _sync_mode():
    """يزامن وضع التخزين (حج/عمرة) مع جلسة المتصفّح قبل كل طلب.

    ملفّات الكشف والإعدادات مستقلّة لكل وضع؛ فبدون هذه المزامنة قد تُقرأ/تُكتب
    بيانات وضع في ملفّ الآخر (كما حدث مع الموسم والمصروفات).
    """
    try:
        if _sess() is not None:
            app_mode.set_mode(_mode())
    except Exception:                              # noqa: BLE001
        pass


# ---- حماية النماذج من الطلبات المزوّرة (CSRF) ----
# رمز سرّي لكل جلسة متصفّح: يُضاف تلقائياً لكل نموذج POST في الصفحات (وكترويسة
# لطلبات fetch)، ويُرفض أي POST لا يحمله.
_FORM_TAG_RE = re.compile(r"<form\b[^<>]*>", re.I)
_POST_ATTR_RE = re.compile(r"\smethod\s*=\s*[\"']?post\b", re.I)
_SCRIPT_RE = re.compile(r"(<script\b.*?</script\s*>)", re.I | re.S)
_CSRF_JS = (
    "(function(){var m=document.querySelector('meta[name=csrf-token]');"
    "if(!m)return;var t=m.content,f=window.fetch;"
    "if(f){window.fetch=function(u,o){o=o||{};"
    "var x=(o.method||(u&&u.method)||'GET').toUpperCase();"
    "if(x!=='GET'&&x!=='HEAD'){try{var l=new URL((u&&u.url)||u,location.href);"
    "if(l.origin===location.origin){var h=new Headers(o.headers||{});"
    "h.set('X-CSRF-Token',t);o.headers=h;}}catch(e){}}"
    "return f.call(this,u,o);};}"
    "document.addEventListener('submit',function(e){var fm=e.target,"
    "b=e.submitter,mm=((b&&b.getAttribute('formmethod'))||"
    "fm.getAttribute('method')||'get').toLowerCase();"
    "if(mm==='post'&&!fm.querySelector('input[name=csrf_token]')){"
    "var i=document.createElement('input');i.type='hidden';"
    "i.name='csrf_token';i.value=t;fm.appendChild(i);"
    "if((fm.getAttribute('method')||'get').toLowerCase()!=='post')"
    "setTimeout(function(){i.remove();},0);}},true);})();")
_CSRF_FAIL = """<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>انتهت صلاحية الصفحة</title></head>
<body style="font-family:Tahoma,Arial,sans-serif;background:#F4F1EC;padding:40px">
<div style="max-width:520px;margin:auto;background:#fff;border-radius:14px;padding:26px;
box-shadow:0 4px 18px rgba(0,0,0,.08)"><h2 style="margin-top:0">⚠ انتهت صلاحية الصفحة</h2>
<p>لم يُنفَّذ الطلب لأن الصفحة قديمة أو أُرسلت من مصدر غير موثوق (حماية الحساب).</p>
<p>ارجع إلى الصفحة، أعد تحميلها، ثم حاول مرّة أخرى.</p>
<p><a href="{back}">↩ رجوع</a></p></div></body></html>"""


def _csrf_token() -> str:
    tok = session.get("csrf")
    if not tok:
        tok = secrets.token_urlsafe(32)
        session["csrf"] = tok
    return tok


@app.context_processor
def _csrf_ctx():
    return {"csrf_token": _csrf_token}


@app.before_request
def _csrf_protect():
    """يرفض أي POST لا يحمل رمز الجلسة (في النموذج أو في ترويسة X-CSRF-Token)."""
    if request.method != "POST" or not app.config.get("CSRF_ENABLED", True):
        return None
    sent = (request.headers.get("X-CSRF-Token")
            or request.form.get("csrf_token") or "")
    good = session.get("csrf") or ""
    if good and hmac.compare_digest(str(sent).encode("utf-8"),
                                    str(good).encode("utf-8")):
        return None
    back = request.referrer or url_for("index")
    if not back.startswith(request.host_url):
        back = url_for("index")
    import html as _html
    return _CSRF_FAIL.replace("{back}", _html.escape(back)), 400, {
        "Content-Type": "text/html; charset=utf-8"}


@app.after_request
def _csrf_inject(resp):
    """يضيف رمز الحماية لكل نماذج POST في صفحات HTML، وسكربتاً صغيراً يرسله مع
    طلبات fetch ومع أزرار formmethod=post."""
    if (not app.config.get("CSRF_ENABLED", True) or resp.direct_passthrough
            or resp.mimetype != "text/html" or resp.status_code >= 400):
        return resp
    try:
        body = resp.get_data(as_text=True)
    except Exception:                              # noqa: BLE001
        return resp
    if "<form" not in body and "fetch(" not in body:
        return resp
    tok = _csrf_token()
    field = f'<input type="hidden" name="csrf_token" value="{tok}">'

    def _add(m):
        tag = m.group(0)
        return tag + field if _POST_ATTR_RE.search(tag) else tag
    # الحقل يُضاف للوسوم الحقيقية فقط، لا لنصوص داخل <script> (بيانات المحرّرات)
    parts = _SCRIPT_RE.split(body)
    new = "".join(p if i % 2 else _FORM_TAG_RE.sub(_add, p)
                  for i, p in enumerate(parts))
    head = f'<meta name="csrf-token" content="{tok}"><script>{_CSRF_JS}</script>'
    if "</head>" in new:
        new = new.replace("</head>", head + "</head>", 1)
    elif "<body" in new:
        new = re.sub(r"(<body\b[^>]*>)", lambda m: m.group(1) + head, new, count=1)
    if new != body:
        resp.set_data(new)
    return resp


# ---- النسخ الاحتياطي: نسخة يومية تلقائية + تنزيل مشفّر + استعادة (للمدير) ----
@app.before_request
def _daily_backup():
    if _sess() is None or request.endpoint in ("static", "service_worker"):
        return None
    try:
        from webapp import backup
        backup.daily()
    except Exception:                              # noqa: BLE001
        pass
    return None


def _backup_admin():
    s = _sess()
    if s is None:
        return None, redirect(url_for("login"))
    if not s.is_admin:
        return None, redirect(url_for("dashboard"))
    return s, None


@app.get("/backup")
def backup_page():
    s, bad = _backup_admin()
    if bad:
        return bad
    from webapp import backup
    snaps = []
    for p in backup.list_snapshots():
        kind = p.stem.split("_", 2)[-1]
        snaps.append({"name": p.name, "size": backup.human_size(p.stat().st_size),
                      "when": p.stem[:10] + " " + p.stem[11:13] + ":" + p.stem[13:15],
                      "kind": {"auto": "يومية تلقائية", "manual": "يدوية",
                               "before-restore": "قبل استعادة"}.get(kind, kind)})
    return render_template("backup.html", active="backup", snaps=snaps,
                           keep=backup.KEEP_DAYS, msg=session.pop("bk_msg", ""),
                           err=session.pop("bk_err", ""), **_ctx())


@app.post("/backup/now")
def backup_now():
    s, bad = _backup_admin()
    if bad:
        return bad
    from webapp import backup
    p = backup.snapshot("manual")
    backup.prune()
    _audit("نسخة احتياطية يدوية", p.name)
    session["bk_msg"] = f"✅ حُفظت نسخة على الخادم: {p.name}"
    return redirect(url_for("backup_page"))


@app.post("/backup/download")
def backup_download():
    """نسخة كاملة مشفّرة بكلمة مرور تُنزَّل لتُحفظ خارج الخادم."""
    s, bad = _backup_admin()
    if bad:
        return bad
    from webapp import backup
    pw = request.form.get("password") or ""
    if len(pw) < 8 or pw != (request.form.get("confirm") or ""):
        session["bk_err"] = "كلمة مرور النسخة ٨ خانات على الأقل، ويجب أن تتطابق مع التأكيد."
        return redirect(url_for("backup_page"))
    z = backup.tempfile_path(".zip")
    enc = backup.tempfile_path(".almbak")
    try:
        n = backup.build_zip(z, with_images=bool(request.form.get("images")))
        backup.encrypt_file(z, enc, pw)
    finally:
        z.unlink(missing_ok=True)
    _audit("تنزيل نسخة احتياطية", f"{n} ملفّاً")
    from datetime import datetime as _dt
    # يُرسل من الملف مباشرةً (لا يُحمَّل كاملاً في الذاكرة) ثم يُحذف
    resp = send_file(str(enc), mimetype="application/octet-stream",
                     as_attachment=True,
                     download_name=f"almustafa-backup-{_dt.now():%Y-%m-%d}.almbak")

    def _cleanup():
        try:
            enc.unlink(missing_ok=True)
        except OSError:
            pass
    resp.call_on_close(_cleanup)
    return resp


@app.post("/backup/restore")
def backup_restore():
    """استعادة من ملف منزّل (بكلمة مروره) أو من نسخة على الخادم — يُخرج الجميع."""
    s, bad = _backup_admin()
    if bad:
        return bad
    from webapp import backup
    snap = (request.form.get("snapshot") or "").strip()
    tmp_zip = backup.tempfile_path(".zip")
    try:
        if snap:
            src = backup.snaps_dir() / snap
            if "/" in snap or "\\" in snap or not src.is_file():
                raise ValueError("النسخة غير موجودة.")
            import shutil
            shutil.copyfile(src, tmp_zip)
        else:
            up = request.files.get("file")
            if not up or not up.filename:
                raise ValueError("اختر ملف النسخة (.almbak).")
            enc = backup.tempfile_path(".almbak")
            try:
                up.save(enc)
                backup.decrypt_file(enc, tmp_zip, request.form.get("password") or "")
            finally:
                enc.unlink(missing_ok=True)
        import zipfile
        if not zipfile.is_zipfile(tmp_zip):
            raise ValueError("الملف ليس نسخة صالحة.")
        # نسخة أمان كاملة (مع الصور) من الحالي — للتراجع إن لزم
        safety = backup.snapshot("before-restore", with_images=True)
        done = backup.restore_zip(tmp_zip)
    except ValueError as exc:
        session["bk_err"] = str(exc)
        return redirect(url_for("backup_page"))
    finally:
        tmp_zip.unlink(missing_ok=True)
    _audit("استعادة نسخة احتياطية",
           f"{snap or 'ملف منزّل'} — {len(done)} ملفّاً (نسخة أمان: {safety.name})")
    # البيانات تغيّرت (وقد يتغيّر مفتاحها): خروج الجميع وإعادة الدخول
    for _d in (_SESSIONS, _ALERTS_CACHE, _PENDING, _TOTP_SETUP, _TOTP_LAST, _FAILS):
        _d.clear()
    session.clear()
    return redirect(url_for("login", restored=1))


# ---- إلزام الدخول بخطوتين (إن فعّله المدير لكل الحسابات) ----
_2FA_FREE = {"account_2fa", "logout", "static", "version", "login", "login_2fa",
             "setup", "recover", "switch", "index", "service_worker",
             "verify_doc", "person_page"}


@app.before_request
def _require_2fa():
    s = _sess()
    if s is None or request.endpoint in _2FA_FREE:
        return None
    try:
        if auth.get_policy().get("require_totp") and not auth.has_totp(s.username):
            return redirect(url_for("account_2fa", need=1))
    except Exception:                              # noqa: BLE001
        return None
    return None


def _qr_svg(data: str, size: int = 200) -> str:
    """رمز QR كـ SVG داخل الصفحة (reportlab، بلا مكتبات إضافية)."""
    try:
        from reportlab.graphics import renderSVG
        from reportlab.graphics.barcode.qr import QrCodeWidget
        from reportlab.graphics.shapes import Drawing
        w = QrCodeWidget(data)
        x0, y0, x1, y1 = w.getBounds()
        d = Drawing(size, size, transform=[size / (x1 - x0), 0, 0,
                                           size / (y1 - y0), 0, 0])
        d.add(w)
        svg = renderSVG.drawToString(d)
        return svg[svg.find("<svg"):]
    except Exception:                              # noqa: BLE001
        return ""


@app.route("/account/2fa", methods=["GET", "POST"])
def account_2fa():
    """تفعيل/إلغاء الدخول بخطوتين لحساب المستخدم نفسه."""
    from hajj_app import totp
    s = _sess()
    if s is None:
        return redirect(url_for("login"))
    sid = session.get("sid")
    ukey = s.username.lower()
    enabled = auth.has_totp(s.username)
    required = bool(auth.get_policy().get("require_totp"))
    msg = err = ""
    wait = _lock_wait(s.username) if request.method == "POST" else 0
    if wait:
        err = _lock_msg(wait)
    elif request.method == "POST":
        action = request.form.get("action")
        code = request.form.get("code")
        if action == "enable" and not enabled:
            secret = _TOTP_SETUP.get(sid)
            step = totp.verify(secret, code) if secret else None
            if step is None:
                _note_fail(s.username, "رمز تفعيل الدخول بخطوتين خاطئ")
                err = ("الرمز غير صحيح — تأكّد أنك مسحت الرمز الظاهر هنا، وأن وقت "
                       "الجوال مضبوط تلقائياً، ثم اكتب الرمز الحالي.")
            else:
                auth.set_totp(s, secret)
                _TOTP_SETUP.pop(sid, None)
                _TOTP_LAST[ukey] = step
                _audit("تفعيل الدخول بخطوتين", s.username)
                enabled, msg = True, "✅ فُعِّل الدخول بخطوتين لحسابك."
        elif action == "disable" and enabled:
            if required:
                err = "الدخول بخطوتين إلزامي لكل الحسابات (قرار المدير) — لا يُلغى."
            else:
                step = totp.verify(auth.get_totp(s) or "", code,
                                   last_step=_TOTP_LAST.get(ukey))
                if step is None:
                    _note_fail(s.username, "رمز إلغاء الدخول بخطوتين خاطئ")
                    err = "الرمز غير صحيح — اكتب الرمز الظاهر الآن في التطبيق."
                else:
                    auth.set_totp(s, None)
                    _TOTP_LAST[ukey] = step
                    _audit("إلغاء الدخول بخطوتين", s.username)
                    enabled, msg = False, "أُلغي الدخول بخطوتين لحسابك."
    setup = None
    if not enabled:
        secret = _TOTP_SETUP.get(sid) or totp.new_secret()
        _TOTP_SETUP[sid] = secret
        setup = {"secret": totp.pretty(secret),
                 "qr": _qr_svg(totp.otpauth_uri(secret, s.username))}
    return render_template("account_2fa.html", active="account2fa",
                           enabled=enabled, required=required,
                           need=bool(request.args.get("need")), setup=setup,
                           msg=msg, err=err, **_ctx())


def _season() -> str:
    """سنة الموسم الحالي (لكل وضع) — من الإعدادات أو الافتراضي حسب التقويم."""
    default = _DEFAULT_HIJRI if _mode() == app_mode.HAJJ else _DEFAULT_GREG
    try:
        app_mode.set_mode(_mode())               # مزامنة ملفّ الإعدادات مع الوضع
        v = str(storage.load_settings().get("season_year", "") or "").strip()
    except Exception:
        v = ""
    return v or default


def _side_packages() -> list:
    """باقات برامج العمرة للقائمة الجانبية (فارغة في الحج)."""
    if _mode() != app_mode.UMRAH or _sess() is None:
        return []
    try:
        from hajj_app import umrah
        return umrah.load_packages(storage.load_settings())
    except Exception:                              # noqa: BLE001
        return []


def _ctx() -> dict:
    """سياق مشترك للقوالب (الوضع/النوع/زر التبديل/الصلاحيات/الموسم)."""
    s = _sess()
    other = app_mode.UMRAH if _mode() == app_mode.HAJJ else app_mode.HAJJ
    return dict(
        noun=_noun(), mode=_mode(),
        other=other, other_label=app_mode.theme(other)["noun"],
        theme=app_mode.theme(_mode()), other_theme=app_mode.theme(other),
        favicon=app_mode.favicon_href(_mode()),
        packages=_side_packages(),
        season=_season(), season_suffix=_season_suffix(),
        is_admin=bool(s is not None and s.is_admin),
        can_edit=bool(s is not None and s.can_edit),
        alert_count=_alert_count(),
        search_q=(request.args.get("q") or "") if request.endpoint == "search_page" else "")


# ---- الإشعارات (تُحسب من البيانات، وتُخزَّن مؤقّتاً حتى تتغيّر الملفّات) ----
_ALERTS_CACHE: dict = {}


def _alerts() -> list:
    """إشعارات النظام الحالي — تُعاد حسابها فقط حين يتغيّر ملف البيانات أو
    الإعدادات أو اليوم."""
    from datetime import date as _date
    from webapp import alerts as _al
    if _sess() is None:
        return []
    def _mt(p):
        try:
            return os.path.getmtime(p)
        except OSError:
            return 0
    key = (_mode(), _mt(storage.default_data_path()), _mt(storage.settings_path()),
           _date.today().isoformat())
    hit = _ALERTS_CACHE.get(key)
    if hit is None:
        try:
            records = _load_records()
            settings = storage.load_settings()
            hit = (_al.umrah_alerts(records, settings) if _mode() == app_mode.UMRAH
                   else _al.hajj_alerts(records, settings))
        except Exception:                          # noqa: BLE001
            hit = []
        _ALERTS_CACHE.clear()
        _ALERTS_CACHE[key] = hit
    return hit


def _alert_count() -> int:
    try:
        return sum(1 for a in _alerts() if a["level"] in ("danger", "warn"))
    except Exception:                              # noqa: BLE001
        return 0


def _alert_link(a: dict) -> str:
    k, ref = a.get("kind"), a.get("ref")
    if k == "program" and ref:
        return url_for("program_edit", code=ref)
    if k == "finance":
        return url_for("finance")
    if k == "quality":
        return url_for("quality_report")
    if k == "travel":
        return url_for("travel_list")
    return url_for("dashboard")


@app.get("/notifications")
def notifications():
    if _sess() is None:
        return redirect(url_for("login"))
    items = [dict(a, link=_alert_link(a)) for a in _alerts()]
    return render_template("notifications.html", active="notifications",
                           items=items, **_ctx())


@app.get("/search")
def search_page():
    """البحث السريع الشامل (خانة أعلى كل صفحة)."""
    if _sess() is None:
        return redirect(url_for("login"))
    from webapp import search as _sr
    q = (request.args.get("q") or "").strip()
    groups = []
    if q:
        records = _load_records()
        try:
            docs = storage.load_documents(session=_sess())
        except Exception:                          # noqa: BLE001
            docs = []
        groups = _sr.search(q, records, storage.load_settings(), _mode(), docs)
        for g in groups:
            for it in g["items"]:
                k, ref = it["kind"], it["ref"]
                if k == "record":
                    it["link"] = url_for("hujjaj_edit", idx=ref,
                                         fp=_rec_token(records[ref]))
                    it["extra"] = url_for("record_docs", idx=ref,
                                          fp=_rec_token(records[ref]))
                elif k == "program":
                    it["link"] = url_for("program_edit", code=ref)
                elif k == "package":
                    it["link"] = url_for("programs", package=ref)
                elif k == "quote":
                    it["link"] = url_for("quote_edit", code=ref[0], num=ref[1])
                elif k == "pricing":
                    it["link"] = url_for("pricing_edit", num=ref)
                elif k == "archive":
                    it["link"] = url_for("archive_pdf", doc_id=ref)
        # نتيجة واحدة فقط ← افتحها مباشرة
        if len(groups) == 1 and groups[0]["total"] == 1:
            return redirect(groups[0]["items"][0]["link"])
    return render_template("search.html", active="search", q=q, groups=groups,
                           total=sum(g["total"] for g in groups), **_ctx())


def _package_cards(records, settings) -> list:
    """بطاقة لكل باقة برامج (العمرة): الرحلات، المعتمرون، المقاعد، أقرب مغادرة."""
    from datetime import date as _date
    from hajj_app import umrah
    from webapp.alerts import _d
    trips = umrah.load_trips(settings)
    today = _date.today()
    cards = []
    for i, pkg in enumerate(umrah.load_packages(settings)):
        ts = [t for t in trips if str(t.package or "").strip() == pkg]
        n = cap = 0
        upcoming = []
        for t in ts:
            k = len(umrah.trip_pilgrims(records, t.code))
            n += k
            try:
                cap += int(float(str(t.capacity or "").strip() or 0))
            except ValueError:
                pass
            d = _d(t.depart_date)
            if d and d >= today:
                upcoming.append(d)
        band = _PROG_COLORS[i % len(_PROG_COLORS)][0]
        cards.append({"name": pkg, "trips": len(ts), "count": n, "cap": cap,
                      "left": cap - n if cap else None,
                      "pct": min(100, round(n * 100 / cap)) if cap else 0,
                      "next": min(upcoming).isoformat() if upcoming else "",
                      "color": band, "link": url_for("programs", package=pkg)})
    return cards


_BUILD_TAG = "2026-10-28f · الصلاحية تسري فوراً على الجلسات المفتوحة"
_BUILD_ID = _BUILD_TAG.split(" · ")[0]      # يظهر في رأس صفحات المحرّر


_SW_JS = r"""// عامل خدمة البورتال: يحفظ الملفّات الثابتة فقط (التنسيق والأيقونات) لتسريع
// الفتح، ولا يحفظ أي صفحة فيها بيانات. بلا اتصال تظهر صفحة توضيحية.
const CACHE = 'almustafa-__BUILD__';
const ASSETS = ['/static/style.css', '/static/logo.png', '/static/icons/icon-192.png',
                '/static/icons/icon-512.png', '/static/manifest.webmanifest'];
const OFFLINE = '<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">' +
  '<meta name="viewport" content="width=device-width, initial-scale=1"><title>لا يوجد اتصال</title></head>' +
  '<body style="font-family:Tahoma,Arial,sans-serif;background:#F4F1EC;text-align:center;padding:60px 20px">' +
  '<h2>📡 لا يوجد اتصال بالإنترنت</h2><p>البورتال يحتاج اتصالاً لعرض البيانات المحدّثة.</p>' +
  '<p><a href="/dashboard" onclick="location.reload();return false">🔄 إعادة المحاولة</a></p></body></html>';
self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE)
    .map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const r = e.request;
  if (r.method !== 'GET') return;
  const u = new URL(r.url);
  if (u.origin !== location.origin) return;
  if (u.pathname.startsWith('/static/')) {
    e.respondWith(fetch(r).then(resp => {
      const cp = resp.clone(); caches.open(CACHE).then(c => c.put(r, cp)); return resp;
    }).catch(() => caches.match(r)));
    return;
  }
  if (r.mode === 'navigate') {
    e.respondWith(fetch(r).catch(() => new Response(OFFLINE,
      {headers: {'Content-Type': 'text/html; charset=utf-8'}})));
  }
});
"""


@app.get("/sw.js")
def service_worker():
    """عامل الخدمة من جذر الموقع (ليشمل كل الصفحات) — بلا تسجيل دخول."""
    body = _SW_JS.replace("__BUILD__", re.sub(r"[^0-9a-z]", "", _BUILD_TAG.split()[0]))
    return body, 200, {"Content-Type": "application/javascript; charset=utf-8",
                       "Cache-Control": "no-cache", "Service-Worker-Allowed": "/"}


@app.get("/version")
def version():
    """كشف النسخة الجارية فعلاً على الخادم (للتشخيص) — بلا تسجيل دخول."""
    return (f"BUILD {_BUILD_TAG}", 200,
            {"Content-Type": "text/plain; charset=utf-8",
             "Cache-Control": "no-store, max-age=0"})


@app.route("/season", methods=["GET", "POST"])
def season_page():
    """تحديد موسم الحج/العمرة (السنة الهجرية) — مستقلّ لكل وضع، للمحرّرين."""
    if _sess() is None:
        return redirect(url_for("login"))
    app_mode.set_mode(_mode())                   # الإعدادات مستقلّة لكل وضع
    saved = ""
    if request.method == "POST" and _sess().can_edit:
        year = (request.form.get("season_year") or "").strip()
        if year in _season_years():
            settings = storage.load_settings()
            settings["season_year"] = year
            try:
                storage.save_settings(settings)
                saved = year
                _audit("تحديد الموسم", f"{year}{_season_suffix()}")
            except Exception:
                pass
        return redirect(url_for("season_page", saved=saved or year))
    cal_label = ("السنة الهجرية" if _mode() == app_mode.HAJJ
                 else "السنة الميلادية")
    return render_template("season.html", active="season",
                           years=_season_years(), current=_season(),
                           cal_label=cal_label, saved=request.args.get("saved"),
                           **_ctx())


@app.get("/accounts")
def accounts():
    """إدارة الحسابات عن بُعد — للمدير فقط: عرض/إضافة/تغيير الصلاحية/حذف."""
    s = _sess()
    if s is None:
        return redirect(url_for("login"))
    if not s.is_admin:
        return render_template("accounts.html", active="accounts",
                               forbidden=True, accounts=[], roles=[], **_ctx())
    rows = [{"username": a["username"], "role": a["role"],
             "role_label": auth.ROLE_LABELS.get(a["role"], a["role"]),
             "updated": (a.get("updated_at") or "").replace("T", "  "),
             "totp": a.get("totp", False),
             "locked": bool(_FAILS.get(("user", _ukey(a["username"])))
                            and len([t for t in _FAILS[("user", _ukey(a["username"]))]
                                     if time.time() - t < _LOCK_WINDOW])
                            >= _LOCK_LIMITS["user"]),
             "me": a["username"].lower() == s.username.lower()}
            for a in auth.list_accounts()]
    return render_template(
        "accounts.html", active="accounts", forbidden=False, accounts=rows,
        require_totp=bool(auth.get_policy().get("require_totp")),
        roles=[(r, auth.ROLE_LABELS[r]) for r in auth.ROLES],
        recovery_key=session.pop("acc_key", None),
        added_user=session.pop("acc_added", None),
        msg=session.pop("acc_msg", ""), err=session.pop("acc_err", ""), **_ctx())


@app.post("/accounts/add")
def accounts_add():
    s = _sess()
    if s is None:
        return redirect(url_for("login"))
    try:
        key = auth.add_account(
            s, (request.form.get("username") or "").strip(),
            request.form.get("password") or "",
            request.form.get("role") or "viewer")
        session["acc_key"] = key
        _u = (request.form.get("username") or "").strip()
        session["acc_added"] = _u
        session["acc_msg"] = "أُضيف الحساب — سلّم صاحبه كلمة المرور ومفتاح الاسترداد."
        _audit("إضافة حساب", f"{_u} ({request.form.get('role') or 'viewer'})")
    except Exception as exc:
        session["acc_err"] = str(exc)
    return redirect(url_for("accounts"))


@app.post("/accounts/<username>/role")
def accounts_role(username):
    s = _sess()
    if s is None:
        return redirect(url_for("login"))
    try:
        auth.set_role(s, username, request.form.get("role") or "viewer")
        session["acc_msg"] = f"غُيّرت صلاحية «{username}»."
        _audit("تغيير صلاحية", f"{username} → {request.form.get('role') or 'viewer'}")
    except Exception as exc:
        session["acc_err"] = str(exc)
    return redirect(url_for("accounts"))


@app.post("/accounts/<username>/password")
def accounts_password(username):
    """إعادة تعيين كلمة مرور حساب — للمدير (لحلّ حساب لا يستطيع الدخول)."""
    s = _sess()
    if s is None:
        return redirect(url_for("login"))
    try:
        rk = auth.admin_set_password(s, username,
                                     request.form.get("password") or "")
        session["acc_msg"] = f"غُيّرت كلمة مرور «{username}» — سلّمها لصاحبه."
        _audit("إعادة تعيين كلمة مرور", username)
        if rk:
            session["acc_key"] = rk
            session["acc_added"] = username
    except Exception as exc:
        session["acc_err"] = str(exc)
    return redirect(url_for("accounts"))


@app.post("/accounts/<username>/2fa-reset")
def accounts_2fa_reset(username):
    """إلغاء الدخول بخطوتين لحساب (ضاع جوال صاحبه) — للمدير."""
    s = _sess()
    if s is None:
        return redirect(url_for("login"))
    try:
        auth.admin_clear_totp(s, username)
        session["acc_msg"] = (f"أُلغي الدخول بخطوتين لـ«{username}» — يفعّله من "
                              "جديد من «🔐 الدخول بخطوتين».")
        _audit("إلغاء الدخول بخطوتين (المدير)", username)
    except Exception as exc:
        session["acc_err"] = str(exc)
    return redirect(url_for("accounts"))


@app.post("/accounts/<username>/unlock")
def accounts_unlock(username):
    """فكّ إيقاف الدخول عن حساب (بعد محاولات خاطئة) — للمدير."""
    s = _sess()
    if s is None:
        return redirect(url_for("login"))
    if s.is_admin:
        _FAILS.pop(("user", _ukey(username)), None)
        session["acc_msg"] = f"فُكّ إيقاف الدخول عن «{username}»."
        _audit("فكّ إيقاف الدخول", username)
    return redirect(url_for("accounts"))


@app.post("/accounts/2fa-policy")
def accounts_2fa_policy():
    """إلزام كل الحسابات بالدخول بخطوتين — للمدير."""
    s = _sess()
    if s is None:
        return redirect(url_for("login"))
    req = bool(request.form.get("require"))
    try:
        auth.set_policy(s, require_totp=req)
        session["acc_msg"] = ("صار الدخول بخطوتين إلزامياً لكل الحسابات."
                              if req else "صار الدخول بخطوتين اختيارياً.")
        _audit("سياسة الدخول بخطوتين", "إلزامي" if req else "اختياري")
    except Exception as exc:
        session["acc_err"] = str(exc)
    return redirect(url_for("accounts"))


@app.post("/accounts/<username>/delete")
def accounts_delete(username):
    s = _sess()
    if s is None:
        return redirect(url_for("login"))
    try:
        auth.remove_account(s, username)
        session["acc_msg"] = f"حُذف الحساب «{username}»."
        _audit("حذف حساب", username)
    except Exception as exc:
        session["acc_err"] = str(exc)
    return redirect(url_for("accounts"))


def _noun_singular() -> str:
    return "الحاج" if _mode() == app_mode.HAJJ else "المعتمر"


def _label(key: str) -> str:
    lbl = BY_KEY[key].label if key in BY_KEY else key
    if _mode() == app_mode.UMRAH:
        lbl = lbl.replace("الحاج", "المعتمر").replace("حاج", "معتمر")
    return lbl


# حقول لوحة «تصفية الكشف» (تُملأ قيمها من البيانات) — كنسخة سطح المكتب
_FILTER_FIELDS = [
    ("group", "المجموعة"), ("hotel", "الفندق"), ("room_type", "نوع الغرفة"),
    ("nationality_ar", "الجنسية"), ("airline", "الطيران"), ("sex", "الجنس"),
    ("executive_service", "التنفيذي"), ("transport", "المواصلات"),
    ("wheelchair", "كرسي متحرك"), ("notes", "ملاحظات"),
]
_SORT_FIELDS = [
    ("", "— بدون ترتيب —"), ("name", "الاسم"), ("__group__", "البرنامج"),
    ("hotel", "الفندق"), ("room_type", "نوع الغرفة"),
    ("nationality_ar", "الجنسية"), ("passport_number", "رقم الجواز"),
]


def _list_filtered(records, gattr):
    """يطبّق البحث والفلاتر والترتيب من معطيات الطلب؛ يعيد [(idx, record)]."""
    q = (request.args.get("q") or "").strip().lower()
    sel = {}
    for key, _l in _FILTER_FIELDS:
        v = (request.args.get("flt_" + key) or "").strip()
        if v:
            sel[key] = v
    sort = (request.args.get("sort") or "").strip()
    out = []
    for i, r in enumerate(records):
        if q and q not in " ".join(str(getattr(r, k, "") or "") for k in
                                   ("full_name_ar", "full_name_en",
                                    "passport_number", "phone",
                                    "reference_number")).lower():
            continue
        if any(str(getattr(r, key, "") or "").strip() != val
               for key, val in sel.items()):
            continue
        out.append((i, r))
    if sort:
        sattr = (gattr if sort == "__group__"
                 else "full_name_ar" if sort == "name" else sort)
        out.sort(key=lambda t: str(getattr(t[1], sattr, "") or ""))
    return out


@app.get("/hujjaj/export.pdf")
def hujjaj_export_pdf():
    """معاينة PDF للنتائج المفلترة الحالية (نفس معطيات القائمة)."""
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app import pdf_io
    recs = [r for _i, r in _list_filtered(_load_records(), _group_attr())]
    title = f"كشف {_noun()} — موسم {_season()}{_season_suffix()}"
    return _pdf_response(lambda p: pdf_io.export_pdf(recs, p, title=title),
                         "list.pdf")


@app.get("/hujjaj/export.xlsx")
def hujjaj_export_xlsx():
    """تصدير إكسل للنتائج المفلترة الحالية."""
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app import excel_io
    recs = [r for _i, r in _list_filtered(_load_records(), _group_attr())]
    p = _tmp(".xlsx")
    excel_io.export_excel(recs, p)
    return send_file(
        p, as_attachment=True, download_name="hujjaj.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument."
                 "spreadsheetml.sheet")


@app.get("/hujjaj")
def hujjaj():
    if _sess() is None:
        return redirect(url_for("login"))
    records = _load_records()
    gattr = _group_attr()                          # program (حج) / trip (عمرة)
    q = (request.args.get("q") or "").strip()
    ql = q.lower()

    def _distinct(attr):
        return sorted({str(getattr(r, attr, "") or "").strip() for r in records
                       if str(getattr(r, attr, "") or "").strip()})

    # لوحة تصفية الكشف (نفس حقول سطح المكتب)
    sel = {}
    for key, _label in _FILTER_FIELDS:
        v = (request.args.get("flt_" + key) or "").strip()
        if v:
            sel[key] = v
    filteropts = [(key, label, _distinct(key)) for key, label in _FILTER_FIELDS]
    sort = (request.args.get("sort") or "").strip()

    indexed = _list_filtered(records, gattr)        # بحث + فلاتر + ترتيب

    total = len(indexed)
    pages = max(1, (total + _PAGE - 1) // _PAGE)
    try:
        page = max(1, min(pages, int(request.args.get("page", 1))))
    except ValueError:
        page = 1
    offset = (page - 1) * _PAGE
    rows = []
    for i, r in indexed[offset:offset + _PAGE]:
        st = str(getattr(r, "status", "") or "").strip()
        rows.append({
            "idx": i,
            "name": getattr(r, "full_name_ar", "") or getattr(
                r, "full_name_en", "") or "—",
            "passport": getattr(r, "passport_number", "") or "—",
            "program": str(getattr(r, gattr, "") or "") or "—",
            "phone": getattr(r, "phone", "") or "—",
            "status": st, "status_cls": _STATUS_CLS.get(st, ""),
            "remaining": format_amount(remaining_amount(r)) or "0",
        })
    qs = {"q": q, "sort": sort}                     # لحفظ الفلاتر عبر الصفحات
    for key, val in sel.items():
        qs["flt_" + key] = val
    return render_template("hujjaj.html", active="hujjaj", rows=rows, q=q,
                           filteropts=filteropts, sel=sel, sort=sort,
                           sortfields=_SORT_FIELDS, any_filter=bool(sel or sort),
                           qs=qs, total=total, page=page, pages=pages,
                           offset=offset, **_ctx())


# أنواع المستندات المستقلّة (بند «المستندات») — تشمل الحزمة
_DOC_KINDS = [
    ("receipt", "🧾", "سند قبض", "إيصال استلام مبلغ من العميل."),
    ("invoice", "🧾", "فاتورة ضريبية", "فاتورة بقيمة البرنامج والضريبة."),
    ("contract", "📜", "عقد خدمات", "عقد الخدمات بين المكتب والعميل."),
    ("voucher", "🏨", "فاوتشر فندق", "قسيمة حجز الفندق للإبراز عند الوصول."),
    ("treq", "🚖", "طلب حجز مواصلات", "طلب حجز مواصلات موجّه للناقل."),
    ("packet", "📦", "حزمة المستندات", "الجواز والبطاقة والسند والعقد في PDF واحد."),
]
_DOC_KIND_LABEL = {k: lbl for k, _ic, lbl, _d in _DOC_KINDS}


@app.get("/documents")
def documents():
    """بند «المستندات» المستقلّ: قائمة أنواع المستندات (اختر النوع ثم الشخص)."""
    if _sess() is None:
        return redirect(url_for("login"))
    return render_template("documents.html", active="documents",
                           docs=_DOC_KINDS, **_ctx())


@app.get("/documents/<kind>")
def documents_pick(kind):
    """اختيار الشخص لإصدار مستند من النوع المحدّد (بحث في السجلات)."""
    if _sess() is None:
        return redirect(url_for("login"))
    if kind not in _DOC_KIND_LABEL:
        return redirect(url_for("documents"))
    records = _load_records()
    q = (request.args.get("q") or "").strip()
    indexed = list(enumerate(records))
    if q:
        ql = q.lower()
        indexed = [(i, r) for i, r in indexed if ql in " ".join(str(
            getattr(r, k, "") or "") for k in
            ("full_name_ar", "full_name_en", "passport_number", "phone",
             "reference_number")).lower()]
    total = len(indexed)
    pages = max(1, (total + _PAGE - 1) // _PAGE)
    try:
        page = max(1, min(pages, int(request.args.get("page", 1))))
    except ValueError:
        page = 1
    offset = (page - 1) * _PAGE
    rows = []
    for i, r in indexed[offset:offset + _PAGE]:
        rows.append({
            "idx": i,
            "name": getattr(r, "full_name_ar", "") or getattr(
                r, "full_name_en", "") or "—",
            "passport": getattr(r, "passport_number", "") or "—",
            "program": str(getattr(r, ("program" if _mode() == app_mode.HAJJ
                                       else "trip"), "") or "") or "—",
            "phone": getattr(r, "phone", "") or "—",
        })
    return render_template("documents_pick.html", active="documents", kind=kind,
                           label=_DOC_KIND_LABEL[kind], rows=rows, q=q,
                           total=total, page=page, pages=pages, offset=offset,
                           **_ctx())


@app.get("/documents/<kind>/manual")
def doc_manual(kind):
    """محرّر مستند يدوي — بحقول فارغة، دون ربطه بأي سجلّ."""
    if _sess() is None:
        return redirect(url_for("login"))
    if kind not in _DOC_TITLES:               # الحزمة تحتاج سجلّاً، فتُستثنى
        return redirect(url_for("documents"))
    from hajj_app.mrz import PassportData
    from hajj_app import webdoc
    settings = storage.load_settings()
    co = settings.get("company") if isinstance(settings, dict) else None
    data, schema = _doc_build(kind, PassportData(), co, settings)
    title, icon = _DOC_TITLES[kind]
    return webdoc._doc_html(
        data, schema, f"{title} (يدوي)", icon,
        submit_action=webdoc.web_submit_action(
            url_for("doc_manual_pdf", kind=kind)),
        back_url=url_for("documents"), mode=_mode(),
        build=_BUILD_ID)


def _attach_verify(kind: str, data: dict, uid: str = "") -> None:
    """يسجّل الفاوتشر/طلب المواصلات في سجلّ التحقّق العام ويضع رابطه في البيانات
    (فيُرسم QR على المستند، ويبقى عند إعادة توليده من الأرشيف)."""
    if kind not in ("voucher", "treq") or not isinstance(data, dict):
        return
    from webapp import public
    guest = (data.get("guest_ar") or data.get("guest_en") or data.get("to")
             or data.get("name") or "")
    info = {"mode": _mode(), "kind": kind, "number": str(data.get("number") or ""),
            "date": str(data.get("date") or ""), "guest": public.mask_name(guest),
            "uid": uid or ""}
    if kind == "voucher":
        info["stays"] = [[str(x or "") for x in (list(r)[:2] + list(r)[5:8])]
                         for r in (data.get("stays") or [])
                         if isinstance(r, (list, tuple)) and len(r) >= 8
                         and str(r[1] or "").strip()]
    else:
        days = sorted(str(m[0]) for m in (data.get("movements") or [])
                      if isinstance(m, (list, tuple)) and m and str(m[0] or "").strip())
        info["moves"] = len(days)
        info["from"], info["to"] = (days[0], days[-1]) if days else ("", "")
    try:
        tok = public.doc_token(info)
        data["verify_url"] = url_for("verify_doc", token=tok, _external=True)
    except Exception:                              # noqa: BLE001
        pass


@app.get("/v/<token>")
def verify_doc(token):
    """صفحة عامة يفتحها مسح QR المستند: تؤكّد أنه صادر من المصطفى (بلا دخول)."""
    from webapp import public
    d = public.get_doc(token)
    return render_template("public_verify.html", d=d,
                           title=_DOC_TITLES.get((d or {}).get("kind"), ("مستند", ""))[0]
                           ), (200 if d else 404)


@app.get("/p/<token>")
def person_page(token):
    """صفحة المعتمر الخاصة (رابط سرّي يُرسل له): برنامجه ورحلته وفندقه
    ومستنداته — تُقرأ بيانات البرنامج حيّةً من الإعدادات."""
    from webapp import public
    p = public.get_person(token)
    if not p:
        return render_template("public_person.html", p=None), 404
    mode = p.get("mode") if p.get("mode") in app_mode.MODES else app_mode.UMRAH
    app_mode.set_mode(mode)
    settings = storage.load_settings()
    info = {"group": p.get("group", ""), "rows": [], "phones": []}
    if mode == app_mode.UMRAH:
        from hajj_app import umrah
        t = next((x for x in umrah.load_trips(settings) if x.code == p.get("group")), None)
        if t:
            info["group"] = t.name or t.code
            fl = lambda f, a, b: " · ".join(x for x in (f, a and f"إقلاع {a}",
                                                        b and f"وصول {b}") if x)
            info["rows"] = [r for r in [
                ("✈️ الطيران", " — ".join(x for x in (t.airline, t.depart_city and
                                                      f"من {t.depart_city}") if x)),
                ("🛫 المغادرة", t.depart_date), ("رحلة الذهاب", fl(t.flight_out,
                    t.out_depart_time, t.out_arrive_time)),
                ("🛬 العودة", t.return_date), ("رحلة العودة", fl(t.flight_ret,
                    t.ret_depart_time, t.ret_arrive_time)),
                ("🏨 فندق مكة", " · ".join(x for x in (t.makkah_hotel, t.makkah_nights
                                                      and f"{t.makkah_nights} ليالٍ") if x)),
                ("🏨 فندق المدينة", " · ".join(x for x in (t.madinah_hotel, t.madinah_nights
                                                          and f"{t.madinah_nights} ليالٍ") if x)),
                ("🚐 النقل", t.transport)] if r[1]]
            info["phones"] = [x for x in (("طوارئ الإمارات", t.emergency_uae),
                                          ("طوارئ السعودية", t.emergency_ksa)) if x[1]]
    else:
        from hajj_app import programs as hp
        for nm, pr in zip(hp.PROGRAM_NAMES, hp.load_programs(settings)):
            if nm == p.get("group"):
                info["rows"] = [r for r in [
                    ("✈️ الناقل", pr.carrier), ("🛫 السفر", pr.travel_date),
                    ("رحلة الذهاب", pr.flight_out), ("🛬 العودة", pr.return_date),
                    ("رحلة العودة", pr.flight_ret), ("🏨 الفندق", pr.hotel)] if r[1]]
    if p.get("room"):
        info["rows"].append(("🛏 نوع الغرفة", p["room"]))
    docs = [(url_for("verify_doc", token=t), _DOC_TITLES.get(d.get("kind"), ("مستند", ""))[0],
             d.get("number", "")) for t, d in public.person_docs(mode, p.get("uid"))]
    return render_template("public_person.html", p=p, info=info, docs=docs,
                           noun="الحاج" if mode == app_mode.HAJJ else "المعتمر")


@app.post("/hujjaj/<int:idx>/link")
def person_link(idx):
    """إنشاء/تجديد/إلغاء رابط المعتمر الخاص (للمحرّرين)."""
    if _sess() is None:
        return redirect(url_for("login"))
    from webapp import public
    records = _load_records()
    j = _resolve_idx(records, idx, request.form.get("fp"))
    if j is None or not _sess().can_edit:
        return redirect(url_for("hujjaj"))
    rec = records[j]
    uid = getattr(rec, "uid", "") or ""
    action = request.form.get("action") or "create"
    name = rec.full_name_ar or rec.full_name_en or ""
    if action == "revoke":
        public.revoke_person(_mode(), uid)
        _audit("إلغاء رابط معتمر", name)
    else:
        public.person_token(_mode(), uid, {
            "first": (name.split() or [""])[0], "group": getattr(rec, _group_attr(), "") or "",
            "room": rec.room_type or ""}, rotate=(action == "rotate"))
        _audit("رابط معتمر" + (" (تجديد)" if action == "rotate" else ""), name)
    return redirect(url_for("record_docs", idx=j, fp=_rec_token(rec)))


@app.get("/calendar")
def calendar_page():
    """تقويم الرحلات: مغادرة وعودة كل برنامج على أيام الشهر، بألوان البرامج."""
    if _sess() is None:
        return redirect(url_for("login"))
    import calendar as _cal
    from datetime import date as _date
    from webapp.alerts import _d
    today = _date.today()
    try:
        y, m = (int(x) for x in (request.args.get("m") or "").split("-")[:2])
        first = _date(y, m, 1)
    except (ValueError, TypeError):
        first = today.replace(day=1)
    settings = storage.load_settings()
    records = _load_records()
    events: dict = {}

    def add(d, ev):
        if d and d.year == first.year and d.month == first.month:
            events.setdefault(d.day, []).append(ev)

    if _mode() == app_mode.UMRAH:
        from hajj_app import umrah
        trips = umrah.load_trips(settings)
        rows = [{"code": t.code, "package": str(t.package or "").strip()} for t in trips]
        _color_rows(rows, trips, _pkg_orders(settings))
        col = {r["code"]: r for r in rows}
        for t in trips:
            n = len(umrah.trip_pilgrims(records, t.code))
            c = col.get(t.code, {})
            base = {"label": f"{t.code} {t.name or ''}".strip(), "n": n,
                    "color": c.get("color", "#1F5FAD"), "fg": c.get("fg", "#fff"),
                    "link": url_for("program_edit", code=t.code),
                    "sub": " · ".join(x for x in (t.airline, t.package) if x)}
            add(_d(t.depart_date), dict(base, icon="🛫"))
            add(_d(t.return_date), dict(base, icon="🛬"))
    else:
        from hajj_app import programs as hp
        for i, (nm, pr) in enumerate(zip(hp.PROGRAM_NAMES, hp.load_programs(settings))):
            n = sum(1 for r in records if (r.program or "") == nm)
            band, _t, fg, _i = _PROG_COLORS[i % len(_PROG_COLORS)]
            base = {"label": nm, "n": n, "color": band, "fg": fg,
                    "link": url_for("travel_list"), "sub": pr.carrier}
            add(_d(pr.travel_date), dict(base, icon="🛫"))
            add(_d(pr.return_date), dict(base, icon="🛬"))
    weeks = []
    for wk in _cal.Calendar(firstweekday=5).monthdayscalendar(first.year, first.month):
        weeks.append([{"day": d, "events": events.get(d, []),
                       "today": (d and first.replace(day=d) == today)} for d in wk])
    prev = (first.replace(day=1) - __import__("datetime").timedelta(days=1)).replace(day=1)
    nxt = (first.replace(day=28) + __import__("datetime").timedelta(days=4)).replace(day=1)
    months = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو",
              "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
    return render_template(
        "calendar.html", active="calendar", weeks=weeks,
        title=f"{months[first.month - 1]} {first.year}",
        prev=prev.strftime("%Y-%m"), next=nxt.strftime("%Y-%m"),
        this=today.strftime("%Y-%m"),
        total=sum(len(v) for v in events.values()), **_ctx())


@app.post("/documents/<kind>/manual/pdf")
def doc_manual_pdf(kind):
    """يولّد PDF لمستند يدوي من البيانات المُحرَّرة (بلا سجلّ)."""
    if _sess() is None:
        return ("", 401)
    if kind not in _DOC_TITLES:
        return ("", 404)
    from hajj_app.mrz import PassportData
    settings = storage.load_settings()
    co = settings.get("company") if isinstance(settings, dict) else None
    data = request.get_json(force=True, silent=True) or {}
    _attach_verify(kind, data)                               # QR للتحقّق
    _archive_doc(kind, data, idx=None, name="يدوي بلا اسم")   # أرشفة تلقائية
    _audit("إصدار مستند يدوي", _DOC_TITLES[kind][0])
    return _pdf_response(
        lambda p: _doc_export(kind, PassportData(), co, data, p),
        f"{kind}-manual.pdf")


@app.route("/hujjaj/new", methods=["GET", "POST"])
def hujjaj_new():
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app.mrz import PassportData
    if not _sess().can_edit:                 # المطّلع لا يضيف
        return redirect(url_for("hujjaj"))
    records = _load_records()
    if request.method == "POST":
        import uuid
        rec = PassportData(source_file="إدخال ويب", uid=uuid.uuid4().hex)
        drop = _UMRAH_DROP if _mode() == app_mode.UMRAH else set()
        for _title, keys in _GROUPS:
            for k in keys:
                if k in drop or k not in BY_KEY or not BY_KEY[k].editable:
                    continue
                if k in request.form:
                    setattr(rec, k, request.form.get(k, "").strip())
        if _mode() == app_mode.UMRAH and "trip" in request.form:
            rec.trip = request.form.get("trip", "").strip()
            _umrah_fill_price(rec)
        records.append(rec)
        try:
            storage.save_records(records, session=_sess())
            _audit("إضافة سجلّ", getattr(rec, "full_name_ar", "") or getattr(
                rec, "full_name_en", "") or getattr(rec, "passport_number", ""))
        except Exception:
            pass
        return redirect(url_for("hujjaj"))
    return _render_edit(PassportData(source_file="إدخال ويب"), is_new=True)


@app.route("/hujjaj/<int:idx>", methods=["GET", "POST"])
def hujjaj_edit(idx):
    if _sess() is None:
        return redirect(url_for("login"))
    records = _load_records()
    if request.method == "POST":
        if not _sess().can_edit:                   # المطّلع لا يعدّل
            return redirect(url_for("hujjaj"))
        j = _resolve_idx(records, idx, request.form.get("fp", ""), strict=True)
        if j is None:                              # تغيّر الكشف منذ فتح الصفحة
            return redirect(url_for("hujjaj", msg="stale"))
        idx = j
    else:
        moved = _follow(records, idx, "hujjaj_edit")
        if moved:
            return moved
    if not (0 <= idx < len(records)):
        return redirect(url_for("hujjaj"))
    rec = records[idx]
    drop = _UMRAH_DROP if _mode() == app_mode.UMRAH else set()
    saved = False
    if request.method == "POST":
        before = (str(getattr(rec, "trip", "") or ""),
                  str(getattr(rec, "room_type", "") or ""))
        for _title, keys in _GROUPS:
            for k in keys:
                if k in drop or k not in BY_KEY or not BY_KEY[k].editable:
                    continue
                if k in request.form:
                    setattr(rec, k, request.form.get(k, "").strip())
        if _mode() == app_mode.UMRAH and "trip" in request.form:
            rec.trip = request.form.get("trip", "").strip()
            _umrah_fill_price(rec, changed=(rec.trip, rec.room_type) != before)
        try:
            storage.save_records(records, session=_sess())
            saved = True
            _audit("تعديل سجلّ", getattr(rec, "full_name_ar", "") or getattr(
                rec, "full_name_en", "") or getattr(rec, "passport_number", ""))
        except Exception:
            saved = False
    return _render_edit(rec, saved=saved, idx=idx)


def _rec_fp(rec) -> str:
    """بصمة سجلّ تُرسَل مع زرّ الحذف: الموضع وحده قد يشير لشخص آخر إن غيّر
    مستخدمٌ آخر الكشف في الأثناء، فلا يُحذف إلّا السجلّ المقصود."""
    return "|".join(str(getattr(rec, k, "") or "").strip() for k in
                    ("passport_number", "full_name_ar", "full_name_en",
                     "reference_number"))


def _rec_token(rec) -> str:
    """رمز السجلّ في النماذج: الوضع + معرّفه الثابت + خلاصة بياناته (لا يطابق
    سجلّاً في الوضع الآخر، ولا نسخةً مكرّرة، ويكشف تعديل غيرك له في الأثناء).
    كلّه حروف لاتينية وأرقام فيعبر النماذج كما هو (بلا أسطر أو رموز)."""
    dig = hashlib.sha1(_rec_fp(rec).encode("utf-8")).hexdigest()[:12]
    return f"{_mode()}#{getattr(rec, 'uid', '') or ''}#{dig}"


def _resolve_idx(records, idx, token, strict: bool = False):
    """الموضع الحالي للسجلّ الذي فُتحت له الصفحة، أو None إن لم يعد موجوداً
    (حُذف، أو تبدّل الوضع في تبويب آخر) — فلا يُكتب على شخصٍ آخر أبداً. المواضع
    تتقدّم بعد حذف سجلّ، فلا يُعتمد على الموضع وحده. ``strict`` (نموذج التعديل)
    يرفض أيضاً إن عدّل غيرك اسمه/جوازه في الأثناء كي لا تُلغى تعديلاته."""
    parts = str(token or "").split("#")
    if len(parts) != 3 or parts[0] != _mode() or not parts[1]:
        return None
    uid = parts[1]
    if 0 <= idx < len(records) and getattr(records[idx], "uid", "") == uid:
        j = idx
    else:
        hits = [i for i, r in enumerate(records)
                if getattr(r, "uid", "") == uid]
        if len(hits) != 1:                         # حُذف (أو التبس) → رفض
            return None
        j = hits[0]
    if strict and _rec_token(records[j]) != token:     # عدّله غيرك في الأثناء
        return None
    return j


def _follow(records, idx, endpoint, **kw):
    """رابط من صفحة قديمة يحمل رمز السجلّ (fp): يُوجَّه إلى موضعه الحالي، أو
    إلى القائمة إن لم يعد موجوداً — فلا تُفتح صفحة شخصٍ آخر بالموضع القديم."""
    tok = request.args.get("fp")
    if not tok:
        return None
    j = _resolve_idx(records, idx, tok)
    if j is None:
        return redirect(url_for("hujjaj", msg="stale"))
    if j != idx:
        return redirect(url_for(endpoint, idx=j, fp=tok, **kw))
    return None


def _shift_idx(i, gone):
    """موضع سجلّ بعد حذف الموضع ``gone``: None للمحذوف، وما بعده يتقدّم واحداً."""
    if not isinstance(i, int) or isinstance(i, bool):
        return i
    if i == gone:
        return None
    return i - 1 if i > gone else i


def _reindex_after_delete(gone: int) -> None:
    """يُصلح الإشارات بموضع السجلّ بعد حذفه: أرشيف المستندات (idx) وتسكين
    مخيمات الحج (assigned/indices) — كي لا تُنسب لشخصٍ آخر بعد التقدّم."""
    try:
        docs = storage.load_documents(session=_sess())
        changed = False
        for d in docs:
            i = d.get("idx")
            if isinstance(i, int) and not isinstance(i, bool) and i >= gone:
                d["idx"] = _shift_idx(i, gone)     # المحذوف: يبقى بالاسم فقط
                changed = True
        if changed:
            storage.save_documents(docs, session=_sess())
    except Exception:                              # noqa: BLE001
        pass
    try:
        camps = _load_camps()
        changed = False

        def _fix(lst):
            return [j for j in (_shift_idx(i, gone) for i in (lst or []))
                    if j is not None]

        for st in camps.values():
            if not isinstance(st, dict):
                continue
            old = (st.get("assigned"), [t.get("indices") for t in
                                        st.get("tents") or []],
                   (st.get("last") or {}).get("indices")
                   if isinstance(st.get("last"), dict) else None)
            if "assigned" in st:
                st["assigned"] = _fix(st["assigned"])
            tents = []
            for t in st.get("tents") or []:
                if isinstance(t, dict):
                    t["indices"] = _fix(t.get("indices"))
                    if t["indices"]:               # خيمة فرغت تُحذف
                        tents.append(t)
            if "tents" in st:
                st["tents"] = tents
            if isinstance(st.get("last"), dict):
                st["last"]["indices"] = _fix(st["last"].get("indices"))
                if not st["last"]["indices"]:
                    st["last"] = None
            new = (st.get("assigned"), [t.get("indices") for t in
                                        st.get("tents") or []],
                   (st.get("last") or {}).get("indices")
                   if isinstance(st.get("last"), dict) else None)
            changed = changed or new != old
        if changed:
            _save_camps(camps)
    except Exception:                              # noqa: BLE001
        pass


@app.post("/hujjaj/<int:idx>/delete")
def hujjaj_delete(idx):
    """حذف سجلّ (للمحرّرين) بعد التحقّق من بصمته، مع صوره المشفّرة."""
    if _sess() is None:
        return redirect(url_for("login"))
    if not _sess().can_edit:                       # المطّلع لا يحذف
        return redirect(url_for("hujjaj"))
    records = _load_records()
    j = _resolve_idx(records, idx, request.form.get("fp", ""))
    if j is None:                                  # تغيّر الكشف ولا تطابق مؤكّد
        return redirect(url_for("hujjaj", msg="notfound"))
    idx = j
    rec = records.pop(idx)
    name = (getattr(rec, "full_name_ar", "") or getattr(rec, "full_name_en", "")
            or getattr(rec, "passport_number", "") or "—")
    try:
        storage.save_records(records, session=_sess())
    except Exception:                              # noqa: BLE001
        return redirect(url_for("hujjaj", msg="error"))
    image_id = str(getattr(rec, "image_id", "") or "").strip()
    if image_id:                                   # صور الجواز/الهوية المشفّرة
        try:
            from hajj_app import images as imgmod
            imgmod.delete_all(image_id)
        except Exception:                          # noqa: BLE001
            pass
    _reindex_after_delete(idx)
    _audit("حذف سجلّ", name)
    return redirect(url_for("hujjaj", msg="deleted", name=name))


def _umrah_fill_price(rec, changed: bool = True) -> None:
    """يزامن سعر الغرفة مع البرنامج المختار كما في سطح المكتب:
    ``room_value`` = سعر الفرد لنوع الغرفة (أساس يُضاف إليه سعر الخدمات)، و«قيمة
    البرنامج» الفارغة = سعر الغرفة + الخدمات (احتياط إن لم يعمل ملء الصفحة).
    القيمة المُدخلة يدوياً لا تُمسّ، و``room_value`` لا يتغيّر إلّا إذا تغيّر
    البرنامج أو نوع الغرفة (``changed``) فلا يُلغى أساسٌ عُدّل عمداً."""
    from hajj_app import umrah
    from hajj_app.fields import format_amount, parse_amount
    price = umrah.trip_room_price(umrah.load_trips(storage.load_settings()),
                                  getattr(rec, "trip", ""),
                                  getattr(rec, "room_type", ""))
    if not price:
        return
    base = parse_amount(price) or 0.0
    if changed or not str(getattr(rec, "room_value", "") or "").strip():
        rec.room_value = format_amount(base)
    if not str(getattr(rec, "program_value", "") or "").strip():
        svc = umrah.record_services_total(rec)
        rec.program_value = format_amount(base + svc) if svc else price


def _render_edit(rec, saved=False, is_new=False, idx=None):
    from hajj_app import umrah
    drop = _UMRAH_DROP if _mode() == app_mode.UMRAH else set()
    groups = []
    for title, keys in _GROUPS:
        fs = []
        for k in keys:
            if k in drop or k not in BY_KEY:
                continue
            val = str(getattr(rec, k, "") or "")
            cmap = ({**_CHOICES, **_UMRAH_CHOICES}
                    if _mode() == app_mode.UMRAH else _CHOICES)
            choices = list(cmap[k]) if k in cmap else None
            if choices is not None and val and val not in choices:
                choices.insert(1, val)          # قيمة قديمة خارج القائمة تبقى ظاهرة
            fs.append({"key": k, "label": _label(k),
                       "value": val,
                       "choices": choices,
                       "type": ("date" if k in _DATE_FIELDS else "")})
        if fs:
            groups.append({"title": title.format(n=_noun()), "fields": fs})
    room_prices = None
    if _mode() == app_mode.UMRAH:            # ربط المعتمر ببرنامج عمرة
        trips = umrah.load_trips(storage.load_settings())
        groups.insert(0, {"title": "البرنامج", "fields": [{
            "key": "trip", "label": "البرنامج (الرحلة)",
            "value": str(getattr(rec, "trip", "") or ""),
            "choices": [["", ""]] + [[t.code, f"{t.code} — {t.name}" if t.name
                                      else t.code] for t in trips],
            "type": ""}]})
        # نوع الغرفة: قائمة من أسعار البرنامج المختار، والسعر يملأ قيمة البرنامج
        room_prices = {t.code: umrah.trip_room_prices(t) for t in trips}
        cur_trip = str(getattr(rec, "trip", "") or "")
        rooms = room_prices.get(cur_trip) or [(n, "") for _k, n, _c in
                                             umrah.ROOM_TYPES]
        cur_room = str(getattr(rec, "room_type", "") or "")
        choices = [["", ""]] + [[n, f"{n} — {p}" if p else n] for n, p in rooms]
        if cur_room and cur_room not in [n for n, _p in rooms]:
            choices.insert(1, [cur_room, cur_room])   # قيمة قديمة تبقى ظاهرة
        for g in groups:
            for f in g["fields"]:
                if f["key"] == "room_type":
                    f["choices"] = choices
                elif f["key"] == "program_value":
                    f["hint"] = ("يُملأ تلقائياً بسعر الفرد من البرنامج حسب نوع "
                                 "الغرفة — ويمكن تعديله.")
    has_docs = idx is not None            # للسجلّ القائم فقط
    return render_template(
        "hujjaj_edit.html", active="hujjaj", groups=groups, saved=saved,
        has_docs=has_docs,
        is_new=is_new, idx=idx, room_prices=room_prices,
        fp=_rec_token(rec) if idx is not None else "",
        svc_total=umrah.record_services_total(rec),   # خدمات المعتمر
        cur_trip=str(getattr(rec, "trip", "") or ""),
        room_names=[n for _k, n, _c in umrah.ROOM_TYPES],
        name=getattr(rec, "full_name_ar", "") or getattr(
            rec, "full_name_en", "") or "",
        number=getattr(rec, "reference_number", "") or "",
        noun_singular=_noun_singular(), **_ctx())


_RECORD_DOCS = [
    ("receipt", "🧾", "سند قبض", "إيصال استلام مبلغ من العميل."),
    ("invoice", "🧾", "فاتورة ضريبية", "فاتورة بقيمة البرنامج والضريبة."),
    ("contract", "📜", "عقد خدمات", "عقد الخدمات بين المكتب والعميل."),
    ("voucher", "🏨", "فاوتشر فندق", "قسيمة حجز الفندق للإبراز عند الوصول."),
    ("treq", "🚖", "طلب حجز مواصلات", "طلب حجز مواصلات موجّه للناقل."),
]


@app.get("/hujjaj/<int:idx>/docs")
def record_docs(idx):
    """قائمة مستندات السجلّ مستقلّة (تحرير كلٍّ ثم حفظ ومعاينة PDF + الحزمة)."""
    if _sess() is None:
        return redirect(url_for("login"))
    records = _load_records()
    moved = _follow(records, idx, "record_docs")
    if moved:
        return moved
    if not (0 <= idx < len(records)):
        return redirect(url_for("hujjaj"))
    rec = records[idx]
    name = getattr(rec, "full_name_ar", "") or getattr(
        rec, "full_name_en", "") or "—"
    saved = []                                     # مستندات هذا الشخص المؤرشفة
    for d in reversed(storage.load_documents(session=_sess())):
        if d.get("idx") == idx or (name != "—" and d.get("name") == name):
            saved.append({"id": d.get("id"),
                          "ts": (d.get("ts") or "").replace("T", "  "),
                          "title": d.get("title") or d.get("kind"),
                          "number": d.get("number") or "—"})
    from webapp import public
    from hajj_app import whatsapp as _wa
    tok = public.find_person(_mode(), getattr(rec, "uid", "") or "")
    plink = url_for("person_page", token=tok, _external=True) if tok else ""
    wa = (_wa.wa_link(rec.phone, f"السلام عليكم {(name.split() or [''])[0]}، هذا رابط "
                      f"برنامجك مع المصطفى للحج والعمرة: {plink}",
                      str(storage.load_settings().get("whatsapp_cc") or "971"))
          if plink and getattr(rec, "phone", "") else None)
    return render_template("record_docs.html", active="hujjaj", idx=idx,
                           fp=_rec_token(rec), plink=plink, wa=wa,
                           name=name, docs=_RECORD_DOCS, saved=saved,
                           noun_singular=_noun_singular(), **_ctx())


def _image_kinds():
    """أنواع مستندات السجلّ حسب الوضع (العمرة: الجواز فقط كما في سطح المكتب)."""
    from hajj_app import images as imgmod
    return (imgmod.PASSPORT,) if _mode() == app_mode.UMRAH else imgmod.KINDS


def _rec_name(rec) -> str:
    return (getattr(rec, "full_name_ar", "") or getattr(rec, "full_name_en", "")
            or getattr(rec, "passport_number", "") or "")


@app.get("/hujjaj/<int:idx>/images")
def record_images(idx):
    """صفحة إرفاق مستندات السجلّ (جواز/شخصية/هوية/تصريح): عرض/رفع/حذف."""
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app import images as imgmod
    records = _load_records()
    moved = _follow(records, idx, "record_images")
    if moved:
        return moved
    if not (0 <= idx < len(records)):
        return redirect(url_for("hujjaj"))
    rec = records[idx]
    iid = getattr(rec, "image_id", "")
    items = []
    for kind in _image_kinds():
        present = bool(iid) and imgmod.has_image(iid, kind)
        is_pdf = False
        if present:                                    # نفكّ التشفير لمعرفة النوع
            blob = imgmod.load_image(iid, kind, _sess())
            present = bool(blob)
            is_pdf = present and imgmod.is_pdf(blob)
        items.append({"kind": kind, "label": imgmod.KIND_LABELS.get(kind, kind),
                      "present": present, "is_pdf": is_pdf})
    return render_template("record_images.html", active="hujjaj", idx=idx,
                           name=_rec_name(rec) or "—", items=items,
                           fp=_rec_token(rec),
                           saved=request.args.get("saved"),
                           err=request.args.get("err"),
                           noun_singular=_noun_singular(), **_ctx())


@app.post("/hujjaj/<int:idx>/images/<kind>")
def record_image_upload(idx, kind):
    """رفع/استبدال مستند لنوع محدّد (يُضغط ويُشفّر مع بيانات الحاج)."""
    if _sess() is None:
        return redirect(url_for("login"))
    if not _sess().can_edit:
        return redirect(url_for("hujjaj"))
    from hajj_app import images as imgmod
    if kind not in _image_kinds():
        return redirect(url_for("record_images", idx=idx))
    records = _load_records()
    j = _resolve_idx(records, idx, request.form.get("fp", ""))
    if j is None:                                  # تغيّر الكشف منذ فتح الصفحة
        return redirect(url_for("hujjaj", msg="stale"))
    idx = j
    rec = records[idx]
    f = request.files.get("file")
    if not f or not f.filename:
        return redirect(url_for("record_images", idx=idx, err="لم يتم اختيار ملف."))
    ext = os.path.splitext(f.filename)[1].lower() or ".jpg"
    p = _tmp(ext)
    f.save(p)
    ok = False
    try:
        if not getattr(rec, "image_id", ""):
            rec.image_id = imgmod.new_image_id()       # يُنشأ عند أول إرفاق
        imgmod.save_image(rec.image_id, kind, p, _sess())
        storage.save_records(records, session=_sess())  # يثبّت image_id على السجلّ
        _audit("إرفاق مستند",
               f"{imgmod.KIND_LABELS.get(kind, kind)} — {_rec_name(rec)}")
        ok = True
    except Exception:                                  # noqa: BLE001
        ok = False
    finally:
        try:
            os.unlink(p)
        except OSError:
            pass
    if ok:
        return redirect(url_for("record_images", idx=idx, saved="رُفع المستند."))
    return redirect(url_for("record_images", idx=idx, err="تعذّر حفظ المستند."))


@app.post("/hujjaj/<int:idx>/images/<kind>/delete")
def record_image_delete(idx, kind):
    """حذف مستند نوع محدّد للسجلّ."""
    if _sess() is None:
        return redirect(url_for("login"))
    if not _sess().can_edit:
        return redirect(url_for("hujjaj"))
    from hajj_app import images as imgmod
    if kind not in _image_kinds():
        return redirect(url_for("record_images", idx=idx))
    records = _load_records()
    j = _resolve_idx(records, idx, request.form.get("fp", ""))
    if j is None:                                  # تغيّر الكشف منذ فتح الصفحة
        return redirect(url_for("hujjaj", msg="stale"))
    idx = j
    rec = records[idx]
    iid = getattr(rec, "image_id", "")
    if iid:
        try:
            imgmod.delete_image(iid, kind)
            _audit("حذف مستند",
                   f"{imgmod.KIND_LABELS.get(kind, kind)} — {_rec_name(rec)}")
        except Exception:                              # noqa: BLE001
            pass
    return redirect(url_for("record_images", idx=idx, saved="حُذف المستند."))


@app.get("/hujjaj/<int:idx>/images/<kind>.file")
def record_image_view(idx, kind):
    """يعيد المستند المخزّن (صورة أو PDF) لعرضه/فتحه في المتصفّح."""
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app import images as imgmod
    if kind not in imgmod.KINDS:
        return ("", 404)
    records = _load_records()
    j = _resolve_idx(records, idx, request.args.get("fp", ""))
    if j is None:                                  # صفحة قديمة: لا نعرض صورة غيره
        return ("", 404)
    rec = records[j]
    iid = getattr(rec, "image_id", "")
    if not iid or not imgmod.has_image(iid, kind):
        return ("", 404)
    data = imgmod.load_image(iid, kind, _sess())
    if not data:
        return ("", 404)
    import io
    if imgmod.is_pdf(data):
        mime, dname = "application/pdf", f"{kind}.pdf"
    else:
        mime, dname = "image/jpeg", f"{kind}.jpg"
    return send_file(io.BytesIO(data), mimetype=mime, as_attachment=False,
                     download_name=dname)


@app.route("/hujjaj/scan", methods=["GET", "POST"])
def hujjaj_scan():
    """قراءة جواز من صورة (OCR) وتعبئة نموذج سجلّ جديد للمراجعة.

    اختياري على الاستضافة: يتطلّب opencv/pytesseract + محرّك tesseract. إن لم
    تتوفّر المكتبات أو المحرّك، تُعرض رسالة لطيفة وتبقى بقية البرنامج سليمة.
    """
    if _sess() is None:
        return redirect(url_for("login"))
    if not _sess().can_edit:                  # المطّلع لا يضيف
        return redirect(url_for("hujjaj"))
    from hajj_app.mrz import PassportData

    ocr_err = None
    _ocr = None
    try:
        from hajj_app import ocr as _ocr        # يتطلّب cv2/pytesseract
        from hajj_app.tesseract_setup import configure_tesseract
        if not configure_tesseract():
            ocr_err = ("محرّك القراءة (tesseract) غير مثبّت على الخادم — "
                       "راجع دليل النشر لتفعيله.")
    except Exception as exc:                    # noqa: BLE001
        ocr_err = (f"مكتبات القراءة غير مثبّتة على هذه الاستضافة "
                   f"({exc.__class__.__name__}).")

    if request.method == "POST":
        if ocr_err:
            return render_template("scan.html", active="hujjaj", ocr_err=ocr_err,
                                   notes=[], noun_singular=_noun_singular(), **_ctx())
        f = request.files.get("image")
        if not f or not f.filename:
            return render_template("scan.html", active="hujjaj", ocr_err=None,
                                   notes=["اختر صورة الجواز أولاً."],
                                   noun_singular=_noun_singular(), **_ctx())
        ext = os.path.splitext(f.filename)[1].lower() or ".jpg"
        p = _tmp(ext)
        f.save(p)
        notes, data = [], None
        try:
            data = _ocr.extract_passport(p)
        except Exception as exc:               # noqa: BLE001
            notes = [f"تعذّرت قراءة الجواز: {exc}. جرّب صورة أوضح أو أدخل يدوياً."]
        finally:
            try:
                os.unlink(p)
            except OSError:
                pass
        if data is None or not (data.full_name_ar or data.full_name_en
                                or data.passport_number):
            if not notes:
                notes = ["تعذّر استخراج بيانات كافية من الصورة — جرّب صورة أوضح."]
            return render_template("scan.html", active="hujjaj", ocr_err=None,
                                   notes=notes, noun_singular=_noun_singular(), **_ctx())
        data.source_file = "قراءة جواز (ويب)"
        # تُعرض البيانات المستخرجة في نموذج جديد للمراجعة ثم الحفظ عبر /hujjaj/new
        return _render_edit(data, is_new=True)

    return render_template("scan.html", active="hujjaj", ocr_err=ocr_err,
                           notes=[], noun_singular=_noun_singular(), **_ctx())


# ------------------------------------------------------------------ التقارير
def _tmp(suffix):
    fd, p = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    return p


@app.get("/reports")
def reports():
    if _sess() is None:
        return redirect(url_for("login"))
    records = _load_records()
    return render_template("reports.html", active="reports",
                           count=len(records), **_ctx())


@app.get("/reports/pilgrims.pdf")
def rep_pilgrims_pdf():
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app import pdf_io
    records = _load_records()
    p = _tmp(".pdf")
    title = "كشف الحجّاج" if _mode() == app_mode.HAJJ else "كشف المعتمرين"
    if _mode() == app_mode.UMRAH:
        pdf_io.export_umrah_pdf(records, p, program_name="")
    else:
        pdf_io.export_pdf(records, p, title=title)
    return send_file(p, mimetype="application/pdf", as_attachment=False,
                     download_name="pilgrims.pdf")


@app.get("/reports/pilgrims.xlsx")
def rep_pilgrims_xlsx():
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app import excel_io
    records = _load_records()
    p = _tmp(".xlsx")
    excel_io.export_excel(records, p)
    return send_file(p, as_attachment=True, download_name="pilgrims.xlsx")


@app.get("/reports/financial.pdf")
def rep_financial_pdf():
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app import pdf_io
    records = _load_records()
    p = _tmp(".pdf")
    pdf_io.export_stats_pdf(records, p)
    return send_file(p, mimetype="application/pdf", as_attachment=False,
                     download_name="financial.pdf")


@app.get("/reports/airline.pdf")
def rep_airline_pdf():
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app import pdf_io
    records = _load_records()
    p = _tmp(".pdf")
    pdf_io.export_airline_pdf(records, p)
    return send_file(p, mimetype="application/pdf", as_attachment=False,
                     download_name="airline.pdf")


def _load_badge_back() -> dict:
    """بيانات خلف بطاقة الحاج (محلولة مع الافتراضيات) — لكل وضع من الإعدادات."""
    from hajj_app import pdf_io
    settings = storage.load_settings()
    data = settings.get("badge_back") if isinstance(settings, dict) else None
    return pdf_io.resolve_badge_back(data if isinstance(data, dict) else None)


def _save_badge_back(data: dict) -> None:
    settings = storage.load_settings()
    settings["badge_back"] = data
    storage.save_settings(settings)


@app.route("/cards/back", methods=["GET", "POST"])
def cards_back():
    """تحرير بيانات خلف بطاقة الحاج (الأطباء/الواعظ/الإداريين/الطوارئ) قبل الطباعة."""
    s = _sess()
    if s is None:
        return redirect(url_for("login"))
    if _mode() != app_mode.HAJJ:               # البطاقات ذات الخلف خاصّة بالحج
        return redirect(url_for("reports"))
    app_mode.set_mode(_mode())
    if request.method == "POST" and s.can_edit:
        names = request.form.getlist("admin_name")
        nums = request.form.getlist("admin_number")
        admins = []
        for i, nm in enumerate(names):
            num = (nums[i] if i < len(nums) else "").strip()
            nm = nm.strip()
            if nm or num:
                admins.append({"name": nm, "number": num})
        data = {
            "doctor": (request.form.get("doctor") or "").strip(),
            "preacher": (request.form.get("preacher") or "").strip(),
            "admins": admins,
            "emergency_name": (request.form.get("emergency_name") or "").strip(),
            "emergency": (request.form.get("emergency") or "").strip(),
        }
        _save_badge_back(data)
        _audit("تعديل بيانات خلف البطاقة", f"{len(admins)} إداري")
        return redirect(url_for("cards_back", saved=1))
    return render_template("badge_back.html", active="reports",
                           back=_load_badge_back(),
                           saved=request.args.get("saved"), **_ctx())


@app.get("/reports/cards.pdf")
def rep_cards_pdf():
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app import pdf_io
    records = _load_records()
    settings = storage.load_settings()
    co = settings.get("company") if isinstance(settings, dict) else None
    p = _tmp(".pdf")
    if _mode() == app_mode.UMRAH:
        pdf_io.export_umrah_cards_pdf(records, p, company=co, session=_sess())
    else:
        c = pdf_io.company_info(co)
        pdf_io.export_badges_pdf(records, p, company=c["name_ar"],
                                 session=_sess(), back=_load_badge_back())
    return send_file(p, mimetype="application/pdf", as_attachment=False,
                     download_name="cards.pdf")


@app.get("/reports/stickers.pdf")
def rep_stickers_pdf():
    """ملصقات الحقائب (شبكة على A4) لكل السجلات."""
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app import pdf_io
    records = _load_records()
    settings = storage.load_settings()
    co = settings.get("company") if isinstance(settings, dict) else None
    season = str(settings.get("season_year", "") or "")
    company = pdf_io.company_info(co)["name_ar"]
    p = _tmp(".pdf")
    pdf_io.export_stickers_pdf(records, p, kind="bag", company=company,
                               season=season)
    return send_file(p, mimetype="application/pdf", as_attachment=False,
                     download_name="stickers.pdf")


@app.get("/reports/transport.pdf")
def rep_transport_pdf():
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app import pdf_io
    records = _load_records()
    p = _tmp(".pdf")
    pdf_io.export_umrah_transport_pdf(records, p)
    return send_file(p, mimetype="application/pdf", as_attachment=False,
                     download_name="transport.pdf")


@app.get("/reports/itinerary.pdf")
def rep_itinerary_pdf():
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app import pdf_io
    settings = storage.load_settings()
    rows = [list(r) for r in settings.get("itinerary", [])]
    p = _tmp(".pdf")
    pdf_io.export_itinerary_pdf(p, rows=rows)
    return send_file(p, mimetype="application/pdf", as_attachment=False,
                     download_name="itinerary.pdf")


@app.route("/import", methods=["GET", "POST"])
def data_import():
    if _sess() is None:
        return redirect(url_for("login"))
    if not _sess().can_edit:
        return redirect(url_for("hujjaj"))
    result, notes = "", []
    if request.method == "POST":
        f = request.files.get("file")
        if f and f.filename:
            from hajj_app import excel_io
            p = _tmp(".xlsx")
            f.save(p)
            try:
                recs, notes = excel_io.import_excel(p)
            except Exception as exc:
                recs, notes = [], [f"تعذّر قراءة الملف: {exc}"]
            try:
                os.unlink(p)
            except OSError:
                pass
            if recs:
                records = _load_records()
                records.extend(recs)
                try:
                    storage.save_records(records, session=_sess())
                    _audit("استيراد إكسل", f"{len(recs)} سجلّ")
                except Exception:
                    pass
                result = f"تمّ استيراد {len(recs)} سجلّاً ودمجها."
                try:
                    from hajj_app.quality import duplicate_groups
                    dups = duplicate_groups(records)
                    if dups:
                        notes = list(notes) + [
                            f"⚠ {len(dups)} رقم جواز مكرّر بعد الدمج — "
                            "راجعها في القائمة."]
                except Exception:
                    pass
            elif not notes:
                notes = ["الملف لا يحتوي بيانات صالحة."]
        else:
            notes = ["اختر ملف إكسل أولاً."]
    return render_template("import.html", active="import", result=result,
                           notes=notes, **_ctx())


# ---- مسعّر المجموعات (حاسبة حيّة على الويب) ----
_PRICER_DEFAULT_ITEMS = ("النقل الداخلي", "نقل المطار", "التأشيرة",
                         "تذكرة الطيران", "ماء وعصير وتمر", "الهدايا",
                         "المصاريف الإدارية")
_PRICER_HAJJ_ITEMS = ("تصريح الحج (نُسك)", "خدمات المشاعر (منى/عرفات/مزدلفة)",
                      "مخيّم منى", "الهدي / الأضحية", "الإعاشة",
                      "النقل والتنقّلات", "تذكرة الطيران", "المصاريف الإدارية")


@app.get("/pricer")
def pricer():
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app import umrah, webpricer
    settings = storage.load_settings()
    number = umrah.next_pricing_number(settings)
    try:
        storage.save_settings(settings)
    except Exception:
        pass
    defaults = (_PRICER_HAJJ_ITEMS if _mode() == app_mode.HAJJ
                else _PRICER_DEFAULT_ITEMS)
    from datetime import date as _date
    hajj = _mode() == app_mode.HAJJ
    data = {"number": number, "date": _date.today().isoformat(),
            "currency": "درهم", "include_madinah": "1",
            "room_types": [n for n, _ in umrah.GROUP_ROOM_TYPES],
            "rate_full_period": "1" if hajj else "",   # الحج: سعر الغرفة للفترة كاملة
            "items": [[n, ""] for n in defaults]}
    return webpricer._pricer_html(data, "مسعّر المجموعات",
                                  submit_js=webpricer._SUBMIT_WEB,
                                  back_url=url_for("offers"), full_period=hajj,
                                  mode=_mode())


@app.post("/pricer/pdf")
def pricer_pdf():
    if _sess() is None:
        return ("", 401)
    if not _sess().can_edit:                       # المطّلع لا يحفظ تسعيراً
        return ("forbidden", 403)
    import io
    from hajj_app import umrah, pdf_io
    data = request.get_json(force=True, silent=True) or {}
    data["rate_full_period"] = "1" if _mode() == app_mode.HAJJ else ""  # حسب الوضع
    settings = storage.load_settings()
    try:                                           # حفظ في «التسعيرات المحفوظة»
        umrah.save_pricing(settings, data)
        storage.save_settings(settings)
        _audit("حفظ تسعير مجموعات", str(data.get("number", "") or ""))
    except Exception:
        pass
    # يُفتح الـ PDF من رابط حقيقي في تبويب جديد (فلا يختفي البرنامج، واسم الحفظ = الرقم)
    number = str(data.get("number", "") or "").strip()
    return {"pdf": url_for("pricing_pdf_get", num=(number or "0"))}


@app.get("/pricings/<num>/pdf")
def pricing_pdf_get(num):
    """يعيد PDF تسعير مجموعات محفوظ inline (يُفتح في تبويب جديد باسم الرقم)."""
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app import umrah, pdf_io
    settings = storage.load_settings()
    p = next((x for x in umrah.load_pricings(settings)
              if str(x.get("number")) == str(num)), None)
    if p is None:
        return ("التسعير غير موجود", 404)
    co = settings.get("company") if isinstance(settings, dict) else None
    safe = re.sub(r'[\\/:*?"<>|]+', "-", str(num)).strip() or "تسعير"
    out = _tmp(".pdf")
    pdf_io.export_group_pricing_pdf(dict(p), out, company=co)
    return send_file(out, mimetype="application/pdf", as_attachment=False,
                     download_name=f"{safe}.pdf")


def _pdf_response(gen, fname):
    """يولّد PDF عبر ``gen(path)`` ويعيده كاستجابة (يفتح في المتصفّح)."""
    import io
    p = _tmp(".pdf")
    gen(p)
    with open(p, "rb") as f:
        buf = io.BytesIO(f.read())
    try:
        os.unlink(p)
    except OSError:
        pass
    buf.seek(0)
    return send_file(buf, mimetype="application/pdf", as_attachment=False,
                     download_name=fname)


# ================= التسعير والعروض (لوحة + عروض الأسعار + التسعيرات) =========
@app.get("/offers")
def offers():
    if _sess() is None:
        return redirect(url_for("login"))
    settings = storage.load_settings()
    nq = sum(len(v) for v in (settings.get("umrah_quotes") or {}).values()
             if isinstance(v, list))
    npr = len(settings.get("umrah_pricings") or [])
    return render_template("offers.html", active="offers",
                           n_quotes=nq, n_pricings=npr, **_ctx())


@app.get("/quotes/new")
def quote_new():
    if _sess() is None:
        return redirect(url_for("login"))
    if not _sess().can_edit:
        return redirect(url_for("offers"))
    from hajj_app import umrah, webdoc, pdf_io
    from hajj_app.mrz import PassportData
    settings = storage.load_settings()
    number = umrah.next_quote_number(settings)
    try:
        storage.save_settings(settings)
    except Exception:
        pass
    lang = "en" if request.args.get("lang") == "en" else "ar"
    co = settings.get("company") if isinstance(settings, dict) else None
    data = pdf_io.build_quotation_data(PassportData(), trip=None, company=co,
                                       number=number, lang=lang)
    title = "Umrah Trip Quotation" if lang == "en" else "عرض سعر رحلة عمرة"
    html = webdoc._doc_html(
        data, pdf_io.umrah_quotation_schema(lang), title, "💲",
        submit_action=webdoc.web_submit_action_url(url_for("quote_pdf")),
        back_url=url_for("offers"), lang=lang,
        lang_reload=url_for("quote_new"), mode=_mode(),
        build=_BUILD_ID)
    return html, 200, {"Cache-Control": "no-store, max-age=0"}


@app.get("/quotes/<code>/<num>")
def quote_edit(code, num):
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app import umrah, webdoc, pdf_io
    settings = storage.load_settings()
    q = next((x for x in umrah.load_quotes(settings, code)
              if str(x.get("number")) == str(num)), None)
    if q is None:
        return redirect(url_for("quotes"))
    data = dict(q)
    lang = request.args.get("lang")
    if lang in ("ar", "en"):                       # تبديل لغة النموذج عند الطلب
        data["lang"] = lang
    else:
        lang = data.get("lang") or "ar"
    title = "Umrah Trip Quotation" if lang == "en" else "عرض سعر رحلة عمرة"
    html = webdoc._doc_html(
        data, pdf_io.umrah_quotation_schema(lang), title, "💲",
        submit_action=webdoc.web_submit_action_url(url_for("quote_pdf")),
        back_url=url_for("quotes"), lang=lang,
        lang_reload=url_for("quote_edit", code=code, num=num), mode=_mode(),
        build=_BUILD_ID)
    return html, 200, {"Cache-Control": "no-store, max-age=0"}


@app.post("/quotes/pdf")
def quote_pdf():
    if _sess() is None:
        return ("", 401)
    if not _sess().can_edit:
        return ("forbidden", 403)
    from hajj_app import umrah
    data = request.get_json(force=True, silent=True) or {}
    settings = storage.load_settings()
    code = str(data.get("code") or "").strip()
    number = str(data.get("number", "") or "").strip()
    try:
        umrah.save_quote(settings, code, data)
        storage.save_settings(settings)
        _audit("حفظ عرض سعر", number)
    except Exception:
        pass
    # يُفتح الـ PDF من رابط حقيقي ليكون اسم الحفظ = الرقم المرجعي (لا معرّف blob)
    return {"pdf": url_for("quote_pdf_get", code=(code or "_manual"),
                           num=(number or "0"))}


@app.get("/quotes/<code>/<num>/pdf")
def quote_pdf_get(code, num):
    """يعيد PDF عرض سعر محفوظ inline باسم حفظ = الرقم المرجعي للعرض."""
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app import umrah, pdf_io
    from hajj_app.mrz import PassportData
    settings = storage.load_settings()
    q = next((x for x in umrah.load_quotes(settings, code)
              if str(x.get("number")) == str(num)), None)
    if q is None:
        return ("العرض غير موجود", 404)
    co = settings.get("company") if isinstance(settings, dict) else None
    safe = re.sub(r'[\\/:*?"<>|]+', "-", str(num)).strip() or "عرض-سعر"
    p = _tmp(".pdf")
    pdf_io.export_umrah_quotation_pdf(PassportData(), p, trip=None,
                                      company=co, data=dict(q))
    return send_file(p, mimetype="application/pdf", as_attachment=False,
                     download_name=f"{safe}.pdf")


@app.get("/quotes")
def quotes():
    if _sess() is None:
        return redirect(url_for("login"))
    settings = storage.load_settings()
    store = settings.get("umrah_quotes") or {}
    rows = []
    for code, lst in store.items():
        if not isinstance(lst, list):
            continue
        for q in lst:
            rows.append({"code": code, "number": q.get("number", ""),
                         "title": q.get("title", "") or "عرض سعر",
                         "to": q.get("addressed_to", "") or "—",
                         "date": q.get("date", "")})
    rows.sort(key=lambda r: str(r["number"]), reverse=True)
    return render_template("quotes_list.html", active="offers", rows=rows,
                           **_ctx())


@app.post("/quotes/<code>/<num>/delete")
def quote_delete(code, num):
    if _sess() is None:
        return redirect(url_for("login"))
    if _sess().can_edit:
        from hajj_app import umrah
        settings = storage.load_settings()
        try:
            umrah.delete_quote(settings, code, num)
            storage.save_settings(settings)
            _audit("حذف عرض سعر", str(num))
        except Exception:
            pass
    return redirect(url_for("quotes"))


# ---- فاوتشر فندق / طلب مواصلات من عرض سعر محفوظ (بالرقم المرجعي) ----
_QUOTE_DOC_KINDS = ("voucher", "treq")


def _quote_doc_data(kind, quote, settings):
    """يبني بيانات المستند من العرض مع رقم مستند جديد (نفس عدّادات المستندات)."""
    from hajj_app import pdf_io, umrah
    co = settings.get("company") if isinstance(settings, dict) else None
    if kind == "voucher":
        num = umrah.next_voucher_number(settings)
        data = pdf_io.voucher_data_from_quote(quote, company=co, number=num)
        schema = pdf_io.voucher_schema(data.get("lang"))   # قوائم بلغة الفاوتشر
    else:
        num = umrah.next_transport_number(settings)
        data = pdf_io.transport_request_data_from_quote(quote, company=co,
                                                        number=num)
        schema = pdf_io.TREQ_SCHEMA
    try:
        storage.save_settings(settings)
    except Exception:
        pass
    return data, schema


@app.get("/quotes/<code>/<num>/doc/<kind>")
def quote_doc(code, num, kind):
    """يفتح محرّر فاوتشر/طلب مواصلات معبّأً من عرض السعر المحفوظ."""
    if _sess() is None:
        return redirect(url_for("login"))
    if kind not in _QUOTE_DOC_KINDS:
        return redirect(url_for("quotes"))
    from hajj_app import umrah, webdoc
    settings = storage.load_settings()
    q = next((x for x in umrah.load_quotes(settings, code)
              if str(x.get("number")) == str(num)), None)
    if q is None:
        return redirect(url_for("quotes"))
    data, schema = _quote_doc_data(kind, q, settings)
    title, icon = _DOC_TITLES[kind]
    html = webdoc._doc_html(
        data, schema, f"{title} — من العرض {num}", icon,
        submit_action=webdoc.web_submit_action(
            url_for("quote_doc_pdf", code=code, num=num, kind=kind)),
        back_url=url_for("quotes"), mode=_mode(),
        build=_BUILD_ID)
    return html, 200, {"Cache-Control": "no-store, max-age=0"}


@app.post("/quotes/<code>/<num>/doc/<kind>/pdf")
def quote_doc_pdf(code, num, kind):
    """يولّد PDF الفاوتشر/الطلب المُحرَّر ويؤرشفه مربوطاً برقم العرض."""
    if _sess() is None:
        return ("", 401)
    if kind not in _QUOTE_DOC_KINDS:
        return ("", 404)
    from hajj_app.mrz import PassportData
    settings = storage.load_settings()
    co = settings.get("company") if isinstance(settings, dict) else None
    data = request.get_json(force=True, silent=True) or {}
    data["quote_ref"] = str(num)
    guest = str(data.get("guest_ar") or data.get("guest_en") or "").strip()
    name = f"{guest or 'بلا اسم'} — عرض {num}"
    _attach_verify(kind, data)                      # QR للتحقّق
    _archive_doc(kind, data, idx=None, name=name)   # أرشفة تلقائية
    _audit("إصدار مستند من عرض سعر", f"{_DOC_TITLES[kind][0]} — {name}")
    return _pdf_response(
        lambda p: _doc_export(kind, PassportData(), co, data, p),
        f"{data.get('number', '') or kind}.pdf")


@app.get("/documents/<kind>/from-quote")
def documents_from_quote(kind):
    """اختيار عرض السعر لإصدار فاوتشر/طلب مواصلات منه: بكتابة رقمه المرجعي
    (ينتقل للمحرّر مباشرةً عند التطابق) أو بالبحث في العروض المحفوظة."""
    if _sess() is None:
        return redirect(url_for("login"))
    if kind not in _QUOTE_DOC_KINDS:
        return redirect(url_for("documents"))
    from hajj_app import umrah
    settings = storage.load_settings()
    q = (request.args.get("q") or "").strip()
    hits = umrah.find_quotes(settings, q) if q else []
    if len(hits) == 1:                             # رقم مرجعي مطابق لعرض واحد
        code, hit = hits[0]
        return redirect(url_for("quote_doc", code=code,
                                num=hit.get("number"), kind=kind))

    def _row(code, x):
        return {"code": code, "number": str(x.get("number")),
                "program": "يدوي" if code == "_manual" else code,
                "to": x.get("addressed_to", "") or "—",
                "title": x.get("title", "") or "عرض سعر",
                "date": x.get("date", ""),
                "hotels": " / ".join(str(s[2]) for s in x.get("stays") or []
                                     if isinstance(s, list) and len(s) > 2
                                     and s[2])}

    if hits:                    # الرقم نفسه محفوظ أكثر من مرّة → يختار المستخدم
        rows = [_row(code, x) for code, x in hits]
    else:
        rows = []
        for code, lst in (settings.get("umrah_quotes") or {}).items():
            for x in lst if isinstance(lst, list) else []:
                if not isinstance(x, dict) or not x.get("number"):
                    continue
                row = _row(code, x)
                hay = " ".join(str(v) for v in row.values()).lower()
                if not q or q.lower() in hay:
                    rows.append(row)
    rows.sort(key=lambda r: r["number"], reverse=True)
    return render_template("documents_quotes.html", active="documents",
                           kind=kind, label=_DOC_TITLES[kind][0],
                           icon=_DOC_TITLES[kind][1], rows=rows, q=q,
                           duplicate=len(hits) > 1, **_ctx())


@app.get("/pricings")
def pricings():
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app import umrah
    settings = storage.load_settings()
    rows = [{"number": p.get("number", ""), "title": p.get("title", "") or "تسعير",
             "date": p.get("date", ""), "currency": p.get("currency", "")}
            for p in umrah.load_pricings(settings)]
    rows.sort(key=lambda r: str(r["number"]), reverse=True)
    return render_template("pricings_list.html", active="offers", rows=rows,
                           **_ctx())


@app.get("/pricings/<num>")
def pricing_edit(num):
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app import umrah, webpricer
    settings = storage.load_settings()
    p = next((x for x in umrah.load_pricings(settings)
              if str(x.get("number")) == str(num)), None)
    if p is None:
        return redirect(url_for("pricings"))
    hajj = _mode() == app_mode.HAJJ
    data = dict(p)
    data["rate_full_period"] = "1" if hajj else ""   # الوضع يحدّد: للفترة/لليلة
    return webpricer._pricer_html(data, "مسعّر المجموعات",
                                  submit_js=webpricer._SUBMIT_WEB,
                                  back_url=url_for("pricings"), full_period=hajj,
                                  mode=_mode())


@app.post("/pricings/<num>/delete")
def pricing_delete(num):
    if _sess() is None:
        return redirect(url_for("login"))
    if _sess().can_edit:
        from hajj_app import umrah
        settings = storage.load_settings()
        try:
            umrah.delete_pricing(settings, num)
            storage.save_settings(settings)
            _audit("حذف تسعير", str(num))
        except Exception:
            pass
    return redirect(url_for("pricings"))


# ============================ برامج العمرة =================================
_PROG_GROUPS = [
    ("البيانات الأساسية", [("package", "الباقة", "package"),
                           ("name", "اسم البرنامج", ""),
                           ("manager", "المسؤول", ""),
                           ("capacity", "السعة (المقاعد)", "number"),
                           ("notes", "ملاحظات", "")]),
    ("التواريخ", [("depart_date", "المغادرة", "date"),
                  ("return_date", "العودة", "date")]),
    ("غرف الفندق المشتركة", [("room_share", "يشارك غرف الفندق مع البرنامج", "share")]),
    ("فندق مكة", [("makkah_hotel", "الفندق", ""),
                  ("makkah_nights", "الليالي", "number"),
                  ("makkah_rooms", "عدد الغرف", "number")]),
    ("فندق المدينة", [("madinah_hotel", "الفندق", ""),
                      ("madinah_nights", "الليالي", "number"),
                      ("madinah_rooms", "عدد الغرف", "number")]),
    ("الطيران", [("airline", "الناقل", "airline"),
                 ("depart_city", "المغادرة من (المدينة)", "city"),
                 ("flight_out", "رحلة الذهاب", ""),
                 ("out_depart_time", "إقلاع الذهاب", ""),
                 ("out_arrive_time", "وصول الذهاب", ""),
                 ("flight_ret", "رحلة العودة", ""),
                 ("ret_depart_time", "إقلاع العودة", ""),
                 ("ret_arrive_time", "وصول العودة", ""),
                 ("flight_pnr", "PNR الطيران", ""),
                 ("transport_pnr", "PNR النقل", "")]),
    ("الأسعار (للفرد حسب الغرفة)", [("price_single", "مفرد", "number"),
                                    ("price_double", "ثنائي", "number"),
                                    ("price_triple", "ثلاثي", "number"),
                                    ("price_quad", "رباعي", "number"),
                                    ("price_child", "طفل", "number"),
                                    ("price_infant", "رضيع", "number")]),
    ("أخرى", [("transport", "ملاحظة النقل الداخلي", ""),
              ("emergency_uae", "طوارئ الإمارات", ""),
              ("emergency_ksa", "طوارئ السعودية", "")]),
]
_PROG_KEYS = [k for _t, fs in _PROG_GROUPS for k, _l, _ty in fs]


# ألوان البرامج في الباقة بالترتيب (اختيار المستخدم للأربعة الأولى):
# (لون الشريط، خلفية الصفوف، لون كتابة الشريط، لون رمز البرنامج في الصفّ)
_PROG_COLORS = [("#1B5E20", "#CFE6CC", "#FFFFFF", "#1B5E20"),   # أخضر غامق
                ("#8BC34A", "#EEF7E0", "#17330A", "#3F6E14"),   # أخضر فاتح
                ("#29B6F6", "#E1F4FD", "#062B40", "#0277BD"),   # سماوي
                ("#D4AF37", "#FBF3D8", "#3A2C00", "#8A6D0B"),   # ذهبي
                ("#1F5FAD", "#DCE8F8", "#FFFFFF", "#1F5FAD"),   # أزرق
                ("#7B3FA0", "#EDE0F5", "#FFFFFF", "#7B3FA0"),   # بنفسجي
                ("#C26A00", "#FCE6C8", "#FFFFFF", "#A65A00"),   # برتقالي
                ("#5B3A21", "#E6DDD3", "#FFFFFF", "#5B3A21")]   # بني
_ORDINALS = ("الأول", "الثاني", "الثالث", "الرابع", "الخامس", "السادس",
             "السابع", "الثامن", "التاسع", "العاشر")


def _pkg_orders(settings) -> dict:
    """الترتيب اليدوي للبرامج في كل باقة: {الباقة: [رموز البرامج بالترتيب]}."""
    raw = settings.get("umrah_package_order") if isinstance(settings, dict) else None
    if not isinstance(raw, dict):
        return {}
    return {str(k): [str(c) for c in v] for k, v in raw.items()
            if isinstance(v, list)}


def _order_fix(settings, code: str, keep: str = None, new: str = None) -> None:
    """ينظّف الترتيب اليدوي المحفوظ من رمز برنامج (القديم «U1»، أو مفتاح برنامج
    بلا ناقل «#U1»): يُحذف من كل الباقات عدا ``keep``، أو يُستبدل بـ ``new`` عند
    تغيير الرمز — كي لا يرث برنامج جديد يأخذ رمزاً محذوفاً مكانَ القديم."""
    orders = _pkg_orders(settings)
    mine = {code: new, f"#{code}": f"#{new}" if new else None}
    changed = False
    for pkg, entries in orders.items():
        if not any(e in mine for e in entries):
            continue
        if new:
            entries[:] = [mine.get(e) or e for e in entries]
        elif pkg != keep:
            entries[:] = [e for e in entries if e not in mine]
        changed = True
    if changed:
        settings["umrah_package_order"] = orders


def _migrate_orders(settings, trips) -> None:
    """يحوّل الترتيب القديم المحفوظ برموز البرامج إلى مفاتيح خطوط الطيران — قبل
    حذف رحلة أو إخراجها أو تعديلها، كي لا يفقد خطّها مكانه ولونه."""
    orders = _pkg_orders(settings)
    codes = {t.code for t in trips}
    changed = False
    for pkg, saved in orders.items():
        if not any(e in codes for e in saved):
            continue
        rows = [{"code": t.code, "package": pkg} for t in trips
                if str(t.package or "").strip() == pkg]
        _color_rows(rows, trips, orders)
        keys: list = []
        for r in sorted(rows, key=lambda r: r["gnum"]):
            if r["gkey"] not in keys:
                keys.append(r["gkey"])
        orders[pkg] = keys
        changed = True
    if changed:
        settings["umrah_package_order"] = orders


def _color_rows(rows, trips, orders: dict = None) -> None:
    """يجمع برامج كل باقة في «برامج» حسب خط الطيران (الناقل + مدينة المغادرة،
    بكل تواريخه)، ويرقّمها (الأول، الثاني…) ويعطي كلاً لونه: بالترتيب اليدوي
    المحفوظ أولاً (▲▼)، ثم بأقرب تاريخ مغادرة وترتيب الإضافة. داخل البرنامج
    الرحلات بتاريخها. اللون نفسه في صفحة الباقة وفي قائمة كل البرامج."""
    from hajj_app import umrah
    orders = orders or {}
    tmap = {t.code: t for t in trips}
    by_pkg: dict = {}
    for i, r in enumerate(rows):
        by_pkg.setdefault(r["package"], []).append((i, r))
    for pkg, lst in by_pkg.items():
        lines = umrah.program_lines([tmap[r["code"]] for _i, r in lst
                                     if r["code"] in tmap])
        saved = orders.get(pkg) or []
        groups: dict = {}
        for i, r in lst:
            key, air, city = lines.get(r["code"], (f"#{r['code']}", "", ""))
            t = tmap.get(r["code"])
            # «البرنامج الأول/الثاني…» مكتوب في اسم الرحلة (أو ملاحظاتها) يحدّد
            # برنامجها ولونه — مهما كان طيرانها وترتيبها
            num = (umrah.program_ordinal(getattr(t, "name", ""))
                   or umrah.program_ordinal(getattr(t, "notes", "")))
            d = str(getattr(t, "depart_date", "") or "").strip() or "9999"
            g = groups.setdefault(f"@{num}" if num else key, {
                "key": f"@{num}" if num else key, "num": num,
                "airline": "" if num else air, "city": "" if num else city,
                "first": i, "date": d, "rows": [], "lines": []})
            g["date"] = min(g["date"], d)
            g["rows"].append((d, i, r))
            label = f"{air} من {city}" if air and city else air
            if label and label not in g["lines"]:
                g["lines"].append(label)

        current = set(groups)

        def pos(g):
            key = g["key"]
            if key in saved:                       # مكانه المحفوظ
                return saved.index(key)
            hits: list = []
            if "|" in key and not key.startswith("#"):
                akey, _sep, city = key.partition("|")
                pref = akey + "|"
                if not city:        # صار خطاً واحداً بعد أن كان مقسوماً بالمدن
                    hits = [k for k, e in enumerate(saved)
                            if e.startswith(pref) and e not in current]
                elif pref not in current:   # قُسم بالمدن بعد أن كان خطاً واحداً
                    hits = [k for k, e in enumerate(saved) if e == pref]
            if not hits:                           # ترتيب قديم برموز البرامج
                codes = {r["code"] for _d, _i, r in g["rows"]}
                hits = [k for k, e in enumerate(saved) if e in codes]
            return min(hits) if hits else len(saved)

        # المرقّمة بالاسم أوّلاً برقمها ولون رقمها الثابت (الأول أخضر غامق…)،
        # ثم بقية الخطوط بالترتيب اليدوي (▲▼) ثم التاريخ، بالألوان التالية
        fixed = sorted((g for g in groups.values() if g["num"]), key=lambda g: g["num"])
        free = sorted((g for g in groups.values() if not g["num"]),
                      key=lambda g: (pos(g), g["date"], g["first"]))
        top = max((g["num"] for g in fixed), default=0)
        for k, g in enumerate(fixed + free):
            n = g["num"] or top + k - len(fixed) + 1
            band, tint, fg, ink = _PROG_COLORS[(n - 1) % len(_PROG_COLORS)]
            for sub, (_d, _i, r) in enumerate(sorted(g["rows"], key=lambda x: x[:2])):
                r.update(gnum=n, gsub=sub, gkey=g["key"], gfixed=bool(g["num"]),
                         gnamed=bool(fixed), glines=g["lines"], color=band,
                         tint=tint, fg=fg, ink=ink, line_air=g["airline"],
                         line_city=g["city"])


def _program_groups(rows) -> list:
    """صفحة الباقة: لكل برنامج (خط طيران) شريط عنوان بلونه ورقمه، وتحته رحلاته."""
    rows.sort(key=lambda r: (r["gnum"], r["gsub"]))
    groups: list = []
    for r in rows:
        if not groups or groups[-1]["num"] != r["gnum"]:
            n = r["gnum"]
            groups.append({"num": n, "key": r["gkey"], "color": r["color"],
                           "fg": r["fg"], "airline": r["line_air"],
                           "city": r["line_city"], "rows": [],
                           "fixed": r["gfixed"], "lines": r["glines"],
                           # في باقة فيها «البرنامج الأول…» مكتوبة: لا رقم لغيرها
                           "show_num": r["gfixed"] or not r["gnamed"],
                           "ordinal": _ORDINALS[n - 1] if n <= len(_ORDINALS)
                           else f"رقم {n}"})
        groups[-1]["rows"].append(r)
    # الأسهم للبرامج غير المرقّمة بالاسم فقط (المرقّمة ترتيبها رقمها)
    free = [g for g in groups if not g["fixed"]]
    for k, g in enumerate(free):
        g["can_up"], g["can_down"] = k > 0, k < len(free) - 1
    for g in groups:
        g["count"] = sum(r["count"] for r in g["rows"])
        caps = [r for r in g["rows"] if isinstance(r["capacity"], int)]
        g["capacity"] = sum(r["capacity"] for r in caps)
        # زيادة رحلة لا تُخفيها مقاعد فارغة في رحلة أخرى: يُعرض كلٌّ وحده
        g["seats_left"] = sum(max(r["remaining"], 0) for r in caps)
        g["seats_over"] = sum(max(-r["remaining"], 0) for r in caps)
    return groups


def _share_choices(trip, trips) -> list:
    """خيارات «يشارك غرف الفندق مع»: البرامج الأخرى التي لا تعود إليه."""
    from hajj_app import umrah
    out = [("", "— لا (غرف مستقلّة لهذا البرنامج)")]
    by_code = {t.code: t for t in trips}
    for t in trips:
        if t.code == trip.code or umrah.room_base(t, trips, by_code).code == trip.code:
            continue
        bits = [t.code, t.name, t.airline, t.depart_date]
        out.append((t.code, " — ".join(b for b in bits if b)))
    return out


def _prog_groups(trip) -> list:
    groups = []
    for title, fs in _PROG_GROUPS:
        groups.append({"title": title, "fields": [
            {"key": k, "label": lbl, "type": ty,
             "value": str(getattr(trip, k, "") or "")} for k, lbl, ty in fs]})
    return groups


@app.get("/programs")
def programs():
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app import umrah
    from hajj_app.fields import parse_amount
    settings = storage.load_settings()
    trips = umrah.load_trips(settings)
    records = _load_records()
    pools = umrah.room_pools(trips)            # مرّة واحدة لكل القائمة
    rows = []
    for t in trips:
        n = len(umrah.trip_pilgrims(records, t.code))
        try:
            cap = int(float(str(t.capacity or "").strip() or 0))
        except ValueError:
            cap = 0
        flights = " / ".join(f for f in (t.flight_out, t.flight_ret) if f)
        rows.append({"code": t.code, "name": t.name or "—",
                     "depart": t.depart_date or "—", "return": t.return_date or "—",
                     "makkah": t.makkah_hotel or "—", "madinah": t.madinah_hotel or "—",
                     "airline": t.airline or "—", "flights": flights,
                     "dcity": umrah.canon_city(getattr(t, "depart_city", "")),
                     # الغرف المتبقّية لكل فندق: [(المدينة، المتاح، المشغول، المتبقّي)]
                     "rooms": umrah.trip_rooms_left(t, records, pool=pools[t.code]),
                     # البرامج التي تتقاسم معه غرف الفندق (طيران آخر)
                     "shared": [p.code for p in pools[t.code] if p.code != t.code],
                     "count": n, "capacity": cap or "—",
                     "remaining": (cap - n) if cap else "—",
                     "over": bool(cap and n > cap), "full": bool(cap and n == cap)})
    pkg_of = {t.code: str(t.package or "").strip() for t in trips}
    for r in rows:
        r["package"] = pkg_of.get(r["code"], "")
        r["pool"] = pools[r["code"]][0].code
    _color_rows(rows, trips, _pkg_orders(settings))
    # صفحة باقة مستقلّة (?package=): برامجها فقط + إضافة برامج مسجّلة إليها
    package = (request.args.get("package") or "").strip()
    others = []
    if package:
        if package not in umrah.load_packages(settings):
            return redirect(url_for("programs"))
        # البرنامج يتبع باقة واحدة: لا يُعرض للإضافة إلا ما ليس في باقة
        others = [r for r in rows if not r["package"]]
        rows = [r for r in rows if r["package"] == package]
    groups = _program_groups(rows) if package else []
    return render_template("programs.html", active="programs", rows=rows,
                           package=package, others=others, groups=groups,
                           msg=request.args.get("msg", ""), **_ctx())


@app.post("/programs/packages/move")
def program_package_move():
    """تقديم/تأخير برنامج (خط طيران بكل رحلاته) داخل باقته (▲▼) — يُحفظ ترتيب
    مفاتيح الخطوط في الإعدادات."""
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app import umrah
    name = (request.form.get("name") or "").strip()
    if not _sess().can_edit:
        return redirect(url_for("programs", package=name))
    settings = storage.load_settings()
    if name not in umrah.load_packages(settings):
        return redirect(url_for("programs"))
    trips = umrah.load_trips(settings)
    rows = [{"code": t.code, "package": name} for t in trips
            if str(t.package or "").strip() == name]
    orders = _pkg_orders(settings)
    _color_rows(rows, trips, orders)
    keys: list = []
    for r in sorted(rows, key=lambda r: r["gnum"]):
        if not r["gfixed"] and r["gkey"] not in keys:
            keys.append(r["gkey"])
    key = request.form.get("group") or ""
    if key in keys:
        i = keys.index(key)
        j = i - 1 if request.form.get("dir") == "up" else i + 1
        if 0 <= j < len(keys):
            keys[i], keys[j] = keys[j], keys[i]
            orders[name] = keys
            settings["umrah_package_order"] = orders
            try:
                storage.save_settings(settings)
                _audit("ترتيب برامج باقة", f"{name} — {'، '.join(keys)}")
            except Exception:
                pass
    return redirect(url_for("programs", package=name))


@app.post("/programs/packages/assign")
def program_package_assign():
    """يضمّ برامج مسجّلة إلى باقة (أو يُخرج برنامجاً منها بـ remove)."""
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app import umrah
    name = (request.form.get("name") or "").strip()
    if not _sess().can_edit:
        return redirect(url_for("programs", package=name))
    settings = storage.load_settings()
    if name not in umrah.load_packages(settings):
        return redirect(url_for("programs"))
    add = set(request.form.getlist("code"))
    remove = (request.form.get("remove") or "").strip()
    trips = umrah.load_trips(settings)
    _migrate_orders(settings, trips)
    n = 0
    for t in trips:
        if t.code in add and not str(t.package or "").strip():   # غير المنضمّ فقط
            t.package, n = name, n + 1
        elif remove and t.code == remove and t.package == name:
            t.package, n = "", n + 1
            _order_fix(settings, remove)
    if n:
        umrah.save_trips(settings, trips)
        try:
            storage.save_settings(settings)
            _audit("تعديل برامج باقة", f"{name} — {n} برنامج")
        except Exception:
            pass
    return redirect(url_for("programs", package=name))


@app.post("/programs/packages/add")
def program_package_add():
    """إضافة باقة برامج جديدة (مثل «برامج رمضان»)."""
    if _sess() is None:
        return redirect(url_for("login"))
    if not _sess().can_edit:
        return redirect(url_for("programs"))
    from hajj_app import umrah
    name = " ".join((request.form.get("name") or "").split())[:80]
    if not name:
        return redirect(url_for("programs"))
    settings = storage.load_settings()
    pkgs = umrah.load_packages(settings)
    if name in pkgs:
        return redirect(url_for("programs", msg=f"الباقة «{name}» موجودة."))
    umrah.save_packages(settings, pkgs + [name])
    try:
        storage.save_settings(settings)
        _audit("إضافة باقة برامج", name)
    except Exception:
        pass
    return redirect(url_for("programs", package=name))     # تُفتح لإضافة برامجها


@app.post("/programs/packages/delete")
def program_package_delete():
    """حذف باقة فارغة (لا تُحذف باقة فيها برامج)."""
    if _sess() is None:
        return redirect(url_for("login"))
    if not _sess().can_edit:
        return redirect(url_for("programs"))
    from hajj_app import umrah
    name = (request.form.get("name") or "").strip()
    settings = storage.load_settings()
    if any(str(t.package or "").strip() == name for t in umrah.load_trips(settings)):
        return redirect(url_for("programs", msg=f"لا تُحذف «{name}»: فيها برامج — "
                                "انقلها لباقة أخرى أولاً."))
    umrah.save_packages(settings, [p for p in umrah.load_packages(settings)
                                   if p != name])
    orders = _pkg_orders(settings)
    if orders.pop(name, None) is not None:
        settings["umrah_package_order"] = orders
    try:
        storage.save_settings(settings)
        _audit("حذف باقة برامج", name)
    except Exception:
        pass
    return redirect(url_for("programs"))


@app.get("/programs/new")
def program_new():
    if _sess() is None:
        return redirect(url_for("login"))
    if not _sess().can_edit:
        return redirect(url_for("programs"))
    from hajj_app import umrah
    settings = storage.load_settings()
    trip = umrah.UmrahTrip(code=umrah.next_code(umrah.load_trips(settings)),
                           package=(request.args.get("package") or "").strip())
    return render_template("program_edit.html", active="programs", is_new=True,
                           code=trip.code, orig="", groups=_prog_groups(trip),
                           share_opts=_share_choices(trip, umrah.load_trips(settings)),
                           airline_opts=umrah.KNOWN_AIRLINES, city_opts=umrah.UAE_CITIES,
                           services=[], **_ctx())


@app.get("/programs/<code>")
def program_edit(code):
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app import umrah
    settings = storage.load_settings()
    trips = umrah.load_trips(settings)
    trip = next((t for t in trips if t.code == code), None)
    if trip is None:
        return redirect(url_for("programs"))
    pool = umrah.room_pool(trip, trips)
    return render_template("program_edit.html", active="programs", is_new=False,
                           code=trip.code, orig=trip.code,
                           groups=_prog_groups(trip),
                           share_opts=_share_choices(trip, trips),
                           pool=[p.code for p in pool if p.code != trip.code],
                           room_src=pool[0].code,
                           airline_opts=umrah.KNOWN_AIRLINES, city_opts=umrah.UAE_CITIES,
                           services=trip.services or [], **_ctx())


@app.post("/programs/save")
def program_save():
    if _sess() is None:
        return redirect(url_for("login"))
    if not _sess().can_edit:
        return redirect(url_for("programs"))
    from hajj_app import umrah
    settings = storage.load_settings()
    trips = umrah.load_trips(settings)
    umrah.clean_shares(trips)          # إشارات لبرامج محذوفة (قبل إعادة استخدام رمزها)
    _migrate_orders(settings, trips)   # ترتيب قديم بالرموز → مفاتيح الخطوط
    data = {k: (request.form.get(k, "") or "").strip() for k in _PROG_KEYS}
    data["code"] = (request.form.get("code", "") or "").strip()
    names = request.form.getlist("service_name")
    prices = request.form.getlist("service_price")
    data["services"] = [{"name": n.strip(), "price": p.strip()}
                        for n, p in zip(names, prices) if n.strip()]
    if not data["code"]:
        data["code"] = umrah.next_code(trips)
    trip = umrah.trip_from_dict(data)
    key = (request.form.get("orig", "") or "").strip() or trip.code
    # البرنامج المنضمّ إلى باقة لا يُنقل إلى باقة أخرى (يُخرَج منها أوّلاً)
    msg = ""
    # مشاركة غرف الفندق: برنامج موجود غير هذا، ولا يعود إليه (منع الحلقات)
    share = str(trip.room_share or "").strip()
    target = next((t for t in trips if t.code == share and t.code not in
                   (key, trip.code)), None)
    if share and (target is None
                  or umrah.room_base(target, trips).code in (key, trip.code)):
        trip.room_share = ""
        msg = f"لا يمكن مشاركة غرف الفندق مع «{share}» (غير موجود أو يشارك هذا البرنامج)."
    elif target is not None:
        trip.room_share = umrah.room_base(target, trips).code   # الأساسي مباشرة
    old = next((t for t in trips if t.code == key), None)
    old_pkg = str(getattr(old, "package", "") or "").strip()
    if old_pkg and trip.package and trip.package != old_pkg:
        trip.package = old_pkg
        msg = msg + (" " if msg else "") + (f"البرنامج «{trip.code}» تابع لباقة «{old_pkg}» ولا يُضاف إلى باقة أخرى"
               " — أخرِجه منها أوّلاً (↩ إخراج). حُفظت بقية التعديلات.")
    # مكان البرنامج في القائمة بعد إزالة القديم (وأي برنامج بنفس الرمز الجديد)
    at = next((sum(1 for u in trips[:i] if u.code not in (key, trip.code))
               for i, t in enumerate(trips) if t.code == key), None)
    if old is None:
        _order_fix(settings, trip.code)            # برنامج جديد: بلا مكان موروث
    else:
        if key != trip.code:
            _order_fix(settings, key, new=trip.code)
        _order_fix(settings, trip.code, keep=trip.package or None)
    trips = [t for t in trips if t.code != key and t.code != trip.code]
    umrah.rename_share(trips, key, trip.code)
    if at is not None and at <= len(trips):
        trips.insert(at, trip)                      # التعديل يُبقي مكانه
    else:
        trips.append(trip)
    umrah.sync_pool_hotels(trips, trip.code)        # فندق واحد للبرامج المشتركة
    umrah.save_trips(settings, trips)
    if trip.package:                               # باقة كُتبت يدوياً تُسجَّل
        umrah.save_packages(settings, umrah.load_packages(settings))
    try:
        storage.save_settings(settings)
        _audit("حفظ برنامج عمرة", f"{trip.code} — {getattr(trip,'name','') or ''}")
    except Exception:
        pass
    return redirect(url_for("programs", msg=msg) if msg else url_for("programs"))


@app.post("/programs/<code>/delete")
def program_delete(code):
    if _sess() is None:
        return redirect(url_for("login"))
    if _sess().can_edit:
        from hajj_app import umrah
        settings = storage.load_settings()
        all_trips = umrah.load_trips(settings)
        _migrate_orders(settings, all_trips)       # قبل الحذف: لا يضيع مكان خطّه
        # من كان يشارك غرف المحذوف: أوّلهم يصبح الأساسي ويأخذ عدد الغرف
        trips = umrah.detach_trip(all_trips, code)
        umrah.save_trips(settings, trips)
        _order_fix(settings, code)                 # لا يرث برنامج جديد مكانه
        try:
            storage.save_settings(settings)
            _audit("حذف برنامج عمرة", str(code))
        except Exception:
            pass
    return redirect(url_for("programs"))


def _trip_or_none(code):
    from hajj_app import umrah
    return next((t for t in umrah.load_trips(storage.load_settings())
                 if t.code == code), None)


@app.get("/programs/<code>/transport.pdf")
def program_transport_pdf(code):
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app import umrah, pdf_io
    trip = _trip_or_none(code)
    if trip is None:
        return redirect(url_for("programs"))
    recs = umrah.trip_pilgrims(_load_records(), code)
    p = _tmp(".pdf")
    pdf_io.export_umrah_transport_pdf(
        recs, p, program_name=(trip.name or trip.code),
        transport_pnr=str(getattr(trip, "transport_pnr", "") or ""))
    return send_file(p, mimetype="application/pdf", as_attachment=False,
                     download_name="transport.pdf")


@app.get("/programs/<code>/rooming/<city>.pdf")
def program_rooming_pdf(code, city):
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app import umrah, pdf_io
    trip = _trip_or_none(code)
    if trip is None or city not in ("makkah", "madinah"):
        return redirect(url_for("programs"))
    if city == "makkah":
        label, rf, hotel, nights = ("مكة المكرّمة", "makkah_room",
                                    trip.makkah_hotel, trip.makkah_nights)
    else:
        label, rf, hotel, nights = ("المدينة المنوّرة", "madinah_room",
                                    trip.madinah_hotel, trip.madinah_nights)
    recs = umrah.trip_pilgrims(_load_records(), code)
    p = _tmp(".pdf")
    pdf_io.export_umrah_rooming_pdf(
        recs, p, city_label=label, hotel=hotel or "", nights=str(nights or ""),
        program_name=(trip.name or trip.code), room_field=rf)
    return send_file(p, mimetype="application/pdf", as_attachment=False,
                     download_name="rooming.pdf")


# ======================= مستندات كل معتمر/حاج ==============================
_DOC_TITLES = {"receipt": ("سند قبض", "🧾"), "invoice": ("فاتورة ضريبية", "🧾"),
               "contract": ("عقد خدمات", "📜"), "voucher": ("فاوتشر فندق", "🏨"),
               "treq": ("طلب حجز مواصلات", "🚖")}


def _web_doc_number(settings, rec, store_key, prefix, start):
    """رقم مستند ثابت لكل سجلّ (نفس منطق سطح المكتب: عدّاد محفوظ + ثبات للسجلّ)."""
    key = (str(getattr(rec, "reference_number", "") or "").strip()
           or str(getattr(rec, "family_number", "") or "").strip()
           or (getattr(rec, "full_name_ar", "") or
               getattr(rec, "full_name_en", "") or "").strip())
    store = settings.setdefault(store_key, {})
    if key and key in store:
        n = int(store[key])
    else:
        n = int(settings.get(store_key + "_next", start))
        if key:
            store[key] = n
        settings[store_key + "_next"] = n + 1
        try:
            storage.save_settings(settings)
        except Exception:
            pass
    return f"{prefix}{n:04d}"


def _doc_build(kind, rec, co, settings):
    """يبني بيانات المستند القابلة للتحرير + مخطّطه حسب النوع."""
    from hajj_app import pdf_io, umrah
    prog = str(getattr(rec, "trip", "") or getattr(rec, "program", "") or "")
    if kind == "receipt":
        num = _web_doc_number(settings, rec, "receipts", "", 119)
        return pdf_io.build_receipt_data(rec, company=co, number=num), \
            pdf_io.RECEIPT_SCHEMA
    if kind == "invoice":
        num = _web_doc_number(settings, rec, "invoices", "INV-", 119)
        return pdf_io.build_invoice_data(rec, company=co, number=num), \
            pdf_io.INVOICE_SCHEMA
    if kind == "contract":
        num = _web_doc_number(settings, rec, "contracts", "CON-", 119)
        return pdf_io.build_contract_data(rec, company=co, number=num), \
            pdf_io.CONTRACT_SCHEMA
    if kind == "voucher":
        num = umrah.next_voucher_number(settings)
        try:
            storage.save_settings(settings)
        except Exception:
            pass
        return pdf_io.build_voucher_data(rec, trip=None, program_name=prog,
                                         company=co, number=num), \
            pdf_io.VOUCHER_SCHEMA
    num = umrah.next_transport_number(settings)   # treq
    try:
        storage.save_settings(settings)
    except Exception:
        pass
    return pdf_io.build_transport_request_data(rec, trip=None, company=co,
                                               number=num), pdf_io.TREQ_SCHEMA


def _doc_export(kind, rec, co, data, path):
    """يولّد الـ PDF للمستند من البيانات المُحرَّرة."""
    from hajj_app import pdf_io
    if kind == "receipt":
        c = pdf_io.company_info(co)
        pdf_io.export_receipt_pdf(rec, path, company=c["name_ar"],
                                  company_en=c["name_en"], data=data)
    elif kind == "invoice":
        pdf_io.export_invoice_pdf(rec, path, company=co, data=data)
    elif kind == "contract":
        pdf_io.export_contract_pdf(rec, path, company=co, data=data)
    elif kind == "voucher":
        pdf_io.export_umrah_voucher_pdf(rec, path, trip=None, company=co,
                                        data=data)
    else:                                          # treq
        pdf_io.export_umrah_transport_request_pdf(rec, path, company=co,
                                                  data=data)


def _archive_doc(kind, data, *, idx=None, name=None):
    """أرشفة تلقائية للمستند المُنشأ (بياناته فقط — يُعاد توليد PDF لاحقاً).

    لا يرفع استثناءً كي لا يُعطّل توليد المستند إن تعذّرت الأرشفة.
    """
    try:
        import secrets as _secrets
        from datetime import datetime as _dt
        docs = storage.load_documents(session=_sess())
        docs.append({
            "id": _secrets.token_hex(6),
            "ts": _dt.now().replace(microsecond=0).isoformat(),
            "kind": kind,
            "title": _DOC_TITLES.get(kind, (kind, ""))[0],
            "number": str((data or {}).get("number", "") or ""),
            "name": name or "",
            "idx": idx,
            "data": data or {},
        })
        if len(docs) > 5000:                       # حدّ أمان لعدم تضخّم الملف
            docs = docs[-5000:]
        storage.save_documents(docs, session=_sess())
    except Exception:                              # noqa: BLE001
        pass


@app.get("/archive")
def archive():
    """أرشيف المستندات المُنشأة تلقائياً — بحث وفلترة وإعادة طباعة."""
    if _sess() is None:
        return redirect(url_for("login"))
    docs = storage.load_documents(session=_sess())
    q = (request.args.get("q") or "").strip()
    ql = q.lower()
    buckets = {k: [] for k in _DOC_TITLES}          # مجموعة لكل نوع مستند
    shown = 0
    for d in reversed(docs):
        if ql and ql not in " ".join(str(d.get(k, "")) for k in
                                     ("title", "number", "name")).lower():
            continue
        k = d.get("kind")
        buckets.setdefault(k, [])
        buckets[k].append({"id": d.get("id"),
                           "ts": (d.get("ts") or "").replace("T", "  "),
                           "number": d.get("number") or "—",
                           "name": d.get("name") or "—"})
        shown += 1
    groups = [{"title": _DOC_TITLES.get(k, (k, ""))[0],
               "icon": _DOC_TITLES.get(k, ("", ""))[1], "rows": buckets[k]}
              for k in _DOC_TITLES if buckets.get(k)]
    return render_template("archive.html", active="archive", groups=groups,
                           q=q, total=len(docs), shown=shown, **_ctx())


@app.get("/archive/<doc_id>.pdf")
def archive_pdf(doc_id):
    """يعيد توليد PDF لمستند مؤرشف من بياناته المحفوظة."""
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app.mrz import PassportData
    docs = storage.load_documents(session=_sess())
    entry = next((d for d in docs if d.get("id") == doc_id), None)
    if not entry or entry.get("kind") not in _DOC_TITLES:
        return redirect(url_for("archive"))
    settings = storage.load_settings()
    co = settings.get("company") if isinstance(settings, dict) else None
    kind = entry["kind"]
    data = entry.get("data") or {}
    rec = PassportData()                            # data تكفي لإعادة التوليد
    idx = entry.get("idx")
    if isinstance(idx, int):
        recs = _load_records()
        if 0 <= idx < len(recs):
            rec = recs[idx]
    title = _DOC_TITLES[kind][0]
    return _pdf_response(lambda p: _doc_export(kind, rec, co, data, p),
                         f"{title}-{entry.get('number','') or ''}.pdf")


@app.post("/archive/<doc_id>/delete")
def archive_delete(doc_id):
    """حذف مستند من الأرشيف (للمحرّرين)."""
    if _sess() is None:
        return redirect(url_for("login"))
    if _sess().can_edit:
        docs = storage.load_documents(session=_sess())
        docs = [d for d in docs if d.get("id") != doc_id]
        try:
            storage.save_documents(docs, session=_sess())
            _audit("حذف مستند من الأرشيف", doc_id)
        except Exception:
            pass
    return redirect(url_for("archive"))


@app.get("/doc/<int:idx>/<kind>")
def doc_edit(idx, kind):
    if _sess() is None:
        return redirect(url_for("login"))
    if kind not in _DOC_TITLES:
        return redirect(url_for("hujjaj"))
    records = _load_records()
    moved = _follow(records, idx, "doc_edit", kind=kind)
    if moved:
        return moved
    if not (0 <= idx < len(records)):
        return redirect(url_for("hujjaj"))
    from hajj_app import webdoc
    settings = storage.load_settings()
    co = settings.get("company") if isinstance(settings, dict) else None
    data, schema = _doc_build(kind, records[idx], co, settings)
    data["_rec"] = _rec_token(records[idx])        # يتحقّق منه الحفظ (الموضع قد يتغيّر)
    title, icon = _DOC_TITLES[kind]
    return webdoc._doc_html(
        data, schema, title, icon,
        submit_action=webdoc.web_submit_action(
            url_for("doc_pdf", idx=idx, kind=kind)),
        back_url=url_for("hujjaj_edit", idx=idx), mode=_mode(),
        build=_BUILD_ID)


@app.post("/doc/<int:idx>/<kind>/pdf")
def doc_pdf(idx, kind):
    if _sess() is None:
        return ("", 401)
    if kind not in _DOC_TITLES:
        return ("", 404)
    records = _load_records()
    data = request.get_json(force=True, silent=True) or {}
    j = _resolve_idx(records, idx, str(data.pop("_rec", "") or ""))
    if j is None:                                  # تغيّر الكشف منذ فتح المحرّر
        return ("تغيّر الكشف منذ فتح المستند — أعد فتحه من صفحة السجلّ.", 409)
    idx = j
    settings = storage.load_settings()
    co = settings.get("company") if isinstance(settings, dict) else None
    title = _DOC_TITLES[kind][0]
    _name = getattr(records[idx], "full_name_ar", "") or getattr(
        records[idx], "full_name_en", "") or ""
    _attach_verify(kind, data, uid=getattr(records[idx], "uid", "") or "")
    _archive_doc(kind, data, idx=idx, name=_name)   # أرشفة تلقائية
    _audit("إصدار مستند", f"{title} — {_name}")
    return _pdf_response(
        lambda p: _doc_export(kind, records[idx], co, data, p),
        f"{title}-{data.get('number','') or ''}.pdf")


@app.get("/hujjaj/<int:idx>/packet.pdf")
def pilgrim_packet(idx):
    """حزمة مستندات حاج واحد: الجواز (إن وُجدت صورته) + البطاقة + سند + عقد."""
    if _sess() is None:
        return redirect(url_for("login"))
    records = _load_records()
    moved = _follow(records, idx, "pilgrim_packet")
    if moved:
        return moved
    if not (0 <= idx < len(records)):
        return redirect(url_for("hujjaj"))
    rec = records[idx]
    import io
    import shutil
    import tempfile
    from hajj_app import pdf_io
    settings = storage.load_settings()
    co = settings.get("company") if isinstance(settings, dict) else None
    company = pdf_io.company_info(co)
    season = str(settings.get("season_year", "") or "")
    name = getattr(rec, "full_name_ar", "") or getattr(rec, "full_name_en", "") \
        or "حاج"
    tmpdir = tempfile.mkdtemp(prefix="hajj_packet_")
    out = _tmp(".pdf")
    parts = []
    try:
        try:                                   # ١) صورة الجواز إن وُجدت
            from hajj_app import images as imgmod
            iid = getattr(rec, "image_id", "")
            if iid and imgmod.has_image(iid, imgmod.PASSPORT):
                data = imgmod.load_image(iid, imgmod.PASSPORT, _sess())
                if data:
                    entries = []
                    for k, pb in enumerate(imgmod.render_pages_png(data), 1):
                        ip = os.path.join(tmpdir, f"pp{k}.img")
                        with open(ip, "wb") as fh:
                            fh.write(pb)
                        entries.append((name, ip))
                    pp = os.path.join(tmpdir, "passport.pdf")
                    pdf_io.export_passports_pdf(entries, pp, title="الجواز")
                    parts.append(pp)
        except Exception:                      # noqa: BLE001
            pass
        try:                                   # ٢) البطاقة
            bp = os.path.join(tmpdir, "badge.pdf")
            pdf_io.export_badges_pdf([rec], bp, company=company["name_ar"],
                                     session=_sess())
            parts.append(bp)
        except Exception:                      # noqa: BLE001
            pass
        rp = os.path.join(tmpdir, "receipt.pdf")   # ٣) سند القبض
        pdf_io.export_receipt_pdf(
            rec, rp, season=season,
            number=_web_doc_number(settings, rec, "receipts", "", 119))
        parts.append(rp)
        cp = os.path.join(tmpdir, "contract.pdf")  # ٤) العقد
        pdf_io.export_contract_pdf(
            rec, cp, company=co, season=season,
            number=_web_doc_number(settings, rec, "contracts", "CON-", 119))
        parts.append(cp)
        pdf_io.merge_pdfs(parts, out)
    finally:
        for pth in parts:
            try:
                os.remove(pth)
            except OSError:
                pass
        shutil.rmtree(tmpdir, ignore_errors=True)
    with open(out, "rb") as f:
        buf = io.BytesIO(f.read())
    try:
        os.unlink(out)
    except OSError:
        pass
    buf.seek(0)
    return send_file(buf, mimetype="application/pdf", as_attachment=False,
                     download_name=f"حزمة-{name}.pdf")


@app.get("/reports/bulk/<kind>.pdf")
def rep_bulk_docs(kind):
    """توليد جماعي لمستند (سند/فاتورة/عقد) لكل السجلات في ملف PDF واحد."""
    if _sess() is None:
        return redirect(url_for("login"))
    if not _sess().can_edit:
        return redirect(url_for("reports"))
    if kind not in ("receipt", "invoice", "contract"):
        return redirect(url_for("reports"))
    import io
    import shutil
    import tempfile
    from hajj_app import pdf_io
    records = _load_records()
    if not records:
        return redirect(url_for("reports"))
    settings = storage.load_settings()
    co = settings.get("company") if isinstance(settings, dict) else None
    tmpdir = tempfile.mkdtemp(prefix="hajj_bulk_")
    out = _tmp(".pdf")
    parts = []
    try:
        for i, rec in enumerate(records):
            pth = os.path.join(tmpdir, f"{i}.pdf")
            try:
                data, _schema = _doc_build(kind, rec, co, settings)
                _doc_export(kind, rec, co, data, pth)
                parts.append(pth)
            except Exception:                  # noqa: BLE001
                continue
        if not parts:
            return redirect(url_for("reports"))
        pdf_io.merge_pdfs(parts, out)
    finally:
        for pth in parts:
            try:
                os.remove(pth)
            except OSError:
                pass
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except OSError:
            pass
    with open(out, "rb") as f:
        buf = io.BytesIO(f.read())
    try:
        os.unlink(out)
    except OSError:
        pass
    buf.seek(0)
    label = _DOC_TITLES[kind][0]
    return send_file(buf, mimetype="application/pdf", as_attachment=False,
                     download_name=f"{label}-الجميع.pdf")


# ==================== مواعيد وتعليمات السفر (برامج الحج) ===================
@app.get("/travel")
def travel_list():
    """قائمة برامج الحج لتحرير «مواعيد وتعليمات السفر» لكلٍّ منها."""
    if _sess() is None:
        return redirect(url_for("login"))
    if _mode() != app_mode.HAJJ:              # ميزة خاصّة بالحج
        return redirect(url_for("reports"))
    from hajj_app.programs import PROGRAM_NAMES
    progs = [{"idx": i, "name": n} for i, n in enumerate(PROGRAM_NAMES)]
    return render_template("travel.html", active="travel", progs=progs, **_ctx())


@app.get("/travel/<int:idx>")
def travel_edit(idx):
    if _sess() is None:
        return redirect(url_for("login"))
    if _mode() != app_mode.HAJJ:
        return redirect(url_for("reports"))
    from hajj_app import travel, webdoc
    from hajj_app.programs import PROGRAM_NAMES, load_programs
    if not (0 <= idx < len(PROGRAM_NAMES)):
        return redirect(url_for("travel_list"))
    settings = storage.load_settings()
    progs = load_programs(settings)
    prog = progs[idx] if idx < len(progs) else None
    data = travel.flatten(travel.load_travel(settings, idx, prog))
    name = PROGRAM_NAMES[idx]
    return webdoc._doc_html(
        data, travel.web_schema(), f"مواعيد وتعليمات السفر — {name}", "🧳",
        submit_action=webdoc.web_submit_action(url_for("travel_pdf", idx=idx)),
        back_url=url_for("travel_list"), mode=_mode(),
        build=_BUILD_ID)


@app.post("/travel/<int:idx>/pdf")
def travel_pdf(idx):
    """يحفظ مواعيد/تعليمات البرنامج (للمحرّرين) ويعيد PDF للمعاينة."""
    if _sess() is None:
        return ("", 401)
    if _mode() != app_mode.HAJJ:
        return ("", 404)
    from hajj_app import travel
    from hajj_app.programs import PROGRAM_NAMES
    from hajj_app.pdf_io import export_travel_pdf
    if not (0 <= idx < len(PROGRAM_NAMES)):
        return ("", 404)
    settings = storage.load_settings()
    result = request.get_json(force=True, silent=True) or {}
    nested = travel.unflatten(result)
    name = PROGRAM_NAMES[idx]
    season = str(settings.get("season_year", "") or "")
    if _sess().can_edit:                       # المطّلع يعاين دون حفظ
        travel.save_travel(settings, idx, nested)
        try:
            storage.save_settings(settings)
            _audit("تعديل مواعيد وتعليمات السفر", name)
        except Exception:
            pass
    return _pdf_response(
        lambda p: export_travel_pdf(p, program_name=name, data=nested,
                                    season=season),
        f"مواعيد-السفر-{name}.pdf")


# ==================== فحص الجودة والجاهزية =================================
@app.get("/quality")
def quality_report():
    """فحص جاهزية الكشف: صلاحية الجواز، التكرار، النقص + نظرة جاهزية عامة."""
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app import quality
    records = _load_records()
    programs = None
    if _mode() == app_mode.HAJJ:
        from hajj_app.programs import PROGRAM_NAMES, load_programs
        progs = load_programs(storage.load_settings())
        programs = {PROGRAM_NAMES[i]: p for i, p in enumerate(progs)
                    if i < len(PROGRAM_NAMES)}
    report = quality.check_records(records, programs=programs)
    groups = [{"kind": k, "issues": [
        {"idx": iss.index, "name": iss.name, "passport": iss.passport,
         "detail": iss.detail} for iss in v]}
        for k, v in report.by_kind().items()]
    labels = {"passport": "جواز ساري", "visa": "تأشيرة", "permit": "تصريح",
              "vaccination": "تطعيم", "payment": "سداد كامل", "contact": "تواصل"}
    tally = {k: 0 for k in labels}
    for r in records:
        for k, v in quality.pilgrim_readiness(r).items():
            if v:
                tally[k] += 1
    n = len(records)
    readiness = [{"label": labels[k], "done": tally[k], "total": n,
                  "pct": round(100 * tally[k] / n) if n else 0} for k in labels]
    return render_template(
        "quality.html", active="quality", groups=groups, total=report.total,
        issues_count=len(report.issues), clean=report.clean,
        readiness=readiness, **_ctx())


# ==================== المجموعات والمرشدون ==================================
@app.route("/groups", methods=["GET", "POST"])
def groups_page():
    """المجموعات والمرشدون: مرشد/مطوّف وهاتف لكل مجموعة (تُحدَّد في سجلّ كل حاج)."""
    if _sess() is None:
        return redirect(url_for("login"))
    records = _load_records()
    settings = storage.load_settings()
    saved = dict(settings.get("groups", {}) or {})
    counts: dict = {}
    for r in records:
        name = str(getattr(r, "group", "") or "").strip()
        if name:
            counts[name] = counts.get(name, 0) + 1
    names = sorted(set(counts) | set(saved))
    if request.method == "POST" and _sess().can_edit:
        data = {}
        for name in names:
            data[name] = {
                "guide": (request.form.get(f"guide__{name}", "") or "").strip(),
                "phone": (request.form.get(f"phone__{name}", "") or "").strip()}
        settings["groups"] = data
        try:
            storage.save_settings(settings)
            _audit("تعديل المجموعات والمرشدين", f"{len(data)} مجموعة")
        except Exception:
            pass
        return redirect(url_for("groups_page", saved=1))
    rows = [{"name": n, "count": counts.get(n, 0),
             "guide": str(saved.get(n, {}).get("guide", "") or ""),
             "phone": str(saved.get(n, {}).get("phone", "") or "")}
            for n in names]
    return render_template("groups.html", active="groups", rows=rows,
                           saved=request.args.get("saved"), **_ctx())


# ==================== سجلّ التدقيق =========================================
@app.get("/audit")
def audit_log():
    """سجلّ التدقيق (من فعل ماذا ومتى) — للمدير فقط."""
    if _sess() is None:
        return redirect(url_for("login"))
    if not _sess().is_admin:
        return render_template("audit.html", active="audit", forbidden=True,
                               entries=[], **_ctx())
    from hajj_app import audit
    entries = [{"ts": (e.get("ts") or "").replace("T", "  "),
                "user": e.get("user") or "—", "action": e.get("action") or "",
                "details": e.get("details") or ""}
               for e in audit.read_entries(limit=500)]
    return render_template("audit.html", active="audit", forbidden=False,
                           entries=entries, **_ctx())


# ==================== رسائل واتساب الجماعية ================================
@app.route("/whatsapp", methods=["GET", "POST"])
def whatsapp_page():
    """يبني روابط wa.me لكل حاجّ برسالة جاهزة (لا يرسل تلقائياً)."""
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app import whatsapp
    records = _load_records()
    settings = storage.load_settings()
    cc_default = str(settings.get("whatsapp_cc", "971")).strip() or "971"
    tpl_names = list(whatsapp.TEMPLATES.keys())
    message = whatsapp.DEFAULT_TEMPLATE
    cc = cc_default
    rows = None
    if request.method == "POST":
        tpl = request.form.get("template", "")
        if tpl and tpl in whatsapp.TEMPLATES and request.form.get("use_tpl"):
            message = whatsapp.TEMPLATES[tpl]
        else:
            message = request.form.get("message", "") or whatsapp.DEFAULT_TEMPLATE
        cc = (request.form.get("cc", "") or cc_default).strip() or cc_default
        rows = []
        for i, rec in enumerate(records):
            name = getattr(rec, "full_name_ar", "") or getattr(
                rec, "full_name_en", "") or "—"
            link = whatsapp.wa_link(getattr(rec, "phone", ""),
                                    whatsapp.render_message(message, rec), cc)
            rows.append({"idx": i, "name": name,
                         "phone": str(getattr(rec, "phone", "") or "—"),
                         "link": link})
    return render_template(
        "whatsapp.html", active="whatsapp", tpl_names=tpl_names, message=message,
        cc=cc, rows=rows, count=len(records),
        placeholders=" ".join(whatsapp.PLACEHOLDERS), **_ctx())


# ==================== الرسوم البيانية (توزيعات) ===========================
@app.get("/charts")
def charts():
    """توزيعات الكشف (برنامج/فندق/جنسية/حالة) كأشرطة + ملخّص مالي."""
    if _sess() is None:
        return redirect(url_for("login"))
    records = _load_records()
    group_key = "trip" if _mode() == app_mode.UMRAH else "program"
    specs = [(group_key, "التوزيع حسب البرنامج"),
             ("hotel", "التوزيع حسب الفندق"),
             ("nationality_ar", "التوزيع حسب الجنسية"),
             ("status", "التوزيع حسب الحالة")]
    charts_data = []
    for key, title in specs:
        buckets = stats.distribution(records, key)[:8]
        charts_data.append({"title": title, "bars": [
            {"label": b.label, "count": b.count, "percent": b.percent}
            for b in buckets]})
    fin = stats.financial_summary(records)
    fin_rows = fin.as_rows()
    return render_template("charts.html", active="charts", charts=charts_data,
                           fin_rows=fin_rows, count=len(records), **_ctx())


# ==================== إشغال الغرف ==========================================
@app.get("/occupancy")
def occupancy():
    """إشغال الغرف: المشغول مقابل السعة لكل غرفة، مع التجاوز والشواغر."""
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app.rooming import group_records_by_room
    records = _load_records()
    rooms_raw, unplaced = group_records_by_room(records)
    rows = []
    full = over = free_beds = 0
    for hotel, cap, number, occ in rooms_raw:
        n = len(occ)
        cap = cap or n
        if n > cap:
            over += 1
            status, cls = f"تجاوز (+{n - cap})", "rover"
        elif n == cap:
            full += 1
            status, cls = "مكتملة", "rfull"
        else:
            free_beds += (cap - n)
            status, cls = f"شاغر {cap - n}", "rpart"
        rows.append({"hotel": hotel or "—", "number": number, "cap": cap,
                     "occ": n, "status": status, "cls": cls})
    summary = {"rooms": len(rows), "full": full, "over": over,
               "free": free_beds, "unplaced": len(unplaced)}
    return render_template("occupancy.html", active="occupancy", rows=rows,
                           summary=summary, pools=_occupancy_pools(records),
                           **_ctx())


def _occupancy_pools(records) -> list:
    """(العمرة) الغرف المتبقّية لكل فندق برنامج — والبرامج المتقاسمة غرف فندق
    واحدة (أكثر من طيران بنفس التاريخ) صفٌّ واحد بعدد مشترك."""
    if _mode() != app_mode.UMRAH:
        return []
    from hajj_app import umrah
    trips = umrah.load_trips(storage.load_settings())
    pools = umrah.room_pools(trips)
    out = []
    for t in trips:
        pool = pools[t.code]
        if pool[0].code != t.code:
            continue                       # صفّ واحد لكل مجموعة (عند الأساسي)
        left = umrah.trip_rooms_left(t, records, pool=pool)
        if not left:
            continue
        out.append({"programs": [(p.code, p.airline or "") for p in pool],
                    "depart": t.depart_date or "—",
                    "hotels": {"مكة": t.makkah_hotel or "—",
                               "المدينة": t.madinah_hotel or "—"},
                    "rooms": left})
    return out


@app.get("/occupancy/rooming.pdf")
def rooming_pdf():
    """كشف التسكين (PDF): كل غرفة وسكّانها مجموعين ككتلة — جاهز للطباعة."""
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app import pdf_io
    records = _load_records()
    title = f"كشف تسكين {_noun()} — موسم {_season()}{_season_suffix()}"
    return _pdf_response(
        lambda p: pdf_io.export_pdf(records, p, title=title, group_by_room=True),
        "rooming.pdf")


@app.get("/occupancy/rooming-cards.pdf")
def rooming_cards_pdf():
    """طباعة تسكين الغرف كبطاقات (٣ بالصفّ) — كالنموذج المطبوع."""
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app import pdf_io
    settings = storage.load_settings()
    co = settings.get("company") if isinstance(settings, dict) else None
    campaign = pdf_io.company_info(co)["name_ar"]
    return _pdf_response(
        lambda p: pdf_io.export_rooming_cards_pdf(
            _load_records(), p, title=f"تسكين الغرف — {_noun()}",
            campaign=campaign, season=f"{_season()}{_season_suffix()}"),
        "rooming-cards.pdf")


@app.route("/occupancy/edit", methods=["GET", "POST"])
def rooming_edit():
    """تعديل تسكين الغرف يدوياً: الفندق/نوع الغرفة/رقم الغرفة لكل سجلّ."""
    if _sess() is None:
        return redirect(url_for("login"))
    if not _sess().can_edit:
        return redirect(url_for("occupancy"))
    records = _load_records()
    if request.method == "POST":
        n = skipped = 0
        # كل صفّ يحمل بصمة سجلّه: يُطبَّق على صاحبه حتى لو تغيّر موضعه،
        # ويُتخطّى إن لم يُعرف (حُذف/عُدّل في الأثناء) — لا يُنقل لشخص آخر
        rows_i = sorted({int(k[3:]) for k in request.form
                         if k.startswith("fp_") and k[3:].isdigit()})
        for i in rows_i:
            j = _resolve_idx(records, i, request.form.get(f"fp_{i}", ""))
            if j is None:
                skipped += 1
                continue
            r = records[j]
            changed = False
            for attr, fld in (("hotel", "hotel"), ("room_type", "rtype"),
                              ("room_number", "rnum")):
                key = f"{fld}_{i}"
                if key in request.form:
                    val = (request.form.get(key) or "").strip()
                    if str(getattr(r, attr, "") or "") != val:
                        setattr(r, attr, val)
                        changed = True
            if changed:
                n += 1
        try:
            storage.save_records(records, session=_sess())
            _audit("تعديل التسكين يدوياً", f"{n} سجلّ")
        except Exception:
            pass
        return redirect(url_for("rooming_edit", saved=n, skipped=skipped))

    def _distinct(attr):
        return sorted({str(getattr(r, attr, "") or "").strip() for r in records
                       if str(getattr(r, attr, "") or "").strip()})

    def _natkey(s):                                # ترتيب طبيعي (الأرقام كأرقام)
        s = str(s or "")
        parts = re.split(r"(\d+)", s)
        return [int(x) if x.isdigit() else x for x in parts]

    sort = (request.args.get("sort") or "").strip()
    sortmap = {"rtype": ("room_type", "room_number"),
               "bus": ("transport", "family_number"),
               "family": ("family_number", "room_number")}
    items = list(enumerate(records))
    if sort in sortmap:
        attrs = sortmap[sort]
        items.sort(key=lambda t: [_natkey(getattr(t[1], a, "")) for a in attrs])
    rows = [{"idx": i, "name": (getattr(r, "full_name_ar", "") or getattr(
                 r, "full_name_en", "") or "—"), "fp": _rec_token(r),
             "hotel": str(getattr(r, "hotel", "") or ""),
             "rtype": str(getattr(r, "room_type", "") or ""),
             "rnum": str(getattr(r, "room_number", "") or ""),
             "fam": str(getattr(r, "family_number", "") or ""),
             "bus": str(getattr(r, "transport", "") or "")}
            for i, r in items]
    return render_template("rooming_edit.html", active="occupancy", rows=rows,
                           hotels=_distinct("hotel"), rtypes=_distinct("room_type"),
                           sort=sort, saved=request.args.get("saved"),
                           skipped=request.args.get("skipped"), **_ctx())


# ==================== مخيمات منى وعرفة =====================================
# خرائط ASCII للمخيمات — نتفادى العربية في مسار الرابط (بعض خوادم WSGI تخنقها)
_CAMP_SLUGS = {"mina": "منى", "arafat": "عرفة"}

_DEFAULT_CAMPAIGN = "المصطفى للحج والعمرة"


def _load_camps():
    """تسكين المخيمات المحفوظ (دائم، مشفّر، مشترك) — dict بمفتاح slug المخيّم."""
    try:
        return storage.load_camps(session=_sess()) or {}
    except Exception:                              # noqa: BLE001
        return {}


def _save_camps(camps):
    try:
        storage.save_camps(camps, session=_sess())
    except Exception:                              # noqa: BLE001
        pass


def _camp_entry(camps, camp_slug):
    """حالة مخيّم واحد داخل خريطة التسكين (تُهيّأ إن لم توجد)."""
    st = camps.get(camp_slug)
    if not isinstance(st, dict):
        st = {}
        camps[camp_slug] = st
    st.setdefault("assigned", [])
    st.setdefault("number", 1)
    st.setdefault("last", None)
    st.setdefault("tents", [])
    st["camp"] = camp_slug
    return st


@app.get("/camps")
def camps_page():
    """صفحة خيارات تسكين المخيمات (منى/عرفة): تصنيف/قطاع/سعة ثم معاينة PDF."""
    if _sess() is None:
        return redirect(url_for("login"))
    if _mode() != app_mode.HAJJ:              # خاصّ بالحج
        return redirect(url_for("reports"))
    from hajj_app.camps import CAMPS, MEN, WOMEN
    slug_of = {v: k for k, v in _CAMP_SLUGS.items()}
    camps = [{"slug": slug_of.get(name, name), "name": name} for name in CAMPS]
    saved = _load_camps()                          # الخيام المحفوظة (دائمة) لكل مخيّم
    saved_camps = []
    for c in camps:
        st = saved.get(c["slug"])
        tents = _tents_view(st) if isinstance(st, dict) else []
        if tents:
            saved_camps.append({"slug": c["slug"], "name": c["name"],
                                "tents": tents,
                                "assigned": len((st or {}).get("assigned", []))})
    return render_template("camps.html", active="camps", camps=camps,
                           classes=[("", "الكل"), (MEN, MEN), (WOMEN, WOMEN)],
                           count=len(_load_records()), saved_camps=saved_camps,
                           reset=request.args.get("reset"), **_ctx())


@app.post("/camps/reset")
def camps_reset():
    """إعادة تعيين تسكين المخيمات: يمسح كل الخيام المحفوظة لكل المخيمات."""
    if _sess() is None:
        return redirect(url_for("login"))
    if _mode() != app_mode.HAJJ:
        return redirect(url_for("reports"))
    _save_camps({})                                # يمسح التسكين الدائم لكل المخيمات
    _audit("إعادة تعيين تسكين المخيمات")
    return redirect(url_for("camps_page", reset=1))


@app.get("/camps/plan.pdf")
def camp_pdf():
    """يبني كشف تسكين المخيّم حسب الخيارات (تصنيف/قطاع/سعة) ويعيده معاينة PDF."""
    if _sess() is None:
        return redirect(url_for("login"))
    if _mode() != app_mode.HAJJ:
        return ("", 404)
    from hajj_app import camps as campmod
    from hajj_app.pdf_io import export_camp_pdf, export_tents_pdf, company_info
    camp = _CAMP_SLUGS.get(request.args.get("camp", ""))
    if camp is None or camp not in campmod.CAMPS:
        return redirect(url_for("camps_page"))
    records = _load_records()
    if not records:
        return redirect(url_for("camps_page"))
    try:
        capacity = int(request.args.get("capacity", "40") or 40)
    except ValueError:
        capacity = 40
    sector = (request.args.get("sector", "") or "").strip()
    only = request.args.get("only", "") or ""
    if only not in (campmod.MEN, campmod.WOMEN):
        only = ""
    layout = request.args.get("layout", "grouped")
    plan = campmod.build_camp_plan(records, camp, capacity=capacity,
                                   sector=sector, only=only)
    title = f"كشف تسكين مخيّم {camp}"
    if only:
        title += f" — {only}"
    if sector:
        title += f" — قطاع {sector}"
    if layout == "pertent":                        # كل خيمة في صفحة مستقلّة
        settings = storage.load_settings()
        co = settings.get("company") if isinstance(settings, dict) else None
        campaign = company_info(co)["name_ar"]
        return _pdf_response(
            lambda p: export_tents_pdf(plan, p, campaign=campaign, title=title),
            "camp-tents.pdf")
    return _pdf_response(lambda p: export_camp_pdf(plan, p, title=title),
                         "camp-plan.pdf")


@app.get("/camps/tents")
def camp_tents():
    """بناء «خيمة بخيمة» تفاعلي: معاينة ركّاب الخيمة التالية قبل تثبيتها."""
    if _sess() is None:
        return redirect(url_for("login"))
    if _mode() != app_mode.HAJJ:
        return redirect(url_for("reports"))
    from hajj_app import camps as campmod
    from hajj_app.rooming import room_number_in_type
    camp_slug = request.args.get("camp", "mina")
    camp = _CAMP_SLUGS.get(camp_slug)
    if camp is None:
        return redirect(url_for("camps_page"))
    records = _load_records()
    st = _camp_entry(_load_camps(), camp_slug)
    assigned = set(st["assigned"])
    cls = request.args.get("cls", campmod.MEN)
    if cls not in (campmod.MEN, campmod.WOMEN):
        cls = campmod.MEN
    count = request.args.get("count", "40")
    sector = request.args.get("sector", "")
    number = request.args.get("number", str(st["number"]))
    campaign = request.args.get("campaign", _DEFAULT_CAMPAIGN)
    preview = campmod.next_tent_indices(records, cls, count, assigned)
    rows = []
    for serial, i in enumerate(preview, start=1):
        rec = records[i]
        room = (str(getattr(rec, "room_number", "") or "").strip()
                or room_number_in_type(str(getattr(rec, "room_type", "") or "")))
        rows.append({"serial": serial,
                     "name": getattr(rec, "full_name_ar", "") or getattr(
                         rec, "full_name_en", "") or "—",
                     "fam": str(getattr(rec, "family_number", "") or "").strip(),
                     "hotel": str(getattr(rec, "hotel", "") or "").strip(),
                     "room": room})
    remaining = campmod.remaining_by_class(records, assigned)
    summary = {"in_tent": len(preview), "remaining": remaining.get(cls, 0),
               "assigned": len(assigned)}
    slug_of = {v: k for k, v in _CAMP_SLUGS.items()}
    camps = [{"slug": slug_of.get(n, n), "name": n} for n in campmod.CAMPS]
    return render_template(
        "camp_tents.html", active="camps", camp=camp, camp_slug=camp_slug,
        camps=camps, classes=[campmod.MEN, campmod.WOMEN], cls=cls, count=count,
        sector=sector, number=number, campaign=campaign, rows=rows,
        summary=summary, has_last=bool(st.get("last")),
        saved_tents=_tents_view(st),
        msg=request.args.get("msg", ""), **_ctx())


@app.post("/camps/tents/export")
def camp_tents_export():
    """يثبّت ركّاب الخيمة الحالية ويحفظ مواصفاتها (لتنزيل PDF)، ثم يعود للبناء."""
    if _sess() is None:
        return redirect(url_for("login"))
    if _mode() != app_mode.HAJJ:
        return ("", 404)
    from hajj_app import camps as campmod
    camp_slug = request.form.get("camp", "mina")
    camp = _CAMP_SLUGS.get(camp_slug)
    if camp is None:
        return redirect(url_for("camps_page"))
    records = _load_records()
    camps = _load_camps()
    st = _camp_entry(camps, camp_slug)
    assigned = set(st["assigned"])
    cls = request.form.get("cls", campmod.MEN)
    if cls not in (campmod.MEN, campmod.WOMEN):
        cls = campmod.MEN
    count = request.form.get("count", "40")
    sector = (request.form.get("sector", "") or "").strip()
    number = (request.form.get("number", "") or "1").strip() or "1"
    campaign = (request.form.get("campaign", "") or _DEFAULT_CAMPAIGN).strip()
    indices = campmod.next_tent_indices(records, cls, count, assigned)
    back = dict(camp=camp_slug, cls=cls, count=count, sector=sector,
                campaign=campaign)
    if not indices:
        return redirect(url_for("camp_tents", number=number,
                                msg=f"لا يوجد {cls} غير مسكّنين لهذه الخيمة.", **back))
    assigned |= set(indices)
    st["assigned"] = sorted(assigned)
    tent = {"indices": indices, "camp": camp, "sector": sector,
            "number": number, "cls": cls, "capacity": count,
            "campaign": campaign}
    st["last"] = tent
    st["tents"].append(tent)                        # حفظ دائم للخيمة
    try:
        nxt = str(int(number) + 1)
    except ValueError:
        nxt = number
    st["number"] = nxt
    _save_camps(camps)
    _audit("تثبيت خيمة (تلقائي)",
           f"{camp} — خيمة {number} — {cls} — {len(indices)} شخصاً")
    return redirect(url_for(
        "camp_tents", number=nxt,
        msg=f"تُثبّتت الخيمة {number} ({cls}): {len(indices)} شخصاً. "
            f"افتح كشفها من الزر أدناه.", **back))


@app.post("/camps/tents/reset")
def camp_tents_reset():
    """يمسح كل الخيام المثبّتة ويبدأ من جديد."""
    if _sess() is None:
        return redirect(url_for("login"))
    camp_slug = request.form.get("camp", "mina")
    camps = _load_camps()
    st = _camp_entry(camps, camp_slug)
    st["assigned"] = []
    st["number"] = 1
    st["last"] = None
    st["tents"] = []
    _save_camps(camps)
    _audit("إعادة ضبط بناء الخيام", _CAMP_SLUGS.get(camp_slug, camp_slug))
    return redirect(url_for("camp_tents", camp=camp_slug, msg="أُعيد الضبط."))


def _tents_view(st):
    """قائمة عرض الخيام المحفوظة (للمعاينة/التصدير لاحقاً)."""
    return [{"n": i, "number": t.get("number", ""), "cls": t.get("cls", ""),
             "count": len(t.get("indices", [])), "sector": t.get("sector", "")}
            for i, t in enumerate(st.get("tents") or [])]


def _tent_plan_from(records, spec):
    from hajj_app import camps as campmod
    return campmod.make_tent(
        records, spec["indices"], camp=spec["camp"], sector=spec["sector"],
        number=spec["number"], classification_label=spec["cls"],
        capacity=spec["capacity"])


@app.get("/camps/tents/tent/<int:n>.pdf")
def camp_tent_pdf(n):
    """يعيد توليد كشف خيمة محفوظة برقمها في القائمة (المعاينة/التصدير لاحقاً)."""
    if _sess() is None:
        return redirect(url_for("login"))
    if _mode() != app_mode.HAJJ:
        return ("", 404)
    from hajj_app.pdf_io import export_tents_pdf
    st = _load_camps().get(request.args.get("camp", "mina")) or {}
    tents = st.get("tents") or []
    if not (0 <= n < len(tents)):
        return redirect(url_for("camp_tents"))
    spec = tents[n]
    plan = _tent_plan_from(_load_records(), spec)
    return _pdf_response(
        lambda p: export_tents_pdf(plan, p, campaign=spec.get("campaign", "")),
        "tent.pdf")


@app.get("/camps/tents/all.pdf")
def camp_tents_all_pdf():
    """كشف كل الخيام المثبّتة — كل خيمة في صفحة مستقلّة."""
    if _sess() is None:
        return redirect(url_for("login"))
    if _mode() != app_mode.HAJJ:
        return ("", 404)
    from hajj_app.camps import CampPlan
    from hajj_app.pdf_io import export_tents_pdf
    st = _load_camps().get(request.args.get("camp", "mina")) or {}
    tents = st.get("tents") or []
    if not tents:
        return redirect(url_for("camp_tents"))
    records = _load_records()
    all_tents = []
    for spec in tents:
        all_tents.extend(_tent_plan_from(records, spec).tents)
    campaign = tents[0].get("campaign", "") or _DEFAULT_CAMPAIGN
    plan = CampPlan(camp=tents[0].get("camp", ""), sector="", capacity=0,
                    tents=all_tents, notes=[])
    return _pdf_response(
        lambda p: export_tents_pdf(plan, p, campaign=campaign),
        "camp-all-tents.pdf")


@app.get("/camps/tents/last.pdf")
def camp_tent_last_pdf():
    """يولّد PDF لآخر خيمة مثبّتة."""
    if _sess() is None:
        return redirect(url_for("login"))
    if _mode() != app_mode.HAJJ:
        return ("", 404)
    from hajj_app import camps as campmod
    from hajj_app.pdf_io import export_tents_pdf
    st = _load_camps().get(request.args.get("camp", "mina")) or {}
    last = st.get("last")
    if not last:
        return redirect(url_for("camp_tents"))
    records = _load_records()
    plan = campmod.make_tent(
        records, last["indices"], camp=last["camp"], sector=last["sector"],
        number=last["number"], classification_label=last["cls"],
        capacity=last["capacity"])
    return _pdf_response(
        lambda p: export_tents_pdf(plan, p, campaign=last["campaign"]),
        "tent.pdf")


@app.get("/camps/tents/manual")
def camp_tents_manual():
    """تسكين يدوي: اختيار الحجّاج بالمربّعات لكل خيمة من قائمة غير المسكّنين."""
    if _sess() is None:
        return redirect(url_for("login"))
    if _mode() != app_mode.HAJJ:
        return redirect(url_for("reports"))
    from hajj_app.rooming import room_number_in_type
    camp_slug = request.args.get("camp", "mina")
    camp = _CAMP_SLUGS.get(camp_slug)
    if camp is None:
        return redirect(url_for("camps_page"))
    records = _load_records()
    st = _camp_entry(_load_camps(), camp_slug)
    assigned = set(st["assigned"])
    rows = []
    for i, rec in enumerate(records):
        if i in assigned:
            continue
        room = (str(getattr(rec, "room_number", "") or "").strip()
                or room_number_in_type(str(getattr(rec, "room_type", "") or "")))
        rows.append({"idx": i, "fp": _rec_token(rec),
                     "name": getattr(rec, "full_name_ar", "") or getattr(
                         rec, "full_name_en", "") or "—",
                     "fam": str(getattr(rec, "family_number", "") or "").strip(),
                     "hotel": str(getattr(rec, "hotel", "") or "").strip(),
                     "room": room, "sex": str(getattr(rec, "sex", "") or "").strip()})
    slug_of = {v: k for k, v in _CAMP_SLUGS.items()}
    from hajj_app.camps import CAMPS
    camps = [{"slug": slug_of.get(n, n), "name": n} for n in CAMPS]
    return render_template(
        "camp_tents_manual.html", active="camps", camp=camp, camp_slug=camp_slug,
        camps=camps, rows=rows, number=str(st["number"]),
        campaign=_DEFAULT_CAMPAIGN, assigned=len(assigned),
        has_last=bool(st.get("last")), saved_tents=_tents_view(st),
        msg=request.args.get("msg", ""), **_ctx())


@app.post("/camps/tents/manual/assign")
def camp_tents_manual_assign():
    """يثبّت خيمة من الحجّاج المختارين يدوياً ويحفظ مواصفاتها لتنزيل الكشف."""
    if _sess() is None:
        return redirect(url_for("login"))
    if _mode() != app_mode.HAJJ:
        return ("", 404)
    from hajj_app import camps as campmod
    camp_slug = request.form.get("camp", "mina")
    camp = _CAMP_SLUGS.get(camp_slug)
    if camp is None:
        return redirect(url_for("camps_page"))
    records = _load_records()
    camps = _load_camps()
    st = _camp_entry(camps, camp_slug)
    assigned = set(st["assigned"])
    number = (request.form.get("number", "") or "1").strip() or "1"
    sector = (request.form.get("sector", "") or "").strip()
    label = (request.form.get("label", "") or "مختار").strip() or "مختار"
    campaign = (request.form.get("campaign", "") or _DEFAULT_CAMPAIGN).strip()
    picks, skipped = [], 0
    for v in request.form.getlist("pick"):
        try:
            i = int(v)
        except ValueError:
            continue
        j = _resolve_idx(records, i, request.form.get(f"fp_{i}", ""))
        if j is None:                              # حُذف/عُدّل منذ فتح الصفحة
            skipped += 1
        elif j not in assigned and j not in picks:
            picks.append(j)
    if not picks:
        return redirect(url_for("camp_tents_manual", camp=camp_slug,
                                msg=("تغيّر الكشف منذ فتح الصفحة — أعد التحديد."
                                     if skipped else "لم تختر أي حاجّ لهذه الخيمة.")))
    assigned |= set(picks)
    st["assigned"] = sorted(assigned)
    tent = {"indices": picks, "camp": camp, "sector": sector,
            "number": number, "cls": label, "capacity": len(picks),
            "campaign": campaign}
    st["last"] = tent
    st["tents"].append(tent)                        # حفظ الخيمة للمعاينة لاحقاً
    try:
        st["number"] = str(int(number) + 1)
    except ValueError:
        st["number"] = number
    _save_camps(camps)
    _audit("تسكين خيمة يدوياً", f"{camp} — خيمة {number} — {len(picks)} شخصاً")
    return redirect(url_for(
        "camp_tents_manual", camp=camp_slug,
        msg=(f"ثُبّتت الخيمة {number}: {len(picks)} شخصاً. افتح كشفها من الزر أدناه."
             + (f" (تُخطّي {skipped} تغيّر سجلّه منذ فتح الصفحة)" if skipped else ""))))


# ==================== المصروفات والمحاسبة ==================================
_EXPENSE_CATS = ("فنادق", "نقل", "إعاشة", "تصاريح", "رواتب", "طيران", "أخرى")


@app.route("/expenses", methods=["GET", "POST"])
def expenses_page():
    """مصروفات الحملة: صافي = المحصّل − المصروفات (للمحرّرين إضافة/حذف)."""
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app.fields import format_amount, parse_amount
    settings = storage.load_settings()
    items = list(settings.get("expenses", []) or [])
    if request.method == "POST" and _sess().can_edit:
        action = request.form.get("action", "")
        if action == "add":
            items.append({
                "date": (request.form.get("date", "") or "").strip(),
                "supplier": (request.form.get("supplier", "") or "").strip(),
                "category": (request.form.get("category", "") or "").strip(),
                "amount": (request.form.get("amount", "") or "").strip(),
                "note": (request.form.get("note", "") or "").strip()})
        elif action == "del":
            try:
                items.pop(int(request.form.get("idx", "-1")))
            except (ValueError, IndexError):
                pass
        settings["expenses"] = items
        try:
            storage.save_settings(settings)
            if action == "add":
                _audit("إضافة مصروف", (request.form.get("category", "") or "")
                       + " — " + (request.form.get("amount", "") or ""))
            elif action == "del":
                _audit("حذف مصروف")
        except Exception:
            pass
        return redirect(url_for("expenses_page"))
    records = _load_records()
    collected = sum(parse_amount(getattr(r, "paid_amount", "")) or 0.0
                    for r in records)
    total_exp = sum(parse_amount(e.get("amount")) or 0.0 for e in items)
    rows = [{"idx": i, "date": e.get("date", ""), "supplier": e.get("supplier", ""),
             "category": e.get("category", ""),
             "amount": format_amount(parse_amount(e.get("amount")) or 0.0) or "0",
             "note": e.get("note", "")} for i, e in enumerate(items)]
    totals = {"collected": format_amount(collected) or "0",
              "expenses": format_amount(total_exp) or "0",
              "net": format_amount(collected - total_exp) or "0"}
    from datetime import date as _date
    return render_template("expenses.html", active="expenses", rows=rows,
                           totals=totals, cats=_EXPENSE_CATS,
                           today=_date.today().isoformat(), **_ctx())


# ============================ المالية والتحصيل =============================
@app.get("/finance")
def finance():
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app.fields import parse_amount
    records = _load_records()
    fin = stats.financial_summary(records)
    cards = [
        {"icon": "💰", "label": "إجمالي القيمة",
         "value": format_amount(fin.total) or "0", "sub": "", "color": "#8A6E4B"},
        {"icon": "✅", "label": "المحصّل", "value": format_amount(fin.paid) or "0",
         "sub": f"{fin.collected_percent}% من الإجمالي", "color": "#2E7D5B"},
        {"icon": "⏳", "label": "المتبقّي",
         "value": format_amount(fin.remaining) or "0", "sub": "AED",
         "color": "#2C5AA0"},
        {"icon": "⚠", "label": "المتأخّرون عن السداد",
         "value": f"{fin.unpaid_count:,}", "sub": "بحاجة متابعة",
         "color": "#C0392B"},
    ]
    progs = [{"name": name, "count": pf.count,
              "paid": format_amount(pf.paid) or "0",
              "remaining": format_amount(pf.remaining) or "0",
              "pct": pf.collected_percent}
             for name, pf in _by_group(records)]
    idx_of = {id(r): i for i, r in enumerate(records)}
    arrears = []
    for r, amt in stats.outstanding(records):
        arrears.append({
            "idx": idx_of[id(r)], "fp": _rec_token(r),
            "name": getattr(r, "full_name_ar", "") or getattr(
                r, "full_name_en", "") or "—",
            "program": str(getattr(r, _group_attr(), "") or "") or "—",
            "phone": getattr(r, "phone", "") or "—",
            "total": format_amount(parse_amount(r.program_value) or 0) or "0",
            "paid": format_amount(parse_amount(r.paid_amount) or 0) or "0",
            "remaining": format_amount(amt) or "0"})
    return render_template("finance.html", active="finance", cards=cards,
                           progs=progs, arrears=arrears, **_ctx())


@app.post("/finance/<int:idx>/pay")
def finance_pay(idx):
    if _sess() is None:
        return redirect(url_for("login"))
    if not _sess().can_edit:
        return redirect(url_for("finance"))
    from datetime import date as _date
    from hajj_app.fields import parse_amount, format_amount as _fmt, sync_paid_amount
    records = _load_records()
    j = _resolve_idx(records, idx, request.form.get("fp", ""))
    if j is None:                                  # تغيّر الكشف منذ فتح الصفحة
        return redirect(url_for("finance", msg="stale"))
    idx = j
    if 0 <= idx < len(records):
        amt = parse_amount(request.form.get("amount"))
        if amt and amt > 0:
            rec = records[idx]
            pays = list(getattr(rec, "payments", None) or [])
            # مبلغ مدفوع سابق أُدخل مباشرةً بلا سجلّ دفعات: نُدرجه كرصيد افتتاحي
            # حتى لا يُلغيه sync_paid_amount عند إعادة الحساب من مجموع الدفعات.
            if not pays:
                prev = parse_amount(getattr(rec, "paid_amount", "")) or 0
                if prev > 0:
                    pays.append({"amount": _fmt(prev), "date": "",
                                 "method": "رصيد سابق"})
            pays.append({"amount": _fmt(amt), "date": _date.today().isoformat(),
                         "method": (request.form.get("method") or "").strip()
                         or "تحويل"})
            rec.payments = pays
            sync_paid_amount(rec)
            try:
                storage.save_records(records, session=_sess())
                _nm = getattr(rec, "full_name_ar", "") or getattr(
                    rec, "full_name_en", "") or getattr(rec, "passport_number", "")
                _audit("تسجيل دفعة", f"{_nm} — {_fmt(amt)}")
            except Exception:
                pass
    return redirect(url_for("finance"))

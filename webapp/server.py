"""خادم Flask لتطبيق الويب — المرحلة الأولى: تسجيل الدخول + لوحة التحكم.

يعيد استخدام منطق ``hajj_app`` كما هو (المصادقة، التخزين، الإحصاءات). الجلسات
تُحفظ في الذاكرة على الخادم (كافٍ للتطوير؛ للنشر السحابي يُضاف تخزين جلسات آمن
وHTTPS)."""

from __future__ import annotations

import hashlib
import html as _html
import io
import os
import secrets
import re
import tempfile
import threading
import hmac
import time

from flask import (Flask, g, redirect, render_template, request, send_file,
                   session, url_for)
from werkzeug.middleware.proxy_fix import ProxyFix

from hajj_app import app_mode, auth, stats, storage
from hajj_app.fields import BY_KEY, format_amount
from hajj_app.stats import remaining_amount

_PAGE = 50
_STATUS_CLS = {"نشط": "good", "ملغى": "crit", "قائمة انتظار": "warn"}
_CHOICES = {"status": ["", "نشط", "ملغى", "قائمة انتظار"],
            "sex": ["", "ذكر", "أنثى"], "wheelchair": ["", "نعم"],
            "blood_type": ["", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]}
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
               "departure_time", "hotel", "permit_status", "masar_number"}
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
    ("التأشيرة والتصاريح", ["visa_number", "visa_status", "permit_status",
                            "masar_number", "vaccination", "insurance"]),
    ("المالية", ["program_value", "paid_amount"]),
    ("الصحة والطوارئ", ["blood_type", "medical_conditions", "medications",
                        "emergency_name", "emergency_phone", "emergency_relation"]),
    ("ملاحظات", ["notes", "staff"]),
]
# أيقونة كل قسم في صفحة السجلّ (حسب بداية العنوان)
_GROUP_ICONS = (("البرنامج", "briefcase"), ("بيانات", "user"), ("الجواز", "id-card"),
                ("السفر", "plane"), ("الإقامة", "hotel"), ("التأشيرة", "shield"),
                ("المالية", "wallet"), ("الصحة", "heart"), ("ملاحظات", "pen"))

app = Flask(__name__)
from webapp import icons as _icons  # noqa: E402
_icons.install(app)                     # ic('…') و|iconize في القوالب
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
from datetime import datetime, timezone, timedelta  # noqa: E402  (لوحة التحكم)
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
    """جلسة hajj_app لهذا المتصفّح؛ بعد إعادة تشغيل الخادم تُستعاد من القرص."""
    sid = session.get("sid")
    if not sid:
        return None
    hs = _SESSIONS.get(sid)
    if hs is None and session.get("sk") and not g.get("_sess_miss"):
        from webapp import websessions
        try:
            hs = websessions.restore(sid, session["sk"])
        except Exception:                          # noqa: BLE001
            hs = None
        if hs is None:
            g._sess_miss = True
        else:
            _SESSIONS[sid] = hs
    return hs


def _persist(sid: str, hs) -> None:
    """يحفظ الجلسة (مشفّرة بمفتاح في متصفّح صاحبها) لتبقى بعد إعادة التشغيل."""
    _LAST_SEEN[sid] = time.time()
    try:
        from webapp import websessions
        session["sk"] = websessions.save(sid, hs, ip=_client_ip(),
                                         ua=request.headers.get("User-Agent", ""))
    except Exception:                              # noqa: BLE001
        pass


def _end(sid) -> None:
    """ينهي جلسة (من الذاكرة والقرص)."""
    if not sid:
        return
    _SESSIONS.pop(sid, None)
    _LAST_SEEN.pop(sid, None)
    try:
        from webapp import websessions
        websessions.drop(sid)
    except Exception:                              # noqa: BLE001
        pass


def _end_user(username: str) -> None:
    """ينهي كل جلسات مستخدم (تغيير كلمة مروره أو حذف حسابه)."""
    for sid in [k for k, v in _SESSIONS.items()
                if getattr(v, "username", "").lower() == (username or "").lower()]:
        _end(sid)
    try:
        from webapp import websessions
        websessions.drop_user(username)
    except Exception:                              # noqa: BLE001
        pass


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
                _pw_mark(username)
                sid = secrets.token_hex(16)
                _SESSIONS[sid] = sess
                session["sid"] = sid
                _persist(sid, sess)
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
_EMAIL_SETUP: dict = {}            # رمز تفعيل «الرمز على الإيميل» لكل جلسة
_FORGOT: dict = {}                 # عنوان → أوقات طلبات «نسيت كلمة المرور»
_MAIL_CODE_TTL = 10 * 60
_MAIL_RESEND = 60                  # ثوانٍ بين رسالتين
_MAIL_MAX_SENDS = 5


def _mail_2fa(username: str) -> bool:
    """رمز الدخول على الإيميل متاح لهذا الحساب الآن؟"""
    from webapp import mailer
    return mailer.configured() and auth.has_email_2fa(username)


def _mask_email(email: str) -> str:
    name, _, dom = (email or "").partition("@")
    return (name[:2] + "•••@" + dom) if dom else ""


def _code_hash(code: str) -> str:
    return hashlib.sha256(("mailcode:" + code).encode("utf-8")).hexdigest()


def _mail_code(state: dict, email: str, title: str, purpose: str) -> tuple[str, str]:
    """يرسل رمزاً من ٦ أرقام ويحفظ بصمته في state. يعيد (خطأ، رسالة)."""
    from webapp import mailer
    now = time.time()
    if now - state.get("elast", 0) < _MAIL_RESEND:
        return (f"انتظر {int(_MAIL_RESEND - (now - state['elast'])) + 1} ثانية "
                "قبل طلب رمز جديد.", "")
    if state.get("esent", 0) >= _MAIL_MAX_SENDS:
        return "طلبت رموزاً كثيرة — أعد المحاولة لاحقاً.", ""
    code = f"{secrets.randbelow(10 ** 6):06d}"
    ok, why = mailer.send(email, f"{title}: {code}", mailer.wrap(title, (
        f"<p>{_html.escape(purpose)}</p><p style=\"font-size:30px;letter-spacing:8px;font-weight:bold;"
        f"text-align:center;direction:ltr\">{code}</p>"
        "<p>الرمز صالح ١٠ دقائق. إن لم تطلبه أنت فتجاهل الرسالة وغيّر كلمة مرورك.</p>")))
    if not ok:
        return "تعذّر إرسال الرمز — " + why, ""
    state.update(ecode=_code_hash(code), eexp=now + _MAIL_CODE_TTL, etries=0,
                 esent=state.get("esent", 0) + 1, elast=now, eto=_mask_email(email))
    return "", f"📧 أرسلنا رمزاً إلى {state['eto']} — صالح ١٠ دقائق."


def _check_mail_code(state: dict, code) -> bool:
    from hajj_app import totp
    if not state.get("ecode") or state.get("eexp", 0) < time.time():
        return False
    if hmac.compare_digest(_code_hash(totp.clean_code(code)), state["ecode"]):
        state.pop("ecode", None)                   # لمرة واحدة
        return True
    state["etries"] = state.get("etries", 0) + 1
    if state["etries"] >= 5:                       # ٥ أخطاء: يُلغى الرمز
        state.pop("ecode", None)
    return False


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
    _persist(sid, hs)
    session["mode"] = mode
    session["username"] = hs.username or username
    session["role"] = getattr(hs, "role_label", "")
    _csrf_token()               # (لا يُبدَّل: تبقى الصفحات المفتوحة صالحة للحفظ)
    session.permanent = bool(remember)                 # تذكّرني
    _FAILS.pop(("user", _ukey(username)), None)
    _note_device(hs.username or username)
    try:
        from webapp import pwpolicy
        pwpolicy.changed_at(hs.username or username)   # حساب بلا تاريخ: يبدأ العدّ الآن
    except Exception:                              # noqa: BLE001
        pass
    try:
        from hajj_app import audit
        audit.record("دخول", f"من {_client_ip()}", user=hs.username or username)
    except Exception:                              # noqa: BLE001
        pass


def _pw_mark(username: str) -> None:
    try:
        from webapp import pwpolicy
        pwpolicy.mark(username)
    except Exception:                              # noqa: BLE001
        pass


def _note_device(username: str) -> None:
    """يسجّل جهاز الدخول؛ جهاز جديد لحساب له أجهزة سابقة = تنبيه لصاحبه بالبريد."""
    from webapp import devices, websessions
    try:
        tok = request.cookies.get(devices.COOKIE)
        if not devices.valid_token(tok):
            tok = secrets.token_urlsafe(24)
            g.dev_cookie = tok
        label = websessions.device(request.headers.get("User-Agent", ""))
        new, had_any = devices.remember(username, tok, label)
        if not (new and had_any):
            return
        ip, when = _client_ip(), time.strftime("%Y-%m-%d %H:%M")
        try:
            from hajj_app import audit
            audit.record("دخول من جهاز جديد", f"{label} — من {ip}", user=username)
        except Exception:                          # noqa: BLE001
            pass
        email = auth.get_email(username)
        mailer = _mailer()
        if not email or not mailer.configured():
            return
        body = mailer.wrap("دخول جديد إلى حسابك", (
            f"<p>دخل أحد إلى حسابك «{_html.escape(username)}» من جهاز لم يُستعمل من قبل:</p>"
            f"<p><b>الجهاز:</b> {_html.escape(label)}<br><b>العنوان:</b> <span dir=\"ltr\">{_html.escape(ip)}</span>"
            f"<br><b>الوقت:</b> <span dir=\"ltr\">{when}</span></p>"
            "<p>إن كنت أنت فتجاهل الرسالة. وإن لم تكن أنت: غيّر كلمة مرورك فوراً وأبلغ المدير "
            "(يستطيع إنهاء الجلسة من «الجلسات النشطة»).</p>"))
        threading.Thread(target=mailer.send, args=(email, "تنبيه: دخول من جهاز جديد", body),
                         daemon=True).start()
    except Exception:                              # noqa: BLE001
        pass


@app.after_request
def _device_cookie(resp):
    tok = g.get("dev_cookie")
    if tok:
        resp.set_cookie("alm_dev", tok, max_age=400 * 86400, httponly=True, samesite="Lax",
                        secure=bool(app.config.get("SESSION_COOKIE_SECURE")))
    return resp


@app.get("/healthz")
def healthz():
    """فحص عمل الموقع (لخدمات المراقبة): يتأكّد أن مجلّد البيانات مقروء."""
    try:
        from hajj_app.paths import data_dir
        ok = os.path.isdir(data_dir()) and os.access(data_dir(), os.R_OK | os.W_OK)
    except Exception:                              # noqa: BLE001
        ok = False
    return ({"status": "ok"} if ok else {"status": "error"}), (200 if ok else 503)


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
            elif auth.has_totp(hs.username) or _mail_2fa(hs.username):
                now = time.time()                  # الخطوة الثانية: رمز الجوال/الإيميل
                for k in [k for k, v in _PENDING.items() if v["exp"] < now]:
                    _PENDING.pop(k, None)
                pid = secrets.token_hex(16)
                _PENDING[pid] = p = {"hs": hs, "user": username, "mode": mode,
                                     "remember": remember, "exp": now + 300}
                if not auth.has_totp(hs.username):   # الإيميل وحده: يُرسل فوراً
                    p["exp"] = now + _MAIL_CODE_TTL
                    p["err"], p["info"] = _mail_code(
                        p, auth.get_email(hs.username), "رمز الدخول",
                        f"رمز الدخول إلى بورتال المصطفى لحساب «{hs.username}»:")
                session["p2fa"] = pid
                return redirect(url_for("login_2fa"))
            else:
                _finish_login(hs, username, mode, remember)
                return redirect(url_for("dashboard"))
    return render_template("login.html", error=error, modes=_MODE_CHOICES,
                           selected_mode=mode)


@app.route("/login/2fa", methods=["GET", "POST"])
def login_2fa():
    """الخطوة الثانية: رمز من تطبيق المصادقة أو رمز يصل إلى إيميل العمل."""
    from hajj_app import totp
    pid = session.get("p2fa")
    p = _PENDING.get(pid) if pid else None
    if not p or p["exp"] < time.time():
        _PENDING.pop(pid, None)
        session.pop("p2fa", None)
        return redirect(url_for("login"))
    hs = p["hs"]
    use_app, use_mail = auth.has_totp(hs.username), _mail_2fa(hs.username)
    if not (use_app or use_mail):                  # أُلغي أثناء الانتظار أو حُذف
        _PENDING.pop(pid, None)
        session.pop("p2fa", None)
        return redirect(url_for("login"))             # يُعاد الدخول بكلمة المرور
    error, info = p.pop("err", ""), p.pop("info", "")
    if request.method == "POST":
        wait = _lock_wait(p["user"])
        if wait:
            error = _lock_msg(wait)
        elif request.form.get("action") == "email":
            if use_mail:
                p["exp"] = max(p["exp"], time.time() + _MAIL_CODE_TTL)
                error, info = _mail_code(
                    p, auth.get_email(hs.username), "رمز الدخول",
                    f"رمز الدخول إلى بورتال المصطفى لحساب «{hs.username}»:")
        else:
            ukey = hs.username.lower()
            code = request.form.get("code")
            ok = False
            if use_app:
                step = totp.verify(auth.get_totp(hs) or "", code,
                                   last_step=_TOTP_LAST.get(ukey))
                if step is not None:
                    _TOTP_LAST[ukey], ok = step, True
            if not ok and use_mail:
                ok = _check_mail_code(p, code)
            if ok:
                _PENDING.pop(pid, None)
                session.pop("p2fa", None)
                _finish_login(hs, p["user"], p["mode"], p["remember"])
                return redirect(url_for("dashboard"))
            _note_fail(p["user"], "رمز دخول بخطوتين خاطئ")
            error = ("الرمز غير صحيح أو انتهت مدّته — اكتب الرمز الظاهر الآن في التطبيق"
                     + (" أو الرمز الذي وصلك على الإيميل." if use_mail and p.get("eto")
                        else "."))
    return render_template("login_2fa.html", error=error, info=info,
                           use_app=use_app, use_mail=use_mail, sent_to=p.get("eto"),
                           selected_mode=p["mode"], username=hs.username)


@app.route("/forgot", methods=["GET", "POST"])
def forgot():
    """نسيت كلمة المرور: طلب يصل المدير، وبعد موافقته رابط لإيميل صاحب الحساب."""
    from webapp import mailer, resets
    if not auth.is_configured():
        return redirect(url_for("setup"))
    done = error = ""
    if request.method == "POST":
        ip, now = _client_ip(), time.time()
        times = [t for t in _FORGOT.get(ip, []) if now - t < 3600]
        if len(times) >= 5:
            error = "طلبات كثيرة من هذا الجهاز — حاول بعد ساعة."
        else:
            _FORGOT[ip] = times + [now]
            if len(_FORGOT) > 2000:
                _FORGOT.clear()
            who = (request.form.get("who") or "").strip()[:254]
            uname = (auth.find_by_email(who) if "@" in who else
                     next((a["username"] for a in auth.list_accounts()
                           if a["username"].lower() == who.lower()), None))
            email = auth.get_email(uname) if uname else ""
            if uname and email and mailer.configured():
                rid, new = resets.add(uname, ip)
                if new:
                    _audit_as(uname, "طلب استعادة كلمة المرور", f"من {ip}")
                    hu = _html.escape(uname)
                    for a in auth.list_accounts():
                        if (a["role"] == "admin" and a.get("email")
                                and a["username"].lower() != uname.lower()):
                            mailer.send(a["email"], f"طلب استعادة كلمة مرور: {uname}",
                                        mailer.wrap("طلب استعادة كلمة مرور", (
                                f"<p>طلب «<b>{hu}</b>» استعادة كلمة المرور من البورتال.</p>"
                                "<p>إن كان الطلب صحيحاً فادخل إلى البورتال ← «إدارة الحسابات» "
                                "واضغط <b>موافقة</b>، فيصله رابط على إيميله لوضع كلمة مرور "
                                "جديدة.</p>")))
                    mailer.send(email, "استلمنا طلب استعادة كلمة المرور", mailer.wrap(
                        "استلمنا طلبك", (
                            f"<p>وصل طلب استعادة كلمة المرور لحسابك «{hu}». سيراجعه "
                            "المدير، وبعد موافقته يصلك رابط هنا لوضع كلمة مرور جديدة.</p>"
                            "<p>إن لم تطلب ذلك فأبلغ المدير.</p>")))
            done = ("إن كان الحساب موجوداً وله إيميل عمل، فقد وصل طلبك إلى المدير. "
                    "بعد موافقته يصلك رابط على إيميلك لوضع كلمة مرور جديدة.")
    return render_template("forgot.html", done=done, error=error,
                           selected_mode=app_mode.UMRAH)


@app.route("/reset/<token>", methods=["GET", "POST"])
def reset_password(token):
    """رابط لمرة واحدة (بعد موافقة المدير) لوضع كلمة مرور جديدة."""
    from webapp import mailer, resets
    rid, r = resets.by_token(token)
    error = ""
    if r is None:
        if request.method == "POST":
            _note_fail("", "رابط استعادة غير صالح")
        return render_template("reset.html", invalid=True, error="",
                               selected_mode=app_mode.UMRAH), 404
    wait = _lock_wait(r["user"]) if request.method == "POST" else 0
    if wait:
        error = _lock_msg(wait)
    elif request.method == "POST":
        pw = request.form.get("password") or ""
        if pw != (request.form.get("confirm") or ""):
            error = "كلمتا المرور غير متطابقتين."
        else:
            try:
                auth.set_password_by_token(r["user"], token, r["wrapped"], pw)
                _pw_mark(r["user"])
            except Exception as exc:               # noqa: BLE001
                error = str(exc)
            else:
                resets.remove(rid)
                _FAILS.pop(("user", _ukey(r["user"])), None)
                _end_user(r["user"])                       # خروج جلساته القديمة
                _audit_as(r["user"], "تعيين كلمة مرور برابط الإيميل", f"من {_client_ip()}")
                email = auth.get_email(r["user"])
                if email:
                    mailer.send(email, "تغيّرت كلمة مرورك", mailer.wrap(
                        "تغيّرت كلمة مرورك", (
                            f"<p>وُضعت كلمة مرور جديدة لحسابك «{_html.escape(r['user'])}» الآن.</p>"
                            "<p>إن لم تفعل ذلك أنت فأبلغ المدير فوراً.</p>")))
                return redirect(url_for("login", reset=1))
    return render_template("reset.html", invalid=False, error=error,
                           username=r["user"], selected_mode=app_mode.UMRAH)


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
                _pw_mark(hs.username)
                sid = secrets.token_hex(16)
                _SESSIONS[sid] = hs
                session["sid"] = sid
                _persist(sid, hs)
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
    _end(session.get("sid"))
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
    season_rings = _season_rings(records, fin)
    seats = next((r for r in season_rings if r["key"] == "seats"), None)
    late = round(len(owe) * 100 / fin.count) if fin.count else 0
    kpis = [
        {"icon": "👤", "label": _noun(), "value": f"{fin.count:,}",
         "sub": seats["detail"] if seats else "", "color": "#8A6E4B",
         "pct": seats["pct"] if seats else None},
        {"icon": "💰", "label": "المحصّل", "value": format_amount(fin.paid) or "0",
         "sub": f"{fin.collected_percent}% من الإجمالي", "color": "#2E7D5B",
         "pct": fin.collected_percent, "ring": _icons.status_color(fin.collected_percent)},
        {"icon": "⏳", "label": "المتبقّي",
         "value": format_amount(fin.remaining) or "0", "sub": "AED",
         "color": "#2C5AA0", "pct": 100 - fin.collected_percent if fin.total else 0,
         "ring": _icons.status_color(fin.collected_percent)},
        {"icon": "⚠", "label": "المتأخّرون عن السداد", "value": f"{len(owe):,}",
         "sub": "بحاجة متابعة", "color": "#C0392B",
         "pct": late, "ring": _icons.status_color(100 - late)},
    ]
    progs = [{"name": name, "count": pf.count,
              "paid": format_amount(pf.paid) or "0",
              "remaining": format_amount(pf.remaining) or "0",
              "pct": pf.collected_percent}
             for name, pf in _by_group(records)]
    settings = storage.load_settings()
    pcards = (_package_cards(records, settings)
              if _mode() == app_mode.UMRAH else [])
    all_alerts = _alerts()
    alerts_top = [dict(a, link=_alert_link(a)) for a in all_alerts[:6]]
    now = datetime.now(_UAE)
    today = now.date()
    trips = _upcoming_trips(records, settings, today)
    s = _sess()
    return render_template(
        "dashboard.html", kpis=kpis, progs=progs, pcards=pcards,
        season_rings=season_rings, alerts_top=alerts_top, active="dashboard",
        greeting="صباح الخير" if 4 <= now.hour < 12 else "مساء الخير",
        today_txt=f"{_AR_DAYS[now.weekday()]} {now.day} {_AR_MONTHS[now.month - 1]} {now.year}",
        brief=_dash_brief(fin, trips, all_alerts), trips=trips,
        chart=_collection_chart(records, fin, today),
        activity=_recent_activity() if s is not None and s.is_admin else [],
        **_ctx())


_AR_MONTHS = ("يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو",
              "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر")
_AR_DAYS = ("الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد")
_UAE = timezone(timedelta(hours=4))            # توقيت الإمارات (بلا توقيت صيفي)


def _days_unit(n: int) -> str:
    return "يوم" if n == 1 else "يومان" if n == 2 else "أيام" if 3 <= n <= 10 else "يوماً"


def _day_txt(d, today) -> str:
    s = f"{d.day} {_AR_MONTHS[d.month - 1]}"
    return s if d.year == today.year else f"{s} {d.year}"


def _trip_list(records, settings) -> list:
    """رحلات الموسم (برامج العمرة أو برامج الحج) بلونها وتاريخَي المغادرة والعودة —
    يستعملها تقويم الرحلات ولوحة التحكم."""
    from webapp.alerts import _d
    out = []
    if _mode() == app_mode.UMRAH:
        from hajj_app import umrah
        trips = umrah.load_trips(settings)
        rows = [{"code": t.code, "package": str(t.package or "").strip()} for t in trips]
        _color_rows(rows, trips, _pkg_orders(settings))
        col = {r["code"]: r for r in rows}
        for t in trips:
            c = col.get(t.code, {})
            try:
                cap = int(float(str(t.capacity or "").strip() or 0))
            except ValueError:
                cap = 0
            out.append({"label": f"{t.code} {t.name or ''}".strip(),
                        "n": len(umrah.trip_pilgrims(records, t.code)), "cap": cap,
                        "color": c.get("color", "#1F5FAD"), "fg": c.get("fg", "#fff"),
                        "link": url_for("program_edit", code=t.code),
                        "sub": " · ".join(x for x in (t.airline, t.package) if x),
                        "depart": _d(t.depart_date), "ret": _d(t.return_date)})
    else:
        from hajj_app import programs as hp
        for i, (nm, pr) in enumerate(zip(hp.PROGRAM_NAMES, hp.load_programs(settings))):
            band, _t, fg, _i = _PROG_COLORS[i % len(_PROG_COLORS)]
            out.append({"label": nm, "n": sum(1 for r in records if (r.program or "") == nm),
                        "cap": 0, "color": band, "fg": fg, "link": url_for("travel_list"),
                        "sub": pr.carrier, "depart": _d(pr.travel_date),
                        "ret": _d(pr.return_date)})
    return out


def _upcoming_trips(records, settings, today, limit: int = 5) -> list:
    """الرحلات الجارية الآن ثم القادمة بالأقرب، مع العدّ التنازلي بالأيام."""
    out = []
    for t in _trip_list(records, settings):
        dep, ret = t["depart"], t["ret"]
        if not dep:
            continue
        if dep > today:
            state, days, pct, when = "soon", (dep - today).days, 0, dep
        elif dep == today:
            state, days, pct, when = "today", 0, 0, dep
        elif ret and dep < today <= ret:
            span = max(1, (ret - dep).days)
            state, days, when = "now", (ret - today).days, ret
            pct = min(100, round((today - dep).days * 100 / span))
        else:
            continue
        out.append(dict(t, state=state, days=days, pct=pct, unit=_days_unit(days),
                        when=when, depart_txt=_day_txt(dep, today),
                        ret_txt=_day_txt(ret, today) if ret else ""))
    rank = {"now": 0, "today": 1, "soon": 2}
    out.sort(key=lambda x: (rank[x["state"]], x["when"]))
    return out[:limit]


def _nice_step(x: float) -> float:
    import math
    if x <= 0:
        return 1.0
    mag = 10 ** math.floor(math.log10(x))
    for m in (1, 2, 2.5, 5, 10):
        if m * mag >= x:
            return m * mag
    return 10 * mag


def _collection_chart(records, fin, today, months: int = 12) -> dict:
    """التحصيل شهراً بشهر من الدفعات المسجّلة بتواريخها (آخر ١٢ شهراً، ٦ على الأقل)،
    مع هندسة الأعمدة جاهزة للرسم: الأقدم يميناً والأحدث يساراً."""
    import math
    from webapp.alerts import _d
    by: dict = {}
    dated = with_date = 0.0                # المرسوم / كل ما له تاريخ (ومنه المؤجَّل)
    for r in records:
        for p in getattr(r, "payments", None) or []:
            if not isinstance(p, dict):
                continue
            d, a = _d(p.get("date")), stats._amount(p.get("amount"))
            if not d or a <= 0:
                continue
            with_date += a
            if d > today:                  # شيك مؤجَّل أو تاريخ مستقبلي: لا يُرسم
                continue
            v = by.setdefault((d.year, d.month), [0.0, 0])
            v[0] += a
            v[1] += 1
            dated += a
    undated = max(0.0, float(fin.paid or 0) - with_date)
    if not by:
        return {"bars": [], "undated": format_amount(undated) if undated >= 1 else ""}

    def shift(ym, n):
        i = ym[0] * 12 + ym[1] - 1 - n
        return (i // 12, i % 12 + 1)

    end = (today.year, today.month)
    start = min(max(min(by), shift(end, months - 1)), shift(end, 5))
    keys, k = [], start
    while k <= end:
        keys.append(k)
        k = shift(k, -1)
    vals = [by.get(k, [0.0, 0]) for k in keys]
    top_v = max(v[0] for v in vals)
    step = _nice_step(top_v / 4)
    ymax = step * max(1, math.ceil(top_v / step))
    W, H, left, right, top, base = 720, 236, 8, 666, 24, 204
    slot = (right - left) / len(keys)
    bw = min(24.0, slot * 0.56)
    compact = ymax >= 10000
    ticks = [{"y": round(base - (base - top) * i * step / ymax, 1),
              "label": (f"{i * step / 1000:g}K" if compact and i else f"{i * step:,.0f}")}
             for i in range(int(round(ymax / step)) + 1)]
    i_max = max(range(len(vals)), key=lambda i: vals[i][0])
    bars = []
    for i, (k, (amt, n)) in enumerate(zip(keys, vals)):
        cx = right - slot * (i + 0.5)
        h = (base - top) * amt / ymax if ymax else 0
        x0, x1, yt = cx - bw / 2, cx + bw / 2, base - h
        rr = min(4.0, h, bw / 2)
        path = (f"M{x0:.1f},{base}V{yt + rr:.1f}Q{x0:.1f},{yt:.1f} {x0 + rr:.1f},{yt:.1f}"
                f"H{x1 - rr:.1f}Q{x1:.1f},{yt:.1f} {x1:.1f},{yt + rr:.1f}V{base}Z") if h >= 0.5 else ""
        label = _AR_MONTHS[k[1] - 1]
        bars.append({"cx": round(cx, 1), "x": round(cx - slot / 2, 1), "w": round(slot, 1),
                     "path": path, "yt": round(yt, 1), "amount": format_amount(amt) or "0",
                     "n": n, "month": label, "title": f"{label} {k[0]}",
                     "n_txt": ("لا دفعات" if not n else "دفعة واحدة" if n == 1 else
                               "دفعتان" if n == 2 else f"{n} دفعات" if n <= 10 else f"{n} دفعة"),
                     "year": k[0] if (k[1] == 1 or i == 0) else "",
                     "cap": bool(amt) and i in (i_max, len(keys) - 1),
                     "now": k == end})
    this = by.get(end, [0.0, 0])[0]
    prev = by.get(shift(end, 1), [0.0, 0])[0]
    return {"bars": bars, "ticks": ticks, "W": W, "H": H, "left": left, "right": right,
            "base": base, "this": format_amount(this) or "0",
            "this_month": _AR_MONTHS[end[1] - 1],
            "delta": round((this - prev) * 100 / prev) if prev else None,
            "dated": format_amount(dated) or "0",
            "undated": format_amount(undated) if undated >= 1 else ""}


def _recent_activity(limit: int = 6) -> list:
    """آخر العمليات من سجلّ التدقيق (للمدير فقط)."""
    from hajj_app import audit
    out = []
    for e in audit.read_entries(limit=limit):
        try:
            ago = _ago(datetime.fromisoformat(str(e.get("ts") or "")).timestamp())
        except ValueError:
            ago = ""
        out.append({"action": str(e.get("action") or ""), "details": str(e.get("details") or ""),
                    "user": str(e.get("user") or "—"), "ago": ago})
    return out


def _dash_brief(fin, trips, alerts) -> list:
    """جُمل قصيرة في ترويسة اللوحة: نسبة التحصيل، أقرب رحلة، والتنبيهات العاجلة."""
    out = []
    if fin.total:
        out.append(f"التحصيل {fin.collected_percent}% من {format_amount(fin.total)} درهم")
    if trips:
        t = trips[0]
        if t["state"] == "now":
            out.append(f"رحلة «{t['label']}» جارية الآن")
        elif t["state"] == "today":
            out.append(f"مغادرة «{t['label']}» اليوم")
        elif t["days"] == 1:
            out.append(f"أقرب رحلة «{t['label']}» غداً")
        else:
            out.append(f"أقرب رحلة «{t['label']}» بعد {t['days']} {t['unit']}")
    urgent = sum(1 for a in alerts if a.get("level") == "danger")
    if urgent:
        out.append(f"تنبيهات عاجلة: {urgent}")
    return out


def _season_rings(records, fin) -> list:
    """حلقات ملخّص الموسم (من الخارج للداخل): التحصيل، ثم المقاعد والغرف في
    العمرة، أو الجاهزية والجوازات السارية في الحج."""
    rings = [{"key": "paid", "label": "التحصيل", "pct": fin.collected_percent,
              "color": "#1E9E6A",
              "detail": f"{format_amount(fin.paid) or '0'} من {format_amount(fin.total) or '0'} درهم"}]
    try:
        if _mode() == app_mode.UMRAH:
            from hajj_app import umrah
            trips = umrah.load_trips(storage.load_settings())
            live = [r for r in records
                    if str(getattr(r, "status", "") or "").strip() != "ملغى"]
            cap = n = 0
            for t in trips:
                try:
                    c = int(float(str(t.capacity or "").strip() or 0))
                except ValueError:
                    c = 0
                if c:
                    cap += c
                    n += len(umrah.trip_pilgrims(live, t.code))
            if cap:
                rings.append({"key": "seats", "label": "المقاعد",
                              "pct": min(100, round(n * 100 / cap)), "color": "#2C7BD0",
                              "detail": f"{n:,} من {cap:,} مقعداً"})
            pools = umrah.room_pools(trips)
            avail = used = 0
            for t in trips:
                if pools[t.code][0].code != t.code:
                    continue
                for _city, a, u, _left in umrah.trip_rooms_left(t, live, pool=pools[t.code]):
                    avail += a
                    used += u
            if avail:
                rings.append({"key": "rooms", "label": "الغرف",
                              "pct": min(100, round(used * 100 / avail)), "color": "#E0A12B",
                              "detail": f"{used:,} من {avail:,} غرفة (مكة والمدينة)"})
        elif records:
            from hajj_app import quality
            marks = [quality.pilgrim_readiness(r) for r in records]
            total = len(marks) * len(marks[0])
            ready = sum(sum(1 for v in m.values() if v) for m in marks)
            rings.append({"key": "ready", "label": "الجاهزية",
                          "pct": round(ready * 100 / total), "color": "#2C7BD0",
                          "detail": "الجواز والتأشيرة والتصريح والتطعيم والسداد والتواصل"})
            ok = sum(1 for m in marks if m["passport"])
            rings.append({"key": "passport", "label": "جوازات سارية",
                          "pct": round(ok * 100 / len(marks)), "color": "#E0A12B",
                          "detail": f"{ok:,} من {len(marks):,}"})
    except Exception:                              # noqa: BLE001
        pass
    return rings


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


def _audit_as(user: str, action: str, details: str = "") -> None:
    try:
        from hajj_app import audit
        audit.record(action, details, user=user)
    except Exception:                              # noqa: BLE001
        pass


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


# ---- مدّة الجلسة: خروج تلقائي بعد مدّة بلا نشاط (يحدّدها المدير لكل المستخدمين) ----
SESSION_CHOICES = (15, 30, 60, 120, 240, 480, 720, 1440)   # دقائق؛ 0 = بلا حدّ
_LAST_SEEN: dict = {}              # رمز الجلسة → وقت آخر نشاط
_IDLE_FREE = {"static", "service_worker", "session_status"}   # لا تُحسب نشاطاً


def _session_minutes() -> int:
    try:
        m = int(auth.get_policy().get("session_minutes") or 0)
    except (TypeError, ValueError):
        return 0
    return m if m in SESSION_CHOICES else 0


@app.before_request
def _idle_timeout():
    sid = session.get("sid")
    if sid is None or _sess() is None:
        return None
    now, mins = time.time(), _session_minutes()
    seen = _LAST_SEEN.get(sid, now)
    if mins and now - seen > mins * 60:
        hs = _SESSIONS.get(sid)
        _end(sid)
        session.clear()
        try:
            from hajj_app import audit
            audit.record("انتهاء الجلسة", f"بعد {mins} دقيقة بلا نشاط",
                         user=getattr(hs, "username", "") or "—")
        except Exception:                          # noqa: BLE001
            pass
        if request.endpoint == "session_status":
            return None
        return redirect(url_for("login", expired=1))
    if request.endpoint not in _IDLE_FREE:
        _LAST_SEEN[sid] = now
        try:
            from webapp import websessions
            websessions.touch(sid)
        except Exception:                          # noqa: BLE001
            pass
    else:
        _LAST_SEEN.setdefault(sid, now)
    return None


@app.get("/session/status")
def session_status():
    """الثواني المتبقّية قبل الخروج التلقائي (لا يُعدّ نشاطاً)."""
    mins = _session_minutes()
    sid = session.get("sid")
    if sid is None or _sess() is None:
        return {"left": 0}
    if not mins:
        return {"left": None}
    return {"left": max(0, int(mins * 60 - (time.time() - _LAST_SEEN.get(sid, time.time()))))}


@app.post("/session/ping")
def session_ping():
    """نشاط في الصفحة (كتابة/نقر) دون طلب للخادم: يمدّد الجلسة."""
    return {"ok": _sess() is not None}


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
        _end(session.get("sid"))
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
    try:
        from webapp import offsite                 # النسخة الخارجية بالبريد (إن حان موعدها)
        if not str(request.endpoint or "").startswith("backup_offsite"):
            offsite.maybe_run(_sess())
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
    from webapp import offsite
    return render_template("backup.html", active="backup", snaps=snaps,
                           off=offsite.status(s), off_freqs=offsite.FREQS,
                           mail_ok=_mailer().configured(),
                           keep=backup.KEEP_DAYS, msg=session.pop("bk_msg", ""),
                           err=session.pop("bk_err", ""), **_ctx())


@app.post("/backup/offsite")
def backup_offsite():
    """إعداد النسخة الخارجية التلقائية بالبريد — للمدير."""
    s, bad = _backup_admin()
    if bad:
        return bad
    from webapp import offsite
    if request.form.get("action") == "disable":
        offsite.disable()
        _audit("إيقاف النسخة الخارجية بالبريد")
        session["bk_msg"] = "أُوقفت النسخة الخارجية التلقائية."
        return redirect(url_for("backup_page"))
    pw = request.form.get("password") or ""
    if pw != (request.form.get("confirm") or ""):
        session["bk_err"] = "كلمة مرور النسخ وتأكيدها غير متطابقتين."
        return redirect(url_for("backup_page"))
    try:
        cfg = offsite.configure(s, request.form.get("email"), request.form.get("freq"), pw)
    except ValueError as exc:
        session["bk_err"] = str(exc)
        return redirect(url_for("backup_page"))
    label = offsite.FREQS[cfg["freq"]][0]
    _audit("إعداد النسخة الخارجية بالبريد", f"{label} إلى {cfg['email']}")
    session["bk_msg"] = f"✅ حُفظ: تُرسل نسخة مشفّرة {label} إلى {cfg['email']}."
    return redirect(url_for("backup_page"))


@app.post("/backup/offsite/send")
def backup_offsite_send():
    """إرسال نسخة خارجية الآن (للتجربة أو قبل تغيير كبير)."""
    s, bad = _backup_admin()
    if bad:
        return bad
    from webapp import offsite
    cfg = offsite.load()
    pw = offsite._password(s, cfg) if cfg.get("pw") else None
    if not cfg.get("enabled") or pw is None:
        session["bk_err"] = "أكمل إعداد النسخة الخارجية أولاً (البريد وكلمة مرور النسخ)."
        return redirect(url_for("backup_page"))
    ok, msg = offsite.send_now(pw, cfg["email"])
    _audit("نسخة خارجية بالبريد" if ok else "فشل النسخة الخارجية", msg)
    session["bk_msg" if ok else "bk_err"] = ("✅ " if ok else "") + msg
    return redirect(url_for("backup_page"))


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
                backup.unwrap_mail_zip(enc)        # نسخة البريد: zip فيه .almbak
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
    for _d in (_SESSIONS, _ALERTS_CACHE, _PENDING, _TOTP_SETUP, _TOTP_LAST, _FAILS,
               _EMAIL_SETUP, _LAST_SEEN):
        _d.clear()
    from webapp import resets, websessions
    resets.clear()                    # مفتاح البيانات قد تغيّر: الروابط القديمة لا تصلح
    websessions.clear()
    session.clear()
    return redirect(url_for("login", restored=1))


# ---- إلزام الدخول بخطوتين (إن فعّله المدير لكل الحسابات) ----
_2FA_FREE = {"account_2fa", "logout", "static", "version", "login", "login_2fa",
             "setup", "recover", "switch", "index", "service_worker",
             "forgot", "reset_password", "session_status", "session_ping",
             "verify_doc", "person_page", "public_trips", "public_trip_request", "trips_og"}


_PW_FREE = _2FA_FREE | {"account_password", "session_ping", "healthz"}


def _password_days() -> int:
    from webapp import pwpolicy
    try:
        d = int(auth.get_policy().get("password_days") or 0)
    except (TypeError, ValueError):
        return 0
    return d if d in pwpolicy.CHOICES else 0


@app.before_request
def _password_expiry():
    s = _sess()
    if s is None or request.endpoint in _PW_FREE:
        return None
    try:
        from webapp import pwpolicy
        left = pwpolicy.days_left(s.username, _password_days())
    except Exception:                              # noqa: BLE001
        return None
    if left is not None and left <= 0:
        return redirect(url_for("account_password", expired=1))
    return None


@app.route("/account/password", methods=["GET", "POST"])
def account_password():
    """تغيير المستخدم كلمة مروره بنفسه (وإلزامياً عند انتهائها)."""
    s = _sess()
    if s is None:
        return redirect(url_for("login"))
    from webapp import pwpolicy
    error, fresh_key = "", None
    if request.method == "POST":
        old = request.form.get("old") or ""
        new = request.form.get("password") or ""
        wait = _lock_wait(s.username)
        if wait:
            error = _lock_msg(wait)
        elif new != (request.form.get("confirm") or ""):
            error = "كلمتا المرور الجديدتان غير متطابقتين."
        elif new == old:
            error = "اختر كلمة مرور مختلفة عن الحالية."
        else:
            try:
                hs = auth.change_password(s.username, old, new)
            except Exception as exc:               # noqa: BLE001
                if "غير صحيحة" in str(exc) or "incorrect" in str(exc).lower():
                    _note_fail(s.username, "كلمة مرور حالية خاطئة عند التغيير")
                    error = "كلمة المرور الحالية غير صحيحة."
                else:
                    error = str(exc)
            else:
                pwpolicy.mark(s.username)
                me = session.get("sid")
                hs.role = s.role
                for sid in [k for k, v in _SESSIONS.items()     # خروج جلساته الأخرى
                            if k != me and getattr(v, "username", "").lower() == s.username.lower()]:
                    _end(sid)
                from webapp import websessions
                mine = websessions.sid_id(me or "")
                for r in websessions.list_all():
                    if r["user"].lower() == s.username.lower() and r["id"] != mine:
                        websessions.drop_id(r["id"])
                _SESSIONS[me] = hs
                _audit("تغيير كلمة المرور", "من صفحة الحساب")
                email = auth.get_email(s.username)
                if email:
                    m = _mailer()
                    m.send(email, "تغيّرت كلمة مرورك", m.wrap("تغيّرت كلمة مرورك", (
                        f"<p>غُيّرت كلمة مرور حسابك «{_html.escape(s.username)}» الآن.</p>"
                        "<p>إن لم تفعل ذلك أنت فأبلغ المدير فوراً.</p>")))
                fresh_key = getattr(hs, "fresh_recovery_key", None)
                session["pw_msg"] = "✅ غُيّرت كلمة المرور، وأُخرجت جلساتك على الأجهزة الأخرى."
                if not fresh_key:
                    return redirect(url_for("account_password"))
    days = _password_days()
    return render_template(
        "account_password.html", active="", error=error, fresh_key=fresh_key,
        expired=bool(request.args.get("expired")), days=days,
        left=pwpolicy.days_left(s.username, days),
        msg=session.pop("pw_msg", ""), **_ctx())


@app.post("/accounts/password-policy")
def accounts_password_policy():
    """انتهاء كلمة المرور لكل الحسابات — للمدير."""
    s = _sess()
    if s is None:
        return redirect(url_for("login"))
    from webapp import pwpolicy
    try:
        days = int(request.form.get("days") or 0)
    except ValueError:
        days = 0
    if days not in pwpolicy.CHOICES:
        days = 0
    try:
        auth.set_policy(s, password_days=days)
        session["acc_msg"] = (f"تنتهي كلمة مرور كل حساب بعد {days} يوماً من آخر تغيير لها."
                              if days else "كلمات المرور لا تنتهي.")
        _audit("سياسة انتهاء كلمة المرور", f"{days} يوماً" if days else "لا تنتهي")
    except Exception as exc:
        session["acc_err"] = str(exc)
    return redirect(url_for("accounts"))


@app.before_request
def _require_2fa():
    s = _sess()
    if s is None or request.endpoint in _2FA_FREE:
        return None
    try:
        if (auth.get_policy().get("require_totp") and not auth.has_totp(s.username)
                and not _mail_2fa(s.username)):
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
    from webapp import mailer
    enabled = auth.has_totp(s.username)
    required = bool(auth.get_policy().get("require_totp"))
    email = auth.get_email(s.username)
    email_on = auth.has_email_2fa(s.username)
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
        elif action == "email_send" and not email_on:
            if not (email and mailer.configured()):
                err = "رمز الإيميل غير متاح — لا يوجد إيميل لحسابك أو البريد غير مفعّل."
            else:
                st = _EMAIL_SETUP.setdefault(sid, {})
                err, msg = _mail_code(st, email, "رمز التفعيل",
                                      "رمز تفعيل الدخول برمز على الإيميل:")
        elif action == "email_enable" and not email_on:
            if _check_mail_code(_EMAIL_SETUP.get(sid, {}), code):
                auth.set_email_2fa(s, True)
                _EMAIL_SETUP.pop(sid, None)
                _audit("تفعيل رمز الدخول على الإيميل", s.username)
                email_on, msg = True, "✅ فُعِّل رمز الدخول على الإيميل لحسابك."
            else:
                _note_fail(s.username, "رمز تفعيل الإيميل خاطئ")
                err = "الرمز غير صحيح أو انتهت مدّته — اطلب رمزاً جديداً."
        elif action == "email_disable" and email_on:
            if required and not enabled:
                err = ("الدخول بخطوتين إلزامي — فعّل تطبيق المصادقة أولاً ثم ألغِ "
                       "رمز الإيميل.")
            else:
                auth.set_email_2fa(s, False)
                _audit("إلغاء رمز الدخول على الإيميل", s.username)
                email_on, msg = False, "أُلغي رمز الدخول على الإيميل لحسابك."
        elif action == "disable" and enabled:
            if required and not email_on:
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
                           email=_mask_email(email), email_on=email_on,
                           mail_ok=mailer.configured(),
                           email_sent=bool(_EMAIL_SETUP.get(sid, {}).get("ecode")),
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
        nav_badges=_nav_badges(),
        session_minutes=_session_minutes() if s is not None else 0,
        cmd_items=_cmd_items(),
        book_new=_book_new_count() if s is not None else 0,
        search_q=(request.args.get("q") or "") if request.endpoint == "search_page" else "")


def _nav_badges() -> dict:
    """رقم على أيقونة كل قسم في القائمة بما يحتاج انتباهاً (تحذير/عاجل)."""
    if _sess() is None:
        return {}
    section = {"program": "ops", "travel": "ops", "finance": "fin", "quality": "reports",
               "missing": "people"}
    out: dict = {}
    try:
        for a in _alerts():
            sec = section.get(a.get("kind"))
            if not sec or a.get("level") not in ("warn", "danger"):
                continue
            b = out.setdefault(sec, {"n": 0, "level": "warn"})
            b["n"] += 1
            if a["level"] == "danger":
                b["level"] = "danger"
        if _sess().is_admin:
            from webapp import resets
            k = sum(1 for r in resets.pending() if r.get("status") == "pending")
            if k:
                out["admin"] = {"n": k, "level": "warn"}
            from webapp import offsite                 # النسخة الخارجية متعطّلة
            cfg = offsite.load()
            if cfg.get("enabled") and cfg.get("last_err"):
                b = out.setdefault("admin", {"n": 0, "level": "warn"})
                b["n"] += 1
                b["level"] = "danger"
    except Exception:                              # noqa: BLE001
        pass
    return out


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
    if k == "missing":                    # من تنقصهم بيانات في هذا البرنامج بالضبط
        return url_for("hujjaj", grp=ref, need=1)
    return url_for("dashboard")


@app.get("/notifications")
def notifications():
    if _sess() is None:
        return redirect(url_for("login"))
    items = [dict(a, link=_alert_link(a)) for a in _alerts()]
    return render_template("notifications.html", active="notifications",
                           items=items, **_ctx())


def _search_groups(q: str) -> list:
    """نتائج البحث الشامل مع رابط كل نتيجة (لصفحة البحث ولوحة البحث السريع)."""
    from webapp import search as _sr
    records = _load_records()
    try:
        docs = storage.load_documents(session=_sess())
    except Exception:                              # noqa: BLE001
        docs = []
    groups = _sr.search(q, records, storage.load_settings(), _mode(), docs)
    for g in groups:
        for it in g["items"]:
            k, ref = it["kind"], it["ref"]
            if k == "record":
                it["link"] = url_for("hujjaj_edit", idx=ref, fp=_rec_token(records[ref]))
                it["extra"] = url_for("record_docs", idx=ref, fp=_rec_token(records[ref]))
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
    return groups


_SUGGEST_ICON = {"record": "user", "program": "folder", "package": "package",
                 "quote": "receipt", "pricing": "calculator", "archive": "archive"}


@app.get("/search/suggest")
def search_suggest():
    """اقتراحات لوحة البحث السريع (Ctrl+K) أثناء الكتابة — JSON، ٦ لكل مجموعة."""
    if _sess() is None:
        return {"groups": [], "login": True}, 401
    q = (request.args.get("q") or "").strip()[:80]
    out = []
    if len(q) >= 2:
        for g in _search_groups(q):
            out.append({"title": g["title"], "total": g["total"],
                        "items": [{"t": it["title"], "s": it.get("sub", ""),
                                   "u": it["link"], "i": _SUGGEST_ICON.get(it["kind"], "search")}
                                  for it in g["items"][:6]]})
    return {"q": q, "groups": out, "all": url_for("search_page", q=q)}


def _cmd(t, k, u, i, g) -> dict:
    return {"t": t, "k": k, "u": u, "i": i, "g": g}


def _cmd_items() -> list:
    """صفحات البورتال وإجراءاته السريعة للوحة البحث (حسب الصلاحية والنظام).
    كل عنصر: t العنوان، k كلمات مساعدة للمطابقة، u الرابط، i الأيقونة، g المجموعة."""
    s = _sess()
    if s is None:
        return []
    um = _mode() == app_mode.UMRAH
    to = app_mode.HAJJ if um else app_mode.UMRAH
    A, P = "إجراءات سريعة", "الصفحات"
    items = []
    if s.can_edit:
        items += [_cmd("إضافة سجلّ جديد", "اضافه جديد معتمر حاج", url_for("hujjaj_new"), "plus", A),
                  _cmd("قراءة جواز بالكاميرا", "مسح صوره جواز", url_for("hujjaj_scan"), "camera", A)]
    items += [
        _cmd("من لم يدفع شيئاً", "سداد متاخر تحصيل", url_for("hujjaj", pay="none"), "alert", A),
        _cmd("من سدّد جزئياً", "سداد جزئي متبقي", url_for("hujjaj", pay="part"), "hourglass", A),
        _cmd("من تنقصهم بيانات السفر", "ناقص تاشيره جواز هاتف", url_for("hujjaj", need=1), "clipboard", A),
        _cmd("التبديل إلى نظام " + app_mode.theme(to)["noun"], "تبديل نظام حج عمره",
             url_for("switch", mode=to, t=_csrf_token()), "swap", A),
        _cmd("لوحة التحكم", "الرئيسيه ملخص", url_for("dashboard"), "grid", P),
        _cmd("السجلّات والبيانات", "قائمه معتمرين حجاج كشف", url_for("hujjaj"), "users", P),
        _cmd("المستندات", "سند فاتوره عقد فاوتشر", url_for("documents"), "file-text", P),
        _cmd("أرشيف المستندات", "ارشيف", url_for("archive"), "archive", P),
        _cmd("المجموعات والمرشدون", "مرشد مجموعه", url_for("groups_page"), "users", P),
        _cmd("طلبات الحجز", "حجز طلبات عملاء جدد موقع", url_for("bookings"), "send", P)]
    if um:
        items.append(_cmd("برامج العمرة", "رحلات باقات طيران فنادق", url_for("programs"), "briefcase", P))
    else:
        items += [_cmd("مواعيد وتعليمات السفر", "سفر طيران برامج", url_for("travel_list"), "plane", P),
                  _cmd("تسكين المخيمات", "مخيم خيام منى عرفات", url_for("camps_page"), "tent", P)]
    items += [
        _cmd("إشغال الغرف", "تسكين فنادق غرف", url_for("occupancy"), "bed", P),
        _cmd("تقويم الرحلات", "تقويم مواعيد مغادره عوده", url_for("calendar_page"), "calendar", P),
        _cmd("تسجيل الحضور", "حضور مسح باركود كاميرا مطار فندق باص تجمع", url_for("checkin_page"), "check", P),
        _cmd("المالية والتحصيل", "دفعات سداد مبالغ ايصال", url_for("finance"), "wallet", P),
        _cmd("حملة التحصيل بالواتساب", "تذكير متبقي واتس سداد تحصيل", url_for("finance_remind"), "chat", P)]
    if s.can_edit:
        items.append(_cmd("المصروفات والمحاسبة", "مصاريف محاسبه", url_for("expenses_page"), "receipt", P))
    items += [
        _cmd("التسعير والعروض", "عرض سعر تسعيره", url_for("offers"), "calculator", P),
        _cmd("التقارير والكشوف", "تقرير كشف طباعه", url_for("reports"), "printer", P),
        _cmd("الرسوم البيانية", "رسوم احصاءات", url_for("charts"), "chart", P),
        _cmd("فحص الجودة والجاهزية", "جوده جاهزيه نواقص", url_for("quality_report"), "check", P),
        _cmd("الإشعارات", "تنبيهات", url_for("notifications"), "bell", P),
        _cmd("تحديد الموسم", "موسم سنه", url_for("season_page"), "calendar", P),
        _cmd("رسائل واتساب", "واتس رسائل", url_for("whatsapp_page"), "chat", P)]
    if s.can_edit:
        items.append(_cmd("استيراد من إكسل", "اكسل استيراد ملف", url_for("data_import"), "import", P))
    if s.is_admin:
        items += [
            _cmd("إدارة الحسابات", "مستخدمين صلاحيات حسابات", url_for("accounts"), "shield", P),
            _cmd("الجلسات النشطة", "جلسات اجهزه", url_for("sessions_page"), "phone-device", P),
            _cmd("سجلّ التدقيق", "سجل عمليات تدقيق", url_for("audit_log"), "history", P),
            _cmd("النسخ الاحتياطي", "نسخه احتياطيه استعاده", url_for("backup_page"), "download", P)]
    items += [
        _cmd("تغيير كلمة المرور", "كلمه سر باسورد", url_for("account_password"), "key", P),
        _cmd("الدخول بخطوتين", "تحقق رمز", url_for("account_2fa"), "shield", P),
        _cmd("تسجيل الخروج", "خروج", url_for("logout", t=_csrf_token()), "logout", P)]
    return items


@app.get("/search")
def search_page():
    """البحث السريع الشامل (خانة أعلى كل صفحة)."""
    if _sess() is None:
        return redirect(url_for("login"))
    q = (request.args.get("q") or "").strip()
    groups = _search_groups(q) if q else []
    if q:
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


_BUILD_TAG = "2026-11-12 · عنوان البرامج حسب نوعها وموسمها"
_BUILD_ID = _BUILD_TAG.split(" · ")[0]      # يظهر في رأس صفحات المحرّر


_SW_JS = r"""// عامل خدمة البورتال: يحفظ الملفّات الثابتة فقط (التنسيق والأيقونات) لتسريع
// الفتح، ولا يحفظ أي صفحة فيها بيانات. بلا اتصال تظهر صفحة توضيحية.
const CACHE = 'almustafa-__BUILD__';
const ASSETS = ['/static/style.css', '/static/logo.png', '/static/icons/icon-192.png',
                '/static/fonts/plex-arabic-400-arabic.woff2', '/static/fonts/plex-arabic-700-arabic.woff2',
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


@app.get("/season/<year>/view")
def season_view(year):
    """عرض موسم محفوظ للقراءة فقط — دون فتحه أو تبديل بيانات أحد."""
    s = _sess()
    if s is None:
        return redirect(url_for("login"))
    from webapp import seasons
    if not seasons.has(year):
        return redirect(url_for("season_page"))
    path = seasons._dir(year) / storage.default_data_path().name
    try:
        records = storage._read_file(path, s) if path.is_file() else []
    except Exception:                              # noqa: BLE001
        records = []
    attr = _group_attr()
    rows = []
    for r in records:
        rem = stats.remaining_amount(r)
        rows.append({"name": r.full_name_ar or getattr(r, "full_name", "") or "—",
                     "passport": r.passport_number, "group": getattr(r, attr, "") or "—",
                     "phone": r.phone, "value": format_amount(stats._amount(r.program_value)) or "—",
                     "paid": format_amount(stats._amount(r.paid_amount)) or "0",
                     "rem": format_amount(rem) or "0", "owes": rem > 0.005,
                     "status": r.status or "نشط"})
    rows.sort(key=lambda x: (x["group"], x["name"]))
    fin = stats.financial_summary(records)
    meta = next((m for m in seasons.list_saved() if m["year"] == year), {})
    return render_template(
        "season_view.html", active="season", year=year, rows=rows, fin=fin,
        saved_at=meta.get("saved_at", ""), groups=len({r["group"] for r in rows}),
        fmt=lambda v: format_amount(v) or "0", **_ctx())


@app.route("/season", methods=["GET", "POST"])
def season_page():
    """تحديد موسم الحج/العمرة — مستقلّ لكل وضع، للمدير فقط.

    الانتقال لسنة أخرى يحفظ الموسم الحالي كاملاً، ثم يفتح المحفوظ إن وُجد أو
    يبدأ موسماً جديداً بقوائم فارغة (مع نقل البرامج). «تصحيح السنة» يغيّر
    التسمية فقط دون حفظ أو تفريغ."""
    from webapp import seasons
    if _sess() is None:
        return redirect(url_for("login"))
    app_mode.set_mode(_mode())                   # الإعدادات مستقلّة لكل وضع
    sfx = _season_suffix()
    if request.method == "POST":
        if not _sess().is_admin:
            return redirect(url_for("season_page"))
        year = (request.form.get("season_year") or "").strip()
        current = _season()
        if year not in _season_years() and not seasons.has(year):
            return redirect(url_for("season_page"))
        ok, msg = True, ""
        try:
            if year == current:
                msg = f"الموسم {year}{sfx} مفتوح أصلاً."
            elif request.form.get("relabel"):
                if seasons.has(year):
                    ok, msg = False, (f"للموسم {year}{sfx} نسخة محفوظة — "
                                      "افتحه بدل تصحيح السنة.")
                else:
                    settings = storage.load_settings()
                    settings["season_year"] = year
                    storage.save_settings(settings)
                    _audit("تصحيح سنة الموسم", f"{current}{sfx} ← {year}{sfx}")
                    msg = f"صُحّحت سنة الموسم الحالي إلى {year}{sfx} دون تغيير البيانات."
            else:
                with _UID_LOCK:
                    how = seasons.switch(current, year)
                _ALERTS_CACHE.clear()
                if how == "new":
                    _audit("بدء موسم جديد", f"حُفظ {current}{sfx} — بدأ {year}{sfx}")
                    msg = (f"حُفظ موسم {current}{sfx} وبدأ موسم {year}{sfx} "
                           "بقوائم فارغة (البرامج نُقلت كما هي).")
                else:
                    _audit("فتح موسم محفوظ", f"حُفظ {current}{sfx} — فُتح {year}{sfx}")
                    msg = f"حُفظ موسم {current}{sfx} وفُتح موسم {year}{sfx} كما كان."
        except Exception as exc:                   # noqa: BLE001
            ok, msg = False, f"تعذّر تغيير الموسم: {exc}"
        session["season_msg"] = [ok, msg]
        return redirect(url_for("season_page"))
    cal_label = ("السنة الهجرية" if _mode() == app_mode.HAJJ
                 else "السنة الميلادية")
    saved = seasons.list_saved(_sess())
    saved_years = {s["year"] for s in saved}
    flash = session.pop("season_msg", None) or [True, ""]
    return render_template("season.html", active="season",
                           years=sorted(set(_season_years()) | saved_years),
                           current=_season(), cal_label=cal_label,
                           saved=saved, saved_years=saved_years,
                           msg_ok=flash[0], msg=flash[1], **_ctx())


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
             "email": a.get("email", ""), "email_2fa": a.get("email_2fa", False),
             "locked": bool(_FAILS.get(("user", _ukey(a["username"])))
                            and len([t for t in _FAILS[("user", _ukey(a["username"]))]
                                     if time.time() - t < _LOCK_WINDOW])
                            >= _LOCK_LIMITS["user"]),
             "me": a["username"].lower() == s.username.lower()}
            for a in auth.list_accounts()]
    from webapp import pwpolicy
    return render_template(
        "accounts.html", active="accounts", forbidden=False, accounts=rows,
        require_totp=bool(auth.get_policy().get("require_totp")),
        session_choices=SESSION_CHOICES,
        password_days=_password_days(), password_choices=pwpolicy.CHOICES,
        mail_status=_mailer().status(), resets=_reset_rows(s),
        roles=[(r, auth.ROLE_LABELS[r]) for r in auth.ROLES],
        recovery_key=session.pop("acc_key", None),
        added_user=session.pop("acc_added", None),
        msg=session.pop("acc_msg", ""), err=session.pop("acc_err", ""), **_ctx())


def _mailer():
    from webapp import mailer
    return mailer


def _reset_rows(s) -> list:
    from webapp import resets
    out = []
    for r in resets.pending():
        out.append({"id": r["id"], "user": r["user"], "ip": r.get("ip", ""),
                    "status": r["status"],
                    "own": r["user"].lower() == s.username.lower(),
                    "when": time.strftime("%Y-%m-%d %H:%M", time.localtime(r["created"]))})
    return out


@app.post("/accounts/<username>/email")
def accounts_email(username):
    """إيميل العمل لحساب — للمدير."""
    s = _sess()
    if s is None:
        return redirect(url_for("login"))
    email = (request.form.get("email") or "").strip()
    try:
        if email and not _mailer().valid_email(email):
            raise ValueError("صيغة الإيميل غير صحيحة.")
        auth.set_email(s, username, email)
        session["acc_msg"] = (f"حُفظ إيميل «{username}»." if email
                              else f"أُزيل إيميل «{username}».")
        _audit("إيميل حساب", f"{username} → {email or '—'}")
    except Exception as exc:
        session["acc_err"] = str(exc)
    return redirect(url_for("accounts"))


@app.post("/accounts/mail-test")
def accounts_mail_test():
    """رسالة تجريبية إلى إيميل المدير نفسه — للتأكّد من إعداد البريد."""
    s = _sess()
    if s is None:
        return redirect(url_for("login"))
    if not s.is_admin:
        return redirect(url_for("accounts"))
    m = _mailer()
    to = auth.get_email(s.username)
    if not to:
        session["acc_err"] = "أضف إيميلاً لحسابك أولاً (في جدول المستخدمين)."
    else:
        ok, why = m.send(to, "رسالة تجريبية من بورتال المصطفى", m.wrap(
            "البريد يعمل ✅", "<p>وصلت هذه الرسالة، فإعداد البريد في البورتال سليم.</p>"))
        if ok:
            session["acc_msg"] = f"أُرسلت رسالة تجريبية إلى {to} — تحقّق من صندوقك (وكذلك Spam)."
        else:
            session["acc_err"] = "فشل الإرسال — " + why
    return redirect(url_for("accounts"))


@app.post("/accounts/resets/<rid>/<action>")
def accounts_reset_action(rid, action):
    """موافقة المدير على طلب استعادة (يُرسل الرابط) أو رفضه."""
    from webapp import resets
    s = _sess()
    if s is None:
        return redirect(url_for("login"))
    if not s.is_admin:
        return redirect(url_for("accounts"))
    r = resets.load().get(rid)
    if r is None:
        session["acc_err"] = "الطلب غير موجود أو انتهت مدّته."
    elif action == "deny":
        resets.remove(rid)
        session["acc_msg"] = f"رُفض طلب استعادة «{r['user']}»."
        _audit("رفض طلب استعادة", r["user"])
    elif action == "approve":
        m = _mailer()
        email = auth.get_email(r["user"])
        if r["user"].lower() == s.username.lower():
            session["acc_err"] = "لا توافق على طلبك أنت — يوافق عليه مدير آخر."
        elif r["status"] != "pending":
            session["acc_err"] = "أُرسل رابط هذا الطلب من قبل."
        elif not email:
            session["acc_err"] = f"لا يوجد إيميل لـ«{r['user']}» — أضفه أولاً."
        else:
            token = secrets.token_urlsafe(32)
            resets.approve(rid, auth.wrap_key_for_token(s, token), token)
            link = url_for("reset_password", token=token, _external=True)
            ok, why = m.send(email, "رابط وضع كلمة مرور جديدة", m.wrap(
                "وضع كلمة مرور جديدة", (
                    f"<p>وافق المدير على طلبك لحساب «{_html.escape(r['user'])}». اضغط الزر لوضع "
                    "كلمة مرور جديدة:</p>"
                    f'<p style="text-align:center"><a href="{link}" style="background:#13795B;'
                    'color:#fff;padding:10px 22px;border-radius:8px;text-decoration:none;'
                    'display:inline-block">وضع كلمة مرور جديدة</a></p>'
                    "<p>الرابط صالح ٣٠ دقيقة ولمرة واحدة. إن لم تطلب ذلك فتجاهله وأبلغ المدير.</p>")))
            if ok:
                session["acc_msg"] = f"أُرسل رابط الاستعادة إلى إيميل «{r['user']}» ({_mask_email(email)})."
                _audit("موافقة على طلب استعادة", r["user"])
            else:
                resets.revert(rid)
                session["acc_err"] = "فشل إرسال الرابط — " + why
    return redirect(url_for("accounts"))


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
        _pw_mark(_u)
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
        _pw_mark(username)
        session["acc_msg"] = f"غُيّرت كلمة مرور «{username}» — سلّمها لصاحبه."
        _audit("إعادة تعيين كلمة مرور", username)
        _em = auth.get_email(username)
        if _em and username.lower() != s.username.lower():
            m = _mailer()
            m.send(_em, "تغيّرت كلمة مرورك", m.wrap("تغيّرت كلمة مرورك", (
                f"<p>عيّن المدير كلمة مرور جديدة لحسابك «{_html.escape(username)}». سيسلّمك إياها.</p>"
                "<p>إن لم تكن تتوقّع ذلك فراجع المدير.</p>")))
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


def _minutes_label(m: int) -> str:
    if not m:
        return "بلا حدّ"
    if m < 60:
        return f"{m} دقيقة"
    h = m // 60
    return {1: "ساعة", 2: "ساعتان", 24: "يوم كامل"}.get(h, f"{h} ساعات" if h <= 10 else f"{h} ساعة")


@app.post("/accounts/session-policy")
def accounts_session_policy():
    """مدّة الجلسة (الخروج التلقائي بعد عدم النشاط) لكل الحسابات — للمدير."""
    s = _sess()
    if s is None:
        return redirect(url_for("login"))
    try:
        mins = int(request.form.get("minutes") or 0)
    except ValueError:
        mins = 0
    if mins not in SESSION_CHOICES:
        mins = 0
    try:
        auth.set_policy(s, session_minutes=mins)
        now = time.time()                          # تبدأ المدّة من الآن للجميع
        for sid in _SESSIONS:
            _LAST_SEEN[sid] = now
        session["acc_msg"] = ("مدّة الجلسة الآن: " + _minutes_label(mins)
                              + (" بلا نشاط لكل المستخدمين." if mins else
                                 " — لا خروج تلقائي."))
        _audit("مدّة الجلسة", _minutes_label(mins))
    except Exception as exc:
        session["acc_err"] = str(exc)
    return redirect(url_for("accounts"))


# ---- الجلسات النشطة: من الداخل الآن ومن أي جهاز، مع إنهاء أي جلسة (للمدير) ----
def _ago(ts: float) -> str:
    d = max(0, int(time.time() - ts))
    if d < 90:
        return "الآن"
    m = d // 60
    if m < 60:
        return "منذ دقيقتين" if m == 2 else (f"منذ {m} دقائق" if m <= 10 else f"منذ {m} دقيقة")
    h = m // 60
    if h < 24:
        return "منذ ساعة" if h == 1 else ("منذ ساعتين" if h == 2 else
                                         f"منذ {h} ساعات" if h <= 10 else f"منذ {h} ساعة")
    days = h // 24
    return "منذ يوم" if days == 1 else ("منذ يومين" if days == 2 else f"منذ {days} أيام")


def _session_rows() -> list:
    from datetime import datetime as _dt
    from webapp import websessions
    live = {websessions.sid_id(k): k for k in _SESSIONS}
    mine = websessions.sid_id(session.get("sid") or "")
    mins = _session_minutes()
    rows = []
    for r in websessions.list_all():
        sid = live.get(r["id"])
        last = max(r["last"], _LAST_SEEN.get(sid, 0) if sid else 0)
        if mins and time.time() - last > mins * 60 and r["id"] != mine:
            continue                              # انتهت بعدم النشاط (تُحذف عند أوّل طلب)
        rows.append({
            "id": r["id"], "user": r["user"],
            "role": auth.ROLE_LABELS.get(r["role"], r["role"]),
            "device": websessions.device(r["ua"]), "ip": r["ip"] or "—",
            "since": _dt.fromtimestamp(r["since"]).strftime("%Y-%m-%d %H:%M") if r["since"] else "—",
            "ago": _ago(last), "active": time.time() - last < 300, "mine": r["id"] == mine})
    return rows


@app.get("/sessions")
def sessions_page():
    s, bad = _backup_admin()
    if bad:
        return bad
    rows = _session_rows()
    return render_template("sessions.html", active="sessions", rows=rows,
                           users=len({r["user"].lower() for r in rows}),
                           msg=session.pop("ss_msg", ""), **_ctx())


def _end_by_id(sess_id: str) -> None:
    from webapp import websessions
    for sid in [k for k in _SESSIONS if websessions.sid_id(k) == sess_id]:
        _end(sid)
    websessions.drop_id(sess_id)


@app.post("/sessions/<sess_id>/end")
def sessions_end(sess_id):
    s, bad = _backup_admin()
    if bad:
        return bad
    row = next((r for r in _session_rows() if r["id"] == sess_id), None)
    if row is None or row["mine"]:
        return redirect(url_for("sessions_page"))
    _end_by_id(sess_id)
    _audit("إنهاء جلسة", f"{row['user']} — {row['device']} — {row['ip']}")
    session["ss_msg"] = f"أُنهيت جلسة «{row['user']}» ({row['device']})."
    return redirect(url_for("sessions_page"))


@app.post("/sessions/end-others")
def sessions_end_others():
    s, bad = _backup_admin()
    if bad:
        return bad
    others = [r for r in _session_rows() if not r["mine"]]
    for r in others:
        _end_by_id(r["id"])
    _audit("إنهاء كل الجلسات الأخرى", f"{len(others)} جلسة")
    session["ss_msg"] = f"أُنهيت {len(others)} جلسة — بقيت جلستك فقط."
    return redirect(url_for("sessions_page"))


@app.post("/accounts/<username>/delete")
def accounts_delete(username):
    s = _sess()
    if s is None:
        return redirect(url_for("login"))
    try:
        auth.remove_account(s, username)
        _end_user(username)
        try:
            from webapp import pwpolicy
            pwpolicy.forget(username)
        except Exception:                          # noqa: BLE001
            pass
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


# حالة السداد لكل سجلّ: (التسمية، صنف اللون، الأيقونة) — تُعرض بنصّ وأيقونة لا باللون وحده
_PAY_STATES = {"paid": ("مسدَّد", "good", "check"),
               "part": ("سداد جزئي", "warn", "hourglass"),
               "none": ("لم يدفع", "crit", "alert")}


def _pay_state(r) -> str:
    """paid / part / none — أو "" إن لم تُحدَّد قيمة البرنامج."""
    if stats._amount(getattr(r, "program_value", "")) <= 0:
        return ""
    if remaining_amount(r) <= 0:
        return "paid"
    return "part" if stats._amount(getattr(r, "paid_amount", "")) > 0 else "none"


def _list_filtered(records, gattr, ignore_pay: bool = False):
    """يطبّق البحث والفلاتر والترتيب من معطيات الطلب؛ يعيد [(idx, record)]."""
    q = (request.args.get("q") or "").strip().lower()
    sel = {}
    for key, _l in _FILTER_FIELDS:
        v = (request.args.get("flt_" + key) or "").strip()
        if v:
            sel[key] = v
    sort = (request.args.get("sort") or "").strip()
    pay = "" if ignore_pay else (request.args.get("pay") or "").strip()
    if pay not in _PAY_STATES:
        pay = ""
    grp = (request.args.get("grp") or "").strip()          # برنامج/رحلة بعينها
    need = request.args.get("need") == "1"                 # من تنقصهم بيانات السفر
    from webapp.alerts import missing_fields
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
        if pay and _pay_state(r) != pay:
            continue
        if grp and str(getattr(r, gattr, "") or "").strip() != grp:
            continue
        if need and not missing_fields(r, _mode()):
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
    from webapp.alerts import missing_fields
    grp = (request.args.get("grp") or "").strip()
    need = request.args.get("need") == "1"
    pay = (request.args.get("pay") or "").strip()
    pay = pay if pay in _PAY_STATES else ""
    # أعداد أزرار السداد: على نتيجة البحث والفلاتر الأخرى (قبل تصفية السداد)
    base = indexed if not pay else _list_filtered(records, gattr, ignore_pay=True)
    counts = {"all": len(base)}
    for key in _PAY_STATES:
        counts[key] = 0
    for _i, r in base:
        st_ = _pay_state(r)
        if st_:
            counts[st_] += 1

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
        name = getattr(r, "full_name_ar", "") or getattr(r, "full_name_en", "") or "—"
        name_en = str(getattr(r, "full_name_en", "") or "").strip()
        ps = _pay_state(r)
        value = stats._amount(getattr(r, "program_value", ""))
        rem = remaining_amount(r)
        initial = next((ch for ch in name if ch.isalpha()), "؟")
        rows.append({
            "idx": i, "name": name,
            "name_en": name_en if name_en and name_en != name else "",
            "initial": initial.upper(), "hue": sum(map(ord, name)) % 6,
            "passport": getattr(r, "passport_number", "") or "—",
            "program": str(getattr(r, gattr, "") or "") or "—",
            "phone": getattr(r, "phone", "") or "—",
            "status": st, "status_cls": _STATUS_CLS.get(st, ""),
            "remaining": format_amount(rem) or "0",
            "pay": ps, "pay_lbl": _PAY_STATES[ps][0] if ps else "",
            "pay_cls": _PAY_STATES[ps][1] if ps else "",
            "pay_icon": _PAY_STATES[ps][2] if ps else "",
            "pct": max(0, min(100, round((value - rem) * 100 / value))) if value > 0 else 0,
            "missing": missing_fields(r, _mode()) if need else [],
        })
    qs = {"q": q, "sort": sort}                     # لحفظ الفلاتر عبر الصفحات
    for key, val in sel.items():
        qs["flt_" + key] = val
    if grp:
        qs["grp"] = grp
    if need:
        qs["need"] = 1
    qs_nopay = dict(qs)
    if pay:
        qs["pay"] = pay
    pay_states = [(k, lbl, cls, icon) for k, (lbl, cls, icon) in _PAY_STATES.items()]
    return render_template("hujjaj.html", active="hujjaj", rows=rows, q=q,
                           filteropts=filteropts, sel=sel, sort=sort,
                           sortfields=_SORT_FIELDS,
                           any_filter=bool(sel or sort or pay or grp or need),
                           qs=qs, qs_nopay=qs_nopay, pay=pay, pay_states=pay_states,
                           grp=grp, need=need,
                           counts=counts, total=total, page=page, pages=pages,
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


# بيانات ترويسة المستندات (تظهر في رأس وتذييل السند والفاتورة والعقد والفاوتشر)
_CO_FIELDS = (("name_ar", "اسم الشركة بالعربية", 80), ("name_en", "الاسم بالإنجليزية", 80),
              ("phone", "الهاتف", 40), ("email", "البريد الإلكتروني", 120),
              ("website", "الموقع الإلكتروني", 120), ("trn", "الرقم الضريبي (TRN)", 20),
              ("address", "العنوان", 120))


@app.get("/documents")
def documents():
    """بند «المستندات» المستقلّ: قائمة أنواع المستندات (اختر النوع ثم الشخص)."""
    s = _sess()
    if s is None:
        return redirect(url_for("login"))
    co = {}
    if s.is_admin:
        settings = storage.load_settings()
        raw = settings.get("company") if isinstance(settings, dict) else None
        co = raw if isinstance(raw, dict) else {}
    msg, err = session.pop("acc_msg", None), session.pop("acc_err", None)
    return render_template("documents.html", active="documents",
                           docs=_DOC_KINDS, co=co, co_fields=_CO_FIELDS,
                           msg=msg, err=err, **_ctx())


@app.post("/documents/company")
def documents_company():
    """يحفظ بيانات ترويسة المستندات (للمدير) — في نظامَي الحج والعمرة معاً كي
    تخرج مستندات النظامين بالترويسة نفسها."""
    s, bad = _backup_admin()
    if bad:
        return bad
    new = {}
    for key, label, limit in _CO_FIELDS:
        v = " ".join((request.form.get(key) or "").split())
        if len(v) > limit:
            session["acc_err"] = f"«{label}» أطول من المسموح ({limit} حرفاً)."
            return redirect(url_for("documents") + "#letterhead")
        new[key] = v
    if new["email"] and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", new["email"]):
        session["acc_err"] = "البريد الإلكتروني غير صحيح."
        return redirect(url_for("documents") + "#letterhead")
    if new["trn"] and not re.fullmatch(r"\d{15}", new["trn"]):
        session["acc_err"] = "الرقم الضريبي في الإمارات ١٥ رقماً."
        return redirect(url_for("documents") + "#letterhead")
    cur = _mode()
    try:
        for m in app_mode.MODES:
            app_mode.set_mode(m)
            st = storage.load_settings()
            co = st.get("company") if isinstance(st.get("company"), dict) else {}
            co.update(new)                      # يحفظ أيّ مفاتيح أخرى كما هي
            st["company"] = co
            storage.save_settings(st)
    finally:
        app_mode.set_mode(cur)
    _audit("تعديل ترويسة المستندات", new["name_ar"] or "—")
    session["acc_msg"] = "حُفظت بيانات الترويسة — تظهر في كل مستند تُصدره من الآن."
    return redirect(url_for("documents") + "#letterhead")


@app.get("/documents/company/preview.pdf")
def documents_company_preview():
    """معاينة الترويسة: فاتورة تجريبية باسم «عميل تجريبي» (لا تُؤرشف ولا تأخذ رقماً)."""
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app import pdf_io
    from hajj_app.mrz import PassportData
    settings = storage.load_settings()
    co = settings.get("company") if isinstance(settings, dict) else None
    demo = PassportData(full_name_ar="عميل تجريبي", passport_number="X0000000",
                        phone="0500000000", nationality_ar="—",
                        program_value="5000", paid_amount="2000")
    return _pdf_response(
        lambda p: pdf_io.export_invoice_pdf(
            demo, p, company=co, number="معاينة",
            data={"item_desc": "معاينة شكل الترويسة والتذييل — ليست فاتورة حقيقية",
                  "notes": "هذه صفحة معاينة فقط."}),
        "letterhead-preview.pdf")


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


def _nights_txt(n) -> str:
    try:
        k = int(float(str(n).strip()))
    except (TypeError, ValueError):
        return f"{n} ليالٍ" if str(n or "").strip() else ""
    return ("ليلة واحدة" if k == 1 else "ليلتان" if k == 2 else
            f"{k} ليالٍ" if 3 <= k <= 10 else f"{k} ليلة")


def _trip_status(dep, ret, today) -> dict:
    """حالة الرحلة للعدّ التنازلي في صفحة «رحلتي»."""
    if dep and today < dep:
        n = (dep - today).days
        return {"state": "before", "n": n, "unit": _days_unit(n)}
    if dep and (today <= (ret or dep)):
        total = ((ret or dep) - dep).days + 1
        k = (today - dep).days + 1
        return {"state": "during", "n": k, "total": total,
                "pct": round(100 * k / total) if total else 100}
    if (ret or dep) and today > (ret or dep):
        return {"state": "after"}
    return {"state": "unknown"}


@app.get("/p/<token>")
def person_page(token):
    """صفحة «رحلتي» الخاصة بالمعتمر (رابط سرّي يُرسل له): عدّ تنازلي، بطاقتا
    الطيران، الفنادق، المرشد، الطوارئ، ومستنداته — تُقرأ بيانات البرنامج حيّةً
    من الإعدادات (الكشف مشفّر فلا يُعرض منه إلا المحفوظ في الرابط)."""
    from webapp import public
    from webapp.alerts import _d
    p = public.get_person(token)
    if not p:
        return render_template("public_person.html", p=None), 404
    mode = p.get("mode") if p.get("mode") in app_mode.MODES else app_mode.UMRAH
    app_mode.set_mode(mode)
    settings = storage.load_settings()
    today = datetime.now(_UAE).date()
    trip = {"name": p.get("group", ""), "flights": [], "hotels": [],
            "room": p.get("room", ""), "transport": "", "dep": None, "ret": None}
    phones = []

    def leg(label, when, flight, t_dep, t_arr, frm="", to="", carrier="", report=""):
        if not any((flight, t_dep, t_arr)):
            return None
        d = _d(when)
        return {"label": label, "date": _day_txt(d, today) if d else (when or ""),
                "wday": _AR_DAYS[d.weekday()] if d else "", "flight": flight,
                "dep": t_dep, "arr": t_arr, "from": frm, "to": to,
                "carrier": carrier, "report": report}

    if mode == app_mode.UMRAH:
        from hajj_app import umrah
        t = next((x for x in umrah.load_trips(settings) if x.code == p.get("group")), None)
        if t:
            trip["name"] = t.name or t.code
            trip["dep"], trip["ret"] = _d(t.depart_date), _d(t.return_date)
            trip["flights"] = [x for x in (
                leg("رحلة الذهاب", t.depart_date, t.flight_out, t.out_depart_time,
                    t.out_arrive_time, frm=t.depart_city, carrier=t.airline),
                leg("رحلة العودة", t.return_date, t.flight_ret, t.ret_depart_time,
                    t.ret_arrive_time, to=t.depart_city, carrier=t.airline)) if x]
            trip["airline"] = t.airline
            trip["hotels"] = [h for h in (
                {"city": "مكة المكرمة", "icon": "kaaba", "name": t.makkah_hotel,
                 "nights": _nights_txt(t.makkah_nights) if t.makkah_nights else ""},
                {"city": "المدينة المنورة", "icon": "moon", "name": t.madinah_hotel,
                 "nights": _nights_txt(t.madinah_nights) if t.madinah_nights else ""})
                if h["name"]]
            trip["transport"] = t.transport
            phones = [x for x in (("طوارئ الإمارات", t.emergency_uae),
                                  ("طوارئ السعودية", t.emergency_ksa)) if x[1]]
    else:
        from hajj_app import programs as hp
        for nm, pr in zip(hp.PROGRAM_NAMES, hp.load_programs(settings)):
            if nm == p.get("group"):
                trip["dep"], trip["ret"] = _d(pr.travel_date), _d(pr.return_date)
                trip["airline"] = pr.carrier
                trip["flights"] = [x for x in (
                    leg("رحلة الذهاب", pr.travel_date, pr.flight_out, pr.takeoff_out,
                        pr.land_out, frm=pr.departure_airport, to=pr.arrival_airport,
                        carrier=pr.carrier, report=pr.report_out),
                    leg("رحلة العودة", pr.return_date, pr.flight_ret, pr.takeoff_ret,
                        pr.land_ret, frm=pr.arrival_airport, to=pr.departure_airport,
                        carrier=pr.carrier, report=pr.report_ret)) if x]
                if pr.hotel:
                    trip["hotels"] = [{"city": "الفندق", "icon": "kaaba",
                                       "name": pr.hotel, "nights": ""}]
                trip["transport"] = pr.transport
    for k in ("dep", "ret"):
        d = trip[k]
        trip[k + "_txt"] = _day_txt(d, today) if d else ""
        trip[k + "_iso"] = d.isoformat() if d else ""
    trip["status"] = _trip_status(trip["dep"], trip["ret"], today)
    team = str(p.get("team") or "").strip()
    g = (settings.get("groups") or {}).get(team) if team else None
    guide = ({"team": team, "name": str(g.get("guide") or ""),
              "phone": str(g.get("phone") or "")}
             if isinstance(g, dict) and (g.get("guide") or g.get("phone")) else None)
    from hajj_app import whatsapp as _wa
    cc = str(settings.get("whatsapp_cc") or "971")
    if guide and guide["phone"]:
        guide["tel"] = re.sub(r"[^\d+]", "", guide["phone"])
        try:
            guide["wa"] = _wa.wa_link(guide["phone"], "السلام عليكم", cc)
        except Exception:                          # noqa: BLE001
            guide["wa"] = ""
    phones = [(k, v, re.sub(r"[^\d+]", "", v)) for k, v in phones]
    docs = [(url_for("verify_doc", token=tk), _DOC_TITLES.get(d.get("kind"), ("مستند", ""))[0],
             d.get("number", ""), d.get("kind", "")) for tk, d in public.person_docs(mode, p.get("uid"))]
    co = settings.get("company") if isinstance(settings.get("company"), dict) else {}
    code = _checkin_code(mode, str(p.get("uid") or ""))
    from markupsafe import Markup
    checkin_qr = Markup(_qr_svg(code)) if code else ""
    return render_template("public_person.html", p=p, trip=trip, guide=guide,
                           checkin_qr=checkin_qr,
                           phones=phones, docs=docs, mode=mode,
                           co_name=co.get("name_ar") or "المصطفى للحج والعمرة",
                           noun="الحاج" if mode == app_mode.HAJJ else "المعتمر")


def _person_info(rec) -> dict:
    """ما يُحفظ في رابط المعتمر العام — أقلّ قدر لازم (لا جواز ولا هاتف ولا مبالغ)."""
    name = rec.full_name_ar or rec.full_name_en or ""
    return {"first": (name.split() or [""])[0], "group": getattr(rec, _group_attr(), "") or "",
            "room": rec.room_type or "", "team": str(getattr(rec, "group", "") or "").strip()}


# ==================== صفحة البرامج العامة وطلبات الحجز ======================
_BOOK_LOCK = threading.Lock()
_BOOK_HITS: dict = {}                    # عنوان IP ← أوقات الطلبات (حدّ الإرسال)
_BOOK_STATUS = {"new": ("جديد", "warn"), "contacted": ("تم التواصل", "info"),
                "converted": ("صار سجلّاً", "good"), "rejected": ("مؤرشف", "muted")}
_BOOK_ROOMS = ("مفرد", "ثنائي", "ثلاثي", "رباعي")
_PUB_WA_DEFAULT = "00971549964801"   # «راسلنا واتساب» في الصفحة العامة (يُغيَّر من «طلبات الحجز»)


def _book_path():
    from hajj_app.paths import data_dir
    return data_dir() / "booking_requests.enc"


def _book_fernet():
    import base64 as _b64
    from cryptography.fernet import Fernet
    key = hashlib.sha256((_session_secret() + "|booking-requests").encode("utf-8")).digest()
    return Fernet(_b64.urlsafe_b64encode(key))


def _book_load() -> list:
    """طلبات الحجز (مشفّرة على القرص بمفتاح الخادم — فيها أسماء وهواتف)."""
    import json as _json
    p = _book_path()
    if not p.is_file():
        return []
    try:
        data = _json.loads(_book_fernet().decrypt(p.read_bytes()).decode("utf-8"))
        return data if isinstance(data, list) else []
    except Exception:                              # noqa: BLE001
        return []


def _book_save(items: list) -> None:
    import json as _json
    p = _book_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_bytes(_book_fernet().encrypt(_json.dumps(items, ensure_ascii=False).encode("utf-8")))
    os.replace(tmp, p)


def _public_cfg(settings) -> dict:
    cfg = settings.get("public_page") if isinstance(settings.get("public_page"), dict) else {}
    return {"published": [str(x) for x in (cfg.get("published") or [])],
            "intro": str(cfg.get("intro") or ""), "seats": dict(cfg.get("seats") or {}),
            "wa": str(cfg.get("wa") or "")}


def _public_programs(mode: str, settings, today) -> list:
    """برامج النظام المنشورة للعامّة القادمة (لا ماضية): بطاقات بلا أي بيانات أشخاص —
    الأسعار حسب الغرفة، ومواعيد رحلتَي الذهاب والعودة، والفنادق والنقل."""
    from webapp.alerts import _d
    cfg = _public_cfg(settings)
    out = []

    def money(v):
        try:
            n = float(str(v or "").replace(",", "").strip())
        except ValueError:
            return ""
        return format_amount(n) if n > 0 else ""

    def prices(vals):                       # بترتيب _BOOK_ROOMS: مفرد، ثنائي، ثلاثي، رباعي
        return [(room, money(v)) for room, v in zip(_BOOK_ROOMS, vals) if money(v)]

    def leg(label, icon, d, flight, t_dep, t_arr):
        return {"label": label, "icon": icon,
                "date": _day_txt(d, today) if d else "يُحدَّد لاحقاً",
                "wday": _AR_DAYS[d.weekday()] if d else "",
                "flight": str(flight or "").strip(), "dep": str(t_dep or "").strip(),
                "arr": str(t_arr or "").strip()}

    def card(key, name, d0, d1, out_leg, ret_leg, ramadan=False, **kw):
        legs = [leg("الذهاب", "takeoff", d0, *out_leg)]
        if d1 or any(str(x or "").strip() for x in ret_leg):
            legs.append(leg("العودة", "landing", d1, *ret_leg))
        return {"mode": mode, "key": key, "name": name, "d0": d0,
                "dep": _day_txt(d0, today) if d0 else "يُحدَّد لاحقاً", "legs": legs,
                "nights": _nights_txt((d1 - d0).days) if d0 and d1 and d1 > d0 else "",
                "ramadan": bool(ramadan or (d0 and _hijri_month(d0) == 9)),
                "left": cfg["seats"].get(key), **kw}
    if mode == app_mode.UMRAH:
        from hajj_app import umrah
        for t in umrah.load_trips(settings):
            if t.code not in cfg["published"]:
                continue
            d0, d1 = _d(t.depart_date), _d(t.return_date)
            if d0 and d0 < today:
                continue
            out.append(card(
                t.code, t.name or t.code, d0, d1,
                (t.flight_out, t.out_depart_time, t.out_arrive_time),
                (t.flight_ret, t.ret_depart_time, t.ret_arrive_time),
                airline=t.airline, city=t.depart_city,
                hotels=[h for h in (
                    ("kaaba", "مكة المكرمة", t.makkah_hotel, _nights_txt(t.makkah_nights) if t.makkah_nights else ""),
                    ("moon", "المدينة المنورة", t.madinah_hotel, _nights_txt(t.madinah_nights) if t.madinah_nights else ""))
                    if h[2]],
                car=("car", "سيارة خاصة"),
                ramadan="رمضان" in f"{t.package} {t.name}",
                prices=prices([t.price_single, t.price_double, t.price_triple, t.price_quad])))
    else:
        from hajj_app import programs as hp
        for nm, pr in zip(hp.PROGRAM_NAMES, hp.load_programs(settings)):
            if nm not in cfg["published"]:
                continue
            d0, d1 = _d(pr.travel_date), _d(pr.return_date)
            if d0 and d0 < today:
                continue
            bus = "باص" in str(pr.transport or "")
            out.append(card(
                nm, f"الحج — {nm}", d0, d1,
                (pr.flight_out, pr.takeoff_out, pr.land_out),
                (pr.flight_ret, pr.takeoff_ret, pr.land_ret),
                airline=pr.carrier, city=pr.departure_airport,
                hotels=[("kaaba", "الفندق", pr.hotel, "")] if pr.hotel else [],
                car=("bus", "باص") if bus else ("car", "سيارة خاصة"),
                prices=prices([pr.cost_single, pr.cost_double, pr.cost_triple, pr.cost_quad])))
    return out


def _hijri_month(d) -> int:
    """الشهر الهجري لتاريخ ميلادي (التقويم الهجري الجدولي — يكفي لمعرفة رمضان؛
    وأسماء البرامج/الباقات التي فيها «رمضان» تُحتسب رمضانية أيضاً)."""
    import math
    epoch = 1948439.5
    jd = d.toordinal() + 1721424.5

    def to_jd(y, m):
        return 1 + math.ceil(29.5 * (m - 1)) + (y - 1) * 354 + (3 + 11 * y) // 30 + epoch - 1
    y = int((30 * (jd - epoch) + 10646) // 10631)
    return min(12, math.ceil((jd - (29 + to_jd(y, 1))) / 29.5) + 1)


def _progs_label(progs) -> str:
    """عنوان مجموعة برامج: «برامج عمرة رمضان»، «برامج عمرة ديسمبر ويناير»،
    «برامج الحج»، «برامج عمرة رمضان والحج»… (والمفرد «برنامج» لبرنامج واحد)."""
    head = "برنامج" if len(progs) == 1 else "برامج"
    um = sorted((p for p in progs if p.get("mode") == app_mode.UMRAH),
                key=lambda p: (p.get("d0") is None, p.get("d0") or datetime.max.date()))
    hj = [p for p in progs if p.get("mode") == app_mode.HAJJ]
    if not um and not hj:
        return "برامج العمرة والحج"
    parts = []
    if um:
        quals = []
        for p in um:
            q = "رمضان" if p.get("ramadan") else (_AR_MONTHS[p["d0"].month - 1] if p.get("d0") else "")
            if q and q not in quals:
                quals.append(q)
        parts.append("عمرة " + " و".join(quals) if 1 <= len(quals) <= 2 else "العمرة")
    if hj:
        parts.append("الحج")
    return f"{head} " + " و".join(parts)


def _trips_og_text(progs, prog=None) -> tuple:
    """نصوص صورة المعاينة: (العنوان، السطر الثاني، المزايا، الزرّ)."""
    sel = [prog] if prog else progs
    car = any(p.get("mode") == app_mode.UMRAH for p in sel) or not sel
    return (_progs_label(sel),
            prog["name"] if prog else "رحلتك إلى الحرمين تبدأ من هنا",
            "طيران  ·  فنادق قريبة من الحرم  ·  " + ("سيارة خاصة" if car else "نقل ومرشدون"),
            "احجز مقعدك الآن")


def _all_public_programs() -> tuple:
    """البرامج المنشورة في النظامين + مقدّمة الصفحة وبيانات الشركة ورقم الواتساب."""
    today = datetime.now(_UAE).date()
    cur = app_mode.get_mode()
    progs, intro, co, wa = [], "", {}, ""
    try:
        for m in (app_mode.UMRAH, app_mode.HAJJ):
            app_mode.set_mode(m)
            st = storage.load_settings()
            progs += _public_programs(m, st, today)
            intro = intro or _public_cfg(st)["intro"]
            wa = wa or _public_cfg(st)["wa"]
            if not co and isinstance(st.get("company"), dict):
                co = st["company"]
    finally:
        app_mode.set_mode(cur)
    progs.sort(key=lambda x: (x["d0"] is None, x["d0"] or today))
    return progs, intro, co, (wa or _PUB_WA_DEFAULT)


def _sync_public_wa(num: str) -> None:
    """رقم «راسلنا واتساب» واحد للصفحة العامة: يُكتب في إعدادات النظام الآخر أيضاً."""
    cur = app_mode.get_mode()
    try:
        for m in app_mode.MODES:
            if m == cur:
                continue
            app_mode.set_mode(m)
            st = storage.load_settings()
            cfg = st.get("public_page") if isinstance(st.get("public_page"), dict) else {}
            if str(cfg.get("wa") or "") != num:
                cfg["wa"] = num
                st["public_page"] = cfg
                storage.save_settings(st)
    finally:
        app_mode.set_mode(cur)


def _update_public_seats(settings, counts: dict) -> None:
    """يحفظ المقاعد المتبقّية للبرامج المنشورة (لقطة للصفحة العامة — الكشف مشفّر)."""
    cfg = settings.get("public_page") if isinstance(settings.get("public_page"), dict) else None
    if not cfg or not cfg.get("published"):
        return
    old = dict(cfg.get("seats") or {})
    seats = {k: v for k, v in old.items() if k in cfg["published"]}
    seats.update({k: v for k, v in counts.items() if k in cfg["published"]})
    if seats != old:
        cfg["seats"] = seats
        try:
            storage.save_settings(settings)
        except Exception:                          # noqa: BLE001
            pass


def _seat_counts(records, settings) -> dict:
    """المقاعد المتبقّية لكل برنامج (السعة − المسجّلون غير الملغين)، أو None بلا سعة."""
    out = {}
    if _mode() == app_mode.UMRAH:
        from hajj_app import umrah
        for t in umrah.load_trips(settings):
            try:
                cap = int(float(str(t.capacity or "").strip() or 0))
            except ValueError:
                cap = 0
            n = sum(1 for r in umrah.trip_pilgrims(records, t.code)
                    if str(r.status or "").strip() != "ملغى")
            out[t.code] = (cap - n) if cap else None
    return out


@app.get("/trips")
def public_trips():
    """الصفحة العامة: البرامج المنشورة ونموذج «احجز مقعدك» — بلا دخول."""
    from hajj_app import whatsapp as _wa
    progs, intro, co, wa_num = _all_public_programs()
    co = {**{"name_ar": "المصطفى للحج والعمرة"}, **{k: v for k, v in co.items() if v}}
    wa = _wa.wa_link(wa_num, "السلام عليكم، أرغب بالاستفسار عن برامجكم") or ""
    pick = request.args.get("p", "")
    pick_prog = next((x for x in progs if f"{x['mode']}:{x['key']}" == pick), None)
    og = _trips_og_text(progs, pick_prog)
    kinds = {x["mode"] for x in progs}
    noun = ("عمرة وحج" if len(kinds) != 1 else "عمرة" if app_mode.UMRAH in kinds else "حج")
    return render_template("public_trips.html", progs=progs, intro=intro, co=co, wa=wa,
                           label=_progs_label(progs), og_title=og[0], og_sub=og[1] if pick_prog else "",
                           og_img=url_for("trips_og", p=pick if pick_prog else None,
                                          v=hashlib.sha1("|".join(og).encode("utf-8")).hexdigest()[:8],
                                          _external=True),
                           noun=noun,
                           rooms=_BOOK_ROOMS, sent=request.args.get("sent"),
                           err=request.args.get("err", ""), pick=pick,
                           room_opts=(pick_prog or {}).get("prices") or [(r, "") for r in _BOOK_ROOMS],
                           pick_room=request.args.get("r", ""))


@app.get("/trips/og.jpg")
def trips_og():
    """صورة معاينة رابط صفحة البرامج: الكعبة والشعار وعنوان البرامج المنشورة
    (أو البرنامج المختار بـ ?p=)."""
    from webapp import share_image
    progs = _all_public_programs()[0]
    key = request.args.get("p", "")
    prog = next((x for x in progs if f"{x['mode']}:{x['key']}" == key), None)
    data = share_image.render(*_trips_og_text(progs, prog))
    resp = send_file(io.BytesIO(data), mimetype="image/jpeg", max_age=3600)
    return resp


@app.post("/trips/request")
def public_trip_request():
    """يستقبل طلب حجز من الصفحة العامة (تحقّق + حدّ إرسال + حقل فخّ للروبوتات)."""
    import secrets as _secrets
    import time as _time
    f = request.form
    back = url_for("public_trips")
    if (f.get("website") or "").strip():               # حقل مخفيّ لا يملؤه إلا الروبوت
        return redirect(back + "?sent=1#done")
    ip = request.remote_addr or "?"
    now = _time.time()
    hits = [t for t in _BOOK_HITS.get(ip, []) if now - t < 600]
    if len(hits) >= 5:
        return redirect(url_for("public_trips", err="كثرت الطلبات من جهازك — حاول بعد قليل") + "#book")
    key = (f.get("program") or "").strip()
    progs = _all_public_programs()[0]
    prog = next((x for x in progs if f"{x['mode']}:{x['key']}" == key), None)
    name = " ".join((f.get("name") or "").split())[:80]
    phone = re.sub(r"[^\d+]", "", (f.get("phone") or "").translate(
        str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")))[:16]
    try:
        count = max(1, min(20, int(f.get("count") or 1)))
    except ValueError:
        count = 1
    room = (f.get("room") or "").strip()
    room = room if room in _BOOK_ROOMS else ""
    note = (f.get("note") or "").strip()[:300]
    err = ("اختر البرنامج" if not prog else "اكتب الاسم الكامل" if len(name) < 5
           else "اكتب رقم هاتف صحيحاً" if len(re.sub(r"\D", "", phone)) < 8 else "")
    if err:
        return redirect(url_for("public_trips", err=err, p=key, r=room) + "#book")
    _BOOK_HITS[ip] = hits + [now]
    item = {"id": _secrets.token_hex(6), "ts": datetime.now(_UAE).replace(microsecond=0).isoformat(),
            "mode": prog["mode"], "key": prog["key"], "prog": prog["name"], "dep": prog["dep"],
            "name": name, "phone": phone, "count": count, "room": room, "note": note,
            "rprice": dict(prog.get("prices") or []).get(room, ""), "status": "new"}
    with _BOOK_LOCK:
        items = _book_load()
        items.append(item)
        _book_save(items[-2000:])
    return redirect(back + "?sent=1#done")


def _book_new_count() -> int:
    try:
        return sum(1 for x in _book_load() if x.get("status") == "new")
    except Exception:                              # noqa: BLE001
        return 0


@app.route("/bookings", methods=["GET", "POST"])
def bookings():
    """طلبات الحجز الواردة من الصفحة العامة + إعدادات النشر (البرامج المعروضة)."""
    s = _sess()
    if s is None:
        return redirect(url_for("login"))
    settings = storage.load_settings()
    if request.method == "POST":                       # إعدادات النشر — للمدير (زرّ صريح)
        if not s.is_admin:
            return redirect(url_for("bookings"))
        from hajj_app import whatsapp as _wa
        wa_in = re.sub(r"[^\d+]", "", (request.form.get("wa") or "").translate(
            str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")))[:20]
        if wa_in and not _wa.to_intl(wa_in, "971"):
            session["acc_err"] = "رقم الواتساب غير صحيح — اكتبه مع رمز الدولة، مثل 00971501234567."
            return redirect(url_for("bookings") + "#publish")
        cfg = settings.get("public_page") if isinstance(settings.get("public_page"), dict) else {}
        cfg["published"] = [x for x in request.form.getlist("pub") if x][:60]
        cfg["intro"] = (request.form.get("intro") or "").strip()[:400]
        cfg["wa"] = wa_in
        settings["public_page"] = cfg
        storage.save_settings(settings)
        _sync_public_wa(wa_in)
        _update_public_seats(settings, _seat_counts(_load_records(), settings))
        _audit("إعدادات صفحة البرامج العامة", f"{len(cfg['published'])} برنامج منشور")
        session["acc_msg"] = "حُفظت إعدادات الصفحة العامة."
        return redirect(url_for("bookings") + "#publish")
    _update_public_seats(settings, _seat_counts(_load_records(), settings))
    show = request.args.get("show", "open")
    items = list(reversed(_book_load()))
    counts = {k: sum(1 for x in items if x.get("status") == k) for k in _BOOK_STATUS}
    if show == "open":
        items = [x for x in items if x.get("status") in ("new", "contacted")]
    elif show in _BOOK_STATUS:
        items = [x for x in items if x.get("status") == show]
    from hajj_app import whatsapp as _wa
    now = datetime.now(_UAE)
    for x in items:
        x["wa"] = _wa.wa_link(x.get("phone"), f"السلام عليكم {x.get('name', '').split(' ')[0]}، "
                              f"شكراً لطلبكم حجز «{x.get('prog', '')}» — معكم المصطفى للحج والعمرة.",
                              str(settings.get("whatsapp_cc") or "971"))
        try:
            mins = int((now - datetime.fromisoformat(x["ts"])).total_seconds() // 60)
        except (KeyError, ValueError, TypeError):
            mins = 0
        x["ago"] = ("الآن" if mins < 2 else f"قبل {mins} دقيقة" if mins < 60 else
                    f"قبل {mins // 60} ساعة" if mins < 1440 else f"قبل {mins // 1440} يوم")
        x["st_lbl"], x["st_cls"] = _BOOK_STATUS.get(x.get("status"), ("—", "muted"))
        x["here"] = x.get("mode") == _mode()
    # البرامج القابلة للنشر في هذا النظام
    cfg = _public_cfg(settings)
    if _mode() == app_mode.UMRAH:
        from hajj_app import umrah
        options = [(t.code, f"{t.code} — {t.name}" if t.name else t.code, t.depart_date)
                   for t in umrah.load_trips(settings)]
    else:
        from hajj_app import programs as hp
        options = [(nm, nm, pr.travel_date) for nm, pr in
                   zip(hp.PROGRAM_NAMES, hp.load_programs(settings))]
    msg, err = session.pop("acc_msg", None), session.pop("acc_err", None)
    return render_template("bookings.html", active="bookings", items=items, show=show,
                           counts=counts, cfg=cfg, options=options, msg=msg, err=err,
                           public_url=url_for("public_trips", _external=True),
                           wa_default=_PUB_WA_DEFAULT,
                           other_mode_new=sum(1 for x in _book_load()
                                              if x.get("status") == "new" and x.get("mode") != _mode()),
                           **_ctx())


@app.post("/bookings/<bid>/delete")
def booking_delete(bid):
    """حذف طلب حجز نهائياً — للمدير حصراً (المحرّر يؤرشف فقط)."""
    s, bad = _backup_admin()
    if bad:
        return bad
    with _BOOK_LOCK:
        items = _book_load()
        it = next((x for x in items if x.get("id") == bid), None)
        if it is not None:
            _book_save([x for x in items if x.get("id") != bid])
    if it is not None:
        _audit("حذف طلب حجز", f"{it.get('name', '')} — {it.get('prog', '')}")
        session["acc_msg"] = f"حُذف طلب «{it.get('name', '')}» نهائياً."
    return redirect(url_for("bookings", show=request.args.get("show", "open")))


@app.post("/bookings/<bid>/<action>")
def booking_action(bid, action):
    """تغيير حالة طلب: تم التواصل / أرشفة / إعادة فتح / تحويل إلى سجلّ."""
    s = _sess()
    if s is None:
        return redirect(url_for("login"))
    if not s.can_edit or action not in ("contacted", "rejected", "new", "convert"):
        return redirect(url_for("bookings"))
    with _BOOK_LOCK:
        items = _book_load()
        it = next((x for x in items if x.get("id") == bid), None)
        if it is None:
            return redirect(url_for("bookings"))
        if action != "convert":
            it["status"] = action
            it["by"] = s.username
            _book_save(items)
            return redirect(url_for("bookings", show=request.args.get("show", "open")))
        if it.get("mode") != _mode():
            session["acc_err"] = ("هذا الطلب لنظام " + app_mode.theme(it.get("mode"))["noun"]
                                  + " — بدّل النظام ثم حوّله.")
            return redirect(url_for("bookings"))
        if it.get("status") == "converted":
            return redirect(url_for("bookings"))
        import uuid
        from hajj_app.mrz import PassportData
        rec = PassportData(full_name_ar=it.get("name", ""), phone=it.get("phone", ""),
                           source_file="طلب حجز من الموقع", uid=uuid.uuid4().hex,
                           notes=(f"طلب حجز {it.get('count', 1)} أشخاص" if int(it.get("count") or 1) > 1
                                  else "طلب حجز") + (f" — {it['note']}" if it.get("note") else ""))
        if _mode() == app_mode.UMRAH:
            rec.trip = it.get("key", "")
            if it.get("room"):
                rec.room_type = it["room"]
            _umrah_fill_price(rec)
        else:
            rec.program = it.get("key", "")
        with _UID_LOCK:
            records = _load_records()
            records.append(rec)
            storage.save_records(records, session=s)
        it["status"], it["by"], it["uid"] = "converted", s.username, rec.uid
        _book_save(items)
    _audit("تحويل طلب حجز إلى سجلّ", it.get("name", ""))
    idx = len(records) - 1
    return redirect(url_for("hujjaj_edit", idx=idx, fp=_rec_token(rec)))


# ==================== تسجيل الحضور بالمسح (المطار/الفندق/الباص/العودة) ====
_CHECK_STAGES = ("المطار", "الفندق", "الباص", "العودة")
_CHECK_RE = re.compile(r"^MSTF-(hajj|umrah)-([\w-]{3,64})$")


def _checkin_code(mode: str, uid: str) -> str:
    """رمز الحضور الشخصي (في QR صفحة «رحلتي»): الوضع + المعرّف الثابت — لا بيانات."""
    return f"MSTF-{mode}-{uid}" if uid else ""


def _qr_svg(data: str, px: int = 6) -> str:
    """رمز QR كـ SVG مضغوط (مسار واحد) — يُرسم على الخادم بلا مكتبات خارجية."""
    from reportlab.graphics.barcode import qrencoder
    q = qrencoder.QRCode(None, qrencoder.QRErrorCorrectLevel.M)
    q.addData(data)
    q.make()
    n = q.getModuleCount()
    path = "".join(f"M{c + 4},{r + 4}h1v1h-1z" for r in range(n) for c in range(n)
                   if q.isDark(r, c))
    size = n + 8
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" '
            f'width="{size * px}" height="{size * px}" shape-rendering="crispEdges" '
            f'role="img" aria-label="رمز الحضور"><rect width="{size}" height="{size}" fill="#fff"/>'
            f'<path d="{path}" fill="#111"/></svg>')


def _checkin_find(records, code: str):
    """يعيد (الموضع، رسالة خطأ) لنصّ ممسوح: رمز «رحلتي»، أو رقم الجواز/المرجع، أو
    نصّ بطاقة قديمة فيه «الجواز: …»."""
    t = str(code or "").strip()
    if not t:
        return None, "لم يُقرأ شيء"
    m = _CHECK_RE.match(t)
    if m:
        if m.group(1) != _mode():
            return None, ("هذا رمز نظام " + app_mode.theme(m.group(1))["noun"]
                          + " — بدّل النظام أولاً")
        uid = m.group(2)
        j = next((i for i, r in enumerate(records)
                  if str(getattr(r, "uid", "") or "") == uid), None)
        return (j, None) if j is not None else (None, "الرمز لا يطابق أي سجلّ (حُذف؟)")
    m = re.search(r"الجواز[:\s]+([A-Za-z0-9]+)", t)
    key = (m.group(1) if m else t).strip().upper()
    for i, r in enumerate(records):
        if str(r.passport_number or "").strip().upper() == key \
                or str(r.reference_number or "").strip().upper() == key:
            return i, None
    return None, f"لم يُعثر على «{t[:40]}»"


def _checkin_scope(records, grp: str) -> list:
    """من يُنتظر حضورهم: سجلّات البرنامج المختار (أو الكل) عدا الملغاة."""
    gattr = _group_attr()
    return [(i, r) for i, r in enumerate(records)
            if str(getattr(r, "status", "") or "").strip() != "ملغى"
            and (not grp or str(getattr(r, gattr, "") or "") == grp)]


def _checkin_groups(records) -> list:
    if _mode() == app_mode.UMRAH:
        from hajj_app import umrah
        return [(t.code, f"{t.code} — {t.name}" if t.name else t.code)
                for t in umrah.load_trips(storage.load_settings())]
    from hajj_app import programs as hp
    used = {str(r.program or "") for r in records}
    return [(n, n) for n in hp.PROGRAM_NAMES if n in used]


@app.get("/checkin")
def checkin_page():
    """تسجيل الحضور: مسح رمز «رحلتي» أو الجواز بكاميرا الجوال، أو الضغط على الاسم."""
    s = _sess()
    if s is None:
        return redirect(url_for("login"))
    stage = request.args.get("stage") or _CHECK_STAGES[0]
    if stage not in _CHECK_STAGES:
        stage = _CHECK_STAGES[0]
    records = _load_records()
    groups = _checkin_groups(records)
    grp = (request.args.get("grp") or "").strip()
    if grp and grp not in [g for g, _l in groups]:
        grp = ""
    people = []
    for i, r in _checkin_scope(records, grp):
        name = r.full_name_ar or r.full_name_en or r.passport_number or "—"
        ck = r.checkins if isinstance(r.checkins, dict) else {}
        people.append({"idx": i, "fp": _rec_token(r), "name": name,
                       "init": (name.split() or ["؟"])[0][:1], "tone": sum(map(ord, name)) % 6,
                       "phone": str(r.phone or ""), "passport": str(r.passport_number or ""),
                       "time": str(ck.get(stage, "") or "")[-5:],
                       "tel": re.sub(r"[^\d+]", "", str(r.phone or ""))})
    present = sum(1 for p in people if p["time"])
    return render_template("checkin.html", active="checkin", stages=_CHECK_STAGES,
                           stage=stage, groups=groups, grp=grp, people=people,
                           grp_label=dict(groups).get(grp, grp),
                           present=present, total=len(people), **_ctx())


@app.post("/checkin/mark")
def checkin_mark():
    """يسجّل حضور شخص (أو يلغيه) في مرحلة — من مسح رمز أو من الضغط على اسمه."""
    s = _sess()
    if s is None:
        return {"ok": False, "msg": "انتهت الجلسة — ادخل من جديد"}, 401
    if not s.can_edit:
        return {"ok": False, "msg": "صلاحيتك اطّلاع فقط"}, 403
    data = request.get_json(silent=True) or {}
    stage = str(data.get("stage") or "")
    if stage not in _CHECK_STAGES:
        return {"ok": False, "msg": "مرحلة غير معروفة"}, 400
    grp = str(data.get("grp") or "").strip()
    undo = bool(data.get("undo"))
    with _UID_LOCK:
        records = _load_records()
        if data.get("code"):
            j, err = _checkin_find(records, str(data.get("code"))[:200])
        else:
            try:
                j = _resolve_idx(records, int(data.get("idx")), str(data.get("fp") or ""))
            except (TypeError, ValueError):
                j = None
            err = None if j is not None else "تغيّر الكشف — حدّث الصفحة"
        if j is None:
            return {"ok": False, "msg": err}
        rec = records[j]
        name = rec.full_name_ar or rec.full_name_en or rec.passport_number or "—"
        gval = str(getattr(rec, _group_attr(), "") or "")
        if grp and gval != grp:
            return {"ok": False, "msg": f"{name} ليس في هذا البرنامج ({gval or 'بلا برنامج'})",
                    "name": name}
        if not isinstance(rec.checkins, dict):
            rec.checkins = {}
        already = stage in rec.checkins
        if undo:
            rec.checkins.pop(stage, None)
        elif not already:
            rec.checkins[stage] = datetime.now(_UAE).strftime("%Y-%m-%d %H:%M")
        if undo or not already:
            storage.save_records(records, session=s)
            if undo:
                _audit("إلغاء تسجيل حضور", f"{name} — {stage}")
        scope = _checkin_scope(records, grp)
        present = sum(1 for _i, r in scope if stage in (r.checkins or {}))
    return {"ok": True, "name": name, "already": already and not undo, "undo": undo,
            "time": str(rec.checkins.get(stage, "") or "")[-5:], "idx": j,
            "fp": _rec_token(rec), "present": present, "total": len(scope)}


@app.get("/checkin/report.pdf")
def checkin_report():
    """تقرير الحضور (PDF): كل شخص × كل مرحلة، للبرنامج المختار أو الكل."""
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app import pdf_io
    records = _load_records()
    grp = (request.args.get("grp") or "").strip()
    recs = [r for _i, r in _checkin_scope(records, grp)]
    title = "تقرير الحضور" + (f" — {grp}" if grp else "")
    return _pdf_response(
        lambda p: pdf_io.export_attendance_pdf(recs, p, stages=list(_CHECK_STAGES),
                                               season=_season(), title=title),
        "attendance.pdf")


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
        public.person_token(_mode(), uid, _person_info(rec), rotate=(action == "rotate"))
        _audit("رابط معتمر" + (" (تجديد)" if action == "rotate" else ""), name)
    return redirect(url_for("record_docs", idx=j, fp=_rec_token(rec)))


def _cal_weeks(trips, first, today) -> tuple:
    """أسابيع الشهر مع أشرطة الرحلات: كل رحلة شريط ممتدّ من المغادرة إلى العودة،
    يُقسَم على الأسابيع، ويأخذ «مساراً» لا يتداخل مع غيره في الأسبوع نفسه.
    يعيد (الأسابيع، رحلات الشهر مرتّبة للقائمة أسفل التقويم)."""
    import calendar as _cal
    spans = []
    for t in trips:
        start = t["depart"] or t["ret"]
        end = t["ret"] or t["depart"]
        if not start:
            continue
        if end < start:
            end = start
        spans.append((start, end, t))
    weeks = []
    for wk in _cal.Calendar(firstweekday=5).monthdatescalendar(first.year, first.month):
        ws, we = wk[0], wk[-1]
        lanes, bars = [], []
        for start, end, t in sorted((x for x in spans if x[0] <= we and x[1] >= ws),
                                    key=lambda x: (x[0], -(x[1] - x[0]).days)):
            c0, c1 = max((start - ws).days, 0), min((end - ws).days, 6)
            lane = next((i for i, last in enumerate(lanes) if last < c0), None)
            if lane is None:
                lanes.append(c1)
                lane = len(lanes) - 1
            else:
                lanes[lane] = c1
            bars.append({**{k: t[k] for k in ("label", "n", "color", "fg", "link", "sub")},
                         "col": c0 + 1, "span": c1 - c0 + 1, "row": lane + 2,
                         "head": start >= ws, "tail": end <= we,
                         "dep": bool(t["depart"]) and ws <= t["depart"] <= we,
                         "ret": bool(t["ret"]) and t["ret"] != t["depart"]
                         and ws <= t["ret"] <= we})
        weeks.append({"days": [{"day": d.day, "out": d.month != first.month,
                                "today": d == today, "fri": d.weekday() == 4} for d in wk],
                      "bars": bars, "lanes": len(lanes)})
    last = (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    agenda = []
    for start, end, t in sorted(spans, key=lambda x: x[0]):
        if start <= last and end >= first:
            nights = (end - start).days
            agenda.append({**t, "from": _day_txt(start, today), "to": _day_txt(end, today),
                           "nights": _nights_txt(nights), "one": start == end,
                           "now": start <= today <= end})
    return weeks, agenda


@app.get("/calendar")
def calendar_page():
    """تقويم الرحلات: كل برنامج شريط ممتدّ من المغادرة إلى العودة بلونه، وقائمة
    رحلات الشهر أسفله."""
    if _sess() is None:
        return redirect(url_for("login"))
    from datetime import date as _date
    today = _date.today()
    try:
        y, m = (int(x) for x in (request.args.get("m") or "").split("-")[:2])
        first = _date(y, m, 1)
    except (ValueError, TypeError):
        first = today.replace(day=1)
    settings = storage.load_settings()
    records = _load_records()
    weeks, agenda = _cal_weeks(_trip_list(records, settings), first, today)
    prev = (first.replace(day=1) - timedelta(days=1)).replace(day=1)
    nxt = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    return render_template(
        "calendar.html", active="calendar", weeks=weeks, agenda=agenda,
        title=f"{_AR_MONTHS[first.month - 1]} {first.year}",
        prev=prev.strftime("%Y-%m"), next=nxt.strftime("%Y-%m"),
        this=today.strftime("%Y-%m"), is_this=(first == today.replace(day=1)),
        total=len(agenda), **_ctx())


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
    for g in groups:
        g["icon"] = next((ic for pre, ic in _GROUP_ICONS if g["title"].startswith(pre)),
                         "file-text")
    return render_template(
        "hujjaj_edit.html", active="hujjaj", groups=groups, saved=saved,
        has_docs=has_docs, prof=_profile(rec, idx) if idx is not None else None,
        is_new=is_new, idx=idx, room_prices=room_prices,
        fp=_rec_token(rec) if idx is not None else "",
        svc_total=umrah.record_services_total(rec),   # خدمات المعتمر
        cur_trip=str(getattr(rec, "trip", "") or ""),
        room_names=[n for _k, n, _c in umrah.ROOM_TYPES],
        name=getattr(rec, "full_name_ar", "") or getattr(
            rec, "full_name_en", "") or "",
        number=getattr(rec, "reference_number", "") or "",
        noun_singular=_noun_singular(), **_ctx())


def _profile(rec, idx) -> dict:
    """بيانات رأس «الملف الشخصي» في صفحة السجلّ: الاسم والصورة والشارات،
    جاهزية السفر (البيانات الناقصة)، حالة السداد، والروابط السريعة."""
    from webapp import alerts, public
    from hajj_app import images as imgmod
    from hajj_app.fields import format_amount
    mode = _mode()
    name = rec.full_name_ar or rec.full_name_en or ""
    parts = name.split()
    initials = (parts[0][:1] + (parts[-1][:1] if len(parts) > 1 else "")) if parts else "؟"
    needs = alerts._NEEDS_HAJJ if mode == app_mode.HAJJ else alerts._NEEDS
    missing = alerts.missing_fields(rec, mode)
    miss_keys = [k for k, _l in needs if not str(getattr(rec, k, "") or "").strip()]
    ready = round(100 * (len(needs) - len(missing)) / len(needs)) if needs else 100
    iid = getattr(rec, "image_id", "") or ""
    has_img = bool(iid) and any(imgmod.has_image(iid, k) for k in
                                (imgmod.PHOTO, imgmod.PASSPORT, imgmod.ID_CARD))
    gval = str(getattr(rec, _group_attr(), "") or "")
    chips = []
    if gval:
        lbl = gval
        if mode == app_mode.UMRAH:
            from hajj_app import umrah
            t = next((x for x in umrah.load_trips(storage.load_settings())
                      if x.code == gval), None)
            lbl = f"{t.code} — {t.name}" if t and t.name else gval
        chips.append(("briefcase", lbl, False))
    if rec.reference_number:
        chips.append(("tag", rec.reference_number, True))
    if rec.passport_number:
        chips.append(("id-card", rec.passport_number, True))
    if rec.nationality_ar:
        chips.append(("globe", rec.nationality_ar, False))
    status = str(rec.status or "").strip()
    pay = _pay_state(rec)
    total = stats._amount(rec.program_value)
    paid = stats._amount(rec.paid_amount)
    pct = max(0, min(100, round(100 * paid / total))) if total > 0 else 0
    from hajj_app import whatsapp as _wa
    tok = public.find_person(mode, getattr(rec, "uid", "") or "")
    fp = _rec_token(rec)
    wa = None
    if rec.phone:
        try:
            wa = _wa.wa_link(rec.phone, f"السلام عليكم {(parts or [''])[0]}",
                             str(storage.load_settings().get("whatsapp_cc") or "971"))
        except Exception:                          # noqa: BLE001
            wa = None
    return {
        "initials": initials, "name_ar": rec.full_name_ar, "name_en": rec.full_name_en,
        "chips": chips, "status": status,
        "status_cls": {"ملغى": "crit", "قائمة انتظار": "warn"}.get(status, "good"),
        "has_img": has_img,
        "avatar": url_for("record_avatar", idx=idx, fp=fp) if has_img else "",
        "ready": ready, "missing": missing, "miss_keys": miss_keys, "ring": round(ready * 1.0053, 2),
        "pay": pay, "pay_lbl": _PAY_STATES[pay][0] if pay else "",
        "pay_cls": _PAY_STATES[pay][1] if pay else "",
        "pay_ic": _PAY_STATES[pay][2] if pay else "",
        "total": format_amount(total) if total else "", "paid": format_amount(paid),
        "remaining": format_amount(max(0.0, remaining_amount(rec))), "pct": pct,
        "plink": url_for("person_page", token=tok) if tok else "",
        "wa": wa,
    }


@app.get("/hujjaj/<int:idx>/avatar.jpg")
def record_avatar(idx):
    """صورة السجلّ المصغّرة لرأس صفحته: الصورة الشخصية المرفوعة، وإلّا الوجه
    مقتصّاً من الجواز/الهوية. لا تُخزَّن مفكوكة على الخادم."""
    if _sess() is None:
        return ("", 401)
    from hajj_app import images as imgmod
    records = _load_records()
    j = _resolve_idx(records, idx, request.args.get("fp", ""))
    if j is None:
        return ("", 404)
    iid = getattr(records[j], "image_id", "") or ""
    if not iid:
        return ("", 404)
    import io
    out = None
    try:
        blob = imgmod.load_image(iid, imgmod.PHOTO, _sess())
        if blob:
            pil = imgmod.to_pil_image(blob)
            if pil is not None:
                w, h = pil.size
                side = min(w, h)
                top = max(0, int((h - side) * 0.2))
                pil = pil.convert("RGB").crop(((w - side) // 2, top,
                                               (w - side) // 2 + side, top + side))
                pil.thumbnail((256, 256))
                bio = io.BytesIO()
                pil.save(bio, format="JPEG", quality=86)
                out = bio.getvalue()
        if out is None:
            for kind in (imgmod.PASSPORT, imgmod.ID_CARD):
                blob = imgmod.load_image(iid, kind, _sess())
                face = imgmod.face_crop(blob, target_aspect=1.0) if blob else None
                if face:
                    pil = imgmod.to_pil_image(face)
                    if pil is not None:
                        pil = pil.convert("RGB")
                        pil.thumbnail((256, 256))
                        bio = io.BytesIO()
                        pil.save(bio, format="JPEG", quality=86)
                        out = bio.getvalue()
                        break
    except Exception:                              # noqa: BLE001
        out = None
    if not out:
        return ("", 404)
    resp = send_file(io.BytesIO(out), mimetype="image/jpeg", download_name="avatar.jpg")
    resp.headers["Cache-Control"] = "private, max-age=600"
    return resp


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
    if tok and getattr(rec, "uid", ""):        # حدّث بيانات الرابط (البرنامج/الغرفة/المجموعة)
        try:
            if any(public.get_person(tok).get(k) != v for k, v in _person_info(rec).items()):
                public.person_token(_mode(), rec.uid, _person_info(rec))
        except Exception:                          # noqa: BLE001
            pass
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
    import hashlib as _h
    import json as _json
    records = _load_records()
    co = storage.load_settings().get("company") or {}
    tv = _h.sha1((_BUILD_TAG + _json.dumps(co, sort_keys=True, ensure_ascii=False))
                 .encode("utf-8")).hexdigest()[:8]
    return render_template("reports.html", active="reports",
                           count=len(records), tv=tv, **_ctx())


# ---- معاينات التقارير: الصفحة الأولى من كل تقرير مولّدة ببيانات تجريبية ----
_THUMB_CACHE: dict = {}
_THUMB_LOCK = threading.Lock()
_THUMB_KINDS = ("pilgrims", "financial", "airline", "cards", "stickers", "transport",
                "itinerary", "receipt", "invoice", "contract")


def _demo_records() -> list:
    """سجلّات تجريبية لمعاينة شكل التقارير — لا بيانات حقيقية فيها."""
    from hajj_app.mrz import PassportData
    names = (("أحمد محمد العلي", "AHMED MOHAMMED ALALI", "ذكر"),
             ("فاطمة حسن الكعبي", "FATIMA HASSAN ALKAABI", "أنثى"),
             ("علي عبدالله الشامسي", "ALI ABDULLA ALSHAMSI", "ذكر"),
             ("مريم سعيد النعيمي", "MARIAM SAEED ALNUAIMI", "أنثى"),
             ("خالد يوسف المري", "KHALID YOUSEF ALMARRI", "ذكر"),
             ("نورة راشد الظاهري", "NOURA RASHED ALDHAHERI", "أنثى"),
             ("حسين جعفر الموسوي", "HUSSAIN JAAFAR ALMUSAWI", "ذكر"),
             ("سارة أحمد المهيري", "SARA AHMED ALMUHAIRI", "أنثى"))
    out = []
    for i, (ar, en, sex) in enumerate(names):
        out.append(PassportData(
            full_name_ar=ar, full_name_en=en, sex=sex, nationality_ar="الإمارات",
            passport_number=f"N{7654321 + i * 1111}", birth_date=f"19{70 + i * 3}-0{1 + i % 9}-1{i}",
            expiry_date="2031-05-20", phone=f"05012345{i:02d}", family_number=str(10 + i // 2),
            reference_number=f"R-{100 + i}", hotel="فندق مكة", room_type="رباعي 1" if i < 4 else "رباعي 2",
            room_number="", airline="الإماراتية", flight_number="EK 815", trip="U1", program="البرنامج الأول",
            arrival_date="2026-12-01", departure_date="2026-12-10", transport="GMC", vehicle="GMC 1",
            program_value="6500", paid_amount=("6500" if i % 3 == 0 else "3000" if i % 3 == 1 else "0")))
    return out


def _report_thumb(kind: str) -> bytes | None:
    """صورة PNG للصفحة الأولى من التقرير بالبيانات التجريبية (تُحفظ في الذاكرة)."""
    import json as _json
    from hajj_app import pdf_io
    settings = storage.load_settings()
    co = settings.get("company") if isinstance(settings.get("company"), dict) else {}
    key = (kind, _mode(), _BUILD_TAG, _json.dumps(co, sort_keys=True, ensure_ascii=False))
    if key in _THUMB_CACHE:
        return _THUMB_CACHE[key]
    with _THUMB_LOCK:
        if key in _THUMB_CACHE:
            return _THUMB_CACHE[key]
        recs = _demo_records()
        umrah_mode = _mode() == app_mode.UMRAH
        c = pdf_io.company_info(co)
        path = _tmp(".pdf")
        try:
            if kind == "pilgrims":
                if umrah_mode:
                    pdf_io.export_umrah_pdf(recs, path, program_name="")
                else:
                    pdf_io.export_pdf(recs, path, title="كشف الحجّاج")
            elif kind == "financial":
                pdf_io.export_stats_pdf(recs, path)
            elif kind == "airline":
                pdf_io.export_airline_pdf(recs, path)
            elif kind == "cards":
                if umrah_mode:
                    pdf_io.export_umrah_cards_pdf(recs, path, company=co, session=_sess())
                else:
                    pdf_io.export_badges_pdf(recs, path, company=c["name_ar"],
                                             session=_sess(), back=_load_badge_back())
            elif kind == "stickers":
                pdf_io.export_stickers_pdf(recs, path, kind="bag", company=c["name_ar"],
                                           season=str(settings.get("season_year", "") or ""))
            elif kind == "transport":
                pdf_io.export_umrah_transport_pdf(recs, path)
            elif kind == "itinerary":
                demo = [["الأول", "01/12", "الوصول والإحرام من الميقات", "الميقات", "الالتزام بالمواعيد"],
                        ["الأول", "01/12", "أداء العمرة (الطواف والسعي)", "المسجد الحرام", "مع المرشد"],
                        ["الثاني", "02/12", "زيارة المعالم", "مكة المكرمة", ""],
                        ["الخامس", "05/12", "التوجّه إلى المدينة المنورة", "قطار الحرمين", "الحقائب 7:00 ص"],
                        ["السادس", "06/12", "زيارة المسجد النبوي", "المدينة المنورة", ""],
                        ["التاسع", "09/12", "العودة", "المطار", "قبل الإقلاع بـ 3 ساعات"]]
                pdf_io.export_itinerary_pdf(path, rows=[list(r) for r in settings.get("itinerary", [])] or demo)
            elif kind in ("receipt", "invoice", "contract"):
                _doc_export(kind, recs[0], co, None, path)
            else:
                return None
            import fitz
            doc = fitz.open(path)
            page = doc[0]
            zoom = 460 / max(page.rect.width, 1)
            png = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False).tobytes("png")
            doc.close()
        except Exception:                          # noqa: BLE001
            png = None
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
        if len(_THUMB_CACHE) > 60:
            _THUMB_CACHE.clear()
        _THUMB_CACHE[key] = png
        return png


@app.get("/reports/preview/<kind>.png")
def report_preview(kind):
    """معاينة مصغّرة لشكل التقرير (ببيانات تجريبية) لبطاقات صفحة التقارير."""
    if _sess() is None:
        return ("", 401)
    if kind not in _THUMB_KINDS:
        return ("", 404)
    png = _report_thumb(kind)
    if not png:
        return ("", 404)
    import io
    resp = send_file(io.BytesIO(png), mimetype="image/png", download_name=f"{kind}.png")
    resp.headers["Cache-Control"] = "private, max-age=3600"
    return resp


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


def _prog_card_info(t, n: int, cap: int) -> dict:
    """بيانات بطاقة البرنامج: التواريخ بالعربية، الليالي، امتلاء المقاعد، والحالة
    (بعد كم يوماً / جارية / انتهت)."""
    from webapp.alerts import _d
    today = datetime.now(_UAE).date()
    d0, d1 = _d(t.depart_date), _d(t.return_date)
    out = {"dep_txt": _day_txt(d0, today) if d0 else "—",
           "ret_txt": _day_txt(d1, today) if d1 else "—",
           "nights_txt": _nights_txt((d1 - d0).days) if d0 and d1 and d1 > d0 else "",
           "pct": min(100, round(100 * n / cap)) if cap else 0,
           "when": "", "when_cls": ""}
    if d0 and today < d0:
        k = (d0 - today).days
        out["when"] = "غداً" if k == 1 else f"بعد {k} {_days_unit(k)}"
        out["when_cls"] = "soon" if k <= 14 else ""
    elif d0 and today <= (d1 or d0):
        out["when"], out["when_cls"] = "جارية الآن", "live"
    elif d0:
        out["when"], out["when_cls"] = "انتهت", "past"
    return out


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
                     "over": bool(cap and n > cap), "full": bool(cap and n == cap),
                     **_prog_card_info(t, n, cap)})
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
    _update_public_seats(settings, _seat_counts(records, settings))
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
    if remove and not _sess().is_admin:          # الإخراج من الباقة للمدير فقط
        return redirect(url_for("programs", package=name))
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
    if not _sess().is_admin and (old is not None or any(t.code == trip.code for t in trips)):
        return redirect(url_for("programs", msg="تعديل البرامج للمدير فقط."))
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
    if _sess().is_admin:                           # الحذف للمدير فقط
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
        pdf_io.export_receipt_pdf(rec, path, company=c,
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
            rec, rp, season=season, company=company,
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
    board, loose = _room_board(records, rooms_raw, unplaced)
    return render_template("occupancy.html", active="occupancy", rows=rows,
                           summary=summary, pools=_occupancy_pools(records),
                           board=board, loose=loose,
                           saved=request.args.get("saved"),
                           skipped=request.args.get("skipped"), **_ctx())


def _room_board(records, rooms_raw, unplaced) -> tuple:
    """لوحة الغرف المرئية: الفنادق ← أنواع الغرف ← الغرف وسكّانها (أسرّة).
    كل ساكن يحمل موضعه ورمز سجلّه كي يُحفظ نقله عبر نموذج التسكين نفسه."""
    from hajj_app.rooming import common_room_type, room_category
    pos = {id(r): i for i, r in enumerate(records)}

    def person(r):
        name = r.full_name_ar or r.full_name_en or "—"
        parts = name.split()
        return {"idx": pos[id(r)], "fp": _rec_token(r), "name": name,
                "short": " ".join(parts[:2]) if parts else "—",
                "init": (parts[0][:1] if parts else "؟"),
                "fam": str(r.family_number or "").strip(), "sex": str(r.sex or "").strip(),
                "rt": str(r.room_type or "").strip(), "tone": sum(map(ord, name)) % 6}
    hotels: dict = {}
    for hotel, cap, number, occ in rooms_raw:
        n = len(occ)
        size = cap or n
        rtype = common_room_type(occ)
        people = [person(r) for r in occ]
        fams = {p["fam"] or "—" for p in people}
        sexes = {p["sex"] for p in people if p["sex"]}
        room = {"hotel": hotel, "cap": size, "number": number, "rtype": rtype,
                "people": people, "free": max(0, size - n),
                "state": "over" if n > size else "full" if n == size else "part",
                "mixed": len(fams) > 1 and len(sexes) > 1}
        h = hotels.setdefault(hotel, {"name": hotel or "", "types": {}, "rooms": 0, "beds": 0, "used": 0})
        t = h["types"].setdefault(size, {"cap": size, "label": room_category(rtype) or rtype or f"سعة {size}",
                                         "rooms": []})
        t["rooms"].append(room)
        h["rooms"] += 1
        h["beds"] += size
        h["used"] += n
    board = []
    for name in sorted(hotels, key=lambda x: (x == "", x)):
        h = hotels[name]
        h["types"] = [h["types"][k] for k in sorted(h["types"])]
        board.append(h)
    return board, [person(r) for r in unplaced]


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
            _audit("تعديل التسكين يدوياً" if request.form.get("back") != "board"
                   else "نقل بين الغرف (لوحة الغرف)", f"{n} سجلّ")
        except Exception:
            pass
        if request.form.get("back") == "board":
            return redirect(url_for("occupancy", saved=n, skipped=skipped) + "#board")
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
# ==================== حملة التحصيل بالواتساب ===============================
_REMIND_TPL = ("السلام عليكم {الاسم}،\n"
               "نذكّركم بالمبلغ المتبقّي {المتبقّي} درهم لبرنامج {البرنامج}"
               " (المغادرة {المغادرة}).\n"
               "نرجو إتمام السداد قبل السفر، ونحن في خدمتكم لأي استفسار.\n"
               "{الرابط}\n"
               "مع تحيات المصطفى للحج والعمرة.")
_REMIND_KEYS = ("{الاسم}", "{المتبقّي}", "{البرنامج}", "{المغادرة}", "{الرابط}")


def _trip_departures(settings) -> dict:
    """تاريخ مغادرة كل برنامج واسمه: {الرمز/الاسم: (التاريخ، الاسم المعروض)}."""
    from webapp.alerts import _d
    out = {}
    if _mode() == app_mode.UMRAH:
        from hajj_app import umrah
        for t in umrah.load_trips(settings):
            out[t.code] = (_d(t.depart_date), f"{t.code} {t.name}".strip())
    else:
        from hajj_app import programs as hp
        for nm, pr in zip(hp.PROGRAM_NAMES, hp.load_programs(settings)):
            out[nm] = (_d(pr.travel_date), nm)
    return out


def _remind_text(tpl: str, rec, prog: str, dep_txt: str, link: str) -> str:
    name = " ".join((rec.full_name_ar or rec.full_name_en or "").split()[:2])
    vals = {"{الاسم}": name, "{المتبقّي}": format_amount(max(0.0, remaining_amount(rec))) or "0",
            "{البرنامج}": prog or "", "{المغادرة}": dep_txt or "—", "{الرابط}": link}
    out = str(tpl or "")
    for k, v in vals.items():
        out = out.replace(k, v)
    out = re.sub(r"[ \t]*\(المغادرة —\)", "", out)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(ln.rstrip() for ln in out.split("\n"))).strip()


@app.route("/finance/remind", methods=["GET", "POST"])
def finance_remind():
    """حملة التحصيل: من عليه مبلغ متبقٍّ مرتّباً بقرب مغادرته، وبجانب كلٍّ زرّ واتساب
    برسالة جاهزة باسمه ومبلغه ورابط «رحلتي» — ويُعلَّم «ذُكّر» عند الضغط."""
    s = _sess()
    if s is None:
        return redirect(url_for("login"))
    settings = storage.load_settings()
    if request.method == "POST":                     # حفظ نصّ الرسالة (زرّ صريح)
        if not s.can_edit:
            return redirect(url_for("finance_remind"))
        if request.form.get("reset"):
            settings.pop("remind_tpl", None)
            msg = "أُعيد النصّ الافتراضي."
        else:
            tpl = (request.form.get("tpl") or "").strip()[:1200]
            if not tpl:
                session["acc_err"] = "اكتب نصّ الرسالة."
                return redirect(url_for("finance_remind", **request.args))
            settings["remind_tpl"] = tpl
            msg = "حُفظ نصّ رسالة التذكير."
        storage.save_settings(settings)
        _audit("تعديل رسالة تذكير التحصيل", "")
        session["acc_msg"] = msg
        return redirect(url_for("finance_remind", **request.args))
    from webapp import public
    from hajj_app import whatsapp as _wa
    from hajj_app.mrz import PassportData as _PD
    tpl = str(settings.get("remind_tpl") or _REMIND_TPL)
    cc = str(settings.get("whatsapp_cc") or "971")
    deps = _trip_departures(settings)
    reminded = settings.get("reminders") if isinstance(settings.get("reminders"), dict) else {}
    today = datetime.now(_UAE).date()
    within = request.args.get("within", "30")
    if within not in ("7", "14", "30", "all"):
        within = "30"
    grp = (request.args.get("grp") or "").strip()
    fresh = request.args.get("fresh") == "1"
    gattr = _group_attr()
    rows, total = [], 0.0
    for i, r in enumerate(_load_records()):
        left = remaining_amount(r)
        if left <= 0.005 or str(r.status or "").strip() == "ملغى":
            continue
        g = str(getattr(r, gattr, "") or "")
        if grp and g != grp:
            continue
        dep, prog = deps.get(g, (None, g))
        days = (dep - today).days if dep else None
        if days is not None and days < -1:
            continue                                   # سافر وعاد — يُتابع من المالية
        if within != "all" and (days is None or days > int(within)):
            continue
        uid = str(getattr(r, "uid", "") or "")
        last = str(reminded.get(uid, "") or "")
        ago = None
        if last:
            try:
                ago = (today - datetime.fromisoformat(last).date()).days
            except ValueError:
                ago = None
        if fresh and ago is not None and ago < 3:
            continue
        tok = public.find_person(_mode(), uid) if uid else None
        link = url_for("person_page", token=tok, _external=True) if tok else ""
        dep_txt = _day_txt(dep, today) if dep else ""
        text = _remind_text(tpl, r, prog, dep_txt, link)
        total_v = stats._amount(r.program_value)
        rows.append({
            "idx": i, "uid": uid, "name": r.full_name_ar or r.full_name_en or "—",
            "prog": prog or "—", "days": days, "dep_txt": dep_txt,
            "when": ("اليوم" if days == 0 else "غداً" if days == 1 else
                     f"بعد {days} {_days_unit(days)}" if days and days > 1 else
                     "سافر" if days is not None and days < 0 else "بلا تاريخ"),
            "urgent": days is not None and days <= 7,
            "left": format_amount(left), "left_v": left,
            "pct": max(0, min(100, round(100 * (total_v - left) / total_v))) if total_v > 0 else 0,
            "phone": str(r.phone or ""), "wa": _wa.wa_link(r.phone, text, cc) if r.phone else None,
            "ago": ago, "has_link": bool(tok)})
        total += left
    rows.sort(key=lambda x: (x["days"] is None, x["days"] if x["days"] is not None else 0,
                             -x["left_v"]))
    msg, err = session.pop("acc_msg", None), session.pop("acc_err", None)
    return render_template(
        "remind.html", active="remind", rows=rows, total=format_amount(total),
        groups=_checkin_groups(_load_records()), grp=grp, within=within, fresh=fresh,
        tpl=tpl, keys=_REMIND_KEYS, is_default=tpl == _REMIND_TPL,
        done_today=sum(1 for x in rows if x["ago"] == 0), msg=msg, err=err,
        sample=_remind_text(tpl, _PD(full_name_ar="أحمد محمد", program_value="6500",
                                     paid_amount="4000"), "عمرة رجب", "1 ديسمبر",
                            "https://…/p/…"), **_ctx())


@app.post("/finance/remind/mark")
def finance_remind_mark():
    """يعلّم أن الشخص ذُكّر اليوم (يُستدعى عند ضغط زرّ واتساب)."""
    s = _sess()
    if s is None:
        return {"ok": False}, 401
    if not s.can_edit:
        return {"ok": False}, 403
    uid = str((request.get_json(silent=True) or {}).get("uid") or "")[:80]
    if not uid:
        return {"ok": False}, 400
    with _UID_LOCK:
        settings = storage.load_settings()
        rem = settings.get("reminders") if isinstance(settings.get("reminders"), dict) else {}
        rem[uid] = datetime.now(_UAE).replace(microsecond=0).isoformat()
        settings["reminders"] = rem
        storage.save_settings(settings)
    return {"ok": True}


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
         "sub": f"{fin.collected_percent}% من الإجمالي", "color": "#2E7D5B",
         "pct": fin.collected_percent, "ring": _icons.status_color(fin.collected_percent)},
        {"icon": "⏳", "label": "المتبقّي",
         "value": format_amount(fin.remaining) or "0", "sub": "AED",
         "color": "#2C5AA0", "pct": 100 - fin.collected_percent if fin.total else 0,
         "ring": _icons.status_color(fin.collected_percent)},
        {"icon": "⚠", "label": "المتأخّرون عن السداد",
         "value": f"{fin.unpaid_count:,}", "sub": "بحاجة متابعة",
         "color": "#C0392B",
         "pct": round(fin.unpaid_count * 100 / fin.count) if fin.count else 0,
         "ring": _icons.status_color(
             100 - (fin.unpaid_count * 100 / fin.count if fin.count else 0))},
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

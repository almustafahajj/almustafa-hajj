"""خادم Flask لتطبيق الويب — المرحلة الأولى: تسجيل الدخول + لوحة التحكم.

يعيد استخدام منطق ``hajj_app`` كما هو (المصادقة، التخزين، الإحصاءات). الجلسات
تُحفظ في الذاكرة على الخادم (كافٍ للتطوير؛ للنشر السحابي يُضاف تخزين جلسات آمن
وHTTPS)."""

from __future__ import annotations

import os
import secrets
import tempfile

from flask import (Flask, redirect, render_template, request, send_file,
                   session, url_for)

from hajj_app import app_mode, auth, stats, storage
from hajj_app.fields import BY_KEY, format_amount
from hajj_app.stats import remaining_amount

_PAGE = 50
_STATUS_CLS = {"نشط": "good", "ملغى": "crit", "قائمة انتظار": "warn"}
_CHOICES = {"status": ["", "نشط", "ملغى", "قائمة انتظار"],
            "sex": ["", "ذكر", "أنثى"], "wheelchair": ["", "نعم"]}
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
# مفتاح توقيع الجلسات: من البيئة في النشر (يُبقي الجلسات صالحة عبر إعادات
# التشغيل)؛ وإلّا عشوائي للتطوير المحلّي.
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(16)
# أمان ملفّات الارتباط — يُفعَّل Secure تلقائياً خلف HTTPS في النشر السحابي.
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=(os.environ.get("HTTPS", "").lower()
                           in ("1", "true", "yes")),
)

# جلسات hajj_app الحيّة (المفكوكة التشفير) مفهرسة برمز جلسة المتصفّح
_SESSIONS: dict = {}


def _sess():
    return _SESSIONS.get(session.get("sid"))


def _mode() -> str:
    return session.get("mode", app_mode.HAJJ)


def _noun() -> str:
    return "الحجّاج" if _mode() == app_mode.HAJJ else "المعتمرون"


def _group_attr() -> str:
    return "program" if _mode() == app_mode.HAJJ else "trip"


def _load_records():
    app_mode.set_mode(_mode())
    try:
        records, _note = storage.load_records(session=_sess())
    except Exception:
        records = []
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
                session["mode"] = app_mode.HAJJ
                session["username"] = username
                session["role"] = sess.role_label
                session["acc_key"] = key           # يُعرض مرّة في صفحة الحسابات
                session["acc_added"] = username
                session["acc_msg"] = "تمّت التهيئة — هذا حساب المالك (مدير)."
                return redirect(url_for("accounts"))
            except Exception as exc:
                error = str(exc)
    return render_template("setup.html", error=error)


@app.route("/login", methods=["GET", "POST"])
def login():
    if not auth.is_configured():           # نشر جديد بلا حسابات → تهيئة المالك
        return redirect(url_for("setup"))
    error = ""
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        mode = request.form.get("mode") or app_mode.HAJJ
        try:
            app_mode.set_mode(mode)
            hs = auth.login(username, password)
            sid = secrets.token_hex(16)
            _SESSIONS[sid] = hs
            session["sid"] = sid
            session["mode"] = mode
            session["username"] = username
            session["role"] = getattr(hs, "role_label", "")
            return redirect(url_for("dashboard"))
        except Exception:
            error = "اسم المستخدم أو كلمة المرور غير صحيحة."
    return render_template("login.html", error=error,
                           modes=[(app_mode.HAJJ, "الحج"),
                                  (app_mode.UMRAH, "العمرة")])


@app.get("/logout")
def logout():
    _SESSIONS.pop(session.get("sid"), None)
    session.clear()
    return redirect(url_for("login"))


@app.get("/switch/<mode>")
def switch(mode):
    if mode in (app_mode.HAJJ, app_mode.UMRAH):
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
    return render_template(
        "dashboard.html", kpis=kpis, progs=progs, active="dashboard",
        **_ctx())


def _ctx() -> dict:
    """سياق مشترك للقوالب (الوضع/النوع/زر التبديل/الصلاحيات)."""
    s = _sess()
    return dict(
        noun=_noun(), mode=_mode(),
        other=(app_mode.UMRAH if _mode() == app_mode.HAJJ else app_mode.HAJJ),
        other_label=("العمرة" if _mode() == app_mode.HAJJ else "الحج"),
        is_admin=bool(s is not None and s.is_admin),
        can_edit=bool(s is not None and s.can_edit))


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
             "me": a["username"].lower() == s.username.lower()}
            for a in auth.list_accounts()]
    return render_template(
        "accounts.html", active="accounts", forbidden=False, accounts=rows,
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
        session["acc_added"] = (request.form.get("username") or "").strip()
        session["acc_msg"] = "أُضيف الحساب — سلّم صاحبه كلمة المرور ومفتاح الاسترداد."
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


@app.get("/hujjaj")
def hujjaj():
    if _sess() is None:
        return redirect(url_for("login"))
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
        st = str(getattr(r, "status", "") or "").strip()
        rows.append({
            "idx": i,
            "name": getattr(r, "full_name_ar", "") or getattr(
                r, "full_name_en", "") or "—",
            "passport": getattr(r, "passport_number", "") or "—",
            "program": str(getattr(r, ("program" if _mode() == app_mode.HAJJ
                                       else "trip"), "") or "") or "—",
            "phone": getattr(r, "phone", "") or "—",
            "status": st, "status_cls": _STATUS_CLS.get(st, ""),
            "remaining": format_amount(remaining_amount(r)) or "0",
        })
    return render_template("hujjaj.html", active="hujjaj", rows=rows, q=q,
                           total=total, page=page, pages=pages, offset=offset,
                           **_ctx())


@app.route("/hujjaj/new", methods=["GET", "POST"])
def hujjaj_new():
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app.mrz import PassportData
    if not _sess().can_edit:                 # المطّلع لا يضيف
        return redirect(url_for("hujjaj"))
    records = _load_records()
    if request.method == "POST":
        rec = PassportData(source_file="إدخال ويب")
        drop = _UMRAH_DROP if _mode() == app_mode.UMRAH else set()
        for _title, keys in _GROUPS:
            for k in keys:
                if k in drop or k not in BY_KEY or not BY_KEY[k].editable:
                    continue
                if k in request.form:
                    setattr(rec, k, request.form.get(k, "").strip())
        records.append(rec)
        try:
            storage.save_records(records, session=_sess())
        except Exception:
            pass
        return redirect(url_for("hujjaj"))
    return _render_edit(PassportData(source_file="إدخال ويب"), is_new=True)


@app.route("/hujjaj/<int:idx>", methods=["GET", "POST"])
def hujjaj_edit(idx):
    if _sess() is None:
        return redirect(url_for("login"))
    records = _load_records()
    if not (0 <= idx < len(records)):
        return redirect(url_for("hujjaj"))
    rec = records[idx]
    drop = _UMRAH_DROP if _mode() == app_mode.UMRAH else set()
    saved = False
    if request.method == "POST" and not _sess().can_edit:   # المطّلع لا يعدّل
        return redirect(url_for("hujjaj"))
    if request.method == "POST":
        for _title, keys in _GROUPS:
            for k in keys:
                if k in drop or k not in BY_KEY or not BY_KEY[k].editable:
                    continue
                if k in request.form:
                    setattr(rec, k, request.form.get(k, "").strip())
        try:
            storage.save_records(records, session=_sess())
            saved = True
        except Exception:
            saved = False
    return _render_edit(rec, saved=saved)


def _render_edit(rec, saved=False, is_new=False):
    drop = _UMRAH_DROP if _mode() == app_mode.UMRAH else set()
    groups = []
    for title, keys in _GROUPS:
        fs = []
        for k in keys:
            if k in drop or k not in BY_KEY:
                continue
            fs.append({"key": k, "label": _label(k),
                       "value": str(getattr(rec, k, "") or ""),
                       "choices": _CHOICES.get(k),
                       "type": ("date" if k in _DATE_FIELDS else "")})
        if fs:
            groups.append({"title": title.format(n=_noun()), "fields": fs})
    return render_template(
        "hujjaj_edit.html", active="hujjaj", groups=groups, saved=saved,
        is_new=is_new,
        name=getattr(rec, "full_name_ar", "") or getattr(
            rec, "full_name_en", "") or "",
        number=getattr(rec, "reference_number", "") or "",
        noun_singular=_noun_singular(), **_ctx())


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
    return send_file(p, as_attachment=True, download_name="pilgrims.pdf")


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
    return send_file(p, as_attachment=True, download_name="financial.pdf")

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
    return _render_edit(rec, saved=saved, idx=idx)


def _render_edit(rec, saved=False, is_new=False, idx=None):
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
    docs = []
    if idx is not None:                    # مستندات المعتمر (للسجلّ القائم فقط)
        docs = [("receipt", "🧾 سند قبض"), ("invoice", "🧾 فاتورة"),
                ("contract", "📜 عقد")]
        if _mode() == app_mode.UMRAH:
            docs += [("voucher", "🏨 فاوتشر"), ("treq", "🚖 طلب مواصلات")]
    return render_template(
        "hujjaj_edit.html", active="hujjaj", groups=groups, saved=saved,
        is_new=is_new, idx=idx, docs=docs,
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
    data = {"number": number, "currency": "درهم", "include_madinah": "1",
            "room_types": [n for n, _ in umrah.GROUP_ROOM_TYPES],
            "items": [[n, ""] for n in defaults]}
    return webpricer._pricer_html(data, "مسعّر المجموعات",
                                  submit_js=webpricer._SUBMIT_WEB,
                                  back_url=url_for("offers"))


@app.post("/pricer/pdf")
def pricer_pdf():
    if _sess() is None:
        return ("", 401)
    if not _sess().can_edit:                       # المطّلع لا يحفظ تسعيراً
        return ("forbidden", 403)
    import io
    from hajj_app import umrah, pdf_io
    data = request.get_json(force=True, silent=True) or {}
    settings = storage.load_settings()
    try:                                           # حفظ في «التسعيرات المحفوظة»
        umrah.save_pricing(settings, data)
        storage.save_settings(settings)
    except Exception:
        pass
    co = settings.get("company") if isinstance(settings, dict) else None
    p = _tmp(".pdf")
    pdf_io.export_group_pricing_pdf(data, p, company=co)
    with open(p, "rb") as f:
        buf = io.BytesIO(f.read())
    try:
        os.unlink(p)
    except OSError:
        pass
    buf.seek(0)
    return send_file(buf, mimetype="application/pdf", as_attachment=False,
                     download_name=f"تسعير-{data.get('number','') or ''}.pdf")


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
    co = settings.get("company") if isinstance(settings, dict) else None
    data = pdf_io.build_quotation_data(PassportData(), trip=None, company=co,
                                       number=number)
    return webdoc._doc_html(
        data, pdf_io.UMRAH_QUOTATION_SCHEMA, "عرض سعر رحلة عمرة", "💲",
        submit_action=webdoc.web_submit_action(url_for("quote_pdf")),
        back_url=url_for("offers"))


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
    return webdoc._doc_html(
        dict(q), pdf_io.UMRAH_QUOTATION_SCHEMA, "عرض سعر رحلة عمرة", "💲",
        submit_action=webdoc.web_submit_action(url_for("quote_pdf")),
        back_url=url_for("quotes"))


@app.post("/quotes/pdf")
def quote_pdf():
    if _sess() is None:
        return ("", 401)
    if not _sess().can_edit:
        return ("forbidden", 403)
    from hajj_app import umrah, pdf_io
    from hajj_app.mrz import PassportData
    data = request.get_json(force=True, silent=True) or {}
    settings = storage.load_settings()
    try:
        umrah.save_quote(settings, data.get("code") or "", data)
        storage.save_settings(settings)
    except Exception:
        pass
    co = settings.get("company") if isinstance(settings, dict) else None
    return _pdf_response(
        lambda p: pdf_io.export_umrah_quotation_pdf(
            PassportData(), p, trip=None, company=co, data=data),
        f"عرض-سعر-{data.get('number','') or ''}.pdf")


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
        except Exception:
            pass
    return redirect(url_for("quotes"))


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
    return webpricer._pricer_html(dict(p), "مسعّر المجموعات",
                                  submit_js=webpricer._SUBMIT_WEB,
                                  back_url=url_for("pricings"))


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
        except Exception:
            pass
    return redirect(url_for("pricings"))


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


@app.get("/doc/<int:idx>/<kind>")
def doc_edit(idx, kind):
    if _sess() is None:
        return redirect(url_for("login"))
    if kind not in _DOC_TITLES:
        return redirect(url_for("hujjaj"))
    records = _load_records()
    if not (0 <= idx < len(records)):
        return redirect(url_for("hujjaj"))
    from hajj_app import webdoc
    settings = storage.load_settings()
    co = settings.get("company") if isinstance(settings, dict) else None
    data, schema = _doc_build(kind, records[idx], co, settings)
    title, icon = _DOC_TITLES[kind]
    return webdoc._doc_html(
        data, schema, title, icon,
        submit_action=webdoc.web_submit_action(
            url_for("doc_pdf", idx=idx, kind=kind)),
        back_url=url_for("hujjaj_edit", idx=idx))


@app.post("/doc/<int:idx>/<kind>/pdf")
def doc_pdf(idx, kind):
    if _sess() is None:
        return ("", 401)
    if kind not in _DOC_TITLES:
        return ("", 404)
    records = _load_records()
    if not (0 <= idx < len(records)):
        return ("", 404)
    settings = storage.load_settings()
    co = settings.get("company") if isinstance(settings, dict) else None
    data = request.get_json(force=True, silent=True) or {}
    title = _DOC_TITLES[kind][0]
    return _pdf_response(
        lambda p: _doc_export(kind, records[idx], co, data, p),
        f"{title}-{data.get('number','') or ''}.pdf")


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
            "idx": idx_of[id(r)],
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
            except Exception:
                pass
    return redirect(url_for("finance"))

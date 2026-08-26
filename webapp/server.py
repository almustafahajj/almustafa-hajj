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
        if _mode() == app_mode.UMRAH and "trip" in request.form:
            rec.trip = request.form.get("trip", "").strip()
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
        if _mode() == app_mode.UMRAH and "trip" in request.form:
            rec.trip = request.form.get("trip", "").strip()
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
    if _mode() == app_mode.UMRAH:            # ربط المعتمر ببرنامج عمرة
        from hajj_app import umrah
        codes = [t.code for t in umrah.load_trips(storage.load_settings())]
        groups.insert(0, {"title": "البرنامج", "fields": [{
            "key": "trip", "label": "البرنامج (الرحلة)",
            "value": str(getattr(rec, "trip", "") or ""),
            "choices": [""] + codes, "type": ""}]})
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
                                 session=_sess())
    return send_file(p, mimetype="application/pdf", as_attachment=False,
                     download_name="cards.pdf")


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


# ============================ برامج العمرة =================================
_PROG_GROUPS = [
    ("البيانات الأساسية", [("name", "اسم البرنامج", ""),
                           ("manager", "المسؤول", ""),
                           ("capacity", "السعة (المقاعد)", "number"),
                           ("notes", "ملاحظات", "")]),
    ("التواريخ", [("depart_date", "المغادرة", "date"),
                  ("return_date", "العودة", "date")]),
    ("فندق مكة", [("makkah_hotel", "الفندق", ""),
                  ("makkah_nights", "الليالي", "number"),
                  ("makkah_rooms", "عدد الغرف", "number")]),
    ("فندق المدينة", [("madinah_hotel", "الفندق", ""),
                      ("madinah_nights", "الليالي", "number"),
                      ("madinah_rooms", "عدد الغرف", "number")]),
    ("الطيران", [("airline", "الناقل", ""),
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
    rows = []
    for t in trips:
        n = len(umrah.trip_pilgrims(records, t.code))
        try:
            cap = int(float(str(t.capacity or "").strip() or 0))
        except ValueError:
            cap = 0
        rows.append({"code": t.code, "name": t.name or "—",
                     "depart": t.depart_date or "—", "return": t.return_date or "—",
                     "makkah": t.makkah_hotel or "—", "madinah": t.madinah_hotel or "—",
                     "count": n, "capacity": cap or "—",
                     "remaining": (cap - n) if cap else "—",
                     "over": bool(cap and n > cap), "full": bool(cap and n == cap)})
    return render_template("programs.html", active="programs", rows=rows, **_ctx())


@app.get("/programs/new")
def program_new():
    if _sess() is None:
        return redirect(url_for("login"))
    if not _sess().can_edit:
        return redirect(url_for("programs"))
    from hajj_app import umrah
    settings = storage.load_settings()
    trip = umrah.UmrahTrip(code=umrah.next_code(umrah.load_trips(settings)))
    return render_template("program_edit.html", active="programs", is_new=True,
                           code=trip.code, orig="", groups=_prog_groups(trip),
                           services=[], **_ctx())


@app.get("/programs/<code>")
def program_edit(code):
    if _sess() is None:
        return redirect(url_for("login"))
    from hajj_app import umrah
    settings = storage.load_settings()
    trip = next((t for t in umrah.load_trips(settings) if t.code == code), None)
    if trip is None:
        return redirect(url_for("programs"))
    return render_template("program_edit.html", active="programs", is_new=False,
                           code=trip.code, orig=trip.code,
                           groups=_prog_groups(trip),
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
    trips = [t for t in trips if t.code != key and t.code != trip.code]
    trips.append(trip)
    umrah.save_trips(settings, trips)
    try:
        storage.save_settings(settings)
    except Exception:
        pass
    return redirect(url_for("programs"))


@app.post("/programs/<code>/delete")
def program_delete(code):
    if _sess() is None:
        return redirect(url_for("login"))
    if _sess().can_edit:
        from hajj_app import umrah
        settings = storage.load_settings()
        trips = [t for t in umrah.load_trips(settings) if t.code != code]
        umrah.save_trips(settings, trips)
        try:
            storage.save_settings(settings)
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
        back_url=url_for("travel_list"))


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

"""تطبيق Flask: الدخول، عرض كشف الحجّاج مع فلاتر، وفتح سجلّ الحاج كاملاً.

يعيد استخدام ``hajj_app.auth`` و ``hajj_app.storage`` و ``hajj_app.fields``
مباشرةً، فيقرأ نفس ملف البيانات المشفّر الذي يستعمله برنامج سطح المكتب.
"""

from __future__ import annotations

import copy
import io
import os
import secrets
import tempfile
import threading
from datetime import date
from functools import wraps
from pathlib import Path

from flask import (
    Flask, abort, flash, g, redirect, render_template, request, send_file,
    url_for, make_response,
)

from hajj_app import (
    app_mode, audit, auth, einvoice, excel_io, fields, pdf_io, programs,
    quality, stats, storage, transport, umrah,
)
from hajj_app.mrz import PassportData
from . import sessions

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_COOKIE = "hajj_session"
_MODE_COOKIE = "hajj_mode"          # وضع التشغيل الحالي (حج/عمرة) لهذا المتصفّح

# يُسلسِل عمليات الكتابة داخل الخادم حتى لا يدهس طلبان الملف نفسه
_WRITE_LOCK = threading.Lock()

# مكدّس تراجع بسيط في ذاكرة الخادم: (وصف، نسخة من السجلات) قبل كل عملية مُتلِفة
_UNDO: list = []
_UNDO_MAX = 10


def _push_undo(records, label):
    _UNDO.append((label, copy.deepcopy(records)))
    del _UNDO[:-_UNDO_MAX]

# أعمدة الجدول (المفتاح، العنوان) — عنوان مختصر مأخوذ من fields حيث أمكن
COLUMNS = [
    ("full_name_ar", "اسم الحاج"),
    ("passport_number", "رقم الجواز"),
    ("nationality_ar", "الجنسية"),
    ("phone", "الهاتف"),
    ("program", "البرنامج"),
    ("hotel", "الفندق"),
    ("room_number", "الغرفة"),
]

# فلاتر منسدلة تُملأ قيمها من البيانات
FILTERS = [
    ("program", "البرنامج"),
    ("hotel", "الفندق"),
    ("nationality_ar", "الجنسية"),
]

# تجميع حقول صفحة السجلّ الكامل (المفتاح من fields.BY_KEY للعنوان العربي)
DETAIL_GROUPS = [
    ("بيانات الجواز", ["full_name_ar", "full_name_en", "passport_number",
                        "nationality_ar", "sex", "birth_date", "expiry_date"]),
    ("الاتصال والتعريف", ["phone", "family_number", "reference_number"]),
    ("البرنامج", ["program", "group", "staff"]),
    ("التسكين", ["hotel", "room_type", "room_number"]),
    ("المواصلات والخدمات", ["transport", "executive_service", "wheelchair", "hady"]),
    ("الطيران", ["airline", "flight_number", "travel_class", "pnr",
                 "arrival_date", "arrival_time", "departure_date", "departure_time"]),
    ("المالية", ["program_value", "paid_amount", "remaining_amount"]),
    ("ملاحظات", ["notes"]),
]

# مجموعات نموذج الإضافة/التعديل: كحقول العرض لكن بلا الحقول المحسوبة
_READONLY_KEYS = {"remaining_amount"}
EDIT_GROUPS = [
    (title, [k for k in keys if k not in _READONLY_KEYS])
    for title, keys in DETAIL_GROUPS
]
EDITABLE_KEYS = [k for _t, keys in EDIT_GROUPS for k in keys]
# حقول ذات قيم محدّدة تُعرض قائمةً منسدلة
CHOICES = {
    "sex": ["", "ذكر", "أنثى"],
    "wheelchair": ["", "نعم"],
}
TEXTAREA_KEYS = {"notes"}

# ---- نماذج وضع العمرة ----
# حقول نموذج برنامج العمرة: (المفتاح، العنوان، النوع)
UMRAH_TRIP_FIELDS = [
    ("name", "اسم البرنامج", "text"),
    ("manager", "مدير البرنامج", "text"),
    ("depart_date", "تاريخ المغادرة", "date"),
    ("return_date", "تاريخ العودة", "date"),
    ("makkah_hotel", "فندق مكة", "text"),
    ("makkah_nights", "ليالي مكة", "number"),
    ("makkah_rooms", "غرف مكة المتاحة", "number"),
    ("madinah_hotel", "فندق المدينة", "text"),
    ("madinah_nights", "ليالي المدينة", "number"),
    ("madinah_rooms", "غرف المدينة المتاحة", "number"),
    ("airline", "شركة الطيران", "text"),
    ("capacity", "السعة (المقاعد)", "number"),
    ("price_single", "سعر المفرد", "number"),
    ("price_double", "سعر الثنائي", "number"),
    ("price_triple", "سعر الثلاثي", "number"),
    ("price_quad", "سعر الرباعي", "number"),
    ("price_child", "سعر الطفل", "number"),
    ("transport", "ملاحظة النقل الداخلي", "text"),
    ("emergency_uae", "طوارئ الإمارات", "text"),
    ("emergency_ksa", "طوارئ السعودية", "text"),
    ("notes", "ملاحظات", "textarea"),
]
# حقول نموذج المعتمر (إدخال يدوي على الويب)
UMRAH_PILGRIM_FIELDS = [
    ("full_name_ar", "الاسم بالعربي", "text"),
    ("full_name_en", "الاسم بالإنجليزي", "text"),
    ("passport_number", "رقم الجواز", "text"),
    ("nationality_ar", "الجنسية", "text"),
    ("phone", "الهاتف", "text"),
    ("room_type", "نوع الغرفة", "room"),
    ("room_number", "رقم الغرفة", "text"),
    ("program_value", "قيمة البرنامج", "number"),
    ("paid_amount", "المبلغ المدفوع", "number"),
    ("payment_method", "طريقة الدفع", "text"),
    ("notes", "ملاحظات", "textarea"),
]
PAYMENT_METHODS = ["نقد", "تحويل بنكي", "شبكة/مدى", "شيك", "رابط دفع", "أخرى"]


def create_app(auth_path: str | Path | None = None,
               data_path: str | Path | None = None) -> Flask:
    from hajj_app.paths import is_frozen, resource_dir
    if is_frozen():
        # في نسخة exe تُستخرج القوالب/الأصول إلى مجلد PyInstaller المؤقّت
        base = resource_dir() / "hajj_web"
        app = Flask(__name__, template_folder=str(base / "templates"),
                    static_folder=str(base / "static"))
    else:
        app = Flask(__name__)
    app.secret_key = secrets.token_hex(32)          # لتوقيع الكوكيّ
    app.config["AUTH_PATH"] = str(auth_path) if auth_path else None
    app.config["DATA_PATH"] = str(data_path) if data_path else None

    def _auth_path():
        return app.config["AUTH_PATH"] or auth.default_auth_path()

    def _data_path():
        # مسار بيانات الوضع الحالي: يُشتقّ اسم الملف من الوضع (حج/عمرة) فتبقى
        # قائمة كل وضع مستقلّة حتى مع تثبيت مسار قاعديّ في الإعدادات.
        base = app.config["DATA_PATH"]
        if base:
            return str(Path(base).with_name(app_mode.data_filename()))
        return str(storage.default_data_path())

    @app.before_request
    def _apply_mode():
        # يضبط وضع التشغيل من كوكيّ المتصفّح قبل أي قراءة/كتابة, فتُحسم مسارات
        # البيانات والإعدادات والمسمّيات تلقائياً لكل طلب.
        mode = request.cookies.get(_MODE_COOKIE, app_mode.HAJJ)
        app_mode.set_mode(mode if mode in (app_mode.HAJJ, app_mode.UMRAH)
                          else app_mode.HAJJ)
        g.mode = app_mode.get_mode()
        g.other_mode = (app_mode.UMRAH if app_mode.is_hajj() else app_mode.HAJJ)

    @app.context_processor
    def _inject_mode():
        # يُتيح لكل القوالب معرفة الوضع الحالي والآخر (لزرّ التبديل والمسمّيات)
        return {
            "mode": app_mode.get_mode(),
            "is_umrah": app_mode.is_umrah(),
            "other_mode": g.get("other_mode", app_mode.HAJJ),
            "other_mode_label": app_mode.mode_label(
                g.get("other_mode", app_mode.HAJJ)),
            "pilgrims_label": app_mode.label("pilgrims"),
        }

    def _company():
        return pdf_io.company_info(storage.load_settings().get("company"))

    def _season():
        return str(storage.load_settings().get("season_year", "")).strip()

    def _programs_map():
        return dict(zip(programs.PROGRAM_NAMES,
                        programs.load_programs(storage.load_settings())))

    # -------------------------------------------------- إدارة الجلسة الحالية
    def current_session():
        return sessions.get(request.cookies.get(_COOKIE))

    def login_required(view):
        @wraps(view)
        def wrapped(*a, **kw):
            g.session = current_session()
            if g.session is None:
                return redirect(url_for("login", next=request.path))
            return view(*a, **kw)
        return wrapped

    def load_records():
        """يحمّل الكشف بجلسة المستخدم، أو يرفع RuntimeError إن فشل التشفير."""
        try:
            return storage.load_records(_data_path(), g.session)
        except auth.AuthError:
            raise RuntimeError("decrypt")

    def _audit(action: str, details: str = ""):
        """يُلحق قيداً بسجلّ التدقيق المجاور لملف بيانات الخادم."""
        audit.record(action, details, user=f"{g.session.username} (ويب)",
                     path=Path(_data_path()).parent / "audit.log")

    def edit_required(view):
        """يمنع من لا يملك صلاحية التعديل (المطّلع) من مسارات الكتابة."""
        @wraps(view)
        def wrapped(*a, **kw):
            g.session = current_session()
            if g.session is None:
                return redirect(url_for("login", next=request.path))
            if not g.session.can_edit:
                abort(403)
            return view(*a, **kw)
        return wrapped

    def _apply_form(rec: PassportData) -> PassportData:
        """ينسخ الحقول القابلة للتعديل من النموذج إلى السجلّ."""
        for key in EDITABLE_KEYS:
            setattr(rec, key, (request.form.get(key) or "").strip())
        return rec

    def _form_groups(rec: PassportData):
        """يبني مجموعات النموذج: (العنوان، [(المفتاح، العنوان، القيمة)])."""
        groups = []
        for title, keys in EDIT_GROUPS:
            items = []
            for key in keys:
                field = fields.BY_KEY.get(key)
                items.append((key, field.label if field else key,
                              getattr(rec, key, "") or ""))
            groups.append((title, items))
        return groups

    # ------------------------------------------------------------- المسارات
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if not auth.is_configured(_auth_path()):
            return render_template("login.html", not_configured=True, error=None)
        error = None
        if request.method == "POST":
            username = (request.form.get("username") or "").strip()
            password = request.form.get("password") or ""
            try:
                session = auth.login(username, password, _auth_path())
            except auth.AuthError as exc:
                error = str(exc)
            else:
                token = sessions.create(session)
                dest = request.args.get("next") or url_for("index")
                resp = make_response(redirect(dest))
                resp.set_cookie(_COOKIE, token, httponly=True, samesite="Lax")
                return resp
        return render_template("login.html", not_configured=False, error=error)

    @app.route("/logout")
    def logout():
        sessions.destroy(request.cookies.get(_COOKIE))
        resp = make_response(redirect(url_for("login")))
        resp.delete_cookie(_COOKIE)
        return resp

    @app.route("/mode/<mode>")
    @login_required
    def switch_mode(mode):
        """يبدّل وضع التشغيل (حج/عمرة) لهذا المتصفّح ثم يعود للرئيسية."""
        if mode not in (app_mode.HAJJ, app_mode.UMRAH):
            abort(404)
        resp = make_response(redirect(url_for("index")))
        resp.set_cookie(_MODE_COOKIE, mode, httponly=True, samesite="Lax")
        return resp

    def _filter_indexed(records):
        """يطبّق الفلاتر والبحث من ?args، ويعيد ([(الفهرس، السجلّ)], selected, q)."""
        selected = {key: (request.args.get(key) or "").strip() for key, _ in FILTERS}
        indexed = list(enumerate(records))
        for key, value in selected.items():
            if value:
                indexed = [(i, r) for i, r in indexed
                           if (getattr(r, key, "") or "").strip() == value]
        query = (request.args.get("q") or "").strip()
        if query:
            ql = query.lower()
            indexed = [
                (i, r) for i, r in indexed
                if ql in (r.full_name_ar or "").lower()
                or ql in (r.passport_number or "").lower()
                or ql in (r.phone or "").lower()
            ]
        return indexed, selected, query

    @app.route("/")
    @login_required
    def index():
        # في وضع العمرة تكون الواجهة مُنظَّمة حسب البرامج (كبرنامج سطح المكتب)
        if app_mode.is_umrah():
            return redirect(url_for("umrah_programs"))
        try:
            records, note = load_records()
        except RuntimeError:
            sessions.destroy(request.cookies.get(_COOKIE))
            return redirect(url_for("login"))

        options = {
            key: sorted({(getattr(r, key, "") or "").strip()
                         for r in records if (getattr(r, key, "") or "").strip()})
            for key, _ in FILTERS
        }
        indexed, selected, query = _filter_indexed(records)
        rows = [
            {"idx": i, "cells": [getattr(r, key, "") or "" for key, _ in COLUMNS]}
            for i, r in indexed
        ]
        kpis = stats.financial_summary(records).as_rows()
        return render_template(
            "index.html", columns=[label for _, label in COLUMNS],
            rows=rows, total=len(rows), grand_total=len(records), query=query,
            filters=FILTERS, options=options, selected=selected, kpis=kpis,
            query_string=request.query_string.decode("utf-8"),
            username=g.session.username, role=g.session.role_label, note=note,
            can_edit=g.session.can_edit, is_admin=g.session.can_manage_accounts,
        )

    # ============================== وضع العمرة ==============================
    def _umrah_records():
        """يحمّل معتمري ملف العمرة (يرفع RuntimeError إن فشل فكّ التشفير)."""
        return load_records()

    def _trip_or_404(code):
        trips = umrah.load_trips(storage.load_settings())
        trip = next((t for t in trips if t.code == code), None)
        if trip is None:
            abort(404)
        return trip

    def _finance_rows(indexed):
        """صفوف مالية لكل معتمر + إجماليات. ``indexed`` أزواج (الفهرس، السجلّ)."""
        rows = []
        total = paid = 0.0
        owe = 0
        count = 0
        for gidx, r in indexed:
            count += 1
            v = fields.parse_amount(r.program_value) or 0.0
            p = fields.parse_amount(r.paid_amount) or 0.0
            rem = v - p
            total += v
            paid += p
            if rem > 0.005 and p > 0.005:
                status, cls = "جزئي", "partial"
                owe += 1
            elif rem > 0.005:
                status, cls = "غير مدفوع", "unpaid"
                owe += 1
            else:
                status, cls = "مسدّد", "paid"
            rows.append({
                "idx": gidx, "orig": r.passport_number or "",
                "name": r.full_name_ar or r.full_name_en or "—",
                "passport": r.passport_number or "—",
                "room": r.room_type or "—",
                "phone": r.phone or "—",
                "value": fields.format_amount(v),
                "paid": fields.format_amount(p),
                "remaining": fields.format_amount(rem),
                "npays": len(getattr(r, "payments", None) or []),
                "status": status, "cls": cls,
            })
        totals = {
            "value": fields.format_amount(total),
            "paid": fields.format_amount(paid),
            "remaining": fields.format_amount(total - paid),
            "pct": (f"{(paid / total * 100):.0f}%" if total else "0%"),
            "owe": owe, "count": count,
        }
        return rows, totals

    def _program_indexed(records, code):
        """أزواج (الفهرس العام، السجلّ) لمعتمري برنامجٍ ضمن الكشف الكامل."""
        return [(i, r) for i, r in enumerate(records)
                if str(getattr(r, "trip", "") or "") == code]

    @app.route("/umrah/programs")
    @login_required
    def umrah_programs():
        try:
            records, note = _umrah_records()
        except RuntimeError:
            sessions.destroy(request.cookies.get(_COOKIE))
            return redirect(url_for("login"))
        trips = umrah.load_trips(storage.load_settings())
        rows = []
        for t in trips:
            pilgrims = umrah.trip_pilgrims(records, t.code)
            _r, tot = _finance_rows(list(enumerate(pilgrims)))
            rows.append({
                "code": t.code, "name": t.name or "—",
                "makkah": t.makkah_hotel or "—", "madinah": t.madinah_hotel or "—",
                "depart": t.depart_date or "—", "ret": t.return_date or "—",
                "count": len(pilgrims), "capacity": t.capacity or "—",
                "value": tot["value"], "paid": tot["paid"],
                "remaining": tot["remaining"],
            })
        return render_template(
            "umrah_programs.html", rows=rows, note=note,
            username=g.session.username, role=g.session.role_label,
            can_edit=g.session.can_edit, is_admin=g.session.can_manage_accounts)

    @app.route("/umrah/program/<code>")
    @login_required
    def umrah_program(code):
        try:
            records, note = _umrah_records()
        except RuntimeError:
            sessions.destroy(request.cookies.get(_COOKIE))
            return redirect(url_for("login"))
        trip = _trip_or_404(code)
        rows, totals = _finance_rows(_program_indexed(records, code))
        return render_template(
            "umrah_program.html", trip=trip, rows=rows, totals=totals, note=note,
            username=g.session.username, role=g.session.role_label,
            can_edit=g.session.can_edit, is_admin=g.session.can_manage_accounts)

    @app.route("/umrah/program/<code>/finance.pdf")
    @login_required
    def umrah_finance_pdf(code):
        try:
            records, _note = _umrah_records()
        except RuntimeError:
            sessions.destroy(request.cookies.get(_COOKIE))
            return redirect(url_for("login"))
        trip = _trip_or_404(code)
        pilgrims = umrah.trip_pilgrims(records, code)
        if not pilgrims:
            abort(404)
        label = f"{trip.code} — {trip.name}" if trip.name else trip.code
        return _send_generated(
            lambda p: pdf_io.export_umrah_finance_pdf(pilgrims, p,
                                                      program_name=label),
            f"مالية {trip.code}.pdf", "application/pdf")

    # ---- إدارة برامج العمرة (إضافة/تعديل/حذف) ----
    def _apply_trip_form(trip):
        for key, _l, _t in UMRAH_TRIP_FIELDS:
            setattr(trip, key, (request.form.get(key) or "").strip())
        return trip

    @app.route("/umrah/program/new", methods=["GET", "POST"])
    @edit_required
    def umrah_program_new():
        if request.method == "POST":
            with _WRITE_LOCK:
                settings = storage.load_settings()
                trips = umrah.load_trips(settings)
                trip = _apply_trip_form(umrah.UmrahTrip(code=umrah.next_code(trips)))
                trips.append(trip)
                umrah.save_trips(settings, trips)
                storage.save_settings(settings)
            _audit("إضافة برنامج عمرة", trip.name or trip.code)
            flash(f"أُضيف البرنامج: {trip.name or trip.code}", "ok")
            return redirect(url_for("umrah_program", code=trip.code))
        return render_template(
            "umrah_program_form.html", title="برنامج عمرة جديد",
            action=url_for("umrah_program_new"), fields=UMRAH_TRIP_FIELDS,
            trip=umrah.UmrahTrip(), is_new=True,
            username=g.session.username, role=g.session.role_label)

    @app.route("/umrah/program/<code>/edit", methods=["GET", "POST"])
    @edit_required
    def umrah_program_edit(code):
        with _WRITE_LOCK:
            settings = storage.load_settings()
            trips = umrah.load_trips(settings)
            trip = next((t for t in trips if t.code == code), None)
            if trip is None:
                abort(404)
            if request.method == "POST":
                _apply_trip_form(trip)
                umrah.save_trips(settings, trips)
                storage.save_settings(settings)
                _audit("تعديل برنامج عمرة", trip.name or trip.code)
                flash("تم حفظ تعديلات البرنامج", "ok")
                return redirect(url_for("umrah_program", code=code))
        return render_template(
            "umrah_program_form.html", title="تعديل البرنامج",
            action=url_for("umrah_program_edit", code=code),
            fields=UMRAH_TRIP_FIELDS, trip=trip, is_new=False,
            username=g.session.username, role=g.session.role_label)

    @app.route("/umrah/program/<code>/delete", methods=["POST"])
    @edit_required
    def umrah_program_delete(code):
        with _WRITE_LOCK:
            settings = storage.load_settings()
            trips = umrah.load_trips(settings)
            if not any(t.code == code for t in trips):
                abort(404)
            umrah.save_trips(settings, [t for t in trips if t.code != code])
            storage.save_settings(settings)
        _audit("حذف برنامج عمرة", code)
        flash("حُذف البرنامج", "ok")
        return redirect(url_for("umrah_programs"))

    # ---- معتمرو البرنامج (إضافة/تعديل/حذف) ----
    def _apply_pilgrim_form(rec):
        for key, _l, _t in UMRAH_PILGRIM_FIELDS:
            setattr(rec, key, (request.form.get(key) or "").strip())
        return rec

    def _umrah_room_names():
        return [n for _k, n, _o in umrah.ROOM_TYPES]

    @app.route("/umrah/program/<code>/pilgrim/new", methods=["GET", "POST"])
    @edit_required
    def umrah_pilgrim_new(code):
        trip = _trip_or_404(code)
        if request.method == "POST":
            with _WRITE_LOCK:
                records, _ = storage.load_records(_data_path(), g.session)
                trips = umrah.load_trips(storage.load_settings())
                trip = next((t for t in trips if t.code == code), trip)
                rec = _apply_pilgrim_form(PassportData(source_file="إدخال ويب"))
                umrah.apply_trip_to_record(trip, rec)
                rec.trip = code
                if not str(rec.reference_number or "").strip():
                    rec.reference_number = umrah.next_reference(trip, records)
                records.append(rec)
                storage.save_records(records, _data_path(), g.session)
            name = rec.full_name_ar or rec.passport_number or "—"
            _audit("إضافة معتمر", name)
            flash(f"أُضيف المعتمر: {name}", "ok")
            return redirect(url_for("umrah_program", code=code))
        return render_template(
            "umrah_pilgrim_form.html", title="إضافة معتمر",
            action=url_for("umrah_pilgrim_new", code=code),
            fields=UMRAH_PILGRIM_FIELDS, rooms=_umrah_room_names(),
            rec=PassportData(), code=code, orig="", is_new=True,
            username=g.session.username, role=g.session.role_label)

    def _pilgrim_in_program(records, code, idx):
        """يعيد سجلّ المعتمر بعد التحقّق من انتمائه للبرنامج، أو 404."""
        if idx < 0 or idx >= len(records):
            abort(404)
        rec = records[idx]
        if str(getattr(rec, "trip", "") or "") != code:
            abort(404)
        return rec

    @app.route("/umrah/program/<code>/pilgrim/<int:idx>/edit",
               methods=["GET", "POST"])
    @edit_required
    def umrah_pilgrim_edit(code, idx):
        _trip_or_404(code)
        with _WRITE_LOCK:
            records, _ = storage.load_records(_data_path(), g.session)
            rec = _pilgrim_in_program(records, code, idx)
            if request.method == "POST":
                if (request.form.get("orig") or "") != (rec.passport_number or ""):
                    abort(409)
                _apply_pilgrim_form(rec)
                rec.trip = code
                storage.save_records(records, _data_path(), g.session)
                name = rec.full_name_ar or rec.passport_number or "—"
                _audit("تعديل معتمر", name)
                flash("تم حفظ التعديلات", "ok")
                return redirect(url_for("umrah_program", code=code))
        return render_template(
            "umrah_pilgrim_form.html", title="تعديل بيانات المعتمر",
            action=url_for("umrah_pilgrim_edit", code=code, idx=idx),
            fields=UMRAH_PILGRIM_FIELDS, rooms=_umrah_room_names(),
            rec=rec, code=code, orig=rec.passport_number or "", is_new=False,
            username=g.session.username, role=g.session.role_label)

    @app.route("/umrah/program/<code>/pilgrim/<int:idx>/delete",
               methods=["POST"])
    @edit_required
    def umrah_pilgrim_delete(code, idx):
        _trip_or_404(code)
        with _WRITE_LOCK:
            records, _ = storage.load_records(_data_path(), g.session)
            rec = _pilgrim_in_program(records, code, idx)
            if (request.form.get("orig") or "") != (rec.passport_number or ""):
                abort(409)
            name = rec.full_name_ar or rec.passport_number or "—"
            _push_undo(records, f"حذف «{name}»")
            del records[idx]
            storage.save_records(records, _data_path(), g.session)
        _audit("حذف معتمر", name)
        flash(f"حُذف المعتمر: {name}", "ok")
        return redirect(url_for("umrah_program", code=code))

    # ---- سجلّ الدفعات (الأقساط) للمعتمر ----
    @app.route("/umrah/program/<code>/pilgrim/<int:idx>/payments")
    @login_required
    def umrah_payments(code, idx):
        _trip_or_404(code)
        try:
            records, _ = storage.load_records(_data_path(), g.session)
        except auth.AuthError:
            sessions.destroy(request.cookies.get(_COOKIE))
            return redirect(url_for("login"))
        rec = _pilgrim_in_program(records, code, idx)
        pays = list(getattr(rec, "payments", None) or [])
        value = fields.parse_amount(rec.program_value) or 0.0
        paid = fields.payment_total(rec)
        totals = {
            "value": fields.format_amount(value),
            "paid": fields.format_amount(paid),
            "remaining": fields.format_amount(value - paid),
        }
        name = rec.full_name_ar or rec.full_name_en or rec.passport_number or "—"
        return render_template(
            "umrah_payments.html", code=code, idx=idx, name=name,
            payments=pays, totals=totals, methods=PAYMENT_METHODS,
            orig=rec.passport_number or "",
            username=g.session.username, role=g.session.role_label,
            can_edit=g.session.can_edit)

    @app.route("/umrah/program/<code>/pilgrim/<int:idx>/payments/add",
               methods=["POST"])
    @edit_required
    def umrah_payment_add(code, idx):
        _trip_or_404(code)
        amount = fields.parse_amount(request.form.get("amount"))
        with _WRITE_LOCK:
            records, _ = storage.load_records(_data_path(), g.session)
            rec = _pilgrim_in_program(records, code, idx)
            if not amount:
                flash("أدخل مبلغ الدفعة بالأرقام", "error")
                return redirect(url_for("umrah_payments", code=code, idx=idx))
            if not isinstance(getattr(rec, "payments", None), list):
                rec.payments = []
            rec.payments.append({
                "date": (request.form.get("date") or "").strip(),
                "amount": fields.format_amount(amount),
                "method": (request.form.get("method") or "").strip(),
                "note": (request.form.get("note") or "").strip(),
            })
            rec.paid_amount = fields.format_amount(fields.payment_total(rec))
            if rec.payments:
                rec.payment_method = str(rec.payments[-1].get("method", "") or "")
                rec.payment_date = str(rec.payments[-1].get("date", "") or "")
            storage.save_records(records, _data_path(), g.session)
        _audit("إضافة دفعة", rec.full_name_ar or rec.passport_number or "—")
        flash("أُضيفت الدفعة", "ok")
        return redirect(url_for("umrah_payments", code=code, idx=idx))

    @app.route("/umrah/program/<code>/pilgrim/<int:idx>/payments/<int:pi>/delete",
               methods=["POST"])
    @edit_required
    def umrah_payment_delete(code, idx, pi):
        _trip_or_404(code)
        with _WRITE_LOCK:
            records, _ = storage.load_records(_data_path(), g.session)
            rec = _pilgrim_in_program(records, code, idx)
            pays = getattr(rec, "payments", None) or []
            if 0 <= pi < len(pays):
                del pays[pi]
                rec.paid_amount = fields.format_amount(fields.payment_total(rec))
                storage.save_records(records, _data_path(), g.session)
        _audit("حذف دفعة", rec.full_name_ar or rec.passport_number or "—")
        flash("حُذفت الدفعة", "ok")
        return redirect(url_for("umrah_payments", code=code, idx=idx))

    def _send_generated(make_fn, download_name, mimetype):
        """يولّد ملفاً مؤقّتاً عبر make_fn(path) ثم يرسله ويحذفه.

        ملفات PDF تُعرض **داخل المتصفّح** (معاينة) فيطبعها المستخدم أو يحفظها
        من عارض المتصفّح؛ بقية الأنواع (إكسل/XML) تُنزَّل مباشرة.
        """
        suffix = Path(download_name).suffix
        fd, tmp = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        try:
            make_fn(tmp)
            data = Path(tmp).read_bytes()
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        inline = (mimetype == "application/pdf")
        return send_file(io.BytesIO(data), as_attachment=not inline,
                         download_name=download_name, mimetype=mimetype)

    def _current_filtered():
        """يحمّل الكشف ويطبّق الفلاتر الحالية، ويعيد قائمة السجلات فقط."""
        records, _note = load_records()
        indexed, _sel, _q = _filter_indexed(records)
        return [r for _i, r in indexed]

    @app.route("/export/excel")
    @login_required
    def export_excel_route():
        try:
            records = _current_filtered()
        except RuntimeError:
            sessions.destroy(request.cookies.get(_COOKIE))
            return redirect(url_for("login"))
        _audit("تصدير إكسل", f"{len(records)} حاج")
        return _send_generated(lambda p: excel_io.export_excel(records, p),
                               "كشف الحجاج.xlsx", _XLSX_MIME)

    @app.route("/export/pdf")
    @login_required
    def export_pdf_route():
        try:
            records = _current_filtered()
        except RuntimeError:
            sessions.destroy(request.cookies.get(_COOKIE))
            return redirect(url_for("login"))
        _audit("تصدير PDF", f"{len(records)} حاج")
        return _send_generated(
            lambda p: pdf_io.export_pdf(records, p, title="كشف الحجاج"),
            "كشف الحجاج.pdf", "application/pdf")

    @app.route("/pilgrim/<int:idx>")
    @login_required
    def pilgrim(idx):
        try:
            records, _note = load_records()
        except RuntimeError:
            sessions.destroy(request.cookies.get(_COOKIE))
            return redirect(url_for("login"))
        if idx < 0 or idx >= len(records):
            abort(404)
        rec = records[idx]

        groups = []
        for title, keys in DETAIL_GROUPS:
            items = []
            for key in keys:
                field = fields.BY_KEY.get(key)
                label = field.label if field else key
                if key == "remaining_amount":
                    value = fields.compute_remaining(rec)
                else:
                    value = getattr(rec, key, "") or ""
                items.append((label, value))
            groups.append((title, items))

        from hajj_app import images
        img_kinds = [("passport", "صورة الجواز"), ("permit", "التصريح السعودي")]
        img_present = {k: bool(rec.image_id and images.has_image(rec.image_id, k))
                       for k, _ in img_kinds}
        name = rec.full_name_ar or rec.full_name_en or rec.passport_number or "—"
        return render_template(
            "pilgrim.html", name=name, groups=groups, idx=idx,
            orig=rec.passport_number or "", img_kinds=img_kinds,
            img_present=img_present,
            username=g.session.username, role=g.session.role_label,
            can_edit=g.session.can_edit,
        )

    # ------------------------------------------------ الإضافة/التعديل/الحذف
    @app.route("/pilgrim/new", methods=["GET", "POST"])
    @edit_required
    def pilgrim_new():
        if request.method == "POST":
            rec = _apply_form(PassportData(source_file="إدخال ويب"))
            with _WRITE_LOCK:
                records, _ = storage.load_records(_data_path(), g.session)
                records.append(rec)
                storage.save_records(records, _data_path(), g.session)
                new_idx = len(records) - 1
            name = rec.full_name_ar or rec.full_name_en or rec.passport_number or "—"
            _audit("إضافة حاج", name)
            flash(f"أُضيف الحاج: {name}", "ok")
            return redirect(url_for("pilgrim", idx=new_idx))
        return render_template(
            "form.html", title="إضافة حاج جديد", action=url_for("pilgrim_new"),
            groups=_form_groups(PassportData()), choices=CHOICES,
            textareas=TEXTAREA_KEYS, orig="", is_new=True,
            username=g.session.username, role=g.session.role_label,
        )

    @app.route("/pilgrim/scan", methods=["GET", "POST"])
    @edit_required
    def pilgrim_scan():
        """إضافة حاج بقراءة جوازه (صورة/PDF): يقرأ ثم يعرض النموذج مملوءاً
        للمراجعة قبل الحفظ."""
        if request.method == "GET":
            return render_template("scan.html", username=g.session.username,
                                   role=g.session.role_label)
        file = request.files.get("file")
        if not file or not file.filename:
            flash("اختر صورة أو ملف PDF للجواز", "error")
            return redirect(url_for("pilgrim_scan"))
        try:
            from hajj_app import ocr
            from hajj_app.tesseract_setup import configure_tesseract
            configure_tesseract()
            ocr.ensure_tesseract()
        except Exception:                              # noqa: BLE001
            flash("قراءة الجواز تحتاج تثبيت Tesseract-OCR على جهاز الخادم.",
                  "error")
            return redirect(url_for("pilgrim_scan"))

        from hajj_app.mrz import MRZError
        suffix = Path(file.filename).suffix.lower()
        fd, tmp = tempfile.mkstemp(suffix=suffix or ".img")
        os.close(fd)
        rec, note = None, ""
        try:
            file.save(tmp)
            if suffix == ".pdf":
                from hajj_app import pdf_in
                recs, _notes = pdf_in.extract_from_pdf(tmp)
                if recs:
                    rec = recs[0]
                    if len(recs) > 1:
                        note = (f"عُثر على {len(recs)} جوازات في الملف — عُرض "
                                "الأول. للبقية استعمل «استيراد».")
            else:
                try:
                    rec = ocr.extract_passport(tmp)
                except MRZError as exc:
                    note = str(exc)
        except Exception as exc:                       # noqa: BLE001
            note = str(exc)
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass

        if rec is None:
            flash(note or "تعذّرت قراءة الجواز — أدخل البيانات يدوياً.", "error")
            rec = PassportData()
        else:
            if note:
                flash(note, "warn")
            flash("راجع البيانات المقروءة ثم اضغط «إضافة».", "ok")
        return render_template(
            "form.html", title="إضافة حاج (من الجواز)",
            action=url_for("pilgrim_new"), groups=_form_groups(rec),
            choices=CHOICES, textareas=TEXTAREA_KEYS, orig="", is_new=True,
            username=g.session.username, role=g.session.role_label)

    @app.route("/pilgrim/<int:idx>/edit", methods=["GET", "POST"])
    @edit_required
    def pilgrim_edit(idx):
        with _WRITE_LOCK:
            records, _ = storage.load_records(_data_path(), g.session)
            if idx < 0 or idx >= len(records):
                abort(404)
            rec = records[idx]
            if request.method == "POST":
                # حارس بسيط ضدّ تغيّر الترتيب بين الفتح والحفظ
                if (request.form.get("orig") or "") != (rec.passport_number or ""):
                    abort(409)
                _apply_form(rec)
                storage.save_records(records, _data_path(), g.session)
                name = rec.full_name_ar or rec.full_name_en or rec.passport_number or "—"
                _audit("تعديل حاج", name)
                flash("تم حفظ التعديلات", "ok")
                return redirect(url_for("pilgrim", idx=idx))
        return render_template(
            "form.html", title="تعديل سجلّ الحاج",
            action=url_for("pilgrim_edit", idx=idx),
            groups=_form_groups(rec), choices=CHOICES, textareas=TEXTAREA_KEYS,
            orig=rec.passport_number or "", is_new=False,
            username=g.session.username, role=g.session.role_label,
        )

    @app.route("/pilgrim/<int:idx>/delete", methods=["POST"])
    @edit_required
    def pilgrim_delete(idx):
        with _WRITE_LOCK:
            records, _ = storage.load_records(_data_path(), g.session)
            if idx < 0 or idx >= len(records):
                abort(404)
            rec = records[idx]
            if (request.form.get("orig") or "") != (rec.passport_number or ""):
                abort(409)
            name = rec.full_name_ar or rec.full_name_en or rec.passport_number or "—"
            _push_undo(records, f"حذف «{name}»")
            del records[idx]
            storage.save_records(records, _data_path(), g.session)
        _audit("حذف حاج", name)
        flash(f"حُذف الحاج: {name}", "ok")
        return redirect(url_for("index"))

    def _selected_idxs():
        out = []
        for s in request.form.getlist("sel"):
            try:
                out.append(int(s))
            except (TypeError, ValueError):
                pass
        return out

    @app.route("/bulk/delete", methods=["POST"])
    @edit_required
    def bulk_delete():
        sel = _selected_idxs()
        if not sel:
            flash("لم تحدّد أي حاج", "error")
            return redirect(url_for("index"))
        with _WRITE_LOCK:
            records, _ = storage.load_records(_data_path(), g.session)
            _push_undo(records, f"حذف {len(sel)} سجل")
            for i in sorted(set(sel), reverse=True):
                if 0 <= i < len(records):
                    del records[i]
            storage.save_records(records, _data_path(), g.session)
        _audit("حذف سجلات", f"{len(sel)} سجل")
        flash(f"حُذف {len(sel)} حاجّاً", "ok")
        return redirect(url_for("index"))

    @app.route("/bulk/edit", methods=["POST"])
    @edit_required
    def bulk_edit():
        sel = _selected_idxs()
        if not sel:
            flash("لم تحدّد أي حاج", "error")
            return redirect(url_for("index"))
        return render_template(
            "bulk_edit.html", sel=sel, count=len(sel),
            groups=_form_groups(PassportData()), choices=CHOICES,
            textareas=TEXTAREA_KEYS, username=g.session.username,
            role=g.session.role_label)

    @app.route("/bulk/edit/apply", methods=["POST"])
    @edit_required
    def bulk_edit_apply():
        sel = _selected_idxs()
        apply_keys = [k for k in EDITABLE_KEYS if request.form.get(f"apply_{k}")]
        if not sel or not apply_keys:
            flash("حدّد الحقول المراد تعديلها", "error")
            return redirect(url_for("index"))
        values = {k: (request.form.get(k) or "").strip() for k in apply_keys}
        with _WRITE_LOCK:
            records, _ = storage.load_records(_data_path(), g.session)
            _push_undo(records, f"تعديل جماعي {len(sel)} سجل")
            for i in sel:
                if 0 <= i < len(records):
                    for k, v in values.items():
                        setattr(records[i], k, v)
            storage.save_records(records, _data_path(), g.session)
        _audit("تعديل جماعي", f"{len(sel)} سجل — {' + '.join(apply_keys)}")
        flash(f"عُدّل {len(sel)} حاجّاً", "ok")
        return redirect(url_for("index"))

    @app.route("/undo", methods=["POST"])
    @edit_required
    def undo():
        if not _UNDO:
            flash("لا يوجد ما يُتراجع عنه", "warn")
            return redirect(url_for("index"))
        label, records = _UNDO.pop()
        with _WRITE_LOCK:
            storage.save_records(records, _data_path(), g.session)
        _audit("تراجع", label)
        flash(f"تم التراجع: {label}", "ok")
        return redirect(url_for("index"))

    # ---------------------------------------------------- الاستيراد
    def _append(records_to_add):
        with _WRITE_LOCK:
            records, _ = storage.load_records(_data_path(), g.session)
            _push_undo(records, f"استيراد {len(records_to_add)} سجل")
            records.extend(records_to_add)
            storage.save_records(records, _data_path(), g.session)

    @app.route("/import")
    @edit_required
    def import_page():
        return render_template(
            "import.html", username=g.session.username, role=g.session.role_label)

    @app.route("/import/excel", methods=["POST"])
    @edit_required
    def import_excel_route():
        file = request.files.get("file")
        if not file or not file.filename:
            flash("اختر ملف إكسل أولاً", "error")
            return redirect(url_for("import_page"))
        fd, tmp = tempfile.mkstemp(suffix=".xlsx")
        os.close(fd)
        try:
            file.save(tmp)
            records, notes = excel_io.import_excel(tmp)
        except Exception as exc:                       # noqa: BLE001
            flash(f"تعذّر قراءة الملف: {exc}", "error")
            return redirect(url_for("import_page"))
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        if not records:
            flash("الملف لا يحتوي بيانات حجّاج صالحة", "error")
            return redirect(url_for("import_page"))
        _append(records)
        _audit("استيراد إكسل", f"{len(records)} سجل")
        flash(f"تم استيراد {len(records)} حاجّاً من إكسل", "ok")
        if notes:
            flash(" | ".join(notes[:3]), "error")
        return redirect(url_for("index"))

    @app.route("/import/passports", methods=["POST"])
    @edit_required
    def import_passports_route():
        files = [f for f in request.files.getlist("files") if f and f.filename]
        if not files:
            flash("اختر صور الجوازات أو ملف PDF", "error")
            return redirect(url_for("import_page"))
        # قراءة الجوازات تحتاج Tesseract على جهاز الخادم
        try:
            from hajj_app import ocr
            from hajj_app.tesseract_setup import configure_tesseract
            configure_tesseract()
            ocr.ensure_tesseract()
        except Exception:                              # noqa: BLE001
            flash("قراءة الجوازات تحتاج تثبيت Tesseract-OCR على جهاز الخادم.",
                  "error")
            return redirect(url_for("import_page"))

        from hajj_app import pdf_in
        from hajj_app.mrz import MRZError
        new, errors = [], []
        for f in files:
            suffix = Path(f.filename).suffix.lower()
            fd, tmp = tempfile.mkstemp(suffix=suffix or ".img")
            os.close(fd)
            try:
                f.save(tmp)
                if suffix == ".pdf":
                    recs, _notes = pdf_in.extract_from_pdf(tmp)
                    new.extend(recs)
                else:
                    try:
                        new.append(ocr.extract_passport(tmp))
                    except MRZError as exc:
                        errors.append(f"{f.filename}: {exc}")
            except Exception as exc:                   # noqa: BLE001
                errors.append(f"{f.filename}: {exc}")
            finally:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
        if new:
            _append(new)
            _audit("إضافة جوازات", f"{len(new)} حاج")
            flash(f"أُضيف {len(new)} حاجّاً من الجوازات", "ok")
        if errors:
            flash("تعذّرت قراءة: " + " | ".join(errors[:5]), "error")
        if not new and not errors:
            flash("لم تُقرأ أي بيانات من الملفات", "error")
        return redirect(url_for("index"))

    # ---------------------------------------------------- الإحصاءات
    @app.route("/stats")
    @login_required
    def stats_page():
        try:
            records, _note = load_records()
        except RuntimeError:
            sessions.destroy(request.cookies.get(_COOKIE))
            return redirect(url_for("login"))
        fin = stats.financial_summary(records)
        dists = [(label, stats.distribution(records, key))
                 for key, label in stats.GROUPINGS]
        return render_template(
            "stats.html", fin_rows=fin.as_rows(), dists=dists,
            total=len(records), username=g.session.username,
            role=g.session.role_label)

    @app.route("/stats/pdf")
    @login_required
    def stats_pdf_route():
        try:
            records, _note = load_records()
        except RuntimeError:
            sessions.destroy(request.cookies.get(_COOKIE))
            return redirect(url_for("login"))
        _audit("تصدير الإحصاءات PDF", f"{len(records)} حاج")
        return _send_generated(
            lambda p: pdf_io.export_stats_pdf(records, p),
            "الإحصاءات والملخص المالي.pdf", "application/pdf")

    # ---------------------------------------------------- الكشوف والبطاقات
    @app.route("/reports")
    @login_required
    def reports_page():
        return render_template(
            "reports.html", query_string=request.query_string.decode("utf-8"),
            username=g.session.username, role=g.session.role_label)

    def _report_download(make_fn, name, mimetype="application/pdf"):
        try:
            records = _current_filtered()
        except RuntimeError:
            sessions.destroy(request.cookies.get(_COOKIE))
            return redirect(url_for("login"))
        _audit("تصدير تقرير", name)
        return _send_generated(lambda p: make_fn(records, p), name, mimetype)

    @app.route("/reports/transport.pdf")
    @login_required
    def report_transport_pdf():
        return _report_download(
            lambda r, p: pdf_io.export_transport_pdf(r, p), "كشف المواصلات.pdf")

    @app.route("/reports/transport.xlsx")
    @login_required
    def report_transport_xlsx():
        return _report_download(
            lambda r, p: transport.export_transport_excel(r, p),
            "كشف المواصلات.xlsx", _XLSX_MIME)

    @app.route("/reports/airline.pdf")
    @login_required
    def report_airline_pdf():
        return _report_download(
            lambda r, p: pdf_io.export_airline_pdf(r, p), "كشف الطيران.pdf")

    @app.route("/reports/badges.pdf")
    @login_required
    def report_badges_pdf():
        return _report_download(
            lambda r, p: pdf_io.export_badges_pdf(r, p, session=g.session),
            "بطاقات الحجّاج.pdf")

    @app.route("/reports/stickers/<kind>.pdf")
    @login_required
    def report_stickers_pdf(kind):
        if kind not in ("bag", "room", "envelope"):
            abort(404)
        names = {"bag": "حقائب", "room": "غرف", "envelope": "أظرف"}
        return _report_download(
            lambda r, p: pdf_io.export_stickers_pdf(r, p, kind=kind),
            f"استيكرات {names[kind]}.pdf")

    @app.route("/reports/rooming.xlsx")
    @login_required
    def report_rooming_xlsx():
        return _report_download(
            lambda r, p: excel_io.export_grouped_excel(r, p, title="كشف التسكين"),
            "كشف التسكين.xlsx", _XLSX_MIME)

    @app.route("/reports/rooming.pdf")
    @login_required
    def report_rooming_pdf():
        return _report_download(
            lambda r, p: pdf_io.export_pdf(r, p, title="كشف التسكين",
                                           group_by_room=True),
            "كشف التسكين.pdf")

    @app.route("/reports/camps.pdf")
    @login_required
    def report_camps_pdf():
        from hajj_app import camps
        camp = (request.args.get("camp") or camps.CAMP_MINA).strip()
        if camp not in camps.CAMPS:
            camp = camps.CAMP_MINA
        try:
            capacity = int(request.args.get("capacity") or 40)
        except (TypeError, ValueError):
            capacity = 40
        try:
            records = _current_filtered()
        except RuntimeError:
            sessions.destroy(request.cookies.get(_COOKIE))
            return redirect(url_for("login"))
        _audit("كشف المخيمات", f"{camp} — {len(records)} حاج")
        plan = camps.build_camp_plan(records, camp, capacity=capacity)
        return _send_generated(
            lambda p: pdf_io.export_tents_pdf(plan, p, title=f"مخيّم {camp}"),
            f"مخيّم {camp}.pdf", "application/pdf")

    # ---------------------------------------- مستندات الحاج الفردية
    def _load_one(idx):
        records, _note = load_records()
        if idx < 0 or idx >= len(records):
            abort(404)
        return records[idx]

    def _doc_route(idx, make_fn, name, mimetype="application/pdf"):
        try:
            rec = _load_one(idx)
        except RuntimeError:
            sessions.destroy(request.cookies.get(_COOKIE))
            return redirect(url_for("login"))
        _audit("مستند حاج", name)
        return _send_generated(lambda p: make_fn(rec, p), name, mimetype)

    @app.route("/pilgrim/<int:idx>/receipt.pdf")
    @login_required
    def pilgrim_receipt(idx):
        return _doc_route(idx, lambda rec, p: pdf_io.export_receipt_pdf(
            rec, p, company=_company()["name_ar"],
            company_en=_company()["name_en"], season=_season(),
            date_str=date.today().isoformat(),
            amount=fields.parse_amount(rec.paid_amount),
            description=pdf_io.build_receipt_description(rec, season=_season())),
            "سند قبض.pdf")

    @app.route("/pilgrim/<int:idx>/invoice.pdf")
    @login_required
    def pilgrim_invoice(idx):
        return _doc_route(idx, lambda rec, p: pdf_io.export_invoice_pdf(
            rec, p, company=_company(), season=_season(),
            date_str=date.today().isoformat(),
            item_desc=pdf_io.build_invoice_item(rec, season=_season())),
            "فاتورة ضريبية.pdf")

    @app.route("/pilgrim/<int:idx>/contract.pdf")
    @login_required
    def pilgrim_contract(idx):
        return _doc_route(idx, lambda rec, p: pdf_io.export_contract_pdf(
            rec, p, company=_company(), season=_season(),
            date_str=date.today().isoformat(),
            body=pdf_io.build_contract_body(rec, company=_company(),
                                            season=_season())),
            "عقد خدمات حج.pdf")

    @app.route("/pilgrim/<int:idx>/einvoice.xml")
    @login_required
    def pilgrim_einvoice(idx):
        return _doc_route(idx, lambda rec, p: einvoice.export_invoice_xml(
            rec, p, company=_company(), date_str=date.today().isoformat(),
            item_desc=pdf_io.build_invoice_item(rec, season=_season())),
            "فاتورة إلكترونية PEPPOL.xml", "application/xml")

    @app.route("/pilgrim/<int:idx>/whatsapp")
    @login_required
    def pilgrim_whatsapp(idx):
        try:
            rec = _load_one(idx)
        except RuntimeError:
            sessions.destroy(request.cookies.get(_COOKIE))
            return redirect(url_for("login"))
        from hajj_app import whatsapp
        cc = str(storage.load_settings().get("whatsapp_cc", "971")).strip() or "971"
        msg = f"حيّاكم الله، بخصوص حجّكم لهذا الموسم"
        link = whatsapp.wa_link(rec.phone, msg, default_cc=cc)
        if not link:
            flash("لا يوجد رقم هاتف صالح لهذا الحاج", "error")
            return redirect(url_for("pilgrim", idx=idx))
        return redirect(link)

    # ---------------------------------------- صور الجوازات والتصاريح
    def _image_as_png(blob):
        """يحوّل بايتات صورة/PDF إلى PNG للعرض في المتصفّح، أو None."""
        from hajj_app import images
        if images.is_pdf(blob):
            pages = images.render_pages_png(blob)
            return pages[0] if pages else None
        try:
            img = images.to_pil_image(blob)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except Exception:                              # noqa: BLE001
            return None

    @app.route("/pilgrim/<int:idx>/image/<kind>")
    @login_required
    def pilgrim_image(idx, kind):
        from hajj_app import images
        if kind not in images.KINDS:
            abort(404)
        try:
            rec = _load_one(idx)
        except RuntimeError:
            sessions.destroy(request.cookies.get(_COOKIE))
            return redirect(url_for("login"))
        if not rec.image_id or not images.has_image(rec.image_id, kind):
            abort(404)
        blob = images.load_image(rec.image_id, kind, g.session)
        if blob is None:
            abort(404)
        png = _image_as_png(blob)
        if png is None:
            abort(404)
        return send_file(io.BytesIO(png), mimetype="image/png")

    @app.route("/pilgrim/<int:idx>/image/<kind>/upload", methods=["POST"])
    @edit_required
    def pilgrim_image_upload(idx, kind):
        from hajj_app import images
        if kind not in images.KINDS:
            abort(404)
        file = request.files.get("file")
        if not file or not file.filename:
            flash("اختر ملف صورة أو PDF", "error")
            return redirect(url_for("pilgrim", idx=idx))
        fd, tmp = tempfile.mkstemp(suffix=Path(file.filename).suffix or ".img")
        os.close(fd)
        try:
            file.save(tmp)
            with _WRITE_LOCK:
                records, _ = storage.load_records(_data_path(), g.session)
                if idx < 0 or idx >= len(records):
                    abort(404)
                rec = records[idx]
                if not rec.image_id:
                    rec.image_id = images.new_image_id()
                images.save_image(rec.image_id, kind, tmp, g.session)
                storage.save_records(records, _data_path(), g.session)
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        _audit("رفع صورة", images.KIND_LABELS.get(kind, kind))
        flash("تم رفع الصورة", "ok")
        return redirect(url_for("pilgrim", idx=idx))

    @app.route("/reports/passports.pdf")
    @login_required
    def report_passports_pdf():
        from hajj_app import images
        try:
            records = _current_filtered()
        except RuntimeError:
            sessions.destroy(request.cookies.get(_COOKIE))
            return redirect(url_for("login"))
        entries, temps = [], []
        try:
            for rec in records:
                if not (rec.image_id and images.has_image(rec.image_id, images.PASSPORT)):
                    continue
                blob = images.load_image(rec.image_id, images.PASSPORT, g.session)
                png = _image_as_png(blob) if blob else None
                if png is None:
                    continue
                fd, tmp = tempfile.mkstemp(suffix=".png")
                os.close(fd)
                Path(tmp).write_bytes(png)
                temps.append(tmp)
                name = (rec.full_name_ar or rec.full_name_en
                        or rec.passport_number or "—")
                entries.append((name, tmp))
            if not entries:
                flash("لا توجد صور جوازات في المعروض", "error")
                return redirect(url_for("reports_page"))
            _audit("طباعة الجوازات", f"{len(entries)} جواز")
            return _send_generated(
                lambda p: pdf_io.export_passports_pdf(entries, p),
                "جوازات الحجّاج.pdf", "application/pdf")
        finally:
            for t in temps:
                try:
                    os.unlink(t)
                except OSError:
                    pass

    # ---------------------------------------------------- فحص الجاهزية
    @app.route("/quality")
    @login_required
    def quality_page():
        try:
            records, _note = load_records()
        except RuntimeError:
            sessions.destroy(request.cookies.get(_COOKIE))
            return redirect(url_for("login"))
        report = quality.check_records(records, programs=_programs_map())
        return render_template(
            "quality.html", groups=report.by_kind(),
            summary=quality.summary_text(report), clean=report.clean,
            username=g.session.username, role=g.session.role_label)

    # ---------------------------------------------------- برامج الحملة
    @app.route("/programs", methods=["GET", "POST"])
    @edit_required
    def programs_page():
        settings = storage.load_settings()
        progs = programs.load_programs(settings)
        if request.method == "POST":
            new = []
            for i in range(len(programs.PROGRAM_NAMES)):
                data = {k: (request.form.get(f"p{i}_{k}") or "").strip()
                        for k in programs.PROGRAM_KEYS}
                new.append(data)
            settings["programs"] = new
            try:
                storage.save_settings(settings)
            except OSError as exc:
                flash(f"تعذّر الحفظ: {exc}", "error")
            else:
                _audit("تعديل البرامج")
                flash("حُفظت برامج الحملة", "ok")
            return redirect(url_for("programs_page"))
        prog_forms = []
        for name, prog in zip(programs.PROGRAM_NAMES, progs):
            prog_forms.append((name, [
                (title, [(k, label, getattr(prog, k, "") or "")
                         for k, label, _t in items])
                for title, items in programs.FIELD_GROUPS
            ]))
        return render_template(
            "programs.html", program_names=list(programs.PROGRAM_NAMES),
            prog_forms=prog_forms, username=g.session.username,
            role=g.session.role_label)

    # ---------------------------------------------------- نسخة احتياطية
    @app.route("/backup", methods=["POST"])
    @edit_required
    def backup_now():
        try:
            records, _note = load_records()
            storage.write_snapshot(records, g.session)
        except (RuntimeError, OSError) as exc:
            flash(f"تعذّرت النسخة الاحتياطية: {exc}", "error")
            return redirect(url_for("index"))
        _audit("نسخة احتياطية", f"{len(records)} سجل")
        flash("تم إنشاء نسخة احتياطية", "ok")
        return redirect(url_for("index"))

    # ---------------------------------------------------- إدارة الحسابات
    def admin_required(view):
        @wraps(view)
        def wrapped(*a, **kw):
            g.session = current_session()
            if g.session is None:
                return redirect(url_for("login", next=request.path))
            if not g.session.can_manage_accounts:
                abort(403)
            return view(*a, **kw)
        return wrapped

    def _render_accounts(new_recovery=None):
        return render_template(
            "accounts.html", accounts=auth.list_accounts(_auth_path()),
            roles=[(r, auth.ROLE_LABELS[r]) for r in auth.ROLES],
            me=g.session.username, new_recovery=new_recovery,
            username=g.session.username, role=g.session.role_label)

    @app.route("/accounts")
    @admin_required
    def accounts_page():
        return _render_accounts()

    @app.route("/accounts/add", methods=["POST"])
    @admin_required
    def accounts_add():
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        role = (request.form.get("role") or "viewer").strip()
        try:
            recovery = auth.add_account(g.session, username, password, role,
                                        _auth_path())
        except auth.AuthError as exc:
            flash(str(exc), "error")
            return _render_accounts()
        _audit("إضافة حساب", f"{username} ({auth.ROLE_LABELS.get(role, role)})")
        flash(f"أُضيف الحساب: {username}", "ok")
        return _render_accounts(new_recovery=(username, recovery))

    @app.route("/accounts/role", methods=["POST"])
    @admin_required
    def accounts_role():
        username = (request.form.get("username") or "").strip()
        role = (request.form.get("role") or "").strip()
        try:
            auth.set_role(g.session, username, role, _auth_path())
        except auth.AuthError as exc:
            flash(str(exc), "error")
        else:
            _audit("تغيير دور", f"{username} -> {auth.ROLE_LABELS.get(role, role)}")
            flash(f"غُيّرت صلاحية «{username}»", "ok")
        return redirect(url_for("accounts_page"))

    @app.route("/accounts/delete", methods=["POST"])
    @admin_required
    def accounts_delete():
        username = (request.form.get("username") or "").strip()
        try:
            auth.remove_account(g.session, username, _auth_path())
        except auth.AuthError as exc:
            flash(str(exc), "error")
        else:
            _audit("حذف حساب", username)
            flash(f"حُذف الحساب «{username}»", "ok")
        return redirect(url_for("accounts_page"))

    # ---------------------------------------------------- سجلّ التدقيق
    @app.route("/audit")
    @login_required
    def audit_page():
        entries = audit.read_entries(limit=500,
                                     path=Path(_data_path()).parent / "audit.log")
        return render_template(
            "audit.html", entries=entries, username=g.session.username,
            role=g.session.role_label)

    # ---------------------------------------------------- حساب المستخدم
    @app.route("/account/password", methods=["GET", "POST"])
    @login_required
    def account_password():
        if request.method == "POST":
            cur = request.form.get("current") or ""
            new = request.form.get("password") or ""
            confirm = request.form.get("confirm") or ""
            problem = auth.password_problem(new, confirm)
            if problem:
                flash(problem, "error")
                return redirect(url_for("account_password"))
            try:
                newsess = auth.change_password(
                    g.session.username, cur, new, _auth_path())
            except auth.AuthError as exc:
                flash(str(exc), "error")
                return redirect(url_for("account_password"))
            _audit("تغيير كلمة المرور")
            flash("تم تغيير كلمة المرور — بياناتك كما هي", "ok")
            if newsess.fresh_recovery_key:
                return render_template(
                    "recovery_shown.html", key=newsess.fresh_recovery_key,
                    username=g.session.username, role=g.session.role_label)
            return redirect(url_for("index"))
        return render_template("account_password.html",
                               username=g.session.username,
                               role=g.session.role_label)

    @app.route("/account/recovery", methods=["GET", "POST"])
    @login_required
    def account_recovery():
        if request.method == "POST":
            password = request.form.get("password") or ""
            try:
                key = auth.regenerate_recovery_key(
                    g.session.username, password, _auth_path())
            except auth.AuthError as exc:
                flash(str(exc), "error")
                return redirect(url_for("account_recovery"))
            _audit("مفتاح استرداد جديد")
            return render_template(
                "recovery_shown.html", key=key, username=g.session.username,
                role=g.session.role_label)
        return render_template("account_recovery.html",
                               username=g.session.username,
                               role=g.session.role_label)

    # ---------------------------------------------------- استعادة نسخة
    @app.route("/restore")
    @edit_required
    def restore_page():
        items = [(p.name, storage.snapshot_label(p))
                 for p in storage.list_snapshots()]
        return render_template("restore.html", items=items,
                               username=g.session.username,
                               role=g.session.role_label)

    @app.route("/restore/apply", methods=["POST"])
    @edit_required
    def restore_apply():
        name = (request.form.get("name") or "").strip()
        snaps = {p.name: p for p in storage.list_snapshots()}
        target = snaps.get(name)
        if not target:
            abort(404)
        try:
            with _WRITE_LOCK:
                current, _ = storage.load_records(_data_path(), g.session)
                storage.write_snapshot(current, g.session)   # أمان قبل الاستبدال
                records, _note = storage.load_records(target, g.session)
                storage.save_records(records, _data_path(), g.session)
        except (auth.AuthError, OSError) as exc:
            flash(f"تعذّرت الاستعادة: {exc}", "error")
            return redirect(url_for("restore_page"))
        _audit("استعادة نسخة", storage.snapshot_label(target))
        flash(f"استُعيدت النسخة ({len(records)} سجل)", "ok")
        return redirect(url_for("index"))

    @app.route("/qr")
    def qr():
        """صفحة برمز QR للرابط على الشبكة — لفتحه من جوال/لوحي بمسح سريع."""
        import base64
        import qrcode
        from .server import _local_ip

        host = request.host
        port = host.split(":")[-1] if ":" in host else os.environ.get(
            "HAJJ_WEB_PORT", "8000")
        url = f"http://{_local_ip()}:{port}"
        img = qrcode.make(url)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return render_template("qr.html", url=url, qr_b64=b64)

    @app.route("/healthz")
    def healthz():
        return {"ok": True}

    return app

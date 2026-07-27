"""تطبيق Flask: الدخول، عرض كشف الحجّاج مع فلاتر، وفتح سجلّ الحاج كاملاً.

يعيد استخدام ``hajj_app.auth`` و ``hajj_app.storage`` و ``hajj_app.fields``
مباشرةً، فيقرأ نفس ملف البيانات المشفّر الذي يستعمله برنامج سطح المكتب.
"""

from __future__ import annotations

import secrets
import threading
from functools import wraps
from pathlib import Path

from flask import (
    Flask, abort, flash, g, redirect, render_template, request, url_for,
    make_response,
)

from hajj_app import audit, auth, fields, storage
from hajj_app.mrz import PassportData
from . import sessions

_COOKIE = "hajj_session"

# يُسلسِل عمليات الكتابة داخل الخادم حتى لا يدهس طلبان الملف نفسه
_WRITE_LOCK = threading.Lock()

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


def create_app(auth_path: str | Path | None = None,
               data_path: str | Path | None = None) -> Flask:
    app = Flask(__name__)
    app.secret_key = secrets.token_hex(32)          # لتوقيع الكوكيّ
    app.config["AUTH_PATH"] = str(auth_path) if auth_path else None
    app.config["DATA_PATH"] = str(data_path) if data_path else None

    def _auth_path():
        return app.config["AUTH_PATH"] or auth.default_auth_path()

    def _data_path():
        return app.config["DATA_PATH"] or storage.default_data_path()

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

    @app.route("/")
    @login_required
    def index():
        try:
            records, note = load_records()
        except RuntimeError:
            sessions.destroy(request.cookies.get(_COOKIE))
            return redirect(url_for("login"))

        # قوائم الفلاتر من كامل البيانات (قبل الترشيح)
        options = {
            key: sorted({(getattr(r, key, "") or "").strip()
                         for r in records if (getattr(r, key, "") or "").strip()})
            for key, _ in FILTERS
        }
        selected = {key: (request.args.get(key) or "").strip() for key, _ in FILTERS}

        # نحتفظ بالفهرس الأصلي ليصل رابط السجلّ إلى الحاج الصحيح
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

        rows = [
            {"idx": i, "cells": [getattr(r, key, "") or "" for key, _ in COLUMNS]}
            for i, r in indexed
        ]
        return render_template(
            "index.html", columns=[label for _, label in COLUMNS],
            rows=rows, total=len(rows), grand_total=len(records), query=query,
            filters=FILTERS, options=options, selected=selected,
            username=g.session.username, role=g.session.role_label, note=note,
            can_edit=g.session.can_edit,
        )

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

        name = rec.full_name_ar or rec.full_name_en or rec.passport_number or "—"
        return render_template(
            "pilgrim.html", name=name, groups=groups, idx=idx,
            orig=rec.passport_number or "",
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
            del records[idx]
            storage.save_records(records, _data_path(), g.session)
        _audit("حذف حاج", name)
        flash(f"حُذف الحاج: {name}", "ok")
        return redirect(url_for("index"))

    @app.route("/healthz")
    def healthz():
        return {"ok": True}

    return app

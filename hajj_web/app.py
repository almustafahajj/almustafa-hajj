"""تطبيق Flask: الدخول، عرض كشف الحجّاج مع فلاتر، وفتح سجلّ الحاج كاملاً.

يعيد استخدام ``hajj_app.auth`` و ``hajj_app.storage`` و ``hajj_app.fields``
مباشرةً، فيقرأ نفس ملف البيانات المشفّر الذي يستعمله برنامج سطح المكتب.
"""

from __future__ import annotations

import io
import os
import secrets
import tempfile
import threading
from functools import wraps
from pathlib import Path

from flask import (
    Flask, abort, flash, g, redirect, render_template, request, send_file,
    url_for, make_response,
)

from hajj_app import audit, auth, excel_io, fields, pdf_io, storage
from hajj_app.mrz import PassportData
from . import sessions

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

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
        return render_template(
            "index.html", columns=[label for _, label in COLUMNS],
            rows=rows, total=len(rows), grand_total=len(records), query=query,
            filters=FILTERS, options=options, selected=selected,
            query_string=request.query_string.decode("utf-8"),
            username=g.session.username, role=g.session.role_label, note=note,
            can_edit=g.session.can_edit,
        )

    def _send_generated(make_fn, download_name, mimetype):
        """يولّد ملفاً مؤقّتاً عبر make_fn(path) ثم يرسله تنزيلاً ويحذفه."""
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
        return send_file(io.BytesIO(data), as_attachment=True,
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

    # ---------------------------------------------------- الاستيراد
    def _append(records_to_add):
        with _WRITE_LOCK:
            records, _ = storage.load_records(_data_path(), g.session)
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

    @app.route("/healthz")
    def healthz():
        return {"ok": True}

    return app

"""تطبيق Flask: الدخول وعرض كشف الحجّاج (المرحلة صفر).

يعيد استخدام ``hajj_app.auth`` و ``hajj_app.storage`` مباشرةً، فيقرأ نفس
ملف البيانات المشفّر الذي يستعمله برنامج سطح المكتب.
"""

from __future__ import annotations

import secrets
from functools import wraps
from pathlib import Path

from flask import (
    Flask, abort, g, redirect, render_template, request, url_for, make_response,
)

from hajj_app import auth, storage
from . import sessions

_COOKIE = "hajj_session"

# الأعمدة المعروضة في الجدول (المرحلة صفر — قراءة فقط)
COLUMNS = [
    ("full_name_ar", "اسم الحاج"),
    ("passport_number", "رقم الجواز"),
    ("nationality_ar", "الجنسية"),
    ("phone", "الهاتف"),
    ("program", "البرنامج"),
    ("hotel", "الفندق"),
    ("room_number", "الغرفة"),
]


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
            records, note = storage.load_records(_data_path(), g.session)
        except auth.AuthError:
            # مفتاح الجلسة لا يطابق الملف — أعِد الدخول
            sessions.destroy(request.cookies.get(_COOKIE))
            return redirect(url_for("login"))

        query = (request.args.get("q") or "").strip()
        if query:
            ql = query.lower()
            records = [
                r for r in records
                if ql in (r.full_name_ar or "").lower()
                or ql in (r.passport_number or "").lower()
                or ql in (r.phone or "").lower()
            ]

        rows = [
            [getattr(r, key, "") or "" for key, _ in COLUMNS]
            for r in records
        ]
        return render_template(
            "index.html", columns=[label for _, label in COLUMNS],
            rows=rows, total=len(rows), query=query,
            username=g.session.username, role=g.session.role_label,
            note=note,
        )

    @app.route("/healthz")
    def healthz():
        return {"ok": True}

    return app

"""مراقبة الأخطاء عبر Sentry — اختيارية تماماً.

تعمل فقط إن وُضع متغيّر البيئة ``SENTRY_DSN`` في Railway (وكانت المكتبة مثبّتة)؛
وإلّا لا يتغيّر شيء. البورتال يحمل بيانات جوازات حقيقية، فلا يخرج إلى Sentry إلّا
ما يلزم لفهم الخطأ:

* لا محتوى نماذج ولا JSON ولا ملفّات ارتباط ولا ترويسات ولا عنوان الزائر.
* الرابط بلا استعلام (?q=…) والمقاطع الطويلة (رموز التحقّق/المعرّفات) تُستبدل.
* لا قيم متغيّرات من سطور الخطأ، ولا «فتات» السجلّات.
* أرقام الجوازات والهواتف في نصّ الخطأ تُخفى.
"""

from __future__ import annotations

import os
import re
from urllib.parse import urlsplit

ENABLED = False                 # هل التقطت المراقبة الإعداد فعلاً؟
_PASSPORT = re.compile(r"\b[A-Za-z]{1,2}\d{5,9}\b")          # P1234567 / AB123456
_DIGITS = re.compile(r"\+?\d(?:[\d \-]{4,}\d)")               # هواتف وأرقام طويلة
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_TOKEN_SEG = re.compile(r"/[A-Za-z0-9_\-]{12,}")              # /v/<رمز> و/archive/<معرّف>


def mask(text) -> str:
    """يخفي ما يشبه رقم جواز أو هاتفاً أو بريداً في نصّ الخطأ."""
    s = str(text or "")
    s = _EMAIL.sub("[بريد]", s)
    s = _PASSPORT.sub("[جواز]", s)
    return _DIGITS.sub("[رقم]", s)[:600]


def clean_url(url) -> str:
    """المسار فقط، بلا نطاق ولا استعلام، والمقاطع الطويلة (رموز) تصير :id."""
    return _TOKEN_SEG.sub("/:id", urlsplit(str(url or "")).path or "/")


def scrub(event, hint=None):
    """قبل الإرسال: يُبقي نوع الخطأ ومكانه في الشيفرة فقط."""
    req = event.get("request")
    if isinstance(req, dict):
        event["request"] = {"method": str(req.get("method") or ""),
                            "url": clean_url(req.get("url"))}
    for k in ("user", "extra", "breadcrumbs"):
        event.pop(k, None)
    for exc in ((event.get("exception") or {}).get("values") or []):
        if exc.get("value"):
            exc["value"] = mask(exc["value"])
        for fr in ((exc.get("stacktrace") or {}).get("frames") or []):
            fr.pop("vars", None)
    for th in ((event.get("threads") or {}).get("values") or []):
        for fr in ((th.get("stacktrace") or {}).get("frames") or []):
            fr.pop("vars", None)
    le = event.get("logentry")
    if isinstance(le, dict):
        le.pop("params", None)
        for k in ("message", "formatted"):
            if le.get(k):
                le[k] = mask(le[k])
    if event.get("message"):
        event["message"] = mask(event["message"])
    tags = event.setdefault("tags", {})
    try:                                           # النظام (حج/عمرة) يفيد في فهم الخطأ
        from flask import has_request_context, session
        if has_request_context() and session.get("mode"):
            tags["mode"] = str(session.get("mode"))
    except Exception:                              # noqa: BLE001
        pass
    return event


def _drop_breadcrumb(crumb, hint=None):
    return None


def init(app, dsn: str | None = None, **extra) -> bool:
    """يفعّل Sentry إن وُجد ``SENTRY_DSN``. لا يرفع استثناءً أبداً."""
    global ENABLED
    dsn = (dsn if dsn is not None else os.environ.get("SENTRY_DSN", "")).strip()
    if not dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        sentry_sdk.init(
            dsn=dsn,
            integrations=[FlaskIntegration(transaction_style="endpoint")],
            send_default_pii=False,
            include_local_variables=False,
            max_request_body_size="never",
            traces_sample_rate=0.0,
            max_breadcrumbs=0,
            before_send=scrub,
            before_breadcrumb=_drop_breadcrumb,
            environment=os.environ.get("RAILWAY_ENVIRONMENT_NAME") or "local",
            release=(os.environ.get("RAILWAY_GIT_COMMIT_SHA") or "")[:12] or None,
            **extra,
        )
        ENABLED = True
    except Exception:                              # noqa: BLE001
        ENABLED = False
    return ENABLED


def send_test(username: str = "") -> bool:
    """خطأ تجريبي يظهر في Sentry — للتأكّد من الإعداد من صفحة المدير."""
    if not ENABLED:
        return False
    try:
        import sentry_sdk
        try:
            raise RuntimeError("خطأ تجريبي من بورتال المصطفى — المراقبة تعمل")
        except RuntimeError as exc:
            sentry_sdk.capture_exception(exc)
        sentry_sdk.flush(timeout=5)
        return True
    except Exception:                              # noqa: BLE001
        return False

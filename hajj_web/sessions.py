"""مخزن جلسات الويب في ذاكرة الخادم.

مفتاح فك التشفير (``data_key``) يبقى في **ذاكرة الخادم فقط**، تماماً كما
يبقى في ذاكرة برنامج سطح المكتب — لا يُوضع في كوكيّ المتصفّح ولا على القرص.
الكوكيّ يحمل *رمزاً* عشوائياً فقط يشير إلى الجلسة المخزّنة هنا.
"""

from __future__ import annotations

import secrets
import threading

from hajj_app.auth import Session

_LOCK = threading.Lock()
_SESSIONS: dict[str, Session] = {}


def create(session: Session) -> str:
    """يخزّن جلسة ويعيد رمزاً عشوائياً يوضع في الكوكيّ."""
    token = secrets.token_urlsafe(32)
    with _LOCK:
        _SESSIONS[token] = session
    return token


def get(token: str | None) -> Session | None:
    if not token:
        return None
    with _LOCK:
        return _SESSIONS.get(token)


def destroy(token: str | None) -> None:
    if not token:
        return
    with _LOCK:
        _SESSIONS.pop(token, None)

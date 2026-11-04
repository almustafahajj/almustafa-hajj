# -*- coding: utf-8 -*-
"""الأجهزة المعروفة لكل حساب، لتنبيه صاحبه عند الدخول من جهاز جديد.

كل متصفّح يحمل ملف ارتباط طويل الأمد برمز عشوائي؛ يُحفظ هنا بصمته فقط.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path

COOKIE = "alm_dev"
MAX_PER_USER = 30
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,64}$")
_LOCK = threading.Lock()


def valid_token(tok: str | None) -> bool:
    return bool(tok and _TOKEN_RE.match(tok))


def _path() -> Path:
    from hajj_app.paths import data_dir
    return Path(data_dir()) / "known_devices.json"


def _load() -> dict:
    try:
        d = json.loads(_path().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _h(tok: str) -> str:
    return hashlib.sha256(("dev:" + tok).encode("utf-8")).hexdigest()[:32]


def remember(username: str, tok: str, label: str = "") -> tuple[bool, bool]:
    """يسجّل الجهاز للحساب. يعيد (جهاز جديد؟، كان للحساب أجهزة قبله؟)."""
    key, h, now = (username or "").strip().lower(), _h(tok), time.time()
    with _LOCK:
        d = _load()
        devs = d.setdefault(key, [])
        hit = next((x for x in devs if x.get("h") == h), None)
        had_any = bool(devs)
        if hit:
            hit["last"] = now
        else:
            devs.append({"h": h, "label": label[:80], "first": now, "last": now})
            devs.sort(key=lambda x: -x.get("last", 0))
            del devs[MAX_PER_USER:]
        p = _path()
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, p)
    return hit is None, had_any

"""سجلّ التدقيق: يسجّل من فعل ماذا ومتى (إضافة/تعديل/حذف/مسح/استيراد…).

يُكتب سطراً JSON لكل عملية في ``data/audit.log`` (إلحاق فقط)، ويُقرأ الأحدث
أولاً للعرض. تصميم بسيط ومتين: السطر التالف يُتجاهَل ولا يُعطّل القراءة.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from . import storage

_MAX_KEEP = 5000        # نُبقي آخر هذا العدد من القيود عند التقليم


def audit_path() -> Path:
    """مسار ملفّ سجلّ التدقيق (بجوار ملفّ البيانات).

    يُحلّ عبر ``storage`` ديناميكياً كي يتبع عزل الاختبارات لمسار البيانات.
    """
    return storage.default_data_path().parent / "audit.log"


def record(action: str, details: str = "", user: str = "—",
           path: str | Path | None = None) -> None:
    """يُلحق قيداً بالسجلّ. لا يرفع استثناءً كي لا يُعطّل العملية الأصلية."""
    p = Path(path) if path else audit_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": datetime.now().replace(microsecond=0).isoformat(),
            "user": str(user or "—"),
            "action": str(action or ""),
            "details": str(details or ""),
        }
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def read_entries(limit: int = 1000,
                 path: str | Path | None = None) -> list[dict]:
    """يعيد آخر ``limit`` قيداً، الأحدث أولاً (يتجاهل الأسطر التالفة)."""
    p = Path(path) if path else audit_path()
    if not p.is_file():
        return []
    out: list[dict] = []
    try:
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    continue
                if isinstance(obj, dict):
                    out.append(obj)
    except OSError:
        return []
    return list(reversed(out[-limit:]))


def clear_log(path: str | Path | None = None) -> None:
    """يفرّغ السجلّ (يُستعمل من نافذة العرض بتأكيد)."""
    p = Path(path) if path else audit_path()
    try:
        if p.is_file():
            p.write_text("", encoding="utf-8")
    except OSError:
        pass


def prune(path: str | Path | None = None, keep: int = _MAX_KEEP) -> None:
    """يقصّ السجلّ إلى آخر ``keep`` قيداً إن تجاوزها (صيانة اختيارية)."""
    p = Path(path) if path else audit_path()
    if not p.is_file():
        return
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
        if len(lines) > keep:
            p.write_text("\n".join(lines[-keep:]) + "\n", encoding="utf-8")
    except OSError:
        pass

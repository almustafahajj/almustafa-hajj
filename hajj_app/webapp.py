"""نسخة ويب محلية (نموذج أوّلي) — خادم من مكتبة Python القياسية.

يعيد استخدام منطق البرنامج كما هو (التخزين، الحقول، إكسل، الـ PDF)، ويقدّم
واجهة متصفّح للعرض والإضافة والتعديل والحذف والتصدير. يعمل **محلياً** على
جهازك؛ البيانات تبقى عندك في ملفٍّ مستقلّ (``hajjaj-web.json``) لا يمسّ
ملفّ سطح المكتب المشفّر.
"""

from __future__ import annotations

import json
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .excel_io import export_excel
from .fields import (EDITABLE, MONEY_KEYS, TIME_KEYS, format_amount,
                     normalize_time, parse_amount, row_dict)
from .mrz import PassportData
from .pdf_io import export_pdf
from .storage import default_data_path, load_records, save_records

_WEB_DIR = Path(__file__).resolve().parent / "web"

# أعمدة الجدول المعروضة (مفتاح، عنوان)
TABLE_COLUMNS = (
    ("serial", "م"),
    ("full_name_ar", "اسم الحاج"),
    ("passport_number", "رقم الجواز"),
    ("phone", "الهاتف"),
    ("program", "البرنامج"),
    ("hotel", "الفندق"),
    ("room_type", "الغرفة"),
    ("program_value", "القيمة"),
    ("paid_amount", "المدفوع"),
    ("remaining_amount", "المتبقّي"),
)

# حقول نموذج الإضافة/التعديل (مختصرة للنموذج الأوّلي)
FORM_FIELDS = (
    "family_number", "reference_number", "full_name_ar", "full_name_en",
    "phone", "program", "hotel", "room_type", "room_number", "nationality_ar",
    "sex", "passport_number", "birth_date", "expiry_date", "airline",
    "arrival_date", "departure_date", "program_value", "paid_amount", "notes",
)

_EDITABLE_KEYS = {f.key for f in EDITABLE}
_LABELS = {f.key: f.label for f in EDITABLE}


def web_data_path() -> Path:
    """مسار بيانات نسخة الويب (مستقلّ عن ملفّ سطح المكتب)."""
    return default_data_path().parent / "hajjaj-web.json"


class WebState:
    """حالة الكشف في الذاكرة + الحفظ. قابلة للاختبار بمعزل عن الـ HTTP."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else web_data_path()
        self.records, _note = load_records(self.path, session=None)
        self._lock = threading.Lock()

    # ---- قراءة ----
    def rows(self) -> list[dict]:
        return [row_dict(r, i + 1) for i, r in enumerate(self.records)]

    def meta(self) -> dict:
        return {
            "columns": [{"key": k, "label": lbl} for k, lbl in TABLE_COLUMNS],
            "form": [{"key": k, "label": _LABELS.get(k, k)} for k in FORM_FIELDS],
        }

    # ---- تعديل ----
    def _clean(self, data: dict) -> dict:
        out = {}
        for key, raw in (data or {}).items():
            if key not in _EDITABLE_KEYS:
                continue
            val = str(raw).strip()
            if key in TIME_KEYS:
                val = normalize_time(val)
            elif key in MONEY_KEYS:
                amt = parse_amount(val)
                if amt is not None:
                    val = format_amount(amt)
            out[key] = val
        return out

    def add(self, data: dict) -> PassportData:
        with self._lock:
            rec = PassportData(source_file="إدخال ويب")
            for k, v in self._clean(data).items():
                setattr(rec, k, v)
            self.records.append(rec)
            self._save()
            return rec

    def update(self, index: int, data: dict) -> bool:
        with self._lock:
            if not 0 <= index < len(self.records):
                return False
            rec = self.records[index]
            for k, v in self._clean(data).items():
                setattr(rec, k, v)
            rec.warnings = []
            self._save()
            return True

    def delete(self, index: int) -> bool:
        with self._lock:
            if not 0 <= index < len(self.records):
                return False
            del self.records[index]
            self._save()
            return True

    def _save(self) -> None:
        save_records(self.records, self.path, session=None)

    # ---- تصدير ----
    def export(self, kind: str) -> tuple[bytes, str, str]:
        """يعيد (المحتوى، اسم الملف، نوع MIME) لتصدير إكسل أو PDF."""
        suffix = "xlsx" if kind == "excel" else "pdf"
        with tempfile.NamedTemporaryFile(suffix=f".{suffix}", delete=False) as fh:
            tmp = Path(fh.name)
        try:
            if kind == "excel":
                export_excel(self.records, tmp)
                mime = ("application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet")
            else:
                export_pdf(self.records, tmp)
                mime = "application/pdf"
            data = tmp.read_bytes()
        finally:
            try:
                tmp.unlink()
            except OSError:
                pass
        return data, f"كشف_الحجاج.{suffix}", mime


# ======================================================================
#  طبقة HTTP
# ======================================================================

def _make_handler(state: WebState):
    class Handler(BaseHTTPRequestHandler):
        server_version = "HajjWeb/0.1"

        def log_message(self, *a):        # كتم سجلّ الطلبات
            pass

        def _send(self, code, body=b"", ctype="application/json; charset=utf-8",
                  extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if body:
                self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return {}
            try:
                return json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return {}

        # ---- المسارات ----
        def do_GET(self):
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                html = (_WEB_DIR / "index.html").read_bytes()
                return self._send(200, html, "text/html; charset=utf-8")
            if path == "/api/records":
                return self._json({"meta": state.meta(), "rows": state.rows()})
            if path in ("/api/export/excel", "/api/export/pdf"):
                kind = "excel" if path.endswith("excel") else "pdf"
                data, name, mime = state.export(kind)
                from urllib.parse import quote
                return self._send(200, data, mime, extra={
                    "Content-Disposition":
                        f"attachment; filename*=UTF-8''{quote(name)}"})
            return self._json({"error": "not found"}, 404)

        def do_POST(self):
            if urlparse(self.path).path == "/api/records":
                rec = state.add(self._body())
                return self._json({"ok": True,
                                   "name": rec.full_name_ar or "—"}, 201)
            return self._json({"error": "not found"}, 404)

        def do_PUT(self):
            path = urlparse(self.path).path
            if path.startswith("/api/records/"):
                try:
                    idx = int(path.rsplit("/", 1)[1])
                except ValueError:
                    return self._json({"error": "bad index"}, 400)
                ok = state.update(idx, self._body())
                return self._json({"ok": ok}, 200 if ok else 404)
            return self._json({"error": "not found"}, 404)

        def do_DELETE(self):
            path = urlparse(self.path).path
            if path.startswith("/api/records/"):
                try:
                    idx = int(path.rsplit("/", 1)[1])
                except ValueError:
                    return self._json({"error": "bad index"}, 400)
                ok = state.delete(idx)
                return self._json({"ok": ok}, 200 if ok else 404)
            return self._json({"error": "not found"}, 404)

    return Handler


def make_server(host: str = "127.0.0.1", port: int = 8000,
                path: str | Path | None = None) -> ThreadingHTTPServer:
    """يبني خادماً جاهزاً (لا يبدأ التشغيل) — للاختبار والتشغيل."""
    state = WebState(path)
    return ThreadingHTTPServer((host, port), _make_handler(state))


def main() -> None:
    host, port = "127.0.0.1", 8000
    server = make_server(host, port)
    url = f"http://{host}:{port}/"
    print(f"برنامج الحج — نسخة الويب المحلية على: {url}")
    print("للإيقاف: Ctrl+C")
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nتم الإيقاف.")
        server.shutdown()


if __name__ == "__main__":
    main()

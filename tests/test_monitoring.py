# -*- coding: utf-8 -*-
"""البورتال: مراقبة الأخطاء (Sentry) — معطّلة بلا SENTRY_DSN، وعند تفعيلها لا يخرج
أي محتوى نماذج أو بحث أو رقم جواز/هاتف؛ ولوحة المدير وزرّ الخطأ التجريبي."""
import io, json, os, sys, tempfile
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HAJJ_DATA_DIR"] = tempfile.mkdtemp(prefix="monitor_")
os.environ.pop("SENTRY_DSN", None)
from hajj_app import auth  # noqa: E402
try:
    from webapp import server, monitoring
    server.app.config["CSRF_ENABLED"] = False
except ImportError as exc:
    print(f"[skip] مسارات الويب: {exc}"); print("ALL OK"); sys.exit(0)

# ---- ١) بلا SENTRY_DSN: لا شيء يتغيّر ----
assert monitoring.ENABLED is False, "المراقبة معطّلة افتراضياً"
assert monitoring.init(server.app, dsn="") is False and monitoring.ENABLED is False
assert monitoring.send_test() is False

# ---- ٢) التنظيف قبل الإرسال (دون شبكة) ----
assert monitoring.clean_url("https://x.app/v/AbCdEf123456789xyz?q=أحمد") == "/v/:id"
assert monitoring.clean_url("https://x.app/hujjaj/12/docs?q=1") == "/hujjaj/12/docs"
m = monitoring.mask("جواز P1234567 وAB123456 هاتف 0501234567 و+971 50 123 4567 بريد sara.x@gmail.com سطر 120")
for bad in ("P1234567", "AB123456", "0501234567", "123 4567", "sara.x@gmail.com"):
    assert bad not in m, (bad, m)
assert "سطر 120" in m, "الأرقام القصيرة (سطر الخطأ) تبقى"
ev = {"request": {"method": "POST", "url": "https://x.app/doc/0/receipt/pdf?q=سالم",
                  "data": {"name": "أحمد سالم", "passport": "P7654321"},
                  "cookies": {"session": "s3cr3t"}, "headers": {"Cookie": "session=s3cr3t"},
                  "query_string": "q=سالم", "env": {"REMOTE_ADDR": "1.2.3.4"}},
      "user": {"ip_address": "1.2.3.4"}, "extra": {"rec": "أحمد"},
      "breadcrumbs": {"values": [{"message": "P7654321"}]},
      "exception": {"values": [{"type": "ValueError", "value": "bad passport P7654321",
                                "stacktrace": {"frames": [{"function": "f", "vars": {"name": "أحمد سالم"}}]}}]},
      "logentry": {"message": "phone %s", "params": ["0509998887"], "formatted": "phone 0509998887"}}
out = json.dumps(monitoring.scrub(ev), ensure_ascii=False)
for bad in ("أحمد", "سالم", "P7654321", "s3cr3t", "1.2.3.4", "0509998887", "vars", "breadcrumbs"):
    assert bad not in out, (bad, out)
assert ev["request"] == {"method": "POST", "url": "/doc/0/receipt/pdf"}
assert ev["exception"]["values"][0]["type"] == "ValueError", "نوع الخطأ يبقى"

# ---- ٣) تفعيل حقيقي بناقل محلّي يلتقط ما كان سيُرسل ----
from sentry_sdk.transport import Transport  # noqa: E402
EVENTS = []


class Cap(Transport):
    def capture_envelope(self, envelope):
        for item in envelope.items:
            got = item.get_event()
            if got:
                EVENTS.append(got)


assert monitoring.init(server.app, dsn="https://abc@o0.ingest.sentry.io/1", transport=Cap) is True
assert monitoring.ENABLED is True


# القيم تُركَّب هنا كي لا تظهر حرفياً في سطور الشيفرة التي يعرضها Sentry مع الخطأ
# (سطور برنامج البورتال نفسه لا تحمل بيانات معتمرين)
_PP, _PH = "P12" + "34567", "050" + "1234567"


def _boom():
    from flask import request
    request.get_data()
    raise ValueError(f"تعذّر حفظ جواز {_PP} للهاتف {_PH}")


server.app.add_url_rule("/_boom_test", "boom_test", _boom, methods=["GET", "POST"])

owner, _rk = auth.create_account("owner", "Passw0rd!x")
auth.add_account(owner, "sara", "Passw0rd!s", role="editor")
auth.add_account(owner, "view", "Passw0rd!v", role="viewer")
c = server.app.test_client()
c.post("/login", data={"username": "owner", "password": "Passw0rd!x"})
e = server.app.test_client()
e.post("/login", data={"username": "sara", "password": "Passw0rd!s"})
v = server.app.test_client()
v.post("/login", data={"username": "view", "password": "Passw0rd!v"})

r = c.post("/_boom_test?q=أحمد سالم العلي", json={"full_name_ar": "أحمد سالم العلي",
                                                   "passport_number": "P1234567"})
assert r.status_code == 500
assert len(EVENTS) == 1, EVENTS
_ev = json.loads(json.dumps(EVENTS[0]))
for _x in _ev.get("exception", {}).get("values", []):     # سطور الشيفرة نفسها ليست بيانات
    for _fr in (_x.get("stacktrace") or {}).get("frames", []):
        for _k in ("pre_context", "context_line", "post_context"):
            _fr.pop(_k, None)
blob = json.dumps(_ev, ensure_ascii=False)
for bad in ("أحمد", "P1234567", "0501234567", "Passw0rd", "session=", "full_name_ar"):
    assert bad not in blob, ("تسرّب إلى Sentry", bad, blob[max(0, blob.find(bad) - 300):blob.find(bad) + 60])
assert EVENTS[0]["request"] == {"method": "POST", "url": "/_boom_test"}, EVENTS[0]["request"]
assert EVENTS[0]["exception"]["values"][-1]["type"] == "ValueError"
assert "[جواز]" in EVENTS[0]["exception"]["values"][-1]["value"]
assert "user" not in EVENTS[0]

# ---- ٤) لوحة المدير: الحالة + زرّ الخطأ التجريبي + رابط مراقبة التوقّف ----
page = c.get("/backup").get_data(as_text=True)
assert "مراقبة الأخطاء والتوقّف" in page and 'action="/backup/monitor-test"' in page and "/healthz" in page
assert "مفعّلة — أي خطأ" in page
r = c.post("/backup/monitor-test")
assert r.status_code == 302
assert "أُرسل خطأ تجريبي" in c.get("/backup").get_data(as_text=True)
assert any("خطأ تجريبي" in json.dumps(x, ensure_ascii=False) for x in EVENTS[1:]), "وصل الخطأ التجريبي"
n = len(EVENTS)
for cl in (e, v):                                  # المحرّر والمطّلع لا يرسلان
    r = cl.post("/backup/monitor-test")
    assert r.status_code == 302 and "/backup" not in r.headers.get("Location", "")
assert len(EVENTS) == n
assert "مراقبة الأخطاء" not in e.get("/backup", follow_redirects=True).get_data(as_text=True)

# ---- ٥) عند التعطيل: خطوات الإعداد ظاهرة للمدير، والزرّ يشرح السبب ----
monitoring.ENABLED = False
page = c.get("/backup").get_data(as_text=True)
assert "غير مفعّلة" in page and "SENTRY_DSN" in page and "sentry.io" in page
assert 'action="/backup/monitor-test"' not in page, "لا زرّ تجربة قبل التفعيل"
c.post("/backup/monitor-test")
assert "أضف SENTRY_DSN" in c.get("/backup").get_data(as_text=True)

# ---- ٦) فحص عمل الموقع لمراقبة التوقّف ----
h = server.app.test_client().get("/healthz")
assert h.status_code == 200 and h.get_json() == {"status": "ok"}
print("ALL OK")

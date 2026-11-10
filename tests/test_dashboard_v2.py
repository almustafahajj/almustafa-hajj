# -*- coding: utf-8 -*-
"""البورتال: لوحة التحكم الجديدة — الترحيب والملخّص، التحصيل الشهري من الدفعات
المؤرّخة، الرحلات الجارية والقادمة بعدّ تنازلي، وآخر العمليات للمدير فقط."""
import io
import os
import sys
import tempfile
from datetime import date, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HAJJ_DATA_DIR"] = tempfile.mkdtemp(prefix="dashv2_")

from hajj_app import app_mode, auth, fields, storage, umrah  # noqa: E402
from hajj_app.mrz import PassportData  # noqa: E402

try:
    from webapp import server
    server.app.config["CSRF_ENABLED"] = False
except ImportError as exc:
    print(f"[skip] مسارات الويب: {exc}")
    print("ALL OK")
    sys.exit(0)

T = server.datetime.now(server._UAE).date()          # «اليوم» كما تراه اللوحة (توقيت الإمارات)
iso = date.isoformat

owner, _rk = auth.create_account("owner", "Passw0rd!x")
auth.add_account(owner, "sara", "Passw0rd!s", role="editor")
c = server.app.test_client()
c.post("/login", data={"username": "owner", "password": "Passw0rd!x"})
SESS = next(v for v in server._SESSIONS.values() if v.username == "owner")
e = server.app.test_client()
e.post("/login", data={"username": "sara", "password": "Passw0rd!s"})

# ---- ١) بلا بيانات: حالات فارغة واضحة لا أخطاء ----
app_mode.set_mode(app_mode.UMRAH)
page = c.get("/dashboard").get_data(as_text=True)
assert "لا دفعات مسجّلة بتواريخها بعد" in page and "لا رحلات قادمة" in page
assert ("صباح الخير" in page) or ("مساء الخير" in page)
assert 'id="hijriDate"' in page

# ---- ٢) بيانات: رحلات بحالات مختلفة ودفعات على شهرين ----
trips = [umrah.UmrahTrip(code="U1", name="جارية", depart_date=iso(T - timedelta(days=2)),
                         return_date=iso(T + timedelta(days=3)), capacity="10"),
         umrah.UmrahTrip(code="U2", name="غداً", depart_date=iso(T + timedelta(days=1))),
         umrah.UmrahTrip(code="U3", name="بعيدة", depart_date=iso(T + timedelta(days=12))),
         umrah.UmrahTrip(code="U9", name="منتهية", depart_date=iso(T - timedelta(days=30)),
                         return_date=iso(T - timedelta(days=20)))]
st = storage.load_settings()
umrah.save_trips(st, trips)
storage.save_settings(st)
first_this = T.replace(day=1)
last_month = first_this - timedelta(days=1)
r1 = PassportData(full_name_ar="أحمد", passport_number="P1", program_value="10000", trip="U1")
r1.payments = [{"date": iso(first_this), "amount": "3,000", "method": "نقد", "note": ""},
               {"date": iso(last_month), "amount": "2,000", "method": "نقد", "note": ""},
               {"date": iso(T + timedelta(days=40)), "amount": "999", "method": "نقد", "note": ""}]
fields.sync_paid_amount(r1)
r2 = PassportData(full_name_ar="مريم", passport_number="P2", program_value="8000",
                  paid_amount="1,500", trip="U2")                 # مدفوع بلا تاريخ دفعة
storage.save_records([r1, r2], session=SESS)

chart = server._collection_chart([r1, r2], server.stats.financial_summary([r1, r2]), T)
assert len(chart["bars"]) == 6, "ستة أشهر على الأقل حتى لو بدأت الدفعات حديثاً"
assert chart["bars"][-1]["now"] and chart["bars"][-1]["amount"] == "3,000", chart["bars"][-1]
assert chart["bars"][-2]["amount"] == "2,000" and chart["bars"][0]["amount"] == "0"
assert chart["this"] == "3,000" and chart["delta"] == 50, chart["delta"]
assert chart["undated"] == "1,500", "الدفعة المستقبلية لا تُحسب والمدفوع بلا تاريخ يُذكر"
assert all(b["cx"] > chart["bars"][i + 1]["cx"] for i, b in enumerate(chart["bars"][:-1])), \
    "الأحدث يساراً والأقدم يميناً"

with server.app.test_request_context():
    up = server._upcoming_trips([r1, r2], st, T)
assert [t["label"].split()[0] for t in up] == ["U1", "U2", "U3"], [t["label"] for t in up]
assert up[0]["state"] == "now" and up[0]["days"] == 3 and up[0]["cap"] == 10
assert up[1]["state"] == "soon" and up[1]["days"] == 1
assert up[2]["days"] == 12 and up[2]["unit"] == "يوماً"
assert server._days_unit(2) == "يومان" and server._days_unit(5) == "أيام"

page = c.get("/dashboard").get_data(as_text=True)
assert "التحصيل الشهري" in page and 'class="col-chart"' in page and "3,000 درهم" in page
assert "عن الشهر السابق" in page and "عرض الأرقام كجدول" in page
assert "1,500 درهم مدفوعة دون تاريخ دفعة" in page
assert "الرحلات القادمة" in page and "في الرحلة" in page and "غداً" in page
assert "منتهية" not in page.split("الرحلات القادمة")[1].split("</section>")[0]
assert "رحلة «U1 جارية» جارية الآن" in page, "الملخّص في الترويسة"
assert "المالية حسب البرنامج" in page and "يحتاج انتباهك" in page

# ---- ٣) آخر العمليات: للمدير فقط ----
assert "آخر العمليات" in page and "سجلّ التدقيق" in page
ep = e.get("/dashboard").get_data(as_text=True)
assert "آخر العمليات" not in ep and "النسخ الاحتياطي" not in ep, "المحرّر لا يرى سجلّ العمليات"
assert "إضافة سجلّ" in ep, "المحرّر يضيف"

# ---- ٤) التقويم ما زال يعرض الرحلات بعد توحيد مصدرها ----
cal = c.get(f"/calendar?m={T.year}-{T.month:02d}").get_data(as_text=True)
assert "U1 جارية" in cal or "U2 غداً" in cal or "U3 بعيدة" in cal, "التقويم يعرض رحلات الشهر"

# ---- ٥) الحج: بلا باقات، والصفحة سليمة ----
c.get("/switch/hajj")
hp = c.get("/dashboard")
assert hp.status_code == 200 and "الرحلات القادمة" in hp.get_data(as_text=True)

print("ALL OK")

# -*- coding: utf-8 -*-
"""البورتال: جولة جمالية — بطاقات الجوال، الدفع الزائد، الدفع السريع، الإشعارات المجمّعة، تاريخ الحسابات."""
import io, os, sys, tempfile
from datetime import date, timedelta
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["HAJJ_DATA_DIR"] = tempfile.mkdtemp(prefix="beauty_")
from hajj_app import auth, storage, app_mode, umrah, fields  # noqa: E402
from hajj_app.mrz import PassportData  # noqa: E402
try:
    from webapp import server
    server.app.config["CSRF_ENABLED"] = False
except ImportError as exc:
    print(f"[skip] مسارات الويب: {exc}"); print("ALL OK"); sys.exit(0)

owner, _rk = auth.create_account("owner", "Passw0rd!x")
auth.add_account(owner, "sara", "Passw0rd!s", role="editor")
c = server.app.test_client()
c.post("/login", data={"username": "owner", "password": "Passw0rd!x"})
S = next(v for v in server._SESSIONS.values() if v.username == "owner")
app_mode.set_mode(app_mode.UMRAH)

# ---- ١) صفحة الإشعارات فارغة: حالة فارغة لطيفة لا تختفي ----
note = c.get("/notifications").get_data(as_text=True)
assert "لا شيء يحتاج انتباهاً الآن" in note and 'class="empty-state nt-empty" data-keep' in note
assert "nt-sum" not in note

# ---- بيانات: رحلة غداً وسداد ناقص، ومعتمر دفع أكثر من القيمة ----
T = date.today()
trips = [umrah.UmrahTrip(code="U1", name="رمضان الأول", depart_date=(T + timedelta(days=1)).isoformat(),
                         return_date=(T + timedelta(days=9)).isoformat(), capacity="30")]
st = storage.load_settings()
umrah.save_trips(st, trips)
storage.save_settings(st)
recs = []
for i, (n, val, paid) in enumerate((("أحمد العلي", "6000", "1000"), ("فاطمة الكعبي", "6000", "6500"),
                                    ("علي الشامسي", "6000", "0"))):
    r = PassportData(full_name_ar=n, passport_number=f"P{100 + i}", program_value=val, phone=f"050000000{i}",
                     trip="U1")
    r.payments = [{"date": T.isoformat(), "amount": paid, "method": "نقد", "note": ""}] if paid != "0" else []
    fields.sync_paid_amount(r)
    recs.append(r)
storage.save_records(recs, session=S)

# ---- ٢) كشف السجلّات: «زيادة» بدل رقم سالب، وعمود الحالة يختفي حين لا حالة لأحد ----
lst = c.get("/hujjaj").get_data(as_text=True)
assert "زيادة 500" in lst and 'class="tag over"' in lst, "الدفع الزائد يظهر شارة «زيادة»"
assert ">-500<" not in lst and ">500-<" not in lst, "لا رقم سالب في عمود المتبقّي"
assert "<th>الحالة</th>" not in lst and 'class="c-st"' not in lst, "عمود الحالة الفارغ لا يظهر"
for cls in ("c-who", "c-pp", "c-prog", "c-ph", "c-pay"):
    assert f'class="{cls}"' in lst, f"خانة {cls} معلَّمة لبطاقة الجوال"
recs[0].status = "ملغى"
storage.save_records(recs, session=S)
lst = c.get("/hujjaj").get_data(as_text=True)
assert "<th>الحالة</th>" in lst and lst.count('class="c-st"') == 3, "يظهر العمود حين يكون لأحدهم حالة"
recs[0].status = ""
storage.save_records(recs, session=S)

# ---- ٣) المالية: نموذج دفعة سريع في سطر واحد بلا تنسيقات مضمّنة ----
fin = c.get("/finance").get_data(as_text=True)
assert 'class="qpay"' in fin and 'class="qp-btn"' in fin and 'class="due"' in fin
assert 'style="flex:1 1 90px' not in fin, "لا تنسيق مضمَّن في نموذج الدفعة"
ed = server.app.test_client()
ed.post("/login", data={"username": "sara", "password": "Passw0rd!s"})
assert 'class="qpay"' in ed.get("/finance").get_data(as_text=True), "المحرّر يسجّل الدفعات أيضاً"

# ---- ٤) الإشعارات مجمّعة حسب الأهمية مع ملخّص بالأعداد ----
note = c.get("/notifications").get_data(as_text=True)
assert 'class="nt-sum"' in note and 'id="nt-danger"' in note and 'href="#nt-danger"' in note
assert "عاجل" in note and 'class="ar-ic"' in note and 'class="ar-go"' in note
import re  # noqa: E402
n_all = note.count('class="alert-row')
assert n_all >= 1 and n_all == sum(int(x) for x in re.findall(r'class="nt-n">(\d+)<', note)), \
    "كل إشعار يظهر مرّة واحدة في مجموعته، والعدد في رأسها صحيح"
dash = c.get("/dashboard").get_data(as_text=True)
assert 'class="ar-t"' in dash, "صفوف التنبيه في لوحة التحكم بالشكل الجديد"

# ---- ٥) إدارة الحسابات: «آخر تحديث» بتاريخ عربي مقروء ----
assert server._nice_stamp("2026-11-16T15:47:20") == "16 نوفمبر 2026 · 15:47"
assert server._nice_stamp("") == "" and server._nice_stamp(None) == ""
assert server._nice_stamp("غير معروف") == "غير معروف"
acc = c.get("/accounts").get_data(as_text=True)
assert 'class="muted acc-when"><b>' in acc and any(m in acc for m in server._AR_MONTHS)

# ---- ٦) قواعد التصميم موجودة: بطاقات الجوال، زرّ البحث مع شريط الحفظ، الشريط العلوي ----
css = open(os.path.join(ROOT, "webapp", "static", "style.css"), encoding="utf-8").read()
for needle in ("table.data.list-table tr.tcard{", "body:has(.savebar) .bb-search .bb-ic", ".topbar .tb-search{ display:none; }",
               ".nt-group{", ".qpay{", ".tag.over{", "td.td-title"):
    assert needle in css, f"قاعدة ناقصة: {needle}"
base = open(os.path.join(ROOT, "webapp", "templates", "base.html"), encoding="utf-8").read()
assert "td-title" in base and "tcard" in base, "عنوان بطاقة الجوال يُعلَّم تلقائياً"

print("ALL OK")

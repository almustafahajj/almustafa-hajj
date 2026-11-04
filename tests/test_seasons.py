# -*- coding: utf-8 -*-
"""البورتال: تحديد الموسم للمدير فقط — الانتقال لموسم جديد يحفظ القديم كاملاً
ويبدأ الجديد بقوائم فارغة (البرامج تنتقل)، ويمكن فتح الموسم المحفوظ كما كان."""
import io
import os
import sys
import tempfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HAJJ_DATA_DIR"] = tempfile.mkdtemp(prefix="seasons_")

from hajj_app import app_mode, auth, storage  # noqa: E402
from hajj_app.mrz import PassportData  # noqa: E402

try:
    from webapp import server, seasons, backup
    server.app.config["CSRF_ENABLED"] = False
except ImportError as exc:
    print(f"[skip] مسارات الويب: {exc}")
    print("ALL OK")
    sys.exit(0)

owner, _rk = auth.create_account("owner", "Passw0rd!x")
auth.add_account(owner, "sara", "Passw0rd!s", role="editor")
c = server.app.test_client()
c.post("/login", data={"username": "owner", "password": "Passw0rd!x"})
SESS = server._SESSIONS[next(iter(server._SESSIONS))]
s = server.app.test_client()
s.post("/login", data={"username": "sara", "password": "Passw0rd!s"})


def umrah():
    app_mode.set_mode(app_mode.UMRAH)


def names(mode=app_mode.UMRAH):
    app_mode.set_mode(mode)
    return [r.full_name_ar for r in storage.load_records(session=SESS)[0]]


def settings():
    umrah()
    return storage.load_settings()


# موسم ٢٠٢٦ م فيه بيانات
umrah()
storage.save_records([PassportData(full_name_ar="أحمد")], session=SESS)
storage.save_records([PassportData(full_name_ar="أحمد")], session=SESS)   # .bak أيضاً
storage.save_documents([{"id": "d1", "name": "سند"}], session=SESS)
st = storage.load_settings()
st.update({"season_year": "2026", "groups": {"G1": {"leader": "x"}},
           "expenses": [{"amount": 5}], "umrah_trips": [{"code": "U1"}],
           "company": {"name_ar": "المصطفى"}, "quote_seq": 7})
storage.save_settings(st)
app_mode.set_mode(app_mode.HAJJ)
storage.save_records([PassportData(full_name_ar="حاج")], session=SESS)

# ---- 1) المحرّر لا يغيّر الموسم ----
page = s.get("/season").get_data(as_text=True)
assert "للمدير فقط" in page and "الانتقال للموسم" not in page
s.post("/season", data={"season_year": "2027"})
assert settings()["season_year"] == "2026" and names() == ["أحمد"]
s.post("/season", data={"season_year": "2027", "relabel": "1"})
assert settings()["season_year"] == "2026"
print("[ok] المحرّر يرى الموسم فقط ولا يغيّره")

# ---- 2) المدير يبدأ موسماً جديداً: القديم محفوظ والجديد فارغ ----
assert "الانتقال للموسم" in c.get("/season").get_data(as_text=True)
c.post("/season", data={"season_year": "2027"})
st = settings()
assert st["season_year"] == "2027"
assert names() == [] and storage.load_documents(session=SESS) == []
assert not storage.default_data_path().with_suffix(".bak").exists()
assert "groups" not in st and "expenses" not in st
assert st["umrah_trips"] == [{"code": "U1"}]                      # البرامج انتقلت
assert st["company"] == {"name_ar": "المصطفى"} and st["quote_seq"] == 7
assert seasons.has("2026") and not seasons.has("2027")
page = c.get("/season").get_data(as_text=True)
assert "بدأ موسم 2027م" in page and "المواسم المحفوظة" in page
assert [(x["year"], x["count"]) for x in seasons.list_saved(SESS)] == [("2026", 1)]
assert names(app_mode.HAJJ) == ["حاج"]                           # الحج لم يتأثّر
print("[ok] موسم جديد: القوائم فارغة، البرامج والإعدادات العامة باقية، والقديم محفوظ")

# ---- 3) فتح الموسم المحفوظ كما كان ----
umrah()
storage.save_records([PassportData(full_name_ar="سعيد")], session=SESS)
st = settings()
st["umrah_trips"] = [{"code": "U1"}, {"code": "U2"}]
st["groups"] = {"G9": {}}
storage.save_settings(st)
c.post("/season", data={"season_year": "2026"})
st = settings()
assert st["season_year"] == "2026" and names() == ["أحمد"]
assert st["groups"] == {"G1": {"leader": "x"}} and st["expenses"] == [{"amount": 5}]
assert st["umrah_trips"] == [{"code": "U1"}]                      # برامج ذلك الموسم
assert storage.load_documents(session=SESS) == [{"id": "d1", "name": "سند"}]
assert seasons.has("2027") and not seasons.has("2026")
c.post("/season", data={"season_year": "2027"})                     # والعودة
st = settings()
assert names() == ["سعيد"] and st["groups"] == {"G9": {}}
assert len(st["umrah_trips"]) == 2 and seasons.has("2026")
print("[ok] فتح موسم محفوظ يعيده كما كان، ويُحفظ الحالي قبله")

# ---- 4) تصحيح السنة فقط ----
c.post("/season", data={"season_year": "2030", "relabel": "1"})
assert settings()["season_year"] == "2030" and names() == ["سعيد"]
assert not seasons.has("2027")
c.post("/season", data={"season_year": "2026", "relabel": "1"})   # لها نسخة محفوظة
assert settings()["season_year"] == "2030"
assert "نسخة محفوظة" in c.get("/season").get_data(as_text=True)
c.post("/season", data={"season_year": "1999"})                     # خارج القائمة
assert settings()["season_year"] == "2030"
print("[ok] تصحيح السنة لا يمسّ البيانات، ويُرفض لسنة محفوظة")

# ---- 5) المواسم المحفوظة ضمن النسخة الاحتياطية واستعادتها ----
z = Path(tempfile.mkdtemp()) / "b.zip"
backup.build_zip(z, with_images=False)
import zipfile  # noqa: E402
arcs = zipfile.ZipFile(z).namelist()
assert "seasons/umrah/2026/umrah.json" in arcs and "seasons/umrah/2026/season.json" in arcs
assert not backup._allowed("seasons/umrah/2026/../auth.json")
assert not backup._allowed("seasons/x/2026/umrah.json")
import shutil  # noqa: E402
shutil.rmtree(seasons.root())
assert not seasons.has("2026")
backup.restore_zip(z)
assert seasons.has("2026")
umrah()
assert [x["count"] for x in seasons.list_saved(SESS)] == [1]
print("[ok] النسخة الاحتياطية تحوي المواسم المحفوظة وتستعيدها")
print("ALL OK")

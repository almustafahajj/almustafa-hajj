"""مولّد «لوحة الموسم» بصيغة صفحة ويب أنيقة (HTML) من بيانات الموسم.

ينتج ملفاً واحداً مستقلّاً (كل التنسيقات مضمّنة) يُفتح في المتصفّح، ويُطبع
أو يُشارك عبر واتساب/الإيميل برابط واحد. الصفحة عربية RTL بهوية الشركة،
وتتكيّف مع الوضع الفاتح/الداكن، وتظهر جيداً على الجوال.

الحساب يطابق تماماً منطق لوحة الموسم داخل البرنامج: لكل برنامج
``قيمة البرنامج`` و``المبلغ المدفوع`` لمعتمريه، والإشغال = العدد ÷ السعة.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

from . import umrah
from .fields import format_amount, parse_amount

_DEFAULT_COMPANY = "المصطفى للحج والعمرة"
_DEFAULT_COMPANY_EN = "Al Mustafa Hajj & Umrah"


def _fmt_date(s: str) -> str:
    """يحوّل ISO (YYYY-MM-DD) إلى DD/MM/YYYY، وإلا يعيد النص كما هو."""
    s = (s or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else s


def _compact(n: float) -> str:
    """صيغة مختصرة للمبالغ الكبيرة: 4.10M / 320K / 850."""
    n = float(n or 0)
    if abs(n) >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if abs(n) >= 1_000:
        return f"{n / 1_000:.0f}K"
    return f"{n:.0f}"


def _status(col_pct: float) -> tuple[str, str]:
    """(صنف الشارة، نصّها) حسب نسبة التحصيل."""
    if col_pct >= 95:
        return "ok", "مكتمل"
    if col_pct >= 75:
        return "mid", "تحصيل جيد"
    if col_pct >= 50:
        return "low", "متابعة"
    return "low", "متأخّر التحصيل"


def season_dashboard_stats(trips: list, records: list,
                           group_attr: str = "trip") -> tuple[list, dict]:
    """صفوف إحصائية لكل برنامج + إجماليات الموسم.

    ``group_attr`` حقل ربط المعتمر/الحاج ببرنامجه: «trip» في العمرة و«program»
    في الحج."""
    rows = []
    tot_total = tot_paid = 0.0
    tot_pil = tot_cap = 0
    for t in trips:
        pilgrims = [r for r in records
                    if str(getattr(r, group_attr, "") or "") == t.code]
        total = sum(parse_amount(r.program_value) or 0.0 for r in pilgrims)
        paid = sum(parse_amount(r.paid_amount) or 0.0 for r in pilgrims)
        count = len(pilgrims)
        cap = int(parse_amount(t.capacity) or 0)
        col_pct = (paid / total * 100) if total else 0.0
        occ_pct = (count / cap * 100) if cap else 0.0
        cls, label = _status(col_pct)
        # خانتا معلومات حسب النوع: فنادق مكة/المدينة (عمرة) أو مطار المغادرة
        # والناقل (حج)
        if group_attr == "program":
            info1 = ("مطار المغادرة", getattr(t, "airport", "") or "—")
            info2 = ("الناقل", getattr(t, "carrier", "") or "—")
        else:
            info1 = ("مكة المكرمة", getattr(t, "makkah_hotel", "") or "—")
            info2 = ("المدينة المنورة", getattr(t, "madinah_hotel", "") or "—")
        rows.append({
            "name": t.name or t.code, "code": t.code,
            "count": count, "capacity": cap,
            "makkah": t.makkah_hotel or "—", "madinah": t.madinah_hotel or "—",
            "info1_label": info1[0], "info1": info1[1],
            "info2_label": info2[0], "info2": info2[1],
            "depart": _fmt_date(getattr(t, "depart_date", "")),
            "return": _fmt_date(getattr(t, "return_date", "")),
            "total": total, "paid": paid,
            "col_pct": col_pct, "occ_pct": occ_pct,
            "status_cls": cls, "status": label,
        })
        tot_total += total
        tot_paid += paid
        tot_pil += count
        tot_cap += cap
    totals = {
        "programs": len(rows), "pilgrims": tot_pil, "capacity": tot_cap,
        "total": tot_total, "paid": tot_paid, "remaining": tot_total - tot_paid,
        "col_pct": (tot_paid / tot_total * 100) if tot_total else 0.0,
        "occ_pct": (tot_pil / tot_cap * 100) if tot_cap else 0.0,
    }
    return rows, totals


def _company_names(company) -> tuple[str, str]:
    """اسم الشركة عربيّ ولاتينيّ من إعداداتها أو الافتراضي."""
    if isinstance(company, dict):
        ar = company.get("name_ar") or company.get("name") or _DEFAULT_COMPANY
        en = company.get("name_en") or _DEFAULT_COMPANY_EN
        return str(ar), str(en)
    return _DEFAULT_COMPANY, _DEFAULT_COMPANY_EN


def _e(text) -> str:
    return html.escape(str(text if text is not None else ""))


def _nouns(kind: str) -> tuple[str, str, str]:
    """(الجمع المرفوع، الجمع المجرور، المفرد المنصوب) حسب نوع الموسم."""
    if kind == "الحج":
        return "الحجّاج", "الحجّاج", "حاجّاً"
    return "المعتمرون", "المعتمرين", "معتمراً"


def render_season_dashboard(rows: list, totals: dict, *, season: str = "",
                            company=None, kind: str = "العمرة") -> str:
    """يبني نصّ HTML كاملاً مستقلّاً للوحة الموسم (عمرة/حج حسب ``kind``)."""
    name_ar, name_en = _company_names(company)
    season = _e(season or "")
    n_nom, n_gen, n_acc = _nouns(kind)
    # الإشغال يظهر فقط حين تتوفّر سعة؛ وإلّا نعرض عدد المعتمرين/الحجّاج
    has_cap = (totals.get("capacity", 0) or 0) > 0

    cards = []
    for r in rows:
        if has_cap:
            occ_metric = (
                f'<div class="metric"><div class="row"><span class="muted">الإشغال</span>'
                f'<b class="num">{r["count"]} / {r["capacity"] or "—"}</b></div>'
                f'<div class="track"><span class="fill-occ" '
                f'style="width:{min(r["occ_pct"],100):.0f}%"></span></div></div>')
        else:
            occ_metric = (
                f'<div class="metric"><div class="row"><span class="muted">{n_nom}</span>'
                f'<b class="num">{r["count"]}</b></div></div>')
        cards.append(f"""
        <article class="card prog">
          <div class="top">
            <div><h3>{_e(r['name'])}</h3><div class="when">{_e(r['depart'])} – {_e(r['return'])}</div></div>
            <span class="pill {r['status_cls']}">{_e(r['status'])}</span>
          </div>
          <div class="hotels">
            <div class="hotel"><div class="city">{_e(r['info1_label'])}</div><div class="name">{_e(r['info1'])}</div></div>
            <div class="hotel"><div class="city">{_e(r['info2_label'])}</div><div class="name">{_e(r['info2'])}</div></div>
          </div>
          <div class="metrics">
            {occ_metric}
            <div class="metric"><div class="row"><span class="muted">التحصيل · <span class="num">{format_amount(r['total'])}</span> AED</span><b class="num">{r['col_pct']:.0f}٪</b></div>
              <div class="track"><span class="fill-col" style="width:{min(r['col_pct'],100):.0f}%"></span></div></div>
          </div>
        </article>""")

    chart = []
    for r in rows:
        chart.append(f"""
        <div class="chrow"><div class="nm">{_e(r['name'])}<span>{_e(r['info1'])} / {_e(r['info2'])}</span></div>
          <div class="chbar"><span style="width:{min(r['col_pct'],100):.0f}%"></span></div>
          <div class="val num">{r['col_pct']:.0f}٪<small>{format_amount(r['paid'])}</small></div></div>""")

    empty = ""
    if not rows:
        empty = ('<p style="text-align:center;color:var(--muted);padding:40px">'
                 'لا توجد برامج في هذا الموسم بعد.</p>')

    return f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>لوحة موسم {season} — {_e(name_ar)}</title>
<style>
{_CSS}
</style>
</head>
<body>
<div class="page">
  <header class="hero">
    <svg class="seal" viewBox="0 0 100 100" aria-hidden="true">
      <g fill="none" stroke="currentColor" stroke-width="1.1">
        <rect x="24" y="24" width="52" height="52"/>
        <rect x="24" y="24" width="52" height="52" transform="rotate(45 50 50)"/>
        <circle cx="50" cy="50" r="37"/><circle cx="50" cy="50" r="30"/>
      </g>
    </svg>
    <div class="wrap">
      <div class="brandrow anim">
        <div><div class="brand-ar">{_e(name_ar)}</div><div class="brand-la">{_e(name_en)}</div></div>
        <div class="stamp">تقرير الموسم · <b>{season}</b></div>
      </div>
      <h1 class="anim d1">لوحة موسم {_e(kind)}</h1>
      <p class="lede anim d2">نظرة شاملة على برامج الموسم: {n_nom}، الإشغال، الإيرادات، ونِسَب التحصيل — في صفحة واحدة تُطبع أو تُشارك.</p>
      <div class="goldrule"></div>
      <div class="kpis anim d3">
        <div class="kpi"><div class="k">إجمالي {n_gen}</div><div class="v num">{totals['pilgrims']}</div></div>
        <div class="kpi"><div class="k">{"نسبة الإشغال" if has_cap else "عدد البرامج"}</div><div class="v num">{(f"{totals['occ_pct']:.0f}") if has_cap else totals['programs']}<small>{"٪" if has_cap else "برنامج"}</small></div></div>
        <div class="kpi"><div class="k">إجمالي الإيراد</div><div class="v num">{_compact(totals['total'])}<small>AED</small></div></div>
        <div class="kpi"><div class="k">نسبة التحصيل</div><div class="v num">{totals['col_pct']:.0f}<small>٪</small></div></div>
      </div>
    </div>
  </header>

  <main class="wrap">
    <section class="sec">
      <div class="sec-head"><span class="eyebrow">Financial</span><h2>الملخّص المالي</h2><div class="rule"></div></div>
      <div class="fin">
        <div class="card stat"><div class="lbl">إجمالي الإيراد المتوقّع</div>
          <div class="big num">{format_amount(totals['total'])}<span class="cur">AED</span></div>
          <div class="sub">من {totals['programs']} برامج · {totals['pilgrims']} {n_acc}</div></div>
        <div class="card stat"><div class="lbl">المبلغ المحصّل</div>
          <div class="big num" style="color:var(--success)">{format_amount(totals['paid'])}</div>
          <div class="sub">{totals['col_pct']:.1f}٪ من الإيراد</div></div>
        <div class="card stat"><div class="lbl">المبلغ المتبقّي</div>
          <div class="big num" style="color:var(--danger)">{format_amount(totals['remaining'])}</div>
          <div class="sub">مستحقّ التحصيل</div></div>
        <div class="card progress">
          <span class="pct num">{totals['col_pct']:.0f}٪</span>
          <div class="bar"><span style="width:{min(totals['col_pct'],100):.1f}%"></span></div>
          <span class="note">التقدّم نحو تحصيل كامل الإيراد</span></div>
      </div>
    </section>

    <section class="sec">
      <div class="sec-head"><span class="eyebrow">Programs</span><h2>برامج الموسم</h2><div class="rule"></div></div>
      <div class="grid">{''.join(cards)}</div>{empty}
    </section>

    <section class="sec">
      <div class="sec-head"><span class="eyebrow">Collection</span><h2>نسبة التحصيل حسب البرنامج</h2><div class="rule"></div></div>
      <div class="card chart">{''.join(chart)}</div>
    </section>
  </main>

  <footer><div class="wrap foot">
    <span class="demo"><span class="dot"></span> تولّدت آلياً من كشف الموسم في البرنامج</span>
    <span>{_e(name_ar)} · لوحة الموسم</span>
  </div></footer>
</div>
</body>
</html>"""


def export_season_dashboard_html(trips: list, records: list, path,
                                 *, season: str = "", company=None,
                                 group_attr: str = "trip",
                                 kind: str = "العمرة") -> Path:
    """يحسب الإحصاءات ويكتب صفحة اللوحة إلى ``path``. يعيد المسار."""
    rows, totals = season_dashboard_stats(trips, records, group_attr)
    out = Path(path)
    out.write_text(
        render_season_dashboard(rows, totals, season=season, company=company,
                                kind=kind),
        encoding="utf-8",
    )
    return out


_CSS = """
  :root{
    --ground:#FAF7F1;--surface:#FFFFFF;--surface-2:#F4EEE3;
    --ink:#211A11;--muted:#6E6355;--line:#E7DCCA;
    --bronze:#8A6E4B;--bronze-deep:#6F5738;--gold:#B8912E;
    --kiswah:#141009;--kiswah-2:#1E170E;--kiswah-line:rgba(200,164,74,.30);
    --on-kiswah:#F2E9D6;--on-kiswah-muted:#B9A985;--seal:#C8A44A;
    --success:#2E7D5B;--danger:#BC4A43;
    --radius:14px;--maxw:1080px;
    --shadow:0 1px 0 rgba(0,0,0,.02),0 12px 34px -22px rgba(60,44,20,.42);
    --font:"Segoe UI","Dubai","Tajawal","Noto Naskh Arabic",system-ui,-apple-system,Arial,sans-serif;
  }
  @media (prefers-color-scheme:dark){:root{
    --ground:#131009;--surface:#1B160E;--surface-2:#221C12;
    --ink:#F0E8D9;--muted:#A99C87;--line:#332A1C;
    --bronze:#CBA972;--bronze-deep:#B08C55;--gold:#D8B44A;
    --success:#5BB98C;--danger:#E17A72;
    --shadow:0 1px 0 rgba(0,0,0,.25),0 16px 40px -24px rgba(0,0,0,.8);
  }}
  *{box-sizing:border-box}html,body{margin:0}
  .page{background:var(--ground);color:var(--ink);font-family:var(--font);line-height:1.55;min-height:100vh;-webkit-font-smoothing:antialiased}
  .wrap{max-width:var(--maxw);margin:0 auto;padding:0 22px}
  .num{font-variant-numeric:tabular-nums;font-feature-settings:"tnum" 1}
  .hero{position:relative;overflow:hidden;color:var(--on-kiswah);
    background:radial-gradient(120% 140% at 82% -10%,rgba(200,164,74,.14),transparent 55%),linear-gradient(180deg,var(--kiswah-2),var(--kiswah));
    border-bottom:1px solid var(--kiswah-line)}
  .hero .wrap{padding:34px 22px 38px;position:relative;z-index:2}
  .seal{position:absolute;inset:auto -70px -120px auto;width:360px;height:360px;opacity:.14;z-index:1;color:var(--seal);pointer-events:none}
  .brandrow{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap}
  .brand-ar{font-size:20px;font-weight:800;color:var(--on-kiswah)}
  .brand-la{font-size:10.5px;letter-spacing:3px;color:var(--on-kiswah-muted);text-transform:uppercase;margin-top:3px}
  .stamp{display:inline-flex;align-items:center;gap:8px;font-size:11.5px;color:var(--on-kiswah-muted);border:1px solid var(--kiswah-line);padding:6px 12px;border-radius:100px;background:rgba(200,164,74,.06)}
  .stamp b{color:var(--seal);font-weight:700}
  .hero h1{margin:22px 0 6px;font-size:clamp(30px,5vw,50px);line-height:1.08;font-weight:800;letter-spacing:-.4px;text-wrap:balance;color:#F7EFDD}
  .hero .lede{margin:0;max-width:60ch;color:var(--on-kiswah-muted);font-size:15px}
  .goldrule{height:1px;margin-top:26px;background:linear-gradient(90deg,transparent,var(--kiswah-line),transparent)}
  .kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;margin-top:26px;background:var(--kiswah-line);border:1px solid var(--kiswah-line);border-radius:12px;overflow:hidden}
  .kpi{background:linear-gradient(180deg,rgba(255,255,255,.02),transparent);padding:16px 18px}
  .kpi .k{font-size:11.5px;color:var(--on-kiswah-muted)}
  .kpi .v{font-size:clamp(24px,3.4vw,32px);font-weight:800;color:#F5EAD2;margin-top:5px}
  .kpi .v small{font-size:13px;font-weight:600;color:var(--seal);margin-inline-start:4px}
  main{padding:40px 0 30px}.sec{margin-bottom:40px}
  .sec-head{display:flex;align-items:baseline;gap:12px;margin:0 0 18px}
  .sec-head h2{margin:0;font-size:20px;font-weight:800}
  .sec-head .eyebrow{font-size:11px;letter-spacing:2px;text-transform:uppercase;color:var(--bronze);font-weight:700}
  .sec-head .rule{flex:1;height:1px;background:var(--line)}
  .fin{display:grid;grid-template-columns:1.4fr 1fr 1fr;gap:14px}
  .card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow)}
  .stat{padding:20px 22px}.stat .lbl{font-size:12.5px;color:var(--muted);font-weight:600}
  .stat .big{font-size:clamp(26px,3.6vw,34px);font-weight:800;letter-spacing:-.4px;margin-top:6px}
  .stat .sub{font-size:12px;color:var(--muted);margin-top:2px}
  .cur{font-size:14px;color:var(--bronze);font-weight:700;margin-inline-start:6px}
  .progress{grid-column:1/-1;padding:16px 22px;display:flex;align-items:center;gap:16px;flex-wrap:wrap}
  .bar{flex:1;min-width:220px;height:12px;border-radius:100px;background:var(--surface-2);overflow:hidden;border:1px solid var(--line)}
  .bar>span{display:block;height:100%;border-radius:100px;background:linear-gradient(90deg,var(--bronze),var(--gold))}
  .progress .pct{font-weight:800;font-size:18px}.progress .note{font-size:12.5px;color:var(--muted)}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px}
  .prog{padding:20px 20px 18px;display:flex;flex-direction:column;gap:14px}
  .prog .top{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}
  .prog h3{margin:0;font-size:17px;font-weight:800}
  .prog .when{font-size:12px;color:var(--muted);margin-top:3px}
  .pill{font-size:11.5px;font-weight:700;padding:4px 11px;border-radius:100px;white-space:nowrap;border:1px solid transparent}
  .pill.ok{color:var(--success);background:color-mix(in srgb,var(--success) 12%,transparent);border-color:color-mix(in srgb,var(--success) 30%,transparent)}
  .pill.mid{color:var(--bronze);background:color-mix(in srgb,var(--bronze) 14%,transparent);border-color:color-mix(in srgb,var(--bronze) 32%,transparent)}
  .pill.low{color:var(--danger);background:color-mix(in srgb,var(--danger) 12%,transparent);border-color:color-mix(in srgb,var(--danger) 30%,transparent)}
  .hotels{display:flex;gap:10px;flex-wrap:wrap}
  .hotel{flex:1;min-width:130px;background:var(--surface-2);border:1px solid var(--line);border-radius:10px;padding:9px 12px}
  .hotel .city{font-size:10.5px;letter-spacing:.5px;color:var(--bronze);font-weight:700}
  .hotel .name{font-size:13px;font-weight:600;margin-top:2px}
  .metrics{display:flex;flex-direction:column;gap:11px}
  .metric .row{display:flex;justify-content:space-between;font-size:12.5px;margin-bottom:5px}
  .metric .row .muted{color:var(--muted)}
  .track{height:8px;border-radius:100px;background:var(--surface-2);border:1px solid var(--line);overflow:hidden}
  .track>span{display:block;height:100%;border-radius:100px}
  .fill-occ{background:linear-gradient(90deg,var(--bronze-deep),var(--bronze))}
  .fill-col{background:linear-gradient(90deg,var(--bronze),var(--gold))}
  .chart{padding:22px}
  .chrow{display:grid;grid-template-columns:180px 1fr 96px;align-items:center;gap:14px;padding:9px 0}
  .chrow+.chrow{border-top:1px solid var(--line)}
  .chrow .nm{font-size:13.5px;font-weight:700}
  .chrow .nm span{display:block;font-size:11px;color:var(--muted);font-weight:500}
  .chbar{height:22px;border-radius:7px;background:var(--surface-2);border:1px solid var(--line);overflow:hidden}
  .chbar>span{display:block;height:100%;background:linear-gradient(90deg,var(--bronze),var(--gold))}
  .chrow .val{text-align:end;font-weight:800;font-size:14px}
  .chrow .val small{display:block;font-size:11px;color:var(--muted);font-weight:600}
  footer{border-top:1px solid var(--line);padding:22px 0 40px;color:var(--muted);font-size:12.5px}
  .foot{display:flex;justify-content:space-between;gap:14px;flex-wrap:wrap;align-items:center}
  .demo{display:inline-flex;align-items:center;gap:7px;color:var(--bronze);font-weight:700}
  .demo .dot{width:7px;height:7px;border-radius:100px;background:var(--gold)}
  @media (max-width:760px){.kpis{grid-template-columns:repeat(2,1fr)}.fin{grid-template-columns:1fr}.chrow{grid-template-columns:120px 1fr 80px;gap:10px}}
  @keyframes rise{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
  .anim{animation:rise .7s cubic-bezier(.2,.7,.2,1) both}
  .d1{animation-delay:.05s}.d2{animation-delay:.12s}.d3{animation-delay:.2s}
  @media (prefers-reduced-motion:reduce){.anim{animation:none}}
  @media print{.hero{-webkit-print-color-adjust:exact;print-color-adjust:exact}.anim{animation:none}}
"""

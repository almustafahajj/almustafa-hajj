"""واجهة **برنامج العمرة** — مبنيّة على محرّك البرنامج المجرّب.

العمرة تُنظَّم حسب **البرامج** (رحلات عمرة متعدّدة على مدار السنة). الشاشة
الرئيسية تعرض البرامج؛ ومن كل برنامج تُدار قائمة معتمريه (إضافة بقراءة
الجواز، تعديل، حذف، تصدير، حجز بالتسعير) وتفاصيله (الفنادق، الطيران بأوقاته،
أسعار الفرد حسب الغرفة، الخدمات المسعّرة، والنقل الداخلي).

يُعاد استخدام: التشفير والجلسة (storage)، قراءة الجواز (ocr/pdf_in)، نافذة
التعديل والأنماط (gui)، والتصدير (excel_io/pdf_io).
"""

from __future__ import annotations

import calendar as _calmod
import re
from datetime import date
from pathlib import Path
from tkinter import (
    BOTH, BooleanVar, Canvas, END, Frame, LEFT, Menu, RIGHT, StringVar, Text,
    Toplevel, X, Y, filedialog, messagebox, ttk,
)

from . import app_mode, assistant, images as imgmod, umrah
from . import gui as G

# CustomTkinter اختياري: يمنح عناصر عصرية (زوايا دائرية) داخل نفس نافذة Tk.
# عند غيابه يعمل البرنامج بالمظهر الكلاسيكي دون كسر.
try:
    import customtkinter as _ctk
    _HAS_CTK = True
except Exception:                      # pragma: no cover - بيئة بلا المكتبة
    _ctk = None
    _HAS_CTK = False


def _ctk_mode() -> str:
    """وضع CustomTkinter (فاتح/داكن) مشتقّ من لون خلفية السمة الحالية."""
    try:
        h = G.BG.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return "dark" if (r * 0.299 + g * 0.587 + b * 0.114) < 128 else "light"
    except Exception:
        return "light"


def _sync_ctk_mode() -> None:
    """يوائم مظهر CustomTkinter مع السمة الحالية (يُستدعى عند فتح نافذة)."""
    if _HAS_CTK:
        try:
            _ctk.set_appearance_mode(_ctk_mode())
        except Exception:
            pass


def _cbtn(parent, label, command, kind="ghost", width=None):
    """زر عصري (CustomTkinter) أو كلاسيكي (ttk) — يُستخدم في النوافذ المشتركة.

    ``kind``: ``primary`` برونزي ممتلئ، ``act`` محدَّد ببرونزي، وإلّا ``ghost``."""
    if _HAS_CTK:
        prim = kind == "primary"
        act = kind == "act"
        kw = {} if width is None else {"width": width}
        return _ctk.CTkButton(
            parent, text=G.rtl(label), command=command, corner_radius=11,
            height=38, font=_ctk.CTkFont(G._FSB, 13, "bold"),
            fg_color=(G.BRONZE if prim else G.GHOST_BG),
            hover_color=(G.BRONZE_DARK if prim else G.GHOST_HOVER),
            text_color=("#FFFFFF" if prim else (G.BRONZE if act else G.TEXT)),
            border_width=(0 if prim else 1),
            border_color=(G.BRONZE if act else G.BORDER), **kw)
    style = {"primary": "Primary.TButton", "act": "Act.TButton"}.get(
        kind, "Ghost.TButton")
    kw = {} if width is None else {"width": max(4, width // 9)}
    return ttk.Button(parent, text=G.rtl(label), style=style,
                      command=command, **kw)


def _centry(parent, textvariable, **kw):
    """حقل إدخال عصري (CustomTkinter) أو كلاسيكي (ttk)."""
    if _HAS_CTK:
        placeholder = kw.pop("placeholder_text", "")
        return _ctk.CTkEntry(
            parent, textvariable=textvariable, height=38, corner_radius=11,
            border_width=1, border_color=G.BORDER, fg_color=G.PANEL,
            font=_ctk.CTkFont(G._FUI, 13), justify="right",
            placeholder_text=placeholder)
    return ttk.Entry(parent, textvariable=textvariable, font=(G._FUI, 13),
                     justify="right")
from .excel_io import export_answer_excel, export_umrah_excel
from .fields import format_amount, parse_amount, payment_total
from .mrz import MRZError, PassportData
from .ocr import extract_passport
from .pdf_in import PDFError, extract_from_pdf
from .pdf_io import (
    QUOTE_AIRPORT_CITIES, QUOTE_CAR_COUNTS, QUOTE_CAR_MODELS, QUOTE_CAR_TYPES,
    QUOTE_CARRIERS, QUOTE_CITY_OPTIONS, QUOTE_FLIGHT_CLASSES, QUOTE_FLIGHT_HEADS,
    QUOTE_GUEST_TYPES, QUOTE_HOTELS, QUOTE_LOCATIONS, QUOTE_MEALS, QUOTE_NIGHTS,
    QUOTE_NOTES, QUOTE_OFFICE_NAME, QUOTE_OFFICE_PHONE, QUOTE_OFFICE_TITLE,
    QUOTE_ROOM_COUNTS, QUOTE_ROOM_TYPES, QUOTE_STAY_HEADS, QUOTE_VIEWS,
    TREQ_BOOK_HEADS, TREQ_FLIGHT_HEADS, TREQ_HONORIFICS, TREQ_MOVE_HEADS,
    VOUCHER_CAR_TYPES, VOUCHER_CITY_OPTIONS, VOUCHER_CITY_OPTIONS_EN,
    VOUCHER_ROOM_COUNTS, VOUCHER_ROOM_TYPES, VOUCHER_ROOM_TYPES_EN,
    VOUCHER_STAY_HEADS, VOUCHER_TRANSPORT_HEADS,
    VOUCHER_VIEW_OPTIONS, build_quotation_data, build_transport_request_data,
    build_voucher_data, normalize_voucher_stay,
    export_airline_pdf, export_group_pricing_pdf, export_umrah_cards_pdf,
    export_umrah_contract_pdf, export_umrah_finance_pdf, export_umrah_invoice_pdf,
    export_umrah_pdf,
    export_umrah_quotation_pdf, export_umrah_receipt_pdf, export_umrah_rooming_pdf,
    export_umrah_transport_pdf, export_umrah_transport_request_pdf,
    export_umrah_voucher_pdf, fmt_money,
    quotation_pricing, quote_times, translate_quotation_data, voucher_car_models,
)
from .storage import load_records, load_settings, save_records, save_settings
from .tesseract_setup import configure_tesseract


def _center(win, parent=None) -> None:
    """يوسّط نافذة على الشاشة."""
    win.update_idletasks()
    w, h = win.winfo_width(), win.winfo_height()
    sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
    win.geometry(f"+{(sw - w) // 2}+{(sh - h) // 3}")


class UmrahApp:
    """الشاشة الرئيسية لبرنامج العمرة: إدارة برامج العمرة."""

    # نستعير بناء الأنماط من HajjApp لتوحيد المظهر تماماً
    _DENSITY = G.HajjApp._DENSITY
    _FONT_SIZES = G.HajjApp._FONT_SIZES
    _build_styles = G.HajjApp._build_styles
    _apply_table_style = G.HajjApp._apply_table_style
    # الشريط الجانبي المشترك (شعار + أكورديون + طيّ) — نفس آلية الحج
    _SIDEBAR_W = G.HajjApp._SIDEBAR_W
    _SIDEBAR_W_MIN = G.HajjApp._SIDEBAR_W_MIN
    _NAV_ICON = G.HajjApp._NAV_ICON
    _NAV_ICON_BIG = G.HajjApp._NAV_ICON_BIG
    _build_shell = G.HajjApp._build_shell
    _build_sidebar = G.HajjApp._build_sidebar
    _nav_item = G.HajjApp._nav_item
    _toggle_sidebar = G.HajjApp._toggle_sidebar
    _set_sidebar_collapsed = G.HajjApp._set_sidebar_collapsed
    _cticon = G.HajjApp._cticon
    _icon = G.HajjApp._icon
    _nav_action = G.HajjApp._nav_action
    _choose = G.HajjApp._choose
    _icon_button = G.HajjApp._icon_button
    _toggle_filter_panel = G.HajjApp._toggle_filter_panel
    _hide_filter_panel = G.HajjApp._hide_filter_panel

    def __init__(self, root, session=None, open_mode: bool = False) -> None:
        self.root = root
        self.session = session
        self._open_mode = open_mode
        self._exit_action = None
        self._style = None

        self._settings = load_settings()
        ui = self._settings.get("ui", {})
        self._ui = ui if isinstance(ui, dict) else {}
        self._density = self._ui.get("density", "عادي")
        if self._density not in self._DENSITY:
            self._density = "عادي"
        self._font_size = self._ui.get("font_size", "متوسط")
        if self._font_size not in self._FONT_SIZES:
            self._font_size = "متوسط"
        accent = self._ui.get("accent", "برونزي")
        try:
            G.apply_accent(accent if accent in G.ACCENTS else "برونزي")
        except Exception:
            pass
        self._theme = self._ui.get("theme", "فاتح")
        if self._theme not in G.THEMES:
            self._theme = "فاتح"
        try:
            G.apply_theme(self._theme)          # يوحّد الوضع الفاتح/الداكن مع الحج
        except Exception:
            pass

        root.title(app_mode.label("window_title"))
        geom = self._ui.get("geometry")
        root.geometry(geom if isinstance(geom, str) and "x" in geom else "1180x720")
        root.minsize(900, 560)
        root.configure(bg=G.BG)
        try:
            G.apply_window_icon(root)
        except Exception:
            pass
        G.detect_fonts(root)          # اختيار أجمل خطّ عربي متوفّر قبل بناء الأنماط
        self._build_styles()

        try:
            self.records, _note = load_records(session=session)
        except Exception:
            self.records = []
        self.trips = umrah.load_trips(self._settings)

        # الموسم = سنة ميلادية كاملة (١ يناير – ٣١ ديسمبر)
        self._season_years = [str(y) for y in range(2024, 2036)]
        saved = str(self._settings.get("umrah_season", "") or "")
        season = saved or str(date.today().year)
        if season not in self._season_years:
            self._season_years = sorted(set(self._season_years) | {season})
        self._season = StringVar(master=root, value=season)

        self._build_shell()          # شريط جانبي + منطقة محتوى
        self._build_sidebar()        # الشعار + الحساب + زرّ الطيّ
        self._build_nav()            # أقسام التنقّل (أكورديون)
        self._build_topbar()         # شريط علوي: الموسم + إجراءات
        self._build_kpi()
        self._build_statusbar()
        self._build_table()
        self._bind_shortcuts()
        self._reload()

    # ---- لوحة تحكّم الموسم (بطاقات مؤشّرات كبيرة، حيّة) ----
    _KPI_ACCENTS = {"pilgrims": "#8A6E4B", "occ": "#2C5AA0",
                    "paid": "#2E7D5B", "late": "#C0392B"}

    def _build_kpi(self) -> None:
        """لوحة تحكّم أعلى الواجهة: بطاقات مؤشّرات عصرية (CTk) أو كلاسيكية."""
        if _HAS_CTK:
            self._build_kpi_modern()
        else:
            self._build_kpi_classic()

    def _build_kpi_modern(self) -> None:
        """بطاقات CustomTkinter بزوايا دائرية وشرائط لون — مظهر عصري."""
        _ctk.set_appearance_mode(_ctk_mode())
        outer = ttk.Frame(self._body, style="Toolbar.TFrame",
                          padding=(16, 8, 16, 12))
        outer.pack(fill=X)
        _ctk.CTkLabel(outer, text=G.rtl("📊  نظرة سريعة على الموسم"),
                      font=_ctk.CTkFont(G._FSB, 13, "bold"),
                      text_color=G.BRONZE, fg_color="transparent").pack(
                          anchor="e", pady=(0, 8))
        wrap = _ctk.CTkFrame(outer, fg_color="transparent")
        wrap.pack(fill=X)
        self._kpi = {}
        specs = [("pilgrims", "المعتمرون", "👤", "", False),
                 ("occ", "نسبة الإشغال", "🏨", "", False),
                 ("paid", "المحصّل", "💰", "AED", False),
                 ("late", "المتأخرون عن السداد", "⚠", "", True)]
        for key, label, icon, unit, clickable in specs:
            acc = self._KPI_ACCENTS[key]
            card = _ctk.CTkFrame(wrap, corner_radius=16, fg_color=G.PANEL,
                                 border_width=1, border_color=G.BORDER)
            card.pack(side=RIGHT, fill="both", expand=True, padx=(12, 0))
            _ctk.CTkFrame(card, height=5, corner_radius=6, fg_color=acc).pack(
                fill="x", padx=14, pady=(12, 0))
            top = _ctk.CTkFrame(card, fg_color="transparent")
            top.pack(fill="x", padx=16, pady=(8, 0))
            _ctk.CTkLabel(top, text=icon, font=_ctk.CTkFont(G._FUI, 18),
                          text_color=acc, fg_color="transparent").pack(side=RIGHT)
            _ctk.CTkLabel(top, text=G.rtl(label),
                          font=_ctk.CTkFont(G._FUI, 12), text_color=G.MUTED,
                          fg_color="transparent").pack(side=RIGHT, padx=(0, 8))
            val = _ctk.CTkLabel(card, text="—",
                                font=_ctk.CTkFont(G._FSB, 30, "bold"),
                                text_color=acc, fg_color="transparent")
            val.pack(anchor="e", padx=18, pady=(4, 0))
            self._kpi[key] = val
            sub = _ctk.CTkLabel(card, text=(unit or " "),
                                font=_ctk.CTkFont(G._FUI, 10),
                                text_color=G.MUTED, fg_color="transparent")
            sub.pack(anchor="e", padx=18, pady=(0, 14))
            if unit:
                self._kpi[key + "_sub"] = sub
            if clickable:
                for w in (card, top, val, sub):
                    w.bind("<Button-1>", lambda _e: self.open_collections())
                self._kpi["late_card"] = card
        # شريط نسبة التحصيل من إجمالي القيمة — مؤشّر مدير يتلوّن حسب الصحّة
        prog = _ctk.CTkFrame(outer, fg_color="transparent")
        prog.pack(fill=X, pady=(14, 0))
        cap = _ctk.CTkFrame(prog, fg_color="transparent")
        cap.pack(fill=X)
        self._kpi_pct_lbl = _ctk.CTkLabel(
            cap, text="—", font=_ctk.CTkFont(G._FSB, 13, "bold"),
            text_color=G.SUCCESS_FG, fg_color="transparent")
        self._kpi_pct_lbl.pack(side=LEFT)
        _ctk.CTkLabel(cap, text=G.rtl("نسبة التحصيل من إجمالي القيمة"),
                      font=_ctk.CTkFont(G._FUI, 11), text_color=G.MUTED,
                      fg_color="transparent").pack(side=RIGHT)
        self._kpi_progress = _ctk.CTkProgressBar(
            prog, height=12, corner_radius=6, progress_color=G.SUCCESS_FG,
            fg_color=G.BORDER)
        self._kpi_progress.pack(fill=X, pady=(6, 0))
        self._kpi_progress.set(0)

    def _build_kpi_classic(self) -> None:
        """النسخة الكلاسيكية (ttk) — تعمل عند غياب CustomTkinter."""
        outer = ttk.Frame(self._body, style="Toolbar.TFrame",
                          padding=(16, 8, 16, 12))
        outer.pack(fill=X)
        ttk.Label(outer, text=G.rtl("📊  نظرة سريعة على الموسم"),
                  font=(G._FSB, 11), foreground=G.BRONZE,
                  background=G.BG).pack(anchor="e", pady=(0, 8))
        wrap = ttk.Frame(outer, style="Toolbar.TFrame")
        wrap.pack(fill=X)
        self._kpi = {}
        # (المفتاح، العنوان، الأيقونة، الوحدة، قابل للنقر)
        specs = [("pilgrims", "المعتمرون", "👤", "", False),
                 ("occ", "نسبة الإشغال", "🏨", "", False),
                 ("paid", "المحصّل", "💰", "AED", False),
                 ("late", "المتأخرون عن السداد", "⏳", "", True)]
        for key, label, icon, unit, clickable in specs:
            acc = self._KPI_ACCENTS[key]
            card = ttk.Frame(wrap, style="Panel.TFrame")
            card.pack(side=RIGHT, fill=BOTH, expand=True, padx=(12, 0))
            Frame(card, background=acc, height=3).pack(fill=X)   # شريط لون علوي
            inner = ttk.Frame(card, style="Panel.TFrame", padding=(16, 12, 16, 15))
            inner.pack(fill=BOTH, expand=True)
            top = ttk.Frame(inner, style="Panel.TFrame")
            top.pack(fill=X)
            ttk.Label(top, text=icon, font=(G._FUI, 16), foreground=acc,
                      background=G.PANEL).pack(side=RIGHT)
            ttk.Label(top, text=G.rtl(label), font=(G._FUI, 10),
                      foreground=G.MUTED, background=G.PANEL).pack(
                          side=RIGHT, padx=(0, 8))
            val = ttk.Label(inner, text="—", font=(G._FSB, 25),
                            foreground=acc, background=G.PANEL)
            val.pack(anchor="e", pady=(8, 0))
            self._kpi[key] = val
            if unit:
                sub = ttk.Label(inner, text=unit, font=(G._FUI, 9),
                                foreground=G.MUTED, background=G.PANEL)
                sub.pack(anchor="e")
                self._kpi[key + "_sub"] = sub
            if clickable:                       # المتأخرون: نقرة تفتح المتابعة
                for w in (card, inner, top, val):
                    try:
                        w.configure(cursor="hand2")
                    except Exception:
                        pass
                    w.bind("<Button-1>", lambda _e: self.open_collections())
                self._kpi["late_card"] = card
        # شريط نسبة التحصيل (نسخة ttk)
        prog = ttk.Frame(outer, style="Toolbar.TFrame")
        prog.pack(fill=X, pady=(12, 0))
        cap = ttk.Frame(prog, style="Toolbar.TFrame")
        cap.pack(fill=X)
        self._kpi_pct_lbl = ttk.Label(cap, text="—", font=(G._FSB, 11),
                                      foreground=G.SUCCESS_FG, background=G.BG)
        self._kpi_pct_lbl.pack(side=LEFT)
        ttk.Label(cap, text=G.rtl("نسبة التحصيل من إجمالي القيمة"),
                  font=(G._FUI, 10), foreground=G.MUTED,
                  background=G.BG).pack(side=RIGHT)
        self._kpi_progress = ttk.Progressbar(prog, mode="determinate",
                                             maximum=100, value=0)
        self._kpi_progress.pack(fill=X, pady=(6, 0))

    def _update_kpi(self, pilgrims, cap_total, total, paid, late) -> None:
        """يحدّث بطاقات لوحة التحكّم من أرقام الموسم الحالية."""
        if not hasattr(self, "_kpi"):
            return
        occ = f"{pilgrims / cap_total * 100:.0f}٪" if cap_total else "—"
        pct = f"{paid / total * 100:.0f}٪" if total else "—"
        self._kpi["pilgrims"].configure(text=str(pilgrims))
        self._kpi["occ"].configure(text=occ)
        self._kpi["paid"].configure(text=format_amount(paid) or "0")
        if "paid_sub" in self._kpi:
            self._kpi["paid_sub"].configure(text=f"AED · محصّل {pct}")
        self._kpi["late"].configure(text=str(late))
        if hasattr(self, "_kpi_progress"):
            cp = (paid / total * 100.0) if total else 0.0
            hue = (G.SUCCESS_FG if cp >= 75 else
                   (G.AMBER_FG if cp >= 40 else G.DANGER))
            pct_txt = f"{cp:.0f}٪" if total else "—"
            try:                                    # CTkProgressBar + CTkLabel
                self._kpi_progress.set(max(0.0, min(1.0, cp / 100.0)))
                self._kpi_progress.configure(progress_color=hue)
                self._kpi_pct_lbl.configure(text=pct_txt, text_color=hue)
            except Exception:                       # ttk
                self._kpi_progress["value"] = max(0.0, min(100.0, cp))
                self._kpi_pct_lbl.configure(text=pct_txt, foreground=hue)

    def _build_statusbar(self) -> None:
        bar = ttk.Frame(self._body, style="Panel.TFrame", padding=(16, 6))
        bar.pack(fill=X, side="bottom")
        self._status = ttk.Label(bar, text="", font=(G._FUI, 10),
                                 foreground=G.TEXT, background=G.BG)
        self._status.pack(side=RIGHT)
        ttk.Label(bar, background=G.BG, foreground=G.MUTED, font=(G._FUI, 9),
                  text=G.rtl("⌨  Ctrl+N برنامج · Enter المعتمرون · "
                             "F5 تحديث · Del حذف")).pack(side=LEFT)

    # ---- اختصارات لوحة المفاتيح ----
    def _bind_shortcuts(self) -> None:
        r = self.root
        r.bind("<Control-n>", lambda e: self.new_trip())
        r.bind("<Control-N>", lambda e: self.new_trip())
        r.bind("<Control-e>", lambda e: self.edit_trip())
        r.bind("<F5>", lambda e: self._reload())
        r.bind("<Return>", self._shortcut_open)
        r.bind("<Delete>", self._shortcut_delete)

    def _editing_now(self) -> bool:
        """هل التركيز داخل حقل كتابة؟ (فلا نلتقط اختصارات النافذة)."""
        w = self.root.focus_get()
        return w is not None and w.winfo_class() in (
            "TEntry", "Entry", "TCombobox", "Text")

    def _shortcut_open(self, _e=None):
        if not self._editing_now() and self.tree.selection():
            self.open_pilgrims()

    def _shortcut_delete(self, _e=None):
        if not self._editing_now() and self.tree.selection():
            self.delete_trip()

    # ---- الحفظ ----
    def save(self) -> None:
        try:
            save_records(self.records, session=self.session)
        except Exception as exc:
            messagebox.showerror("تعذّر الحفظ", str(exc), parent=self.root)

    def save_trips(self) -> None:
        umrah.save_trips(self._settings, self.trips)
        try:
            save_settings(self._settings)
        except OSError:
            pass

    # ---- الترويسة ----
    def _build_header(self) -> None:
        bar = ttk.Frame(self.root, style="Toolbar.TFrame", padding=(16, 10, 16, 6))
        bar.pack(fill=X)
        self._logo = G.logo_image(self.root, width=140)
        if self._logo is not None:
            ttk.Label(bar, image=self._logo, background=G.BG).pack(
                side=RIGHT, padx=(0, 14))
        titles = ttk.Frame(bar, style="Toolbar.TFrame")
        titles.pack(side=RIGHT)
        row1 = ttk.Frame(titles, style="Toolbar.TFrame")
        row1.pack(anchor="e")
        ttk.Label(row1, text="إدارة موسم العمرة", font=(G._FSB, 17),
                  foreground=G.TEXT, background=G.BG).pack(side=RIGHT)
        year_box = ttk.Combobox(row1, textvariable=self._season, state="readonly",
                                width=7, font=(G._FSB, 14), values=self._season_years)
        year_box.pack(side=RIGHT, padx=(8, 0))
        year_box.bind("<<ComboboxSelected>>", lambda _e: self._on_season_change())
        self._subtitle = ttk.Label(titles, text=self._season_text(),
                                    font=(G._FUI, 10), foreground=G.MUTED,
                                    background=G.BG)
        self._subtitle.pack(anchor="e")

        other = app_mode.mode_label(app_mode.HAJJ)
        self._mkbtn(bar, f"🕋  التبديل إلى {other}", self.switch_mode).pack(
            side=LEFT, padx=(0, 8))
        _theme_btn = self._mkbtn(
            bar, ("☀️  فاتح" if self._theme == "داكن" else "🌙  داكن"),
            self.toggle_theme)
        _theme_btn.pack(side=LEFT, padx=(0, 8))
        G.add_tooltip(_theme_btn, G.rtl("التبديل بين الوضع الفاتح والداكن"))
        rmenu = self._make_menu(bar, (
            ("📊  نظرة سريعة", self.open_dashboard),
            ("🌐  تقرير ويب (يُشارك برابط)", self.export_web_dashboard),
            ("📄  تقرير PDF (للطباعة)", self.export_season_pdf),
            None,
            ("💰  متابعة التحصيل (المتأخرون)", self.open_collections),
            ("📋  نسخ ملخّص الموسم", self.copy_season_summary),
        ))
        self._report_menu = rmenu          # مرجع يمنع جمع القمامة
        if _HAS_CTK:
            rep = self._mkbtn(bar, "📊  لوحة الموسم", None)
            rep.configure(command=lambda: self._popup_menu(rmenu, rep))
        else:
            rep = ttk.Menubutton(bar, text=G.rtl("📊  لوحة الموسم"),
                                 style="Ghost.TMenubutton", direction="below")
            rep["menu"] = rmenu
        rep.pack(side=LEFT, padx=(0, 8))
        G.add_tooltip(rep, G.rtl("تقارير الموسم: نظرة سريعة، ويب، وPDF"))
        _ask = self._mkbtn(bar, "🔎  اسأل بياناتك", self.ask_data)
        _ask.pack(side=LEFT, padx=(0, 8))
        G.add_tooltip(_ask, G.rtl(
            "اكتب سؤالاً بالعربية عن معتمري الموسم فيجيبك من بياناتك فوراً"))
        if self.session is not None:
            info = ttk.Frame(bar, style="Toolbar.TFrame")
            info.pack(side=LEFT)
            ttk.Label(info,
                      text=f"👤  {self.session.username}  ·  {self.session.role_label}",
                      font=(G._FSB, 10), foreground=G.TEXT,
                      background=G.BG).pack(anchor="w")
            ttk.Label(info, text="🔒 البيانات مشفّرة", font=(G._FUI, 9),
                      foreground=G.BRONZE, background=G.BG).pack(anchor="w")
            self._mkbtn(bar, "🚪  تسجيل الخروج", self.do_logout).pack(
                side=LEFT, padx=(0, 8))

    # ---- شريط الأدوات ----
    #  واجهة مبسّطة: زران رئيسيان دائما الظهور + قوائم منسدلة تجمع بقية الأدوات
    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self.root, style="Panel.TFrame", padding=(16, 10, 16, 12))
        bar.pack(fill=X)
        self._menus: list = []
        # الأكثر استخداماً — أزرار مباشرة
        b_new = self._mkbtn(bar, "➕  برنامج جديد", self.new_trip, "primary")
        b_new.pack(side=RIGHT, padx=3)
        G.add_tooltip(b_new, G.rtl("إضافة برنامج عمرة جديد  (Ctrl+N)"))
        b_pil = self._mkbtn(bar, "👤  المعتمرون", self.open_pilgrims, "act")
        b_pil.pack(side=RIGHT, padx=3)
        G.add_tooltip(b_pil, G.rtl("فتح معتمري البرنامج المحدَّد  (Enter)"))
        # قوائم منسدلة تجمع الأدوات ذات الصلة لتخفيف الازدحام
        self._menu_button(bar, "✏️  البرنامج", (
            ("✏️  تعديل البرنامج", self.edit_trip),
            ("🗑  حذف البرنامج", self.delete_trip),
        ), tip="تعديل أو حذف البرنامج المحدَّد  (Ctrl+E / Del)")
        self._menu_button(bar, "💰  التسعير والعروض", (
            ("📋  عروض الأسعار المحفوظة", self.open_quotes),
            ("💲  عرض سعر يدوي جديد", self.new_manual_quotation),
            ("📁  العروض اليدوية", self.open_manual_quotes),
            None,
            ("🧮  مسعّر المجموعات", self.open_group_pricer),
            ("🗂  التسعيرات المحفوظة", self.open_pricings),
        ), tip="عروض الأسعار، المسعّر، والتسعيرات المحفوظة")
        self._menu_button(bar, "📄  مستندات وكشوف", (
            ("💰  الملخّص المالي", self.prog_finance),
            ("🛏  التسكين", self.prog_rooming),
            ("🚐  المواصلات", self.prog_transport),
            ("✈  كشف الطيران", self.prog_airline),
            ("🪪  بطاقات العمرة", self.prog_cards),
            None,
            ("🧾  سند قبض", self.prog_receipt),
            ("🧾  فاتورة", self.prog_invoice),
            ("📜  عقد", self.prog_contract),
            ("💲  عرض سعر", self.prog_quotation),
            None,
            ("🏨  فاوتشر فندق يدوي", self.new_manual_voucher),
            ("🗂  الفاوتشرات المحفوظة", self.open_vouchers),
        ), tip="كشوف البرنامج المحدَّد ومستنداته (مالية/تسكين/مواصلات/طيران/بطاقات)")
        self._menu_button(bar, "🚖  الطلبات", (
            ("🚖  طلب حجز مواصلات", self.new_transport_request),
            ("🗂  الطلبات المحفوظة", self.open_transport_requests),
        ), tip="طلب حجز مواصلات (خطاب لشركة النقل) والطلبات المحفوظة")

    def _mkbtn(self, parent, label, command, kind="ghost"):
        """زر عصري (CustomTkinter) أو كلاسيكي حسب توفّر المكتبة.

        ``kind``: ``primary`` (برونزي ممتلئ) / ``act`` أو ``ghost`` (فاتح محدّد)."""
        if _HAS_CTK:
            prim = kind == "primary"
            return _ctk.CTkButton(
                parent, text=G.rtl(label), command=command, corner_radius=11,
                height=40, font=_ctk.CTkFont(G._FSB, 13, "bold"),
                fg_color=(G.BRONZE if prim else G.GHOST_BG),
                hover_color=(G.BRONZE_DARK if prim else G.GHOST_HOVER),
                text_color=("#FFFFFF" if prim else G.TEXT),
                border_width=(0 if prim else 1), border_color=G.BORDER)
        style = {"primary": "Primary.TButton", "act": "Act.TButton"}.get(
            kind, "Ghost.TButton")
        return ttk.Button(parent, text=G.rtl(label), style=style, command=command)

    @staticmethod
    def _popup_menu(menu, btn) -> None:
        """يُظهر قائمةً منسدلة أسفل زرّ CustomTkinter."""
        try:
            menu.tk_popup(btn.winfo_rootx(),
                          btn.winfo_rooty() + btn.winfo_height())
        finally:
            menu.grab_release()

    def _make_menu(self, parent, items) -> "Menu":
        """يبني قائمة tk من عناصر (نص، أمر) أو None لفاصل."""
        menu = Menu(parent, tearoff=0, font=(G._FUI, 10))
        for entry in items:
            if entry is None:
                menu.add_separator()
            else:
                text, cmd = entry
                menu.add_command(label=G.rtl(text), command=cmd)
        return menu

    def _menu_button(self, bar, label, items, tip="", side=RIGHT):
        """زر بقائمة منسدلة — عصري (CTk) أو كلاسيكي، مع الحفاظ على كائن القائمة."""
        menu = self._make_menu(bar, items)
        self._menus.append(menu)          # مرجع يمنع جمع القمامة
        if _HAS_CTK:
            # الخطّ لا يرسم السهم ▾ فيظهر مربّعاً؛ الرمز التعبيري في العنوان كافٍ
            mb = _ctk.CTkButton(
                bar, text=G.rtl(label.replace("▾", "").strip()),
                corner_radius=11, height=40,
                font=_ctk.CTkFont(G._FSB, 13, "bold"), fg_color=G.GHOST_BG,
                hover_color=G.GHOST_HOVER, text_color=G.TEXT, border_width=1,
                border_color=G.BORDER)
            mb.configure(command=lambda m=menu, b=mb: self._popup_menu(m, b))
        else:
            mb = ttk.Menubutton(bar, text=G.rtl(label),
                                style="Ghost.TMenubutton", direction="below")
            mb["menu"] = menu
        mb.pack(side=side, padx=3)
        if tip:
            G.add_tooltip(mb, G.rtl(tip))
        return mb

    def _save_ui_settings(self) -> None:
        """يحفظ إعدادات الواجهة (يُستدعى من آلية طيّ الشريط المشتركة)."""
        self._settings["ui"] = self._ui
        try:
            save_settings(self._settings)
        except OSError:
            pass

    def _build_nav(self) -> None:
        """أقسام التنقّل في الشريط الجانبي (أكورديون) — خاصّة بالعمرة."""
        self._menus = []
        self._nav_sections = []
        self._nav_headers = []
        # ---- إجراءات مباشرة أعلى التنقّل (نُقلت من الشريط العلوي) ----
        # (الوضع الفاتح/الداكن يبقى داخل قسم «الإعدادات» فقط)
        _other = app_mode.mode_label(app_mode.HAJJ)
        self._nav_action("برنامج جديد", "add", self.new_trip, color=G.NAV_LIME)
        self._nav_action("المعتمرون", "id", self.open_pilgrims, color=G.NAV_SKY)
        self._nav_action("اسأل بياناتك", "search", self.ask_data,
                         color=G.NAV_BLUE)
        self._nav_action(f"التبديل إلى {_other}", "swap", self.switch_mode,
                         color=G.NAV_VIOLET)
        import tkinter as _tk
        _tk.Frame(self._nav_holder, bg=G.SIDEBAR_SEP, height=1).pack(
            fill="x", padx=16, pady=(8, 4))
        self._nav_item("لوحة الموسم", (
            ("📊  نظرة سريعة", self.open_dashboard),
            ("🌐  تقرير ويب (يُشارك برابط)", self.export_web_dashboard),
            ("📄  تقرير PDF (للطباعة)", self.export_season_pdf),
            None,
            ("🔎  اسأل بياناتك", self.ask_data),
            ("💰  متابعة التحصيل (المتأخرون)", self.open_collections),
            ("📋  نسخ ملخّص الموسم", self.copy_season_summary),
        ), icon=("report", G.NAV_ROSE), tip="تقارير الموسم والتحصيل والمساعد")
        self._nav_item("البرنامج", (
            ("➕  برنامج جديد", self.new_trip),
            ("👤  المعتمرون", self.open_pilgrims),
            None,
            ("✏️  تعديل البرنامج", self.edit_trip),
            ("🗑  حذف البرنامج", self.delete_trip),
        ), icon=("columns", G.NAV_TEAL), tip="إدارة برامج العمرة ومعتمريها")
        self._nav_item("التسعير والعروض", (
            ("📋  عروض الأسعار المحفوظة", self.open_quotes),
            ("💲  عرض سعر يدوي جديد", self.new_manual_quotation),
            ("📁  العروض اليدوية", self.open_manual_quotes),
            None,
            ("🧮  مسعّر المجموعات", self.open_group_pricer),
            ("🗂  التسعيرات المحفوظة", self.open_pricings),
        ), icon=("chart", G.NAV_GOLD), tip="عروض الأسعار والمسعّر والتسعيرات")
        self._nav_item("مستندات وكشوف", (
            ("💰  الملخّص المالي", self.prog_finance),
            ("🛏  التسكين", self.prog_rooming),
            ("🚐  المواصلات", self.prog_transport),
            ("✈  كشف الطيران", self.prog_airline),
            ("🪪  بطاقات العمرة", self.prog_cards),
            None,
            ("🧾  سند قبض", self.prog_receipt),
            ("🧾  فاتورة", self.prog_invoice),
            ("📜  عقد", self.prog_contract),
            ("💲  عرض سعر", self.prog_quotation),
            None,
            ("🏨  فاوتشر فندق يدوي", self.new_manual_voucher),
            ("🗂  الفاوتشرات المحفوظة", self.open_vouchers),
        ), icon=("id", G.NAV_GREEN), tip="كشوف البرنامج ومستنداته")
        self._nav_item("الطلبات", (
            ("🚖  طلب حجز مواصلات", self.new_transport_request),
            ("🗂  الطلبات المحفوظة", self.open_transport_requests),
        ), icon=("tent", G.NAV_ORANGE), tip="طلبات حجز المواصلات المحفوظة")
        self._nav_item("الإعدادات", [
            ("🗓  اختيار الموسم (السنة)", self._pick_season),
            None,
            ("↕  كثافة الصفوف", self._pick_density),
            ("🔤  حجم الخط", self._pick_font),
            ("🎨  الوضع (فاتح/داكن)", self._pick_theme),
        ], icon=("gear", G.NAV_BRONZE), tip="الموسم وكثافة الصفوف وحجم الخط والوضع")
        if self._ui.get("sidebar_collapsed"):
            self._set_sidebar_collapsed(True)

    # ---- اختيارات الإعدادات (من الشريط الجانبي) ----
    def _pick_season(self) -> None:
        self._choose("اختر الموسم (السنة)", list(self._season_years),
                     self._season.get(),
                     lambda v: (self._season.set(v), self._on_season_change()))

    def _pick_density(self) -> None:
        def _set(v):
            self._density = v
            self._apply_table_style()
            self._save_ui_settings()
        self._choose("كثافة الصفوف", list(self._DENSITY), self._density, _set)

    def _pick_font(self) -> None:
        def _set(v):
            self._font_size = v
            self._apply_table_style()
            self._save_ui_settings()
        self._choose("حجم الخط", list(self._FONT_SIZES), self._font_size, _set)

    def _pick_theme(self) -> None:
        def _set(v):
            self._theme = v
            self._ui["theme"] = v
            self._settings["ui"] = self._ui
            try:
                save_settings(self._settings)
            except Exception:
                pass
            if self.session is None:
                G.apply_theme(v)
                return
            self._exit_action = "restart"
            self.root.destroy()
        self._choose("الوضع (فاتح/داكن)", list(G.THEMES),
                     getattr(self, "_theme", "فاتح"), _set)

    def _build_topbar(self) -> None:
        """شريط علوي رفيع: عنوان الموسم فقط (بقيّة الأزرار في الشريط الجانبي)."""
        bar = ttk.Frame(self._body, style="Toolbar.TFrame",
                        padding=(18, 12, 18, 6))
        bar.pack(fill=X)
        titles = ttk.Frame(bar, style="Toolbar.TFrame")
        titles.pack(side=RIGHT)
        # العنوان + السنة للعرض فقط (تحديد الموسم من الإعدادات في الشريط الجانبي)
        row1 = ttk.Frame(titles, style="Toolbar.TFrame")
        row1.pack(anchor="e")
        ttk.Label(row1, text="إدارة موسم العمرة", font=(G._FSB, 18),
                  foreground=G.TEXT, background=G.BG).pack(side=RIGHT)
        ttk.Label(row1, textvariable=self._season, font=(G._FSB, 18, "bold"),
                  foreground=G.BRONZE, background=G.BG).pack(side=RIGHT, padx=(8, 0))
        self._subtitle = ttk.Label(titles, text=self._season_text(),
                                    font=(G._FUI, 10), foreground=G.MUTED,
                                    background=G.BG)
        self._subtitle.pack(anchor="e")

    # ---- جدول البرامج ----
    def _build_table(self) -> None:
        wrap = ttk.Frame(self._body, style="Toolbar.TFrame", padding=(16, 4, 16, 14))
        wrap.pack(fill=BOTH, expand=True)

        # صفّ الفلاتر والبحث (بنفس تصميم نافذة الحج): زرّ «الفلاتر» + بحث فوري
        filt = ttk.Frame(wrap, style="Toolbar.TFrame")
        filt.pack(fill=X, pady=(0, 4))
        # مربّع البحث الحرّ أقصى اليمين
        self._query = StringVar(master=self.root, value="")
        ent = ttk.Entry(filt, textvariable=self._query, width=20,
                        justify="right", font=(G._FUI, 10))
        ent.pack(side=RIGHT, padx=(0, 6))
        ttk.Label(filt, text=G.rtl("🔍 بحث"), font=(G._FUI, 9),
                  background=G.BG, foreground=G.TEXT).pack(side=RIGHT, padx=(2, 4))
        # زرّ واحد يفتح لوحة الفلاتر (فندق مكة/المدينة/حالة السعة)
        self._filter_btn = self._icon_button(
            filt, "الفلاتر  ▾", self._toggle_filter_panel, "Ghost.TButton",
            ("filter", G.TEXT))
        self._filter_btn.pack(side=RIGHT, padx=(0, 12))
        # صفّ رقائق الفلاتر النشطة (يُظهَر في _reload عند وجود فلاتر)
        self._chips_row = ttk.Frame(wrap, style="Toolbar.TFrame")
        self._build_filter_panel()
        self._query.trace_add("write", lambda *a: self._reload())

        # الجدول داخل بطاقة مدوّرة (مظهر عصري) مع تباعد أوسع للصفوف
        try:
            ttk.Style().configure("Treeview", rowheight=32, font=(G._FUI, 11))
        except Exception:
            pass
        if _HAS_CTK:
            card = _ctk.CTkFrame(wrap, corner_radius=16, fg_color=G.PANEL,
                                 border_width=1, border_color=G.BORDER)
            card.pack(fill=BOTH, expand=True)
            holder = ttk.Frame(card, style="Panel.TFrame")
            holder.pack(fill=BOTH, expand=True, padx=8, pady=8)
        else:
            holder = ttk.Frame(wrap, style="Toolbar.TFrame")
            holder.pack(fill=BOTH, expand=True)
        cols = ("code", "name", "depart", "return", "makkah", "madinah",
                "count", "capacity", "remaining")
        heads = {"code": "الرمز", "name": "اسم البرنامج", "depart": "المغادرة",
                 "return": "العودة", "makkah": "فندق مكة",
                 "madinah": "فندق المدينة", "count": "المعتمرون",
                 "capacity": "السعة", "remaining": "المتبقّي"}
        widths = {"code": 56, "name": 200, "depart": 96, "return": 96,
                  "makkah": 150, "madinah": 150, "count": 84, "capacity": 62,
                  "remaining": 96}
        self._cols, self._heads = cols, heads
        self._sort = None                  # (العمود، معكوس) — للفرز بالنقر
        self.tree = ttk.Treeview(holder, columns=cols, show="headings",
                                 selectmode="browse")
        for c in cols:
            self.tree.heading(c, text=heads[c],
                              command=lambda col=c: self._sort_by(col))
            anchor = "e" if c in ("name", "makkah", "madinah") else "center"
            self.tree.column(c, width=widths[c], anchor=anchor)
        vs = ttk.Scrollbar(holder, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        vs.pack(side=RIGHT, fill="y")
        self.tree.tag_configure("odd", background=G.PANEL)
        # تلوين حسب حالة السعة: مكتمل (أخضر باهت) / متجاوز (أحمر باهت)
        self.tree.tag_configure("full", background="#E6F1E9")
        self.tree.tag_configure("over", background="#F6D9D0")
        self.tree.bind("<Double-1>", lambda _e: self.open_pilgrims())
        # وسيلة إيضاح ألوان السعة — تُقرأ بلمحة
        import tkinter as _tk
        legend = ttk.Frame(wrap, style="Toolbar.TFrame", padding=(2, 6, 2, 0))
        legend.pack(side="bottom", fill=X)
        for txt, color in (("مكتمل السعة", "#E6F1E9"),
                           ("متجاوز السعة", "#F6D9D0")):
            item = ttk.Frame(legend, style="Toolbar.TFrame")
            item.pack(side=RIGHT, padx=(0, 14))
            ttk.Label(item, text=G.rtl(txt), font=(G._FUI, 9),
                      foreground=G.MUTED, background=G.BG).pack(
                          side=RIGHT, padx=(0, 5))
            sw = _tk.Frame(item, background=color, width=16, height=12,
                           highlightbackground=G.BORDER, highlightthickness=1)
            sw.pack(side=RIGHT)
            sw.pack_propagate(False)

        self._empty = ttk.Label(
            self._body, justify="center", background=G.BG, foreground=G.MUTED,
            font=(G._FUI, 12),
            text=G.rtl("🌙  لا برامج في هذا الموسم بعد.\n\n"
                       "ابدأ بـ «➕ برنامج جديد» لإنشاء أوّل برنامج عمرة،\n"
                       "أو غيّر «الموسم» أعلى النافذة لعرض موسمٍ آخر."))

    # ---- لوحة الفلاتر (بنفس أسلوب نافذة الحج، بحقول العمرة) ----
    _ALL = "الكل"
    _STATUS_OPTIONS = ("الكل", "متاح", "مكتمل", "متجاوز السعة")
    # (المفتاح، العنوان، سمة البرنامج)
    _FILTER_FIELDS = (("makkah", "فندق مكة", "makkah_hotel"),
                      ("madinah", "فندق المدينة", "madinah_hotel"))

    def _build_filter_panel(self) -> None:
        """لوحة منسدلة تجمع فلاتر برامج العمرة (الفنادق وحالة السعة)."""
        self.filter_vars = {"makkah": StringVar(value=self._ALL),
                            "madinah": StringVar(value=self._ALL),
                            "status": StringVar(value=self._ALL)}
        self.filter_boxes = {}
        panel = Toplevel(self.root)
        panel.withdraw()
        panel.overrideredirect(True)
        panel.configure(bg=G.BORDER)                 # إطار رفيع
        self._filter_panel = panel
        inner = ttk.Frame(panel, style="Panel.TFrame", padding=14)
        inner.pack(padx=1, pady=1)
        ttk.Label(inner, text=G.rtl("تصفية البرامج"), font=(G._FSB, 11),
                  foreground=G.TEXT, background=G.BG).grid(
                      row=0, column=0, columnspan=4, sticky="e", pady=(0, 8))
        rows = [("makkah", "فندق مكة"), ("madinah", "فندق المدينة"),
                ("status", "حالة السعة")]
        for i, (key, label) in enumerate(rows):
            ttk.Label(inner, text=G.rtl(label), font=(G._FUI, 9),
                      foreground=G.TEXT, background=G.BG).grid(
                          row=1 + i, column=1, sticky="e", padx=(10, 3), pady=3)
            vals = ([self._ALL] if key != "status"
                    else list(self._STATUS_OPTIONS))
            box = ttk.Combobox(inner, textvariable=self.filter_vars[key],
                               state="readonly", width=18, font=(G._FUI, 9),
                               values=vals)
            box.grid(row=1 + i, column=0, sticky="e", pady=3)
            box.bind("<<ComboboxSelected>>", lambda _e: self._reload())
            self.filter_boxes[key] = box
        ttk.Separator(inner, orient="horizontal").grid(
            row=97, column=0, columnspan=4, sticky="ew", pady=(12, 0))
        btns = ttk.Frame(inner, style="Panel.TFrame")
        btns.grid(row=99, column=0, columnspan=4, sticky="e", pady=(12, 0))
        self._mkbtn(btns, "🧹 مسح الفلاتر", self.clear_filters).pack(
            side=RIGHT, padx=3)
        self._mkbtn(btns, "إغلاق", self._hide_filter_panel).pack(
            side=RIGHT, padx=3)
        panel.bind("<Escape>", lambda _e: self._hide_filter_panel())

    def clear_filters(self) -> None:
        for v in self.filter_vars.values():
            v.set(self._ALL)
        if hasattr(self, "_query"):
            self._query.set("")
        self._reload()

    def _update_filter_button(self) -> None:
        if not hasattr(self, "_filter_btn"):
            return
        active = sum(1 for v in self.filter_vars.values() if v.get() != self._ALL)
        text = f"الفلاتر ({active})  ▾" if active else "الفلاتر  ▾"
        self._filter_btn.configure(text=G.rtl(text))

    def _populate_filter_values(self, trips) -> None:
        """يملأ قوائم الفنادق من برامج الموسم (كما في فلاتر الحج)."""
        if not hasattr(self, "filter_boxes"):
            return
        for key, _label, attr in self._FILTER_FIELDS:
            vals = sorted({(getattr(t, attr) or "").strip()
                           for t in trips if (getattr(t, attr) or "").strip()})
            self.filter_boxes[key].configure(values=[self._ALL, *vals])
            if self.filter_vars[key].get() not in (self._ALL, *vals):
                self.filter_vars[key].set(self._ALL)   # قيمة اختفت بتغيّر الموسم

    def _update_chips(self) -> None:
        """يعرض الفلاتر النشطة كوسوم قابلة للإزالة بنقرة (كما في الحج)."""
        if not hasattr(self, "_chips_row"):
            return
        for w in self._chips_row.winfo_children():
            w.destroy()
        active = []
        labels = {"makkah": "فندق مكة", "madinah": "فندق المدينة",
                  "status": "حالة السعة"}
        for key, label in labels.items():
            val = self.filter_vars[key].get()
            if val != self._ALL:
                active.append((f"{label}: {val}",
                               lambda k=key: (self.filter_vars[k].set(self._ALL),
                                              self._reload())))
        q = (self._query.get() if hasattr(self, "_query") else "").strip()
        if q:
            active.append((f"بحث: {q}", lambda: self._query.set("")))
        if not active:
            self._chips_row.pack_forget()
            return
        self._chips_row.pack(fill=X, pady=(4, 0))
        ttk.Label(self._chips_row, text=G.rtl("الفلاتر النشطة:"),
                  font=(G._FUI, 9), foreground=G.MUTED,
                  background=G.BG).pack(side=RIGHT, padx=(0, 6))
        import tkinter as _tk
        for text, clear in active:
            chip = _tk.Label(self._chips_row, text=G.rtl(f" ✕  {text} "),
                             bg=G.GHOST_BG, fg=G.TEXT, font=(G._FUI, 9),
                             padx=2, cursor="hand2")
            chip.pack(side=RIGHT, padx=3)
            chip.bind("<Button-1>", lambda _e, c=clear: c())

    def _season_text(self) -> str:
        y = self._season.get()
        return f"موسم العمرة {y} — من ١ يناير إلى ٣١ ديسمبر {y}"

    def _on_season_change(self) -> None:
        self._settings["umrah_season"] = self._season.get()
        try:
            save_settings(self._settings)
        except OSError:
            pass
        if hasattr(self, "_subtitle"):
            self._subtitle.configure(text=self._season_text())
        self._reload()

    def _season_trips(self) -> list:
        """برامج الموسم المختار (البرنامج بلا تاريخ يظهر في كل المواسم)."""
        season = self._season.get()
        return [t for t in self.trips
                if not umrah.trip_year(t) or umrah.trip_year(t) == season]

    def _visible_trips(self) -> list:
        """برامج الموسم بعد تطبيق البحث الفوري وفلاتر الفنادق وحالة السعة."""
        trips = self._season_trips()
        q = (self._query.get() if hasattr(self, "_query") else "").strip().lower()
        if q:
            trips = [t for t in trips
                     if q in (t.code or "").lower()
                     or q in (t.name or "").lower()
                     or q in (t.makkah_hotel or "").lower()
                     or q in (t.madinah_hotel or "").lower()]
        fv = getattr(self, "filter_vars", None)
        if not fv:
            return trips
        mk, md = fv["makkah"].get(), fv["madinah"].get()
        if mk != self._ALL:
            trips = [t for t in trips if (t.makkah_hotel or "").strip() == mk]
        if md != self._ALL:
            trips = [t for t in trips if (t.madinah_hotel or "").strip() == md]
        st = fv["status"].get()
        if st != self._ALL:
            def _match(t):
                try:
                    cap = int(float(str(t.capacity or "").strip() or 0))
                except ValueError:
                    cap = 0
                if not cap:
                    return False                 # بلا سعة محدّدة → بلا حالة
                n = len(umrah.trip_pilgrims(self.records, t.code))
                if st == "متاح":
                    return n < cap
                if st == "مكتمل":
                    return n == cap
                return n > cap                   # متجاوز السعة
            trips = [t for t in trips if _match(t)]
        return trips

    def _sort_by(self, col: str) -> None:
        """يفرز البرامج حسب عمودٍ عند النقر على رأسه (يبدّل الاتجاه بالنقر ثانيةً)."""
        if self._sort and self._sort[0] == col:
            self._sort = (col, not self._sort[1])
        else:
            self._sort = (col, False)
        self._reload()

    def _update_headings(self) -> None:
        for c in self._cols:
            txt = self._heads[c]
            if self._sort and self._sort[0] == c:
                txt += "  " + ("▼" if self._sort[1] else "▲")
            self.tree.heading(c, text=txt)

    def _apply_sort(self, rows: list) -> list:
        if not self._sort:
            return rows
        col, rev = self._sort
        def key(row):
            t = row["t"]
            return {
                "count": row["n"], "capacity": row["cap"],
                "remaining": (row["seats"] if row["seats"] is not None else -1),
                "code": (t.code or "").lower(), "name": (t.name or "").lower(),
                "depart": t.depart_date or "", "return": t.return_date or "",
                "makkah": (t.makkah_hotel or "").lower(),
                "madinah": (t.madinah_hotel or "").lower(),
            }.get(col, "")
        return sorted(rows, key=key, reverse=rev)

    def _reload(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self._populate_filter_values(self._season_trips())
        rows = []
        n_pil = cap_total = late = 0
        total = paid = 0.0
        for t in self._visible_trips():
            pilgrims = umrah.trip_pilgrims(self.records, t.code)
            n = len(pilgrims)
            n_pil += n
            for r in pilgrims:
                pv = parse_amount(r.program_value) or 0.0
                pd = parse_amount(r.paid_amount) or 0.0
                total += pv
                paid += pd
                if pv - pd > 0.5:
                    late += 1
            try:
                cap = int(float(str(t.capacity or "").strip() or 0))
            except ValueError:
                cap = 0
            cap_total += cap
            rows.append({"t": t, "n": n, "cap": cap,
                         "seats": (cap - n) if cap else None})
        rows = self._apply_sort(rows)
        self._update_headings()
        for i, row in enumerate(rows):
            t, n, cap, seats_left = row["t"], row["n"], row["cap"], row["seats"]
            # تلوين الصفّ: متجاوز السعة (أحمر) / مكتمل (أخضر) / تخطيط متناوب
            if cap and n > cap:
                tag = "over"
            elif cap and seats_left == 0:
                tag = "full"
            else:
                tag = "odd" if i % 2 else ""
            self.tree.insert("", END, iid=t.code, values=(
                t.code, t.name or "—", t.depart_date or "—", t.return_date or "—",
                t.makkah_hotel or "—", t.madinah_hotel or "—",
                n, t.capacity or "—",
                seats_left if seats_left is not None else "—"),
                tags=(tag,) if tag else ())
        shown = rows
        if hasattr(self, "_status"):
            self._status.configure(text=(
                f"🗂 البرامج: {len(shown)}    ·    👤 المعتمرون: {n_pil}"
                f"    ·    💰 المحصّل: {format_amount(paid)}"
                f"    ·    ⏳ المتبقّي: {format_amount(total - paid)}"))
        self._update_kpi(n_pil, cap_total, total, paid, late)
        self._update_filter_button()
        self._update_chips()
        if not shown:
            q = (self._query.get() if hasattr(self, "_query") else "").strip()
            _flt_on = any(v.get() != self._ALL
                          for v in getattr(self, "filter_vars", {}).values())
            if q or _flt_on:
                self._empty.configure(text=G.rtl(
                    "🔎  لا برامج مطابقة للبحث/الفلاتر الحالية.\n\n"
                    "عدّل الفلاتر أو اضغط «🧹 مسح الفلاتر»."))
            else:
                self._empty.configure(text=G.rtl(
                    "🌙  لا برامج في هذا الموسم بعد.\n\n"
                    "ابدأ بـ «➕ برنامج جديد» لإنشاء أوّل برنامج عمرة،\n"
                    "أو غيّر «الموسم» أعلى النافذة لعرض موسمٍ آخر."))
            self._empty.pack(pady=24)
        else:
            self._empty.pack_forget()

    def _selected_trip(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return next((t for t in self.trips if t.code == sel[0]), None)

    # ---- أوامر البرامج ----
    def new_trip(self) -> None:
        trip = umrah.UmrahTrip(code=umrah.next_code(self.trips))
        TripEditorDialog(self.root, trip, {t.code for t in self.trips},
                         self._on_trip_saved, title="برنامج عمرة جديد")

    def edit_trip(self) -> None:
        trip = self._selected_trip()
        if trip is None:
            messagebox.showinfo("تعديل", "اختر برنامجاً أولاً.", parent=self.root)
            return
        others = {t.code for t in self.trips if t is not trip}
        TripEditorDialog(self.root, trip, others, self._on_trip_saved,
                         title=f"تعديل البرنامج — {trip.name or trip.code}")

    def _on_trip_saved(self, trip) -> None:
        if trip not in self.trips:
            self.trips.append(trip)
        self.save_trips()
        # ابقِ البرنامج ظاهراً: انتقل إلى موسم سنته إن اختلف
        yr = umrah.trip_year(trip)
        if yr and yr != self._season.get() and yr in self._season_years:
            self._season.set(yr)
            self._on_season_change()
        self._reload()
        try:
            self.tree.selection_set(trip.code)
        except Exception:
            pass

    def delete_trip(self) -> None:
        trip = self._selected_trip()
        if trip is None:
            messagebox.showinfo("حذف", "اختر برنامجاً أولاً.", parent=self.root)
            return
        n = len(umrah.trip_pilgrims(self.records, trip.code))
        msg = f"حذف البرنامج «{trip.name or trip.code}»؟"
        if n:
            msg += (f"\n\nملاحظة: به {n} معتمراً. سيبقون في البيانات دون برنامج "
                    "(لن يُحذفوا).")
        if not messagebox.askyesno("حذف البرنامج", msg, parent=self.root):
            return
        self.trips.remove(trip)
        self.save_trips()
        self._reload()

    def open_pilgrims(self) -> None:
        trip = self._selected_trip()
        if trip is None:
            messagebox.showinfo("المعتمرون", "اختر برنامجاً أولاً.", parent=self.root)
            return
        TripPilgrimsWindow(self, trip)

    def new_manual_voucher(self) -> None:
        """فاوتشر فندق لأي حجز — حتى خارج برامج العمرة — يُملأ يدوياً بالكامل."""
        co = self._settings.get("company")
        co = co if isinstance(co, dict) else None
        number = umrah.next_voucher_number(self._settings)
        try:
            save_settings(self._settings)
        except OSError:
            pass
        rec = PassportData()
        data = build_voucher_data(rec, trip=None, program_name="",
                                  company=co, number=number)
        VoucherEditorDialog(self.root, rec, None, data, program="",
                            company=co, app=self)

    def new_transport_request(self) -> None:
        """طلب حجز مواصلات لأي حجز — يُملأ يدوياً بالكامل (خارج البرامج)."""
        co = self._settings.get("company")
        co = co if isinstance(co, dict) else None
        number = umrah.next_transport_number(self._settings)
        try:
            save_settings(self._settings)
        except OSError:
            pass
        rec = PassportData()
        data = build_transport_request_data(rec, trip=None, program_name="",
                                            company=co, number=number)
        TransportRequestEditorDialog(self.root, rec, None, data, company=co,
                                     app=self)

    def open_transport_requests(self) -> None:
        """قائمة طلبات المواصلات المحفوظة (فتح/تعديل، معاينة، حذف)."""
        TransportRequestsListWindow(self.root, self)

    def open_vouchers(self) -> None:
        """قائمة الفاوتشرات المحفوظة (فتح/تعديل، معاينة، حذف)."""
        VouchersListWindow(self.root, self)

    def _season_stats(self):
        """إحصاءات برامج الموسم المعروض: صفوف لكل برنامج + إجماليات."""
        rows = []
        tot_total = tot_paid = 0.0
        tot_pil = 0
        for t in self._visible_trips():
            pilgrims = umrah.trip_pilgrims(self.records, t.code)
            total = sum(parse_amount(r.program_value) or 0.0 for r in pilgrims)
            paid = sum(parse_amount(r.paid_amount) or 0.0 for r in pilgrims)
            rows.append({"name": t.name or t.code, "count": len(pilgrims),
                         "total": total, "paid": paid})
            tot_total += total
            tot_paid += paid
            tot_pil += len(pilgrims)
        totals = {
            "programs": len(rows), "pilgrims": tot_pil,
            "paid": format_amount(tot_paid),
            "remaining": format_amount(tot_total - tot_paid),
            "pct": f"{(tot_paid / tot_total * 100):.0f}%" if tot_total else "0%"}
        return rows, totals

    def open_dashboard(self) -> None:
        """لوحة الموسم: نظرة سريعة على البرامج والتحصيل برسوم بسيطة."""
        rows, totals = self._season_stats()
        if not rows:
            messagebox.showinfo("لوحة الموسم", "لا برامج في هذا الموسم.",
                                parent=self.root)
            return
        SeasonDashboard(self.root, self._season.get(), rows, totals)

    def export_web_dashboard(self) -> None:
        """يولّد لوحة موسم أنيقة بصيغة ويب (HTML) ويفتحها في المتصفّح."""
        from . import dashboard_html
        trips = self._visible_trips()
        if not trips:
            messagebox.showinfo("لوحة الموسم (ويب)",
                                "لا برامج في هذا الموسم.", parent=self.root)
            return
        import os
        import tempfile
        season = self._season.get()
        safe = re.sub(r'[\\/:*?"<>|]+', "-", f"لوحة الموسم {season}").strip()
        path = os.path.join(tempfile.gettempdir(), f"{safe}.html")
        try:
            dashboard_html.export_season_dashboard_html(
                trips, self.records, path,
                season=season, company=self._company_dict())
        except Exception as exc:
            G._log.exception("فشل توليد لوحة الموسم (ويب)")
            messagebox.showerror("لوحة الموسم (ويب)",
                                 f"تعذّر توليد اللوحة:\n\n{exc}", parent=self.root)
            return
        try:
            G.open_in_viewer(path)
        except OSError as exc:
            messagebox.showerror("لوحة الموسم (ويب)",
                                 f"تعذّر فتح المتصفّح:\n\n{exc}", parent=self.root)

    def export_season_pdf(self) -> None:
        """يولّد تقرير الموسم الفاخر (PDF) بتصميم اللوحة، ويفتحه للمعاينة."""
        from . import pdf_io
        trips = self._visible_trips()
        if not trips:
            messagebox.showinfo("تقرير الموسم (PDF)",
                                "لا برامج في هذا الموسم.", parent=self.root)
            return
        season = self._season.get()
        G.open_preview(
            self.root,
            lambda p: pdf_io.export_season_report_pdf(
                trips, self.records, p, season=season,
                company=self._company_dict()),
            f"تقرير الموسم {season}", "pdf")

    def ask_data(self) -> None:
        """يفتح مساعد «اسأل بياناتك» للإجابة عن أسئلة الموسم بالعربية."""
        AskWindow(self.root, UmrahCtx(self))

    def copy_season_summary(self) -> None:
        """ينسخ ملخّص مؤشّرات الموسم إلى الحافظة، جاهزاً للمشاركة."""
        text = assistant.season_summary_text(
            self._visible_trips(), self.records, season=self._season.get(),
            group_attr="trip", company=self._company_dict())
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        messagebox.showinfo("نسخ ملخّص الموسم",
                            "نُسخ الملخّص — الصقه في واتساب أو الإيميل:\n\n"
                            + text, parent=self.root)

    def open_collections(self) -> None:
        """يفتح متابعة التحصيل لكل متأخّري الموسم المعروض مباشرةً."""
        codes = {t.code for t in self._visible_trips()}

        def rem(r):
            return ((parse_amount(r.program_value) or 0)
                    - (parse_amount(r.paid_amount) or 0))
        late = [r for r in self.records
                if str(getattr(r, "trip", "") or "") in codes and rem(r) > 0.5]
        late.sort(key=rem, reverse=True)
        if not late:
            messagebox.showinfo("متابعة التحصيل",
                                "لا متأخرات — الحمد لله، الجميع سدّد بالكامل.",
                                parent=self.root)
            return
        DueFollowupWindow(self.root, UmrahCtx(self), late)

    # ---- كشوف ومستندات البرنامج المحدَّد (من الواجهة الرئيسية) ----
    def _company_dict(self):
        co = self._settings.get("company")
        return co if isinstance(co, dict) else None

    def _sel_trip_or_warn(self, title):
        t = self._selected_trip()
        if t is None:
            messagebox.showinfo(title, "اختر برنامجاً من القائمة أولاً.",
                                parent=self.root)
        return t

    def _prog_recs(self, trip, title):
        recs = umrah.trip_pilgrims(self.records, trip.code)
        if not recs:
            messagebox.showinfo(title, "لا معتمرين في هذا البرنامج.",
                                parent=self.root)
        return recs

    def _prog_name(self, trip):
        return f"{trip.code} — {trip.name}" if trip.name else trip.code

    def prog_finance(self):
        t = self._sel_trip_or_warn("الملخّص المالي")
        if t is None or not self._prog_recs(t, "الملخّص المالي"):
            return
        UmrahFinanceWindow(self.root, self, t, on_change=self._reload)

    def prog_rooming(self):
        t = self._sel_trip_or_warn("التسكين")
        if t is None or not self._prog_recs(t, "التسكين"):
            return
        RoomingWindow(self, t)

    def prog_transport(self):
        t = self._sel_trip_or_warn("المواصلات")
        if t is None or not self._prog_recs(t, "المواصلات"):
            return
        TransportWindow(self, t)

    def prog_airline(self):
        t = self._sel_trip_or_warn("كشف الطيران")
        if t is None:
            return
        recs = self._prog_recs(t, "كشف الطيران")
        if not recs:
            return
        G.open_preview(self.root, lambda p: export_airline_pdf(
            recs, p, title=f"Flight Manifest — {t.code}"),
            f"طيران {t.code}", "pdf")

    def prog_cards(self):
        t = self._sel_trip_or_warn("بطاقات العمرة")
        if t is None:
            return
        recs = self._prog_recs(t, "بطاقات العمرة")
        if not recs:
            return
        G.open_preview(self.root, lambda p: export_umrah_cards_pdf(
            recs, p, program_name=self._prog_name(t),
            company=self._company_dict(), session=self.session,
            emergency_uae=str(getattr(t, "emergency_uae", "") or ""),
            emergency_ksa=str(getattr(t, "emergency_ksa", "") or "")),
            f"بطاقات {t.code}", "pdf")

    def _pick_pilgrim(self, trip, title):
        """يعرض منتقي معتمر لبرنامجٍ (يعيد السجلّ أو None)."""
        recs = umrah.trip_pilgrims(self.records, trip.code)
        if not recs:
            messagebox.showinfo(title, "لا معتمرين في هذا البرنامج.",
                                parent=self.root)
            return None
        if len(recs) == 1:
            return recs[0]
        win = Toplevel(self.root)
        win.title(title)
        win.configure(bg=G.BG)
        win.transient(self.root)
        frm = ttk.Frame(win, padding=12)
        frm.pack(fill=BOTH, expand=True)
        ttk.Label(frm, text="اختر المعتمر:").pack(anchor="e", pady=(0, 6))
        names = [f"{i + 1}. "
                 f"{r.full_name_ar or r.full_name_en or r.passport_number or '—'}"
                 for i, r in enumerate(recs)]
        var = StringVar(value=names[0])
        ttk.Combobox(frm, textvariable=var, values=names, state="readonly",
                     width=42).pack(fill=X)
        chosen = {"rec": None}

        def ok():
            try:
                chosen["rec"] = recs[names.index(var.get())]
            except ValueError:
                chosen["rec"] = recs[0]
            win.destroy()
        btns = ttk.Frame(frm)
        btns.pack(fill=X, pady=(10, 0))
        ttk.Button(btns, text="اختيار", command=ok).pack(side=RIGHT)
        ttk.Button(btns, text="إلغاء", command=win.destroy).pack(side=RIGHT,
                                                                 padx=6)
        win.grab_set()
        win.wait_window()
        return chosen["rec"]

    def _prog_doc(self, export_fn, base):
        t = self._sel_trip_or_warn(base)
        if t is None:
            return
        rec = self._pick_pilgrim(t, base)
        if rec is None:
            return
        G.open_preview(self.root, lambda p: export_fn(
            rec, p, program_name=self._prog_name(t),
            company=self._company_dict()), f"{base} {t.code}", "pdf")

    def prog_receipt(self):
        self._prog_doc(export_umrah_receipt_pdf, "سند")

    def prog_invoice(self):
        self._prog_doc(export_umrah_invoice_pdf, "فاتورة")

    def prog_contract(self):
        self._prog_doc(export_umrah_contract_pdf, "عقد")

    def prog_quotation(self):
        t = self._sel_trip_or_warn("عرض سعر")
        if t is None:
            return
        rec = self._pick_pilgrim(t, "عرض سعر")
        if rec is None:
            return
        number = umrah.next_quote_number(self._settings)
        try:
            save_settings(self._settings)
        except OSError:
            pass
        co = self._company_dict()
        data = build_quotation_data(rec, trip=t, company=co, number=number)
        QuotationEditorDialog(self.root, rec, t, data, app=self, company=co)

    def open_quotes(self) -> None:
        """فتح قائمة «عروض الأسعار» المحفوظة للبرنامج المحدّد."""
        trip = self._selected_trip()
        if trip is None:
            messagebox.showinfo("عروض الأسعار", "اختر برنامجاً أولاً.",
                                parent=self.root)
            return
        QuotesListWindow(self.root, self, trip)

    def new_manual_quotation(self) -> None:
        """عرض سعر لأي رحلة — حتى خارج البرامج — يُملأ يدوياً بالكامل."""
        co = self._settings.get("company")
        co = co if isinstance(co, dict) else None
        number = umrah.next_quote_number(self._settings)
        try:
            save_settings(self._settings)
        except OSError:
            pass
        rec = PassportData()
        data = build_quotation_data(rec, trip=None, company=co, number=number)
        QuotationEditorDialog(self.root, rec, None, data, app=self, company=co)

    def open_manual_quotes(self) -> None:
        """قائمة «عروض الأسعار اليدوية» المحفوظة (خارج البرامج)."""
        QuotesListWindow(self.root, self, None)

    def open_group_pricer(self) -> None:
        """مسعّر المجموعات: أداة حساب كلفة الفرد وسعر البيع لكل نوع غرفة."""
        GroupPricerWindow(self.root, self)

    def open_pricings(self) -> None:
        """قائمة التسعيرات المحفوظة (فتح/تعديل، معاينة، حذف)."""
        PricingsListWindow(self.root, self)

    def toggle_theme(self) -> None:
        """يبدّل بين الوضع الفاتح والداكن ويعيد البناء نظيفاً بالوضع الجديد."""
        self._theme = "داكن" if self._theme == "فاتح" else "فاتح"
        self._ui["theme"] = self._theme
        self._settings["ui"] = self._ui
        try:
            save_settings(self._settings)
        except OSError:
            pass
        if self.session is None:                 # وضع مفتوح — طبّق قدر الإمكان
            G.apply_theme(self._theme)
            return
        self._exit_action = "restart"            # إعادة بناء بالوضع الجديد
        self.root.destroy()

    # ---- الخروج والتبديل ----
    def switch_mode(self) -> None:
        if not messagebox.askyesno(
                "تبديل الوضع",
                f"الانتقال إلى وضع «{app_mode.mode_label(app_mode.HAJJ)}»؟\n"
                "لكلّ وضع بياناته المستقلّة.", parent=self.root):
            return
        # ننتقل مباشرةً إلى نافذة الحج (بلا المرور بشاشة الاختيار)
        self._exit_action = f"switch:{app_mode.HAJJ}"
        self.root.destroy()

    def do_logout(self) -> None:
        if self.session is None:
            return
        if not messagebox.askyesno(
                "تسجيل الخروج",
                f"تسجيل خروج «{self.session.username}» والعودة إلى شاشة الدخول؟",
                parent=self.root):
            return
        self._exit_action = "logout"
        self.root.destroy()


class TripEditorDialog(Toplevel):
    """نافذة إنشاء/تعديل برنامج عمرة: التفاصيل، الأسعار، الطيران، والخدمات."""

    def __init__(self, parent, trip, existing_codes, on_save,
                 *, title="برنامج") -> None:
        super().__init__(parent)
        self.trip = trip
        self.existing = set(existing_codes)
        self.on_save = on_save
        self.title(title)
        self.configure(bg=G.BG)
        self.transient(parent)
        self.resizable(True, True)
        self.grab_set()
        G.enable_minmax(self)
        self.vars: dict[str, StringVar] = {}

        outer = ttk.Frame(self, padding=14)
        outer.pack(fill=BOTH, expand=True)
        nb = ttk.Notebook(outer)
        nb.pack(fill=BOTH, expand=True)
        nb.add(self._tab_basic(nb), text="البرنامج والأسعار")
        nb.add(self._tab_flight(nb), text="الطيران والنقل")
        nb.add(self._tab_services(nb), text="الخدمات")

        btns = ttk.Frame(outer)
        btns.pack(fill=X, pady=(14, 0))
        ttk.Button(btns, text=G.rtl("💾 حفظ البرنامج"), style="Primary.TButton",
                   command=self._save).pack(side=RIGHT, padx=3)
        ttk.Button(btns, text="إلغاء", style="Ghost.TButton",
                   command=self.destroy).pack(side=LEFT, padx=3)
        self.bind("<Escape>", lambda _e: self.destroy())
        _center(self, parent)

    def _field(self, parent, key, label, width, row, col) -> None:
        cell = ttk.Frame(parent)
        cell.grid(row=row, column=col, sticky="e", padx=8, pady=4)
        ttk.Label(cell, text=label, font=(G._FUI, 10),
                  foreground=G.TEXT).pack(side=RIGHT, padx=(8, 4))
        v = StringVar(value=str(getattr(self.trip, key, "") or ""))
        self.vars[key] = v
        ttk.Entry(cell, textvariable=v, width=width, justify="right").pack(side=RIGHT)

    def _tab_basic(self, nb) -> ttk.Frame:
        f = ttk.Frame(nb, padding=12)
        rows = [("code", "رمز البرنامج *", 14), ("name", "اسم البرنامج", 32),
                ("depart_date", "تاريخ المغادرة", 18),
                ("return_date", "تاريخ العودة", 18),
                ("makkah_hotel", "فندق مكة", 30), ("makkah_nights", "ليالي مكة", 12),
                ("makkah_rooms", "عدد غرف مكة", 12),
                ("madinah_hotel", "فندق المدينة", 30),
                ("madinah_nights", "ليالي المدينة", 12),
                ("madinah_rooms", "عدد غرف المدينة", 12)]
        for i, (key, label, width) in enumerate(rows):
            r, c = divmod(i, 2)
            self._field(f, key, label, width, r, c)

        pf = ttk.LabelFrame(f, text=G.rtl("أسعار الفرد حسب الغرفة (درهم)"),
                            padding=8)
        pf.grid(row=(len(rows) + 1) // 2 + 1, column=0, columnspan=2,
                sticky="ew", pady=(10, 0), padx=6)
        for i, (key, name, _cap) in enumerate(umrah.ROOM_TYPES):
            self._field(pf, key, name, 12, i // 3, i % 3)
        return f

    def _tab_flight(self, nb) -> ttk.Frame:
        f = ttk.Frame(nb, padding=12)
        self._field(f, "airline", "شركة الطيران", 26, 0, 0)
        self._field(f, "capacity", "سعة الطيران (مقاعد)", 12, 0, 1)
        self._field(f, "flight_pnr", "PNR الطيران", 16, 1, 0)

        out = ttk.LabelFrame(f, text=G.rtl("رحلة الذهاب"), padding=8)
        out.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0), padx=6)
        self._field(out, "flight_out", "رقم الرحلة", 16, 0, 0)
        self._field(out, "out_depart_time", "وقت المغادرة", 14, 0, 1)
        self._field(out, "out_arrive_time", "وقت الوصول", 14, 1, 0)

        ret = ttk.LabelFrame(f, text=G.rtl("رحلة العودة"), padding=8)
        ret.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0), padx=6)
        self._field(ret, "flight_ret", "رقم الرحلة", 16, 0, 0)
        self._field(ret, "ret_depart_time", "وقت المغادرة", 14, 0, 1)
        self._field(ret, "ret_arrive_time", "وقت الوصول", 14, 1, 0)

        tr = ttk.LabelFrame(f, text=G.rtl("النقل الداخلي (سيارة خاصة)"), padding=8)
        tr.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0), padx=6)
        self._field(tr, "transport", "الافتراضي", 26, 0, 0)
        self._field(tr, "transport_pnr", "PNR النقل", 16, 0, 1)
        ttk.Label(tr, text=G.rtl("يُحدَّد آلياً حسب العدد: شخصان ← فورد، "
                                 "٣ فأكثر ← جيمس (٦ كحدّ أقصى) — قابل للتعديل يدوياً"),
                  font=(G._FUI, 9), foreground=G.MUTED).grid(
            row=1, column=0, columnspan=2, sticky="e", pady=(6, 0))

        em = ttk.LabelFrame(f, text=G.rtl("أرقام الطوارئ (تظهر في بطاقة العمرة)"),
                            padding=8)
        em.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 0), padx=6)
        self._field(em, "emergency_uae", "الإمارات", 20, 0, 0)
        self._field(em, "emergency_ksa", "السعودية", 20, 0, 1)
        return f

    def _tab_services(self, nb) -> ttk.Frame:
        f = ttk.Frame(nb, padding=12)
        ttk.Label(f, text=G.rtl("اختر الخدمات المتاحة وسعر الفرد لكلٍّ (درهم):"),
                  font=(G._FSB, 11), foreground=G.BRONZE,
                  background=G.BG).grid(row=0, column=0, columnspan=3, sticky="e",
                                        pady=(0, 8))
        existing = {s.get("name", ""): str(s.get("price", ""))
                    for s in (self.trip.services or [])}
        names = list(umrah.DEFAULT_SERVICES)
        for extra in existing:
            if extra and extra not in names:
                names.append(extra)
        self.svc_on: dict[str, BooleanVar] = {}
        self.svc_price: dict[str, StringVar] = {}
        for i, name in enumerate(names):
            on = BooleanVar(value=name in existing)
            pr = StringVar(value=existing.get(name, ""))
            self.svc_on[name] = on
            self.svc_price[name] = pr
            ttk.Checkbutton(f, text=G.rtl(name), variable=on).grid(
                row=i + 1, column=0, sticky="e", padx=(6, 4), pady=3)
            ttk.Entry(f, textvariable=pr, width=10, justify="center").grid(
                row=i + 1, column=1, sticky="w", pady=3)
            ttk.Label(f, text="درهم", font=(G._FUI, 9),
                      foreground=G.MUTED).grid(row=i + 1, column=2, sticky="w")

        ttk.Label(f, text=G.rtl("ملاحظات:"), font=(G._FUI, 10),
                  foreground=G.TEXT).grid(row=len(names) + 2, column=0,
                                          sticky="e", pady=(10, 2))
        self.notes = Text(f, height=3, width=54, wrap="word", font=(G._FUI, 10))
        self.notes.grid(row=len(names) + 3, column=0, columnspan=3, sticky="ew")
        self.notes.insert("1.0", self.trip.notes or "")
        return f

    def _save(self) -> None:
        code = self.vars["code"].get().strip()
        if not code:
            messagebox.showwarning("رمز مطلوب", "أدخل رمز البرنامج.", parent=self)
            return
        if code in self.existing:
            messagebox.showwarning("رمز مكرّر",
                                   f"الرمز «{code}» مستعمل في برنامج آخر.",
                                   parent=self)
            return
        for key, v in self.vars.items():
            setattr(self.trip, key, v.get().strip())
        self.trip.services = [
            {"name": name, "price": self.svc_price[name].get().strip()}
            for name, on in self.svc_on.items() if on.get()]
        self.trip.notes = self.notes.get("1.0", END).strip()
        self.on_save(self.trip)
        self.destroy()


class BookingDialog(Toplevel):
    """حجز بالتسعير: تضبط الغرفة والخدمات والنقل، ثم تضيف كل شخص بقراءة جوازه
    أو يدوياً — ويُطبَّق السعر والغرفة والنقل المحسوب على كل معتمر تلقائياً."""

    def __init__(self, window: "TripPilgrimsWindow", trip) -> None:
        super().__init__(window)
        self.window = window
        self.app = window.app
        self.session = window.session
        self.trip = trip
        self._added = 0
        self.title(f"إضافة حجز بالتسعير — {trip.name or trip.code}")
        self.configure(bg=G.BG)
        self.transient(window)
        self.resizable(True, True)
        self.grab_set()
        G.enable_minmax(self)
        self._room_by_name = {name: key for key, name, _c in umrah.ROOM_TYPES}

        f = ttk.Frame(self, padding=16)
        f.pack(fill=BOTH, expand=True)

        top = ttk.Frame(f)
        top.pack(fill=X)
        ttk.Label(top, text=G.rtl("عدد أشخاص الحجز:"), font=(G._FUI, 10),
                  foreground=G.TEXT).pack(side=RIGHT, padx=(8, 4))
        self.persons = StringVar(value="1")
        ttk.Spinbox(top, from_=1, to=50, width=6, textvariable=self.persons,
                    justify="center", command=self._recalc).pack(side=RIGHT)
        self.persons.trace_add("write", lambda *_a: self._recalc())

        ttk.Label(top, text=G.rtl("نوع الغرفة:"), font=(G._FUI, 10),
                  foreground=G.TEXT).pack(side=RIGHT, padx=(16, 4))
        self.room = StringVar(value=umrah.ROOM_TYPES[1][1])   # ثنائي افتراضاً
        cb = ttk.Combobox(top, textvariable=self.room, state="readonly", width=10,
                          justify="center",
                          values=[name for _k, name, _c in umrah.ROOM_TYPES])
        cb.pack(side=RIGHT)
        cb.bind("<<ComboboxSelected>>", lambda _e: self._recalc())

        # الخدمات: اختيار وتسعير يدوي + إمكانية إضافة خدمة مخصّصة
        self.svc_rows: list = []
        sf = ttk.LabelFrame(f, text=G.rtl("الخدمات (اختر وسعّر لكل فرد — أو أضِف خدمة)"),
                            padding=8)
        sf.pack(fill=X, pady=(12, 0))
        self._svc_body = ttk.Frame(sf)
        self._svc_body.pack(fill=X)
        for name, price in umrah.services_map(trip).items():
            self._add_service_row(name, f"{price:.0f}" if price else "")
        addrow = ttk.Frame(sf)
        addrow.pack(fill=X, pady=(6, 0))
        self._new_svc = StringVar()
        self._new_price = StringVar()
        ttk.Label(addrow, text=G.rtl("خدمة جديدة:"), font=(G._FUI, 9),
                  foreground=G.TEXT).pack(side=RIGHT)
        ttk.Entry(addrow, textvariable=self._new_svc, width=20,
                  justify="right").pack(side=RIGHT, padx=3)
        ttk.Entry(addrow, textvariable=self._new_price, width=8,
                  justify="center").pack(side=RIGHT, padx=3)
        ttk.Button(addrow, text=G.rtl("➕ أضِف"), style="Ghost.TButton",
                   command=self._add_custom_service).pack(side=RIGHT, padx=3)

        tr = ttk.Frame(f)
        tr.pack(fill=X, pady=(12, 0))
        ttk.Label(tr, text=G.rtl("النقل الداخلي:"), font=(G._FUI, 10),
                  foreground=G.TEXT).pack(side=RIGHT, padx=(8, 4))
        self.transport = StringVar(value=umrah.suggest_transport(1))
        ttk.Entry(tr, textvariable=self.transport, width=34,
                  justify="right").pack(side=RIGHT)
        ttk.Button(tr, text=G.rtl("↻ تلقائي"), style="Ghost.TButton",
                   command=self._auto_transport).pack(side=RIGHT, padx=(0, 6))
        self._transport_auto = True

        self.summary = ttk.Label(f, text="", font=(G._FSB, 12),
                                 foreground=G.BRONZE, background=G.BG)
        self.summary.pack(anchor="e", pady=(14, 2))
        self.counter = ttk.Label(f, text="", font=(G._FUI, 10),
                                 foreground=G.MUTED, background=G.BG)
        self.counter.pack(anchor="e")

        # إضافة كل شخص بقراءة الجواز أو يدوياً (يُطبَّق التسعير تلقائياً)
        btns = ttk.Frame(f)
        btns.pack(fill=X, pady=(12, 0))
        ttk.Button(btns, text=G.rtl("📷 إضافة بقراءة الجواز"),
                   style="Primary.TButton",
                   command=self.add_passport).pack(side=RIGHT, padx=3)
        ttk.Button(btns, text=G.rtl("➕ إضافة يدوي"), style="Act.TButton",
                   command=self.add_manual).pack(side=RIGHT, padx=3)
        ttk.Button(btns, text="إنهاء", style="Ghost.TButton",
                   command=self.destroy).pack(side=LEFT, padx=3)
        self._recalc()
        _center(self, window)

    # ---- الحساب ----
    def _persons_n(self) -> int:
        try:
            return max(1, int(float(self.persons.get() or 1)))
        except ValueError:
            return 1

    def _add_service_row(self, name: str, price: str = "",
                         checked: bool = False) -> None:
        """يضيف صفّ خدمة (اسم + مربّع اختيار + سعر قابل للتعديل)."""
        row = ttk.Frame(self._svc_body)
        row.pack(fill=X, pady=1)
        on = BooleanVar(value=checked)
        pv = StringVar(value=str(price or ""))
        ttk.Checkbutton(row, variable=on, text=G.rtl(name),
                        command=self._recalc).pack(side=RIGHT)
        ttk.Label(row, text="درهم", font=(G._FUI, 8),
                  foreground=G.MUTED).pack(side=RIGHT, padx=(2, 8))
        ttk.Entry(row, textvariable=pv, width=8,
                  justify="center").pack(side=RIGHT, padx=3)
        pv.trace_add("write", lambda *_a: self._recalc())
        self.svc_rows.append({"name": name, "on": on, "price": pv})

    def _add_custom_service(self) -> None:
        name = self._new_svc.get().strip()
        if not name:
            return
        self._add_service_row(name, self._new_price.get().strip(), checked=True)
        self._new_svc.set("")
        self._new_price.set("")
        self._recalc()

    def _chosen_priced(self) -> list:
        """الخدمات المختارة بأسعارها المُدخَلة يدوياً."""
        return [{"name": r["name"],
                 "price": f"{parse_amount(r['price'].get()) or 0:.0f}"}
                for r in self.svc_rows if r["on"].get()]

    def _services_total(self) -> float:
        return sum(parse_amount(r["price"].get()) or 0
                   for r in self.svc_rows if r["on"].get())

    def _auto_transport(self) -> None:
        self.transport.set(umrah.suggest_transport(self._persons_n()))
        self._transport_auto = True

    def _per_person_price(self) -> float:
        key = self._room_by_name.get(self.room.get(), "price_double")
        return umrah.room_price(self.trip, key) + self._services_total()

    def _recalc(self) -> None:
        n = self._persons_n()
        if getattr(self, "_transport_auto", True):
            self.transport.set(umrah.suggest_transport(n))
        per = self._per_person_price()
        self._per_person = per
        self.summary.configure(text=(
            f"سعر الفرد: {format_amount(per)}   ·   "
            f"الإجمالي ({n}): {format_amount(per * n)}"))
        self.counter.configure(
            text=f"أُضيف في هذا الحجز: {self._added} من {n}")

    def _apply_booking(self, rec) -> None:
        """يطبّق إعدادات الحجز (السفر/الإقامة من البرنامج + الغرفة/النقل/السعر)."""
        self.window._enrich(rec)               # سفر/إقامة من البرنامج + رقم مرجعي
        key = self._room_by_name.get(self.room.get(), "price_double")
        base = umrah.room_price(self.trip, key)
        chosen = self._chosen_priced()
        rec.room_type = self.room.get()
        rec.transport = self.transport.get().strip()
        rec.room_value = f"{base:.0f}"
        rec.umrah_services = chosen
        total = base + sum(parse_amount(s["price"]) or 0 for s in chosen)
        rec.program_value = f"{total:.0f}"

    def _commit_person(self, rec) -> None:
        """يضيف المعتمر للبرنامج ويحفظ ويحدّث العدّادات والجدول."""
        if rec not in self.app.records:
            self.app.records.append(rec)
        self.app.save()
        self._added += 1
        self.window._reload()
        self._recalc()

    # ---- الإضافة يدوياً ----
    def add_manual(self) -> None:
        if not self.window._check_capacity(1):
            return
        rec = PassportData()
        self._apply_booking(rec)               # يُعبّئ السعر/الغرفة/النقل مسبقاً
        self.grab_release()                    # نسلّم القبض لنافذة التعديل

        def on_save(r):
            r.trip = self.trip.code            # نحفظ ما عدّله المستخدم كما هو
            self._commit_person(r)

        ed = G.EditDialog(self, rec, on_save, title="إضافة معتمر (حجز)",
                          save_text="إضافة", session=self.session, umrah=True,
                          trip=self.trip)
        # نستعيد القبض عند إغلاق نافذة التعديل نفسها (لا عناصرها الداخلية)
        ed.bind("<Destroy>",
                lambda e, w=ed: self._regrab() if e.widget is w else None)

    def _regrab(self) -> None:
        try:
            if self.winfo_exists():
                self.grab_set()
        except Exception:
            pass

    # ---- الإضافة بقراءة الجواز ----
    def add_passport(self) -> None:
        if not self.window._check_capacity(1):
            return
        if not configure_tesseract():
            messagebox.showerror(
                "Tesseract غير موجود",
                "برنامج Tesseract OCR غير مثبّت.\nثبّته ثم أعد المحاولة.",
                parent=self)
            return
        paths = filedialog.askopenfilenames(
            title="اختر صور أو ملفات PDF للجوازات", parent=self,
            filetypes=G.SCAN_TYPES)
        if not paths:
            return
        cap = self.window._capacity()
        self.configure(cursor="watch")
        self.update_idletasks()
        added, fails, full = 0, [], False
        for p in paths:
            if cap and len(self.window._pilgrims()) >= cap:
                full = True
                break
            try:
                if Path(p).suffix.lower() == ".pdf":
                    recs, _notes = extract_from_pdf(p)
                else:
                    recs = [extract_passport(p)]
            except Exception as exc:                       # noqa: BLE001
                fails.append(f"{Path(p).name}: {exc}")
                continue
            for rec in recs:
                if cap and len(self.window._pilgrims()) >= cap:
                    full = True
                    break
                self._apply_booking(rec)
                if len(recs) == 1:
                    self.window._attach_image(rec, p)
                self.app.records.append(rec)
                added += 1
                self._added += 1
        self.configure(cursor="")
        if added:
            self.app.save()
            self.window._reload()
            self._recalc()
        msg = f"أُضيف {added} معتمراً بسعر فرد {format_amount(self._per_person_price())}."
        if full:
            msg += f"\n\nتوقّفت الإضافة: اكتملت سعة البرنامج ({cap})."
        if fails:
            msg += "\n\nتعذّرت قراءة:\n- " + "\n- ".join(fails[:8])
        messagebox.showinfo("قراءة الجوازات", msg, parent=self)


class TripPilgrimsWindow(Toplevel):
    """قائمة معتمري برنامجٍ واحد: إضافة (جواز/يدوي/حجز)، تعديل، حذف، تصدير."""

    def __init__(self, app: UmrahApp, trip) -> None:
        super().__init__(app.root)
        self.app = app
        self.trip = trip
        self.session = app.session
        self.title(f"المعتمرين — {trip.name or trip.code}")
        self.configure(bg=G.BG)
        self.geometry("1320x760")
        self.minsize(960, 560)
        self.transient(app.root)

        head = ttk.Frame(self, style="Toolbar.TFrame", padding=(14, 10, 14, 4))
        head.pack(fill=X)
        ttk.Label(head, text=f"👤 المعتمرين — «{trip.name or trip.code}»",
                  font=(G._FSB, 15), foreground=G.TEXT,
                  background=G.BG).pack(side=RIGHT)
        self.fin = ttk.Label(head, text="", font=(G._FUI, 10),
                             foreground=G.BRONZE, background=G.BG)
        self.fin.pack(side=LEFT)

        bar = ttk.Frame(self, style="Panel.TFrame", padding=(14, 8, 14, 10))
        bar.pack(fill=X)
        # الكشوف والمستندات على مستوى البرنامج نُقلت إلى الواجهة الرئيسية؛
        # هنا تبقى إجراءات المعتمرين والمستندات ذات المحرّر (لكل معتمر محدَّد).
        for text, cmd, kind in (
            ("📷  إضافة بقراءة الجواز", self.add_passport, "primary"),
            ("🧮  إضافة حجز (تسعير)", self.add_booking, "act"),
            ("➕  إضافة يدوي", self.add_manual, "ghost"),
            ("✏️  تعديل", self.edit_selected, "ghost"),
            ("🗑  حذف", self.delete_selected, "ghost"),
        ):
            _cbtn(bar, text, cmd, kind).pack(side=RIGHT, padx=3)
        for text, cmd in (("📋  عروض الأسعار", self.do_quotes_list),
                          ("🏨  فاوتشر الفندق", self.do_voucher),
                          ("🚖  طلب مواصلات", self.do_transport_request)):
            _cbtn(bar, text, cmd).pack(side=LEFT, padx=3)
        _cbtn(bar, "👁  معاينة PDF", self.export_pdf).pack(side=LEFT, padx=3)
        _cbtn(bar, "📊  تصدير إكسل", self.export_excel).pack(side=LEFT, padx=3)

        wrap = ttk.Frame(self, style="Toolbar.TFrame", padding=(14, 4, 14, 12))
        wrap.pack(fill=BOTH, expand=True)
        cols = ("n", "name", "passport", "room", "phone", "status", "remaining")
        heads = {"n": "م", "name": "اسم المعتمر", "passport": "رقم الجواز",
                 "room": "الغرفة", "phone": "الهاتف", "status": "الحالة",
                 "remaining": "المتبقّي"}
        widths = {"n": 44, "name": 250, "passport": 120, "room": 90, "phone": 130,
                  "status": 90, "remaining": 110}
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings")
        for c in cols:
            self.tree.heading(c, text=heads[c])
            self.tree.column(c, width=widths[c],
                             anchor="e" if c == "name" else "center")
        vs = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        vs.pack(side=RIGHT, fill="y")
        self.tree.tag_configure("odd", background=G.PANEL)
        self.tree.tag_configure("expire", background="#F6D9D0")   # جواز قارب الانتهاء
        self.tree.bind("<Double-1>", lambda _e: self.edit_selected())

        self.grab_set()
        G.enable_minmax(self)
        self._reload()

    def _pilgrims(self) -> list:
        return umrah.trip_pilgrims(self.app.records, self.trip.code)

    def _capacity(self) -> int:
        try:
            return int(float(str(self.trip.capacity or "").strip() or 0))
        except ValueError:
            return 0

    def _seats_left(self) -> int:
        cap = self._capacity()
        return max(0, cap - len(self._pilgrims())) if cap else 0

    def _check_capacity(self, adding: int = 1) -> bool:
        """يمنع تجاوز السعة المحدّدة للبرنامج."""
        cap = self._capacity()
        if cap and len(self._pilgrims()) + adding > cap:
            messagebox.showwarning(
                "السعة مكتملة",
                f"سعة البرنامج {cap} مقعداً، والمتبقّي {self._seats_left()}.\n"
                "لا يمكن إضافة أكثر من السعة المحدّدة.", parent=self)
            return False
        return True

    def _enrich(self, rec) -> None:
        """يأخذ السفر والإقامة من البرنامج ويبني الرقم المرجعي تلقائياً."""
        umrah.apply_trip_to_record(self.trip, rec)
        rec.trip = self.trip.code
        if not str(rec.reference_number or "").strip():
            rec.reference_number = umrah.next_reference(self.trip, self.app.records)

    def _reload(self) -> None:
        self.tree.delete(*self.tree.get_children())
        recs = self._pilgrims()
        total = paid = 0.0
        expiring = 0
        depart = str(getattr(self.trip, "depart_date", "") or "")
        for i, r in enumerate(recs):
            val = parse_amount(r.program_value) or 0.0
            pd = parse_amount(r.paid_amount) or 0.0
            total += val
            paid += pd
            name = r.full_name_ar or r.full_name_en or "—"
            tags = ["odd"] if i % 2 else []
            if umrah.passport_expiry_soon(r, depart):   # جواز ينتهي قبل ٦ أشهر
                tags.append("expire")
                expiring += 1
            self.tree.insert("", END, iid=str(i), values=(
                i + 1, name, r.passport_number or "—", r.room_type or "—",
                r.phone or "—", r.status or "نشط",
                format_amount(val - pd) if val else "—"),
                tags=tuple(tags))
        text = (f"العدد: {len(recs)}   ·   الإجمالي: {format_amount(total)}   ·   "
                f"المحصّل: {format_amount(paid)}   ·   "
                f"المتبقّي: {format_amount(total - paid)}")
        cap = self._capacity()
        if cap:
            text += f"   ·   🪑 المقاعد المتبقّية: {self._seats_left()} من {cap}"
        if expiring:
            text += f"   ·   ⚠ جوازات تنتهي/قاربت: {expiring}"
        if cap and len(recs) > cap:
            text += f"   ·   ⛔ تجاوز سعة الطيران ({cap})"
        for label, used, avail in self._rooms_over():
            text += f"   ·   ⛔ تجاوز غرف {label} ({used}/{avail})"
        self.fin.configure(text=text)
        self.app._reload()

    def _rooms_over(self) -> list:
        """المدن التي تجاوز فيها التوزيع عدد الغرف المتاحة (label, used, avail)."""
        over = []
        recs = self._pilgrims()
        for _k, label, room_field, _hf, _nf, rooms_field in umrah.CITIES:
            try:
                avail = int(float(str(getattr(self.trip, rooms_field, "") or "")
                                  .strip() or 0))
            except ValueError:
                avail = 0
            if not avail:
                continue
            used = len({str(getattr(r, room_field, "") or "").strip()
                        for r in recs
                        if str(getattr(r, room_field, "") or "").strip()})
            if used > avail:
                over.append((label, used, avail))
        return over

    def _selected(self):
        sel = self.tree.selection()
        if not sel:
            return None
        recs = self._pilgrims()
        idx = int(sel[0])
        return recs[idx] if 0 <= idx < len(recs) else None

    # ---- الإضافة ----
    def add_manual(self) -> None:
        if not self._check_capacity(1):
            return
        rec = PassportData()
        self._enrich(rec)                      # سفر/إقامة من البرنامج + رقم مرجعي

        def on_save(r):
            r.trip = self.trip.code
            if r not in self.app.records:
                self.app.records.append(r)
            self.app.save()
            self._reload()

        G.EditDialog(self, rec, on_save, title="إضافة معتمر",
                     save_text="إضافة", session=self.session, umrah=True,
                     trip=self.trip)

    def add_booking(self) -> None:
        BookingDialog(self, self.trip)

    def open_rooming(self) -> None:
        if not self._pilgrims():
            messagebox.showinfo("التسكين", "لا معتمرين في هذا البرنامج.", parent=self)
            return
        RoomingWindow(self.app, self.trip)

    def open_transport(self) -> None:
        if not self._pilgrims():
            messagebox.showinfo("المواصلات", "لا معتمرين في هذا البرنامج.",
                                parent=self)
            return
        TransportWindow(self.app, self.trip)

    def open_flights(self) -> None:
        """معاينة كشف الطيران (مانيفست) لمعتمري البرنامج."""
        recs = self._pilgrims()
        if not recs:
            messagebox.showinfo("الطيران", "لا معتمرين في هذا البرنامج.", parent=self)
            return
        title = f"Flight Manifest — {self.trip.code}"
        G.open_preview(self, lambda p: export_airline_pdf(recs, p, title=title),
                       f"طيران {self.trip.code}", "pdf")

    def add_passport(self) -> None:
        if not self._check_capacity(1):
            return
        if not configure_tesseract():
            messagebox.showerror(
                "Tesseract غير موجود",
                "برنامج Tesseract OCR غير مثبّت.\nثبّته ثم أعد المحاولة.",
                parent=self)
            return
        paths = filedialog.askopenfilenames(
            title="اختر صور أو ملفات PDF للجوازات", parent=self,
            filetypes=G.SCAN_TYPES)
        if not paths:
            return
        cap = self._capacity()
        self.configure(cursor="watch")
        self.update_idletasks()
        added, fails, full = 0, [], False
        for p in paths:
            if cap and len(self._pilgrims()) >= cap:
                full = True
                break
            try:
                if Path(p).suffix.lower() == ".pdf":
                    recs, _notes = extract_from_pdf(p)
                else:
                    recs = [extract_passport(p)]
            except (MRZError, PDFError) as exc:
                fails.append(f"{Path(p).name}: {exc}")
                continue
            except Exception as exc:                       # noqa: BLE001
                fails.append(f"{Path(p).name}: {exc}")
                continue
            for rec in recs:
                if cap and len(self._pilgrims()) >= cap:
                    full = True
                    break
                self._enrich(rec)
                if len(recs) == 1:
                    self._attach_image(rec, p)
                self.app.records.append(rec)
                added += 1
        self.configure(cursor="")
        if added:
            self.app.save()
            self._reload()
        msg = f"أُضيف {added} معتمراً."
        if full:
            msg += f"\n\nتوقّفت الإضافة: اكتملت سعة البرنامج ({cap})."
        if fails:
            msg += "\n\nتعذّرت قراءة:\n- " + "\n- ".join(fails[:8])
        messagebox.showinfo("قراءة الجوازات", msg, parent=self)

    def _attach_image(self, rec, source) -> None:
        try:
            if not rec.image_id:
                rec.image_id = imgmod.new_image_id()
            imgmod.save_image(rec.image_id, imgmod.PASSPORT, source, self.session)
        except Exception:
            pass

    # ---- التعديل والحذف ----
    def edit_selected(self) -> None:
        rec = self._selected()
        if rec is None:
            messagebox.showinfo("تعديل", "اختر معتمراً أولاً.", parent=self)
            return

        def on_save(_r):
            rec.trip = self.trip.code
            self.app.save()
            self._reload()

        G.EditDialog(self, rec, on_save, title="تعديل بيانات المعتمر",
                     session=self.session, umrah=True, trip=self.trip)

    def delete_selected(self) -> None:
        rec = self._selected()
        if rec is None:
            messagebox.showinfo("حذف", "اختر معتمراً أولاً.", parent=self)
            return
        name = rec.full_name_ar or rec.full_name_en or rec.passport_number or "—"
        if not messagebox.askyesno("حذف معتمر", f"حذف «{name}»؟", parent=self):
            return
        try:
            self.app.records.remove(rec)
        except ValueError:
            return
        self.app.save()
        self._reload()

    # ---- التصدير ----
    def _prog_label(self) -> str:
        """اسم البرنامج مع رمزه للكشف (يُذكر رمز البرنامج)."""
        return (f"{self.trip.code} — {self.trip.name}"
                if self.trip.name else self.trip.code)

    def export_excel(self) -> None:
        recs = self._pilgrims()
        if not recs:
            messagebox.showinfo("تصدير", "لا معتمرين في هذا البرنامج.", parent=self)
            return
        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=".xlsx",
            initialfile=f"معتمرو {self.trip.code}.xlsx",
            filetypes=[("إكسل", "*.xlsx")])
        if not path:
            return
        try:
            export_umrah_excel(recs, path, program_name=self._prog_label())
        except Exception as exc:                           # noqa: BLE001
            messagebox.showerror("تعذّر التصدير", str(exc), parent=self)
            return
        messagebox.showinfo("تم", f"حُفظ الملف:\n{path}", parent=self)

    def export_pdf(self) -> None:
        """معاينة PDF لكشف معتمري البرنامج (طباعة أو حفظ من العارض)."""
        recs = self._pilgrims()
        if not recs:
            messagebox.showinfo("معاينة", "لا معتمرين في هذا البرنامج.", parent=self)
            return
        dep = str(getattr(self.trip, "depart_date", "") or "")
        G.open_preview(
            self, lambda p: export_umrah_pdf(recs, p, program_name=self._prog_label(),
                                             depart_date=dep),
            f"معتمرو {self.trip.code}", "pdf")

    def do_finance(self) -> None:
        """يفتح نافذة الإدارة المالية للبرنامج (قيم/محصّل/متبقّي + دفعات + ملخّص)."""
        recs = self._pilgrims()
        if not recs:
            messagebox.showinfo("الإدارة المالية", "لا معتمرين في هذا البرنامج.",
                                parent=self)
            return
        UmrahFinanceWindow(self, self.app, self.trip, on_change=self._reload)

    def do_cards(self) -> None:
        """معاينة بطاقات العمرة (بطاقة لكل معتمر)."""
        recs = self._pilgrims()
        if not recs:
            messagebox.showinfo("بطاقات العمرة", "لا معتمرين في هذا البرنامج.",
                                parent=self)
            return
        company = self._company()
        G.open_preview(
            self,
            lambda p: export_umrah_cards_pdf(
                recs, p, program_name=self._prog_label(), company=company,
                session=self.session,
                emergency_uae=str(getattr(self.trip, "emergency_uae", "") or ""),
                emergency_ksa=str(getattr(self.trip, "emergency_ksa", "") or "")),
            f"بطاقات {self.trip.code}", "pdf")

    def _company(self):
        co = self.app._settings.get("company")
        return co if isinstance(co, dict) else None

    def _doc_for_selected(self, export_fn, base) -> None:
        """يعاين مستند العمرة (سند/فاتورة/عقد) للمعتمر المحدّد."""
        rec = self._selected()
        if rec is None:
            messagebox.showinfo("مستند", "اختر معتمراً أولاً.", parent=self)
            return
        company = self._company()
        prog = self.trip.name or self.trip.code
        G.open_preview(
            self, lambda p: export_fn(rec, p, program_name=prog, company=company),
            f"{base} {self.trip.code}", "pdf")

    def do_receipt(self) -> None:
        """معاينة سند قبض العمرة للمعتمر المحدّد."""
        self._doc_for_selected(export_umrah_receipt_pdf, "سند")

    def do_invoice(self) -> None:
        """معاينة فاتورة العمرة للمعتمر المحدّد."""
        self._doc_for_selected(export_umrah_invoice_pdf, "فاتورة")

    def do_contract(self) -> None:
        """معاينة عقد خدمات العمرة للمعتمر المحدّد."""
        self._doc_for_selected(export_umrah_contract_pdf, "عقد")

    def do_voucher(self) -> None:
        """فتح محرّر فاوتشر الفندق للمعتمر المحدّد (تعديل/إضافة/حذف الخلايا
        قبل المعاينة)."""
        rec = self._selected()
        if rec is None:
            messagebox.showinfo("فاوتشر", "اختر معتمراً أولاً.", parent=self)
            return
        prog = self.trip.name or self.trip.code
        number = umrah.next_voucher_number(self.app._settings)
        try:
            save_settings(self.app._settings)
        except OSError:
            pass
        company = self._company()
        data = build_voucher_data(rec, trip=self.trip, program_name=prog,
                                  company=company, number=number)
        VoucherEditorDialog(self, rec, self.trip, data, program=prog,
                            company=company, app=self.app)

    def do_transport_request(self) -> None:
        """فتح محرّر طلب حجز المواصلات (خطاب لشركة النقل) للمعتمر المحدّد."""
        rec = self._selected()
        if rec is None:
            messagebox.showinfo("طلب مواصلات", "اختر معتمراً أولاً.", parent=self)
            return
        prog = self.trip.name or self.trip.code
        number = umrah.next_transport_number(self.app._settings)
        try:
            save_settings(self.app._settings)
        except OSError:
            pass
        company = self._company()
        data = build_transport_request_data(rec, trip=self.trip,
                                            program_name=prog, company=company,
                                            number=number)
        TransportRequestEditorDialog(self, rec, self.trip, data, company=company,
                                     app=self.app)

    def do_quotation(self) -> None:
        """فتح محرّر عرض السعر للبرنامج (يأخذ نوع غرفة المعتمر المحدّد إن وُجد)."""
        rec = self._selected() or PassportData()
        number = umrah.next_quote_number(self.app._settings)
        try:
            save_settings(self.app._settings)
        except OSError:
            pass
        company = self._company()
        data = build_quotation_data(rec, trip=self.trip, company=company,
                                    number=number)
        QuotationEditorDialog(self, rec, self.trip, data, app=self.app,
                              company=company)

    def do_quotes_list(self) -> None:
        """فتح قائمة «عروض الأسعار» المحفوظة لهذا البرنامج."""
        QuotesListWindow(self, self.app, self.trip)


class UmrahFinanceWindow(Toplevel):
    """الإدارة المالية لبرنامج عمرة: قيمة كل معتمر والمحصّل والمتبقّي وحالته،
    مع تسجيل الدفعات (الأقساط) لكل معتمر، سند قبض، ومعاينة الملخّص المالي."""

    _CARDS = (("value", "إجمالي القيمة"), ("paid", "المحصّل"),
              ("remaining", "المتبقّي"), ("pct", "نسبة التحصيل"),
              ("owe", "متأخّرون"))

    def __init__(self, parent, app, trip, on_change=None) -> None:
        super().__init__(parent)
        self.app = app
        self.trip = trip
        self.session = app.session
        self._on_change = on_change
        self.title(f"💰 الإدارة المالية — {trip.name or trip.code}")
        self.configure(bg=G.BG)
        self.geometry("1080x680")
        self.minsize(840, 520)
        self.transient(parent)

        head = ttk.Frame(self, style="Toolbar.TFrame", padding=(16, 12, 16, 4))
        head.pack(fill=X)
        ttk.Label(head, text=f"💰 الإدارة المالية — «{trip.name or trip.code}»",
                  font=(G._FSB, 15), foreground=G.TEXT,
                  background=G.BG).pack(side=RIGHT)

        # بطاقات الملخّص المالي
        cards = ttk.Frame(self, style="Panel.TFrame", padding=(16, 10))
        cards.pack(fill=X)
        self._card_vars: dict[str, StringVar] = {}
        for key, label in self._CARDS:
            box = ttk.Frame(cards, style="Panel.TFrame")
            box.pack(side=RIGHT, expand=True, fill=X, padx=4)
            v = StringVar(value="—")
            self._card_vars[key] = v
            ttk.Label(box, textvariable=v, font=(G._FSB, 16), foreground=G.ACCENT,
                      background=G.BG).pack()
            ttk.Label(box, text=label, font=(G._FUI, 9), foreground=G.MUTED,
                      background=G.BG).pack()

        bar = ttk.Frame(self, style="Panel.TFrame", padding=(16, 6, 16, 10))
        bar.pack(fill=X)
        ttk.Button(bar, text=G.rtl("💵  دفعات المعتمر"), style="Primary.TButton",
                   command=self.open_payments).pack(side=RIGHT, padx=3)
        ttk.Button(bar, text=G.rtl("🧾  سند قبض"), style="Act.TButton",
                   command=self.do_receipt).pack(side=RIGHT, padx=3)
        ttk.Button(bar, text=G.rtl("👁  معاينة الملخّص PDF"), style="Ghost.TButton",
                   command=self.preview_pdf).pack(side=LEFT, padx=3)
        ttk.Button(bar, text="إغلاق", style="Ghost.TButton",
                   command=self.destroy).pack(side=LEFT, padx=3)

        wrap = ttk.Frame(self, style="Toolbar.TFrame", padding=(16, 4, 16, 14))
        wrap.pack(fill=BOTH, expand=True)
        cols = ("n", "name", "room", "value", "paid", "remaining", "status",
                "method")
        heads = {"n": "م", "name": "اسم المعتمر", "room": "الغرفة",
                 "value": "القيمة", "paid": "المحصّل", "remaining": "المتبقّي",
                 "status": "الحالة", "method": "آخر طريقة دفع"}
        widths = {"n": 44, "name": 240, "room": 90, "value": 110, "paid": 110,
                  "remaining": 110, "status": 100, "method": 120}
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings",
                                 selectmode="browse")
        for c in cols:
            self.tree.heading(c, text=heads[c])
            self.tree.column(c, width=widths[c],
                             anchor="e" if c == "name" else "center")
        vs = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        vs.pack(side=RIGHT, fill="y")
        self.tree.tag_configure("paid", background="#E6F1E9")       # مسدّد — أخضر
        self.tree.tag_configure("partial", background="#FBF0DC")    # جزئي — كهرماني
        self.tree.tag_configure("unpaid", background="#F6D9D0")     # غير مدفوع — أحمر
        self.tree.bind("<Double-1>", lambda _e: self.open_payments())

        self.grab_set()
        try:
            G.enable_minmax(self)
        except Exception:
            pass
        self._reload()

    def _pilgrims(self) -> list:
        return umrah.trip_pilgrims(self.app.records, self.trip.code)

    def _prog_label(self) -> str:
        return (f"{self.trip.code} — {self.trip.name}"
                if self.trip.name else self.trip.code)

    def _reload(self) -> None:
        self.tree.delete(*self.tree.get_children())
        recs = self._pilgrims()
        total = paid = 0.0
        owe = 0
        for i, r in enumerate(recs):
            v = parse_amount(r.program_value) or 0.0
            p = parse_amount(r.paid_amount) or 0.0
            rem = v - p
            total += v
            paid += p
            if rem > 0.005 and p > 0.005:
                status, tag = "جزئي", "partial"
                owe += 1
            elif rem > 0.005:
                status, tag = "غير مدفوع", "unpaid"
                owe += 1
            else:
                status, tag = "مسدّد", "paid"
            name = r.full_name_ar or r.full_name_en or "—"
            method = str(getattr(r, "payment_method", "") or "—")
            self.tree.insert("", END, iid=str(i), values=(
                i + 1, name, r.room_type or "—", format_amount(v),
                format_amount(p), format_amount(rem), status, method),
                tags=(tag,))
        pct = f"{(paid / total * 100):.0f}%" if total else "0%"
        self._card_vars["value"].set(format_amount(total) or "0")
        self._card_vars["paid"].set(format_amount(paid) or "0")
        self._card_vars["remaining"].set(format_amount(total - paid) or "0")
        self._card_vars["pct"].set(pct)
        self._card_vars["owe"].set(str(owe))

    def _selected(self):
        sel = self.tree.selection()
        if not sel:
            return None
        recs = self._pilgrims()
        idx = int(sel[0])
        return recs[idx] if 0 <= idx < len(recs) else None

    def open_payments(self) -> None:
        """يفتح سجلّ الدفعات (الأقساط) للمعتمر المحدّد ويُزامن المالية."""
        rec = self._selected()
        if rec is None:
            messagebox.showinfo("الدفعات", "اختر معتمراً أولاً.", parent=self)
            return

        def on_change():
            # مزامنة آخر طريقة/تاريخ دفع من سجلّ الأقساط لعرضٍ وملخّصٍ متّسق
            pays = getattr(rec, "payments", None) or []
            if pays:
                last = pays[-1]
                rec.payment_method = str(last.get("method", "") or "")
                rec.payment_date = str(last.get("date", "") or "")
            self.app.save()
            self._reload()
            if callable(self._on_change):
                self._on_change()

        G.PaymentsDialog(self, rec, on_change)

    def do_receipt(self) -> None:
        """معاينة سند قبض للمعتمر المحدّد (بقيمة المحصّل الحالية)."""
        rec = self._selected()
        if rec is None:
            messagebox.showinfo("سند قبض", "اختر معتمراً أولاً.", parent=self)
            return
        co = self.app._settings.get("company")
        company = co if isinstance(co, dict) else None
        G.open_preview(
            self,
            lambda p: export_umrah_receipt_pdf(rec, p, company=company,
                                               program_name=self._prog_label()),
            f"سند {rec.reference_number or rec.passport_number or 'قبض'}", "pdf")

    def preview_pdf(self) -> None:
        """معاينة الملخّص المالي الكامل للبرنامج (PDF)."""
        recs = self._pilgrims()
        if not recs:
            messagebox.showinfo("الملخّص المالي", "لا معتمرين.", parent=self)
            return
        G.open_preview(
            self,
            lambda p: export_umrah_finance_pdf(recs, p,
                                               program_name=self._prog_label()),
            f"مالية {self.trip.code}", "pdf")


_MONTHS_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep",
              "Oct", "Nov", "Dec")


class _CalendarPopup(Toplevel):
    """تقويم منبثق لاختيار تاريخ (بأسلوب Material) — تنقّل بالشهر والسنة."""

    def __init__(self, picker) -> None:
        super().__init__(picker)
        self.picker = picker
        try:
            self.overrideredirect(True)
        except Exception:
            pass
        self.configure(bg=G.BG, bd=1, relief="solid")
        today = date.today()
        try:
            y, m, d = (int(x) for x in picker.get().split("-"))
        except Exception:
            y, m, d = today.year, today.month, today.day
        self._y, self._m, self._sel = y, m, d
        self._render()
        self.update_idletasks()
        x = picker.winfo_rootx()
        yy = picker.winfo_rooty() + picker.winfo_height()
        self.geometry(f"+{x}+{yy}")
        try:
            self.grab_set()
        except Exception:
            pass
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<FocusOut>", lambda e: self.after(120, self._maybe_close))

    def _maybe_close(self) -> None:
        try:
            if self.focus_get() is None:
                self.destroy()
        except Exception:
            pass

    def _render(self) -> None:
        for w in self.winfo_children():
            w.destroy()
        hdr = ttk.Frame(self, padding=4)
        hdr.pack(fill=X)
        ttk.Button(hdr, text="«", width=2, command=self._prev_year).pack(
            side=LEFT)
        ttk.Button(hdr, text="‹", width=2, command=self._prev).pack(side=LEFT)
        ttk.Label(hdr, text=f"{_MONTHS_EN[self._m - 1]} {self._y}",
                  font=(G._FUI, 10, "bold")).pack(side=LEFT, expand=True)
        ttk.Button(hdr, text="›", width=2, command=self._next).pack(side=LEFT)
        ttk.Button(hdr, text="»", width=2, command=self._next_year).pack(
            side=LEFT)
        ttk.Button(hdr, text="✕", width=2, command=self.destroy).pack(
            side=LEFT, padx=(4, 0))
        g = ttk.Frame(self, padding=(4, 0, 4, 4))
        g.pack()
        for i, wd in enumerate(("Su", "Mo", "Tu", "We", "Th", "Fr", "Sa")):
            ttk.Label(g, text=wd, width=3, anchor="center",
                      font=(G._FUI, 8, "bold")).grid(row=0, column=i, padx=1)
        weeks = _calmod.Calendar(firstweekday=6).monthdayscalendar(self._y,
                                                                   self._m)
        for r, week in enumerate(weeks, start=1):
            for c, day in enumerate(week):
                if day == 0:
                    continue
                ttk.Button(g, text=str(day), width=3,
                           command=lambda d=day: self._pick(d)).grid(
                    row=r, column=c, padx=1, pady=1)
        # صفّ أدوات: مسح التاريخ / اليوم / إغلاق
        foot = ttk.Frame(self, padding=(4, 0, 4, 4))
        foot.pack(fill=X)
        ttk.Button(foot, text="مسح", command=self._clear).pack(side=LEFT)
        ttk.Button(foot, text="اليوم", command=self._today).pack(side=LEFT,
                                                                 padx=3)
        ttk.Button(foot, text="إغلاق", command=self.destroy).pack(side=RIGHT)

    def _clear(self) -> None:
        self.picker.set("")
        self.destroy()

    def _today(self) -> None:
        t = date.today()
        self.picker.set(t.isoformat())
        self.destroy()

    def _prev(self) -> None:
        self._m -= 1
        if self._m < 1:
            self._m, self._y = 12, self._y - 1
        self._render()

    def _next(self) -> None:
        self._m += 1
        if self._m > 12:
            self._m, self._y = 1, self._y + 1
        self._render()

    def _prev_year(self) -> None:
        self._y -= 1
        self._render()

    def _next_year(self) -> None:
        self._y += 1
        self._render()

    def _pick(self, d) -> None:
        self.picker.set(f"{self._y:04d}-{self._m:02d}-{d:02d}")
        self.destroy()


class DatePicker(ttk.Frame):
    """حقل تاريخ يعرض DD/MM/YYYY ويفتح تقويماً منبثقاً عند الضغط على 📅."""

    def __init__(self, parent, iso="", width=12) -> None:
        super().__init__(parent)
        self._iso = str(iso or "")          # فارغ يبقى فارغاً
        self._disp = StringVar()
        self._refresh()
        ttk.Entry(self, textvariable=self._disp, width=width, state="readonly",
                  justify="center").pack(side=LEFT)
        ttk.Button(self, text="📅", width=3, command=self._open).pack(side=LEFT)

    def _refresh(self) -> None:
        try:
            y, m, d = self._iso.split("-")
            self._disp.set(f"{int(d):02d}/{int(m):02d}/{y}")
        except Exception:
            self._disp.set(self._iso)

    def set(self, iso) -> None:
        self._iso = str(iso or "")
        self._refresh()

    def get(self) -> str:
        return self._iso

    def _open(self) -> None:
        _CalendarPopup(self)


class _EditorMixin:
    """أدوات مشتركة لمحرّرات المستندات (فاوتشر/عرض سعر): حاوية قابلة للتمرير،
    نسخ/لصق يعمل مع اللوحة العربية، تقويم منبثق للتاريخ، وحذف الصفوف."""

    def _scroll_body(self):
        """ينشئ حاوية قابلة للتمرير ويضبط ``self.body``؛ يعيد إطار المحتوى."""
        outer = ttk.Frame(self, padding=(10, 10, 10, 4))
        outer.pack(fill=BOTH, expand=True)
        canvas = Canvas(outer, bg=G.BG, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        self.body = ttk.Frame(canvas, padding=2)
        self.body.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        win = canvas.create_window((0, 0), window=self.body, anchor="nw")
        canvas.bind(
            "<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side=LEFT, fill=BOTH, expand=True)
        sb.pack(side=RIGHT, fill=Y)
        canvas.bind_all(
            "<MouseWheel>",
            lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))
        return self.body

    def _section(self, title: str) -> ttk.LabelFrame:
        lf = ttk.LabelFrame(self.body, text=title, padding=8)
        lf.pack(fill=X, pady=(0, 8))
        return lf

    # ---- التاريخ (تقويم منبثق) ----
    def _build_date_picker(self, parent, iso, row, col, prefix="_d"):
        """يُنشئ حقل تاريخ بتقويم منبثق ويخزّنه في ``self.<prefix>``."""
        dp = DatePicker(parent, iso=iso)
        dp.grid(row=row, column=col, sticky="w", pady=3)
        setattr(self, prefix, dp)
        return dp

    def _del_row(self, store: list, entry) -> None:
        entry[0].destroy()
        if entry in store:
            store.remove(entry)

    # ---- النسخ واللصق (يعمل مع اللوحة العربية) ----
    def _attach_clipboard(self, widget) -> None:
        if widget.winfo_class() in ("TEntry", "Entry", "Text", "TCombobox"):
            widget.bind("<Button-3>", self._clip_menu)
            widget.bind("<Control-KeyPress>", self._clip_key)
        for child in widget.winfo_children():
            self._attach_clipboard(child)

    @staticmethod
    def _select_all(w) -> None:
        try:
            if w.winfo_class() == "Text":
                w.tag_add("sel", "1.0", "end-1c")
            else:
                w.select_range(0, "end")
                w.icursor("end")
        except Exception:
            pass

    def _clip_key(self, event):
        w = event.widget
        actions = {67: "<<Copy>>", 86: "<<Paste>>", 88: "<<Cut>>"}
        if event.keycode in actions:
            w.event_generate(actions[event.keycode])
            return "break"
        if event.keycode == 65:
            self._select_all(w)
            return "break"
        return None

    def _clip_menu(self, event) -> None:
        w = event.widget
        try:
            w.focus_set()
        except Exception:
            pass
        m = Menu(self, tearoff=0)
        m.add_command(label="قص", command=lambda: w.event_generate("<<Cut>>"))
        m.add_command(label="نسخ", command=lambda: w.event_generate("<<Copy>>"))
        m.add_command(label="لصق", command=lambda: w.event_generate("<<Paste>>"))
        m.add_separator()
        m.add_command(label="تحديد الكل", command=lambda: self._select_all(w))
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    # ---- خلايا الصفوف (قائمة منسدلة / تاريخ) ----
    def _cell(self, parent, label, value, options, width, readonly=True):
        """خلية بعنوان صغير فوق قائمة منسدلة، ضمن صفّ أفقي."""
        sub = ttk.Frame(parent)
        sub.pack(side=RIGHT, padx=2)
        ttk.Label(sub, text=label, font=(G._FUI, 7)).pack()
        var = StringVar(value=str(value or ""))
        ttk.Combobox(sub, textvariable=var, values=list(options), width=width,
                     state="readonly" if readonly else "normal").pack()
        return var

    def _date_cell(self, parent, label, iso, width=9):
        """خلية تاريخ بتقويم منبثق (مع كتابة يدوية)، بعنوان صغير، ضمن صفّ أفقي."""
        sub = ttk.Frame(parent)
        sub.pack(side=RIGHT, padx=2)
        ttk.Label(sub, text=label, font=(G._FUI, 7)).pack()
        dp = DatePicker(sub, iso=iso, width=width)
        dp.pack()
        return dp

    # ---- قراءة رحلات أماديوس (صورة/حافظة/لقطة/سحب وإفلات) ----
    #  يتطلّب المحرِّر أن يوفّر ``self._flight_rows`` و``self._add_flight_row``
    #  بمخطّط الصف [التاريخ، الناقل، الإقلاع، من، الوصول، إلى].
    def _enable_drop(self, widget):
        """يفعّل السحب والإفلات على ``widget`` عبر tkdnd (مستقرّ مع Tkinter)."""
        try:
            from tkinterdnd2 import DND_FILES, TkinterDnD
            TkinterDnD._require(widget)
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._on_drop_amadeus)
            return True
        except Exception:
            return False

    def _on_drop_amadeus(self, event):
        try:
            paths = list(self.tk.splitlist(event.data))
        except Exception:
            paths = [event.data]
        paths = [p for p in paths if str(p).strip()]
        if not paths:
            return
        self.after(50, lambda: self._apply_amadeus(paths[0]))

    def _amadeus_year(self):
        for src in (getattr(self, "_pf", None), getattr(self, "_d", None)):
            v = src.get() if src is not None and hasattr(src, "get") else None
            if v and "-" in str(v):
                try:
                    return int(str(v).split("-")[0])
                except ValueError:
                    pass
        return None

    def _apply_amadeus(self, image_path):
        """يشغّل OCR على الصورة ويملأ جدول الطيران بالرحلات المقروءة."""
        try:
            from .ocr import read_amadeus_text
            text = read_amadeus_text(image_path)
        except Exception as exc:
            messagebox.showerror("قراءة أماديوس", str(exc), parent=self)
            return
        rows = umrah.parse_amadeus_flights(text, year=self._amadeus_year())
        if not rows:
            messagebox.showinfo(
                "قراءة أماديوس",
                "تعذّر التعرّف على رحلات في الصورة. تأكّد من وضوح اللقطة "
                "وأنّ أسطر الرحلات ظاهرة كاملةً.", parent=self)
            return
        for entry in list(self._flight_rows):
            entry[0].destroy()
        self._flight_rows.clear()
        for r in rows:
            self._add_flight_row(r)
        messagebox.showinfo("قراءة أماديوس", f"تمّت قراءة {len(rows)} رحلة.",
                            parent=self)

    def _amadeus_file(self):
        path = filedialog.askopenfilename(
            parent=self, title="صورة حجز أماديوس",
            filetypes=[("صور", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff"),
                       ("كل الملفّات", "*.*")])
        if path:
            self._apply_amadeus(path)

    def _save_temp_image(self, img):
        import os
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        img.save(path)
        return path

    def _amadeus_clipboard(self):
        """يقرأ صورة أماديوس ملصوقة في الحافظة (بعد Win+Shift+S مثلاً)."""
        try:
            from PIL import Image, ImageGrab
            grabbed = ImageGrab.grabclipboard()
        except Exception as exc:
            messagebox.showerror("قراءة أماديوس",
                                 f"تعذّر قراءة الحافظة: {exc}", parent=self)
            return
        img = None
        if isinstance(grabbed, list) and grabbed:
            img = Image.open(grabbed[0])
        elif grabbed is not None and hasattr(grabbed, "save"):
            img = grabbed
        if img is None:
            messagebox.showinfo(
                "قراءة أماديوس",
                "لا توجد صورة في الحافظة. التقط لقطة (Win+Shift+S) ثم أعد "
                "المحاولة.", parent=self)
            return
        self._apply_amadeus(self._save_temp_image(img))

    def _amadeus_screen(self):
        """يلتقط لقطة شاشة كاملة ويقرأ منها رحلات أماديوس."""
        try:
            from PIL import ImageGrab
        except Exception as exc:
            messagebox.showerror("قراءة أماديوس", str(exc), parent=self)
            return
        self.withdraw()
        self.after(400, lambda: self._grab_screen(ImageGrab))

    def _grab_screen(self, ImageGrab):
        try:
            img = ImageGrab.grab()
        except Exception as exc:
            self.deiconify()
            messagebox.showerror("قراءة أماديوس", str(exc), parent=self)
            return
        self.deiconify()
        self._apply_amadeus(self._save_temp_image(img))

    def _amadeus_bar(self, parent):
        """صفّ أزرار قراءة أماديوس + منطقة سحب وإفلات (يعيد إطار الأزرار)."""
        amz = ttk.Frame(parent)
        for text, cmd in (("📷 من صورة", self._amadeus_file),
                          ("📋 من الحافظة", self._amadeus_clipboard),
                          ("📸 لقطة شاشة", self._amadeus_screen)):
            ttk.Button(amz, text=text, command=cmd).pack(side=LEFT, padx=2)
        return amz


class VoucherEditorDialog(Toplevel, _EditorMixin):
    """محرّر فاوتشر الفندق: تعديل كل الخلايا، وإضافة/حذف صفوف الإقامات وجهات
    التواصل وبنود الشروط، قبل المعاينة."""

    def __init__(self, parent, rec, trip, data: dict, *, program: str = "",
                 company=None, app=None, on_saved=None) -> None:
        super().__init__(parent)
        self.parent = parent
        self.rec = rec
        self.trip = trip
        self._program = program
        self._company_dict = company
        self._app = app
        self._on_saved = on_saved
        self._lang = str(data.get("lang") or "ar")
        self.title("محرّر فاوتشر الفندق")
        self.configure(bg=G.BG)
        self.geometry("920x680")
        self.minsize(720, 480)
        self.transient(parent)

        # شريط اختيار اللغة (عربي/إنجليزي) أعلى النافذة
        top = ttk.Frame(self, padding=(12, 8, 12, 0))
        top.pack(fill=X)
        ttk.Label(top, text="لغة الفاوتشر:",
                  font=(G._FUI, 10, "bold")).pack(side=RIGHT, padx=(0, 6))
        self._lang_var = StringVar(
            value="English" if self._lang == "en" else "عربي")
        lang_cb = ttk.Combobox(top, textvariable=self._lang_var, width=10,
                               state="readonly", values=["عربي", "English"])
        lang_cb.pack(side=RIGHT)
        lang_cb.bind("<<ComboboxSelected>>", self._on_lang_change)

        self._scroll_body()

        self._meta: dict[str, StringVar] = {}
        self._stay_rows: list[list] = []
        self._transport_rows: list[list] = []
        self._contact_rows: list[list] = []
        # الشروط والأحكام والرقم ثابتة (غير قابلة للتعديل من المحرّر)
        self._terms = list(data.get("terms") or [])
        self._number = str(data.get("number") or "")

        self._build_meta(data)
        self._build_stays(data)
        self._build_transport(data)
        self._build_contacts(data)
        self._attach_clipboard(self.body)

        bar = ttk.Frame(self, padding=(10, 6))
        bar.pack(fill=X)
        ttk.Button(bar, text="🖨  معاينة PDF",
                   command=self._preview).pack(side=RIGHT)
        if self._app is not None:
            ttk.Button(bar, text="💾  حفظ الفاوتشر",
                       command=self._save).pack(side=RIGHT, padx=6)
        ttk.Button(bar, text="إغلاق",
                   command=self.destroy).pack(side=RIGHT, padx=6)

        try:
            G.enable_minmax(self)
        except Exception:
            pass
        self.grab_set()

    def _persist(self, data):
        """يخزّن الفاوتشر ضمن «الفاوتشرات المحفوظة» (يحدّث الموجود بنفس الرقم)."""
        if self._app is None:
            return
        umrah.save_voucher(self._app._settings, data)
        try:
            save_settings(self._app._settings)
        except OSError:
            pass
        if callable(self._on_saved):
            self._on_saved()

    def _save(self):
        if self._app is None:
            return
        self._persist(self._collect())
        messagebox.showinfo("الفاوتشرات",
                            f"تم حفظ الفاوتشر {self._number}.", parent=self)

    # ---- أقسام النموذج -------------------------------------------------
    def _on_lang_change(self, _event=None) -> None:
        """تبديل لغة الفاوتشر: يعيد بناء المحرّر بالقيَم الافتراضية للّغة
        الجديدة (المدن، الوجبات، الصفات، الشروط) مع الحفاظ على الرقم."""
        new = "en" if self._lang_var.get() == "English" else "ar"
        if new == self._lang:
            return
        data = build_voucher_data(self.rec, trip=self.trip,
                                  program_name=self._program,
                                  company=self._company_dict,
                                  number=self._number, lang=new)
        parent = self.parent
        rec, trip = self.rec, self.trip
        program, company = self._program, self._company_dict
        app, on_saved = self._app, self._on_saved
        self.destroy()
        VoucherEditorDialog(parent, rec, trip, data, program=program,
                            company=company, app=app, on_saved=on_saved)

    def _build_meta(self, data: dict) -> None:
        lf = self._section("البيانات الأساسية")
        # رقم الفاوتشر تسلسلي تلقائي (غير قابل للتعديل)
        ttk.Label(lf, text="رقم الفاوتشر").grid(row=0, column=0, sticky="e",
                                                padx=(8, 4), pady=3)
        ttk.Label(lf, text=self._number, foreground=G.ACCENT,
                  font=(G._FUI, 10, "bold")).grid(row=0, column=1,
                                                       sticky="w", pady=3)
        # التاريخ: يوم / شهر / سنة من قوائم منسدلة
        ttk.Label(lf, text="التاريخ").grid(row=0, column=2, sticky="e",
                                           padx=(8, 4), pady=3)
        self._build_date_picker(lf, data.get("date"), row=0, col=3)

        fields = [("اسم الضيف (عربي)", "guest_ar"),
                  ("اسم الضيف (إنجليزي)", "guest_en"),
                  ("رقم الحجز", "booking_no"), ("البرنامج", "program")]
        for i, (label, key) in enumerate(fields):
            r, c = divmod(i, 2)
            r += 1
            ttk.Label(lf, text=label).grid(row=r, column=c * 2, sticky="e",
                                           padx=(8, 4), pady=3)
            var = StringVar(value=str(data.get(key) or ""))
            self._meta[key] = var
            ttk.Entry(lf, textvariable=var, width=28, justify="right").grid(
                row=r, column=c * 2 + 1, sticky="we", padx=(0, 8), pady=3)
        lf.columnconfigure(1, weight=1)
        lf.columnconfigure(3, weight=1)

    def _build_stays(self, data: dict) -> None:
        lf = self._section("الإقامات (المدينة / الفندق / نوع الغرفة / عدد الغرف / "
                           "الإطلالة / الدخول / المغادرة / الليالي / الوجبات)")
        self._stay_head = lf
        # عرض كل عمود بالبكسل ليتناسب مع القوائم والتقويم المنبثق
        self._stay_widths = [13, 16, 11, 8, 10, 12, 12, 5, 11]
        hdr = ttk.Frame(lf)
        hdr.pack(fill=X)
        for w, h in zip(self._stay_widths, VOUCHER_STAY_HEADS):
            ttk.Label(hdr, text=h, width=w, anchor="center",
                      font=(G._FUI, 8, "bold")).pack(side=RIGHT, padx=1)
        ttk.Label(hdr, text="", width=5).pack(side=RIGHT)
        self._stay_box = ttk.Frame(lf)
        self._stay_box.pack(fill=X)
        for row in data.get("stays", []):
            self._add_stay_row(list(row))
        ttk.Button(lf, text="＋ إضافة صف",
                   command=lambda: self._add_stay_row()).pack(anchor="e",
                                                              pady=(4, 0))

    def _add_stay_row(self, values=None) -> None:
        # ترحيل الصفوف القديمة (٨ أعمدة) إلى ٩ بإدراج «عدد الغرف»
        values = normalize_voucher_stay(values)
        en = self._lang == "en"
        cities = VOUCHER_CITY_OPTIONS_EN if en else VOUCHER_CITY_OPTIONS
        room_types = VOUCHER_ROOM_TYPES_EN if en else VOUCHER_ROOM_TYPES
        fr = ttk.Frame(self._stay_box)
        fr.pack(fill=X, pady=1)
        cells = []
        w = self._stay_widths
        for i in range(9):
            if i == 0:          # المدينة → قائمة منسدلة (مكة/المدينة)
                var = StringVar(value=str(values[i] or ""))
                ttk.Combobox(fr, textvariable=var, width=w[i], justify="right",
                             values=list(cities)).pack(side=RIGHT, padx=1)
                cells.append(var)
            elif i == 2:        # نوع الغرفة → قائمة منسدلة
                var = StringVar(value=str(values[i] or ""))
                ttk.Combobox(fr, textvariable=var, width=w[i], justify="right",
                             values=list(room_types)).pack(side=RIGHT, padx=1)
                cells.append(var)
            elif i == 3:        # عدد الغرف → قائمة منسدلة قابلة للكتابة
                var = StringVar(value=str(values[i] or ""))
                ttk.Combobox(fr, textvariable=var, width=w[i], justify="center",
                             values=list(VOUCHER_ROOM_COUNTS)).pack(
                    side=RIGHT, padx=1)
                cells.append(var)
            elif i == 4:        # الإطلالة → قائمة منسدلة
                var = StringVar(value=str(values[i] or ""))
                ttk.Combobox(fr, textvariable=var, width=w[i] - 1,
                             state="readonly", justify="center",
                             values=list(VOUCHER_VIEW_OPTIONS)).pack(
                    side=RIGHT, padx=1)
                cells.append(var)
            elif i in (5, 6):   # الدخول/المغادرة → تقويم منبثق
                dp = DatePicker(fr, iso=str(values[i] or ""), width=w[i] - 3)
                dp.pack(side=RIGHT, padx=1)
                cells.append(dp)
            else:               # الفندق/الليالي/الوجبات → إدخال نصّي
                var = StringVar(value=str(values[i] or ""))
                ttk.Entry(fr, textvariable=var, width=w[i],
                          justify="right").pack(side=RIGHT, padx=1)
                cells.append(var)
        entry = [fr, cells]
        ttk.Button(fr, text="حذف", width=5,
                   command=lambda: self._del_row(self._stay_rows, entry)).pack(
            side=RIGHT, padx=(4, 1))
        self._stay_rows.append(entry)
        self._attach_clipboard(fr)

    def _build_transport(self, data: dict) -> None:
        lf = self._section("خطة النقل (نوع السيارة / الموديل / الوجهة)")
        hdr = ttk.Frame(lf)
        hdr.pack(fill=X)
        for w, h in zip((14, 9, 34), VOUCHER_TRANSPORT_HEADS):
            ttk.Label(hdr, text=h, width=w, anchor="center",
                      font=(G._FUI, 8, "bold")).pack(side=RIGHT, padx=1)
        ttk.Label(hdr, text="", width=5).pack(side=RIGHT)
        self._transport_box = ttk.Frame(lf)
        self._transport_box.pack(fill=X)
        for r in data.get("transport_rows", []):
            self._add_transport_row(list(r))
        ttk.Button(lf, text="＋ إضافة سيارة",
                   command=lambda: self._add_transport_row()).pack(
            anchor="e", pady=(4, 0))

        srow = ttk.Frame(lf)
        srow.pack(fill=X, pady=(6, 0))
        self._status = StringVar(value=str(data.get("status") or ""))
        ttk.Entry(srow, textvariable=self._status, justify="right").pack(
            side=RIGHT, fill=X, expand=True)
        ttk.Label(srow, text="حالة الحجز").pack(side=RIGHT, padx=(4, 6))

    def _add_transport_row(self, values=None) -> None:
        values = list(values or []) + ["", "", ""]
        fr = ttk.Frame(self._transport_box)
        fr.pack(fill=X, pady=1)
        cells = []
        # الوجهة (يدوي) على اليمين... لكن الترتيب البصري: نوع/موديل/وجهة
        v_car = StringVar(value=str(values[0] or ""))
        v_model = StringVar(value=str(values[1] or ""))
        v_dest = StringVar(value=str(values[2] or ""))
        # نوع السيارة: قائمة قابلة للإضافة يدوياً
        ttk.Combobox(fr, textvariable=v_car, width=13,
                     values=list(VOUCHER_CAR_TYPES)).pack(side=RIGHT, padx=1)
        # الموديل: قائمة من 2025 وما فوق
        ttk.Combobox(fr, textvariable=v_model, width=8, state="readonly",
                     values=[""] + voucher_car_models()).pack(side=RIGHT, padx=1)
        # الوجهة: يدوي
        ttk.Entry(fr, textvariable=v_dest, width=40, justify="right").pack(
            side=RIGHT, fill=X, expand=True, padx=1)
        cells = [v_car, v_model, v_dest]
        entry = [fr, cells]
        ttk.Button(fr, text="حذف", width=5,
                   command=lambda: self._del_row(self._transport_rows,
                                                 entry)).pack(side=RIGHT,
                                                              padx=(4, 1))
        self._transport_rows.append(entry)
        self._attach_clipboard(fr)

    def _build_contacts(self, data: dict) -> None:
        lf = self._section("جهات التواصل (الصفة / الاسم / الهاتف)")
        self._contact_box = ttk.Frame(lf)
        self._contact_box.pack(fill=X)
        for c in data.get("contacts", []):
            self._add_contact_row(list(c))
        ttk.Button(lf, text="＋ إضافة جهة",
                   command=lambda: self._add_contact_row()).pack(anchor="e",
                                                                 pady=(4, 0))

    def _add_contact_row(self, values=None) -> None:
        values = list(values or []) + ["", "", ""]
        fr = ttk.Frame(self._contact_box)
        fr.pack(fill=X, pady=1)
        cells = []
        for i, w in enumerate((16, 26, 18)):
            var = StringVar(value=str(values[i] or ""))
            ttk.Entry(fr, textvariable=var, width=w, justify="right").pack(
                side=RIGHT, padx=1)
            cells.append(var)
        entry = [fr, cells]
        ttk.Button(fr, text="حذف", width=5,
                   command=lambda: self._del_row(self._contact_rows,
                                                 entry)).pack(side=RIGHT,
                                                              padx=(4, 1))
        self._contact_rows.append(entry)
        self._attach_clipboard(fr)

    # ---- المعاينة ------------------------------------------------------
    def _iso_date(self) -> str:
        return self._d.get()

    def _collect(self) -> dict:
        data = {k: v.get().strip() for k, v in self._meta.items()}
        data["lang"] = self._lang
        data["number"] = self._number
        data["date"] = self._iso_date()
        data["terms"] = self._terms          # ثابتة (غير قابلة للتعديل)
        data["stays"] = [[c.get().strip() for c in cells]
                         for _fr, cells in self._stay_rows
                         if any(c.get().strip() for c in cells)]
        data["transport_rows"] = [[c.get().strip() for c in cells]
                                  for _fr, cells in self._transport_rows
                                  if any(c.get().strip() for c in cells)]
        data["status"] = self._status.get().strip()
        data["contacts"] = [[c.get().strip() for c in cells]
                            for _fr, cells in self._contact_rows
                            if any(c.get().strip() for c in cells)]
        return data

    def _preview(self) -> None:
        data = self._collect()
        self._persist(data)          # كل معاينة تُحفظ تلقائياً في الفاوتشرات
        code = getattr(self.trip, "code", "") or "يدوي"
        G.open_preview(
            self,
            lambda p: export_umrah_voucher_pdf(self.rec, p, data=data),
            f"فاوتشر {code}", "pdf")


class TransportRequestEditorDialog(Toplevel, _EditorMixin):
    """محرّر طلب حجز المواصلات: خطاب رسمي لشركة النقل — الجهة واللقب والضيف،
    حجوزات مكة/المدينة (فندق/غرفة/إطلالة)، جدول الطيران (بقراءة أماديوس سحباً
    وإفلاتاً)، وجدول الحركة، مع الحفظ في النظام والمعاينة."""

    def __init__(self, parent, rec, trip, data, *, company=None, app=None,
                 on_saved=None) -> None:
        super().__init__(parent)
        self.parent = parent
        self.rec = rec
        self.trip = trip
        self._company_dict = company
        self._app = app
        self._on_saved = on_saved
        self._number = str(data.get("number") or "")
        self.title("محرّر طلب حجز المواصلات")
        self.configure(bg=G.BG)
        self.geometry("980x720")
        self.minsize(780, 520)
        self.transient(parent)
        self._scroll_body()

        self._meta: dict[str, StringVar] = {}
        self._book_rows: list = []
        self._flight_rows: list = []
        self._move_rows: list = []

        self._build_head(data)
        self._build_bookings(data)
        self._build_flights(data)
        self._build_moves(data)
        self._attach_clipboard(self.body)

        bar = ttk.Frame(self, padding=(10, 6))
        bar.pack(fill=X)
        ttk.Button(bar, text="🖨  معاينة PDF",
                   command=self._preview).pack(side=RIGHT)
        ttk.Button(bar, text="💾  حفظ الطلب",
                   command=self._save).pack(side=RIGHT, padx=6)
        ttk.Button(bar, text="إغلاق", command=self.destroy).pack(side=RIGHT,
                                                                 padx=6)
        try:
            G.enable_minmax(self)
        except Exception:
            pass
        self.grab_set()

    def _mrow(self, lf, label, key, r, c, data, width=26, values=None):
        ttk.Label(lf, text=label).grid(row=r, column=c * 2, sticky="e",
                                       padx=(8, 4), pady=3)
        var = StringVar(value=str(data.get(key) or ""))
        self._meta[key] = var
        if values:
            ttk.Combobox(lf, textvariable=var, values=list(values),
                         width=width).grid(row=r, column=c * 2 + 1, sticky="we",
                                           padx=(0, 8), pady=3)
        else:
            ttk.Entry(lf, textvariable=var, width=width, justify="right").grid(
                row=r, column=c * 2 + 1, sticky="we", padx=(0, 8), pady=3)
        return var

    def _build_head(self, data):
        lf = self._section("بيانات الطلب")
        ttk.Label(lf, text="رقم الطلب").grid(row=0, column=0, sticky="e",
                                             padx=(8, 4), pady=3)
        ttk.Label(lf, text=self._number, foreground=G.ACCENT,
                  font=(G._FUI, 10, "bold")).grid(row=0, column=1,
                                                       sticky="w", pady=3)
        ttk.Label(lf, text="التاريخ").grid(row=0, column=2, sticky="e",
                                           padx=(8, 4), pady=3)
        self._build_date_picker(lf, data.get("date"), row=0, col=3)
        self._mrow(lf, "الجهة (السادة/…)", "recipient", 1, 0, data, width=40)
        self._mrow(lf, "اللقب", "honorific", 2, 0, data, width=12,
                   values=TREQ_HONORIFICS)
        self._mrow(lf, "اسم الضيف", "guest_ar", 2, 1, data)
        self._mrow(lf, "الجنسية", "nationality", 3, 0, data, width=14)
        self._mrow(lf, "جوال رقم", "phone", 3, 1, data)
        self._mrow(lf, "عدد الأشخاص", "persons", 4, 0, data, width=8)
        lf.columnconfigure(1, weight=1)
        lf.columnconfigure(3, weight=1)

    def _build_bookings(self, data):
        lf = self._section("الحجوزات (المدينة / الفندق / نوع الغرفة / الإطلالة)")
        self._book_box = ttk.Frame(lf)
        self._book_box.pack(fill=X)
        for r in data.get("bookings", []):
            self._add_book_row(list(r))
        ttk.Button(lf, text="＋ إضافة حجز",
                   command=lambda: self._add_book_row()).pack(anchor="e",
                                                              pady=(4, 0))

    def _add_book_row(self, values=None):
        values = list(values or []) + ["", "", "", ""]
        fr = ttk.Frame(self._book_box)
        fr.pack(fill=X, pady=2)
        city = self._cell(fr, "المدينة", values[0], QUOTE_CITY_OPTIONS, 12,
                          False)
        hotel = self._cell(fr, "الفندق", values[1], QUOTE_HOTELS, 22, False)
        room = self._cell(fr, "نوع الغرفة", values[2], QUOTE_ROOM_TYPES, 13,
                          False)
        view = self._cell(fr, "الإطلالة", values[3], QUOTE_VIEWS, 12, False)
        entry = [fr, [city, hotel, room, view]]
        ttk.Button(fr, text="حذف", width=5,
                   command=lambda: self._del_row(self._book_rows, entry)).pack(
            side=RIGHT, padx=(4, 2))
        self._book_rows.append(entry)
        self._attach_clipboard(fr)

    def _build_flights(self, data):
        lf = self._section("جدول الطيران — اقرأ من صورة حجز أماديوس أو أدخل "
                           "يدوياً")
        self._amadeus_bar(lf).pack(anchor="e", pady=(0, 4))
        self._drop = ttk.Label(
            lf, text="⬇ اسحب صورة حجز الأماديوس هنا وأفلتها لقراءتها",
            anchor="center", relief="groove", padding=6)
        self._drop.pack(fill=X, pady=(0, 4))
        if not self._enable_drop(self._drop):
            self._drop.configure(text="📷 استخدم أزرار القراءة أعلاه "
                                      "(السحب والإفلات غير متاح)")
        self._flight_box = ttk.Frame(lf)
        self._flight_box.pack(fill=X)
        for r in data.get("flights", []):
            self._add_flight_row(list(r))
        ttk.Button(lf, text="＋ إضافة رحلة",
                   command=lambda: self._add_flight_row()).pack(anchor="e",
                                                                pady=(4, 0))

    def _add_flight_row(self, values=None):
        # [التاريخ، الناقل، الإقلاع، من، الوصول، إلى]
        values = list(values or []) + [""] * 6
        fr = ttk.Frame(self._flight_box)
        fr.pack(fill=X, pady=2)
        dp = self._date_cell(fr, "التاريخ", values[0])
        specs = [("الناقل", QUOTE_CARRIERS, 10, False),
                 ("الإقلاع", quote_times(), 7, False),
                 ("من", QUOTE_AIRPORT_CITIES, 8, False),
                 ("الوصول", quote_times(), 7, False),
                 ("إلى", QUOTE_AIRPORT_CITIES, 8, False)]
        cells = [self._cell(fr, lbl, values[i], opts, w, ro)
                 for i, (lbl, opts, w, ro) in enumerate(specs, start=1)]
        entry = [fr, dp, cells]
        ttk.Button(fr, text="حذف", width=5,
                   command=lambda: self._del_row(self._flight_rows, entry)).pack(
            side=RIGHT, padx=(4, 2))
        self._flight_rows.append(entry)
        self._attach_clipboard(fr)

    def _build_moves(self, data):
        lf = self._section("جدول الحركة — المواصلات المطلوبة (التاريخ / خط "
                           "السير / عدد / نوع السيارة / موديل / الوقت)")
        self._move_box = ttk.Frame(lf)
        self._move_box.pack(fill=X)
        for r in data.get("movements", []):
            self._add_move_row(list(r))
        ttk.Button(lf, text="＋ إضافة حركة",
                   command=lambda: self._add_move_row()).pack(anchor="e",
                                                              pady=(4, 0))

    def _add_move_row(self, values=None):
        # [التاريخ، خط السير، عدد، نوع السيارة، موديل، الوقت]
        values = list(values or []) + [""] * 6
        fr = ttk.Frame(self._move_box)
        fr.pack(fill=X, pady=2)
        dp = self._date_cell(fr, "التاريخ", values[0])
        route = StringVar(value=str(values[1] or ""))
        sub = ttk.Frame(fr)
        sub.pack(side=RIGHT, padx=2)
        ttk.Label(sub, text="خط السير", font=(G._FUI, 7)).pack()
        ttk.Entry(sub, textvariable=route, width=26, justify="right").pack()
        count = self._cell(fr, "عدد", values[2] or "1",
                           [str(i) for i in range(1, 11)], 4, False)
        car = self._cell(fr, "نوع السيارة", values[3], VOUCHER_CAR_TYPES, 9,
                         False)
        model = self._cell(fr, "موديل", values[4], voucher_car_models(), 7,
                           False)
        tm = self._cell(fr, "الوقت", values[5], quote_times(), 7, False)
        entry = [fr, dp, route, [count, car, model, tm]]
        ttk.Button(fr, text="حذف", width=5,
                   command=lambda: self._del_row(self._move_rows, entry)).pack(
            side=RIGHT, padx=(4, 2))
        self._move_rows.append(entry)
        self._attach_clipboard(fr)

    def _collect(self) -> dict:
        data = {k: v.get().strip() for k, v in self._meta.items()}
        data["number"] = self._number
        data["date"] = self._d.get()
        data["office_manager"] = QUOTE_OFFICE_NAME
        data["office_title"] = QUOTE_OFFICE_TITLE
        data["bookings"] = [[c.get().strip() for c in cells]
                            for _fr, cells in self._book_rows
                            if any(c.get().strip() for c in cells)]
        data["flights"] = [[dp.get()] + [c.get().strip() for c in cells]
                           for _fr, dp, cells in self._flight_rows
                           if dp.get() or any(c.get().strip() for c in cells)]
        data["movements"] = [
            [dp.get(), route.get().strip()] + [c.get().strip() for c in cells]
            for _fr, dp, route, cells in self._move_rows
            if dp.get() or route.get().strip()
            or any(c.get().strip() for c in cells)]
        return data

    def _persist(self, data):
        """يخزّن الطلب ضمن «طلبات المواصلات» (يحدّث الموجود بنفس الرقم)."""
        if self._app is None:
            return
        umrah.save_transport_request(self._app._settings, data)
        try:
            save_settings(self._app._settings)
        except OSError:
            pass
        if callable(self._on_saved):
            self._on_saved()

    def _save(self):
        if self._app is None:
            messagebox.showinfo("حفظ", "تعذّر تحديد النظام للحفظ.", parent=self)
            return
        self._persist(self._collect())
        messagebox.showinfo("الطلبات", f"تم حفظ الطلب {self._number}.",
                            parent=self)

    def _preview(self):
        data = self._collect()
        self._persist(data)          # كل معاينة تُحفظ تلقائياً في الطلبات
        code = getattr(self.trip, "code", "") or "يدوي"
        G.open_preview(
            self,
            lambda p: export_umrah_transport_request_pdf(self.rec, p, data=data),
            f"مواصلات {code}", "pdf")


class QuotationEditorDialog(Toplevel, _EditorMixin):
    """محرّر عرض السعر: قوائم منسدلة للضيوف والإقامة والطيران والمواصلات،
    تقويم منبثق للتواريخ، وبنود قطار الحرمين والتأشيرات — قبل المعاينة."""

    def __init__(self, parent, rec, trip, data: dict, *, app=None,
                 company=None, on_saved=None) -> None:
        super().__init__(parent)
        self.parent = parent
        self.rec = rec
        self.trip = trip
        self._app = app
        self._company_dict = company
        self._on_saved = on_saved
        self._lang = str(data.get("lang") or "ar")
        self.title("محرّر عرض السعر")
        self.configure(bg=G.BG)
        self.geometry("1000x720")
        self.minsize(820, 500)
        self.transient(parent)

        # شريط اختيار اللغة (عربي/إنجليزي)
        top = ttk.Frame(self, padding=(12, 8, 12, 0))
        top.pack(fill=X)
        ttk.Label(top, text="لغة العرض:",
                  font=(G._FUI, 10, "bold")).pack(side=RIGHT, padx=(0, 6))
        self._lang_var = StringVar(
            value="English" if self._lang == "en" else "عربي")
        cb = ttk.Combobox(top, textvariable=self._lang_var, width=10,
                          state="readonly", values=["عربي", "English"])
        cb.pack(side=RIGHT)
        cb.bind("<<ComboboxSelected>>", self._on_lang_change)

        self._scroll_body()

        self._fields: dict[str, StringVar] = {}
        self._guests: list = []
        self._stay_rows: list = []
        self._flight_rows: list = []
        self._line_rows: list = []
        self._number = str(data.get("number") or "")
        self._greeting = str(data.get("greeting") or "")   # ثابتة

        self._build_head(data)
        self._build_toggles(data)
        self._build_guests(data)
        self._build_stays(data)
        self._build_flights(data)
        self._build_transport(data)
        self._build_extras(data)
        self._build_costs(data)
        self._build_signatures(data)
        self._attach_clipboard(self.body)

        bar = ttk.Frame(self, padding=(10, 6))
        bar.pack(fill=X)
        ttk.Button(bar, text="🖨  معاينة PDF",
                   command=self._preview).pack(side=RIGHT)
        if self._app is not None:
            ttk.Button(bar, text="💾  حفظ في عروض الأسعار",
                       command=self._save).pack(side=RIGHT, padx=6)
        ttk.Button(bar, text="إغلاق", command=self.destroy).pack(side=RIGHT,
                                                                 padx=6)
        try:
            G.enable_minmax(self)
        except Exception:
            pass
        self.grab_set()

    def _persist(self, data):
        """يخزّن العرض ضمن «عروض الأسعار» (يحدّث الموجود بنفس الرقم)."""
        if self._app is None:
            return
        code = getattr(self.trip, "code", "") or ""
        umrah.save_quote(self._app._settings, code, data)
        try:
            save_settings(self._app._settings)
        except OSError:
            pass
        if callable(self._on_saved):
            self._on_saved()

    def _save(self):
        """يحفظ العرض يدوياً مع رسالة تأكيد."""
        if self._app is None:
            return
        self._persist(self._collect())
        messagebox.showinfo("عروض الأسعار",
                            f"تم حفظ العرض {self._number}.", parent=self)

    def _on_lang_change(self, _event=None):
        """تبديل لغة العرض: يترجم المحتوى الحالي (مع الحفاظ على تعديلات المستخدم)
        ويعيد فتح المحرّر باللغة الجديدة — يعمل للعروض المحفوظة أيضاً."""
        new = "en" if self._lang_var.get() == "English" else "ar"
        if new == self._lang:
            return
        data = translate_quotation_data(self._collect(), new)
        parent, rec, trip = self.parent, self.rec, self.trip
        app, company, on_saved = self._app, self._company_dict, self._on_saved
        self.destroy()
        QuotationEditorDialog(parent, rec, trip, data, app=app, company=company,
                              on_saved=on_saved)

    # ---- عناصر مساعدة ----
    def _field(self, parent, label, key, data, r, c, width=26):
        ttk.Label(parent, text=label).grid(row=r, column=c * 2, sticky="e",
                                           padx=(8, 4), pady=3)
        var = StringVar(value=str(data.get(key) or ""))
        self._fields[key] = var
        ttk.Entry(parent, textvariable=var, width=width, justify="right").grid(
            row=r, column=c * 2 + 1, sticky="we", padx=(0, 8), pady=3)

    def _combo(self, parent, label, key, data, values, r, c, width=18,
               readonly=True):
        ttk.Label(parent, text=label).grid(row=r, column=c * 2, sticky="e",
                                           padx=(8, 4), pady=3)
        var = StringVar(value=str(data.get(key) or ""))
        self._fields[key] = var
        ttk.Combobox(parent, textvariable=var, values=list(values), width=width,
                     state="readonly" if readonly else "normal").grid(
            row=r, column=c * 2 + 1, sticky="w", pady=3)

    # ``_cell`` و``_date_cell`` موروثتان من ``_EditorMixin``.

    # ---- البيانات الأساسية ----
    def _build_head(self, data):
        lf = self._section("البيانات الأساسية")
        ttk.Label(lf, text="رقم العرض").grid(row=0, column=0, sticky="e",
                                             padx=(8, 4), pady=3)
        ttk.Label(lf, text=self._number, foreground=G.ACCENT,
                  font=(G._FUI, 10, "bold")).grid(row=0, column=1,
                                                       sticky="w", pady=3)
        ttk.Label(lf, text="التاريخ").grid(row=0, column=2, sticky="e",
                                           padx=(8, 4), pady=3)
        self._build_date_picker(lf, data.get("date"), row=0, col=3)
        self._field(lf, "العنوان", "title", data, 1, 0)
        ttk.Label(lf, text="الفترة من").grid(row=2, column=0, sticky="e",
                                             padx=(8, 4), pady=3)
        self._build_date_picker(lf, data.get("period_from"), row=2, col=1,
                                prefix="_pf")
        ttk.Label(lf, text="إلى").grid(row=2, column=2, sticky="e",
                                       padx=(8, 4), pady=3)
        self._build_date_picker(lf, data.get("period_to"), row=2, col=3,
                                prefix="_pt")
        # توجيه العرض باسم الضيف (اختياري) مع اللقب (السيد/السيدة أو Mr./Mrs.)
        self._addr_on = BooleanVar(
            value=bool(str(data.get("addressed_to") or "").strip()))
        ttk.Checkbutton(lf, text="توجيه باسم الضيف", variable=self._addr_on).grid(
            row=3, column=0, sticky="e", padx=(8, 4), pady=3)
        arow = ttk.Frame(lf)
        arow.grid(row=3, column=1, columnspan=3, sticky="we", padx=(0, 8),
                  pady=3)
        titles = (["Mr.", "Mrs.", "Ms."] if self._lang == "en"
                  else ["السيد", "السيدة", "الآنسة"])
        self._addr_title = StringVar(
            value=str(data.get("addressed_title") or titles[0]))
        ttk.Combobox(arow, textvariable=self._addr_title, values=titles,
                     width=7).pack(side=RIGHT, padx=(4, 0))
        self._addr = StringVar(value=str(data.get("addressed_to") or ""))
        ttk.Entry(arow, textvariable=self._addr, justify="right").pack(
            side=RIGHT, fill=X, expand=True)
        lf.columnconfigure(1, weight=1)
        lf.columnconfigure(3, weight=1)

    # ---- بنود العرض (إظهار/إخفاء أي بند) ----
    def _build_toggles(self, data):
        lf = self._section("بنود العرض (أظهر/أخفِ أي بند)")
        self._show = {}
        row = ttk.Frame(lf)
        row.pack(fill=X)
        for label, key in (("الإقامة", "show_stays"),
                           ("الطيران", "show_flights"),
                           ("المواصلات", "show_transport"),
                           ("التكلفة", "show_costs")):
            var = BooleanVar(value=bool(data.get(key, True)))
            self._show[key] = var
            ttk.Checkbutton(row, text=label, variable=var).pack(side=RIGHT,
                                                                padx=10)
        ttk.Label(row, text="إظهار:").pack(side=RIGHT, padx=(0, 6))

    # ---- الضيوف ----
    def _build_guests(self, data):
        lf = self._section("الضيوف (العدد + النوع)")
        ctl = ttk.Frame(lf)
        ctl.pack(fill=X)
        self._g_count = StringVar(value="2")
        self._g_type = StringVar(value=QUOTE_GUEST_TYPES[0])
        ttk.Button(ctl, text="＋ إضافة ضيوف",
                   command=self._add_guest_ctl).pack(side=RIGHT, padx=(6, 0))
        ttk.Combobox(ctl, textvariable=self._g_type,
                     values=list(QUOTE_GUEST_TYPES), width=8,
                     state="readonly").pack(side=RIGHT, padx=2)
        ttk.Combobox(ctl, textvariable=self._g_count,
                     values=[str(i) for i in range(1, 21)], width=4,
                     state="readonly").pack(side=RIGHT, padx=2)
        ttk.Label(ctl, text="العدد / النوع:").pack(side=RIGHT, padx=(0, 4))
        self._guest_box = ttk.Frame(lf)
        self._guest_box.pack(fill=X, pady=(4, 0))
        for g in data.get("guests", []):
            self._add_guest(list(g))

    def _add_guest_ctl(self):
        self._add_guest([self._g_count.get(), self._g_type.get()])

    def _add_guest(self, values):
        values = list(values or []) + ["", ""]
        fr = ttk.Frame(self._guest_box)
        fr.pack(fill=X, pady=1)
        cvar = StringVar(value=str(values[0] or ""))
        tvar = StringVar(value=str(values[1] or ""))
        ttk.Button(fr, text="حذف", width=5,
                   command=lambda: self._del_guest(fr)).pack(side=RIGHT,
                                                             padx=(4, 1))
        ttk.Label(fr, text=f"  {values[0]} {values[1]}",
                  font=(G._FUI, 10)).pack(side=RIGHT)
        self._guests.append([fr, cvar, tvar])

    def _del_guest(self, fr):
        fr.destroy()
        self._guests = [g for g in self._guests if g[0] is not fr]

    # ---- الإقامة ----
    def _build_stays(self, data):
        lf = self._section("الإقامة")
        self._stay_specs = [
            ("المدينة", QUOTE_CITY_OPTIONS, 12, True),
            ("الليالي", QUOTE_NIGHTS, 5, True),
            ("الفندق", QUOTE_HOTELS, 20, False),
            ("نوع الغرفة", QUOTE_ROOM_TYPES, 16, True),
            ("عدد الغرف", QUOTE_ROOM_COUNTS, 5, True),
            ("الإطلالة", QUOTE_VIEWS, 12, True),
            ("الوجبات", QUOTE_MEALS, 12, True),
        ]
        self._stay_box = ttk.Frame(lf)
        self._stay_box.pack(fill=X)
        for r in data.get("stays", []):
            self._add_stay_row(list(r))
        ttk.Button(lf, text="＋ إضافة إقامة",
                   command=lambda: self._add_stay_row()).pack(anchor="e",
                                                              pady=(4, 0))

    def _add_stay_row(self, values=None):
        values = list(values or []) + [""] * 9
        fr = ttk.Frame(self._stay_box)
        fr.pack(fill=X, pady=2)
        cells = []
        for i, (label, opts, w, ro) in enumerate(self._stay_specs):
            cells.append(self._cell(fr, label, values[i], opts, w, ro))
        # تاريخ الإقامة (من – إلى) يُحدَّد يدوياً لكل مدينة
        cin = self._date_cell(fr, "من", values[7])
        cout = self._date_cell(fr, "إلى", values[8])
        entry = [fr, cells, cin, cout]
        ttk.Button(fr, text="حذف", width=5,
                   command=lambda: self._del_row(self._stay_rows, entry)).pack(
            side=RIGHT, padx=(4, 2))
        self._stay_rows.append(entry)
        self._attach_clipboard(fr)

    # ---- الطيران ----
    def _build_flights(self, data):
        lf = self._section("الطيران")
        self._combo(lf, "الدرجة", "flight_class", data, QUOTE_FLIGHT_CLASSES,
                    0, 0, width=14)
        amz = ttk.Frame(lf)
        amz.grid(row=0, column=2, columnspan=2, sticky="w", padx=6)
        for text, cmd in (("📷 من صورة", self._amadeus_file),
                          ("📋 من الحافظة", self._amadeus_clipboard),
                          ("📸 لقطة شاشة", self._amadeus_screen)):
            ttk.Button(amz, text=text, command=cmd).pack(side=LEFT, padx=2)
        lf.columnconfigure(1, weight=1)
        # منطقة سحب وإفلات صورة الأماديوس (عبر tkdnd — مستقرّة مع Tkinter)
        self._drop = ttk.Label(
            lf, text="⬇ اسحب صورة حجز الأماديوس هنا وأفلتها لقراءتها",
            anchor="center", relief="groove", padding=6)
        self._drop.grid(row=1, column=0, columnspan=4, sticky="we", pady=(6, 2))
        if not self._enable_drop(self._drop):
            self._drop.configure(text="📷 استخدم أزرار القراءة أعلاه "
                                      "(السحب والإفلات غير متاح)")
        self._flight_box = ttk.Frame(lf)
        self._flight_box.grid(row=2, column=0, columnspan=4, sticky="we",
                              pady=(4, 0))
        for r in data.get("flights", []):
            self._add_flight_row(list(r))
        ttk.Button(lf, text="＋ إضافة رحلة",
                   command=lambda: self._add_flight_row()).grid(
            row=3, column=0, columnspan=4, sticky="e", pady=(4, 0))

    # مجموعة قراءة أماديوس (السحب/الحافظة/اللقطة) موروثة من ``_EditorMixin``.

    def _add_flight_row(self, values=None):
        values = list(values or []) + [""] * 6
        fr = ttk.Frame(self._flight_box)
        fr.pack(fill=X, pady=2)
        wrap = ttk.Frame(fr)
        wrap.pack(side=RIGHT, padx=2)
        ttk.Label(wrap, text="اليوم", font=(G._FUI, 7)).pack()
        dp = DatePicker(wrap, iso=values[0], width=9)
        dp.pack()
        specs = [("الناقل", QUOTE_CARRIERS, 10, True),
                 ("الإقلاع", quote_times(), 7, False),
                 ("من", QUOTE_AIRPORT_CITIES, 8, True),
                 ("الوصول", quote_times(), 7, False),
                 ("إلى", QUOTE_AIRPORT_CITIES, 8, True)]
        cells = []
        for i, (label, opts, w, ro) in enumerate(specs, start=1):
            cells.append(self._cell(fr, label, values[i], opts, w, ro))
        entry = [fr, dp, cells]
        ttk.Button(fr, text="حذف", width=5,
                   command=lambda: self._del_row(self._flight_rows, entry)).pack(
            side=RIGHT, padx=(4, 2))
        self._flight_rows.append(entry)
        self._attach_clipboard(fr)

    # ---- المواصلات ----
    def _build_transport(self, data):
        lf = self._section("المواصلات والتنقّلات")
        veh = ttk.Frame(lf)
        veh.pack(fill=X)
        self._car_type = self._cell(veh, "نوع السيارة", data.get("car_type"),
                                    QUOTE_CAR_TYPES, 12, False)
        self._car_model = self._cell(veh, "الموديل", data.get("car_model"),
                                     QUOTE_CAR_MODELS, 7, True)
        self._car_count = self._cell(veh, "عدد السيارات", data.get("car_count"),
                                     QUOTE_CAR_COUNTS, 5, True)
        ttk.Label(veh, text="المركبة:").pack(side=RIGHT, padx=(0, 6))
        ttk.Label(lf, text="بنود التنقّل (التاريخ / من / إلى):").pack(
            anchor="e", pady=(6, 2))
        self._line_box = ttk.Frame(lf)
        self._line_box.pack(fill=X)
        for line in data.get("transport_lines", []):
            self._add_line_row(list(line) if isinstance(line, (list, tuple))
                               else ["", "", str(line)])
        ttk.Button(lf, text="＋ إضافة بند تنقّل",
                   command=lambda: self._add_line_row()).pack(anchor="e",
                                                              pady=(4, 0))

    def _add_line_row(self, values=None):
        values = list(values or []) + ["", "", ""]
        fr = ttk.Frame(self._line_box)
        fr.pack(fill=X, pady=2)
        wrap = ttk.Frame(fr)
        wrap.pack(side=RIGHT, padx=2)
        ttk.Label(wrap, text="التاريخ", font=(G._FUI, 7)).pack()
        dp = DatePicker(wrap, iso=values[0], width=9)
        dp.pack()
        cells = []
        for i, label in ((1, "من"), (2, "إلى")):
            cells.append(self._cell(fr, label, values[i], QUOTE_LOCATIONS, 16))
        entry = [fr, dp, cells]
        ttk.Button(fr, text="حذف", width=5,
                   command=lambda: self._del_row(self._line_rows, entry)).pack(
            side=RIGHT, padx=(4, 2))
        self._line_rows.append(entry)
        self._attach_clipboard(fr)

    # ---- قطار الحرمين (بنود متعددة) والتأشيرات ----
    def _build_extras(self, data):
        lf = self._section("قطار الحرمين (يمكن إضافة أكثر من بند)")
        self._train_rows = []
        self._train_box = ttk.Frame(lf)
        self._train_box.pack(fill=X)
        trains = data.get("trains")
        if not trains and str(data.get("train_tickets") or "").strip():
            # توافق خلفي: تحويل البند المفرد القديم إلى صفّ
            trains = [[data.get("train_tickets"), data.get("train_class"),
                       data.get("train_from"), data.get("train_to"),
                       data.get("train_date"), data.get("train_dep"),
                       data.get("train_arr")]]
        for tr in (trains or []):
            self._add_train_row(list(tr))
        ttk.Button(lf, text="＋ إضافة بند قطار",
                   command=lambda: self._add_train_row()).pack(anchor="e",
                                                               pady=(4, 0))

        lf2 = self._section("التأشيرات")
        self._visas_on = BooleanVar(
            value=bool(str(data.get("visa_count") or data.get("visas") or
                           "").strip()))
        row = ttk.Frame(lf2)
        row.pack(fill=X)
        ttk.Checkbutton(row, text="إضافة بند التأشيرات",
                        variable=self._visas_on).pack(side=RIGHT, padx=(0, 12))
        self._visa_count = self._cell(row, "العدد", data.get("visa_count"),
                                      [str(i) for i in range(1, 51)], 5)
        self._visa_type = self._cell(row, "النوع",
                                     data.get("visa_type") or "عمرة",
                                     ("سياحية", "عمرة"), 10)

    def _add_train_row(self, values=None):
        values = list(values or []) + [""] * 7
        fr = ttk.Frame(self._train_box)
        fr.pack(fill=X, pady=2)
        v_tk = self._cell(fr, "التذاكر", values[0],
                          [str(i) for i in range(1, 21)], 5)
        v_cl = self._cell(fr, "الدرجة", values[1] or "سياحية",
                          QUOTE_FLIGHT_CLASSES, 11)
        v_fr = self._cell(fr, "من", values[2] or "المدينة",
                          ("المدينة", "مكة"), 9, False)
        v_to = self._cell(fr, "إلى", values[3] or "مكة",
                          ("المدينة", "مكة"), 9, False)
        dp = self._date_cell(fr, "التاريخ", values[4])
        v_dep = self._cell(fr, "الإقلاع", values[5], quote_times(), 7, False)
        v_arr = self._cell(fr, "الوصول", values[6], quote_times(), 7, False)
        entry = [fr, [v_tk, v_cl, v_fr, v_to], dp, [v_dep, v_arr]]
        ttk.Button(fr, text="حذف", width=5,
                   command=lambda: self._del_row(self._train_rows, entry)).pack(
            side=RIGHT, padx=(4, 2))
        self._train_rows.append(entry)
        self._attach_clipboard(fr)

    # ---- التكلفة (تُحسب تلقائياً) ----
    def _build_costs(self, data):
        lf = self._section("التكلفة (تُحسب تلقائياً حسب العدد ونوع الغرفة)")
        self._currency = StringVar(value=str(data.get("currency") or "درهم"))
        self._price_rows = []
        self._price_heads = [("نوع الشخص", 10), ("نوع الغرفة", 16),
                             ("العدد", 6), ("سعر الفرد", 10), ("الإجمالي", 11)]
        hdr = ttk.Frame(lf)
        hdr.pack(fill=X)
        for label, w in self._price_heads:
            ttk.Label(hdr, text=label, width=w, anchor="center",
                      font=(G._FUI, 8, "bold")).pack(side=RIGHT, padx=1)
        ttk.Label(hdr, text="", width=5).pack(side=RIGHT)
        self._price_box = ttk.Frame(lf)
        self._price_box.pack(fill=X)
        for r in data.get("pricing", []):
            self._add_price_row(list(r))
        ttk.Button(lf, text="＋ إضافة فئة سعر",
                   command=lambda: self._add_price_row()).pack(anchor="e",
                                                               pady=(4, 0))
        # الإجمالي الكلي (محسوب تلقائياً) + العملة
        tot = ttk.Frame(lf)
        tot.pack(fill=X, pady=(8, 0))
        self._total_var = StringVar(value="0")
        ttk.Label(tot, textvariable=self._total_var,
                  font=(G._FUI, 13, "bold"),
                  foreground=G.ACCENT).pack(side=RIGHT, padx=6)
        ttk.Label(tot, text="التكلفة الإجمالية:",
                  font=(G._FUI, 11, "bold")).pack(side=RIGHT)
        ttk.Combobox(tot, textvariable=self._currency,
                     values=["درهم", "ريال", "دولار"], width=7).pack(side=LEFT)
        ttk.Label(tot, text="العملة:").pack(side=LEFT)
        self._recalc_total()

        # الصلاحية والملاحظات والخاتمة
        lf2 = self._section("الصلاحية والملاحظات والخاتمة")
        ttk.Label(lf2, text="صالح حتى").grid(row=0, column=0, sticky="e",
                                             padx=(8, 4), pady=3)
        self._build_date_picker(lf2, data.get("validity"), row=0, col=1,
                                prefix="_vl")
        # وقت نهاية الصلاحية
        ttk.Label(lf2, text="الساعة").grid(row=0, column=2, sticky="e",
                                           padx=(8, 4), pady=3)
        self._vl_time = StringVar(value=str(data.get("validity_time") or ""))
        ttk.Combobox(lf2, textvariable=self._vl_time, values=quote_times(),
                     width=8).grid(row=0, column=3, sticky="w", pady=3)
        self._vl_on = BooleanVar(value=bool(str(data.get("validity") or
                                               "").strip()))
        ttk.Checkbutton(lf2, text="إظهار الصلاحية",
                        variable=self._vl_on).grid(row=1, column=0, sticky="w",
                                                   padx=(8, 0))
        # ملاحظة على العرض — مع ملاحظات جاهزة تُترجم آلياً
        ttk.Label(lf2, text="ملاحظة").grid(row=2, column=0, sticky="ne",
                                           padx=(8, 4), pady=3)
        nfr = ttk.Frame(lf2)
        nfr.grid(row=2, column=1, columnspan=3, sticky="we", padx=(0, 8),
                 pady=3)
        preset = StringVar()
        ttk.Combobox(nfr, textvariable=preset, values=list(QUOTE_NOTES),
                     state="readonly", width=48).pack(fill=X)
        self._note = Text(nfr, height=2, wrap="word", font=(G._FUI, 10))
        self._note.insert("1.0", str(data.get("note") or ""))
        self._note.pack(fill=X, pady=(3, 0))

        def _add_preset(_e=None):
            p = preset.get().strip()
            if p:
                cur = self._note.get("1.0", "end").strip()
                self._note.delete("1.0", "end")
                self._note.insert("1.0", (cur + "\n" + p).strip()
                                  if cur else p)
        preset.trace_add("write", lambda *a: _add_preset())
        self._field(lf2, "خاتمة العرض", "closing", data, 3, 0, width=60)
        lf2.columnconfigure(1, weight=1)
        lf2.columnconfigure(3, weight=1)

    def _add_price_row(self, values=None):
        values = list(values or []) + ["", "", "", ""]
        fr = ttk.Frame(self._price_box)
        fr.pack(fill=X, pady=2)
        pt = StringVar(value=str(values[0] or ""))
        rt = StringVar(value=str(values[1] or ""))
        cnt = StringVar(value=str(values[2] or ""))
        price = StringVar(value=str(values[3] or ""))
        sub = StringVar(value="0")
        ttk.Combobox(fr, textvariable=pt, values=list(QUOTE_GUEST_TYPES),
                     width=9, state="readonly").pack(side=RIGHT, padx=1)
        ttk.Combobox(fr, textvariable=rt, values=list(QUOTE_ROOM_TYPES),
                     width=15).pack(side=RIGHT, padx=1)
        ttk.Combobox(fr, textvariable=cnt,
                     values=[str(i) for i in range(1, 31)], width=5).pack(
            side=RIGHT, padx=1)
        ttk.Entry(fr, textvariable=price, width=10, justify="center").pack(
            side=RIGHT, padx=1)
        ttk.Label(fr, textvariable=sub, width=11, anchor="center",
                  font=(G._FUI, 9, "bold"),
                  foreground=G.ACCENT).pack(side=RIGHT, padx=1)
        entry = [fr, [pt, rt, cnt, price], sub]
        ttk.Button(fr, text="حذف", width=5,
                   command=lambda: (self._del_row(self._price_rows, entry),
                                    self._recalc_total())).pack(side=RIGHT,
                                                                padx=(4, 1))
        for v in (cnt, price):
            v.trace_add("write", lambda *a: self._recalc_total())
        self._price_rows.append(entry)
        self._attach_clipboard(fr)
        self._recalc_total()

    def _recalc_total(self):
        pricing = [[pt.get(), rt.get(), cnt.get(), pr.get()]
                   for _fr, (pt, rt, cnt, pr), _sub in self._price_rows]
        rows, total = quotation_pricing(pricing)
        for (_fr, _cells, subvar), row in zip(self._price_rows, rows):
            subvar.set(fmt_money(row[4]))
        if hasattr(self, "_total_var"):
            self._total_var.set(fmt_money(total))

    def _build_signatures(self, data):
        lf = self._section("التوقيعات")
        # الخانة القابلة للتعديل: الاسم / الصفة / رقم الهاتف
        self._field(lf, "الصفة", "gm_title", data, 0, 0)
        self._field(lf, "الاسم", "gm_name", data, 0, 1)
        self._field(lf, "رقم الهاتف", "gm_phone", data, 1, 0)
        # الخانة الثابتة (غير قابلة للتعديل)
        ttk.Label(lf, text="الخانة الثابتة:").grid(row=2, column=0, sticky="e",
                                                   padx=(8, 4), pady=(8, 3))
        fixed = (f"{QUOTE_OFFICE_TITLE} — {QUOTE_OFFICE_NAME} — "
                 f"{QUOTE_OFFICE_PHONE}")
        ttk.Label(lf, text=fixed, foreground=G.ACCENT,
                  font=(G._FUI, 9, "bold")).grid(row=2, column=1,
                                                     columnspan=3, sticky="w",
                                                     pady=(8, 3))
        lf.columnconfigure(1, weight=1)
        lf.columnconfigure(3, weight=1)

    # ---- الجمع والمعاينة ----
    def _collect(self):
        data = {k: v.get().strip() for k, v in self._fields.items()}
        data["lang"] = self._lang
        data["number"] = self._number
        data["greeting"] = self._greeting
        data["date"] = self._d.get()
        data["period_from"] = self._pf.get()
        data["period_to"] = self._pt.get()
        data["validity"] = self._vl.get() if self._vl_on.get() else ""
        data["validity_time"] = (self._vl_time.get().strip()
                                 if self._vl_on.get() else "")
        data["note"] = self._note.get("1.0", "end").strip()
        data["guests"] = [[c.get().strip(), t.get().strip()]
                          for _fr, c, t in self._guests
                          if c.get().strip() or t.get().strip()]
        data["stays"] = [[c.get().strip() for c in cells]
                         + [cin.get(), cout.get()]
                         for _fr, cells, cin, cout in self._stay_rows
                         if any(c.get().strip() for c in cells)]
        data["flights"] = [[dp.get().strip()] +
                           [c.get().strip() for c in cells]
                           for _fr, dp, cells in self._flight_rows
                           if dp.get().strip() or
                           any(c.get().strip() for c in cells)]
        for key, var in self._show.items():
            data[key] = bool(var.get())
        data["addressed_to"] = (self._addr.get().strip()
                                if self._addr_on.get() else "")
        data["addressed_title"] = self._addr_title.get().strip()
        # قطار الحرمين: بنود متعددة [التذاكر، الدرجة، من، إلى، التاريخ، الإقلاع،
        # الوصول] — تُدرَج البنود التي لها عدد تذاكر فقط
        data["trains"] = [[c.get().strip() for c in cells4] + [dp.get()]
                          + [c.get().strip() for c in cells2]
                          for _fr, cells4, dp, cells2 in self._train_rows
                          if cells4[0].get().strip()]
        # التأشيرات: يُبنى النصّ من العدد والنوع (سياحية/عمرة)
        vcnt = self._visa_count.get().strip()
        vtype = self._visa_type.get().strip() or "عمرة"
        data["visa_count"] = vcnt if self._visas_on.get() else ""
        data["visa_type"] = vtype
        data["visas"] = (f"عدد ({vcnt}) تأشيرة {vtype}"
                         if (self._visas_on.get() and vcnt) else "")
        data["car_type"] = self._car_type.get().strip()
        data["car_model"] = self._car_model.get().strip()
        data["car_count"] = self._car_count.get().strip()
        lines = [[dp.get().strip()] + [c.get().strip() for c in cells]
                 for _fr, dp, cells in self._line_rows]
        data["transport_lines"] = [row for row in lines if any(row)]
        # التسعير: [نوع الشخص، نوع الغرفة، العدد، سعر الفرد] (الإجمالي تلقائي)
        data["currency"] = self._currency.get().strip() or "درهم"
        data["pricing"] = [[pt.get().strip(), rt.get().strip(),
                            cnt.get().strip(), pr.get().strip()]
                           for _fr, (pt, rt, cnt, pr), _sub in self._price_rows
                           if any(x.get().strip() for x in (pt, rt, cnt, pr))]
        return data

    def _preview(self):
        data = self._collect()
        self._persist(data)          # كل معاينة تُحفظ تلقائياً في عروض الأسعار
        code = getattr(self.trip, "code", "") or "يدوي"
        G.open_preview(
            self,
            lambda p: export_umrah_quotation_pdf(self.rec, p, data=data),
            f"عرض سعر {code}", "pdf")


class QuotesListWindow(Toplevel):
    """قائمة «عروض الأسعار» المحفوظة لبرنامج: فتح/تعديل، معاينة، حذف."""

    def __init__(self, parent, app, trip) -> None:
        super().__init__(parent)
        self.app = app
        self.trip = trip
        name = getattr(trip, "name", "") or getattr(trip, "code", "")
        self.title(f"عروض الأسعار — {name}")
        self.configure(bg=G.BG)
        self.geometry("760x430")
        self.transient(parent)
        outer = ttk.Frame(self, padding=8)
        outer.pack(fill=BOTH, expand=True)
        cols = ("number", "date", "to", "total")
        heads = {"number": "رقم العرض", "date": "التاريخ",
                 "to": "موجّه إلى", "total": "الإجمالي"}
        widths = {"number": 120, "date": 100, "to": 280, "total": 130}
        self.tree = ttk.Treeview(outer, columns=cols, show="headings",
                                 selectmode="browse")
        for c in cols:
            self.tree.heading(c, text=heads[c])
            self.tree.column(c, width=widths[c],
                             anchor="e" if c == "to" else "center")
        vs = ttk.Scrollbar(outer, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        vs.pack(side=RIGHT, fill="y")
        bar = ttk.Frame(self, padding=(8, 6))
        bar.pack(fill=X)
        for text, cmd in (("✏ فتح/تعديل", self.open_sel),
                          ("👁 معاينة", self.preview_sel),
                          ("🗑 حذف", self.delete_sel),
                          ("↻ تحديث", self.refresh)):
            ttk.Button(bar, text=G.rtl(text), command=cmd).pack(side=RIGHT,
                                                                padx=3)
        ttk.Button(bar, text="إغلاق", command=self.destroy).pack(side=LEFT,
                                                                 padx=3)
        self.tree.bind("<Double-1>", lambda e: self.open_sel())
        self._quotes: list = []
        self.refresh()
        try:
            G.enable_minmax(self)
        except Exception:
            pass
        self.grab_set()

    def refresh(self) -> None:
        code = getattr(self.trip, "code", "") or ""
        self._quotes = umrah.load_quotes(self.app._settings, code)
        self.tree.delete(*self.tree.get_children())
        for i, q in enumerate(self._quotes):
            _rows, total = quotation_pricing(q.get("pricing", []))
            cur = q.get("currency", "درهم")
            self.tree.insert("", "end", iid=str(i), values=(
                q.get("number", ""), q.get("date", ""),
                q.get("addressed_to", "") or "—", f"{fmt_money(total)} {cur}"))

    def _sel(self):
        s = self.tree.selection()
        return self._quotes[int(s[0])] if s else None

    def open_sel(self) -> None:
        q = self._sel()
        if q is None:
            messagebox.showinfo("عروض الأسعار", "اختر عرضاً أولاً.", parent=self)
            return
        QuotationEditorDialog(self, PassportData(), self.trip, dict(q),
                              app=self.app, company=self.app._settings.get(
                                  "company") if isinstance(
                                  self.app._settings.get("company"), dict)
                              else None, on_saved=self.refresh)

    def preview_sel(self) -> None:
        q = self._sel()
        if q is None:
            return
        G.open_preview(
            self,
            lambda p: export_umrah_quotation_pdf(PassportData(), p, data=q),
            f"عرض {q.get('number', '')}", "pdf")

    def delete_sel(self) -> None:
        q = self._sel()
        if q is None:
            return
        if not messagebox.askyesno("حذف",
                                   f"حذف العرض {q.get('number', '')}؟",
                                   parent=self):
            return
        umrah.delete_quote(self.app._settings, getattr(self.trip, "code", "")
                           or "", q.get("number", ""))
        try:
            save_settings(self.app._settings)
        except OSError:
            pass
        self.refresh()


class GroupPricerWindow(Toplevel, _EditorMixin):
    """مسعّر المجموعات: يحسب كلفة الفرد وسعر البيع لكل نوع غرفة تلقائياً من
    بنود الفنادق والوجبات والخدمات والربح (على غرار جداول التسعير)."""

    def __init__(self, parent, app, data=None, on_saved=None) -> None:
        super().__init__(parent)
        self._app = app
        self._on_saved = on_saved
        self._number = str((data or {}).get("number") or
                           umrah.next_pricing_number(app._settings))
        if not (data or {}).get("number"):
            try:
                save_settings(app._settings)
            except OSError:
                pass
        self.title("مسعّر المجموعات")
        self.configure(bg=G.BG)
        self.geometry("980x700")
        self.minsize(800, 520)
        self.transient(parent)
        self._scroll_body()

        self._f: dict[str, StringVar] = {}
        self._widgets: dict[str, object] = {}
        self._build_head()
        self._build_types()
        self._build_hotels()
        self._build_services()
        self._build_margin()
        self._build_result()
        if data:
            self._populate(data)
        self._attach_clipboard(self.body)

        bar = ttk.Frame(self, padding=(10, 6))
        bar.pack(fill=X)
        _cbtn(bar, "🖨  معاينة PDF", self._preview, "act").pack(side=RIGHT)
        _cbtn(bar, "💾  حفظ التسعير", self._save, "primary").pack(
            side=RIGHT, padx=6)
        _cbtn(bar, "إغلاق", self.destroy).pack(side=RIGHT, padx=6)
        try:
            G.enable_minmax(self)
        except Exception:
            pass
        self.grab_set()
        self._recalc()

    def _populate(self, data):
        for k, v in self._f.items():
            if k in data:
                v.set(str(data.get(k) or ""))
        if data.get("period_from"):
            self._pf.set(data["period_from"])
        if data.get("period_to"):
            self._pt.set(data["period_to"])
        sel = data.get("room_types")
        if isinstance(sel, list) and sel:
            for name, var in self._type_vars.items():
                var.set(name in sel)
        if "include_madinah" in data:
            inc = str(data.get("include_madinah")).strip() not in (
                "", "0", "False", "false")
            self._inc_md.set(inc)
            self._toggle_madinah()
        items = data.get("items")
        if isinstance(items, list):
            for entry in list(self._item_rows):
                entry[0].destroy()
            self._item_rows.clear()
            for it in items:
                name, amt = (list(it) + ["", ""])[:2]
                self._add_item_row(name, amt)

    def _save(self):
        data = self._collect()
        umrah.save_pricing(self._app._settings, data)
        try:
            save_settings(self._app._settings)
        except OSError:
            pass
        messagebox.showinfo("التسعيرات",
                            f"تم حفظ التسعير {self._number}.", parent=self)
        if callable(self._on_saved):
            self._on_saved()

    def _mfield(self, parent, label, key, r, c, values=None, width=15):
        ttk.Label(parent, text=label).grid(row=r, column=c * 2, sticky="e",
                                           padx=(8, 4), pady=3)
        v = StringVar(value="")
        self._f[key] = v
        if values:
            w = ttk.Combobox(parent, textvariable=v, values=list(values),
                             width=width)
        else:
            w = ttk.Entry(parent, textvariable=v, width=width, justify="right")
        w.grid(row=r, column=c * 2 + 1, sticky="we", padx=(0, 8), pady=3)
        self._widgets[key] = w
        v.trace_add("write", lambda *a: self._recalc())
        return v

    def _build_head(self):
        lf = self._section("العنوان والفترة والعملة")
        ttk.Label(lf, text="رقم التسعير").grid(row=0, column=2, sticky="e",
                                               padx=(8, 4), pady=3)
        ttk.Label(lf, text=self._number, foreground=G.ACCENT,
                  font=(G._FUI, 10, "bold")).grid(row=0, column=3,
                                                       sticky="w", pady=3)
        self._mfield(lf, "عنوان التسعير", "title", 0, 0, width=40)
        ttk.Label(lf, text="من").grid(row=1, column=0, sticky="e", padx=(8, 4),
                                      pady=3)
        self._build_date_picker(lf, "", row=1, col=1, prefix="_pf")
        ttk.Label(lf, text="إلى").grid(row=1, column=2, sticky="e", padx=(8, 4),
                                       pady=3)
        self._build_date_picker(lf, "", row=1, col=3, prefix="_pt")
        self._mfield(lf, "العملة", "currency", 2, 0,
                     values=("درهم", "ريال", "دولار"))
        self._f["currency"].set("درهم")
        lf.columnconfigure(1, weight=1)
        lf.columnconfigure(3, weight=1)

    def _build_types(self):
        lf = self._section("أنواع الغرف المطلوب تسعيرها")
        self._type_vars: dict[str, "BooleanVar"] = {}
        row = ttk.Frame(lf)
        row.pack(fill=X)
        for name, _occ in umrah.GROUP_ROOM_TYPES:
            var = BooleanVar(value=True)
            self._type_vars[name] = var
            ttk.Checkbutton(row, text=name, variable=var,
                            command=self._recalc).pack(side=RIGHT, padx=8)
            var.trace_add("write", lambda *a: self._recalc())

    _MADINAH_KEYS = ("madinah_hotel", "madinah_nights", "madinah_rate",
                     "madinah_meals")

    def _build_hotels(self):
        lf = self._section("الفنادق (سعر الغرفة/الليلة + الوجبات للفرد)")
        nights = [str(i) for i in range(1, 16)]
        self._mfield(lf, "فندق مكة", "makkah_hotel", 0, 0, width=22)
        self._mfield(lf, "ليالي مكة", "makkah_nights", 0, 1, values=nights)
        self._mfield(lf, "سعر غرفة مكة/الليلة", "makkah_rate", 1, 0)
        self._mfield(lf, "وجبات مكة (للفرد)", "makkah_meals", 1, 1)
        # تضمين المدينة المنوّرة (يمكن حذفها لمجموعات مكة فقط)
        self._inc_md = BooleanVar(value=True)
        ttk.Checkbutton(lf, text="تضمين المدينة المنوّرة", variable=self._inc_md,
                        command=self._toggle_madinah).grid(
            row=2, column=0, columnspan=4, sticky="e", padx=(8, 4), pady=(8, 2))
        self._mfield(lf, "فندق المدينة", "madinah_hotel", 3, 0, width=22)
        self._mfield(lf, "ليالي المدينة", "madinah_nights", 3, 1, values=nights)
        self._mfield(lf, "سعر غرفة المدينة/الليلة", "madinah_rate", 4, 0)
        self._mfield(lf, "وجبات المدينة (للفرد)", "madinah_meals", 4, 1)
        lf.columnconfigure(1, weight=1)
        lf.columnconfigure(3, weight=1)

    def _toggle_madinah(self):
        state = "normal" if self._inc_md.get() else "disabled"
        for key in self._MADINAH_KEYS:
            w = self._widgets.get(key)
            if w is not None:
                try:
                    w.configure(state=state)
                except Exception:
                    pass
        self._recalc()

    _DEFAULT_ITEMS = ("النقل الداخلي", "نقل المطار", "التأشيرة", "تذكرة الطيران",
                      "ماء وعصير وتمر", "الهدايا", "المصاريف الإدارية")
    # بنود افتراضية خاصة بالحج (المشاعر والهدي والتصريح والإعاشة...)
    _HAJJ_ITEMS = ("تصريح الحج (نُسك)", "خدمات المشاعر (منى/عرفات/مزدلفة)",
                   "مخيّم منى", "الهدي / الأضحية", "الإعاشة",
                   "النقل والتنقّلات", "تذكرة الطيران", "المصاريف الإدارية")

    def _build_services(self):
        lf = self._section("البنود (للفرد) — يمكن الإضافة أو الحذف")
        self._item_rows: list = []
        hdr = ttk.Frame(lf)
        hdr.pack(fill=X)
        ttk.Label(hdr, text="المبلغ", width=14, anchor="center",
                  font=(G._FUI, 8, "bold")).pack(side=RIGHT, padx=2)
        ttk.Label(hdr, text="البند", anchor="center",
                  font=(G._FUI, 8, "bold")).pack(side=RIGHT, fill=X,
                                                     expand=True, padx=2)
        ttk.Label(hdr, text="", width=5).pack(side=RIGHT)
        self._item_box = ttk.Frame(lf)
        self._item_box.pack(fill=X)
        defaults = self._HAJJ_ITEMS if app_mode.is_hajj() else self._DEFAULT_ITEMS
        for name in defaults:
            self._add_item_row(name, "")
        _cbtn(lf, "＋ إضافة بند", lambda: self._add_item_row()).pack(
            anchor="e", pady=(4, 0))

    def _add_item_row(self, name="", amount=""):
        fr = ttk.Frame(self._item_box)
        fr.pack(fill=X, pady=1)
        nvar = StringVar(value=str(name or ""))
        avar = StringVar(value=str(amount or ""))
        entry = [fr, nvar, avar]
        ttk.Button(fr, text="حذف", width=5,
                   command=lambda: (self._del_row(self._item_rows, entry),
                                    self._recalc())).pack(side=RIGHT, padx=(4, 1))
        ttk.Entry(fr, textvariable=avar, width=14, justify="right").pack(
            side=RIGHT, padx=2)
        ttk.Entry(fr, textvariable=nvar, justify="right").pack(
            side=RIGHT, fill=X, expand=True, padx=2)
        avar.trace_add("write", lambda *a: self._recalc())
        self._item_rows.append(entry)
        self._attach_clipboard(fr)
        self._recalc()

    def _build_margin(self):
        lf = self._section("الربح والمصاريف (للفرد)")
        self._mfield(lf, "نسبة الربح %", "profit_pct", 0, 0)
        self._mfield(lf, "مصاريف أخرى", "other", 0, 1)
        self._mfield(lf, "ربح عام (لكل الأنواع)", "profit", 1, 0)
        ttk.Label(lf, text="أو مبلغ ربح لكل نوع غرفة:",
                  font=(G._FUI, 8, "italic")).grid(row=2, column=0,
                                                       columnspan=4, sticky="e",
                                                       padx=(8, 4), pady=(6, 0))
        self._mfield(lf, "مفرد", "profit_single", 3, 0, width=10)
        self._mfield(lf, "ثنائي", "profit_double", 3, 1, width=10)
        self._mfield(lf, "ثلاثي", "profit_triple", 4, 0, width=10)
        self._mfield(lf, "رباعي", "profit_quad", 4, 1, width=10)
        self._mfield(lf, "طفل", "profit_child", 5, 0, width=10)
        lf.columnconfigure(1, weight=1)
        lf.columnconfigure(3, weight=1)

    def _build_result(self):
        lf = self._section("النتيجة — التكلفة والربح والنسبة وسعر البيع لكل فرد")
        cols = ("type", "net", "profit", "pct", "selling")
        self._tree = ttk.Treeview(lf, columns=cols, show="headings", height=5,
                                  selectmode="none")
        for c, txt, w in (("type", "نوع الغرفة", 110),
                          ("net", "التكلفة الصافية", 130),
                          ("profit", "الربح", 100),
                          ("pct", "النسبة %", 80),
                          ("selling", "سعر البيع", 130)):
            self._tree.heading(c, text=txt)
            self._tree.column(c, width=w, anchor="center")
        self._tree.pack(fill=X)

    def _company(self):
        co = self._app._settings.get("company")
        return co if isinstance(co, dict) else None

    def _collect(self) -> dict:
        data = {k: v.get().strip() for k, v in self._f.items()}
        data["number"] = self._number
        data["period_from"] = self._pf.get()
        data["period_to"] = self._pt.get()
        # البنود الديناميكية [الاسم، المبلغ]
        data["items"] = [[n.get().strip(), a.get().strip()]
                         for _fr, n, a in getattr(self, "_item_rows", [])
                         if n.get().strip() or a.get().strip()]
        # أنواع الغرف المختارة (فارغ = الكل)
        data["room_types"] = [name for name, var
                              in getattr(self, "_type_vars", {}).items()
                              if var.get()]
        # تضمين المدينة المنوّرة
        data["include_madinah"] = "1" if getattr(
            self, "_inc_md", None) and self._inc_md.get() else "0"
        return data

    def _recalc(self):
        if not hasattr(self, "_tree"):      # قد تُستدعى قبل بناء الجدول
            return
        rows = umrah.group_pricing(self._collect())
        self._tree.delete(*self._tree.get_children())
        for r in rows:
            self._tree.insert("", "end", values=(
                r["type"], fmt_money(r["net"]), fmt_money(r["margin"]),
                f"{r['margin_pct']:.1f}%", fmt_money(r["selling"])))

    def _preview(self):
        data = self._collect()
        # حفظ تلقائي في التسعيرات المحفوظة
        umrah.save_pricing(self._app._settings, data)
        try:
            save_settings(self._app._settings)
        except OSError:
            pass
        if callable(self._on_saved):
            self._on_saved()
        name = str(data.get("title") or "").strip() or "تسعير المجموعات"
        G.open_preview(
            self,
            lambda p: export_group_pricing_pdf(data, p, company=self._company()),
            name, "pdf")


class PricingsListWindow(Toplevel):
    """قائمة تسعيرات المجموعات المحفوظة: فتح/تعديل، معاينة، حذف."""

    def __init__(self, parent, app) -> None:
        super().__init__(parent)
        self.app = app
        self.title("التسعيرات المحفوظة")
        self.configure(bg=G.BG)
        self.geometry("720x430")
        self.transient(parent)
        outer = ttk.Frame(self, padding=8)
        outer.pack(fill=BOTH, expand=True)
        cols = ("number", "title", "cur", "double")
        heads = {"number": "الرقم", "title": "العنوان", "cur": "العملة",
                 "double": "بيع الثنائي/فرد"}
        widths = {"number": 100, "title": 300, "cur": 80, "double": 130}
        self.tree = ttk.Treeview(outer, columns=cols, show="headings",
                                 selectmode="browse")
        for c in cols:
            self.tree.heading(c, text=heads[c])
            self.tree.column(c, width=widths[c],
                             anchor="e" if c == "title" else "center")
        vs = ttk.Scrollbar(outer, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        vs.pack(side=RIGHT, fill="y")
        bar = ttk.Frame(self, padding=(8, 6))
        bar.pack(fill=X)
        for text, cmd in (("✏ فتح/تعديل", self.open_sel),
                          ("👁 معاينة", self.preview_sel),
                          ("🗑 حذف", self.delete_sel), ("↻ تحديث", self.refresh)):
            ttk.Button(bar, text=G.rtl(text), command=cmd).pack(side=RIGHT,
                                                                padx=3)
        ttk.Button(bar, text="إغلاق", command=self.destroy).pack(side=LEFT,
                                                                 padx=3)
        self.tree.bind("<Double-1>", lambda e: self.open_sel())
        self._items: list = []
        self.refresh()
        try:
            G.enable_minmax(self)
        except Exception:
            pass
        self.grab_set()

    def refresh(self) -> None:
        self._items = umrah.load_pricings(self.app._settings)
        self.tree.delete(*self.tree.get_children())
        for i, p in enumerate(self._items):
            dbl = next((r for r in umrah.group_pricing(p)
                        if r["type"] == "ثنائي"), None)
            self.tree.insert("", "end", iid=str(i), values=(
                p.get("number", ""), p.get("title", "") or "—",
                p.get("currency", "درهم"),
                fmt_money(dbl["selling"]) if dbl else "—"))

    def _sel(self):
        s = self.tree.selection()
        return self._items[int(s[0])] if s else None

    def open_sel(self) -> None:
        p = self._sel()
        if p is None:
            messagebox.showinfo("التسعيرات", "اختر تسعيراً أولاً.", parent=self)
            return
        GroupPricerWindow(self, self.app, data=dict(p), on_saved=self.refresh)

    def preview_sel(self) -> None:
        p = self._sel()
        if p is None:
            return
        name = str(p.get("title") or "").strip() or "تسعير المجموعات"
        G.open_preview(
            self,
            lambda path: export_group_pricing_pdf(
                p, path, company=self.app._settings.get("company")
                if isinstance(self.app._settings.get("company"), dict)
                else None), name, "pdf")

    def delete_sel(self) -> None:
        p = self._sel()
        if p is None:
            return
        if not messagebox.askyesno("حذف",
                                   f"حذف التسعير {p.get('number', '')}؟",
                                   parent=self):
            return
        umrah.delete_pricing(self.app._settings, p.get("number", ""))
        try:
            save_settings(self.app._settings)
        except OSError:
            pass
        self.refresh()


class SeasonDashboard(Toplevel):
    """لوحة الموسم: بطاقات ملخّص + رسم بياني للتحصيل لكل برنامج (Canvas)."""

    def __init__(self, parent, season, rows, totals) -> None:
        super().__init__(parent)
        self._rows = rows
        self.title(f"لوحة موسم العمرة {season}")
        self.configure(bg=G.BG)
        self.geometry("760x580")
        self.minsize(560, 420)
        self.transient(parent)

        head = ttk.Frame(self, style="Toolbar.TFrame", padding=(16, 12, 16, 4))
        head.pack(fill=X)
        ttk.Label(head, text=f"📊 لوحة موسم العمرة {season}",
                  font=(G._FSB, 15), foreground=G.TEXT,
                  background=G.BG).pack(side=RIGHT)

        cards = ttk.Frame(self, style="Panel.TFrame", padding=(16, 10))
        cards.pack(fill=X)
        for label, val in (("البرامج", totals["programs"]),
                           ("المعتمرون", totals["pilgrims"]),
                           ("المحصّل", totals["paid"]),
                           ("المتبقّي", totals["remaining"]),
                           ("نسبة التحصيل", totals["pct"])):
            box = ttk.Frame(cards, style="Panel.TFrame")
            box.pack(side=RIGHT, expand=True, fill=X, padx=4)
            ttk.Label(box, text=str(val), font=(G._FSB, 16),
                      foreground=G.ACCENT, background=G.BG).pack()
            ttk.Label(box, text=label, font=(G._FUI, 9), foreground=G.MUTED,
                      background=G.BG).pack()

        self._cv = Canvas(self, bg="#FFFFFF", highlightthickness=0)
        self._cv.pack(fill=BOTH, expand=True, padx=16, pady=(6, 16))
        self._cv.bind("<Configure>", lambda _e: self._draw())
        try:
            G.enable_minmax(self)
        except Exception:
            pass
        self.grab_set()
        self.after(60, self._draw)

    def _draw(self) -> None:
        cv = self._cv
        cv.delete("all")
        W = max(cv.winfo_width(), 400)
        H = max(cv.winfo_height(), 200)
        pad = 18
        cv.create_text(W - pad, pad, anchor="ne",
                       text="التحصيل لكل برنامج (المحصّل من الإجمالي)",
                       font=(G._FSB, 12), fill="#6E543A")
        rows = self._rows
        top = pad + 26
        avail = H - top - pad
        row_h = min(46, avail / max(len(rows), 1))
        label_w = 140
        bx0 = pad + 44
        bx1 = W - pad - label_w
        for i, r in enumerate(rows):
            y = top + i * row_h + row_h / 2
            if y > H - pad:
                break
            cv.create_text(W - pad, y, anchor="e",
                           text=(r["name"][:22]), font=(G._FUI, 10),
                           fill="#333333")
            cv.create_rectangle(bx0, y - 10, bx1, y + 10, fill="#EFE9DF",
                                outline="#E0D8CB")
            pct = (r["paid"] / r["total"]) if r["total"] else 0.0
            fillw = (bx1 - bx0) * min(pct, 1.0)
            if fillw > 0:                     # التعبئة من اليمين (RTL)
                cv.create_rectangle(bx1 - fillw, y - 10, bx1, y + 10,
                                    fill="#8A6E4B", outline="")
            cv.create_text((bx0 + bx1) / 2, y,
                           text=f"{pct * 100:.0f}%   ·   {r['count']} معتمر",
                           font=(G._FUI, 9), fill="#1A1A1A")
            cv.create_text(pad, y, anchor="w", text=str(r["count"]),
                           font=(G._FSB, 10), fill="#6E543A")


class _ProgAdapter:
    """يمثّل برنامج حجّ بواجهة موحّدة تفهمها المساعد ولوحات الموسم.

    برنامج الحج يحمل: مطار المغادرة، الناقل، فندقاً واحداً، وتاريخي السفر
    والعودة — نعرضها في البطاقات بدل خانتَي فندق مكة/المدينة."""

    def __init__(self, name, program=None):
        self.code = name
        self.name = name
        self.capacity = ""            # لا سعة محدّدة لبرامج الحج
        self.hotel = getattr(program, "hotel", "") if program else ""
        self.airport = getattr(program, "departure_airport", "") if program else ""
        self.carrier = getattr(program, "carrier", "") if program else ""
        # للتوافق مع الكشوف العامة (خانتا الفندق)
        self.makkah_hotel = self.hotel
        self.madinah_hotel = ""
        self.depart_date = (getattr(program, "travel_date", "")
                            or getattr(program, "departure_date", "")) if program else ""
        self.return_date = getattr(program, "return_date", "") if program else ""


def _hajj_programs(app) -> list:
    """برامج الحج ككائنات موحّدة للمساعد (برامج الحملة + أي برنامج في السجلّات)."""
    try:
        from .programs import PROGRAM_NAMES, load_programs
        progs = load_programs(app._settings) if getattr(app, "_settings", None) else []
        pmap = dict(zip(PROGRAM_NAMES, progs))
        names = list(PROGRAM_NAMES)
    except Exception:
        pmap, names = {}, []
    for r in getattr(app, "records", []) or []:
        pn = str(getattr(r, "program", "") or "").strip()
        if pn and pn not in names:
            names.append(pn)
    return [_ProgAdapter(n, pmap.get(n)) for n in names]


class _AssistCtx:
    """جسر بين المساعد والنافذة الرئيسية — يوحّد الاختلاف بين العمرة والحج."""

    group_attr = "trip"
    n_def = "المعتمر"          # الاسم المعرّف (المعتمر/الحاج)
    n_acc = "معتمراً"          # الاسم المنصوب المنكّر (معتمراً/حاجّاً)

    def __init__(self, app):
        self.app = app

    @property
    def records(self):
        return self.app.records

    @property
    def settings(self):
        return getattr(self.app, "_settings", {}) or {}

    def programs(self):
        return []

    def season(self):
        return ""

    def company(self):
        return None

    def save(self):
        self.app.save()

    def reload(self):
        try:
            self.app._reload()
        except Exception:
            pass


class UmrahCtx(_AssistCtx):
    group_attr = "trip"

    def programs(self):
        return self.app._visible_trips()

    def season(self):
        return self.app._season.get()

    def company(self):
        return self.app._company_dict()


class HajjCtx(_AssistCtx):
    group_attr = "program"
    n_def = "الحاج"
    n_acc = "حاجّاً"

    def programs(self):
        return _hajj_programs(self.app)

    def season(self):
        try:
            return self.app.season_year.get()
        except Exception:
            return ""

    def company(self):
        co = self.settings.get("company")
        return co if isinstance(co, dict) else None

    def save(self):
        self.app.save_data()

    def reload(self):
        try:
            self.app.refresh()
        except Exception:
            pass


class AskWindow(Toplevel):
    """مساعد «اسأل بياناتك»: سؤال عربي + جواب فوري محسوب من كشف الموسم."""

    def __init__(self, parent, ctx) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.app = getattr(ctx, "app", ctx)
        self.title("اسأل بياناتك")
        self.configure(bg=G.BG)
        self.geometry("720x580")
        self.minsize(560, 460)
        self.transient(parent)
        _sync_ctk_mode()
        try:
            G.apply_window_icon(self)
        except Exception:
            pass
        G.enable_minmax(self)

        head = ttk.Frame(self, style="Toolbar.TFrame", padding=(18, 14, 18, 6))
        head.pack(fill=X)
        ttk.Label(head, text="🔎 اسأل بياناتك", font=(G._FSB, 16),
                  foreground=G.TEXT, background=G.BG).pack(side=RIGHT)
        ttk.Label(head, text=G.rtl("إجابات فورية من كشف الموسم — بلا إنترنت"),
                  font=(G._FUI, 10), foreground=G.MUTED,
                  background=G.BG).pack(side=RIGHT, padx=(0, 12))

        row = ttk.Frame(self, style="Panel.TFrame", padding=(18, 12))
        row.pack(fill=X)
        self._q = StringVar()
        _cbtn(row, "اسأل", self._ask, "primary").pack(side=LEFT, padx=(0, 8))
        entry = _centry(row, self._q,
                        placeholder_text="اكتب سؤالك ثم اضغط اسأل…")
        entry.pack(side=RIGHT, fill=X, expand=True)
        entry.bind("<Return>", lambda _e: self._ask())
        G.install_entry_editing(entry)
        entry.focus_set()
        self._entry = entry

        # منطقة النتيجة (تُعاد بناؤها مع كل سؤال)
        self._body = ttk.Frame(self, style="Toolbar.TFrame", padding=(18, 8, 18, 16))
        self._body.pack(fill=BOTH, expand=True)
        self._render(assistant.answer(
            "", self.ctx.programs(), self.ctx.records,
            group_attr=self.ctx.group_attr))

    def _ask(self) -> None:
        ans = assistant.answer(self._q.get(), self.ctx.programs(),
                               self.ctx.records, season=self.ctx.season(),
                               group_attr=self.ctx.group_attr)
        self._render(ans)

    def _clear(self) -> None:
        for w in self._body.winfo_children():
            w.destroy()

    def _render(self, ans: dict) -> None:
        self._clear()
        b = self._body
        ttk.Label(b, text=G.rtl(ans.get("title", "")), font=(G._FUI, 11),
                  foreground=G.BRONZE, background=G.BG).pack(anchor="e")
        ttk.Label(b, text=G.rtl(ans.get("headline", "")), font=(G._FSB, 19),
                  foreground=G.TEXT, background=G.BG, wraplength=640,
                  justify="right").pack(anchor="e", pady=(2, 0))
        if ans.get("note"):
            ttk.Label(b, text=G.rtl(ans["note"]), font=(G._FUI, 10),
                      foreground=G.MUTED, background=G.BG, wraplength=640,
                      justify="right").pack(anchor="e", pady=(3, 0))

        if ans.get("chart"):
            self._chart(b, ans["chart"])
        if ans.get("rows"):
            self._table(b, ans["headers"], ans["rows"],
                        ans.get("records") if ans.get("action") == "whatsapp_due"
                        else None)
            xbar = ttk.Frame(b, style="Toolbar.TFrame")
            xbar.pack(fill=X, pady=(8, 0))
            _cbtn(xbar, "📊  تصدير إكسل",
                  lambda a=ans: self._export_excel(a)).pack(side=LEFT)
        if ans.get("kind") == "help" or ans.get("examples"):
            self._examples(b, ans.get("examples") or list(assistant.EXAMPLES))

    def _chart(self, parent, chart: dict) -> None:
        """مخطّط أعمدة أفقي أنيق (RTL) لبيانات المخطّط في الإجابة."""
        items = chart.get("items") or []
        if not items:
            return
        mx = chart.get("max") or max((v for _, v, _ in items), default=1) or 1
        cv = Canvas(parent, height=14 + len(items) * 28, bg=G.PANEL,
                    highlightthickness=1, highlightbackground=G.BORDER)
        cv.pack(fill=X, pady=(12, 0))

        def draw(_e=None):
            cv.delete("all")
            w = cv.winfo_width() or 640
            pad, label_w, val_w = 12, 170, 56
            x_right = w - pad
            bx1, bx0 = x_right - label_w, pad + val_w
            for i, (label, val, disp) in enumerate(items):
                y = 17 + i * 28
                cv.create_text(x_right, y, anchor="e", text=G.rtl(str(label)),
                               font=(G._FUI, 10), fill=G.TEXT)
                cv.create_rectangle(bx0, y - 8, bx1, y + 8,
                                    fill=G.ROW_ALT, outline="")
                frac = max(0.0, min(val / mx, 1.0)) if mx else 0.0
                fw = (bx1 - bx0) * frac
                if fw > 1:
                    cv.create_rectangle(bx1 - fw, y - 8, bx1, y + 8,
                                        fill="#8A6E4B", outline="")   # RTL
                cv.create_text(pad, y, anchor="w", text=G.rtl(str(disp)),
                               font=(G._FSB, 10), fill="#6E543A")

        cv.bind("<Configure>", draw)
        self.after(30, draw)

    def _table(self, parent, headers, rows, records=None) -> None:
        wrap = ttk.Frame(parent, style="Panel.TFrame", padding=6)
        wrap.pack(fill=BOTH, expand=True, pady=(14, 0))
        cols = [f"c{i}" for i in range(len(headers))]
        tv = ttk.Treeview(wrap, columns=cols, show="headings", height=11)
        for c, h in zip(cols, headers):
            tv.heading(c, text=G.rtl(h))
            tv.column(c, anchor="e",
                      width=260 if c == "c0" else 150, stretch=True)
        self._iid_rec = {}
        for i, r in enumerate(rows):
            iid = tv.insert("", "end",
                            values=[G.rtl(str(v)) for v in r],
                            tags=("odd",) if i % 2 else ())
            if records is not None and i < len(records):
                self._iid_rec[iid] = records[i]
        tv.tag_configure("odd", background=G.PANEL)
        vs = ttk.Scrollbar(wrap, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=vs.set)
        vs.pack(side=LEFT, fill=Y)
        tv.pack(side=RIGHT, fill=BOTH, expand=True)

        if records is not None:          # قائمة متأخرين -> إجراء تذكير واتساب
            self._tv = tv
            self._due_records = records
            tv.bind("<Double-1>", lambda _e: self._wa_selected())
            bar = ttk.Frame(parent, style="Toolbar.TFrame")
            bar.pack(fill=X, pady=(10, 0))
            _cbtn(bar, "📱  تذكير المحدَّد عبر واتساب", self._wa_selected,
                  "primary").pack(side=RIGHT)
            _cbtn(bar, "💰  متابعة كل المتأخرين", self._followup_all,
                  "act").pack(side=RIGHT, padx=(8, 0))
            _cbtn(bar, "📋  نسخ الأرقام", self._copy_due_phones).pack(
                side=RIGHT, padx=(8, 0))
            ttk.Label(bar, text=G.rtl("انقر الاسم نقرتين للتذكير"),
                      font=(G._FUI, 9), foreground=G.MUTED,
                      background=G.BG).pack(side=RIGHT, padx=(0, 10))

    def _followup_all(self) -> None:
        """يفتح أداة متابعة التحصيل لكل المتأخرين مع تتبّع من ذُكِّر."""
        recs = getattr(self, "_due_records", [])
        if recs:
            DueFollowupWindow(self, self.ctx, list(recs))

    def _copy_due_phones(self) -> None:
        """ينسخ أرقام كل المتأخرين بالصيغة الدولية إلى الحافظة (للبثّ الجماعي)."""
        from .whatsapp import to_intl
        cc = str(self.ctx.settings.get("whatsapp_cc", "971")).strip() or "971"
        nums, skipped = [], 0
        for r in getattr(self, "_due_records", []):
            n = to_intl(getattr(r, "phone", ""), cc)
            if n:
                nums.append(n)
            else:
                skipped += 1
        if not nums:
            messagebox.showinfo("نسخ الأرقام",
                                "لا توجد أرقام صالحة في القائمة.", parent=self)
            return
        self.clipboard_clear()
        self.clipboard_append("\n".join(nums))
        note = f"نُسخ {len(nums)} رقماً."
        if skipped:
            note += f" ({skipped} بلا رقم صالح)"
        messagebox.showinfo("نسخ الأرقام", note, parent=self)

    def _wa_selected(self) -> None:
        """يفتح واتساب برسالة تذكير سداد للمعتمر المحدَّد في الجدول."""
        sel = self._tv.selection()
        if not sel:
            messagebox.showinfo("تذكير واتساب",
                                f"اختر {self.ctx.n_acc} من القائمة أولاً.",
                                parent=self)
            return
        rec = self._iid_rec.get(sel[0])
        if rec is None:
            return
        code = getattr(rec, self.ctx.group_attr, "")
        prog = next((t.name or t.code for t in self.ctx.programs()
                     if t.code == code), "")
        co = self.ctx.company() or {}
        cc = str(self.ctx.settings.get("whatsapp_cc", "971")).strip() or "971"
        link = assistant.due_wa_link(rec, prog,
                                     co.get("name_ar") or "المصطفى للحج والعمرة", cc)
        if not link:
            messagebox.showwarning(
                "تذكير واتساب",
                f"لا يوجد رقم هاتف صالح لـ«{getattr(rec, 'full_name_ar', '')}».",
                parent=self)
            return
        try:
            G.open_in_viewer(link)
        except OSError as exc:
            messagebox.showerror("تذكير واتساب", str(exc), parent=self)

    def _examples(self, parent, examples) -> None:
        ttk.Label(parent, text=G.rtl("أمثلة — اضغط أيّها لتجربته:"),
                  font=(G._FUI, 10), foreground=G.MUTED,
                  background=G.BG).pack(anchor="e", pady=(16, 6))
        chips = ttk.Frame(parent, style="Toolbar.TFrame")
        chips.pack(fill=X)
        for ex in examples:
            _cbtn(chips, ex, lambda e=ex: self._run_example(e)).pack(
                side=RIGHT, padx=4, pady=4)

    def _run_example(self, ex: str) -> None:
        self._q.set(ex)
        self._ask()

    def _export_excel(self, ans: dict) -> None:
        """يصدّر نتيجة السؤال الحالية (جدول) إلى إكسل ويفتحها."""
        title = ans.get("title") or "نتيجة"
        safe = re.sub(r'[\\/:*?"<>|]+', "-", title).strip() or "نتيجة"
        G.open_preview(
            self,
            lambda p: export_answer_excel(title, ans.get("headers") or [],
                                          ans.get("rows") or [], p),
            f"نتيجة - {safe}", "xlsx")


class DueFollowupWindow(Toplevel):
    """متابعة تحصيل المتأخرين: قائمة بكلٍّ منهم مع تذكير واتساب وتتبّع من ذُكِّر."""

    _MARK = {"pending": "⏳ بانتظار", "done": "✓ ذُكِّر", "skip": "⤼ مؤجَّل",
             "paid": "💵 سُدِّد"}

    def __init__(self, parent, ctx, records: list) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.records = records
        self.state = ["pending"] * len(records)
        self.title("متابعة تحصيل المتأخرين")
        self.configure(bg=G.BG)
        self.geometry("820x560")
        self.minsize(640, 460)
        self.transient(parent)
        _sync_ctk_mode()
        try:
            G.apply_window_icon(self)
        except Exception:
            pass
        G.enable_minmax(self)

        self._names = {t.code: (t.name or t.code) for t in ctx.programs()}
        self._cc = str(ctx.settings.get("whatsapp_cc", "971")).strip() or "971"
        co = ctx.company() or {}
        self._company = co.get("name_ar") or "المصطفى للحج والعمرة"

        head = ttk.Frame(self, style="Toolbar.TFrame", padding=(18, 14, 18, 6))
        head.pack(fill=X)
        ttk.Label(head, text="💰 متابعة تحصيل المتأخرين", font=(G._FSB, 16),
                  foreground=G.TEXT, background=G.BG).pack(side=RIGHT)
        self._prog = ttk.Label(head, text="", font=(G._FUI, 11),
                               foreground=G.BRONZE, background=G.BG)
        self._prog.pack(side=LEFT)

        band = ttk.Frame(self, style="Panel.TFrame", padding=(18, 8))
        band.pack(fill=X)
        self._band = ttk.Label(band, text="", font=(G._FUI, 11),
                               foreground=G.TEXT, background=G.BG)
        self._band.pack(side=RIGHT)

        body = ttk.Frame(self, style="Panel.TFrame", padding=6)
        body.pack(fill=BOTH, expand=True, padx=16, pady=(6, 10))
        cols = ("name", "prog", "rem", "phone", "last", "state")
        heads = (self.ctx.n_def, "البرنامج", "المتبقّي", "الهاتف",
                 "آخر تذكير", "الحالة")
        widths = (175, 140, 100, 110, 110, 125)
        tv = ttk.Treeview(body, columns=cols, show="headings", height=11)
        for c, h, w in zip(cols, heads, widths):
            tv.heading(c, text=G.rtl(h))
            tv.column(c, anchor="e", width=w, stretch=(c in ("name", "prog")))
        self._today = date.today().isoformat()
        _green = G.SUCCESS_BG if hasattr(G, "SUCCESS_BG") else "#E6F1E9"
        tv.tag_configure("done", background=_green)
        tv.tag_configure("paid", background="#CDE9D6")
        tv.tag_configure("skip", background=G.WARN_BG if hasattr(G, "WARN_BG")
                         else "#FBF0DC")
        vs = ttk.Scrollbar(body, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=vs.set)
        vs.pack(side=LEFT, fill=Y)
        tv.pack(side=RIGHT, fill=BOTH, expand=True)
        tv.bind("<Double-1>", lambda _e: self._remind())
        self._tv = tv
        self._fill()

        actions = ttk.Frame(self, style="Toolbar.TFrame", padding=(16, 0, 16, 14))
        actions.pack(fill=X)
        _cbtn(actions, "📱  تذكير المحدَّد", self._remind, "primary").pack(
            side=RIGHT)
        _cbtn(actions, "💵  سجّل دفعة", self._record_payment, "act").pack(
            side=RIGHT, padx=(8, 0))
        _cbtn(actions, "⤼  تأجيل", self._skip).pack(side=RIGHT, padx=(8, 0))
        _cbtn(actions, "⏭  التالي", self._next_pending).pack(
            side=RIGHT, padx=(8, 0))
        _cbtn(actions, "إغلاق", self.destroy).pack(side=LEFT)
        self._select_index(0)

    def _fill(self) -> None:
        self._tv.delete(*self._tv.get_children())
        self._iids = []
        settings = self.ctx.settings
        for i, r in enumerate(self.records):
            last = umrah.last_reminded(settings, r)
            last_txt = "اليوم" if last == self._today else (last or "—")
            iid = self._tv.insert("", "end", values=[
                G.rtl(getattr(r, "full_name_ar", "") or "—"),
                G.rtl(self._names.get(getattr(r, self.ctx.group_attr, ""), "—")),
                G.rtl(f"{format_amount(assistant._rem(r))} AED"),
                getattr(r, "phone", "") or "—",
                G.rtl(last_txt),
                G.rtl(self._MARK[self.state[i]]),
            ], tags=(self.state[i],) if self.state[i] != "pending" else ())
            self._iids.append(iid)
        done = self.state.count("done")
        self._prog.configure(text=G.rtl(f"ذُكِّر {done} من {len(self.records)}"))
        outstanding = sum(max(assistant._rem(r), 0) for r in self.records)
        remaining_cnt = sum(1 for r in self.records if assistant._rem(r) > 0.5)
        self._band.configure(text=G.rtl(
            f"{remaining_cnt} {self.ctx.n_acc} متأخّراً · إجمالي المتبقّي "
            f"{format_amount(outstanding)} AED"))

    def _sel_index(self):
        sel = self._tv.selection()
        return self._iids.index(sel[0]) if sel and sel[0] in self._iids else None

    def _select_index(self, i: int) -> None:
        if 0 <= i < len(self._iids):
            self._tv.selection_set(self._iids[i])
            self._tv.see(self._iids[i])

    def _remind(self) -> None:
        i = self._sel_index()
        if i is None:
            messagebox.showinfo("متابعة التحصيل",
                                f"اختر {self.ctx.n_acc} من القائمة.", parent=self)
            return
        rec = self.records[i]
        prog = self._names.get(getattr(rec, self.ctx.group_attr, ""), "")
        link = assistant.due_wa_link(rec, prog, self._company, self._cc)
        if not link:
            messagebox.showwarning(
                "متابعة التحصيل",
                f"لا يوجد رقم صالح لـ«{getattr(rec, 'full_name_ar', '')}».",
                parent=self)
            return
        try:
            G.open_in_viewer(link)
        except OSError as exc:
            messagebox.showerror("متابعة التحصيل", str(exc), parent=self)
            return
        self.state[i] = "done"
        umrah.set_reminded(self.ctx.settings, rec, self._today)   # سجلّ دائم
        try:
            save_settings(self.ctx.settings)
        except OSError:
            pass
        self._fill()
        self._next_pending()

    def _record_payment(self) -> None:
        """يسجّل دفعةً للمعتمر المحدَّد فيُغلق دينه ويُحدَّث الكشف الرئيسي."""
        i = self._sel_index()
        if i is None:
            messagebox.showinfo("تسجيل دفعة",
                                f"اختر {self.ctx.n_acc} من القائمة.", parent=self)
            return
        rec = self.records[i]
        rem = assistant._rem(rec)
        if rem <= 0.5:
            messagebox.showinfo("تسجيل دفعة",
                                f"هذا {self.ctx.n_def} سدّد بالكامل.", parent=self)
            return
        dlg = Toplevel(self)
        dlg.title("تسجيل دفعة")
        dlg.configure(bg=G.BG)
        dlg.resizable(False, False)
        dlg.transient(self)
        frm = ttk.Frame(dlg, style="Toolbar.TFrame", padding=18)
        frm.pack(fill=BOTH, expand=True)
        ttk.Label(frm, text=G.rtl(getattr(rec, "full_name_ar", "") or "—"),
                  font=(G._FSB, 13), foreground=G.TEXT,
                  background=G.BG).pack(anchor="e")
        ttk.Label(frm, text=G.rtl(f"المتبقّي: {format_amount(rem)} AED"),
                  font=(G._FUI, 11), foreground=G.DANGER if hasattr(G, "DANGER")
                  else "#B23A3A", background=G.BG).pack(anchor="e", pady=(2, 10))
        row = ttk.Frame(frm, style="Toolbar.TFrame")
        row.pack(fill=X)
        var = StringVar(value=format_amount(rem))
        ent = ttk.Entry(row, textvariable=var, font=(G._FUI, 12),
                        justify="right", width=16)
        ent.pack(side=RIGHT)
        ttk.Label(row, text=G.rtl("مبلغ الدفعة:"), font=(G._FUI, 10),
                  foreground=G.MUTED, background=G.BG).pack(side=RIGHT, padx=(0, 8))
        G.install_entry_editing(ent)
        ent.focus_set()
        ent.select_range(0, "end")

        def commit(full=False):
            amt = rem if full else parse_amount(var.get())
            if not amt or amt <= 0:
                messagebox.showwarning("مبلغ غير صالح",
                                       "أدخل مبلغ الدفعة بالأرقام.", parent=dlg)
                return
            if not isinstance(getattr(rec, "payments", None), list):
                rec.payments = []
            # حفظ الرصيد المدفوع سابقاً كأول قيد كي لا يضيع عند اعتماد السجلّ
            prior = parse_amount(getattr(rec, "paid_amount", "")) or 0
            if not rec.payments and prior > 0:
                rec.payments.append({"date": "", "amount": format_amount(prior),
                                     "method": "", "note": "رصيد سابق"})
            rec.payments.append({"date": self._today,
                                 "amount": format_amount(amt),
                                 "method": "", "note": "تحصيل بعد تذكير"})
            rec.paid_amount = format_amount(payment_total(rec))
            self.ctx.save()
            try:
                self.ctx.reload()
            except Exception:
                pass
            if assistant._rem(rec) <= 0.5:
                self.state[i] = "paid"
            self._fill()
            self._select_index(i)
            dlg.destroy()

        btns = ttk.Frame(frm, style="Toolbar.TFrame")
        btns.pack(fill=X, pady=(14, 0))
        _cbtn(btns, "💵  سدّد كامل المتبقّي",
              lambda: commit(full=True), "primary").pack(side=RIGHT)
        _cbtn(btns, "تسجيل", lambda: commit(False), "act").pack(
            side=RIGHT, padx=(8, 0))
        _cbtn(btns, "إلغاء", dlg.destroy).pack(side=LEFT)
        ent.bind("<Return>", lambda _e: commit(False))
        dlg.grab_set()

    def _skip(self) -> None:
        i = self._sel_index()
        if i is None:
            return
        if self.state[i] != "done":
            self.state[i] = "skip"
        self._fill()
        self._next_pending()

    def _next_pending(self) -> None:
        start = self._sel_index()
        n = len(self.records)
        if start is None:
            start = -1
        for step in range(1, n + 1):
            j = (start + step) % n
            if self.state[j] == "pending":
                self._select_index(j)
                return
        # لا يوجد متبقٍّ
        if all(s != "pending" for s in self.state):
            done = self.state.count("done")
            messagebox.showinfo(
                "اكتملت المتابعة",
                f"تمّت متابعة الجميع — ذُكِّر {done} من {n}.", parent=self)


class TransportRequestsListWindow(Toplevel):
    """قائمة طلبات المواصلات المحفوظة: فتح/تعديل، معاينة، حذف."""

    def __init__(self, parent, app) -> None:
        super().__init__(parent)
        self.app = app
        self.title("طلبات المواصلات المحفوظة")
        self.configure(bg=G.BG)
        self.geometry("760x430")
        self.transient(parent)
        outer = ttk.Frame(self, padding=8)
        outer.pack(fill=BOTH, expand=True)
        cols = ("number", "recipient", "guest", "date")
        heads = {"number": "الرقم", "recipient": "الجهة", "guest": "الضيف",
                 "date": "التاريخ"}
        widths = {"number": 100, "recipient": 260, "guest": 220, "date": 110}
        self.tree = ttk.Treeview(outer, columns=cols, show="headings",
                                 selectmode="browse")
        for c in cols:
            self.tree.heading(c, text=heads[c])
            self.tree.column(c, width=widths[c],
                             anchor="e" if c in ("recipient", "guest")
                             else "center")
        vs = ttk.Scrollbar(outer, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        vs.pack(side=RIGHT, fill="y")
        bar = ttk.Frame(self, padding=(8, 6))
        bar.pack(fill=X)
        for text, cmd in (("✏ فتح/تعديل", self.open_sel),
                          ("👁 معاينة", self.preview_sel),
                          ("🗑 حذف", self.delete_sel), ("↻ تحديث", self.refresh)):
            ttk.Button(bar, text=G.rtl(text), command=cmd).pack(side=RIGHT,
                                                                padx=3)
        ttk.Button(bar, text="إغلاق", command=self.destroy).pack(side=LEFT,
                                                                 padx=3)
        self.tree.bind("<Double-1>", lambda e: self.open_sel())
        self._items: list = []
        self.refresh()
        try:
            G.enable_minmax(self)
        except Exception:
            pass
        self.grab_set()

    def refresh(self) -> None:
        self._items = umrah.load_transport_requests(self.app._settings)
        self.tree.delete(*self.tree.get_children())
        for i, q in enumerate(self._items):
            self.tree.insert("", "end", iid=str(i), values=(
                q.get("number", ""), q.get("recipient", "") or "—",
                q.get("guest_ar", "") or "—", q.get("date", "") or "—"))

    def _sel(self):
        s = self.tree.selection()
        return self._items[int(s[0])] if s else None

    def _company(self):
        co = self.app._settings.get("company")
        return co if isinstance(co, dict) else None

    def open_sel(self) -> None:
        q = self._sel()
        if q is None:
            messagebox.showinfo("الطلبات", "اختر طلباً أولاً.", parent=self)
            return
        TransportRequestEditorDialog(self, PassportData(), None, dict(q),
                                     company=self._company(), app=self.app,
                                     on_saved=self.refresh)

    def preview_sel(self) -> None:
        q = self._sel()
        if q is None:
            return
        G.open_preview(
            self,
            lambda path: export_umrah_transport_request_pdf(
                PassportData(), path, data=q, company=self._company()),
            f"مواصلات {q.get('number', '')}", "pdf")

    def delete_sel(self) -> None:
        q = self._sel()
        if q is None:
            return
        if not messagebox.askyesno("حذف",
                                   f"حذف الطلب {q.get('number', '')}؟",
                                   parent=self):
            return
        umrah.delete_transport_request(self.app._settings, q.get("number", ""))
        try:
            save_settings(self.app._settings)
        except OSError:
            pass
        self.refresh()


class VouchersListWindow(Toplevel):
    """قائمة فاوتشرات الفنادق المحفوظة: فتح/تعديل، معاينة، حذف."""

    def __init__(self, parent, app) -> None:
        super().__init__(parent)
        self.app = app
        self.title("الفاوتشرات المحفوظة")
        self.configure(bg=G.BG)
        self.geometry("760x430")
        self.transient(parent)
        outer = ttk.Frame(self, padding=8)
        outer.pack(fill=BOTH, expand=True)
        cols = ("number", "guest", "booking", "date")
        heads = {"number": "الرقم", "guest": "الضيف", "booking": "رقم الحجز",
                 "date": "التاريخ"}
        widths = {"number": 100, "guest": 260, "booking": 140, "date": 110}
        self.tree = ttk.Treeview(outer, columns=cols, show="headings",
                                 selectmode="browse")
        for c in cols:
            self.tree.heading(c, text=heads[c])
            self.tree.column(c, width=widths[c],
                             anchor="e" if c == "guest" else "center")
        vs = ttk.Scrollbar(outer, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        vs.pack(side=RIGHT, fill="y")
        bar = ttk.Frame(self, padding=(8, 6))
        bar.pack(fill=X)
        for text, cmd in (("✏ فتح/تعديل", self.open_sel),
                          ("👁 معاينة", self.preview_sel),
                          ("🗑 حذف", self.delete_sel), ("↻ تحديث", self.refresh)):
            ttk.Button(bar, text=G.rtl(text), command=cmd).pack(side=RIGHT,
                                                                padx=3)
        ttk.Button(bar, text="إغلاق", command=self.destroy).pack(side=LEFT,
                                                                 padx=3)
        self.tree.bind("<Double-1>", lambda e: self.open_sel())
        self._items: list = []
        self.refresh()
        try:
            G.enable_minmax(self)
        except Exception:
            pass
        self.grab_set()

    def refresh(self) -> None:
        self._items = umrah.load_vouchers(self.app._settings)
        self.tree.delete(*self.tree.get_children())
        for i, v in enumerate(self._items):
            self.tree.insert("", "end", iid=str(i), values=(
                v.get("number", ""),
                v.get("guest_ar", "") or v.get("guest_en", "") or "—",
                v.get("booking_no", "") or "—", v.get("date", "") or "—"))

    def _sel(self):
        s = self.tree.selection()
        return self._items[int(s[0])] if s else None

    def _company(self):
        co = self.app._settings.get("company")
        return co if isinstance(co, dict) else None

    def open_sel(self) -> None:
        v = self._sel()
        if v is None:
            messagebox.showinfo("الفاوتشرات", "اختر فاوتشراً أولاً.", parent=self)
            return
        VoucherEditorDialog(self, PassportData(), None, dict(v),
                            company=self._company(), app=self.app,
                            on_saved=self.refresh)

    def preview_sel(self) -> None:
        v = self._sel()
        if v is None:
            return
        G.open_preview(
            self,
            lambda path: export_umrah_voucher_pdf(
                PassportData(), path, data=v, company=self._company()),
            f"فاوتشر {v.get('number', '')}", "pdf")

    def delete_sel(self) -> None:
        v = self._sel()
        if v is None:
            return
        if not messagebox.askyesno("حذف",
                                   f"حذف الفاوتشر {v.get('number', '')}؟",
                                   parent=self):
            return
        umrah.delete_voucher(self.app._settings, v.get("number", ""))
        try:
            save_settings(self.app._settings)
        except OSError:
            pass
        self.refresh()


class RoomingWindow(Toplevel):
    """التسكين: توزيع معتمري البرنامج على غرف مكة والمدينة (تبويب لكل مدينة)."""

    def __init__(self, app: UmrahApp, trip) -> None:
        super().__init__(app.root)
        self.app = app
        self.trip = trip
        self.session = app.session
        self.title(f"التسكين — {trip.name or trip.code}")
        self.configure(bg=G.BG)
        self.geometry("980x620")
        self.minsize(760, 460)
        self.transient(app.root)

        outer = ttk.Frame(self, padding=8)
        outer.pack(fill=BOTH, expand=True)
        nb = ttk.Notebook(outer)
        nb.pack(fill=BOTH, expand=True)

        self._cities: dict = {}      # key -> (label, room_field, hotel, nights)
        self._trees: dict = {}
        self._sum: dict = {}
        for (key, label, room_field, hotel_field, nights_field,
             rooms_field) in umrah.CITIES:
            hotel = str(getattr(trip, hotel_field, "") or "")
            nights = str(getattr(trip, nights_field, "") or "")
            rooms = str(getattr(trip, rooms_field, "") or "")
            self._cities[key] = (label, room_field, hotel, nights, rooms)
            nb.add(self._build_tab(nb, key), text=label)

        self._seed_from_room_number()
        self.grab_set()
        G.enable_minmax(self)
        for key in self._cities:
            self._reload(key)

    def _seed_from_room_number(self) -> None:
        """يأخذ رقم الغرفة من «الإقامة والحجز» إن وُجد ولم يُحدَّد لهذه المدينة."""
        seeded = False
        for _k, _l, room_field, *_rest in umrah.CITIES:
            for r in self._pilgrims():
                if (not str(getattr(r, room_field, "") or "").strip()
                        and str(r.room_number or "").strip()):
                    setattr(r, room_field, str(r.room_number).strip())
                    seeded = True
        if seeded:
            self.app.save()

    def _prog_label(self) -> str:
        return (f"{self.trip.code} — {self.trip.name}"
                if self.trip.name else self.trip.code)

    def _pilgrims(self) -> list:
        return umrah.trip_pilgrims(self.app.records, self.trip.code)

    def _build_tab(self, nb, key: str) -> ttk.Frame:
        label, room_field, hotel, nights, _rooms = self._cities[key]
        f = ttk.Frame(nb, padding=8)
        head = ttk.Frame(f, style="Toolbar.TFrame")
        head.pack(fill=X)
        cap = f"🏨 {label} — {hotel or '—'}"
        if nights:
            cap += f"  ({nights} ليالٍ)"
        ttk.Label(head, text=cap, font=(G._FSB, 13), foreground=G.TEXT,
                  background=G.BG).pack(side=RIGHT)
        sumlbl = ttk.Label(head, text="", font=(G._FUI, 10), foreground=G.BRONZE,
                           background=G.BG)
        sumlbl.pack(side=LEFT)
        self._sum[key] = sumlbl

        bar = ttk.Frame(f, style="Panel.TFrame", padding=(8, 6))
        bar.pack(fill=X, pady=(6, 6))
        ttk.Button(bar, text=G.rtl("🎲 توزيع تلقائي"), style="Primary.TButton",
                   command=lambda k=key: self._auto(k)).pack(side=RIGHT, padx=3)
        ttk.Button(bar, text=G.rtl("🧹 مسح التوزيع"), style="Ghost.TButton",
                   command=lambda k=key: self._clear(k)).pack(side=RIGHT, padx=3)
        ttk.Button(bar, text=G.rtl("👁 معاينة كشف الغرف"), style="Ghost.TButton",
                   command=lambda k=key: self._preview(k)).pack(side=LEFT, padx=3)
        ttk.Label(bar, text=G.rtl("نقرة مزدوجة لتعيين رقم الغرفة"),
                  font=(G._FUI, 9), foreground=G.MUTED,
                  background=G.BG).pack(side=LEFT, padx=10)

        cols = ("n", "name", "passport", "room_type", "room")
        heads = {"n": "م", "name": "الاسم", "passport": "رقم الجواز",
                 "room_type": "نوع الغرفة", "room": "رقم الغرفة"}
        widths = {"n": 40, "name": 250, "passport": 130, "room_type": 100,
                  "room": 100}
        tree = ttk.Treeview(f, columns=cols, show="headings")
        for c in cols:
            tree.heading(c, text=heads[c])
            tree.column(c, width=widths[c], anchor="e" if c == "name" else "center")
        tree.pack(fill=BOTH, expand=True)
        tree.tag_configure("odd", background=G.PANEL)
        tree.bind("<Double-1>", lambda _e, k=key: self._edit_room(k))
        self._trees[key] = tree
        return f

    def _available(self, key: str) -> int:
        """عدد الغرف المتاحة في فندق هذه المدينة (0 = غير محدَّد)."""
        try:
            return int(float(str(self._cities[key][4] or "").strip() or 0))
        except ValueError:
            return 0

    def _reload(self, key: str) -> None:
        label, room_field, _hotel, _nights, _rooms = self._cities[key]
        tree = self._trees[key]
        tree.delete(*tree.get_children())
        recs = self._pilgrims()
        for i, r in enumerate(recs):
            tree.insert("", END, iid=str(i), values=(
                i + 1, r.full_name_ar or r.full_name_en or "—",
                r.passport_number or "—", r.room_type or "—",
                getattr(r, room_field, "") or "—"),
                tags=("odd",) if i % 2 else ())
        rooms, un = umrah.rooming_rooms(recs, room_field)
        avail = self._available(key)
        used = f"{len(rooms)} من {avail}" if avail else str(len(rooms))
        self._sum[key].configure(
            text=f"الغرف: {used}   ·   بلا غرفة: {len(un)}   ·   "
                 f"العدد: {len(recs)}")

    def _auto(self, key: str) -> None:
        room_field = self._cities[key][1]
        avail = self._available(key)
        n, overflow = umrah.auto_assign_rooms(self._pilgrims(), room_field,
                                              max_rooms=avail)
        self.app.save()
        self._reload(key)
        msg = f"وُزّع المعتمرون على {n} غرفة حسب نوع الغرفة."
        if overflow:
            msg += (f"\n\n⛔ لا يمكن تجاوز عدد الغرف المتاحة ({avail}). بقي "
                    f"{overflow} معتمراً بلا غرفة — قلّل البيع أو زد الغرف.")
        messagebox.showinfo("توزيع تلقائي", msg, parent=self)

    def _clear(self, key: str) -> None:
        room_field = self._cities[key][1]
        if not messagebox.askyesno("مسح التوزيع",
                                   "مسح أرقام غرف هذه المدينة لكل المعتمرين؟",
                                   parent=self):
            return
        for r in self._pilgrims():
            setattr(r, room_field, "")
        self.app.save()
        self._reload(key)

    def _edit_room(self, key: str) -> None:
        room_field = self._cities[key][1]
        tree = self._trees[key]
        sel = tree.selection()
        if not sel:
            return
        recs = self._pilgrims()
        idx = int(sel[0])
        if not (0 <= idx < len(recs)):
            return
        rec = recs[idx]
        ed = Toplevel(self)
        ed.title("رقم الغرفة")
        ed.configure(bg=G.BG)
        ed.transient(self)
        ed.resizable(True, True)
        ed.grab_set()
        G.enable_minmax(ed)
        frm = ttk.Frame(ed, padding=16)
        frm.pack()
        who = rec.full_name_ar or rec.full_name_en or rec.passport_number or "—"
        ttk.Label(frm, text=f"رقم غرفة «{who}»", font=(G._FUI, 10),
                  foreground=G.TEXT).pack(anchor="e")
        v = StringVar(value=getattr(rec, room_field, "") or "")
        entry = ttk.Entry(frm, textvariable=v, width=18, justify="center")
        entry.pack(pady=8)
        entry.focus_set()

        def _save():
            newval = v.get().strip()
            avail = self._available(key)
            if avail and newval:
                # لا يُسمح بإنشاء غرفة جديدة تتجاوز عدد الغرف المتاحة
                current = {str(getattr(r, room_field, "") or "").strip()
                           for r in self._pilgrims()
                           if str(getattr(r, room_field, "") or "").strip()}
                current.discard(str(getattr(rec, room_field, "") or "").strip())
                if newval not in current and len(current) + 1 > avail:
                    messagebox.showwarning(
                        "تجاوز السعة",
                        f"عدد الغرف المتاحة في الفندق {avail} فقط. "
                        "لا يمكن إضافة غرفة جديدة.", parent=ed)
                    return
            setattr(rec, room_field, newval)
            self.app.save()
            ed.destroy()
            self._reload(key)

        row = ttk.Frame(frm)
        row.pack()
        ttk.Button(row, text=G.rtl("💾 حفظ"), style="Primary.TButton",
                   command=_save).pack(side=RIGHT, padx=3)
        ttk.Button(row, text="إلغاء", style="Ghost.TButton",
                   command=ed.destroy).pack(side=LEFT, padx=3)
        ed.bind("<Return>", lambda _e: _save())
        ed.bind("<Escape>", lambda _e: ed.destroy())
        _center(ed, self)

    def _preview(self, key: str) -> None:
        label, room_field, hotel, nights, _rooms = self._cities[key]
        recs = self._pilgrims()
        if not recs:
            messagebox.showinfo("معاينة", "لا معتمرين.", parent=self)
            return
        G.open_preview(
            self,
            lambda p: export_umrah_rooming_pdf(
                recs, p, city_label=label, hotel=hotel, nights=nights,
                program_name=self._prog_label(), room_field=room_field),
            f"تسكين {label} {self.trip.code}", "pdf")


class TransportWindow(Toplevel):
    """المواصلات: توزيع معتمري البرنامج على المركبات (فورد ≤ شخصين، جيمس حتى ٦)."""

    def __init__(self, app: UmrahApp, trip) -> None:
        super().__init__(app.root)
        self.app = app
        self.trip = trip
        self.session = app.session
        self.title(f"المواصلات — {trip.name or trip.code}")
        self.configure(bg=G.BG)
        self.geometry("900x600")
        self.minsize(740, 460)
        self.transient(app.root)

        head = ttk.Frame(self, style="Toolbar.TFrame", padding=(12, 10, 12, 4))
        head.pack(fill=X)
        ttk.Label(head, text=f"🚐 مواصلات «{trip.name or trip.code}»",
                  font=(G._FSB, 14), foreground=G.TEXT,
                  background=G.BG).pack(side=RIGHT)
        self._sum = ttk.Label(head, text="", font=(G._FUI, 10),
                              foreground=G.BRONZE, background=G.BG)
        self._sum.pack(side=LEFT)

        bar = ttk.Frame(self, style="Panel.TFrame", padding=(12, 8))
        bar.pack(fill=X)
        ttk.Button(bar, text=G.rtl("🎲 توزيع تلقائي"), style="Primary.TButton",
                   command=self._auto).pack(side=RIGHT, padx=3)
        ttk.Button(bar, text=G.rtl("🧹 مسح التوزيع"), style="Ghost.TButton",
                   command=self._clear).pack(side=RIGHT, padx=3)
        ttk.Button(bar, text=G.rtl("👁 معاينة كشف المواصلات"), style="Ghost.TButton",
                   command=self._preview).pack(side=LEFT, padx=3)
        ttk.Label(bar, text=G.rtl("نقرة مزدوجة لتعيين المركبة"), font=(G._FUI, 9),
                  foreground=G.MUTED, background=G.BG).pack(side=LEFT, padx=10)

        wrap = ttk.Frame(self, style="Toolbar.TFrame", padding=(12, 4, 12, 12))
        wrap.pack(fill=BOTH, expand=True)
        cols = ("n", "name", "passport", "phone", "vehicle")
        heads = {"n": "م", "name": "الاسم", "passport": "رقم الجواز",
                 "phone": "الهاتف", "vehicle": "المركبة"}
        widths = {"n": 40, "name": 260, "passport": 130, "phone": 140,
                  "vehicle": 130}
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings")
        for c in cols:
            self.tree.heading(c, text=heads[c])
            self.tree.column(c, width=widths[c], anchor="e" if c == "name"
                             else "center")
        self.tree.pack(fill=BOTH, expand=True)
        self.tree.tag_configure("odd", background=G.PANEL)
        self.tree.bind("<Double-1>", lambda _e: self._edit())

        self.grab_set()
        G.enable_minmax(self)
        self._reload()

    def _prog_label(self) -> str:
        return (f"{self.trip.code} — {self.trip.name}"
                if self.trip.name else self.trip.code)

    def _pilgrims(self) -> list:
        return umrah.trip_pilgrims(self.app.records, self.trip.code)

    def _reload(self) -> None:
        self.tree.delete(*self.tree.get_children())
        recs = self._pilgrims()
        for i, r in enumerate(recs):
            self.tree.insert("", END, iid=str(i), values=(
                i + 1, r.full_name_ar or r.full_name_en or "—",
                r.passport_number or "—", r.phone or "—", r.vehicle or "—"),
                tags=("odd",) if i % 2 else ())
        groups, un = umrah.rooming_rooms(recs, "vehicle")
        self._sum.configure(
            text=f"المركبات: {len(groups)}   ·   بلا مركبة: {len(un)}   ·   "
                 f"العدد: {len(recs)}")

    def _auto(self) -> None:
        n = umrah.auto_assign_vehicles(self._pilgrims())
        self.app.save()
        self._reload()
        messagebox.showinfo("توزيع تلقائي",
                            f"وُزّع المعتمرون على {n} مركبة.", parent=self)

    def _clear(self) -> None:
        if not messagebox.askyesno("مسح التوزيع",
                                   "مسح تخصيص المركبات لكل المعتمرين؟",
                                   parent=self):
            return
        for r in self._pilgrims():
            r.vehicle = ""
        self.app.save()
        self._reload()

    def _edit(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        recs = self._pilgrims()
        idx = int(sel[0])
        if not (0 <= idx < len(recs)):
            return
        rec = recs[idx]
        ed = Toplevel(self)
        ed.title("المركبة")
        ed.configure(bg=G.BG)
        ed.transient(self)
        ed.resizable(True, True)
        ed.grab_set()
        G.enable_minmax(ed)
        frm = ttk.Frame(ed, padding=16)
        frm.pack()
        who = rec.full_name_ar or rec.full_name_en or rec.passport_number or "—"
        ttk.Label(frm, text=f"مركبة «{who}»", font=(G._FUI, 10),
                  foreground=G.TEXT).pack(anchor="e")
        v = StringVar(value=rec.vehicle or "")
        entry = ttk.Entry(frm, textvariable=v, width=22, justify="center")
        entry.pack(pady=8)
        entry.focus_set()

        def _save():
            rec.vehicle = v.get().strip()
            self.app.save()
            ed.destroy()
            self._reload()

        row = ttk.Frame(frm)
        row.pack()
        ttk.Button(row, text=G.rtl("💾 حفظ"), style="Primary.TButton",
                   command=_save).pack(side=RIGHT, padx=3)
        ttk.Button(row, text="إلغاء", style="Ghost.TButton",
                   command=ed.destroy).pack(side=LEFT, padx=3)
        ed.bind("<Return>", lambda _e: _save())
        ed.bind("<Escape>", lambda _e: ed.destroy())
        _center(ed, self)

    def _preview(self) -> None:
        recs = self._pilgrims()
        if not recs:
            messagebox.showinfo("معاينة", "لا معتمرين.", parent=self)
            return
        G.open_preview(
            self,
            lambda p: export_umrah_transport_pdf(
                recs, p, program_name=self._prog_label(),
                transport_pnr=str(getattr(self.trip, "transport_pnr", "") or "")),
            f"مواصلات {self.trip.code}", "pdf")

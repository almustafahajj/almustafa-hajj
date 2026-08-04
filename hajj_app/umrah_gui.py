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
from datetime import date
from pathlib import Path
from tkinter import (
    BOTH, BooleanVar, Canvas, END, LEFT, Menu, RIGHT, StringVar, Text, Toplevel,
    X, Y, filedialog, messagebox, ttk,
)

from . import app_mode, images as imgmod, umrah
from . import gui as G
from .excel_io import export_umrah_excel
from .fields import format_amount, parse_amount
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
    VOUCHER_CAR_TYPES, VOUCHER_STAY_HEADS, VOUCHER_TRANSPORT_HEADS,
    VOUCHER_VIEW_OPTIONS, build_quotation_data, build_transport_request_data,
    build_voucher_data,
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

        root.title(app_mode.label("window_title"))
        geom = self._ui.get("geometry")
        root.geometry(geom if isinstance(geom, str) and "x" in geom else "1180x720")
        root.minsize(900, 560)
        root.configure(bg=G.BG)
        try:
            G.apply_window_icon(root)
        except Exception:
            pass
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

        self._build_header()
        self._build_toolbar()
        self._build_table()
        self._reload()

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
        ttk.Button(bar, text=G.rtl(f"🕋  التبديل إلى {other}"),
                   style="Ghost.TButton",
                   command=self.switch_mode).pack(side=LEFT, padx=(0, 8))
        if self.session is not None:
            info = ttk.Frame(bar, style="Toolbar.TFrame")
            info.pack(side=LEFT)
            ttk.Label(info,
                      text=f"👤  {self.session.username}  ·  {self.session.role_label}",
                      font=(G._FSB, 10), foreground=G.TEXT,
                      background=G.BG).pack(anchor="w")
            ttk.Label(info, text="🔒 البيانات مشفّرة", font=(G._FUI, 9),
                      foreground=G.BRONZE, background=G.BG).pack(anchor="w")
            ttk.Button(bar, text=G.rtl("🚪  تسجيل الخروج"), style="Ghost.TButton",
                       command=self.do_logout).pack(side=LEFT, padx=(0, 8))

    # ---- شريط الأدوات ----
    #  واجهة مبسّطة: زران رئيسيان دائما الظهور + قوائم منسدلة تجمع بقية الأدوات
    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self.root, style="Panel.TFrame", padding=(16, 10, 16, 12))
        bar.pack(fill=X)
        self._menus: list = []
        # الأكثر استخداماً — أزرار مباشرة
        ttk.Button(bar, text=G.rtl("➕  برنامج جديد"), style="Primary.TButton",
                   command=self.new_trip).pack(side=RIGHT, padx=3)
        ttk.Button(bar, text=G.rtl("👤  المعتمرون"), style="Act.TButton",
                   command=self.open_pilgrims).pack(side=RIGHT, padx=3)
        # قوائم منسدلة تجمع الأدوات ذات الصلة لتخفيف الازدحام
        self._menu_button(bar, "✏️  البرنامج", (
            ("✏️  تعديل البرنامج", self.edit_trip),
            ("🗑  حذف البرنامج", self.delete_trip),
        ))
        self._menu_button(bar, "💰  التسعير والعروض", (
            ("📋  عروض الأسعار المحفوظة", self.open_quotes),
            ("💲  عرض سعر يدوي جديد", self.new_manual_quotation),
            ("📁  العروض اليدوية", self.open_manual_quotes),
            None,
            ("🧮  مسعّر المجموعات", self.open_group_pricer),
            ("🗂  التسعيرات المحفوظة", self.open_pricings),
        ))
        self._menu_button(bar, "🏨  مستندات", (
            ("🏨  فاوتشر فندق يدوي", self.new_manual_voucher),
        ))
        self._menu_button(bar, "🚖  الطلبات", (
            ("🚖  طلب حجز مواصلات", self.new_transport_request),
            ("🗂  الطلبات المحفوظة", self.open_transport_requests),
        ))

    def _menu_button(self, bar, label, items):
        """زر بقائمة منسدلة (Menubutton + Menu) بعناصر (نص، أمر) أو None لفاصل."""
        mb = ttk.Menubutton(bar, text=G.rtl(label), style="Ghost.TMenubutton",
                            direction="below")
        menu = Menu(mb, tearoff=0, font=(G._FUI, 10))
        for entry in items:
            if entry is None:
                menu.add_separator()
            else:
                text, cmd = entry
                menu.add_command(label=G.rtl(text), command=cmd)
        mb["menu"] = menu
        self._menus.append(menu)          # مرجع يمنع جمع القمامة
        mb.pack(side=RIGHT, padx=3)
        return mb

    # ---- جدول البرامج ----
    def _build_table(self) -> None:
        wrap = ttk.Frame(self.root, style="Toolbar.TFrame", padding=(16, 4, 16, 14))
        wrap.pack(fill=BOTH, expand=True)
        cols = ("code", "name", "depart", "return", "makkah", "madinah",
                "count", "capacity", "remaining")
        heads = {"code": "الرمز", "name": "اسم البرنامج", "depart": "المغادرة",
                 "return": "العودة", "makkah": "فندق مكة",
                 "madinah": "فندق المدينة", "count": "المعتمرون",
                 "capacity": "السعة", "remaining": "المتبقّي"}
        widths = {"code": 56, "name": 200, "depart": 96, "return": 96,
                  "makkah": 150, "madinah": 150, "count": 84, "capacity": 62,
                  "remaining": 96}
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings",
                                 selectmode="browse")
        for c in cols:
            self.tree.heading(c, text=heads[c])
            anchor = "e" if c in ("name", "makkah", "madinah") else "center"
            self.tree.column(c, width=widths[c], anchor=anchor)
        vs = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        vs.pack(side=RIGHT, fill="y")
        self.tree.tag_configure("odd", background=G.PANEL)
        self.tree.bind("<Double-1>", lambda _e: self.open_pilgrims())

        self._empty = ttk.Label(
            self.root, text=G.rtl("لا برامج بعد — ابدأ بـ «➕ برنامج جديد»."),
            font=(G._FUI, 11), foreground=G.MUTED, background=G.BG)

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

    def _reload(self) -> None:
        self.tree.delete(*self.tree.get_children())
        shown = self._season_trips()
        for i, t in enumerate(shown):
            pilgrims = umrah.trip_pilgrims(self.records, t.code)
            try:
                cap = int(float(str(t.capacity or "").strip() or 0))
            except ValueError:
                cap = 0
            seats_left = (cap - len(pilgrims)) if cap else None   # السعة − المعتمرين
            self.tree.insert("", END, iid=t.code, values=(
                t.code, t.name or "—", t.depart_date or "—", t.return_date or "—",
                t.makkah_hotel or "—", t.madinah_hotel or "—",
                len(pilgrims), t.capacity or "—",
                seats_left if seats_left is not None else "—"),
                tags=("odd",) if i % 2 else ())
        if not shown:
            self._empty.pack(pady=8)
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
                            company=co)

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
        for text, cmd, style in (
            ("📷  إضافة بقراءة الجواز", self.add_passport, "Primary.TButton"),
            ("🧮  إضافة حجز (تسعير)", self.add_booking, "Act.TButton"),
            ("➕  إضافة يدوي", self.add_manual, "Ghost.TButton"),
            ("✏️  تعديل", self.edit_selected, "Ghost.TButton"),
            ("🗑  حذف", self.delete_selected, "Ghost.TButton"),
            ("🏨  التسكين", self.open_rooming, "Ghost.TButton"),
            ("🚐  المواصلات", self.open_transport, "Ghost.TButton"),
            ("✈  كشف الطيران", self.open_flights, "Ghost.TButton"),
        ):
            ttk.Button(bar, text=G.rtl(text), style=style,
                       command=cmd).pack(side=RIGHT, padx=3)
        ttk.Button(bar, text=G.rtl("💰  الملخّص المالي"), style="Ghost.TButton",
                   command=self.do_finance).pack(side=LEFT, padx=3)
        ttk.Button(bar, text=G.rtl("🪪  بطاقات العمرة"), style="Ghost.TButton",
                   command=self.do_cards).pack(side=LEFT, padx=3)
        for text, cmd in (("🧾  سند قبض", self.do_receipt),
                          ("🧾  فاتورة", self.do_invoice),
                          ("📜  عقد", self.do_contract),
                          ("💲  عرض سعر", self.do_quotation),
                          ("📋  عروض الأسعار", self.do_quotes_list),
                          ("🏨  فاوتشر الفندق", self.do_voucher),
                          ("🚖  طلب مواصلات", self.do_transport_request)):
            ttk.Button(bar, text=G.rtl(text), style="Ghost.TButton",
                       command=cmd).pack(side=LEFT, padx=3)
        ttk.Button(bar, text=G.rtl("👁  معاينة PDF"), style="Ghost.TButton",
                   command=self.export_pdf).pack(side=LEFT, padx=3)
        ttk.Button(bar, text=G.rtl("📊  تصدير إكسل"), style="Ghost.TButton",
                   command=self.export_excel).pack(side=LEFT, padx=3)

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
                            company=company)

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
                  font=("Segoe UI", 10, "bold")).pack(side=LEFT, expand=True)
        ttk.Button(hdr, text="›", width=2, command=self._next).pack(side=LEFT)
        ttk.Button(hdr, text="»", width=2, command=self._next_year).pack(
            side=LEFT)
        ttk.Button(hdr, text="✕", width=2, command=self.destroy).pack(
            side=LEFT, padx=(4, 0))
        g = ttk.Frame(self, padding=(4, 0, 4, 4))
        g.pack()
        for i, wd in enumerate(("Su", "Mo", "Tu", "We", "Th", "Fr", "Sa")):
            ttk.Label(g, text=wd, width=3, anchor="center",
                      font=("Segoe UI", 8, "bold")).grid(row=0, column=i, padx=1)
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
        ttk.Label(sub, text=label, font=("Segoe UI", 7)).pack()
        var = StringVar(value=str(value or ""))
        ttk.Combobox(sub, textvariable=var, values=list(options), width=width,
                     state="readonly" if readonly else "normal").pack()
        return var

    def _date_cell(self, parent, label, iso, width=9):
        """خلية تاريخ بتقويم منبثق (مع كتابة يدوية)، بعنوان صغير، ضمن صفّ أفقي."""
        sub = ttk.Frame(parent)
        sub.pack(side=RIGHT, padx=2)
        ttk.Label(sub, text=label, font=("Segoe UI", 7)).pack()
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
                 company=None) -> None:
        super().__init__(parent)
        self.parent = parent
        self.rec = rec
        self.trip = trip
        self._program = program
        self._company_dict = company
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
                  font=("Segoe UI", 10, "bold")).pack(side=RIGHT, padx=(0, 6))
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
        ttk.Button(bar, text="إغلاق",
                   command=self.destroy).pack(side=RIGHT, padx=6)

        try:
            G.enable_minmax(self)
        except Exception:
            pass
        self.grab_set()

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
        self.destroy()
        VoucherEditorDialog(parent, rec, trip, data, program=program,
                            company=company)

    def _build_meta(self, data: dict) -> None:
        lf = self._section("البيانات الأساسية")
        # رقم الفاوتشر تسلسلي تلقائي (غير قابل للتعديل)
        ttk.Label(lf, text="رقم الفاوتشر").grid(row=0, column=0, sticky="e",
                                                padx=(8, 4), pady=3)
        ttk.Label(lf, text=self._number, foreground=G.ACCENT,
                  font=("Segoe UI", 10, "bold")).grid(row=0, column=1,
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
        lf = self._section("الإقامات (المدينة / الفندق / الغرفة / الإطلالة / "
                           "الدخول / المغادرة / الليالي / الوجبات)")
        self._stay_head = lf
        self._stay_widths = [10, 15, 9, 8, 10, 10, 5, 11]
        hdr = ttk.Frame(lf)
        hdr.pack(fill=X)
        for w, h in zip(self._stay_widths, VOUCHER_STAY_HEADS):
            ttk.Label(hdr, text=h, width=w, anchor="center",
                      font=("Segoe UI", 8, "bold")).pack(side=RIGHT, padx=1)
        ttk.Label(hdr, text="", width=5).pack(side=RIGHT)
        self._stay_box = ttk.Frame(lf)
        self._stay_box.pack(fill=X)
        for row in data.get("stays", []):
            self._add_stay_row(list(row))
        ttk.Button(lf, text="＋ إضافة صف",
                   command=lambda: self._add_stay_row()).pack(anchor="e",
                                                              pady=(4, 0))

    def _add_stay_row(self, values=None) -> None:
        values = list(values or []) + [""] * 8
        fr = ttk.Frame(self._stay_box)
        fr.pack(fill=X, pady=1)
        cells = []
        for i, w in enumerate(self._stay_widths):
            var = StringVar(value=str(values[i] or ""))
            if i == 3:      # الإطلالة → قائمة منسدلة
                ttk.Combobox(fr, textvariable=var, width=w - 1,
                             state="readonly", justify="center",
                             values=list(VOUCHER_VIEW_OPTIONS)).pack(
                    side=RIGHT, padx=1)
            else:
                ttk.Entry(fr, textvariable=var, width=w, justify="right").pack(
                    side=RIGHT, padx=1)
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
                      font=("Segoe UI", 8, "bold")).pack(side=RIGHT, padx=1)
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
                  font=("Segoe UI", 10, "bold")).grid(row=0, column=1,
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
        ttk.Label(sub, text="خط السير", font=("Segoe UI", 7)).pack()
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

    def _save(self):
        if self._app is None:
            messagebox.showinfo("حفظ", "تعذّر تحديد النظام للحفظ.", parent=self)
            return
        data = self._collect()
        umrah.save_transport_request(self._app._settings, data)
        try:
            save_settings(self._app._settings)
        except OSError:
            pass
        messagebox.showinfo("الطلبات", f"تم حفظ الطلب {self._number}.",
                            parent=self)
        if callable(self._on_saved):
            self._on_saved()

    def _preview(self):
        data = self._collect()
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
                  font=("Segoe UI", 10, "bold")).pack(side=RIGHT, padx=(0, 6))
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

    def _cell(self, parent, label, value, options, width, readonly=True):
        """خلية بعنوان صغير فوق قائمة منسدلة، ضمن صفّ أفقي."""
        sub = ttk.Frame(parent)
        sub.pack(side=RIGHT, padx=2)
        ttk.Label(sub, text=label, font=("Segoe UI", 7)).pack()
        var = StringVar(value=str(value or ""))
        ttk.Combobox(sub, textvariable=var, values=list(options), width=width,
                     state="readonly" if readonly else "normal").pack()
        return var

    def _date_cell(self, parent, label, iso, width=9):
        """خلية تاريخ بتقويم منبثق، بعنوان صغير، ضمن صفّ أفقي."""
        sub = ttk.Frame(parent)
        sub.pack(side=RIGHT, padx=2)
        ttk.Label(sub, text=label, font=("Segoe UI", 7)).pack()
        dp = DatePicker(sub, iso=iso, width=width)
        dp.pack()
        return dp

    # ---- البيانات الأساسية ----
    def _build_head(self, data):
        lf = self._section("البيانات الأساسية")
        ttk.Label(lf, text="رقم العرض").grid(row=0, column=0, sticky="e",
                                             padx=(8, 4), pady=3)
        ttk.Label(lf, text=self._number, foreground=G.ACCENT,
                  font=("Segoe UI", 10, "bold")).grid(row=0, column=1,
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
                  font=("Segoe UI", 10)).pack(side=RIGHT)
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

    def _enable_drop(self, widget):
        """يفعّل السحب والإفلات على ``widget`` عبر tkdnd (مستقرّ مع Tkinter)."""
        try:
            from tkinterdnd2 import DND_FILES, TkinterDnD
            TkinterDnD._require(widget)      # تحميل حزمة tkdnd في المفسّر
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._on_drop_amadeus)
            return True
        except Exception:
            return False

    def _on_drop_amadeus(self, event):
        """يُستدعى عند إفلات صورة على منطقة السحب — يقرأ رحلات الأماديوس."""
        try:
            paths = list(self.tk.splitlist(event.data))
        except Exception:
            paths = [event.data]
        paths = [p for p in paths if str(p).strip()]
        if not paths:
            return
        # نؤجّل القراءة قليلاً كي يكتمل حدث الإفلات قبل تشغيل OCR
        self.after(50, lambda: self._apply_amadeus(paths[0]))

    # ---- قراءة رحلات أماديوس (صورة / حافظة / لقطة شاشة) ----
    def _amadeus_year(self):
        for src in (self._pf.get(), self._d.get()):
            if src and "-" in src:
                try:
                    return int(src.split("-")[0])
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
                "وأنّ أسطر الرحلات ظاهرة كاملةً.",
                parent=self)
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
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".png")
        import os
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

    def _add_flight_row(self, values=None):
        values = list(values or []) + [""] * 6
        fr = ttk.Frame(self._flight_box)
        fr.pack(fill=X, pady=2)
        wrap = ttk.Frame(fr)
        wrap.pack(side=RIGHT, padx=2)
        ttk.Label(wrap, text="اليوم", font=("Segoe UI", 7)).pack()
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
        ttk.Label(wrap, text="التاريخ", font=("Segoe UI", 7)).pack()
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
                      font=("Segoe UI", 8, "bold")).pack(side=RIGHT, padx=1)
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
                  font=("Segoe UI", 13, "bold"),
                  foreground=G.ACCENT).pack(side=RIGHT, padx=6)
        ttk.Label(tot, text="التكلفة الإجمالية:",
                  font=("Segoe UI", 11, "bold")).pack(side=RIGHT)
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
                  font=("Segoe UI", 9, "bold"),
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
                  font=("Segoe UI", 9, "bold")).grid(row=2, column=1,
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
        ttk.Button(bar, text="🖨  معاينة PDF",
                   command=self._preview).pack(side=RIGHT)
        ttk.Button(bar, text="💾  حفظ التسعير",
                   command=self._save).pack(side=RIGHT, padx=6)
        ttk.Button(bar, text="إغلاق", command=self.destroy).pack(side=RIGHT,
                                                                 padx=6)
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
                  font=("Segoe UI", 10, "bold")).grid(row=0, column=3,
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

    def _build_services(self):
        lf = self._section("البنود (للفرد) — يمكن الإضافة أو الحذف")
        self._item_rows: list = []
        hdr = ttk.Frame(lf)
        hdr.pack(fill=X)
        ttk.Label(hdr, text="المبلغ", width=14, anchor="center",
                  font=("Segoe UI", 8, "bold")).pack(side=RIGHT, padx=2)
        ttk.Label(hdr, text="البند", anchor="center",
                  font=("Segoe UI", 8, "bold")).pack(side=RIGHT, fill=X,
                                                     expand=True, padx=2)
        ttk.Label(hdr, text="", width=5).pack(side=RIGHT)
        self._item_box = ttk.Frame(lf)
        self._item_box.pack(fill=X)
        for name in self._DEFAULT_ITEMS:
            self._add_item_row(name, "")
        ttk.Button(lf, text="＋ إضافة بند",
                   command=lambda: self._add_item_row()).pack(anchor="e",
                                                              pady=(4, 0))

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
                  font=("Segoe UI", 8, "italic")).grid(row=2, column=0,
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

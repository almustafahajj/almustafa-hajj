"""واجهة **برنامج العمرة** — مبنيّة على محرّك البرنامج المجرّب.

العمرة تُنظَّم حسب **البرامج** (رحلات عمرة متعدّدة على مدار السنة). الشاشة
الرئيسية تعرض البرامج؛ ومن كل برنامج تُدار قائمة معتمريه (إضافة بقراءة
الجواز، تعديل، حذف، تصدير، حجز بالتسعير) وتفاصيله (الفنادق، الطيران بأوقاته،
أسعار الفرد حسب الغرفة، الخدمات المسعّرة، والنقل الداخلي).

يُعاد استخدام: التشفير والجلسة (storage)، قراءة الجواز (ocr/pdf_in)، نافذة
التعديل والأنماط (gui)، والتصدير (excel_io/pdf_io).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from tkinter import (
    BOTH, BooleanVar, END, LEFT, RIGHT, StringVar, Text, Toplevel, X, filedialog,
    messagebox, ttk,
)

from . import app_mode, images as imgmod, umrah
from . import gui as G
from .excel_io import export_umrah_excel
from .fields import format_amount, parse_amount
from .mrz import MRZError, PassportData
from .ocr import extract_passport
from .pdf_in import PDFError, extract_from_pdf
from .pdf_io import (
    export_airline_pdf, export_umrah_cards_pdf, export_umrah_finance_pdf,
    export_umrah_pdf, export_umrah_rooming_pdf, export_umrah_transport_pdf,
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
    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self.root, style="Panel.TFrame", padding=(16, 10, 16, 12))
        bar.pack(fill=X)
        for text, cmd, style in (
            ("➕  برنامج جديد", self.new_trip, "Primary.TButton"),
            ("👤  المعتمرين", self.open_pilgrims, "Act.TButton"),
            ("✏️  تعديل البرنامج", self.edit_trip, "Ghost.TButton"),
            ("🗑  حذف البرنامج", self.delete_trip, "Ghost.TButton"),
        ):
            ttk.Button(bar, text=G.rtl(text), style=style,
                       command=cmd).pack(side=RIGHT, padx=3)

        other = app_mode.mode_label(app_mode.HAJJ)
        ttk.Button(bar, text=G.rtl(f"🕋  التبديل إلى {other}"),
                   style="Ghost.TButton",
                   command=self.switch_mode).pack(side=LEFT, padx=3)

    # ---- جدول البرامج ----
    def _build_table(self) -> None:
        wrap = ttk.Frame(self.root, style="Toolbar.TFrame", padding=(16, 4, 16, 14))
        wrap.pack(fill=BOTH, expand=True)
        cols = ("code", "name", "depart", "return", "makkah", "madinah",
                "count", "capacity")
        heads = {"code": "الرمز", "name": "اسم البرنامج", "depart": "المغادرة",
                 "return": "العودة", "makkah": "فندق مكة",
                 "madinah": "فندق المدينة", "count": "المعتمرون",
                 "capacity": "السعة"}
        widths = {"code": 60, "name": 220, "depart": 100, "return": 100,
                  "makkah": 170, "madinah": 170, "count": 90, "capacity": 70}
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
            count = len(umrah.trip_pilgrims(self.records, t.code))
            self.tree.insert("", END, iid=t.code, values=(
                t.code, t.name or "—", t.depart_date or "—", t.return_date or "—",
                t.makkah_hotel or "—", t.madinah_hotel or "—",
                count, t.capacity or "—"),
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

    # ---- الخروج والتبديل ----
    def switch_mode(self) -> None:
        if not messagebox.askyesno(
                "تبديل الوضع",
                f"الانتقال إلى وضع «{app_mode.mode_label(app_mode.HAJJ)}»؟\n"
                "لكلّ وضع بياناته المستقلّة.", parent=self.root):
            return
        self._exit_action = "switch"
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
        self.grab_set()
        self.resizable(False, False)
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
        self.grab_set()
        self.resizable(False, False)
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

        # الخدمات المتاحة في البرنامج (اختيار أيّها)
        smap = umrah.services_map(trip)
        self.svc_vars: dict[str, BooleanVar] = {}
        if smap:
            sf = ttk.LabelFrame(f, text=G.rtl("الخدمات الإضافية (تُطبَّق لكل شخص)"),
                                padding=8)
            sf.pack(fill=X, pady=(12, 0))
            for i, (name, price) in enumerate(smap.items()):
                bv = BooleanVar(value=False)
                self.svc_vars[name] = bv
                ttk.Checkbutton(
                    sf, variable=bv,
                    text=G.rtl(f"{name}  ({format_amount(price)})"),
                    command=self._recalc).grid(row=i // 2, column=i % 2,
                                               sticky="e", padx=8, pady=2)

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

    def _chosen_services(self) -> list:
        return [n for n, bv in self.svc_vars.items() if bv.get()]

    def _auto_transport(self) -> None:
        self.transport.set(umrah.suggest_transport(self._persons_n()))
        self._transport_auto = True

    def _per_person_price(self) -> float:
        key = self._room_by_name.get(self.room.get(), "price_double")
        return umrah.package_per_person(self.trip, key, self._chosen_services())

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
        smap = umrah.services_map(self.trip)
        chosen = self._chosen_services()
        rec.room_type = self.room.get()
        rec.transport = self.transport.get().strip()
        rec.room_value = f"{base:.0f}"
        rec.umrah_services = [{"name": n, "price": f"{smap.get(n, 0):.0f}"}
                              for n in chosen]
        rec.program_value = f"{base + sum(smap.get(n, 0) for n in chosen):.0f}"

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
        self.tree.bind("<Double-1>", lambda _e: self.edit_selected())

        self.grab_set()
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
        for i, r in enumerate(recs):
            val = parse_amount(r.program_value) or 0.0
            pd = parse_amount(r.paid_amount) or 0.0
            total += val
            paid += pd
            name = r.full_name_ar or r.full_name_en or "—"
            self.tree.insert("", END, iid=str(i), values=(
                i + 1, name, r.passport_number or "—", r.room_type or "—",
                r.phone or "—", r.status or "نشط",
                format_amount(val - pd) if val else "—"),
                tags=("odd",) if i % 2 else ())
        text = (f"العدد: {len(recs)}   ·   الإجمالي: {format_amount(total)}   ·   "
                f"المحصّل: {format_amount(paid)}   ·   "
                f"المتبقّي: {format_amount(total - paid)}")
        cap = self._capacity()
        if cap:
            text += f"   ·   🪑 المقاعد المتبقّية: {self._seats_left()} من {cap}"
        self.fin.configure(text=text)
        self.app._reload()

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
        G.open_preview(
            self, lambda p: export_umrah_pdf(recs, p, program_name=self._prog_label()),
            f"معتمرو {self.trip.code}", "pdf")

    def do_finance(self) -> None:
        """معاينة الملخّص المالي للبرنامج (إجماليات، طرق الدفع، المتأخّرات)."""
        recs = self._pilgrims()
        if not recs:
            messagebox.showinfo("الملخّص المالي", "لا معتمرين في هذا البرنامج.",
                                parent=self)
            return
        G.open_preview(
            self,
            lambda p: export_umrah_finance_pdf(recs, p, program_name=self._prog_label()),
            f"مالية {self.trip.code}", "pdf")

    def do_cards(self) -> None:
        """معاينة بطاقات العمرة (بطاقة لكل معتمر)."""
        recs = self._pilgrims()
        if not recs:
            messagebox.showinfo("بطاقات العمرة", "لا معتمرين في هذا البرنامج.",
                                parent=self)
            return
        company = self.app._settings.get("company") if isinstance(
            self.app._settings.get("company"), dict) else None
        G.open_preview(
            self,
            lambda p: export_umrah_cards_pdf(recs, p, program_name=self._prog_label(),
                                             company=company),
            f"بطاقات {self.trip.code}", "pdf")


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
        n = umrah.auto_assign_rooms(self._pilgrims(), room_field)
        self.app.save()
        self._reload(key)
        avail = self._available(key)
        msg = f"وُزّع المعتمرون على {n} غرفة حسب نوع الغرفة."
        if avail and n > avail:
            msg += (f"\n\n⚠ تجاوزٌ للسعة: الغرف المتاحة في الفندق {avail} فقط. "
                    "راجع البيع/التوزيع.")
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
        ed.grab_set()
        ed.resizable(False, False)
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
            setattr(rec, room_field, v.get().strip())
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
        ed.grab_set()
        ed.resizable(False, False)
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

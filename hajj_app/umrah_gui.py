"""واجهة **برنامج العمرة** — مبنيّة على محرّك البرنامج المجرّب.

العمرة تُنظَّم حسب **الأفواج** (رحلات عمرة متعدّدة على مدار السنة). الشاشة
الرئيسية تعرض الأفواج؛ ومن كل فوج تُدار قائمة معتمريه (إضافة بقراءة الجواز،
تعديل، حذف، تصدير) وتفاصيله (فندقا مكة والمدينة، الطيران، النقل، الخدمات،
المالية).

يُعاد استخدام: التشفير والجلسة (storage)، قراءة الجواز (ocr/pdf_in)، نافذة
التعديل والأنماط (gui)، والتصدير (excel_io/pdf_io) — فلا يُعاد اختراع المجرّب.
"""

from __future__ import annotations

from pathlib import Path
from tkinter import (
    BOTH, BooleanVar, END, LEFT, RIGHT, StringVar, Text, Toplevel, X, filedialog,
    messagebox, ttk,
)
import tkinter as tk

from . import app_mode, images as imgmod, umrah
from . import gui as G
from .excel_io import export_excel
from .fields import format_amount, parse_amount
from .mrz import MRZError, PassportData
from .ocr import extract_passport
from .pdf_in import PDFError, extract_from_pdf
from .pdf_io import export_pdf
from .storage import load_records, load_settings, save_records, save_settings
from .tesseract_setup import configure_tesseract


def _center(win, parent=None) -> None:
    """يوسّط نافذة على الشاشة (أو فوق أصلها)."""
    win.update_idletasks()
    w, h = win.winfo_width(), win.winfo_height()
    sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
    win.geometry(f"+{(sw - w) // 2}+{(sh - h) // 3}")


class UmrahApp:
    """الشاشة الرئيسية لبرنامج العمرة: إدارة الأفواج."""

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

        self._build_header()
        self._build_toolbar()
        self._build_table()
        self._reload()

    # ---- الحفظ ----
    def save(self) -> None:
        """يحفظ سجلّات المعتمرين (مشفّرة)."""
        try:
            save_records(self.records, session=self.session)
        except Exception as exc:
            messagebox.showerror("تعذّر الحفظ", str(exc), parent=self.root)

    def save_trips(self) -> None:
        """يحفظ الأفواج في الإعدادات."""
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
        ttk.Label(titles, text="برنامج العمرة — الأفواج", font=(G._FSB, 17),
                  foreground=G.TEXT, background=G.BG).pack(anchor="e")
        ttk.Label(titles, text="إدارة أفواج ومعتمري العمرة", font=(G._FUI, 10),
                  foreground=G.MUTED, background=G.BG).pack(anchor="e")

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
            ("➕  فوج جديد", self.new_trip, "Primary.TButton"),
            ("👤  معتمرو الفوج", self.open_pilgrims, "Act.TButton"),
            ("✏️  تعديل الفوج", self.edit_trip, "Ghost.TButton"),
            ("🗑  حذف الفوج", self.delete_trip, "Ghost.TButton"),
        ):
            ttk.Button(bar, text=G.rtl(text), style=style,
                       command=cmd).pack(side=RIGHT, padx=3)

        other = app_mode.mode_label(app_mode.HAJJ)
        ttk.Button(bar, text=G.rtl(f"🕋  التبديل إلى {other}"),
                   style="Ghost.TButton",
                   command=self.switch_mode).pack(side=LEFT, padx=3)

    # ---- جدول الأفواج ----
    def _build_table(self) -> None:
        wrap = ttk.Frame(self.root, style="Toolbar.TFrame", padding=(16, 4, 16, 14))
        wrap.pack(fill=BOTH, expand=True)
        cols = ("code", "name", "depart", "return", "makkah", "madinah",
                "count", "capacity")
        heads = {"code": "الرمز", "name": "اسم الفوج", "depart": "المغادرة",
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
            self.root, text=G.rtl("لا أفواج بعد — ابدأ بـ «➕ فوج جديد»."),
            font=(G._FUI, 11), foreground=G.MUTED, background=G.BG)

    def _reload(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for i, t in enumerate(self.trips):
            count = len(umrah.trip_pilgrims(self.records, t.code))
            self.tree.insert("", END, iid=t.code, values=(
                t.code, t.name or "—", t.depart_date or "—", t.return_date or "—",
                t.makkah_hotel or "—", t.madinah_hotel or "—",
                count, t.capacity or "—"),
                tags=("odd",) if i % 2 else ())
        if not self.trips:
            self._empty.pack(pady=8)
        else:
            self._empty.pack_forget()

    def _selected_trip(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return next((t for t in self.trips if t.code == sel[0]), None)

    # ---- أوامر الأفواج ----
    def new_trip(self) -> None:
        trip = umrah.UmrahTrip(code=umrah.next_code(self.trips))
        TripEditorDialog(self.root, trip, {t.code for t in self.trips},
                         self._on_trip_saved, title="فوج عمرة جديد")

    def edit_trip(self) -> None:
        trip = self._selected_trip()
        if trip is None:
            messagebox.showinfo("تعديل", "اختر فوجاً أولاً.", parent=self.root)
            return
        others = {t.code for t in self.trips if t is not trip}
        TripEditorDialog(self.root, trip, others, self._on_trip_saved,
                         title=f"تعديل الفوج — {trip.name or trip.code}")

    def _on_trip_saved(self, trip) -> None:
        if trip not in self.trips:
            self.trips.append(trip)
        self.save_trips()
        self._reload()
        try:
            self.tree.selection_set(trip.code)
        except Exception:
            pass

    def delete_trip(self) -> None:
        trip = self._selected_trip()
        if trip is None:
            messagebox.showinfo("حذف", "اختر فوجاً أولاً.", parent=self.root)
            return
        n = len(umrah.trip_pilgrims(self.records, trip.code))
        msg = f"حذف الفوج «{trip.name or trip.code}»؟"
        if n:
            msg += (f"\n\nملاحظة: به {n} معتمراً. سيبقون في البيانات دون فوج "
                    "(لن يُحذفوا).")
        if not messagebox.askyesno("حذف الفوج", msg, parent=self.root):
            return
        self.trips.remove(trip)
        self.save_trips()
        self._reload()

    def open_pilgrims(self) -> None:
        trip = self._selected_trip()
        if trip is None:
            messagebox.showinfo("المعتمرون", "اختر فوجاً أولاً.", parent=self.root)
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
    """نافذة إنشاء/تعديل فوج عمرة بكل تفاصيله وخدماته."""

    def __init__(self, parent, trip, existing_codes, on_save, *, title="فوج") -> None:
        super().__init__(parent)
        self.trip = trip
        self.existing = set(existing_codes)
        self.on_save = on_save
        self.title(title)
        self.configure(bg=G.BG)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)

        outer = ttk.Frame(self, padding=16)
        outer.pack(fill=BOTH, expand=True)
        self.vars: dict[str, StringVar] = {}

        # صفوف الحقول: (المفتاح، العنوان، العرض)
        rows = [
            ("code", "رمز الفوج *", 14), ("name", "اسم الفوج", 34),
            ("depart_date", "تاريخ المغادرة", 18), ("return_date", "تاريخ العودة", 18),
            ("makkah_hotel", "فندق مكة", 34), ("makkah_nights", "ليالي مكة", 14),
            ("madinah_hotel", "فندق المدينة", 34), ("madinah_nights", "ليالي المدينة", 14),
            ("airline", "شركة الطيران", 24), ("flight_out", "رحلة الذهاب", 16),
            ("flight_ret", "رحلة العودة", 16), ("transport", "النقل الداخلي", 24),
            ("capacity", "السعة (مقاعد)", 12), ("price", "سعر الباقة (درهم)", 14),
        ]
        grid = ttk.Frame(outer)
        grid.pack(fill=X)
        for i, (key, label, width) in enumerate(rows):
            r, c = divmod(i, 2)
            cell = ttk.Frame(grid)
            cell.grid(row=r, column=c, sticky="e", padx=8, pady=4)
            ttk.Label(cell, text=label, font=(G._FUI, 10),
                      foreground=G.TEXT).pack(side=RIGHT, padx=(8, 4))
            v = StringVar(value=str(getattr(trip, key, "") or ""))
            self.vars[key] = v
            ttk.Entry(cell, textvariable=v, width=width,
                      justify="right").pack(side=RIGHT)

        # الخدمات (مربّعات اختيار)
        ttk.Label(outer, text=G.rtl("الخدمات الإضافية:"), font=(G._FSB, 11),
                  foreground=G.BRONZE, background=G.BG).pack(anchor="e", pady=(12, 4))
        svc = ttk.Frame(outer)
        svc.pack(fill=X)
        self.svc_vars: dict[str, BooleanVar] = {}
        for i, name in enumerate(umrah.SERVICES):
            bv = BooleanVar(value=name in (trip.services or []))
            self.svc_vars[name] = bv
            ttk.Checkbutton(svc, text=G.rtl(name), variable=bv).grid(
                row=i // 2, column=i % 2, sticky="e", padx=8, pady=2)

        # ملاحظات
        ttk.Label(outer, text=G.rtl("ملاحظات:"), font=(G._FUI, 10),
                  foreground=G.TEXT, background=G.BG).pack(anchor="e", pady=(10, 2))
        self.notes = Text(outer, height=3, width=64, wrap="word", font=(G._FUI, 10))
        self.notes.pack(fill=X)
        self.notes.insert("1.0", trip.notes or "")

        btns = ttk.Frame(outer)
        btns.pack(fill=X, pady=(14, 0))
        ttk.Button(btns, text=G.rtl("💾 حفظ الفوج"), style="Primary.TButton",
                   command=self._save).pack(side=RIGHT, padx=3)
        ttk.Button(btns, text="إلغاء", style="Ghost.TButton",
                   command=self.destroy).pack(side=LEFT, padx=3)
        self.bind("<Escape>", lambda _e: self.destroy())
        _center(self, parent)

    def _save(self) -> None:
        code = self.vars["code"].get().strip()
        if not code:
            messagebox.showwarning("رمز مطلوب", "أدخل رمز الفوج.", parent=self)
            return
        if code in self.existing:
            messagebox.showwarning("رمز مكرّر",
                                   f"الرمز «{code}» مستعمل في فوج آخر.", parent=self)
            return
        for key, v in self.vars.items():
            setattr(self.trip, key, v.get().strip())
        self.trip.services = [n for n, bv in self.svc_vars.items() if bv.get()]
        self.trip.notes = self.notes.get("1.0", END).strip()
        self.on_save(self.trip)
        self.destroy()


class TripPilgrimsWindow(Toplevel):
    """قائمة معتمري فوجٍ واحد: إضافة (بقراءة الجواز/يدوي)، تعديل، حذف، تصدير."""

    def __init__(self, app: UmrahApp, trip) -> None:
        super().__init__(app.root)
        self.app = app
        self.trip = trip
        self.session = app.session
        self.title(f"معتمرو الفوج — {trip.name or trip.code}")
        self.configure(bg=G.BG)
        self.geometry("1080x640")
        self.minsize(820, 480)
        self.transient(app.root)

        head = ttk.Frame(self, style="Toolbar.TFrame", padding=(14, 10, 14, 4))
        head.pack(fill=X)
        ttk.Label(head, text=f"👤 معتمرو «{trip.name or trip.code}»",
                  font=(G._FSB, 15), foreground=G.TEXT,
                  background=G.BG).pack(side=RIGHT)
        self.fin = ttk.Label(head, text="", font=(G._FUI, 10),
                             foreground=G.BRONZE, background=G.BG)
        self.fin.pack(side=LEFT)

        bar = ttk.Frame(self, style="Panel.TFrame", padding=(14, 8, 14, 10))
        bar.pack(fill=X)
        for text, cmd, style in (
            ("📷  إضافة بقراءة الجواز", self.add_passport, "Primary.TButton"),
            ("➕  إضافة يدوي", self.add_manual, "Act.TButton"),
            ("✏️  تعديل", self.edit_selected, "Ghost.TButton"),
            ("🗑  حذف", self.delete_selected, "Ghost.TButton"),
        ):
            ttk.Button(bar, text=G.rtl(text), style=style,
                       command=cmd).pack(side=RIGHT, padx=3)
        ttk.Button(bar, text=G.rtl("📄  تصدير PDF"), style="Ghost.TButton",
                   command=self.export_pdf).pack(side=LEFT, padx=3)
        ttk.Button(bar, text=G.rtl("📊  تصدير إكسل"), style="Ghost.TButton",
                   command=self.export_excel).pack(side=LEFT, padx=3)

        wrap = ttk.Frame(self, style="Toolbar.TFrame", padding=(14, 4, 14, 12))
        wrap.pack(fill=BOTH, expand=True)
        cols = ("n", "name", "passport", "nat", "phone", "status", "remaining")
        heads = {"n": "م", "name": "اسم المعتمر", "passport": "رقم الجواز",
                 "nat": "الجنسية", "phone": "الهاتف", "status": "الحالة",
                 "remaining": "المتبقّي"}
        widths = {"n": 44, "name": 260, "passport": 120, "nat": 110, "phone": 130,
                  "status": 100, "remaining": 110}
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

    # ---- بيانات الفوج ----
    def _pilgrims(self) -> list:
        return umrah.trip_pilgrims(self.app.records, self.trip.code)

    def _reload(self) -> None:
        self.tree.delete(*self.tree.get_children())
        recs = self._pilgrims()
        total = paid = 0.0
        for i, r in enumerate(recs):
            val = parse_amount(r.program_value) or 0.0
            pd = parse_amount(r.paid_amount) or 0.0
            total += val
            paid += pd
            rem = val - pd
            name = r.full_name_ar or r.full_name_en or "—"
            self.tree.insert("", END, iid=str(i), values=(
                i + 1, name, r.passport_number or "—", r.nationality_ar or "—",
                r.phone or "—", r.status or "نشط",
                format_amount(rem) if val else "—"),
                tags=("odd",) if i % 2 else ())
        self.fin.configure(text=(
            f"العدد: {len(recs)}   ·   الإجمالي: {format_amount(total)}   ·   "
            f"المحصّل: {format_amount(paid)}   ·   المتبقّي: {format_amount(total - paid)}"))
        self.app._reload()                 # حدّث عدّاد الفوج في الشاشة الرئيسية

    def _selected(self):
        sel = self.tree.selection()
        if not sel:
            return None
        recs = self._pilgrims()
        idx = int(sel[0])
        return recs[idx] if 0 <= idx < len(recs) else None

    # ---- الإضافة ----
    def add_manual(self) -> None:
        rec = PassportData()
        rec.trip = self.trip.code

        def on_save(r):
            r.trip = self.trip.code
            if r not in self.app.records:
                self.app.records.append(r)
            self.app.save()
            self._reload()

        G.EditDialog(self, rec, on_save, title="إضافة معتمر",
                     save_text="إضافة", session=self.session)

    def add_passport(self) -> None:
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
        self.configure(cursor="watch")
        self.update_idletasks()
        added, fails = 0, []
        for p in paths:
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
                rec.trip = self.trip.code
                if len(recs) == 1:
                    self._attach_image(rec, p)
                self.app.records.append(rec)
                added += 1
        self.configure(cursor="")
        if added:
            self.app.save()
            self._reload()
        msg = f"أُضيف {added} معتمراً."
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
                     session=self.session)

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
    def _export(self, fn, ext, label) -> None:
        recs = self._pilgrims()
        if not recs:
            messagebox.showinfo("تصدير", "لا معتمرين في هذا الفوج.", parent=self)
            return
        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=ext,
            initialfile=f"معتمرو {self.trip.code}{ext}",
            filetypes=[(label, f"*{ext}")])
        if not path:
            return
        try:
            fn(recs, path)
        except Exception as exc:                           # noqa: BLE001
            messagebox.showerror("تعذّر التصدير", str(exc), parent=self)
            return
        messagebox.showinfo("تم", f"حُفظ الملف:\n{path}", parent=self)

    def export_excel(self) -> None:
        self._export(lambda recs, p: export_excel(recs, p), ".xlsx", "إكسل")

    def export_pdf(self) -> None:
        title = f"معتمرو العمرة — {self.trip.name or self.trip.code}"
        self._export(lambda recs, p: export_pdf(recs, p, title=title),
                     ".pdf", "PDF")

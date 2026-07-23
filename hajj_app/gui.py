"""واجهة سطح المكتب لبرنامج موسم الحج."""

from __future__ import annotations

import queue
import re
import threading
import traceback
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, Y, StringVar, Tk, Toplevel, filedialog, messagebox, ttk

from .excel_io import export_excel, import_excel
from .fields import (
    DATE_KEYS, DIAG_FIELDS, EDITABLE, FIELDS, MONEY_KEYS, MRZ_FILLED, TIME_KEYS,
    compute_remaining, format_amount, normalize_time, parse_amount, row_dict,
)
from .mrz import MRZError, PassportData
from .ocr import extract_passport
from .tesseract_setup import arabic_supported, configure_tesseract
from .pdf_in import PDFError, extract_from_pdf
from .pdf_io import export_pdf
from .rooming import ROOM_CATEGORIES, room_capacity, room_category, room_number_in_type
from .login import (
    ChangePasswordDialog, NewRecoveryKeyDialog, RecoveryKeyDialog,
    apply_window_icon, authenticate, logo_image, rtl,
)
from .storage import (
    default_data_path, load_records, load_settings, save_records, save_settings,
)

_IMG_EXT = "*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp"
SCAN_TYPES = (
    ("صور وملفات PDF", f"{_IMG_EXT} *.pdf"),
    ("صور الجوازات", _IMG_EXT),
    ("ملفات PDF", "*.pdf"),
    ("كل الملفات", "*.*"),
)
EXCEL_TYPES = (("ملفات إكسل", "*.xlsx *.xlsm"), ("كل الملفات", "*.*"))

# السنوات الهجرية المتاحة في قائمة الموسم (حج 2026 = 1447هـ)
HIJRI_YEARS = tuple(str(y) for y in range(1445, 1456))
_DEFAULT_SEASON = "1447"

# ---- ألوان العلامة الثابتة (لا تتبدّل بين الفاتح والداكن) ----
ACCENT = "#111111"          # الأسود — سطح رؤوس الجدول
BRONZE = "#8A6E4B"          # البرونزي — التمييز والتفاعل
BRONZE_DARK = "#6F5738"
ACCENT_HOVER = BRONZE
WARN_BG = "#FBF0DC"         # كهرماني باهت (تمييز صفوف التنبيه)
SUCCESS_FG = "#2E6B45"
SUCCESS_BG = "#E6F1E9"
AMBER_FG = "#B26A00"
DANGER = "#B23A3A"
DANGER_HOVER = "#8F2C2C"
BRONZE_LIGHT = "#B4986E"    # حواف الأزرار ثلاثية الأبعاد
BRONZE_EDGE = "#4E3C25"
DANGER_LIGHT = "#D57B7B"
DANGER_EDGE = "#7A2222"

# ---- أدوار الألوان (تتبدّل مع الوضع الفاتح/الداكن) ----
_PALETTES = {
    "فاتح": {
        "BG": "#F7F5F2", "PANEL": "#FFFFFF", "ROW_ALT": "#F2ECE3",
        "HOVER_BG": "#EADFCB", "BORDER": "#E2DACE", "MUTED": "#777777",
        "TEXT": "#111111", "GHOST_BG": "#F1ECE3", "GHOST_HOVER": "#E7DECF",
        "GHOST_LIGHT": "#FFFFFF", "GHOST_EDGE": "#C7BBA6", "PANEL_EDGE": "#D8CFC0",
    },
    "داكن": {
        "BG": "#1E1E22", "PANEL": "#26262B", "ROW_ALT": "#2C2C33",
        "HOVER_BG": "#3A3A44", "BORDER": "#3A3A44", "MUTED": "#9A948B",
        "TEXT": "#EAE6DF", "GHOST_BG": "#33333A", "GHOST_HOVER": "#3E3E48",
        "GHOST_LIGHT": "#4A4A54", "GHOST_EDGE": "#141418", "PANEL_EDGE": "#141418",
    },
}
THEMES = tuple(_PALETTES)

# القيم الحالية (تُضبط بـ apply_theme)
BG = PANEL = ROW_ALT = HOVER_BG = BORDER = MUTED = TEXT = ""
GHOST_BG = GHOST_HOVER = GHOST_LIGHT = GHOST_EDGE = PANEL_EDGE = ""


def apply_theme(name: str) -> None:
    """يضبط أدوار الألوان حسب الوضع (فاتح/داكن)."""
    global BG, PANEL, ROW_ALT, HOVER_BG, BORDER, MUTED, TEXT
    global GHOST_BG, GHOST_HOVER, GHOST_LIGHT, GHOST_EDGE, PANEL_EDGE
    pal = _PALETTES.get(name, _PALETTES["فاتح"])
    BG, PANEL, ROW_ALT = pal["BG"], pal["PANEL"], pal["ROW_ALT"]
    HOVER_BG, BORDER, MUTED = pal["HOVER_BG"], pal["BORDER"], pal["MUTED"]
    TEXT = pal["TEXT"]
    GHOST_BG, GHOST_HOVER = pal["GHOST_BG"], pal["GHOST_HOVER"]
    GHOST_LIGHT, GHOST_EDGE, PANEL_EDGE = pal["GHOST_LIGHT"], pal["GHOST_EDGE"], pal["PANEL_EDGE"]


apply_theme("فاتح")            # الافتراضي حتى تُحمَّل الإعدادات


def install_entry_editing(widget) -> None:
    """يفعّل النسخ/اللصق/القص/تحديد الكل بقائمة يمين ولوحة المفاتيح.

    يعمل حتى مع **لوحة المفاتيح العربية**: نربط بالرمز الفيزيائي للمفتاح
    (keycode) لا بحرفه، فاختصارات Ctrl تعمل مهما كانت لغة الإدخال.
    """
    def do(action: str) -> None:
        try:
            if action == "copy":
                widget.event_generate("<<Copy>>")
            elif action == "paste":
                widget.event_generate("<<Paste>>")
            elif action == "cut":
                widget.event_generate("<<Cut>>")
            elif action == "all":
                widget.select_range(0, "end")
                widget.icursor("end")
        except tk.TclError:
            pass

    menu = tk.Menu(widget, tearoff=0)
    menu.add_command(label="نسخ", command=lambda: do("copy"))
    menu.add_command(label="لصق", command=lambda: do("paste"))
    menu.add_command(label="قص", command=lambda: do("cut"))
    menu.add_separator()
    menu.add_command(label="تحديد الكل", command=lambda: do("all"))

    def popup(event):
        widget.focus_set()
        menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def ctrl(event):
        act = {67: "copy", 86: "paste", 88: "cut", 65: "all"}.get(event.keycode)
        if act:
            do(act)
            return "break"

    widget.bind("<Button-3>", popup)
    widget.bind("<Control-KeyPress>", ctrl)


class HajjApp:
    def __init__(self, root: Tk, session=None, open_mode: bool = False) -> None:
        self.root = root
        self.session = session      # يحمل مفتاح التشفير؛ None في الاختبارات
        self._open_mode = open_mode  # فتح بلا رقم سري (بلا تشفير) — ملف بيانات منفصل
        self.records: list[PassportData] = []
        self.data_path = default_data_path()
        if open_mode:
            # ملف منفصل حتى لا يُمسّ الكشف المشفّر ولا يُستبدل بنصّ صريح
            self.data_path = self.data_path.with_name("hajjaj-open.json")
        self.tesseract_path = configure_tesseract()
        # قائمة انتظار لنقل نتائج الخيط الخلفي إلى واجهة Tk بأمان
        self.results: queue.Queue = queue.Queue()

        # السنة الهجرية للموسم — تُحفظ ويحدّدها المستخدم
        self._settings = load_settings()
        saved_year = str(self._settings.get("season_year", "")).strip()
        self.season_year = StringVar(
            value=saved_year if saved_year in HIJRI_YEARS else _DEFAULT_SEASON
        )
        # تاريخ سفر الموسم — مرجع قاعدة صلاحية الجواز (6 أشهر من السفر)
        self.travel_date_ref = StringVar(
            value=str(self._settings.get("travel_date", "")).strip())
        self.travel_date_ref.trace_add("write", lambda *_a: self._save_travel_date())

        # الترتيب عرض فقط: لا يمسّ ترتيب self.records الأصلي، فيمكن إلغاؤه
        self.sort_field: str | None = None
        self.sort_desc = False

        # إعدادات الواجهة المحفوظة (تُستعاد بين الجلسات)
        self._ui = dict(self._settings.get("ui", {}))
        self._density = self._ui.get("density", "عادي")
        if self._density not in self._DENSITY:
            self._density = "عادي"
        self._font_size = self._ui.get("font_size", "متوسط")
        if self._font_size not in self._FONT_SIZES:
            self._font_size = "متوسط"
        self._hidden_cols: set[str] = set(self._ui.get("hidden_columns", ["source_file"]))
        # الوضع الفاتح/الداكن — يُطبّق قبل بناء الأنماط
        self._theme = self._ui.get("theme", "فاتح")
        if self._theme not in THEMES:
            self._theme = "فاتح"
        apply_theme(self._theme)

        root.title("برنامج الحج — إدارة بيانات الحجاج")
        geom = self._ui.get("geometry")
        root.geometry(geom if isinstance(geom, str) and "x" in geom else "1280x740")
        root.minsize(900, 560)
        root.configure(bg=BG)

        self._build_styles()
        self._build_header()
        self._build_toolbar()
        self._build_filters()
        self._build_table()
        self._build_status()
        self._bind_shortcuts()

        self._load_saved_data()
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        if self.records:
            pass        # رسالة الاستعادة أهم من تنبيهات التهيئة
        elif not self.tesseract_path:
            self.set_status("تنبيه: Tesseract غير مثبّت — قراءة الصور معطّلة", warn=True)
        elif not arabic_supported():
            self.set_status(
                "تنبيه: حزمة اللغة العربية غير مثبّتة — لن يُقرأ الاسم العربي من الصور",
                warn=True,
            )

    # كثافة الصفوف وحجم الخط (قابلة للاختيار وتُحفظ)
    _DENSITY = {"مريح": 31, "عادي": 26, "مضغوط": 21}
    _FONT_SIZES = {"صغير": 9, "متوسط": 10, "كبير": 12}

    # ------------------------------------------------------------------ بناء
    def _build_styles(self) -> None:
        s = ttk.Style()
        self._style = s
        try:
            s.theme_use("clam")
        except Exception:
            pass

        s.configure("Toolbar.TFrame", background=BG)
        # لوح بارز (bevel) للشريط العلوي — إحساس ثلاثي الأبعاد بالعمق
        s.configure("Panel.TFrame", background=BG, relief="raised", borderwidth=1,
                    lightcolor=GHOST_LIGHT, darkcolor=PANEL_EDGE, bordercolor=PANEL_EDGE)
        s.configure("Sep.TFrame", background=BRONZE)      # فاصل برونزي رفيع

        # الجدول: صفوف متناوبة الألوان وتمييز برونزي للصف المحدد
        self._apply_table_style()
        s.configure("Treeview.Heading", font=("Segoe UI Semibold", 10),
                    background=ACCENT, foreground="white", padding=7, relief="raised",
                    borderwidth=2, lightcolor="#3A3A3A", darkcolor="#000000",
                    bordercolor="#000000")
        s.map("Treeview.Heading",
              background=[("active", BRONZE)],
              relief=[("pressed", "sunken"), ("active", "raised")])

        # ---- أزرار ثلاثية الأبعاد (حواف مشطوفة + ضغطة غائرة) ----
        def bevel(name, bg, fg, light, dark, hover, *, bold=True, pad=(15, 8)):
            font = ("Segoe UI Semibold", 10) if bold else ("Segoe UI", 10)
            s.configure(name, font=font, padding=pad, foreground=fg, background=bg,
                        relief="raised", borderwidth=3, focuscolor=bg,
                        lightcolor=light, darkcolor=dark, bordercolor=dark)
            s.map(name,
                  background=[("pressed", dark), ("active", hover),
                              ("disabled", "#CFC6B6")],
                  foreground=[("disabled", "#8C857A")],
                  relief=[("pressed", "sunken"), ("!pressed", "raised")],
                  # عكس الإضاءة عند الضغط ليبدو الزر مضغوطاً للداخل
                  lightcolor=[("pressed", dark)], darkcolor=[("pressed", light)])

        bevel("Primary.TButton", BRONZE, "white", BRONZE_LIGHT, BRONZE_EDGE, BRONZE_DARK)
        bevel("Danger.TButton", DANGER, "white", DANGER_LIGHT, DANGER_EDGE, DANGER_HOVER)
        bevel("Ghost.TButton", GHOST_BG, TEXT, GHOST_LIGHT, GHOST_EDGE, GHOST_HOVER,
              bold=False)
        # Act.TButton (يُستعمل في النوافذ) — بارز ثانوي
        bevel("Act.TButton", GHOST_BG, TEXT, GHOST_LIGHT, GHOST_EDGE, GHOST_HOVER,
              bold=False, pad=(12, 7))

        # ---- قوائم منسدلة ثلاثية الأبعاد ----
        def bevel_mb(name, bg, fg, light, dark, hover, arrow, *, bold=True):
            font = ("Segoe UI Semibold", 10) if bold else ("Segoe UI", 10)
            s.configure(name, font=font, padding=(15, 8), foreground=fg, background=bg,
                        arrowcolor=arrow, relief="raised", borderwidth=3,
                        lightcolor=light, darkcolor=dark, bordercolor=dark)
            s.map(name,
                  background=[("pressed", dark), ("active", hover),
                              ("disabled", "#CFC6B6")],
                  relief=[("pressed", "sunken"), ("!pressed", "raised")],
                  lightcolor=[("pressed", dark)], darkcolor=[("pressed", light)])

        bevel_mb("Toolbar.TMenubutton", BRONZE, "white", BRONZE_LIGHT, BRONZE_EDGE,
                 BRONZE_DARK, "white")
        # إبراز القوائم الأساسية (إضافة/التقارير) بخطّ أكبر قليلاً
        s.configure("Toolbar.TMenubutton", font=("Segoe UI Semibold", 11),
                    padding=(17, 9))
        bevel_mb("Ghost.TMenubutton", GHOST_BG, TEXT, GHOST_LIGHT, GHOST_EDGE,
                 GHOST_HOVER, TEXT, bold=False)

        # حقول الإدخال والقوائم: أخدود غائر + ألوان تتبع الوضع
        for widget in ("TEntry", "TCombobox", "TSpinbox"):
            s.configure(widget, relief="sunken", borderwidth=1,
                        fieldbackground=PANEL, foreground=TEXT,
                        insertcolor=TEXT, arrowcolor=TEXT, background=PANEL,
                        bordercolor=GHOST_EDGE, lightcolor=GHOST_EDGE,
                        darkcolor=GHOST_LIGHT)
        s.map("TCombobox", fieldbackground=[("readonly", PANEL)],
              foreground=[("readonly", TEXT)])
        # قوائم Tk المنسدلة (يمين الفأرة/القوائم) تتبع الوضع
        self.root.option_add("*Menu.background", PANEL)
        self.root.option_add("*Menu.foreground", TEXT)
        self.root.option_add("*Menu.activeBackground", BRONZE)
        self.root.option_add("*Menu.activeForeground", "white")

        # ---- حواف دائرية حقيقية (صور 9-slice) فوق البيفل، مع تراجع آمن ----
        self._round_refs = []
        self._rounded_style(s, "Primary.TButton", BRONZE, BRONZE_LIGHT, BRONZE_EDGE,
                            BRONZE_DARK, "white")
        self._rounded_style(s, "Danger.TButton", DANGER, DANGER_LIGHT, DANGER_EDGE,
                            DANGER_HOVER, "white")
        self._rounded_style(s, "Ghost.TButton", GHOST_BG, GHOST_LIGHT, GHOST_EDGE,
                            GHOST_HOVER, TEXT)
        self._rounded_style(s, "Act.TButton", GHOST_BG, GHOST_LIGHT, GHOST_EDGE,
                            GHOST_HOVER, TEXT)
        self._rounded_style(s, "Toolbar.TMenubutton", BRONZE, BRONZE_LIGHT,
                            BRONZE_EDGE, BRONZE_DARK, "white", arrow="white", menu=True)
        self._rounded_style(s, "Ghost.TMenubutton", GHOST_BG, GHOST_LIGHT, GHOST_EDGE,
                            GHOST_HOVER, TEXT, arrow=TEXT, menu=True)

    def _rounded_style(self, s, style, bg, light, dark, hover, fg,
                       *, arrow=None, menu=False) -> None:
        """يعطي النمط حوافَّ دائرية عبر عنصر صورة 9-slice (يتراجع للبيفل عند الفشل)."""
        try:
            from PIL import ImageTk
            from . import icons as iconlib
            base = ImageTk.PhotoImage(iconlib.button_bg(bg, light, dark))
            act = ImageTk.PhotoImage(iconlib.button_bg(hover, light, dark))
            prs = ImageTk.PhotoImage(iconlib.button_bg(bg, light, dark, pressed=True))
            self._round_refs += [base, act, prs]
            elem = style.replace(".", "_") + "_rbg"
            s.element_create(elem, "image", base, ("pressed", prs), ("active", act),
                             border=13, sticky="nsew", padding=(16, 8))
            font = ("Segoe UI Semibold", 11) if menu else \
                (("Segoe UI Semibold", 10) if "Primary" in style or "Danger" in style
                 else ("Segoe UI", 10))
            if menu:
                s.layout(style, [(elem, {"sticky": "nsew", "children": [
                    ("Menubutton.padding", {"sticky": "nsew", "children": [
                        ("Menubutton.indicator", {"side": "left", "sticky": ""}),
                        ("Menubutton.label", {"sticky": "nsew"}),
                    ]})]})])
            else:
                s.layout(style, [(elem, {"sticky": "nsew", "children": [
                    ("Button.padding", {"sticky": "nsew", "children": [
                        ("Button.label", {"sticky": "nsew"}),
                    ]})]})])
            cfg = dict(background=bg, foreground=fg, font=font, borderwidth=0,
                       focuscolor=bg)
            if arrow is not None:
                cfg["arrowcolor"] = arrow
            s.configure(style, **cfg)
        except Exception:
            pass          # نُبقي مظهر البيفل ثلاثي الأبعاد

    def _apply_table_style(self) -> None:
        """يطبّق كثافة الصفوف وحجم الخط على الجدول (قابل للتغيير حياً)."""
        rowheight = self._DENSITY.get(self._density, 26)
        size = self._FONT_SIZES.get(self._font_size, 10)
        s = self._style
        s.configure("Treeview", rowheight=rowheight, font=("Segoe UI", size),
                    background=PANEL, fieldbackground=PANEL, foreground=TEXT,
                    borderwidth=0)
        s.map("Treeview",
              background=[("selected", BRONZE)], foreground=[("selected", "white")])

    def _build_header(self) -> None:
        bar = ttk.Frame(self.root, style="Toolbar.TFrame", padding=(16, 10, 16, 6))
        bar.pack(fill=X)

        # الشعار أقصى اليمين — بداية القراءة في الواجهة العربية
        self._logo = logo_image(self.root, width=150)
        if self._logo is not None:
            ttk.Label(bar, image=self._logo, background=BG).pack(side=RIGHT, padx=(0, 14))

        titles = ttk.Frame(bar, style="Toolbar.TFrame")
        titles.pack(side=RIGHT)
        ttk.Label(titles, text="برنامج الحج موسم", font=("Segoe UI Semibold", 17),
                  foreground=TEXT, background=BG).pack(side=RIGHT)
        year_box = ttk.Combobox(
            titles, textvariable=self.season_year, state="readonly",
            width=6, font=("Segoe UI Semibold", 15), values=HIJRI_YEARS,
        )
        year_box.pack(side=RIGHT, padx=(8, 0))
        year_box.bind("<<ComboboxSelected>>", lambda _e: self._on_season_change())

        # تاريخ سفر الموسم — مرجع فحص صلاحية الجواز (6 أشهر من السفر)
        travel = ttk.Frame(bar, style="Toolbar.TFrame")
        travel.pack(side=RIGHT, padx=(18, 0))
        ttk.Label(travel, text="تاريخ السفر", font=("Segoe UI", 9),
                  foreground=MUTED, background=BG).pack(anchor="e")
        tv = ttk.Entry(travel, textvariable=self.travel_date_ref, width=12,
                       justify="center", font=("Segoe UI", 10))
        tv.pack(anchor="e")
        _tip = "لفحص صلاحية الجواز (6 أشهر من السفر). الصيغة: YYYY-MM-DD"
        for _w in (tv,):
            _w.bind("<FocusIn>", lambda _e: self.set_status(_tip))

        # حالة الجلسة والحماية أقصى اليسار
        if self.session is not None:
            info = ttk.Frame(bar, style="Toolbar.TFrame")
            info.pack(side=LEFT)
            ttk.Label(info, text=f"👤  {self.session.username}",
                      font=("Segoe UI Semibold", 10), foreground=TEXT,
                      background=BG).pack(anchor="w")
            ttk.Label(info, text="🔒 البيانات مشفّرة", font=("Segoe UI", 9),
                      foreground=BRONZE, background=BG).pack(anchor="w")
            for text, action in (
                ("تغيير كلمة المرور", self.change_password),
                ("مفتاح استرداد جديد", self.new_recovery_key),
            ):
                link = ttk.Label(info, text=text, font=("Segoe UI", 9, "underline"),
                                 foreground=TEXT, background=BG, cursor="hand2")
                link.pack(anchor="w")
                link.bind("<Button-1>", lambda _e, run=action: run())
        elif self._open_mode:
            info = ttk.Frame(bar, style="Toolbar.TFrame")
            info.pack(side=LEFT)
            ttk.Label(info, text="🔓 وضع مفتوح — بلا رقم سري",
                      font=("Segoe UI Semibold", 10), foreground=AMBER_FG,
                      background=BG).pack(anchor="w")
            ttk.Label(info, text="البيانات غير مشفّرة (مؤقتاً)", font=("Segoe UI", 9),
                      foreground=MUTED, background=BG).pack(anchor="w")

        # فاصل برونزي رفيع يفصل الترويسة عمّا تحتها
        ttk.Frame(self.root, style="Sep.TFrame", height=2).pack(fill=X)

    def new_recovery_key(self) -> None:
        """يولّد مفتاح استرداد جديداً ويعرضه — يبطل القديم."""
        if self.session is None:
            return
        dialog = NewRecoveryKeyDialog(self.root, self.session.username)
        self.root.wait_window(dialog)
        if dialog.recovery_key:
            RecoveryKeyDialog(self.root, dialog.recovery_key, is_new=False)
            self.set_status("أُنشئ مفتاح استرداد جديد — المفتاح السابق لم يعد صالحاً")

    def change_password(self) -> None:
        """يغيّر كلمة مرور الجلسة الحالية. لا يمسّ ملف البيانات."""
        if self.session is None:
            return
        dialog = ChangePasswordDialog(self.root, self.session.username)
        self.root.wait_window(dialog)
        if dialog.session is None:
            return
        self.session = dialog.session
        if dialog.session.fresh_recovery_key:
            RecoveryKeyDialog(self.root, dialog.session.fresh_recovery_key, is_new=False)
        self.set_status("تم تغيير كلمة المرور — بياناتك كما هي")

    def _on_season_change(self) -> None:
        """يحفظ السنة الهجرية المختارة."""
        self._settings["season_year"] = self.season_year.get()
        try:
            save_settings(self._settings)
        except OSError:
            pass
        self.set_status(f"موسم الحج: {self.season_year.get()}هـ")

    def _save_travel_date(self) -> None:
        """يحفظ تاريخ سفر الموسم (مرجع فحص صلاحية الجواز)."""
        self._settings["travel_date"] = self.travel_date_ref.get().strip()
        try:
            save_settings(self._settings)
        except OSError:
            pass

    def _travel_ref(self):
        """يحوّل تاريخ سفر الموسم إلى date أو None (للفحص)."""
        from .quality import parse_date
        return parse_date(self.travel_date_ref.get())

    def _report_title(self, base: str) -> str:
        """عنوان تقرير يتضمّن موسم السنة الهجرية."""
        year = self.season_year.get().strip()
        return f"{base} — موسم {year}هـ" if year else base

    def _icon(self, name: str, color: str, size: int = 18):
        """أيقونة مولّدة (PhotoImage) مخزّنة لمنع جمع القمامة."""
        key = (name, color, size)
        cache = getattr(self, "_icon_cache", None)
        if cache is None:
            cache = self._icon_cache = {}
        if key not in cache:
            try:
                from PIL import ImageTk
                from . import icons as iconlib
                cache[key] = ImageTk.PhotoImage(iconlib.make_icon(name, color, size))
            except Exception:
                cache[key] = None
        return cache[key]

    def _menubutton(self, parent, text, items, *, style="Toolbar.TMenubutton",
                    icon=None):
        """زر بقائمة منسدلة (Menubutton + Menu) بعناصر (نص، أمر)، بأيقونة اختيارية."""
        mb = ttk.Menubutton(parent, text=rtl(text), style=style, direction="below")
        if icon is not None:
            img = self._icon(*icon)
            if img is not None:
                mb.configure(image=img, compound="right")
        menu = tk.Menu(mb, tearoff=0, font=("Segoe UI", 10))
        for entry in items:
            if entry is None:
                menu.add_separator()
            else:
                label, cmd = entry
                menu.add_command(label=label, command=cmd)
        mb["menu"] = menu
        self._menus.append(menu)          # نحتفظ بمرجع لمنع جمع القمامة
        return mb

    def _icon_button(self, parent, text, command, style, icon):
        """زر بأيقونة ملوّنة (الأيقونة يميناً في التخطيط العربي)."""
        btn = ttk.Button(parent, text=rtl(text), command=command, style=style)
        img = self._icon(*icon)
        if img is not None:
            btn.configure(image=img, compound="right")
        return btn

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self.root, style="Panel.TFrame", padding=(16, 10, 16, 12))
        bar.pack(fill=X)
        self._menus: list = []
        WHITE, INK, RED = "#FFFFFF", TEXT, "#FFFFFF"

        # ---- قوائم مصنّفة (تقسيم البرنامج إلى قوائم) ----
        # 👥 الحجّاج: الإدخال والتعديل والحذف وفحص الجاهزية
        pilgrims_mb = self._menubutton(bar, "الحجّاج  ▾", [
            ("➕  إضافة حاج يدوياً", self.add_manual),
            ("📷  إضافة جوازات (صور / PDF)", self.add_images),
            ("📁  استيراد من إكسل", self.import_from_excel),
            None,
            ("✏️  تعديل السجل", self.edit_selected),
            ("✏️  تعديل جماعي للمحدّدين", self.bulk_edit_selected),
            ("🗑  حذف المحدد", self.delete_selected),
            None,
            ("🩺  فحص جاهزية الكشف", self.do_quality_check),
            None,
            ("🗂  برامج الحملة (الأول/الثاني/الثالث)", self.do_programs),
            ("🧹  مسح الكل", self.clear_all),
        ], icon=("id", WHITE))
        pilgrims_mb.pack(side=RIGHT, padx=(0, 4))

        # 📋 الكشوفات والتقارير: التصدير والكشوفات والطباعة
        rep_mb = self._menubutton(bar, "الكشوفات والتقارير  ▾", [
            ("📊  تصدير إكسل", self.do_export_excel),
            ("📄  تصدير PDF", self.do_export_pdf),
            ("🖨  طباعة المعروض", self.do_print_filtered),
            None,
            ("✈  كشف الطيران وأماديوس", self.do_airline),
            ("🚌  كشف المواصلات", self.do_transport),
            ("🏨  تسكين إكسل", self.do_rooming_excel),
            ("🏨  تسكين PDF", self.do_rooming_pdf),
            ("⛺  خيام المخيمات", self.do_camps),
            None,
            ("🪪  بطاقات الحجّاج", self.do_badges),
            ("🏷  طباعة الاستيكرات (حقائب/غرف/أظرف)", self.do_stickers),
            ("🖼  طباعة الجوازات والتصاريح", self.do_print_images),
        ], icon=("report", WHITE))
        rep_mb.pack(side=RIGHT, padx=(4, 3))

        # 💰 المالية: الإحصاءات والملخّص المالي والمستندات المالية
        fin_mb = self._menubutton(bar, "المالية  ▾", [
            ("📊  إحصاءات وملخّص مالي", self.do_stats),
            ("📄  تصدير الإحصاءات والمالية PDF", self.do_stats_pdf),
            None,
            ("🧾  سند قبض (معاينة)", self._receipt_selected),
            ("🧾  فاتورة ضريبية (معاينة)",
             lambda: self._invoice_selected(electronic=False)),
            ("💳  فاتورة إلكترونية PEPPOL (معاينة)",
             lambda: self._invoice_selected(electronic=True)),
            ("📜  عقد خدمات حج (معاينة)", self._contract_selected),
        ], style="Ghost.TMenubutton", icon=("chart", INK))
        fin_mb.pack(side=RIGHT, padx=3)

        # 🛡 الحماية والنظام: النسخ الاحتياطية والحساب
        prot_items = [
            ("🛡  نسخة احتياطية الآن", self.do_backup_now),
            ("↩  استعادة نسخة احتياطية", self.do_restore),
        ]
        if self.session is not None:
            prot_items += [None,
                           ("🔑  تغيير كلمة المرور", self.change_password),
                           ("🗝  مفتاح استرداد جديد", self.new_recovery_key)]
        prot_mb = self._menubutton(bar, "الحماية  ▾", prot_items,
                                   style="Ghost.TMenubutton", icon=("shield", INK))
        prot_mb.pack(side=RIGHT, padx=3)

        # شريط التقدّم يُنشأ مخفيّاً ويظهر فقط أثناء العمليات الطويلة
        self.progress = ttk.Progressbar(bar, mode="determinate", length=180)

        self._shadow_strip(self.root)     # ظلّ ناعم يفصل الشريط عمّا تحته

    def _shadow_strip(self, parent) -> None:
        """ظلّ متدرّج رفيع (ثلاثة أسطر) يوحي بعمق تحت الشريط."""
        for col in ("#CDC4B2", "#DED6C7", "#ECE6DB"):
            tk.Frame(parent, bg=col, height=1).pack(fill=X)

    # الحقول القابلة للفلترة بقائمة منسدلة (تُملأ قيمها من البيانات)
    _FILTER_FIELDS = (
        ("hotel", "الفندق"),
        ("room_type", "نوع الغرفة"),
        ("nationality_ar", "الجنسية"),
        ("airline", "الطيران"),
        ("sex", "الجنس"),
        ("executive_service", "التنفيذي"),
        ("transport", "المواصلات"),
        ("wheelchair", "كرسي متحرك"),
        ("notes", "ملاحظات"),
    )
    _ALL = "الكل"
    # حقول يبحث فيها مربّع البحث الحر
    _SEARCH_KEYS = (
        "full_name_ar", "full_name_en", "passport_number", "phone",
        "family_number", "reference_number", "room_number",
    )

    # عدد القوائم المنسدلة في الصف الأول (بجوار البحث)؛ الباقي في صف ثانٍ
    _FILTERS_ROW1 = 3

    # الأعمدة المتاحة للترتيب حسبها (المفتاح، العنوان)
    _SORT_NONE = "— بدون ترتيب —"
    _SORT_FIELDS = (
        ("full_name_ar", "اسم الحاج بالعربي"),
        ("family_number", "رقم العائلة"),
        ("hotel", "الفندق"),
        ("room_type", "نوع الغرفة"),
        ("room_number", "رقم الغرفة"),
        ("nationality_ar", "الجنسية"),
        ("airline", "الطيران"),
        ("birth_date", "تاريخ الميلاد"),
        ("remaining_amount", "المبلغ المتبقي"),
    )

    def _build_filters(self) -> None:
        outer = ttk.Frame(self.root, style="Toolbar.TFrame", padding=(16, 0, 16, 8))
        outer.pack(fill=X)
        row1 = ttk.Frame(outer, style="Toolbar.TFrame")
        row1.pack(fill=X)

        # الأزرار أقصى يسار
        self._icon_button(row1, "طباعة المعروض", self.do_print_filtered,
                          "Ghost.TButton", ("print", TEXT)).pack(side=LEFT, padx=3)
        self._icon_button(row1, "مسح الفلاتر", self.clear_filters,
                          "Ghost.TButton", ("clear", TEXT)).pack(side=LEFT, padx=3)
        self._build_columns_menubutton(row1).pack(side=LEFT, padx=3)
        self._build_view_menubutton(row1).pack(side=LEFT, padx=3)

        # ترتيب حسب: قائمة العمود + زر الاتجاه
        sort_box_frame = ttk.Frame(row1, style="Toolbar.TFrame")
        sort_box_frame.pack(side=LEFT, padx=(14, 0))
        self.sort_dir_btn = ttk.Button(sort_box_frame, text="▲", width=3,
                                       command=self._toggle_sort_dir, style="Act.TButton")
        self.sort_dir_btn.pack(side=LEFT)
        self.sort_var = StringVar(value=self._SORT_NONE)
        sort_box = ttk.Combobox(
            sort_box_frame, textvariable=self.sort_var, state="readonly", width=15,
            font=("Segoe UI", 9),
            values=[self._SORT_NONE, *(label for _k, label in self._SORT_FIELDS)],
        )
        sort_box.pack(side=LEFT, padx=(0, 4))
        sort_box.bind("<<ComboboxSelected>>", lambda _e: self._apply_sort())
        ttk.Label(sort_box_frame, text="ترتيب حسب", font=("Segoe UI", 9),
                  background=BG, foreground=TEXT).pack(side=LEFT, padx=(2, 0))

        # مربّع البحث الحر أقصى اليمين
        self.filter_search = StringVar()
        self.filter_search.trace_add("write", lambda *_a: self.refresh())
        entry = ttk.Entry(row1, textvariable=self.filter_search, width=20,
                          justify="right", font=("Segoe UI", 10))
        entry.pack(side=RIGHT, padx=(0, 6))
        self._search_entry = entry
        install_entry_editing(entry)
        ttk.Label(row1, text="🔍 بحث", font=("Segoe UI", 9),
                  background=BG, foreground=TEXT).pack(side=RIGHT, padx=(2, 4))

        # زرّ واحد يفتح لوحة كل الفلاتر (تجميع الفلاتر في قائمة واحدة)
        self._filter_btn = self._icon_button(
            row1, "الفلاتر  ▾", self._toggle_filter_panel, "Ghost.TButton",
            ("filter", TEXT))
        self._filter_btn.pack(side=RIGHT, padx=(0, 12))

        self._build_filter_panel()

    def _build_filter_panel(self) -> None:
        """لوحة منسدلة تجمع كل الفلاتر التسعة في مكان واحد."""
        panel = Toplevel(self.root)
        panel.withdraw()
        panel.overrideredirect(True)
        panel.configure(bg=BORDER)                 # إطار رفيع
        self._filter_panel = panel
        inner = ttk.Frame(panel, style="Panel.TFrame", padding=14)
        inner.pack(padx=1, pady=1)
        ttk.Label(inner, text="تصفية الكشف", font=("Segoe UI Semibold", 11),
                  foreground=TEXT, background=BG).grid(row=0, column=0, columnspan=6,
                                                       sticky="e", pady=(0, 8))

        self.filter_vars: dict[str, StringVar] = {}
        self.filter_boxes: dict[str, ttk.Combobox] = {}
        cols = 3
        for index, (key, label) in enumerate(self._FILTER_FIELDS):
            r = 1 + index // cols
            c = (index % cols) * 2
            ttk.Label(inner, text=label, font=("Segoe UI", 9), foreground=TEXT,
                      background=BG).grid(row=r, column=c + 1, sticky="e", padx=(10, 3),
                                          pady=3)
            var = StringVar(value=self._ALL)
            box = ttk.Combobox(inner, textvariable=var, state="readonly",
                               width=13, font=("Segoe UI", 9), values=[self._ALL])
            box.grid(row=r, column=c, sticky="e", pady=3)
            box.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
            self.filter_vars[key] = var
            self.filter_boxes[key] = box

        btns = ttk.Frame(inner, style="Panel.TFrame")
        btns.grid(row=99, column=0, columnspan=6, sticky="e", pady=(12, 0))
        self._icon_button(btns, "مسح الفلاتر", self.clear_filters, "Ghost.TButton",
                          ("clear", TEXT)).pack(side=RIGHT, padx=3)
        ttk.Button(btns, text="إغلاق", style="Ghost.TButton",
                   command=self._hide_filter_panel).pack(side=RIGHT, padx=3)
        panel.bind("<Escape>", lambda _e: self._hide_filter_panel())

    def _toggle_filter_panel(self) -> None:
        panel = self._filter_panel
        if panel.winfo_viewable():
            self._hide_filter_panel()
            return
        panel.update_idletasks()
        pw = panel.winfo_reqwidth()
        b = self._filter_btn
        x = b.winfo_rootx() + b.winfo_width() - pw     # محاذاة يمين الزرّ (RTL)
        y = b.winfo_rooty() + b.winfo_height() + 3
        x = max(6, x)
        panel.geometry(f"+{int(x)}+{int(y)}")
        panel.deiconify()
        panel.lift()
        panel.focus_set()

    def _hide_filter_panel(self) -> None:
        try:
            self._filter_panel.withdraw()
        except Exception:
            pass

    def _update_filter_button(self) -> None:
        """يعرض عدد الفلاتر النشطة على زرّ الفلاتر."""
        if not hasattr(self, "_filter_btn"):
            return
        active = sum(1 for v in self.filter_vars.values() if v.get() != self._ALL)
        text = f"الفلاتر ({active})  ▾" if active else "الفلاتر  ▾"
        self._filter_btn.configure(text=rtl(text))

    # ------------------------------------------------ مُختار الأعمدة والعرض
    # الأعمدة الأساسية التي يُبقيها زر «الأساسية فقط»
    _ESSENTIAL_COLS = (
        "serial", "family_number", "full_name_ar", "full_name_en", "phone",
        "hotel", "room_type", "room_number", "passport_number",
        "nationality_ar", "sex", "airline", "remaining_amount",
    )

    def _display_columns(self) -> tuple:
        """أعمدة الجدول بترتيب العرض (مسلسل أقصى اليمين)."""
        return tuple(reversed(FIELDS + DIAG_FIELDS))

    def _build_columns_menubutton(self, parent):
        mb = ttk.Menubutton(parent, text=rtl("الأعمدة ▾"),
                            style="Ghost.TMenubutton", direction="below")
        _img = self._icon("columns", TEXT)
        if _img is not None:
            mb.configure(image=_img, compound="right")
        menu = tk.Menu(mb, tearoff=0, font=("Segoe UI", 10))
        self._col_vars: dict[str, tk.BooleanVar] = {}
        for f in self._display_columns():
            var = tk.BooleanVar(value=f.key not in self._hidden_cols)
            self._col_vars[f.key] = var
            menu.add_checkbutton(label=f.label, variable=var,
                                 command=self._apply_columns)
        menu.add_separator()
        menu.add_command(label="إظهار كل الأعمدة",
                         command=lambda: self._preset_columns(None))
        menu.add_command(label="الأعمدة الأساسية فقط",
                         command=lambda: self._preset_columns(self._ESSENTIAL_COLS))
        mb["menu"] = menu
        self._menus.append(menu)
        return mb

    def _preset_columns(self, keep) -> None:
        """يضبط الأعمدة الظاهرة: keep=None يُظهر الكل، وإلا يُبقي المجموعة فقط."""
        for key, var in self._col_vars.items():
            var.set(True if keep is None else key in keep)
        self._apply_columns()

    def _apply_columns(self) -> None:
        """يطبّق الأعمدة الظاهرة على الجدول ويحفظها."""
        self._hidden_cols = {k for k, v in self._col_vars.items() if not v.get()}
        visible = [f.key for f in self.columns if f.key not in self._hidden_cols]
        if not visible:                       # لا نُخفي كل الأعمدة
            visible = ["serial"]
            self._col_vars["serial"].set(True)
            self._hidden_cols.discard("serial")
        try:
            self.tree["displaycolumns"] = visible
        except Exception:
            pass
        self._save_ui_settings()

    def _build_view_menubutton(self, parent):
        mb = ttk.Menubutton(parent, text=rtl("العرض ▾"),
                            style="Ghost.TMenubutton", direction="below")
        _img = self._icon("gear", TEXT)
        if _img is not None:
            mb.configure(image=_img, compound="right")
        menu = tk.Menu(mb, tearoff=0, font=("Segoe UI", 10))
        self._density_var = tk.StringVar(value=self._density)
        dmenu = tk.Menu(menu, tearoff=0, font=("Segoe UI", 10))
        for name in self._DENSITY:
            dmenu.add_radiobutton(label=name, value=name,
                                  variable=self._density_var,
                                  command=self._on_density_change)
        menu.add_cascade(label="كثافة الصفوف", menu=dmenu)
        self._fontsize_var = tk.StringVar(value=self._font_size)
        fmenu = tk.Menu(menu, tearoff=0, font=("Segoe UI", 10))
        for name in self._FONT_SIZES:
            fmenu.add_radiobutton(label=name, value=name,
                                  variable=self._fontsize_var,
                                  command=self._on_font_change)
        menu.add_cascade(label="حجم الخط", menu=fmenu)
        menu.add_separator()
        self._theme_var = tk.StringVar(value=self._theme)
        tmenu = tk.Menu(menu, tearoff=0, font=("Segoe UI", 10))
        for name in THEMES:
            tmenu.add_radiobutton(label=name, value=name, variable=self._theme_var,
                                  command=self._on_theme_change)
        menu.add_cascade(label="الوضع (فاتح/داكن)", menu=tmenu)
        mb["menu"] = menu
        self._menus += [menu, dmenu, fmenu, tmenu]
        return mb

    def _on_theme_change(self) -> None:
        self._theme = self._theme_var.get()
        self._save_ui_settings()
        messagebox.showinfo(
            "الوضع",
            f"سيُطبَّق الوضع «{self._theme}» عند إعادة تشغيل البرنامج.")

    def _on_density_change(self) -> None:
        self._density = self._density_var.get()
        self._apply_table_style()
        self._save_ui_settings()

    def _on_font_change(self) -> None:
        self._font_size = self._fontsize_var.get()
        self._apply_table_style()
        self._save_ui_settings()

    def _save_ui_settings(self) -> None:
        """يحفظ حجم النافذة والأعمدة والكثافة والخط لتُستعاد لاحقاً."""
        try:
            geom = self.root.winfo_geometry()
        except Exception:
            geom = self._ui.get("geometry", "")
        self._ui.update({
            "geometry": geom,
            "hidden_columns": sorted(self._hidden_cols),
            "density": self._density,
            "font_size": self._font_size,
            "theme": getattr(self, "_theme", "فاتح"),
        })
        self._settings["ui"] = self._ui
        try:
            save_settings(self._settings)
        except OSError:
            pass

    # ------------------------------------------------ اختصارات لوحة المفاتيح
    def _bind_shortcuts(self) -> None:
        self.root.bind("<Control-f>", lambda _e: self._focus_search())
        self.root.bind("<Control-F>", lambda _e: self._focus_search())
        self.root.bind("<Control-n>", lambda _e: self.add_manual())
        self.root.bind("<Control-N>", lambda _e: self.add_manual())
        self.root.bind("<Control-p>", lambda _e: self.do_print_filtered())
        self.root.bind("<Control-P>", lambda _e: self.do_print_filtered())
        self.tree.bind("<Delete>", lambda _e: self.delete_selected())

    def _focus_search(self) -> str:
        try:
            self._search_entry.focus_set()
            self._search_entry.select_range(0, "end")
        except Exception:
            pass
        return "break"

    # ------------------------------------------------ قائمة يمين الفأرة
    def _on_row_hover(self, event) -> None:
        """يميّز صفّ الجدول تحت مؤشّر الفأرة (بلا طمس صفوف التنبيه أو التحديد)."""
        iid = self.tree.identify_row(event.y)
        if iid == self._hover_iid:
            return
        self._clear_hover()
        if iid and iid not in self.tree.selection():
            cur = self.tree.item(iid, "tags")
            if cur and cur[0] == "warn":        # نُبقي تمييز التنبيه
                return
            self._hover_prev = cur
            self.tree.item(iid, tags=("hover",))
            self._hover_iid = iid

    def _clear_hover(self) -> None:
        if self._hover_iid and self.tree.exists(self._hover_iid):
            self.tree.item(self._hover_iid, tags=self._hover_prev)
        self._hover_iid = None

    def _show_row_menu(self, event) -> None:
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        if iid not in self.tree.selection():
            self.tree.selection_set(iid)
        self._row_menu.tk_popup(event.x_root, event.y_root)

    def _copy_field(self, key: str) -> None:
        idxs = self._selected_indices()
        if not idxs:
            return
        value = str(getattr(self.records[idxs[0]], key, "") or "").strip()
        if value:
            self.root.clipboard_clear()
            self.root.clipboard_append(value)
            self.set_status(f"نُسخ: {value}", ok=True)

    def _filter_value(self, rec: PassportData, key: str) -> str:
        """القيمة القابلة للمقارنة في الفلتر.

        فلتر نوع الغرفة يقارن بالفئة فقط (مفرد/ثنائي/ثلاثي/رباعي) دون رقم
        الغرفة، فـ'رباعية 1' و'رباعية 9' كلاهما تحت 'رباعي'.
        """
        raw = str(getattr(rec, key, "") or "").strip()
        if key == "room_type":
            return room_category(raw)
        return raw

    def _sort_filter_values(self, key: str, values: set) -> list:
        """يرتّب قيم القائمة: فئات الغرف بترتيب السعة، والبقية أبجدياً."""
        if key == "room_type":
            order = {c: i for i, c in enumerate(ROOM_CATEGORIES)}
            return sorted(values, key=lambda v: order.get(v, 99))
        return sorted(values)

    def _populate_filters(self) -> None:
        """يملأ قيم القوائم المنسدلة من البيانات، مع الإبقاء على الاختيار الحالي."""
        for key, _label in self._FILTER_FIELDS:
            values = {self._filter_value(rec, key) for rec in self.records}
            values.discard("")
            box = self.filter_boxes[key]
            box["values"] = [self._ALL, *self._sort_filter_values(key, values)]
            # إن اختفت القيمة المختارة بعد تغيّر البيانات نرجع إلى "الكل"
            current = self.filter_vars[key].get()
            if current != self._ALL and current not in values:
                self.filter_vars[key].set(self._ALL)

    def clear_filters(self) -> None:
        """يعيد كل الفلاتر إلى وضع الكل ويمسح البحث."""
        for var in self.filter_vars.values():
            var.set(self._ALL)
        self.filter_search.set("")
        self.refresh()

    def _row_matches(self, rec: PassportData) -> bool:
        """هل يطابق السجل الفلاتر النشطة كلها؟"""
        for key, _label in self._FILTER_FIELDS:
            chosen = self.filter_vars[key].get()
            if chosen != self._ALL and self._filter_value(rec, key) != chosen:
                return False
        query = self.filter_search.get().strip().lower()
        if query:
            haystack = " ".join(
                str(getattr(rec, k, "") or "") for k in self._SEARCH_KEYS
            ).lower()
            if query not in haystack:
                return False
        return True

    def _filter_active(self) -> bool:
        return bool(self.filter_search.get().strip()) or any(
            v.get() != self._ALL for v in self.filter_vars.values()
        )

    def _visible_records(self) -> list[PassportData]:
        """السجلات المطابقة للفلتر الحالي، بترتيب العرض (يحترم الترتيب)."""
        return [r for r in self._ordered() if self._row_matches(r)]

    # ------------------------------------------------------------ الترتيب
    def _sort_key(self, rec: PassportData, key: str):
        """مفتاح ترتيب واعٍ بالنوع: أرقام كأرقام، والغرف بالسعة ثم الرقم."""
        raw = (compute_remaining(rec) if key == "remaining_amount"
               else str(getattr(rec, key, "") or "").strip())
        empty = raw == ""       # الفارغ يأتي أخيراً دائماً
        if key in MONEY_KEYS:
            amount = parse_amount(raw)
            return (empty, amount if amount is not None else 0.0, "")
        if key == "room_type":
            rtype = str(getattr(rec, "room_type", "") or "")
            num = str(getattr(rec, "room_number", "") or "").strip() or room_number_in_type(rtype)
            digits = re.match(r"(\d+)", num)
            return (empty, room_capacity(rtype) if rtype else 99,
                    int(digits.group(1)) if digits else 10 ** 9, num)
        if key in ("family_number", "room_number", "reference_number"):
            lead = re.match(r"^\s*(\d+)", raw)
            if lead:
                return (empty, int(lead.group(1)), raw.lower())
        return (empty, 0, raw.lower())

    def _ordered(self, records: list | None = None) -> list:
        """السجلات بترتيب العرض الحالي — دون المساس بترتيب self.records الأصلي.

        بلا عمود ترتيب يعيدها كما هي (الترتيب الأصلي)، فاختيار «بدون ترتيب»
        يعيد الجدول كما كان.
        """
        records = self.records if records is None else records
        if not self.sort_field:
            return list(records)
        return sorted(records, key=lambda r: self._sort_key(r, self.sort_field),
                      reverse=self.sort_desc)

    def _apply_sort(self) -> None:
        """يضبط عمود الترتيب كعرض فقط (لا يعدّل السجلات ولا يحفظ)."""
        label = self.sort_var.get()
        self.sort_field = next((k for k, lbl in self._SORT_FIELDS if lbl == label), None)
        self.refresh()
        if self.sort_field:
            direction = "تنازلي" if self.sort_desc else "تصاعدي"
            self.set_status(f"العرض مرتّب حسب: {label} ({direction})")
        else:
            self.set_status("أُلغي الترتيب — عاد الكشف إلى ترتيبه الأصلي")

    def _toggle_sort_dir(self) -> None:
        """يعكس اتجاه الترتيب ويعيد تطبيقه."""
        self.sort_desc = not self.sort_desc
        self.sort_dir_btn.config(text="▼" if self.sort_desc else "▲")
        self._apply_sort()

    def _sort_by_column(self, key: str) -> None:
        """الترتيب بالنقر على رأس العمود (يعكس الاتجاه عند تكرار العمود)."""
        if self.sort_field == key:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_field = key
            self.sort_desc = False
        label = next((lbl for k, lbl in self._SORT_FIELDS if k == key), None)
        self.sort_var.set(label or self._SORT_NONE)   # مزامنة القائمة إن أمكن
        self.sort_dir_btn.config(text="▼" if self.sort_desc else "▲")
        self.refresh()
        col_label = self._col_labels.get(key, key)
        direction = "تنازلي" if self.sort_desc else "تصاعدي"
        self.set_status(f"العرض مرتّب حسب: {col_label} ({direction})")

    def _update_heading_arrows(self) -> None:
        """يُظهر سهم الاتجاه على رأس عمود الترتيب النشط فقط."""
        if not hasattr(self, "_col_labels"):
            return
        for f in self.columns:
            base = self._col_labels[f.key]
            if self.sort_field == f.key:
                base = f"{base}  {'▼' if self.sort_desc else '▲'}"
            self.tree.heading(f.key, text=base)

    def _build_table(self) -> None:
        wrap = ttk.Frame(self.root, padding=(16, 4, 16, 8))
        wrap.pack(fill=BOTH, expand=True)

        # الأعمدة معكوسة ليظهر "مسلسل" أقصى اليمين كما في الكشف الورقي
        self.columns = tuple(reversed(FIELDS + DIAG_FIELDS))
        self._col_labels = {f.key: f.label for f in self.columns}
        cols = [f.key for f in self.columns]
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="extended")

        for f in self.columns:
            # النقر على رأس العمود يرتّب حسبه (مع سهم اتجاه)
            self.tree.heading(f.key, text=f.label,
                              command=lambda k=f.key: self._sort_by_column(k))
            self.tree.column(f.key, width=max(f.width * 9, 70), anchor="center",
                             stretch=False)

        vs = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        hs = ttk.Scrollbar(wrap, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)

        vs.pack(side=RIGHT, fill=Y)
        hs.pack(side="bottom", fill=X)
        self.tree.pack(fill=BOTH, expand=True)

        # تخطيط متناوب الألوان + تمييز صفوف التنبيه + تمييز صفّ مرور الفأرة
        self.tree.tag_configure("even", background=PANEL)
        self.tree.tag_configure("odd", background=ROW_ALT)
        self.tree.tag_configure("warn", background=WARN_BG, foreground="#5A4A2E")
        self.tree.tag_configure("hover", background=HOVER_BG)
        self.tree.bind("<Double-1>", lambda _e: self.edit_selected())
        self._hover_iid = None
        self._hover_prev: tuple = ()
        self.tree.bind("<Motion>", self._on_row_hover)
        self.tree.bind("<Leave>", lambda _e: self._clear_hover())

        # قائمة يمين الفأرة على الصف
        self._row_menu = tk.Menu(self.tree, tearoff=0, font=("Segoe UI", 10))
        self._row_menu.add_command(label="✏️  تعديل السجل", command=self.edit_selected)
        self._row_menu.add_command(label="✏️  تعديل جماعي للمحدّدين",
                                   command=self.bulk_edit_selected)
        self._row_menu.add_command(label="🗑  حذف المحدد", command=self.delete_selected)
        self._row_menu.add_separator()
        self._row_menu.add_command(label="نسخ اسم الحاج",
                                   command=lambda: self._copy_field("full_name_ar"))
        self._row_menu.add_command(label="نسخ رقم الجواز",
                                   command=lambda: self._copy_field("passport_number"))
        self._row_menu.add_separator()
        self._row_menu.add_command(label="🧾  سند قبض (معاينة)",
                                   command=self._receipt_selected)
        self._row_menu.add_command(
            label="🧾  فاتورة ضريبية (معاينة)",
            command=lambda: self._invoice_selected(electronic=False))
        self._row_menu.add_command(
            label="💳  فاتورة إلكترونية PEPPOL (معاينة)",
            command=lambda: self._invoice_selected(electronic=True))
        self._row_menu.add_command(label="📜  عقد خدمات حج (معاينة)",
                                   command=self._contract_selected)
        self.tree.bind("<Button-3>", self._show_row_menu)

        # حالة فارغة أنيقة تظهر حين لا بيانات (تُخفى عند وجود سجلات)
        self._empty = ttk.Frame(wrap, style="Toolbar.TFrame", padding=20)
        self._empty_logo = logo_image(self.root, width=120)
        if self._empty_logo is not None:
            ttk.Label(self._empty, image=self._empty_logo,
                      background=BG).pack(pady=(0, 12))
        ttk.Label(self._empty, text="لا يوجد حجّاج بعد", background=BG,
                  font=("Segoe UI Semibold", 16), foreground=TEXT).pack()
        ttk.Label(self._empty, text="ابدأ بإضافة صور الجوازات أو استيراد ملف إكسل",
                  background=BG, font=("Segoe UI", 10), foreground=MUTED).pack(
            pady=(4, 14))
        eb = ttk.Frame(self._empty, style="Toolbar.TFrame")
        eb.pack()
        ttk.Button(eb, text=rtl("📷  إضافة جوازات"), style="Primary.TButton",
                   command=self.add_images).pack(side=RIGHT, padx=4)
        ttk.Button(eb, text=rtl("📁  استيراد إكسل"), style="Ghost.TButton",
                   command=self.import_from_excel).pack(side=RIGHT, padx=4)

        # تطبيق الأعمدة الظاهرة المحفوظة
        self._apply_columns()

        # الأعمدة أعرض من الشاشة، وTk يبدأ العرض من اليسار. في كشف عربي
        # يجب أن يبدأ من اليمين حيث عمود "مسلسل" واسم الحاج، لا من
        # "ملاحظات" و"الملف المصدر" في آخر الكشف.
        self._scrolled_home = False
        self.tree.bind("<Configure>", lambda _e: self._scroll_to_start(), add="+")

    def _scroll_to_start(self) -> None:
        """يضبط العرض الأفقي على أقصى اليمين، مرة واحدة بعد أول رسم.

        التمرير لا يعمل قبل أن يرسم Tk الجدول بعرضه الحقيقي، ولا نكرّره
        بعد نجاحه حتى لا نُلغي تمرير المستخدم كلما غيّر حجم النافذة.
        """
        if self._scrolled_home or not self.records:
            return
        if self.tree.winfo_width() <= 1:        # لم تُرسم النافذة بعد
            return
        self._scrolled_home = True
        self.tree.xview_moveto(1.0)

    def _build_status(self) -> None:
        self.status = StringVar(value="جاهز — أضف صور الجوازات أو استورد ملف إكسل للبدء")
        # خطّ فاصل علوي رفيع يمنح شريط الحالة عمقاً
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill=X)
        bar = ttk.Frame(self.root, padding=(16, 7))
        bar.pack(fill=X)
        # مؤشّر حالة ملوّن (نقطة) يمين النص
        self._status_dot = tk.Label(bar, text="●", font=("Segoe UI", 11),
                                    fg="#8C857A", bg=BG)
        self._status_dot.pack(side=RIGHT, padx=(6, 0))
        self.status_label = ttk.Label(bar, textvariable=self.status,
                                      font=("Segoe UI", 10), foreground="#444")
        self.status_label.pack(side=RIGHT)
        self.count_label = ttk.Label(bar, text="", font=("Segoe UI Semibold", 11),
                                     foreground=TEXT)
        self.count_label.pack(side=LEFT)
        ttk.Label(bar, text="💾 الحفظ تلقائي", font=("Segoe UI", 9),
                  foreground=MUTED).pack(side=LEFT, padx=12)

    # ------------------------------------------------------------ حفظ واستعادة
    def _load_saved_data(self) -> None:
        """يستعيد الكشف المحفوظ من الجلسة السابقة."""
        try:
            records, note = load_records(self.data_path, self.session)
        except Exception as exc:
            self.set_status(f"تعذّر تحميل البيانات المحفوظة: {exc}", warn=True)
            return

        self.records = records
        self.refresh()

        if note:
            messagebox.showwarning("ملف البيانات", note)
            self.set_status("تم البدء بعد مشكلة في ملف البيانات", warn=True)
        elif records:
            self.set_status(f"تمت استعادة {len(records)} حاج من آخر جلسة")

    def save_data(self) -> bool:
        """يحفظ الكشف الحالي. يعيد True عند النجاح."""
        try:
            save_records(self.records, self.data_path, self.session)
            return True
        except Exception as exc:
            self.set_status(f"تعذّر الحفظ: {exc}", warn=True)
            messagebox.showerror(
                "تعذّر الحفظ",
                f"لم يتمكن البرنامج من حفظ البيانات:\n\n{exc}\n\n"
                f"المسار: {self.data_path}\n\n"
                "صدّر نسخة إكسل الآن حتى لا تفقد العمل.",
            )
            return False

    def _on_close(self) -> None:
        self._save_ui_settings()          # يحفظ حجم النافذة والأعمدة والعرض
        try:                              # لقطة نسخة احتياطية عند كل إغلاق
            if self.records:
                from .storage import write_snapshot
                write_snapshot(self.records, self.session)
        except Exception:
            pass
        if self.save_data():
            self.root.destroy()
            return
        # الحفظ فشل — لا نغلق دون تحذير المستخدم من ضياع العمل
        if messagebox.askyesno(
            "الخروج دون حفظ",
            "فشل حفظ البيانات. الخروج الآن يعني فقدان التعديلات.\n\nهل تريد الخروج فعلاً؟",
        ):
            self.root.destroy()

    # ------------------------------------------------------------------ أدوات
    def set_status(self, text: str, *, warn: bool = False, ok: bool = False) -> None:
        if warn:
            fg, icon = AMBER_FG, "⚠"
        elif ok:
            fg, icon = SUCCESS_FG, "✓"
        else:
            fg, icon = TEXT, "•"
        self.status.set(f"{icon}  {text}")
        self.status_label.configure(foreground=fg)
        if hasattr(self, "_status_dot"):
            self._status_dot.configure(fg=fg)

    def toast(self, message: str, *, kind: str = "info", ms: int = 2600) -> None:
        """إشعار منبثق سريع أسفل يمين النافذة، يختفي تلقائياً."""
        try:
            if not self.root.winfo_viewable():
                return                      # لا إشعارات ونحن مخفيّون (الاختبارات)
        except Exception:
            return
        bg = {"success": SUCCESS_FG, "warn": AMBER_FG}.get(kind, "#2B2B2B")
        icon = {"success": "✓", "warn": "⚠"}.get(kind, "•")
        try:
            win = Toplevel(self.root)
            win.overrideredirect(True)
            win.configure(bg=bg)
            win.attributes("-topmost", True)
            tk.Label(win, text=f"   {icon}   {message}   ", bg=bg, fg="white",
                     font=("Segoe UI Semibold", 10)).pack(ipady=9)
            win.update_idletasks()
            rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
            rw, rh = self.root.winfo_width(), self.root.winfo_height()
            ww, wh = win.winfo_width(), win.winfo_height()
            win.geometry(f"+{rx + rw - ww - 26}+{ry + rh - wh - 44}")
            win.after(ms, win.destroy)
        except Exception:
            pass

    def refresh(self) -> None:
        """يعيد رسم الجدول من self.records مطبّقاً الفلاتر النشطة.

        رقم الصف (iid) يبقى فهرس السجل الأصلي دائماً، فلا يختلّ التعديل ولا
        الحذف عند إخفاء صفوف بالفلترة. والمسلسل المعروض يبقى على ترتيب
        السجل الأصلي في الكشف الكامل.
        """
        self._populate_filters()
        self.tree.delete(*self.tree.get_children())
        # iid يبقى فهرس السجل في self.records الأصلي، فلا يختلّ التعديل والحذف
        # مهما تغيّر ترتيب العرض أو أُخفيت صفوف بالفلترة.
        orig_index = {id(rec): i for i, rec in enumerate(self.records)}
        shown = 0
        for rec in self._ordered():
            if not self._row_matches(rec):
                continue
            # المسلسل يعاد ترقيمه 1..ن على الصفوف المعروضة بعد الفلترة والترتيب
            shown += 1
            data = row_dict(rec, shown)
            values = [data.get(f.key, "") for f in self.columns]
            # صفّ التنبيه بلونه، والبقية متناوبة الألوان
            tag = "warn" if data.get("warnings") else ("odd" if shown % 2 else "even")
            self.tree.insert("", END, iid=str(orig_index[id(rec)]), values=values,
                             tags=(tag,))

        total = len(self.records)
        if self._filter_active() and shown != total:
            self.count_label.configure(text=f"المعروض: {shown} من {total}")
        else:
            self.count_label.configure(text=f"إجمالي الحجاج: {total}")

        # حالة فارغة: نُظهر اللوحة الترحيبية فوق الجدول حين لا سجلات
        if hasattr(self, "_empty"):
            if self.records:
                self._empty.place_forget()
            else:
                self._empty.place(relx=0.5, rely=0.42, anchor="center")

        self._update_heading_arrows()
        self._update_filter_button()
        self._scroll_to_start()

    def _selected_indices(self) -> list[int]:
        return sorted(int(i) for i in self.tree.selection())

    # ------------------------------------------------------------ إضافة يدوية
    def add_manual(self) -> None:
        """يفتح سجلاً فارغاً لإدخال بيانات حاج يدوياً."""
        record = PassportData(source_file="إدخال يدوي")
        EditDialog(
            self.root, record, on_save=self._after_manual_add,
            title="إضافة حاج جديد", save_text="إضافة", session=self.session,
        )

    def _after_manual_add(self, record: PassportData) -> None:
        self.records.append(record)
        self.refresh()
        self.save_data()
        # ننتقل إلى السجل الجديد ونحدّده ليراه المستخدم مباشرة
        last = str(len(self.records) - 1)
        self.tree.selection_set(last)
        self.tree.see(last)
        name = record.full_name_ar or record.full_name_en or "بدون اسم"
        self.set_status(f"تمت إضافة: {name}", ok=True)
        self.toast(f"تمت إضافة: {name}", kind="success")

    # ------------------------------------------------------------- إضافة صور
    def add_images(self) -> None:
        if not self.tesseract_path:
            self.tesseract_path = configure_tesseract()
            if not self.tesseract_path:
                messagebox.showerror(
                    "Tesseract غير موجود",
                    "برنامج Tesseract OCR غير مثبّت.\n\n"
                    "ثبّته من:\nhttps://github.com/UB-Mannheim/tesseract/wiki\n\n"
                    "أو عبر الأمر:\nwinget install UB-Mannheim.TesseractOCR",
                )
                return

        paths = filedialog.askopenfilenames(
            title="اختر صور أو ملفات PDF للجوازات", filetypes=SCAN_TYPES
        )
        if not paths:
            return

        self._progress_show(len(paths))
        self.set_status(f"جارٍ قراءة {len(paths)} ملف…")
        self._disable_toolbar(True)
        self._scan_state = {"failures": [], "notes": [], "added": 0,
                            "processed": 0}

        # القراءة في خيط منفصل حتى لا تتجمّد الواجهة
        threading.Thread(target=self._scan_worker, args=(list(paths),), daemon=True).start()
        self.root.after(100, self._drain_results, len(paths))

    def _progress_show(self, maximum: int) -> None:
        """يُظهر شريط التقدّم (يميناً بعد شريط الحالة) ويهيّئه لعملية جديدة."""
        self.progress.configure(maximum=max(1, maximum), value=0)
        if not self.progress.winfo_manager():        # ليس مُدرَجاً بعد
            self.progress.pack(side=LEFT, padx=8)
        self.progress.update_idletasks()

    def _progress_hide(self) -> None:
        """يُخفي شريط التقدّم عند انتهاء العملية."""
        self.progress.configure(value=0)
        self.progress.pack_forget()

    def _scan_worker(self, paths: list[str]) -> None:
        """يقرأ كل ملف (صورة أو PDF) ويرسل النتائج عبر قائمة الانتظار."""
        for p in paths:
            name = Path(p).name
            try:
                if Path(p).suffix.lower() == ".pdf":
                    # صفحة PDF واحدة قد تحمل جوازاً، والملف قد يحمل عدة جوازات
                    def report(page, total, _n=name):
                        self.results.put(("progress", f"{_n}: صفحة {page}/{total}"))

                    records, notes = extract_from_pdf(p, progress=report)
                    for note in notes:
                        self.results.put(("note", f"{name} — {note}"))
                    self.results.put(("ok", (records, p)))
                else:
                    self.results.put(("ok", ([extract_passport(p)], p)))
            except (MRZError, PDFError) as exc:
                self.results.put(("fail", (name, str(exc))))
            except Exception:
                self.results.put(("fail", (name, traceback.format_exc(limit=2))))
            self.results.put(("step", None))
        self.results.put(("done", None))

    def _attach_source_image(self, record: PassportData, source: str) -> None:
        """يحفظ ملف المصدر (صورة الجواز أو PDF جواز واحد) كصورة جواز للحاج.

        يجري على خيط الواجهة حيث تتوفّر الجلسة للتشفير. فشل الحفظ لا يمنع
        إضافة السجل.
        """
        from . import images as imgmod
        try:
            if not record.image_id:
                record.image_id = imgmod.new_image_id()
            imgmod.save_image(record.image_id, imgmod.PASSPORT, source, self.session)
        except Exception:
            pass

    def _drain_results(self, total: int) -> None:
        """يُستدعى في خيط الواجهة لسحب النتائج من الخيط الخلفي."""
        state = self._scan_state
        finished = False

        while True:
            try:
                kind, payload = self.results.get_nowait()
            except queue.Empty:
                break
            if kind == "ok":
                recs, source = payload
                self.records.extend(recs)
                state["added"] += len(recs)
                # ملف واحد أنتج حاجاً واحداً -> نحفظ صورته كصورة جواز تلقائياً
                if source and len(recs) == 1:
                    self._attach_source_image(recs[0], source)
            elif kind == "fail":
                state["failures"].append(payload)
            elif kind == "note":
                state["notes"].append(payload)
            elif kind == "progress":
                self.set_status(f"جارٍ القراءة… {payload}")
            elif kind == "step":
                state["processed"] = state.get("processed", 0) + 1
                # تعيين القيمة صراحةً وإجبار إعادة الرسم فوراً ليتحرّك الشريط
                self.progress.configure(value=state["processed"])
                self.progress.update_idletasks()
            else:
                finished = True

        self.refresh()

        if not finished:
            self.root.after(100, self._drain_results, total)
            return

        self._disable_toolbar(False)
        self._progress_hide()

        failures, notes, added = state["failures"], state["notes"], state["added"]
        if added:
            self.save_data()
        ok_files = total - len(failures)
        # نحسب التحذيرات على السجلات المضافة الآن فقط، لا على الجدول كله
        unsure = sum(1 for r in self.records[-added:] if r.warnings) if added else 0

        msg = f"تمت قراءة {ok_files} من {total} ملف — أضيف {added} حاج"
        if unsure:
            msg += f" ({unsure} يحتاج مراجعة — مظلّل بالأصفر)"
        self.set_status(msg, warn=bool(failures or unsure))

        if failures:
            detail = "\n\n".join(f"• {n}\n{e}" for n, e in failures[:8])
            if len(failures) > 8:
                detail += f"\n\n… و{len(failures) - 8} ملف آخر"
            messagebox.showwarning("ملفات تعذّرت قراءتها", detail)
        elif notes:
            messagebox.showinfo("ملاحظات القراءة", "\n\n".join(notes[:12]))

    def _disable_toolbar(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        for child in self.root.winfo_children():
            for w in child.winfo_children():
                if isinstance(w, (ttk.Button, ttk.Menubutton)):
                    w.configure(state=state)

    # ----------------------------------------------------------- إكسل / PDF
    def import_from_excel(self) -> None:
        path = filedialog.askopenfilename(title="اختر ملف الإكسل", filetypes=EXCEL_TYPES)
        if not path:
            return
        try:
            records, notes = import_excel(path)
        except Exception as exc:
            messagebox.showerror("خطأ في الاستيراد", f"تعذّر قراءة الملف:\n\n{exc}")
            return

        if not records:
            messagebox.showwarning("لا توجد بيانات", "\n\n".join(notes) or "الملف لا يحتوي بيانات.")
            return

        self.records.extend(records)
        self.refresh()
        self.save_data()
        self.set_status(f"تم استيراد {len(records)} سجل من {Path(path).name}", ok=True)

        # تنبيه ذكي: أرقام جوازات مكرّرة بعد الدمج (خطأ شائع)
        from .quality import duplicate_groups
        dups = duplicate_groups(self.records)
        if dups:
            notes = list(notes) + [
                f"⚠ تنبيه: {len(dups)} رقم جواز مكرّر بعد الدمج "
                "(مثل: " + "، ".join(list(dups)[:3]) + ").\n"
                "افتح «التقارير ← فحص جاهزية الكشف» لمراجعتها."
            ]
        if notes:
            messagebox.showinfo("ملاحظات الاستيراد", "\n\n".join(notes))

    def _default_name(self, ext: str) -> str:
        return f"كشف_الحجاج_{date.today().isoformat()}.{ext}"

    def _filter_title(self) -> str:
        """عنوان يصف الفلتر النشط، ليظهر في ترويسة الطباعة."""
        parts = []
        for key, label in self._FILTER_FIELDS:
            value = self.filter_vars[key].get()
            if value != self._ALL:
                parts.append(value)
        query = self.filter_search.get().strip()
        if query:
            parts.append(f"بحث: {query}")
        base = self._report_title("كشف الحجاج")
        return f"{base} — " + " • ".join(parts) if parts else base

    def do_print_filtered(self) -> None:
        """يطبع المعروض: المطابق للفلتر إن وُجد، وإلا الكشف كاملاً."""
        if not self._require_records():
            return
        records = self._visible_records()
        if not records:
            messagebox.showinfo("لا نتائج", "لا يوجد حاج مطابق للفلتر الحالي.")
            return

        # فصل الغرف يطبّق فقط حين يكون فلتر «نوع الغرفة» نشطاً؛ بقية الفلاتر
        # تطبع قائمة عادية غير مفصولة. أما فصل كامل الغرف فمن زر كشف التسكين.
        by_room = self.filter_vars["room_type"].get() != self._ALL

        scope = (f"سيُطبع {len(records)} حاجاً (المعروض حسب الفلتر)"
                 if self._filter_active()
                 else f"سيُطبع كامل الكشف ({len(records)} حاجاً)")
        if by_room:
            scope += "\nمفصولاً حسب الغرف"
        scope += "\n\nستُفتح معاينة الكشف — اطبعها (Ctrl+P) واختر الطابعة. متابعة؟"
        if not messagebox.askyesno("طباعة", scope):
            return

        import os
        import tempfile
        path = os.path.join(tempfile.gettempdir(),
                            f"hajj_print_{date.today().isoformat()}.pdf")
        try:
            export_pdf(records, path, title=self._filter_title(), group_by_room=by_room)
        except Exception as exc:
            messagebox.showerror("خطأ في التجهيز للطباعة", str(exc))
            return

        # نفتح المعاينة في عارض PDF؛ منها يطبع المستخدم ويختار الطابعة —
        # بلا نافذة «حفظ باسم» ولا طباعة صامتة.
        try:
            os.startfile(path)
        except OSError as exc:
            messagebox.showerror(
                "تعذّر فتح المعاينة",
                f"تعذّر فتح ملف الطباعة للمعاينة:\n{exc}\n\n"
                "تأكد من وجود تطبيق لفتح ملفات PDF.",
            )
            return
        self.set_status(
            f"فُتحت معاينة الطباعة ({len(records)} حاج) — اطبعها واختر الطابعة"
        )

    def do_print_images(self) -> None:
        """يجمع صور نوع مختار (جواز/هوية/تصريح/الكل) ويفتح معاينتها للطباعة."""
        if not self._require_records():
            return

        from . import images as imgmod
        from .transport import distinct_transports
        records = self._ordered()
        transports = distinct_transports(records)
        executives = sorted({str(r.executive_service or "").strip()
                             for r in records
                             if str(r.executive_service or "").strip()})
        choice = ImageKindDialog(self.root, transports=transports,
                                 executives=executives)
        self.root.wait_window(choice)
        if choice.kinds is None:            # أُلغِي
            return
        kinds = choice.kinds

        # نطاق الطباعة: كل المعروض / باص محدّد / خدمة تنفيذي (الجيمس) محدّدة
        scope_kind, scope_val = choice.scope
        if scope_kind == "transport":
            selected = [r for r in records
                        if str(r.transport or "").strip() == scope_val]
            scope_label = f"باص {scope_val}"
        elif scope_kind == "executive":
            selected = [r for r in records
                        if str(r.executive_service or "").strip() == scope_val]
            scope_label = f"خدمة {scope_val}"
        else:
            selected = records
            scope_label = ""
        if not selected:
            messagebox.showinfo("لا نتائج",
                                f"لا يوجد حاج ضمن «{scope_label}».")
            return

        from .pdf_io import export_passports_pdf
        import os
        import tempfile
        tmpdir = tempfile.mkdtemp(prefix="hajj_img_")
        entries: list[tuple[str, str]] = []
        for rec in selected:
            name = rec.full_name_ar or rec.full_name_en or rec.passport_number or "—"
            for kind in kinds:
                if not imgmod.has_image(rec.image_id, kind):
                    continue
                data = imgmod.load_image(rec.image_id, kind, self.session)
                if not data:
                    continue
                # ملف PDF مرفوع -> صفحة لكل ورقة؛ الصورة -> صفحة واحدة
                pages = imgmod.render_pages_png(data)
                for page_no, page_bytes in enumerate(pages, start=1):
                    img_path = os.path.join(tmpdir, f"{len(entries)}.img")
                    with open(img_path, "wb") as fh:
                        fh.write(page_bytes)
                    caption = name
                    if len(kinds) > 1:
                        caption += f" — {imgmod.KIND_LABELS[kind]}"
                    if len(pages) > 1:
                        caption += f" ({page_no})"
                    entries.append((caption, img_path))

        if not entries:
            messagebox.showinfo(
                "لا توجد صور",
                "لم تُرفَق صور من النوع المطلوب بعد.\n"
                "أضف الصور من زر «تعديل السجل» ← تبويب «الصور».",
            )
            return

        scope_note = f" ({scope_label})" if scope_label else ""
        if not messagebox.askyesno(
            "طباعة الصور",
            f"سيُجهَّز {len(entries)} صورة{scope_note} في ملف واحد، وتُفتح "
            "معاينته للطباعة.\n\nمتابعة؟",
        ):
            return

        tag = re.sub(r'[\\/:*?"<>|]+', "-", scope_label).strip() or "الكل"
        title = "صور الحجاج" + (f" — {scope_label}" if scope_label else "")
        pdf_path = os.path.join(tempfile.gettempdir(),
                                f"hajj_images_{tag}_{date.today().isoformat()}.pdf")
        try:
            export_passports_pdf(entries, pdf_path, title=title)
        except Exception as exc:
            messagebox.showerror("خطأ في تجهيز الصور", str(exc))
            return
        finally:
            # نحذف صور فكّ التشفير المؤقتة فوراً (الـ PDF يحوي نسخها)
            for _caption, img_path in entries:
                try:
                    os.remove(img_path)
                except OSError:
                    pass
            try:
                os.rmdir(tmpdir)
            except OSError:
                pass

        try:
            os.startfile(pdf_path)
        except OSError as exc:
            messagebox.showerror("تعذّر فتح المعاينة", str(exc))
            return
        self.set_status(f"فُتحت معاينة {len(entries)} صورة — اطبعها واختر الطابعة")

    def do_stickers(self) -> None:
        """يطبع استيكرات (للحقائب/الغرف/الأظرف) للمعروض — معاينة في العارض."""
        if not self._require_records():
            return
        records = self._visible_records()
        if not records:
            messagebox.showinfo("لا نتائج", "لا يوجد حاج مطابق للفلتر الحالي.")
            return
        dlg = StickersDialog(self.root)
        self.root.wait_window(dlg)
        if dlg.kind is None:                # أُلغِي
            return

        import os
        import tempfile
        from .pdf_io import STICKER_LABELS, export_stickers_pdf
        path = os.path.join(tempfile.gettempdir(),
                            f"stickers_{dlg.kind}_{date.today().isoformat()}.pdf")
        try:
            export_stickers_pdf(records, path, kind=dlg.kind,
                                company=self._company_info()["name_ar"],
                                season=self.season_year.get())
        except Exception as exc:
            messagebox.showerror("خطأ في الاستيكرات", str(exc))
            return
        try:
            os.startfile(path)
        except OSError as exc:
            messagebox.showerror("تعذّر فتح المعاينة", str(exc))
            return
        self.set_status(f"فُتحت معاينة {STICKER_LABELS[dlg.kind]} — اطبعها "
                        "واختر الطابعة")

    def do_airline(self) -> None:
        """يفتح نافذة كشف الطيران: تصدير إكسل/PDF ونسخ إدخالات أماديوس."""
        if not self._require_records():
            return
        records = self._visible_records()
        if not records:
            messagebox.showinfo("لا نتائج", "لا يوجد حاج مطابق للفلتر الحالي.")
            return
        AirlineDialog(self.root, records)

    def do_camps(self) -> None:
        """يفتح نافذة خيام المخيمات (منى/عرفة): إنشاء كل خيمة على حدة وتصديرها."""
        if not self._require_records():
            return
        records = self._visible_records()
        if not records:
            messagebox.showinfo("لا نتائج", "لا يوجد حاج مطابق للفلتر الحالي.")
            return
        CampsDialog(self.root, records)

    def do_quality_check(self) -> None:
        """يفتح فحص جاهزية الكشف (صلاحية الجواز، التكرار، النقص)."""
        if not self._require_records():
            return
        QualityDialog(self.root, lambda: self.records, self._focus_record,
                      travel_ref=self._travel_ref)

    def do_stats(self) -> None:
        """يفتح لوحة الإحصاءات والملخّص المالي."""
        if not self._require_records():
            return
        StatsDialog(self.root, list(self.records), season=self.season_year.get())

    def do_stats_pdf(self) -> None:
        """يصدّر تقرير الإحصاءات والملخّص المالي إلى PDF مباشرةً."""
        if not self._require_records():
            return
        path = filedialog.asksaveasfilename(
            title="حفظ الإحصاءات والملخّص المالي", defaultextension=".pdf",
            initialfile=f"إحصاءات_ومالية_{date.today().isoformat()}.pdf",
            filetypes=(("ملف PDF", "*.pdf"), ("كل الملفات", "*.*")))
        if not path:
            return
        from .pdf_io import export_stats_pdf
        try:
            export_stats_pdf(list(self.records), path, season=self.season_year.get())
        except PermissionError:
            messagebox.showerror("الملف مفتوح",
                                 "الملف مفتوح في برنامج آخر. أغلقه ثم أعد المحاولة.")
            return
        except Exception as exc:
            messagebox.showerror("خطأ في التصدير", str(exc))
            return
        self.set_status("تم تصدير الإحصاءات والملخّص المالي PDF", ok=True)
        self._offer_open(path)

    def do_backup_now(self) -> None:
        """يُنشئ نسخة احتياطية مؤرّخة (لقطة) للكشف الحالي."""
        if not self.records:
            messagebox.showinfo("لا بيانات", "لا يوجد ما يُنسخ احتياطياً.")
            return
        from .storage import write_snapshot
        try:
            write_snapshot(self.records, self.session)
        except Exception as exc:
            messagebox.showerror("تعذّرت النسخة الاحتياطية", str(exc))
            return
        self.set_status("تم إنشاء نسخة احتياطية مؤرّخة", ok=True)
        self.toast("تم إنشاء نسخة احتياطية", kind="success")

    def do_restore(self) -> None:
        """يفتح نافذة استعادة نسخة احتياطية."""
        from .storage import list_snapshots
        if not list_snapshots():
            messagebox.showinfo(
                "لا نسخ احتياطية",
                "لا توجد نسخ احتياطية بعد.\nأنشئ واحدة من «🛡 نسخة احتياطية الآن».")
            return
        RestoreDialog(self.root, self.session, self._do_restore)

    def _do_restore(self, records: list, label: str) -> None:
        if not messagebox.askyesno(
                "تأكيد الاستعادة",
                f"استبدال الكشف الحالي ({len(self.records)} سجلاً) بنسخة "
                f"{label} ({len(records)} سجلاً)؟\n\n"
                "سيُحفظ الكشف الحالي كنسخة قبل الاستبدال."):
            return
        try:                                    # لقطة أمان للحالة الراهنة
            from .storage import write_snapshot
            if self.records:
                write_snapshot(self.records, self.session)
        except Exception:
            pass
        self.records = records
        self.refresh()
        self.save_data()
        self.set_status(f"استُعيدت نسخة {label}: {len(records)} سجلاً", ok=True)
        self.toast(f"استُعيدت نسخة {label}", kind="success")

    def do_transport(self) -> None:
        """يفتح كشف المواصلات (توزيع حسب الباص)."""
        if not self._require_records():
            return
        records = self._visible_records()
        if not records:
            messagebox.showinfo("لا نتائج", "لا يوجد حاج مطابق للفلتر الحالي.")
            return
        TransportDialog(self.root, records)

    def do_badges(self) -> None:
        """يفتح نافذة بطاقات الحجّاج (وجه وخلفية، 5.2×8سم) لإدخال بيانات الخلفية."""
        if not self._require_records():
            return
        records = self._visible_records()
        if not records:
            messagebox.showinfo("لا نتائج", "لا يوجد حاج مطابق للفلتر الحالي.")
            return
        BadgesDialog(self.root, records, self.session)

    def bulk_edit_selected(self) -> None:
        """تعديل جماعي: يطبّق حقولاً على كل السجلات المحدّدة."""
        idxs = self._selected_indices()
        if len(idxs) < 2:
            messagebox.showinfo(
                "تعديل جماعي",
                "حدّد سجلين أو أكثر أولاً (استعمل Ctrl أو Shift للتحديد المتعدّد).")
            return

        def apply(changes: dict) -> None:
            n = self._apply_bulk(idxs, changes)
            self.refresh()
            self.save_data()
            self.set_status(f"عُدّل {n} سجلاً في {len(changes)} حقلاً", ok=True)
            self.toast(f"عُدّل {n} سجلاً", kind="success")

        BulkEditDialog(self.root, len(idxs), apply)

    def _apply_bulk(self, indices: list[int], changes: dict) -> int:
        """يطبّق التغييرات على السجلات المحدّدة (قابل للاختبار). يعيد العدد."""
        for i in indices:
            rec = self.records[i]
            for key, value in changes.items():
                setattr(rec, key, value)
        return len(indices)

    def _doc_number(self, rec, store_key: str, prefix: str, start: int) -> str:
        """رقم مستند ثابت لكل حاج، يُرقَّم تسلسلياً من عدّاد محفوظ.

        نفس الحاج يعطي نفس الرقم عند إعادة المعاينة (يُخزَّن مفتاحه بالجواز)."""
        key = (str(rec.passport_number or "").strip().upper()
               or (rec.full_name_ar or rec.full_name_en or "").strip())
        store = self._settings.setdefault(store_key, {})
        if key and key in store:
            n = int(store[key])
        else:
            n = int(self._settings.get(store_key + "_next", start))
            if key:
                store[key] = n
            self._settings[store_key + "_next"] = n + 1
            try:
                save_settings(self._settings)
            except Exception:
                pass
        return f"{prefix}{n:04d}"

    def _receipt_number(self, rec) -> str:
        """رقم سند القبض (عدّاد محفوظ يبدأ 0119)."""
        return self._doc_number(rec, "receipts", "", 119)

    def _company_info(self) -> dict:
        """بيانات الشركة المحفوظة (الاسم/الرقم الضريبي/الهاتف/العنوان)."""
        from .pdf_io import company_info
        return company_info(self._settings.get("company"))

    def _save_company(self, data: dict) -> None:
        """يحفظ بيانات الشركة ليُعاد استخدامها في الفواتير والعقود لاحقاً."""
        self._settings["company"] = dict(data)
        try:
            save_settings(self._settings)
        except Exception:
            pass

    def _load_programs(self):
        """يحمّل برامج الحملة الثلاثة من الإعدادات."""
        from .programs import load_programs
        return load_programs(self._settings)

    def _save_programs(self, progs) -> None:
        """يحفظ برامج الحملة الثلاثة في الإعدادات."""
        from .programs import programs_to_dicts
        self._settings["programs"] = programs_to_dicts(progs)
        try:
            save_settings(self._settings)
        except Exception:
            pass

    def do_programs(self) -> None:
        """يفتح نافذة إعداد برامج الحملة (الأول/الثاني/الثالث)."""
        ProgramsDialog(self.root, self)

    def _receipt_selected(self) -> None:
        """يفتح نافذة سند القبض للحاج المحدّد — **معاينة فقط** بلا حفظ مباشر."""
        rec = self._selected_record()
        if rec is not None:
            ReceiptDialog(self.root, rec, number=self._receipt_number(rec),
                          season=self.season_year.get())

    def _selected_record(self):
        """يعيد السجل المحدّد أو None (مع تنبيه) — لأوامر المستندات الفردية."""
        idxs = self._selected_indices()
        if not idxs:
            messagebox.showinfo("لم يتم التحديد", "اختر حاجاً من الجدول أولاً.")
            return None
        return self.records[idxs[0]]

    def _invoice_selected(self, *, electronic: bool = False) -> None:
        """يفتح نافذة الفاتورة (الضريبية أو الإلكترونية) — معاينة فقط."""
        rec = self._selected_record()
        if rec is None:
            return
        prefix = "EINV-" if electronic else "INV-"
        num = self._doc_number(rec, "invoices", prefix, 119)
        InvoiceDialog(self.root, rec, self, number=num,
                      season=self.season_year.get(), electronic=electronic)

    def _contract_selected(self) -> None:
        """يفتح نافذة عقد الخدمات للحاج المحدّد — معاينة فقط."""
        rec = self._selected_record()
        if rec is None:
            return
        num = self._doc_number(rec, "contracts", "CON-", 119)
        ContractDialog(self.root, rec, self, number=num,
                       season=self.season_year.get())

    def _focus_record(self, index: int) -> None:
        """يحدّد سجلاً في الجدول الرئيسي ويُظهره (من نافذة الفحص)."""
        iid = str(index)
        if self._filter_active():          # قد يكون مخفياً بالفلتر
            self.clear_filters()
        try:
            self.tree.selection_set(iid)
            self.tree.see(iid)
            self.tree.focus(iid)
            self.root.lift()
        except Exception:
            pass

    def do_export_excel(self) -> None:
        if not self._require_records():
            return
        path = filedialog.asksaveasfilename(
            title="حفظ ملف الإكسل", defaultextension=".xlsx",
            initialfile=self._default_name("xlsx"), filetypes=EXCEL_TYPES,
        )
        if not path:
            return
        try:
            export_excel(self._ordered(), path)
        except PermissionError:
            messagebox.showerror("الملف مفتوح",
                                 "الملف مفتوح في برنامج آخر. أغلقه ثم أعد المحاولة.")
            return
        except Exception as exc:
            messagebox.showerror("خطأ في التصدير", str(exc))
            return
        self.set_status(f"تم حفظ الإكسل: {path}")
        self._offer_open(path)

    def do_export_pdf(self) -> None:
        if not self._require_records():
            return
        path = filedialog.asksaveasfilename(
            title="حفظ ملف PDF", defaultextension=".pdf",
            initialfile=self._default_name("pdf"),
            filetypes=(("ملفات PDF", "*.pdf"), ("كل الملفات", "*.*")),
        )
        if not path:
            return
        cards = messagebox.askyesno(
            "بطاقات تفصيلية",
            "هل تريد إضافة صفحة بطاقة مفصّلة لكل حاج بعد الجدول؟",
        )
        try:
            export_pdf(self._ordered(), path, title=self._report_title("كشف الحجاج"),
                       with_cards=cards)
        except PermissionError:
            messagebox.showerror("الملف مفتوح",
                                 "الملف مفتوح في برنامج آخر. أغلقه ثم أعد المحاولة.")
            return
        except Exception as exc:
            messagebox.showerror("خطأ في التصدير", str(exc))
            return
        self.set_status(f"تم حفظ PDF: {path}")
        self._offer_open(path)

    def _confirm_rooming(self):
        """يفحص وجود غرف ويعرض ملخّصاً. يعيد عدد الغرف أو None عند الإلغاء."""
        if not self._require_records():
            return None

        from .rooming import group_records_by_room
        rooms, unplaced = group_records_by_room(self.records)
        if not rooms:
            messagebox.showinfo(
                "لا يمكن بناء كشف التسكين",
                "لا يوجد حاج له نوع غرفة أو رقم غرفة.\n"
                "أضف «نوع الغرفة» للحجاج (مثل: رباعي 2، ثلاثي 3) ثم أعد المحاولة.",
            )
            return None

        over = sum(1 for _h, cap, _n, occ in rooms if len(occ) > cap)
        summary = f"عدد الغرف: {len(rooms)}\n"
        if over:
            summary += f"⚠ غرف تجاوزت سعتها: {over}\n"
        if unplaced:
            summary += f"⚠ حجاج بلا نوع غرفة (لن يُدرجوا): {len(unplaced)}\n"
        summary += "\nمتابعة؟"
        if not messagebox.askyesno("كشف التسكين", summary):
            return None
        return len(rooms)

    def do_rooming_pdf(self) -> None:
        """يصدّر كشف التسكين إلى PDF — بنفس أعمدة الطباعة، مجموعاً بالغرف."""
        rooms = self._confirm_rooming()
        if rooms is None:
            return
        path = filedialog.asksaveasfilename(
            title="حفظ كشف التسكين PDF", defaultextension=".pdf",
            initialfile=self._default_name("pdf").replace("كشف_الحجاج", "كشف_التسكين"),
            filetypes=(("ملفات PDF", "*.pdf"), ("كل الملفات", "*.*")),
        )
        if not path:
            return
        self._do_rooming_export(
            lambda p: export_pdf(self.records, p,
                                 title=self._report_title("كشف التسكين"),
                                 group_by_room=True),
            path, rooms,
        )

    def do_rooming_excel(self) -> None:
        """يصدّر كشف التسكين إلى إكسل — بنفس أعمدة الطباعة، مجموعاً بالغرف."""
        rooms = self._confirm_rooming()
        if rooms is None:
            return
        path = filedialog.asksaveasfilename(
            title="حفظ كشف التسكين إكسل", defaultextension=".xlsx",
            initialfile=self._default_name("xlsx").replace("كشف_الحجاج", "كشف_التسكين"),
            filetypes=EXCEL_TYPES,
        )
        if not path:
            return
        from .excel_io import export_grouped_excel
        self._do_rooming_export(
            lambda p: export_grouped_excel(self.records, p,
                                           title=self._report_title("كشف التسكين")),
            path, rooms,
        )

    def _do_rooming_export(self, export_fn, path: str, rooms: int) -> None:
        """ينفّذ التصدير مع معالجة موحّدة للأخطاء."""
        try:
            export_fn(path)
        except PermissionError:
            messagebox.showerror("الملف مفتوح",
                                 "الملف مفتوح في برنامج آخر. أغلقه ثم أعد المحاولة.")
            return
        except Exception as exc:
            messagebox.showerror("خطأ في التصدير", str(exc))
            return
        self.set_status(f"تم حفظ كشف التسكين: {rooms} غرفة")
        self._offer_open(path)

    def _require_records(self) -> bool:
        if not self.records:
            messagebox.showinfo("لا توجد بيانات", "أضف صور جوازات أو استورد ملف إكسل أولاً.")
            return False
        return True

    def _offer_open(self, path: str) -> None:
        if messagebox.askyesno("تم الحفظ", f"تم حفظ الملف بنجاح:\n{path}\n\nهل تريد فتحه الآن؟"):
            import os
            try:
                os.startfile(path)
            except Exception as exc:
                messagebox.showwarning("تعذّر الفتح", str(exc))

    # ------------------------------------------------------------ تحرير/حذف
    def edit_selected(self) -> None:
        idx = self._selected_indices()
        if not idx:
            messagebox.showinfo("لم يتم التحديد", "اختر سجلاً من الجدول أولاً.")
            return
        EditDialog(self.root, self.records[idx[0]], on_save=self._after_edit,
                   session=self.session)

    def _after_edit(self, rec: PassportData) -> None:
        self.refresh()
        self.save_data()
        self.set_status("تم حفظ التعديلات")

    def delete_selected(self) -> None:
        idx = self._selected_indices()
        if not idx:
            messagebox.showinfo("لم يتم التحديد", "اختر سجلاً أو أكثر للحذف.")
            return
        if not messagebox.askyesno("تأكيد الحذف", f"حذف {len(idx)} سجل؟"):
            return
        from . import images as imgmod
        for i in reversed(idx):
            imgmod.delete_all(self.records[i].image_id)   # حذف صور الحاج المشفّرة
            del self.records[i]
        self.refresh()
        self.save_data()
        self.set_status(f"تم حذف {len(idx)} سجل")

    _CLEAR_CONFIRM_WORD = "مسح"

    def _clear_credential_ok(self, value: str) -> bool:
        """يتحقق من بوابة أمان المسح: كلمة مرور الحساب، أو كلمة التأكيد.

        عند وجود جلسة (حساب) نطلب **كلمة مرور الحساب نفسها** (لا رقماً سرياً
        منفصلاً يُخزَّن ويُنسى)، فنتحقق منها عبر تسجيل دخول تجريبي. وبلا حساب
        (كالاختبارات) نكتفي بكتابة كلمة «مسح» لمنع الضغط غير المقصود.
        """
        if self.session is None:
            return value.strip() == self._CLEAR_CONFIRM_WORD
        try:
            from .auth import login as _login
            _login(self.session.username, value)
            return True
        except Exception:
            return False

    def _confirm_destructive(self) -> bool:
        """نافذة بوابة الأمان قبل مسح كل السجلات. تعيد True عند التأكيد."""
        use_password = self.session is not None
        dlg = Toplevel(self.root)
        dlg.title("تأكيد المسح النهائي")
        dlg.configure(bg=BG)
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)
        frame = ttk.Frame(dlg, padding=20)
        frame.pack(fill=BOTH, expand=True)

        ttk.Label(frame, text="⚠  مسح جميع السجلات", background=BG,
                  font=("Segoe UI Semibold", 13), foreground=DANGER).pack(anchor="e")
        ttk.Label(frame, background=BG, foreground=TEXT, justify="right",
                  font=("Segoe UI", 10), wraplength=340,
                  text=(f"سيُحذف {len(self.records)} سجلاً وكل صورهم نهائياً "
                        "(تبقى نسخة احتياطية .bak).")).pack(anchor="e", pady=(8, 10))

        if use_password:
            prompt = f"للتأكيد، أدخل كلمة مرور حسابك «{self.session.username}»:"
        else:
            prompt = f"للتأكيد، اكتب كلمة «{self._CLEAR_CONFIRM_WORD}» في الحقل:"
        ttk.Label(frame, text=prompt, background=BG, foreground=TEXT,
                  font=("Segoe UI", 10), wraplength=340, justify="right").pack(anchor="e")

        var = StringVar()
        entry = ttk.Entry(frame, textvariable=var, width=30, justify="center",
                          show="●" if use_password else "")
        install_entry_editing(entry)
        entry.pack(anchor="e", pady=(6, 0))
        entry.focus_set()
        err = ttk.Label(frame, text="", background=BG, foreground=DANGER,
                        font=("Segoe UI", 9))
        err.pack(anchor="e", pady=(4, 0))

        state = {"ok": False, "attempts": 0}

        def attempt():
            if self._clear_credential_ok(var.get()):
                state["ok"] = True
                dlg.destroy()
                return
            state["attempts"] += 1
            var.set("")
            if use_password and state["attempts"] >= 3:
                err.config(text="كلمة المرور غير صحيحة — أُلغيت العملية.")
                dlg.after(1000, dlg.destroy)
                return
            err.config(text=("كلمة المرور غير صحيحة. حاول مجدداً."
                             if use_password else
                             f"اكتب «{self._CLEAR_CONFIRM_WORD}» بالضبط."))

        btns = ttk.Frame(frame)
        btns.pack(anchor="e", pady=(16, 0))
        ttk.Button(btns, text=rtl("🗑  تأكيد المسح"), style="Danger.TButton",
                   command=attempt).pack(side=RIGHT, padx=3)
        ttk.Button(btns, text="إلغاء", style="Ghost.TButton",
                   command=dlg.destroy).pack(side=RIGHT, padx=3)
        dlg.bind("<Return>", lambda _e: attempt())
        dlg.bind("<Escape>", lambda _e: dlg.destroy())
        self.root.wait_window(dlg)
        return state["ok"]

    def clear_all(self) -> None:
        if not self.records:
            return
        if not self._confirm_destructive():
            self.set_status("أُلغي المسح")
            return
        from . import images as imgmod
        for rec in self.records:
            imgmod.delete_all(rec.image_id)          # حذف كل الصور المشفّرة
        self.records.clear()
        self.refresh()
        self.save_data()
        self.set_status("تم مسح جميع السجلات", ok=True)


class AirlineDialog(Toplevel):
    """كشف الطيران: تصدير إكسل/PDF (إنجليزي LTR) ونسخ إدخالات أماديوس."""

    _ALL_FLIGHTS = "كل الرحلات"

    def __init__(self, parent, records: list[PassportData]) -> None:
        super().__init__(parent)
        self._all = records
        self.title("كشف الطيران — Flight Manifest")
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()

        outer = ttk.Frame(self, padding=16)
        outer.pack(fill=BOTH, expand=True)

        # اختيار الرحلة/الطيران + عدد الركّاب المطابق
        top = ttk.Frame(outer)
        top.pack(fill=X)
        self._count_label = ttk.Label(top, font=("Segoe UI Semibold", 11),
                                      foreground=TEXT)
        self._count_label.pack(side=LEFT)
        self._flight_var = StringVar(value=self._ALL_FLIGHTS)
        box = ttk.Combobox(top, textvariable=self._flight_var, state="readonly",
                           width=24, font=("Segoe UI", 10),
                           values=self._flight_combo_values())
        box.pack(side=RIGHT)
        box.bind("<<ComboboxSelected>>", lambda _e: self._rebuild())
        ttk.Label(top, text="الطيران:", font=("Segoe UI", 10),
                  foreground=TEXT).pack(side=RIGHT, padx=(2, 5))

        ttk.Label(outer, foreground=MUTED, font=("Segoe UI", 9), justify="right",
                  text=rtl("الأعمدة (إنجليزي، يسار←يمين): # • Last • First • "
                           "Passport • Expiry • DOB • Gender • Nationality • "
                           "Class • Family • PNR")).pack(anchor="e", pady=(4, 10))

        row = ttk.Frame(outer)
        row.pack(anchor="e", pady=(0, 10))
        ttk.Button(row, text=rtl("📊  تصدير إكسل"), style="Act.TButton",
                   command=self._excel).pack(side=RIGHT, padx=3)
        ttk.Button(row, text=rtl("📄  تصدير PDF"), style="Act.TButton",
                   command=self._pdf).pack(side=RIGHT, padx=3)

        ttk.Separator(outer, orient="horizontal").pack(fill=X, pady=8)
        ttk.Label(outer, text="إدخالات أماديوس — انقر نقراً مزدوجاً على راكب لنسخ إدخاله:",
                  font=("Segoe UI Semibold", 10), foreground=TEXT).pack(anchor="e")

        table_frame = ttk.Frame(outer)
        table_frame.pack(fill=BOTH, expand=True, pady=(6, 8))
        scroll = ttk.Scrollbar(table_frame, orient="vertical")
        scroll.pack(side=RIGHT, fill=Y)
        self._tree = ttk.Treeview(table_frame, columns=("name", "amadeus"),
                                  show="headings", selectmode="browse", height=11,
                                  yscrollcommand=scroll.set)
        self._tree.heading("name", text="الراكب")
        self._tree.heading("amadeus", text="إدخال أماديوس")
        self._tree.column("name", width=150, anchor="center", stretch=False)
        self._tree.column("amadeus", width=520, anchor="w")
        self._tree.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.config(command=self._tree.yview)
        self._tree.bind("<Double-1>", lambda _e: self._copy_selected())

        self._entry_by_iid: dict[str, str] = {}
        self._amadeus = ""
        self._rebuild()          # يملأ القائمة والعدّاد حسب الرحلة المختارة

        bottom = ttk.Frame(outer)
        bottom.pack(anchor="e")
        ttk.Button(bottom, text=rtl("📋  نسخ إدخال الراكب المحدد"), style="Act.TButton",
                   command=self._copy_selected).pack(side=RIGHT, padx=3)
        ttk.Button(bottom, text=rtl("📋  نسخ كل الإدخالات"), style="Act.TButton",
                   command=self._copy_amadeus).pack(side=RIGHT, padx=3)
        ttk.Button(bottom, text="إغلاق", style="Act.TButton",
                   command=self.destroy).pack(side=RIGHT)

        self.bind("<Escape>", lambda _e: self.destroy())

    def _flight_combo_values(self) -> list[str]:
        """قيم قائمة الرحلات: «كل الرحلات» + الرحلات الفريدة غير الفارغة مرتّبة."""
        flights = sorted({str(r.airline or "").strip()
                          for r in self._all if str(r.airline or "").strip()})
        return [self._ALL_FLIGHTS, *flights]

    def _current(self) -> list[PassportData]:
        """الركّاب المطابقون للرحلة المختارة (أو الجميع)."""
        sel = self._flight_var.get()
        if sel == self._ALL_FLIGHTS:
            return list(self._all)
        return [r for r in self._all if str(r.airline or "").strip() == sel]

    @property
    def _default(self) -> str:
        sel = self._flight_var.get()
        suffix = "" if sel == self._ALL_FLIGHTS else f"_{re.sub(r'[^\w -]', '', sel).strip()}"
        return f"كشف_الطيران{suffix}_{date.today().isoformat()}"

    def _rebuild(self) -> None:
        """يعيد ملء قائمة أماديوس والعدّاد حسب الرحلة المختارة."""
        from .airline import amadeus_entries, amadeus_entry, split_name
        records = self._current()
        self._tree.delete(*self._tree.get_children())
        self._entry_by_iid = {}
        self._amadeus = amadeus_entries(records)
        for i, rec in enumerate(records):
            entry = amadeus_entry(rec)
            if not entry:
                continue
            last, first = split_name(rec)
            display = rec.full_name_ar or f"{first} {last}".strip() or "—"
            iid = str(i)
            self._tree.insert("", END, iid=iid,
                              values=(display, entry.replace("\n", "   |   ")))
            self._entry_by_iid[iid] = entry
        self._count_label.config(text=f"عدد الركّاب: {len(records)}")

    def _copy_selected(self) -> None:
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("لم يتم التحديد", "اختر راكباً من القائمة أولاً.",
                                parent=self)
            return
        entry = self._entry_by_iid.get(sel[0], "")
        if entry:
            self.clipboard_clear()
            self.clipboard_append(entry)
            name = self._tree.item(sel[0], "values")[0]
            self.set_title_status(f"نُسخ إدخال: {name}")

    def set_title_status(self, text: str) -> None:
        """يعرض تأكيداً موجزاً في عنوان النافذة (بلا نافذة منبثقة لكل نسخة)."""
        self.title(f"كشف الطيران — {text}")
        self.after(1800, lambda: self.title("كشف الطيران — Flight Manifest"))

    def _save_path(self, ext: str) -> str | None:
        return filedialog.asksaveasfilename(
            parent=self, title="حفظ كشف الطيران", defaultextension=f".{ext}",
            initialfile=f"{self._default}.{ext}",
            filetypes=((f"ملفات {ext.upper()}", f"*.{ext}"), ("كل الملفات", "*.*")),
        )

    def _run(self, export_fn, ext: str) -> None:
        path = self._save_path(ext)
        if not path:
            return
        try:
            export_fn(self._current(), path)
        except PermissionError:
            messagebox.showerror("الملف مفتوح",
                                 "الملف مفتوح في برنامج آخر. أغلقه ثم أعد المحاولة.",
                                 parent=self)
            return
        except Exception as exc:
            messagebox.showerror("خطأ في التصدير", str(exc), parent=self)
            return
        if messagebox.askyesno("تم الحفظ", f"حُفظ:\n{path}\n\nفتحه الآن؟", parent=self):
            import os
            try:
                os.startfile(path)
            except Exception:
                pass

    def _excel(self) -> None:
        from .airline import export_airline_excel
        self._run(export_airline_excel, "xlsx")

    def _pdf(self) -> None:
        from .pdf_io import export_airline_pdf
        self._run(export_airline_pdf, "pdf")

    def _copy_amadeus(self) -> None:
        if not self._amadeus:
            return
        self.clipboard_clear()
        self.clipboard_append(self._amadeus)
        messagebox.showinfo("نُسخ", "نُسخت إدخالات أماديوس — الصقها في النظام.",
                            parent=self)


class CampsDialog(Toplevel):
    """خيام المخيمات (منى/عرفة): إنشاء **كل خيمة على حدة** وتصديرها.

    لكل خيمة يحدّد المستخدم رقمها وقطاعها وتصنيفها (رجال/نساء) وعدد أشخاصها،
    فتُملأ تلقائياً بذلك العدد من غير المسكّنين (العائلة وسكّان الغرفة معاً)،
    ثم «تصدير» يُنشئ ملف الخيمة وينتقل للتالية بمن تبقّى. لا يُحفظ في البيانات.
    """

    _DEFAULT_CAMPAIGN = "المصطفى للحج والعمرة"

    def __init__(self, parent, records: list[PassportData]) -> None:
        super().__init__(parent)
        self._records = records
        self._assigned: set[int] = set()      # فهارس من سُكّنوا في خيام أُنشئت
        self._preview: list[int] = []          # فهارس الخيمة المعروضة حالياً
        self.title("إنشاء خيام المخيمات")
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()

        from .camps import CAMP_MINA, CAMPS, MEN, WOMEN

        outer = ttk.Frame(self, padding=16)
        outer.pack(fill=BOTH, expand=True)

        # ---- معطيات الخيمة الواحدة ----
        form = ttk.Frame(outer)
        form.pack(fill=X)
        self._camp_var = StringVar(value=CAMP_MINA)
        self._class_var = StringVar(value=MEN)
        self._sector_var = StringVar(value="")
        self._number_var = StringVar(value="1")
        self._count_var = StringVar(value="40")
        self._campaign_var = StringVar(value=self._DEFAULT_CAMPAIGN)

        def field(label, var, width, combo=None, on_change=None):
            cell = ttk.Frame(form)
            cell.pack(side=RIGHT, padx=(6, 0))
            ttk.Label(cell, text=label, font=("Segoe UI", 10),
                      foreground=TEXT).pack(anchor="e")
            if combo is not None:
                w = ttk.Combobox(cell, textvariable=var, state="readonly",
                                 width=width, values=combo, font=("Segoe UI", 10))
                if on_change:
                    w.bind("<<ComboboxSelected>>", lambda _e: on_change())
            else:
                w = ttk.Entry(cell, textvariable=var, width=width,
                              justify="center", font=("Segoe UI", 10))
                install_entry_editing(w)
                if on_change:
                    w.bind("<Return>", lambda _e: on_change())
                    w.bind("<FocusOut>", lambda _e: on_change())
            w.pack(anchor="e")
            return w

        field("المخيّم", self._camp_var, 12, combo=list(CAMPS))
        field("التصنيف", self._class_var, 10, combo=[MEN, WOMEN],
              on_change=self._refresh_preview)
        field("القطاع", self._sector_var, 10)
        field("رقم الخيمة", self._number_var, 8)
        field("عدد الأشخاص", self._count_var, 8, on_change=self._refresh_preview)

        # اسم الحملة (يظهر في كشف الخيمة)
        camp_row = ttk.Frame(outer)
        camp_row.pack(fill=X, pady=(8, 0))
        ttk.Label(camp_row, text="اسم الحملة:", font=("Segoe UI", 10),
                  foreground=TEXT).pack(side=RIGHT, padx=(4, 5))
        camp_entry = ttk.Entry(camp_row, textvariable=self._campaign_var, width=32,
                               justify="right", font=("Segoe UI", 10))
        install_entry_editing(camp_entry)
        camp_entry.pack(side=RIGHT)

        self._summary = ttk.Label(outer, font=("Segoe UI Semibold", 11),
                                  foreground=TEXT)
        self._summary.pack(anchor="e", pady=(10, 2))
        ttk.Label(outer, foreground=MUTED, font=("Segoe UI", 9), justify="right",
                  text=rtl("تُملأ الخيمة تلقائياً بعدد الأشخاص المحدّد من التصنيف "
                           "المختار (العائلة وسكّان الغرفة معاً). «تصدير» يُنشئ ملف "
                           "هذه الخيمة ثم ينتقل للتالية بمن تبقّى."))\
            .pack(anchor="e", pady=(2, 8))

        # ---- معاينة ركّاب الخيمة الحالية ----
        table = ttk.Frame(outer)
        table.pack(fill=BOTH, expand=True)
        scroll = ttk.Scrollbar(table, orient="vertical")
        scroll.pack(side=RIGHT, fill=Y)
        self._tree = ttk.Treeview(
            table, columns=("serial", "name", "fam", "hotel", "room"),
            show="headings", height=13, yscrollcommand=scroll.set)
        for col, label, width, stretch in (
            ("serial", "م", 45, False), ("name", "اسم الحاج", 240, True),
            ("fam", "العائلة", 80, False), ("hotel", "الفندق", 150, False),
            ("room", "الغرفة", 70, False),
        ):
            self._tree.heading(col, text=label)
            self._tree.column(col, width=width,
                              anchor="center" if col != "name" else "e",
                              stretch=stretch)
        self._tree.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.config(command=self._tree.yview)

        # ---- أزرار ----
        row = ttk.Frame(outer)
        row.pack(anchor="e", pady=(10, 0))
        ttk.Button(row, text=rtl("🏕  تصدير هذه الخيمة"), style="Act.TButton",
                   command=self._export_tent).pack(side=RIGHT, padx=3)
        ttk.Button(row, text=rtl("↺  إعادة الضبط"), style="Act.TButton",
                   command=self._reset).pack(side=RIGHT, padx=3)
        ttk.Button(row, text="إغلاق", style="Act.TButton",
                   command=self.destroy).pack(side=LEFT, padx=3)

        self.bind("<Escape>", lambda _e: self.destroy())
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        """يحسب ركّاب الخيمة التالية (تلقائياً) ويعرضهم دون تثبيتهم."""
        from .camps import next_tent_indices, remaining_by_class
        from .rooming import room_number_in_type
        cls = self._class_var.get()
        self._preview = next_tent_indices(
            self._records, cls, self._count_var.get(), self._assigned)
        self._tree.delete(*self._tree.get_children())
        for serial, i in enumerate(self._preview, start=1):
            rec = self._records[i]
            room = (str(rec.room_number or "").strip()
                    or room_number_in_type(str(rec.room_type or "")))
            self._tree.insert("", END, values=(
                serial, rec.full_name_ar or rec.full_name_en or "—",
                str(rec.family_number or "").strip(),
                str(rec.hotel or "").strip(), room,
            ))
        remaining = remaining_by_class(self._records, self._assigned)
        self._summary.config(text=(
            f"سيدخل هذه الخيمة: {len(self._preview)}  •  "
            f"المتبقّون ({cls}): {remaining.get(cls, 0)}  •  "
            f"إجمالي المسكّنين: {len(self._assigned)}"))

    def _reset(self) -> None:
        """يمسح كل ما سُكّن ويبدأ من جديد."""
        if self._assigned and not messagebox.askyesno(
                "إعادة الضبط", "مسح كل الخيام التي أُنشئت والبدء من جديد؟",
                parent=self):
            return
        self._assigned = set()
        self._refresh_preview()

    def _export_tent(self) -> None:
        """يُنشئ ملف الخيمة الحالية، ثم يثبّت ركّابها وينتقل للتالية."""
        if not self._preview:
            messagebox.showinfo(
                "لا يوجد من يُسكّن",
                f"لا يوجد {self._class_var.get()} غير مسكّنين لهذه الخيمة.",
                parent=self)
            return
        from .camps import make_tent
        from .pdf_io import export_tents_pdf
        from .camps import export_tents_excel

        number = str(self._number_var.get()).strip() or "1"
        cls = self._class_var.get()
        sector = self._sector_var.get().strip()
        base = f"خيمة {number} - {cls}" + (f" - قطاع {sector}" if sector else "")
        import re as _re
        base = _re.sub(r'[\\/:*?"<>|]+', "-", base).strip() or f"خيمة {number}"
        path = filedialog.asksaveasfilename(
            parent=self, title="حفظ ملف الخيمة", initialfile=base,
            defaultextension=".pdf",
            filetypes=(("ملف PDF", "*.pdf"), ("ملف إكسل", "*.xlsx"),
                       ("كل الملفات", "*.*")))
        if not path:
            return

        plan = make_tent(
            self._records, self._preview, camp=self._camp_var.get(),
            sector=sector, number=number, classification_label=cls,
            capacity=self._count_var.get())
        exporter = (export_tents_excel if path.lower().endswith(".xlsx")
                    else export_tents_pdf)
        try:
            exporter(plan, path, campaign=self._campaign_var.get())
        except PermissionError:
            messagebox.showerror("الملف مفتوح",
                                 "الملف مفتوح في برنامج آخر. أغلقه ثم أعد المحاولة.",
                                 parent=self)
            return
        except Exception as exc:
            messagebox.showerror("خطأ في التصدير", str(exc), parent=self)
            return

        # تثبيت ركّاب هذه الخيمة والانتقال للتالية
        self._assigned.update(self._preview)
        if str(number).isdigit():
            self._number_var.set(str(int(number) + 1))
        self._refresh_preview()
        opened = messagebox.askyesno(
            "تم إنشاء الخيمة",
            f"حُفظت «خيمة {number}» ({len(plan.tents[0].occupants)} شخصاً):\n{path}"
            "\n\nفتحها الآن؟", parent=self)
        if opened:
            import os
            try:
                os.startfile(path)
            except Exception:
                pass


class BulkEditDialog(Toplevel):
    """تعديل جماعي: يضبط حقولاً مختارة لكل السجلات المحدّدة دفعةً واحدة."""

    _FIELDS = (
        ("hotel", "الفندق"),
        ("room_type", "نوع الغرفة"),
        ("airline", "الطيران"),
        ("flight_number", "رقم الرحلة"),
        ("travel_class", "درجة السفر"),
        ("transport", "المواصلات"),
        ("executive_service", "خدمة التنفيذي"),
        ("wheelchair", "كرسي متحرك"),
        ("hady", "الهدي"),
        ("nationality_ar", "الجنسية"),
        ("arrival_date", "تاريخ الوصول"),
        ("departure_date", "تاريخ المغادرة"),
        ("staff", "الموظف المسؤول"),
    )

    def __init__(self, parent, count: int, on_apply) -> None:
        super().__init__(parent)
        self._on_apply = on_apply
        self.title(f"تعديل جماعي — {count} سجلاً")
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)

        outer = ttk.Frame(self, padding=18)
        outer.pack(fill=BOTH, expand=True)
        ttk.Label(outer, text=f"سيُطبّق على {count} سجلاً محدّداً",
                  font=("Segoe UI Semibold", 12), foreground=TEXT,
                  background=BG).pack(anchor="e")
        ttk.Label(outer, foreground=MUTED, font=("Segoe UI", 9), justify="right",
                  background=BG,
                  text=rtl("علّم «طبّق» بجانب الحقل واكتب قيمته — تُطبَّق على "
                           "الجميع. الحقول غير المعلّمة تبقى كما هي.")).pack(
            anchor="e", pady=(2, 10))

        grid = ttk.Frame(outer)
        grid.pack(fill=X)
        self._vars: dict[str, tuple[tk.BooleanVar, StringVar]] = {}
        for row, (key, label) in enumerate(self._FIELDS):
            apply_var = tk.BooleanVar(value=False)
            val_var = StringVar()
            chk = ttk.Checkbutton(grid, text=label, variable=apply_var)
            chk.grid(row=row, column=1, sticky="e", padx=(8, 0), pady=2)
            entry = ttk.Entry(grid, textvariable=val_var, width=26, justify="right",
                              font=("Segoe UI", 10))
            install_entry_editing(entry)
            entry.grid(row=row, column=0, sticky="e", pady=2)
            # الكتابة في الحقل تعلّم «طبّق» تلقائياً
            entry.bind("<KeyRelease>", lambda _e, v=apply_var: v.set(True))
            self._vars[key] = (apply_var, val_var)

        btns = ttk.Frame(outer)
        btns.pack(anchor="e", pady=(16, 0))
        ttk.Button(btns, text=rtl("✔  تطبيق على المحدّدين"), style="Primary.TButton",
                   command=self._apply).pack(side=RIGHT, padx=3)
        ttk.Button(btns, text="إلغاء", style="Ghost.TButton",
                   command=self.destroy).pack(side=RIGHT, padx=3)
        self.bind("<Escape>", lambda _e: self.destroy())

    def _apply(self) -> None:
        changes = {k: v.get() for k, (a, v) in self._vars.items() if a.get()}
        if not changes:
            messagebox.showinfo("لا تغييرات",
                                "علّم «طبّق» بجانب حقل واحد على الأقل.", parent=self)
            return
        self._on_apply(changes)
        self.destroy()


class TransportDialog(Toplevel):
    """كشف المواصلات: يختار الوسيلة (أو الكل) ويصدّر إكسل/PDF مجموعاً بالباص."""

    _ALL = "كل الوسائل"

    def __init__(self, parent, records) -> None:
        super().__init__(parent)
        self._all = records
        self.title("🚌 كشف المواصلات")
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()

        from .transport import distinct_transports

        outer = ttk.Frame(self, padding=16)
        outer.pack(fill=BOTH, expand=True)
        top = ttk.Frame(outer)
        top.pack(fill=X)
        self._count = ttk.Label(top, font=("Segoe UI Semibold", 11), foreground=TEXT)
        self._count.pack(side=LEFT)
        self._var = StringVar(value=self._ALL)
        box = ttk.Combobox(top, textvariable=self._var, state="readonly", width=24,
                           font=("Segoe UI", 10),
                           values=[self._ALL, *distinct_transports(records)])
        box.pack(side=RIGHT)
        box.bind("<<ComboboxSelected>>", lambda _e: self._rebuild())
        ttk.Label(top, text="الوسيلة:", font=("Segoe UI", 10),
                  foreground=TEXT).pack(side=RIGHT, padx=(2, 5))

        cols = ("phone", "hotel", "executive", "wheelchair")
        self._tree = ttk.Treeview(outer, columns=cols, show="tree headings", height=13)
        self._tree.heading("#0", text="الباص / الحاج")
        for c, lbl, w in (("phone", "الهاتف", 120), ("hotel", "الفندق", 150),
                          ("executive", "خدمة التنفيذي", 100),
                          ("wheelchair", "كرسي متحرك", 90)):
            self._tree.heading(c, text=lbl)
            self._tree.column(c, width=w, anchor="center", stretch=False)
        self._tree.column("#0", width=240, anchor="e", stretch=True)
        self._tree.pack(fill=BOTH, expand=True, pady=(10, 8))

        row = ttk.Frame(outer)
        row.pack(anchor="e")
        ttk.Button(row, text=rtl("📊  تصدير إكسل"), style="Act.TButton",
                   command=self._excel).pack(side=RIGHT, padx=3)
        ttk.Button(row, text=rtl("📄  تصدير PDF"), style="Act.TButton",
                   command=self._pdf).pack(side=RIGHT, padx=3)
        ttk.Button(row, text="إغلاق", style="Ghost.TButton",
                   command=self.destroy).pack(side=RIGHT, padx=3)
        self.bind("<Escape>", lambda _e: self.destroy())
        self._rebuild()

    def _current(self):
        sel = self._var.get()
        if sel == self._ALL:
            return list(self._all)
        return [r for r in self._all if str(r.transport or "").strip() == sel]

    def _rebuild(self) -> None:
        from .transport import executive_display, group_by_transport
        records = self._current()
        self._tree.delete(*self._tree.get_children())
        groups, unassigned = group_by_transport(records)
        blocks = list(groups) + ([("بلا مواصلات", unassigned)] if unassigned else [])
        for name, occ in blocks:
            gid = self._tree.insert("", END, text=f"{name}  ({len(occ)})", open=True)
            for rec in occ:
                self._tree.insert(gid, END,
                                  text=rec.full_name_ar or rec.full_name_en or "—",
                                  values=(str(rec.phone or "").strip() or "—",
                                          str(rec.hotel or "").strip() or "—",
                                          executive_display(rec) or "—",
                                          str(rec.wheelchair or "").strip() or "—"))
        self._count.config(text=f"عدد الحجّاج: {len(records)}")

    def _default(self, ext):
        return f"كشف_المواصلات_{date.today().isoformat()}.{ext}"

    def _run(self, export_fn, ext):
        records = self._current()
        if not records:
            messagebox.showinfo("لا نتائج", "لا يوجد حجّاج.", parent=self)
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="حفظ كشف المواصلات", defaultextension=f".{ext}",
            initialfile=self._default(ext),
            filetypes=((f"ملفات {ext.upper()}", f"*.{ext}"), ("كل الملفات", "*.*")))
        if not path:
            return
        try:
            export_fn(records, path)
        except PermissionError:
            messagebox.showerror("الملف مفتوح",
                                 "الملف مفتوح في برنامج آخر. أغلقه ثم أعد المحاولة.",
                                 parent=self)
            return
        except Exception as exc:
            messagebox.showerror("خطأ في التصدير", str(exc), parent=self)
            return
        if messagebox.askyesno("تم الحفظ", f"حُفظ:\n{path}\n\nفتحه الآن؟", parent=self):
            import os
            try:
                os.startfile(path)
            except Exception:
                pass

    def _excel(self):
        from .transport import export_transport_excel
        self._run(export_transport_excel, "xlsx")

    def _pdf(self):
        from .pdf_io import export_transport_pdf
        self._run(export_transport_pdf, "pdf")


class StatsDialog(Toplevel):
    """لوحة إحصاءات وملخّص مالي: توزيع الحجّاج + المحصّل/المتبقّي + المتأخّرات."""

    _CARD_COLORS = {
        "المحصّل": SUCCESS_FG,
        "المتبقّي": DANGER,
        "نسبة التحصيل": BRONZE,
        "عدد غير المكتمل": AMBER_FG,
    }

    def __init__(self, parent, records, season: str = "") -> None:
        super().__init__(parent)
        self._records = records
        self._season = season
        self.title("📊 إحصاءات وملخّص مالي")
        self.configure(bg=BG)
        self.transient(parent)
        self.geometry("760x600")

        from .stats import financial_summary, GROUPINGS

        outer = ttk.Frame(self, padding=16)
        outer.pack(fill=BOTH, expand=True)

        # ---- بطاقات الملخّص المالي ----
        fin = financial_summary(records)
        cards = ttk.Frame(outer, style="Toolbar.TFrame")
        cards.pack(fill=X, pady=(0, 12))
        for label, value in fin.as_rows():
            card = ttk.Frame(cards, style="Toolbar.TFrame", padding=(12, 6))
            card.pack(side=RIGHT, padx=4)
            ttk.Label(card, text=value, background=BG,
                      font=("Segoe UI Semibold", 15),
                      foreground=self._CARD_COLORS.get(label, ACCENT)).pack(anchor="e")
            ttk.Label(card, text=label, background=BG, foreground=MUTED,
                      font=("Segoe UI", 9)).pack(anchor="e")

        nb = ttk.Notebook(outer)
        nb.pack(fill=BOTH, expand=True)

        # ---- تبويب التوزيع ----
        dist_tab = ttk.Frame(nb, padding=10)
        nb.add(dist_tab, text="التوزيع")
        top = ttk.Frame(dist_tab)
        top.pack(fill=X, pady=(0, 6))
        self._group_var = StringVar(value=GROUPINGS[0][1])
        self._group_map = {lbl: key for key, lbl in GROUPINGS}
        box = ttk.Combobox(top, textvariable=self._group_var, state="readonly",
                           width=16, font=("Segoe UI", 10),
                           values=[lbl for _k, lbl in GROUPINGS])
        box.pack(side=RIGHT)
        box.bind("<<ComboboxSelected>>", lambda _e: self._refresh_dist())
        ttk.Label(top, text="التوزيع حسب:", font=("Segoe UI", 10),
                  foreground=TEXT).pack(side=RIGHT, padx=(4, 6))

        self._dist = ttk.Treeview(dist_tab, columns=("count", "pct", "bar"),
                                  show="tree headings", height=12)
        self._dist.heading("#0", text="القيمة")
        self._dist.heading("count", text="العدد")
        self._dist.heading("pct", text="النسبة")
        self._dist.heading("bar", text="")
        self._dist.column("#0", width=200, anchor="e", stretch=False)
        self._dist.column("count", width=70, anchor="center", stretch=False)
        self._dist.column("pct", width=70, anchor="center", stretch=False)
        self._dist.column("bar", width=260, anchor="w", stretch=True)
        self._dist.pack(fill=BOTH, expand=True)

        # ---- تبويب المتأخّرات ----
        owe_tab = ttk.Frame(nb, padding=10)
        nb.add(owe_tab, text="المتأخّرات")
        self._owe_total = ttk.Label(owe_tab, font=("Segoe UI Semibold", 11),
                                    foreground=DANGER)
        self._owe_total.pack(anchor="e", pady=(0, 6))
        self._owe = ttk.Treeview(owe_tab, columns=("passport", "phone", "amount"),
                                 show="tree headings", height=12)
        self._owe.heading("#0", text="اسم الحاج")
        self._owe.heading("passport", text="رقم الجواز")
        self._owe.heading("phone", text="الهاتف")
        self._owe.heading("amount", text="المتبقّي")
        self._owe.column("#0", width=230, anchor="e", stretch=True)
        self._owe.column("passport", width=120, anchor="center", stretch=False)
        self._owe.column("phone", width=120, anchor="center", stretch=False)
        self._owe.column("amount", width=110, anchor="center", stretch=False)
        self._owe.pack(fill=BOTH, expand=True)

        row = ttk.Frame(outer)
        row.pack(anchor="e", pady=(10, 0))
        ttk.Button(row, text=rtl("📄  تصدير PDF"), style="Act.TButton",
                   command=self._export_pdf).pack(side=RIGHT, padx=3)
        ttk.Button(row, text="إغلاق", style="Ghost.TButton",
                   command=self.destroy).pack(side=RIGHT, padx=3)
        self.bind("<Escape>", lambda _e: self.destroy())

        self._refresh_dist()
        self._refresh_outstanding()

    def _export_pdf(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self, title="حفظ الإحصاءات والملخّص المالي",
            defaultextension=".pdf",
            initialfile=f"إحصاءات_ومالية_{date.today().isoformat()}.pdf",
            filetypes=(("ملف PDF", "*.pdf"), ("كل الملفات", "*.*")))
        if not path:
            return
        from .pdf_io import export_stats_pdf
        try:
            export_stats_pdf(self._records, path, season=self._season)
        except PermissionError:
            messagebox.showerror("الملف مفتوح",
                                 "الملف مفتوح في برنامج آخر. أغلقه ثم أعد المحاولة.",
                                 parent=self)
            return
        except Exception as exc:
            messagebox.showerror("خطأ في التصدير", str(exc), parent=self)
            return
        if messagebox.askyesno("تم الحفظ", f"حُفظ:\n{path}\n\nفتحه الآن؟", parent=self):
            import os
            try:
                os.startfile(path)
            except Exception:
                pass

    def _refresh_dist(self) -> None:
        from .stats import distribution
        key = self._group_map[self._group_var.get()]
        self._dist.delete(*self._dist.get_children())
        for b in distribution(self._records, key):
            bar = "█" * max(1, round(b.percent / 4))     # شريط بصري مصغّر
            self._dist.insert("", END, text=b.label,
                              values=(b.count, f"{b.percent}%", bar))

    def _refresh_outstanding(self) -> None:
        from .stats import outstanding
        from .fields import format_amount
        self._owe.delete(*self._owe.get_children())
        items = outstanding(self._records)
        total = sum(a for _r, a in items)
        self._owe_total.config(
            text=f"عدد المتأخّرين: {len(items)}  •  إجمالي المتبقّي: {format_amount(total)}")
        for rec, amount in items:
            name = rec.full_name_ar or rec.full_name_en or "—"
            self._owe.insert("", END, text=name, values=(
                str(rec.passport_number or "").strip() or "—",
                str(rec.phone or "").strip() or "—", format_amount(amount)))


class BadgesDialog(Toplevel):
    """بطاقات الحجّاج (وجه وخلفية، 5.2×8سم): إدخال بيانات الخلفية ثم التصدير."""

    _DEFAULT_CAMPAIGN = "المصطفى للحج والعمرة"

    def __init__(self, parent, records, session) -> None:
        super().__init__(parent)
        self._records = records
        self._session = session
        self.title("🪪 بطاقات الحجّاج")
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)

        outer = ttk.Frame(self, padding=18)
        outer.pack(fill=BOTH, expand=True)
        ttk.Label(outer, text=f"إنشاء بطاقات لـ {len(records)} حاجاً",
                  font=("Segoe UI Semibold", 12), foreground=TEXT,
                  background=BG).pack(anchor="e")
        ttk.Label(outer, foreground=MUTED, font=("Segoe UI", 9), justify="right",
                  background=BG, wraplength=420,
                  text=rtl("الوجه: الشعار + الصورة الشخصية (للرجال) أو رمز امرأة "
                           "محجّبة (للنساء) + الاسم والهاتف والفندق.\n"
                           "الخلفية: الشعار + المعلومات أدناه.")).pack(
            anchor="e", pady=(2, 12))

        form = ttk.Frame(outer)
        form.pack(fill=X)
        self._company = StringVar(value=self._DEFAULT_CAMPAIGN)
        self._preacher = StringVar(value="")
        self._emergency = StringVar(value="")

        def row(label, var):
            fr = ttk.Frame(form)
            fr.pack(fill=X, pady=3)
            ttk.Label(fr, text=label, font=("Segoe UI", 10), foreground=TEXT,
                      background=BG, width=18, anchor="e").pack(side=RIGHT, padx=(6, 0))
            e = ttk.Entry(fr, textvariable=var, width=30, justify="right",
                          font=("Segoe UI", 10))
            install_entry_editing(e)
            e.pack(side=RIGHT, fill=X, expand=True)

        row("اسم الحملة", self._company)
        row("رقم واعظ الحملة", self._preacher)
        row("رقم الطوارئ", self._emergency)

        ttk.Label(outer, text="الإداريون (اختياري — سطر لكل إداري):",
                  font=("Segoe UI", 10), foreground=TEXT, background=BG).pack(
            anchor="e", pady=(8, 2))
        self._admins = tk.Text(outer, height=3, width=44, font=("Segoe UI", 10),
                               wrap="word")
        self._admins.pack(fill=X)

        btns = ttk.Frame(outer)
        btns.pack(anchor="e", pady=(16, 0))
        ttk.Button(btns, text=rtl("🪪  تصدير البطاقات"), style="Primary.TButton",
                   command=self._export).pack(side=RIGHT, padx=3)
        ttk.Button(btns, text="إغلاق", style="Ghost.TButton",
                   command=self.destroy).pack(side=RIGHT, padx=3)
        self.bind("<Escape>", lambda _e: self.destroy())

    def _export(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self, title="حفظ بطاقات الحجّاج", defaultextension=".pdf",
            initialfile=f"بطاقات_الحجاج_{date.today().isoformat()}.pdf",
            filetypes=(("ملف PDF", "*.pdf"), ("كل الملفات", "*.*")))
        if not path:
            return
        from .pdf_io import export_badges_pdf
        try:
            export_badges_pdf(
                self._records, path, company=self._company.get().strip(),
                session=self._session, preacher=self._preacher.get().strip(),
                admins=self._admins.get("1.0", "end").strip(),
                emergency=self._emergency.get().strip())
        except PermissionError:
            messagebox.showerror("الملف مفتوح",
                                 "الملف مفتوح في برنامج آخر. أغلقه ثم أعد المحاولة.",
                                 parent=self)
            return
        except Exception as exc:
            messagebox.showerror("خطأ في البطاقات", str(exc), parent=self)
            return
        self.destroy()
        if messagebox.askyesno("تم الحفظ",
                               f"حُفظت {len(self._records)} بطاقة:\n{path}\n\nفتحها الآن؟"):
            import os
            try:
                os.startfile(path)
            except Exception:
                pass


class QualityDialog(Toplevel):
    """فحص جودة الكشف: يعرض مشكلات الجواز والتكرار والنقص، ويقفز للسجل."""

    _TAGS = {
        "صلاحية الجواز": ("pp", "#F7E7E5", DANGER),
        "تكرار رقم الجواز": ("dup", "#FBF0DC", AMBER_FG),
        "نقص بيانات حرجة": ("miss", "#EFEBE4", "#555555"),
    }

    def __init__(self, parent, get_records, on_select, travel_ref=None) -> None:
        super().__init__(parent)
        self._get_records = get_records      # دالة تُعيد السجلات الحالية
        self._on_select = on_select          # (index) -> يحدّد السجل في الجدول
        self._travel_ref = travel_ref        # دالة تُعيد تاريخ سفر الموسم أو None
        self.title("🩺 فحص جاهزية الكشف")
        self.configure(bg=BG)
        self.transient(parent)
        self.geometry("720x520")

        outer = ttk.Frame(self, padding=16)
        outer.pack(fill=BOTH, expand=True)
        self._summary = ttk.Label(outer, font=("Segoe UI Semibold", 12),
                                  foreground=TEXT, background=BG)
        self._summary.pack(anchor="e")
        ttk.Label(outer, foreground=MUTED, font=("Segoe UI", 9), justify="right",
                  background=BG,
                  text=rtl("انقر نقراً مزدوجاً على مشكلة للانتقال إلى سجل الحاج "
                           "في الجدول الرئيسي.")).pack(anchor="e", pady=(2, 8))

        table = ttk.Frame(outer)
        table.pack(fill=BOTH, expand=True)
        scroll = ttk.Scrollbar(table, orient="vertical")
        scroll.pack(side=RIGHT, fill=Y)
        self._tree = ttk.Treeview(table, columns=("passport", "detail"),
                                  show="tree headings", height=15,
                                  yscrollcommand=scroll.set)
        self._tree.heading("#0", text="الحاج / نوع المشكلة")
        self._tree.heading("passport", text="رقم الجواز")
        self._tree.heading("detail", text="التفصيل")
        self._tree.column("#0", width=300, anchor="e", stretch=True)
        self._tree.column("passport", width=130, anchor="center", stretch=False)
        self._tree.column("detail", width=250, anchor="e", stretch=False)
        self._tree.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.config(command=self._tree.yview)
        for _kind, (tag, bg, fg) in self._TAGS.items():
            self._tree.tag_configure(tag, background=bg, foreground=fg)
        self._tree.bind("<Double-1>", lambda _e: self._jump())

        row = ttk.Frame(outer)
        row.pack(anchor="e", pady=(10, 0))
        ttk.Button(row, text=rtl("↻  إعادة الفحص"), style="Ghost.TButton",
                   command=self.refresh).pack(side=RIGHT, padx=3)
        ttk.Button(row, text="إغلاق", style="Ghost.TButton",
                   command=self.destroy).pack(side=RIGHT, padx=3)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.refresh()

    def refresh(self) -> None:
        from .quality import check_records, summary_text
        travel_ref = self._travel_ref() if callable(self._travel_ref) else None
        report = check_records(self._get_records(), travel_ref=travel_ref)
        self._tree.delete(*self._tree.get_children())
        if report.clean:
            self._summary.config(text=f"✓  {summary_text(report)}",
                                 foreground=SUCCESS_FG)
            return
        self._summary.config(
            text=f"⚠  {report.total} سجلاً — {summary_text(report)}",
            foreground=DANGER)
        for kind, items in report.by_kind().items():
            tag = self._TAGS.get(kind, ("miss", "#EEE", "#333"))[0]
            parent = self._tree.insert("", END, text=f"{kind}  ({len(items)})",
                                       open=True, tags=(tag,))
            for iss in items:
                self._tree.insert(parent, END, text=iss.name,
                                  values=(iss.passport or "—", iss.detail),
                                  tags=(tag, f"idx:{iss.index}"))

    def _jump(self) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        for tag in self._tree.item(sel[0], "tags"):
            if isinstance(tag, str) and tag.startswith("idx:"):
                self._on_select(int(tag[4:]))
                break


class RestoreDialog(Toplevel):
    """استعادة نسخة احتياطية مؤرّخة: يعرض اللقطات ويستعيد المختارة."""

    def __init__(self, parent, session, on_restore) -> None:
        super().__init__(parent)
        self._session = session
        self._on_restore = on_restore
        self._paths: dict[str, object] = {}
        self.title("↩ استعادة نسخة احتياطية")
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()
        self.geometry("520x440")

        outer = ttk.Frame(self, padding=16)
        outer.pack(fill=BOTH, expand=True)
        ttk.Label(outer, text="اختر نسخة احتياطية لاستعادتها",
                  font=("Segoe UI Semibold", 12), foreground=TEXT,
                  background=BG).pack(anchor="e")
        ttk.Label(outer, foreground=MUTED, font=("Segoe UI", 9), justify="right",
                  background=BG,
                  text=rtl("الاستعادة تستبدل الكشف الحالي — لكن يُحفظ الحالي "
                           "كنسخة قبلها، فلا يضيع شيء.")).pack(anchor="e", pady=(2, 8))

        table = ttk.Frame(outer)
        table.pack(fill=BOTH, expand=True)
        scroll = ttk.Scrollbar(table, orient="vertical")
        scroll.pack(side=RIGHT, fill=Y)
        self._tree = ttk.Treeview(table, columns=("count",), show="tree headings",
                                  height=12, yscrollcommand=scroll.set)
        self._tree.heading("#0", text="التاريخ والوقت")
        self._tree.heading("count", text="عدد السجلات")
        self._tree.column("#0", width=300, anchor="e", stretch=True)
        self._tree.column("count", width=120, anchor="center", stretch=False)
        self._tree.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.config(command=self._tree.yview)
        self._tree.bind("<Double-1>", lambda _e: self._restore())

        from .storage import list_snapshots, load_records, snapshot_label
        for path in list_snapshots():
            try:
                records, _note = load_records(path, session)
                count = str(len(records))
            except Exception:
                count = "—"
            iid = self._tree.insert("", END, text=snapshot_label(path),
                                    values=(count,))
            self._paths[iid] = path

        row = ttk.Frame(outer)
        row.pack(anchor="e", pady=(10, 0))
        ttk.Button(row, text=rtl("↩  استعادة المحدّدة"), style="Primary.TButton",
                   command=self._restore).pack(side=RIGHT, padx=3)
        ttk.Button(row, text="إغلاق", style="Ghost.TButton",
                   command=self.destroy).pack(side=RIGHT, padx=3)
        self.bind("<Escape>", lambda _e: self.destroy())

    def _restore(self) -> None:
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("لم يتم التحديد", "اختر نسخة من القائمة.", parent=self)
            return
        path = self._paths.get(sel[0])
        label = self._tree.item(sel[0], "text")
        from .storage import load_records
        try:
            records, _note = load_records(path, self._session)
        except Exception as exc:
            messagebox.showerror("تعذّرت الاستعادة", str(exc), parent=self)
            return
        self.destroy()
        self._on_restore(records, label)


class ImageKindDialog(Toplevel):
    """اختيار نوع الصور ونطاق الطباعة (كل المعروض / باص / خدمة تنفيذي).

    يضبط ``self.kinds`` (قائمة الأنواع) و``self.scope`` = (نوع النطاق، القيمة)،
    أو يبقي ``kinds`` = None عند الإلغاء.
    """

    def __init__(self, parent, *, transports=None, executives=None) -> None:
        super().__init__(parent)
        self.kinds: list[str] | None = None
        self.scope: tuple[str, str | None] = ("all", None)
        self.title("طباعة الجوازات والتصاريح")
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)

        from .images import ID_CARD, PASSPORT, PERMIT, PHOTO
        transports = transports or []
        executives = executives or []

        outer = ttk.Frame(self, padding=18)
        outer.pack(fill=BOTH, expand=True)

        # ---- نوع الصور ----
        ttk.Label(outer, text="نوع الصور للطباعة:",
                  font=("Segoe UI Semibold", 11), foreground=TEXT).pack(
            anchor="e", pady=(0, 8))
        self._choice = StringVar(value="pass_permit")
        self._map = {
            "pass_permit": [PASSPORT, PERMIT],
            "passport": [PASSPORT],
            "permit": [PERMIT],
            "id": [ID_CARD],
            "photo": [PHOTO],
            "all": [PASSPORT, ID_CARD, PERMIT, PHOTO],
        }
        for value, label in (("pass_permit", "الجوازات والتصاريح"),
                             ("passport", "صور الجوازات"),
                             ("permit", "التصاريح السعودية"),
                             ("id", "صور الهوية"),
                             ("photo", "الصور الشخصية"),
                             ("all", "كل الصور")):
            ttk.Radiobutton(outer, text=label, value=value,
                            variable=self._choice).pack(anchor="e", pady=1)

        ttk.Separator(outer, orient="horizontal").pack(fill=X, pady=10)

        # ---- نطاق الطباعة ----
        ttk.Label(outer, text="نطاق الطباعة:",
                  font=("Segoe UI Semibold", 11), foreground=TEXT).pack(
            anchor="e", pady=(0, 8))
        self._scope = StringVar(value="all")
        ttk.Radiobutton(outer, text="كل المعروض", value="all",
                        variable=self._scope).pack(anchor="e", pady=1)

        # صفّ الباص: زرّ اختيار + قائمة القيم
        bus_row = ttk.Frame(outer)
        bus_row.pack(fill=X, pady=1)
        self._bus = ttk.Combobox(bus_row, values=transports, state="readonly",
                                 width=16, justify="right")
        self._bus.pack(side=LEFT, padx=(0, 8))
        ttk.Radiobutton(bus_row, text="حسب رقم الباص", value="transport",
                        variable=self._scope).pack(side=RIGHT)
        self._bus.bind("<<ComboboxSelected>>",
                       lambda _e: self._scope.set("transport"))

        # صفّ الجيمس (خدمة التنفيذي)
        exec_row = ttk.Frame(outer)
        exec_row.pack(fill=X, pady=1)
        self._exec = ttk.Combobox(exec_row, values=executives, state="readonly",
                                  width=16, justify="right")
        self._exec.pack(side=LEFT, padx=(0, 8))
        ttk.Radiobutton(exec_row, text="حسب الجيمس (خدمة التنفيذي)",
                        value="executive", variable=self._scope).pack(side=RIGHT)
        self._exec.bind("<<ComboboxSelected>>",
                        lambda _e: self._scope.set("executive"))

        if not transports:
            self._bus.configure(state="disabled")
        if not executives:
            self._exec.configure(state="disabled")

        btns = ttk.Frame(outer)
        btns.pack(anchor="e", pady=(14, 0))
        ttk.Button(btns, text="طباعة", style="Act.TButton",
                   command=self._ok).pack(side=RIGHT, padx=4)
        ttk.Button(btns, text="إلغاء", style="Act.TButton",
                   command=self.destroy).pack(side=RIGHT)
        self.bind("<Escape>", lambda _e: self.destroy())

        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 3
        self.geometry(f"+{x}+{y}")

    def _ok(self) -> None:
        scope = self._scope.get()
        if scope == "transport":
            val = self._bus.get().strip()
            if not val:
                messagebox.showwarning("اختر الباص",
                                       "اختر رقم الباص من القائمة.", parent=self)
                return
            self.scope = ("transport", val)
        elif scope == "executive":
            val = self._exec.get().strip()
            if not val:
                messagebox.showwarning("اختر الخدمة",
                                       "اختر خدمة التنفيذي من القائمة.",
                                       parent=self)
                return
            self.scope = ("executive", val)
        else:
            self.scope = ("all", None)
        self.kinds = self._map[self._choice.get()]
        self.destroy()


class ProgramsDialog(Toplevel):
    """إعداد برامج الحملة الثلاثة — لكلٍّ بيانات رحلته وتكاليفه وخدماته.

    يُختار البرنامج من الأعلى (الأول/الثاني/الثالث)، وتُعرَض حقوله للتحرير،
    وتُحفَظ الثلاثة معاً في الإعدادات.
    """

    def __init__(self, parent, app) -> None:
        super().__init__(parent)
        self.app = app
        self.title("🗂 برامج الحملة")
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)

        from .programs import FIELD_GROUPS, PROGRAM_NAMES, TRANSPORT_OPTIONS
        self._groups = FIELD_GROUPS
        self.programs = app._load_programs()
        self._current = 0
        self._vars: dict[str, StringVar] = {}

        outer = ttk.Frame(self, padding=16)
        outer.pack(fill=BOTH, expand=True)

        # اختيار البرنامج
        top = ttk.Frame(outer)
        top.pack(fill=X, pady=(0, 10))
        ttk.Label(top, text="البرنامج:", font=("Segoe UI Semibold", 11),
                  foreground=TEXT).pack(side=RIGHT, padx=(0, 8))
        self._sel = StringVar(value="0")
        for idx, name in enumerate(PROGRAM_NAMES):
            ttk.Radiobutton(top, text=name, value=str(idx), variable=self._sel,
                            command=self._switch).pack(side=RIGHT, padx=4)

        # الحقول مجمّعة
        body = ttk.Frame(outer)
        body.pack(fill=BOTH, expand=True)
        body.columnconfigure(0, weight=1)
        r = 0
        for gtitle, gfields in self._groups:
            ttk.Label(body, text=gtitle, font=("Segoe UI Semibold", 11),
                      foreground=BRONZE, background=BG).grid(
                row=r, column=0, columnspan=2, sticky="e", pady=(10, 3))
            r += 1
            for key, label, kind in gfields:
                ttk.Label(body, text=label, foreground=TEXT).grid(
                    row=r, column=1, sticky="e", padx=(10, 0), pady=3)
                var = StringVar()
                self._vars[key] = var
                if kind == "transport":
                    ttk.Combobox(body, textvariable=var, state="readonly",
                                 values=list(TRANSPORT_OPTIONS), width=18,
                                 justify="right").grid(row=r, column=0,
                                                       sticky="ew", pady=3)
                else:
                    just = "center" if kind == "money" else "right"
                    ttk.Entry(body, textvariable=var, width=26,
                              justify=just).grid(row=r, column=0, sticky="ew",
                                                 pady=3)
                r += 1

        hint = ttk.Label(outer, foreground=MUTED,
                         text="القيم تُحفَظ للموسم وتُستخدم مرجعاً للتكاليف "
                              "والخدمات.")
        hint.pack(anchor="e", pady=(10, 8))

        btns = ttk.Frame(outer)
        btns.pack(anchor="e")
        ttk.Button(btns, text="حفظ", style="Act.TButton",
                   command=self._save).pack(side=RIGHT, padx=4)
        ttk.Button(btns, text="إغلاق", style="Act.TButton",
                   command=self.destroy).pack(side=RIGHT)
        self.bind("<Escape>", lambda _e: self.destroy())

        self._load_into_form(0)
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 8
        self.geometry(f"+{x}+{y}")

    def _load_into_form(self, idx: int) -> None:
        prog = self.programs[idx]
        for key, var in self._vars.items():
            var.set(str(getattr(prog, key, "")))

    def _dump_form_to(self, idx: int) -> None:
        from .fields import format_amount, parse_amount
        prog = self.programs[idx]
        money_keys = {k for _t, fs in self._groups for k, _l, kind in fs
                      if kind == "money"}
        for key, var in self._vars.items():
            val = var.get().strip()
            if key in money_keys and val:
                amt = parse_amount(val)
                if amt is not None:
                    val = format_amount(amt)
            setattr(prog, key, val)

    def _switch(self) -> None:
        new = int(self._sel.get())
        if new != self._current:
            self._dump_form_to(self._current)
            self._current = new
            self._load_into_form(new)

    def _save(self) -> None:
        self._dump_form_to(self._current)
        self.app._save_programs(self.programs)
        self.app.set_status("حُفظت برامج الحملة", ok=True)
        self.destroy()


class StickersDialog(Toplevel):
    """اختيار نوع الاستيكرات (حقائب/غرف/أظرف). يضبط self.kind أو None عند الإلغاء."""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.kind: str | None = None
        self.title("طباعة الاستيكرات")
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)

        outer = ttk.Frame(self, padding=18)
        outer.pack(fill=BOTH, expand=True)
        ttk.Label(outer, text="اختر نوع الاستيكرات:",
                  font=("Segoe UI Semibold", 11), foreground=TEXT).pack(
            anchor="e", pady=(0, 10))

        self._choice = StringVar(value="bag")
        for value, label in (("bag", "🧳  استيكرات الحقائب"),
                             ("room", "🚪  استيكرات الغرف"),
                             ("envelope", "✉  استيكرات الأظرف")):
            ttk.Radiobutton(outer, text=label, value=value,
                            variable=self._choice).pack(anchor="e", pady=2)

        ttk.Label(outer, foreground=MUTED,
                  text="تُطبع للمعروض حالياً؛ استخدم الفلاتر لتحديد الحجّاج.").pack(
            anchor="e", pady=(8, 8))

        btns = ttk.Frame(outer)
        btns.pack(anchor="e", pady=(6, 0))
        ttk.Button(btns, text="معاينة وطباعة", style="Act.TButton",
                   command=self._ok).pack(side=RIGHT, padx=4)
        ttk.Button(btns, text="إلغاء", style="Act.TButton",
                   command=self.destroy).pack(side=RIGHT)
        self.bind("<Escape>", lambda _e: self.destroy())

        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 3
        self.geometry(f"+{x}+{y}")

    def _ok(self) -> None:
        self.kind = self._choice.get()
        self.destroy()


class ReceiptDialog(Toplevel):
    """سند قبض (Receipt Voucher) — تعبئة الحقول ثم **معاينة فقط** بلا حفظ مباشر.

    تُبنى الحقول تلقائياً من بيانات الحاج (الاسم/المبلغ/البيان)، ويمكن تعديلها،
    ثم يُفتح ملف PDF مؤقّت في العارض الافتراضي؛ للمستخدم أن يطبع أو يحفظ من هناك.
    """

    def __init__(self, parent, rec, *, number: str = "0001",
                 season: str = "") -> None:
        super().__init__(parent)
        self.rec = rec
        self.season = season
        self.title("سند قبض — معاينة")
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)

        from .fields import num_to_words_en, parse_amount
        from .pdf_io import build_receipt_description

        amount = parse_amount(rec.paid_amount)
        if amount is None:
            amount = parse_amount(rec.program_value) or 0.0

        outer = ttk.Frame(self, padding=18)
        outer.pack(fill=BOTH, expand=True)
        outer.columnconfigure(0, weight=1)
        name = rec.full_name_ar or rec.full_name_en or "—"
        ttk.Label(outer, text=f"🧾  سند قبض — {name}",
                  font=("Segoe UI Semibold", 12), foreground=TEXT).grid(
            row=0, column=0, columnspan=2, sticky="e", pady=(0, 12))

        self.v_number = StringVar(value=str(number))
        self.v_date = StringVar(value=date.today().strftime("%B %d, %Y"))
        self.v_amount = StringVar(value=f"{amount:,.2f}")
        self.v_words = StringVar(value=num_to_words_en(amount))
        self.v_bank = StringVar(value="Bank Transfer")

        def row(r, label, var, width=36):
            ttk.Label(outer, text=label, foreground=TEXT).grid(
                row=r, column=1, sticky="e", padx=(10, 0), pady=4)
            e = ttk.Entry(outer, textvariable=var, width=width, justify="right")
            e.grid(row=r, column=0, sticky="ew", pady=4)
            return e

        row(1, "رقم السند:", self.v_number)
        row(2, "التاريخ:", self.v_date)
        amount_entry = row(3, "المبلغ (AED):", self.v_amount)
        row(4, "المبلغ كتابةً (إنجليزي):", self.v_words)
        row(5, "طريقة الدفع / البنك:", self.v_bank)

        # «المبلغ كتابةً» يتحدّث تلقائياً عند تغيير المبلغ (ويبقى قابلاً للتعديل)
        def _sync_words(_e=None):
            a = parse_amount(self.v_amount.get())
            if a is not None:
                self.v_words.set(num_to_words_en(a))
        amount_entry.bind("<FocusOut>", _sync_words)
        amount_entry.bind("<Return>", _sync_words)

        ttk.Label(outer, text="البيان «وذلك عن»:", foreground=TEXT).grid(
            row=6, column=1, sticky="ne", padx=(10, 0), pady=(8, 4))
        self.txt = tk.Text(outer, width=54, height=4, wrap="word",
                           font=("Segoe UI", 10))
        self.txt.grid(row=6, column=0, sticky="ew", pady=(8, 4))
        self.txt.insert("1.0", build_receipt_description(
            rec, season=season, amount=amount))

        ttk.Label(outer, foreground=MUTED,
                  text="معاينة فقط — يفتح في العارض؛ احفظ أو اطبع من هناك.").grid(
            row=7, column=0, columnspan=2, sticky="e", pady=(4, 10))

        btns = ttk.Frame(outer)
        btns.grid(row=8, column=0, columnspan=2, sticky="e")
        ttk.Button(btns, text="👁  معاينة", style="Act.TButton",
                   command=self._preview).pack(side=RIGHT, padx=4)
        ttk.Button(btns, text="إغلاق", style="Act.TButton",
                   command=self.destroy).pack(side=RIGHT)
        self.bind("<Escape>", lambda _e: self.destroy())

        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 3
        self.geometry(f"+{x}+{y}")

    def _preview(self) -> None:
        import os
        import tempfile
        from .fields import parse_amount
        from .pdf_io import export_receipt_pdf

        amount = parse_amount(self.v_amount.get()) or 0.0
        number = self.v_number.get().strip() or "0001"
        safe = re.sub(r'[\\/:*?"<>|]+', "-", number) or "0001"
        path = Path(tempfile.gettempdir()) / f"receipt_{safe}.pdf"
        try:
            export_receipt_pdf(
                self.rec, path, season=self.season, number=number,
                date_str=self.v_date.get().strip(), amount=amount,
                amount_words=self.v_words.get().strip(),
                description=self.txt.get("1.0", "end").strip(),
                bank=self.v_bank.get().strip() or "Bank Transfer",
            )
        except Exception as exc:
            messagebox.showerror("خطأ في السند", str(exc), parent=self)
            return
        try:
            os.startfile(str(path))            # يفتح في العارض الافتراضي للمعاينة
        except Exception as exc:
            messagebox.showerror("تعذّر الفتح", str(exc), parent=self)


class InvoiceDialog(Toplevel):
    """فاتورة ضريبية / فاتورة إلكترونية (QR) — تعبئة ثم **معاينة فقط** بلا حفظ.

    بيانات الشركة (الرقم الضريبي/الهاتف/العنوان) تُحفظ لإعادة استخدامها لاحقاً.
    """

    def __init__(self, parent, rec, app, *, number: str = "INV-0001",
                 season: str = "", electronic: bool = False) -> None:
        super().__init__(parent)
        self.rec = rec
        self.app = app
        self.season = season
        self.electronic = electronic
        kind = "فاتورة إلكترونية" if electronic else "فاتورة ضريبية"
        self.title(kind + " — معاينة")
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)

        from .pdf_io import build_invoice_item
        co = app._company_info()

        outer = ttk.Frame(self, padding=18)
        outer.pack(fill=BOTH, expand=True)
        outer.columnconfigure(0, weight=1)
        name = rec.full_name_ar or rec.full_name_en or "—"
        icon = "💳" if electronic else "🧾"
        ttk.Label(outer, text=f"{icon}  {kind} — {name}",
                  font=("Segoe UI Semibold", 12), foreground=TEXT).grid(
            row=0, column=0, columnspan=2, sticky="e", pady=(0, 12))

        self.v_number = StringVar(value=str(number))
        self.v_date = StringVar(value=date.today().isoformat())
        self.v_trn = StringVar(value=co["trn"])
        self.v_phone = StringVar(value=co["phone"])
        self.v_addr = StringVar(value=co["address"])
        self.v_notes = StringVar(value="")

        self._r = 1

        def field(label, var, width=42):
            ttk.Label(outer, text=label, foreground=TEXT).grid(
                row=self._r, column=1, sticky="e", padx=(10, 0), pady=4)
            ttk.Entry(outer, textvariable=var, width=width, justify="right").grid(
                row=self._r, column=0, sticky="ew", pady=4)
            self._r += 1

        field("رقم الفاتورة:", self.v_number)
        field("التاريخ:", self.v_date)
        field("الرقم الضريبي للشركة (TRN):", self.v_trn)
        field("هاتف الشركة:", self.v_phone)
        field("عنوان الشركة:", self.v_addr)

        ttk.Label(outer, text="وصف البند:", foreground=TEXT).grid(
            row=self._r, column=1, sticky="ne", padx=(10, 0), pady=(8, 4))
        self.txt = tk.Text(outer, width=52, height=3, wrap="word",
                           font=("Segoe UI", 10))
        self.txt.grid(row=self._r, column=0, sticky="ew", pady=(8, 4))
        self.txt.insert("1.0", build_invoice_item(rec, season=season))
        self._r += 1
        field("ملاحظات:", self.v_notes)

        ttk.Label(outer, foreground=MUTED,
                  text="معاينة فقط — يفتح في العارض؛ احفظ أو اطبع من هناك.").grid(
            row=self._r, column=0, columnspan=2, sticky="e", pady=(4, 10))
        self._r += 1
        btns = ttk.Frame(outer)
        btns.grid(row=self._r, column=0, columnspan=2, sticky="e")
        ttk.Button(btns, text="👁  معاينة", style="Act.TButton",
                   command=self._preview).pack(side=RIGHT, padx=4)
        if electronic:
            ttk.Button(btns, text="📄  ملف XML (PEPPOL)", style="Act.TButton",
                       command=self._export_xml).pack(side=RIGHT, padx=4)
        ttk.Button(btns, text="إغلاق", style="Act.TButton",
                   command=self.destroy).pack(side=RIGHT)
        self.bind("<Escape>", lambda _e: self.destroy())

        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 4
        self.geometry(f"+{x}+{y}")

    def _company(self) -> dict:
        co = dict(self.app._company_info())
        co["trn"] = self.v_trn.get().strip()
        co["phone"] = self.v_phone.get().strip()
        co["address"] = self.v_addr.get().strip()
        self.app._save_company(co)
        return co

    def _preview(self) -> None:
        import os
        import tempfile
        from .pdf_io import export_invoice_pdf

        co = self._company()
        num = self.v_number.get().strip() or "INV-0001"
        safe = re.sub(r'[\\/:*?"<>|]+', "-", num) or "INV"
        tag = "einvoice" if self.electronic else "invoice"
        path = Path(tempfile.gettempdir()) / f"{tag}_{safe}.pdf"
        try:
            export_invoice_pdf(
                self.rec, path, company=co, number=num,
                date_str=self.v_date.get().strip(), electronic=self.electronic,
                season=self.season, item_desc=self.txt.get("1.0", "end").strip(),
                notes=self.v_notes.get().strip(),
            )
        except Exception as exc:
            messagebox.showerror("خطأ في الفاتورة", str(exc), parent=self)
            return
        try:
            os.startfile(str(path))
        except Exception as exc:
            messagebox.showerror("تعذّر الفتح", str(exc), parent=self)

    def _export_xml(self) -> None:
        """يبني ملف الفاتورة الإلكترونية الرسمي (UBL 2.1 / PINT AE) ويفتحه."""
        import os
        import tempfile
        from .einvoice import export_invoice_xml

        co = self._company()
        num = self.v_number.get().strip() or "INV-0001"
        safe = re.sub(r'[\\/:*?"<>|]+', "-", num) or "INV"
        path = Path(tempfile.gettempdir()) / f"einvoice_{safe}.xml"
        try:
            export_invoice_xml(
                self.rec, path, company=co, number=num,
                date_str=self.v_date.get().strip(),
                item_desc=self.txt.get("1.0", "end").strip(),
            )
        except Exception as exc:
            messagebox.showerror("خطأ في ملف XML", str(exc), parent=self)
            return
        try:
            os.startfile(str(path))
        except Exception as exc:
            messagebox.showerror("تعذّر الفتح", str(exc), parent=self)


class ContractDialog(Toplevel):
    """عقد خدمات حج — تعبئة وبنود قابلة للتحرير ثم **معاينة فقط** بلا حفظ."""

    def __init__(self, parent, rec, app, *, number: str = "CON-0001",
                 season: str = "") -> None:
        super().__init__(parent)
        self.rec = rec
        self.app = app
        self.season = season
        self.title("عقد خدمات حج — معاينة")
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)

        from .pdf_io import build_contract_body
        co = app._company_info()

        outer = ttk.Frame(self, padding=18)
        outer.pack(fill=BOTH, expand=True)
        outer.columnconfigure(0, weight=1)
        name = rec.full_name_ar or rec.full_name_en or "—"
        ttk.Label(outer, text=f"📜  عقد خدمات حج — {name}",
                  font=("Segoe UI Semibold", 12), foreground=TEXT).grid(
            row=0, column=0, columnspan=2, sticky="e", pady=(0, 12))

        self.v_number = StringVar(value=str(number))
        self.v_date = StringVar(value=date.today().isoformat())
        self.v_trn = StringVar(value=co["trn"])
        self.v_phone = StringVar(value=co["phone"])
        self._r = 1

        def field(label, var):
            ttk.Label(outer, text=label, foreground=TEXT).grid(
                row=self._r, column=1, sticky="e", padx=(10, 0), pady=4)
            ttk.Entry(outer, textvariable=var, width=42, justify="right").grid(
                row=self._r, column=0, sticky="ew", pady=4)
            self._r += 1

        field("رقم العقد:", self.v_number)
        field("التاريخ:", self.v_date)
        field("الرقم الضريبي للشركة (TRN):", self.v_trn)
        field("هاتف الشركة:", self.v_phone)

        ttk.Label(outer, text="بنود العقد:", foreground=TEXT).grid(
            row=self._r, column=1, sticky="ne", padx=(10, 0), pady=(8, 4))
        self.txt = tk.Text(outer, width=66, height=15, wrap="word",
                           font=("Segoe UI", 10))
        self.txt.grid(row=self._r, column=0, sticky="ew", pady=(8, 4))
        self.txt.insert("1.0", build_contract_body(rec, company=co, season=season))
        self._r += 1

        ttk.Label(outer, foreground=MUTED,
                  text="معاينة فقط — يفتح في العارض؛ احفظ أو اطبع من هناك.").grid(
            row=self._r, column=0, columnspan=2, sticky="e", pady=(4, 10))
        self._r += 1
        btns = ttk.Frame(outer)
        btns.grid(row=self._r, column=0, columnspan=2, sticky="e")
        ttk.Button(btns, text="👁  معاينة", style="Act.TButton",
                   command=self._preview).pack(side=RIGHT, padx=4)
        ttk.Button(btns, text="إغلاق", style="Act.TButton",
                   command=self.destroy).pack(side=RIGHT)
        self.bind("<Escape>", lambda _e: self.destroy())

        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 6
        self.geometry(f"+{x}+{y}")

    def _preview(self) -> None:
        import os
        import tempfile
        from .pdf_io import export_contract_pdf

        co = dict(self.app._company_info())
        co["trn"] = self.v_trn.get().strip()
        co["phone"] = self.v_phone.get().strip()
        self.app._save_company(co)
        num = self.v_number.get().strip() or "CON-0001"
        safe = re.sub(r'[\\/:*?"<>|]+', "-", num) or "CON"
        path = Path(tempfile.gettempdir()) / f"contract_{safe}.pdf"
        try:
            export_contract_pdf(
                self.rec, path, company=co, number=num,
                date_str=self.v_date.get().strip(), season=self.season,
                body=self.txt.get("1.0", "end").strip(),
            )
        except Exception as exc:
            messagebox.showerror("خطأ في العقد", str(exc), parent=self)
            return
        try:
            os.startfile(str(path))
        except Exception as exc:
            messagebox.showerror("تعذّر الفتح", str(exc), parent=self)


class EditDialog(Toplevel):
    """نافذة تعديل بيانات حاج واحد، موزّعة على تبويبات حسب نوع البيانات."""

    # التبويبات ومحتواها. الحقول غير المذكورة تُضاف إلى "أخرى".
    TABS: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("بيانات الحاج", ("family_number", "reference_number", "full_name_ar",
                          "full_name_en", "phone", "program")),
        ("الجواز", ("passport_number", "nationality_ar", "sex", "birth_date",
                    "expiry_date")),
        ("السفر", ("airline", "flight_number", "travel_class", "pnr",
                   "arrival_date", "arrival_time", "departure_date",
                   "departure_time", "transport")),
        ("الإقامة والخدمات", ("hotel", "room_type", "room_number",
                              "executive_service", "wheelchair", "hady")),
        ("المالية", ("program_value", "paid_amount")),
        ("ملاحظات", ("notes", "staff")),
    )

    def __init__(self, parent, record: PassportData, on_save, *,
                 title: str = "تعديل بيانات الحاج",
                 save_text: str = "حفظ", session=None) -> None:
        super().__init__(parent)
        self.record = record
        self.on_save = on_save
        self.session = session
        self.vars: dict[str, StringVar] = {}
        # عمليات الصور المؤجّلة حتى الحفظ: النوع -> مسار جديد أو "DELETE" أو None
        self._pending_images: dict[str, str | None] = {}
        self._thumb_refs: dict[str, object] = {}    # مراجع لمنع حذف الصور من الذاكرة

        self.title(title)
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)

        outer = ttk.Frame(self, padding=14)
        outer.pack(fill=BOTH, expand=True)

        notebook = ttk.Notebook(outer)
        notebook.pack(fill=BOTH, expand=True)

        by_key = {f.key: f for f in EDITABLE}
        placed: set[str] = set()

        for tab_title, keys in self.TABS:
            fields = [by_key[k] for k in keys if k in by_key]
            if not fields:
                continue
            placed.update(f.key for f in fields)
            notebook.add(self._make_tab(notebook, fields), text=tab_title)

        leftover = [f for f in EDITABLE if f.key not in placed]
        if leftover:
            notebook.add(self._make_tab(notebook, leftover), text="أخرى")

        notebook.add(self._build_images_tab(notebook), text="الصور")

        # المتبقي محسوب تلقائياً، فنعرضه للقراءة فقط
        self.remaining = ttk.Label(
            outer, font=("Segoe UI Semibold", 10), foreground=TEXT
        )
        self.remaining.pack(anchor="e", pady=(10, 0))
        self._update_remaining()
        for key in ("program_value", "paid_amount"):
            if key in self.vars:
                self.vars[key].trace_add("write", lambda *_a: self._update_remaining())

        if record.warnings:
            ttk.Label(
                outer, text="⚠ " + " | ".join(record.warnings), foreground="#B26A00",
                font=("Segoe UI", 9), wraplength=640, justify="right",
            ).pack(anchor="e", pady=(8, 0))

        btns = ttk.Frame(outer)
        btns.pack(anchor="e", pady=(14, 0))
        ttk.Button(btns, text=save_text, command=self._save,
                   style="Act.TButton").pack(side=RIGHT, padx=4)
        ttk.Button(btns, text="إلغاء", command=self.destroy,
                   style="Act.TButton").pack(side=RIGHT)

        self.bind("<Return>", lambda _e: self._save())
        self.bind("<Escape>", lambda _e: self.destroy())

    def _make_tab(self, parent, fields) -> ttk.Frame:
        """يبني تبويباً بعمودين: العنوان يميناً وحقل الإدخال يساره."""
        frame = ttk.Frame(parent, padding=14)
        half = (len(fields) + 1) // 2

        for i, f in enumerate(fields):
            col = 0 if i < half else 2
            row = i if i < half else i - half
            var = StringVar(value=getattr(self.record, f.key, ""))
            self.vars[f.key] = var

            label = f.label
            if f.key in MRZ_FILLED:
                label += " *"          # نجمة: مقروء من الجواز
            ttk.Label(frame, text=label, font=("Segoe UI", 10)).grid(
                row=row, column=col + 1, sticky="e", padx=(16, 6), pady=5
            )
            if f.key == "program":
                # قائمة اختيار البرنامج + زرّ تطبيق (تعبئة تلقائية واحتساب)
                from .programs import PROGRAM_NAMES
                cell = ttk.Frame(frame)
                cell.grid(row=row, column=col, sticky="w", pady=5)
                ttk.Combobox(cell, textvariable=var, state="readonly", width=14,
                             justify="center",
                             values=[""] + list(PROGRAM_NAMES)).pack(side=LEFT)
                ttk.Button(cell, text="تطبيق", style="Ghost.TButton", width=7,
                           command=self._apply_program).pack(side=LEFT, padx=(4, 0))
                continue
            entry = ttk.Entry(frame, textvariable=var, width=26, justify="center")
            entry.grid(row=row, column=col, sticky="w", pady=5)
            install_entry_editing(entry)      # نسخ/لصق/قص + قائمة يمين
        return frame

    def _apply_program(self) -> None:
        """يعبّئ حقول الرحلة من البرنامج المختار ويحسب قيمة البرنامج."""
        from .fields import format_amount
        from .programs import (AUTOFILL_MAP, load_programs, program_by_name,
                               program_cost)
        from .storage import load_settings

        name = self.vars.get("program", StringVar()).get().strip()
        if not name:
            messagebox.showinfo("اختر البرنامج",
                                "اختر برنامج الحملة من القائمة أولاً.", parent=self)
            return
        prog = program_by_name(load_programs(load_settings()), name)
        if prog is None:
            messagebox.showwarning("غير معرّف",
                                   "هذا البرنامج غير معرّف. عرّفه من «برامج "
                                   "الحملة» أولاً.", parent=self)
            return

        filled = []
        for pkey, rkey in AUTOFILL_MAP:
            val = str(getattr(prog, pkey, "")).strip()
            if val and rkey in self.vars:
                self.vars[rkey].set(val)
                filled.append(rkey)

        total, breakdown = program_cost(
            prog,
            room_type=self.vars.get("room_type", StringVar()).get(),
            wheelchair=self.vars.get("wheelchair", StringVar()).get(),
            hady=self.vars.get("hady", StringVar()).get(),
            executive_service=self.vars.get("executive_service", StringVar()).get(),
            travel_class=self.vars.get("travel_class", StringVar()).get(),
            transport=self.vars.get("transport", StringVar()).get(),
        )
        if total and "program_value" in self.vars:
            self.vars["program_value"].set(format_amount(total))

        lines = "\n".join(f"• {lbl}: {format_amount(amt)}" for lbl, amt in breakdown)
        summary = f"طُبِّق «{name}».\n"
        if filled:
            summary += "عُبّئت: الفندق/الطيران/التواريخ/المواصلات حسب توفّرها.\n"
        summary += (f"\nالتكلفة المحسوبة: {format_amount(total)}\n{lines}"
                    if breakdown else
                    "\nلم تُحسَب تكلفة (حدّد نوع الغرفة/الخدمات ثم أعد التطبيق).")
        messagebox.showinfo("تطبيق البرنامج", summary, parent=self)

    _IMAGE_TYPES = (
        ("صور وملفات PDF", "*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp *.pdf"),
        ("صور", "*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp"),
        ("ملفات PDF", "*.pdf"),
        ("كل الملفات", "*.*"),
    )

    def _build_images_tab(self, parent) -> ttk.Frame:
        """تبويب الصور: الجواز والشخصية والهوية والتصريح — تُحفظ مشفّرة (شبكة 2×2)."""
        frame = ttk.Frame(parent, padding=12)
        self._img_preview: dict[str, ttk.Label] = {}
        from .images import KINDS, KIND_LABELS
        for index, kind in enumerate(KINDS):
            row, base = divmod(index, 2)
            col = 1 - base                    # RTL: أول صورة أقصى اليمين
            box = ttk.Frame(frame, padding=6)
            box.grid(row=row, column=col, padx=10, pady=4, sticky="n")
            ttk.Label(box, text=KIND_LABELS[kind], font=("Segoe UI Semibold", 10),
                      foreground=TEXT).pack()
            preview = ttk.Label(box, relief="solid", borderwidth=1,
                                anchor="center", width=22)
            preview.pack(pady=4, ipadx=3, ipady=3)
            self._img_preview[kind] = preview
            btns = ttk.Frame(box)
            btns.pack()
            ttk.Button(btns, text="اختيار", style="Act.TButton",
                       command=lambda k=kind: self._choose_image(k)).pack(side=RIGHT, padx=2)
            ttk.Button(btns, text="حذف", style="Act.TButton",
                       command=lambda k=kind: self._remove_image(k)).pack(side=RIGHT)
            self._render_preview(kind)
        return frame

    def _choose_image(self, kind: str) -> None:
        path = filedialog.askopenfilename(
            parent=self, title="اختر صورة", filetypes=self._IMAGE_TYPES,
        )
        if path:
            self._pending_images[kind] = path
            self._render_preview(kind, source=path)

    def _remove_image(self, kind: str) -> None:
        self._pending_images[kind] = "DELETE"
        self._render_preview(kind)

    def _render_preview(self, kind: str, source: str | None = None) -> None:
        """يعرض معاينة مصغّرة (من مسار جديد أو من المخزَّن المشفّر).

        يقبل الصور وملفات PDF — يُعرض من الـ PDF أول صفحة.
        """
        label = self._img_preview[kind]
        pending = self._pending_images.get(kind)
        try:
            from PIL import ImageTk
            from . import images as imgmod

            src = source or (pending if pending and pending != "DELETE" else None)
            raw = None
            if src:
                raw = Path(src).read_bytes()
            elif pending != "DELETE" and imgmod.has_image(self.record.image_id, kind):
                raw = imgmod.load_image(self.record.image_id, kind, self.session)

            image = imgmod.to_pil_image(raw) if raw else None
            if image is None:
                self._thumb_refs.pop(kind, None)
                is_pdf = bool(raw) and imgmod.is_pdf(raw)
                label.configure(image="", width=22,
                                text="ملف PDF" if is_pdf else "لا توجد صورة")
                return
            image.thumbnail((150, 150))
            thumb = ImageTk.PhotoImage(image)
            self._thumb_refs[kind] = thumb        # مرجع يمنع حذفها من الذاكرة
            label.configure(image=thumb, text="", width=0)
        except Exception:
            label.configure(image="", text="تعذّر عرض الملف", width=22)

    def _save_images(self) -> None:
        """ينفّذ عمليات الصور المؤجّلة عند حفظ السجل."""
        from . import images as imgmod
        for kind, action in self._pending_images.items():
            if action == "DELETE":
                imgmod.delete_image(self.record.image_id, kind)
            elif action:                          # مسار صورة جديدة
                if not self.record.image_id:
                    self.record.image_id = imgmod.new_image_id()
                imgmod.save_image(self.record.image_id, kind, action, self.session)

    def _update_remaining(self) -> None:
        total = parse_amount(self.vars.get("program_value", StringVar()).get())
        paid = parse_amount(self.vars.get("paid_amount", StringVar()).get())
        if total is None:
            self.remaining.configure(text="المبلغ المتبقي: —")
        else:
            self.remaining.configure(
                text=f"المبلغ المتبقي: {format_amount(total - (paid or 0))}"
            )

    def _save(self) -> None:
        # سجل بلا اسم ولا رقم جواز لا يفيد أحداً في الكشف
        identifying = ("full_name_ar", "full_name_en", "passport_number",
                       "reference_number")
        if not any(self.vars[k].get().strip() for k in identifying if k in self.vars):
            messagebox.showwarning(
                "بيانات ناقصة",
                "أدخل على الأقل اسم الحاج أو رقم الجواز أو الرقم المرجعي.",
                parent=self,
            )
            return

        for key, var in self.vars.items():
            value = var.get().strip()
            # نوحّد الأوقات والمبالغ عند الحفظ ليتطابق الجدول والتصدير
            if key in TIME_KEYS:
                value = normalize_time(value)
            elif key in MONEY_KEYS:
                amount = parse_amount(value)
                if amount is not None:
                    value = format_amount(amount)
            setattr(self.record, key, value)

        # التعديل اليدوي يلغي التحذيرات — المستخدم راجع البيانات
        self.record.warnings = []
        self.record.checksum_ok = True
        try:
            self._save_images()
        except Exception as exc:
            messagebox.showerror("تعذّر حفظ الصور", str(exc), parent=self)
            return
        self.on_save(self.record)
        self.destroy()


def _show_splash(root):
    """شاشة بداية بالشعار تظهر لحظةً أثناء تجهيز النافذة."""
    try:
        splash = Toplevel(root)
        splash.overrideredirect(True)
        splash.configure(bg=BG)
        frame = tk.Frame(splash, bg=BG, padx=48, pady=40)
        frame.pack()
        img = logo_image(splash, width=240)
        if img is not None:
            lbl = tk.Label(frame, image=img, bg=BG)
            lbl.image = img                    # مرجع يمنع جمع القمامة
            lbl.pack()
        tk.Label(frame, text="برنامج الحج", bg=BG, fg=ACCENT,
                 font=("Segoe UI Semibold", 16)).pack(pady=(12, 0))
        tk.Label(frame, text="جارٍ التحميل…", bg=BG, fg=MUTED,
                 font=("Segoe UI", 10)).pack(pady=(4, 0))
        splash.update_idletasks()
        w, h = splash.winfo_width(), splash.winfo_height()
        sw, sh = splash.winfo_screenwidth(), splash.winfo_screenheight()
        splash.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")
        splash.update()
        return splash
    except Exception:
        return None


# ⚠ وضع مؤقّت أثناء البناء: يفتح البرنامج **بلا رقم سري** وبلا تشفير، على ملف
# بيانات منفصل (hajjaj-open.json)، دون المساس بالكشف المشفّر ولا حساب الدخول.
# لإعادة الدخول برقم سري لاحقاً: اجعل هذا False، فتعود بياناتك المشفّرة.
OPEN_MODE_NO_LOGIN = True


def main() -> None:
    if OPEN_MODE_NO_LOGIN:
        session, open_mode = None, True        # بلا دخول، بلا تشفير (مؤقتاً)
    else:
        session = authenticate()               # الدخول أولاً بمفتاح فك التشفير
        if session is None:
            return
        open_mode = False

    root = Tk()
    root.withdraw()                            # نخفيها حتى تجهز، خلف شاشة البداية
    apply_window_icon(root)
    splash = _show_splash(root)
    HajjApp(root, session, open_mode=open_mode)

    def _reveal():
        if splash is not None:
            splash.destroy()
        root.deiconify()

    root.after(900, _reveal)
    root.mainloop()

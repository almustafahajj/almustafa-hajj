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

from . import app_mode
from .logging_setup import get_logger
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
    AccountsDialog, ChangePasswordDialog, NewRecoveryKeyDialog,
    RecoveryKeyDialog, apply_window_icon, authenticate, logo_image, rtl,
)
from .storage import (
    default_data_path, load_records, load_settings, save_records, save_settings,
)


_log = get_logger(__name__)


def open_in_viewer(path) -> None:
    """يفتح ملفاً في العارض الافتراضي للنظام (ويندوز/ماك/لينكس).

    يوحّد سلوك ``os.startfile`` (ويندوز فقط) عبر الأنظمة: ``open`` على ماك،
    و``xdg-open`` على لينكس. يرفع ``OSError`` إن تعذّر الفتح لتُعالَج كما كانت.
    """
    import os
    import subprocess
    import sys
    p = str(path)
    if sys.platform == "darwin":
        subprocess.run(["open", p], check=False)
    elif os.name == "nt":
        os.startfile(p)                      # type: ignore[attr-defined]
    else:
        subprocess.run(["xdg-open", p], check=False)


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

# أعمدة مخفيّة افتراضياً في الجدول (تفاصيل إضافية تظهر عند الطلب من «الأعمدة»)
_DEFAULT_HIDDEN_COLS = (
    "source_file", "visa_number", "visa_status", "permit_status", "masar_number",
    "mahram_name", "mahram_relation", "blood_type", "medical_conditions",
    "medications", "vaccination", "insurance", "emergency_name",
    "emergency_phone", "emergency_relation",
)

# ---- ألوان العلامة الثابتة (لا تتبدّل بين الفاتح والداكن) ----
ACCENT = "#241E17"          # فحميّ دافئ — سطح رؤوس الجدول (منسجم مع البرونزي)
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
        "DUE_BG": "#F8E4E2", "PAID_BG": "#E6F1E9",
    },
    "داكن": {
        "BG": "#1E1E22", "PANEL": "#26262B", "ROW_ALT": "#2C2C33",
        "HOVER_BG": "#3A3A44", "BORDER": "#3A3A44", "MUTED": "#9A948B",
        "TEXT": "#EAE6DF", "GHOST_BG": "#33333A", "GHOST_HOVER": "#3E3E48",
        "GHOST_LIGHT": "#4A4A54", "GHOST_EDGE": "#141418", "PANEL_EDGE": "#141418",
        "DUE_BG": "#3C2A2A", "PAID_BG": "#26332B",
    },
}
THEMES = tuple(_PALETTES)

# القيم الحالية (تُضبط بـ apply_theme)
BG = PANEL = ROW_ALT = HOVER_BG = BORDER = MUTED = TEXT = ""
GHOST_BG = GHOST_HOVER = GHOST_LIGHT = GHOST_EDGE = PANEL_EDGE = ""
DUE_BG = PAID_BG = ""


def apply_theme(name: str) -> None:
    """يضبط أدوار الألوان حسب الوضع (فاتح/داكن)."""
    global BG, PANEL, ROW_ALT, HOVER_BG, BORDER, MUTED, TEXT
    global GHOST_BG, GHOST_HOVER, GHOST_LIGHT, GHOST_EDGE, PANEL_EDGE
    global DUE_BG, PAID_BG
    pal = _PALETTES.get(name, _PALETTES["فاتح"])
    BG, PANEL, ROW_ALT = pal["BG"], pal["PANEL"], pal["ROW_ALT"]
    HOVER_BG, BORDER, MUTED = pal["HOVER_BG"], pal["BORDER"], pal["MUTED"]
    TEXT = pal["TEXT"]
    GHOST_BG, GHOST_HOVER = pal["GHOST_BG"], pal["GHOST_HOVER"]
    GHOST_LIGHT, GHOST_EDGE, PANEL_EDGE = pal["GHOST_LIGHT"], pal["GHOST_EDGE"], pal["PANEL_EDGE"]
    DUE_BG, PAID_BG = pal["DUE_BG"], pal["PAID_BG"]


apply_theme("فاتح")            # الافتراضي حتى تُحمَّل الإعدادات

# سمات لون البرنامج (accent): (البرونزي، الداكن، الفاتح، الحافة)
ACCENTS = {
    "برونزي": ("#8A6E4B", "#6F5738", "#B4986E", "#4E3C25"),
    "أخضر زمرّدي": ("#2E7D5B", "#245F46", "#5CA588", "#1B4433"),
    "أزرق ملكي": ("#2C5AA0", "#214679", "#5B84C0", "#173156"),
    "عنّابي": ("#9B3B45", "#7C2E37", "#C06A72", "#5A1F26"),
}


def apply_accent(name: str) -> None:
    """يضبط لون التمييز (البرونزي) وتدرّجاته حسب السمة المختارة."""
    global BRONZE, BRONZE_DARK, BRONZE_LIGHT, BRONZE_EDGE, ACCENT_HOVER
    a = ACCENTS.get(name, ACCENTS["برونزي"])
    BRONZE, BRONZE_DARK, BRONZE_LIGHT, BRONZE_EDGE = a
    ACCENT_HOVER = BRONZE


# ---- عائلة الخطّ (تُكتشف عند الإقلاع؛ افتراضياً Segoe UI) ----
_FUI = "Segoe UI"
_FSB = "Segoe UI Semibold"


def detect_fonts(root) -> None:
    """يختار أجمل خطّ عربي متوفّر (Dubai/Sakkal) مع تراجع إلى Segoe UI."""
    global _FUI, _FSB
    try:
        from tkinter import font as _tkfont
        fams = set(_tkfont.families(root))
    except Exception:
        return
    for reg, semi in (("Dubai", "Dubai Medium"),
                      ("Sakkal Majalla", "Sakkal Majalla"),
                      ("Segoe UI", "Segoe UI Semibold")):
        if reg in fams:
            _FUI = reg
            _FSB = semi if semi in fams else reg
            return


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


def add_tooltip(widget, text: str) -> None:
    """تلميح صغير يظهر عند مرور الفأرة فوق الأداة (Tooltip)."""
    if not text:
        return
    state = {"tip": None}

    def show(_e=None):
        if state["tip"] is not None:
            return
        try:
            x = widget.winfo_rootx() + 18
            y = widget.winfo_rooty() + widget.winfo_height() + 4
        except tk.TclError:
            return
        tw = tk.Toplevel(widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(tw, text=text, bg="#1A1A1A", fg="#FFFFFF", justify="right",
                 font=(_FUI, 9), padx=8, pady=3).pack()
        state["tip"] = tw

    def hide(_e=None):
        if state["tip"] is not None:
            state["tip"].destroy()
            state["tip"] = None

    widget.bind("<Enter>", show, add="+")
    widget.bind("<Leave>", hide, add="+")
    widget.bind("<ButtonPress>", hide, add="+")


def open_preview(parent, export_fn, base_name: str, ext: str):
    """يولّد الملف مؤقّتاً ويفتحه للمعاينة في العارض الافتراضي.

    نمطٌ موحّد لكل أوامر التصدير/الطباعة: بلا نافذة «حفظ باسم»؛ يفتح الملف
    في عارضه (PDF أو إكسل) ومنه يطبع المستخدم أو يحفظ نسخةً. يعيد المسار أو
    None عند الفشل/التعذّر.
    """
    import os
    import tempfile
    safe = re.sub(r'[\\/:*?"<>|]+', "-", str(base_name)).strip() or "ملف"
    path = os.path.join(tempfile.gettempdir(), f"{safe}.{ext}")
    try:
        export_fn(path)
    except PermissionError:
        messagebox.showerror("الملف مفتوح",
                             "الملف مفتوح في العارض. أغلقه ثم أعد المحاولة.",
                             parent=parent)
        return None
    except Exception as exc:
        _log.exception("فشل توليد المستند: %s", path)
        messagebox.showerror("خطأ في التجهيز", str(exc), parent=parent)
        return None
    try:
        open_in_viewer(path)
    except OSError as exc:
        _log.warning("تعذّر فتح المعاينة %s: %s", path, exc)
        messagebox.showerror("تعذّر فتح المعاينة", str(exc), parent=parent)
        return None
    return path


def enable_minmax(win) -> None:
    """يُفعّل أزرار التصغير والتكبير (مع الإغلاق) في نافذة منبثقة على ويندوز.

    النوافذ العابرة (transient) تُظهر زرّ الإغلاق فقط افتراضياً؛ نضيف نمطي
    WS_MINIMIZE/MAXIMIZE ونزيل نمط «نافذة الأدوات» فتظهر الأزرار الثلاثة.
    """
    try:
        win.resizable(True, True)
        win.update_idletasks()
        import ctypes

        u = ctypes.windll.user32
        hwnd = u.GetParent(win.winfo_id()) or win.winfo_id()
        GWL_STYLE, GWL_EXSTYLE = -16, -20
        WS_MINIMIZEBOX, WS_MAXIMIZEBOX = 0x20000, 0x10000
        WS_EX_TOOLWINDOW, WS_EX_APPWINDOW = 0x80, 0x40000
        style = u.GetWindowLongW(hwnd, GWL_STYLE)
        u.SetWindowLongW(hwnd, GWL_STYLE, style | WS_MINIMIZEBOX | WS_MAXIMIZEBOX)
        ex = u.GetWindowLongW(hwnd, GWL_EXSTYLE)
        u.SetWindowLongW(hwnd, GWL_EXSTYLE,
                         (ex & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW)
        had_grab = win.grab_current() is win
        win.withdraw()
        win.deiconify()
        if had_grab:
            try:
                win.grab_set()
            except Exception:
                pass
    except Exception:
        try:
            win.resizable(True, True)
        except Exception:
            pass


class HajjApp:
    def __init__(self, root: Tk, session=None, open_mode: bool = False) -> None:
        self.root = root
        self.session = session      # يحمل مفتاح التشفير؛ None في الاختبارات
        self._open_mode = open_mode  # فتح بلا رقم سري (بلا تشفير) — ملف بيانات منفصل
        self._logout_requested = False   # يرفعه «تسجيل الخروج» ليعيد main شاشة الدخول
        self._exit_action = None          # 'logout' | 'restart' | None (إغلاق عادي)
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

        # الترتيب عرض فقط: لا يمسّ ترتيب self.records الأصلي، فيمكن إلغاؤه
        self.sort_field: str | None = None
        self.sort_desc = False

        # مكدّس التراجع: لقطات السجلات قبل العمليات المُتلِفة (حذف/مسح/تعديل جماعي)
        self._undo_stack: list[tuple[str, list]] = []

        # إعدادات الواجهة المحفوظة (تُستعاد بين الجلسات)
        self._ui = dict(self._settings.get("ui", {}))
        from . import i18n
        i18n.set_lang(self._ui.get("ui_lang", "ar"))
        self._density = self._ui.get("density", "عادي")
        if self._density not in self._DENSITY:
            self._density = "عادي"
        self._font_size = self._ui.get("font_size", "متوسط")
        if self._font_size not in self._FONT_SIZES:
            self._font_size = "متوسط"
        self._hidden_cols: set[str] = set(
            self._ui.get("hidden_columns", list(_DEFAULT_HIDDEN_COLS)))
        # الوضع الفاتح/الداكن — يُطبّق قبل بناء الأنماط
        self._theme = self._ui.get("theme", "فاتح")
        if self._theme not in THEMES:
            self._theme = "فاتح"
        apply_theme(self._theme)
        self._accent = self._ui.get("accent", "برونزي")
        if self._accent not in ACCENTS:
            self._accent = "برونزي"
        apply_accent(self._accent)

        root.title(app_mode.label("window_title"))
        geom = self._ui.get("geometry")
        root.geometry(geom if isinstance(geom, str) and "x" in geom else "1280x740")
        root.minsize(900, 560)
        root.configure(bg=BG)

        detect_fonts(root)            # اختيار أجمل خطّ عربي متوفّر قبل بناء الأنماط
        self._build_styles()
        self._build_header()
        self._build_toolbar()
        self._build_filters()
        self._build_table()
        self._build_status()
        self._bind_shortcuts()

        self._load_saved_data()
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._setup_auto_lock()
        if self.session is not None:
            if not self._ui.get("onboarded"):
                self.root.after(1300, self._show_onboarding)   # أول تشغيل
            elif self._ui.get("show_welcome", True):
                self.root.after(1300, self._show_welcome)

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
        s.configure("Treeview.Heading", font=(_FSB, 10),
                    background=ACCENT, foreground="white", padding=8, relief="raised",
                    borderwidth=2, lightcolor="#4A4038", darkcolor="#17120D",
                    bordercolor="#17120D")
        s.map("Treeview.Heading",
              background=[("active", BRONZE)],
              relief=[("pressed", "sunken"), ("active", "raised")])

        # ---- أزرار ثلاثية الأبعاد (حواف مشطوفة + ضغطة غائرة) ----
        def bevel(name, bg, fg, light, dark, hover, *, bold=True, pad=(15, 8)):
            font = (_FSB, 10) if bold else (_FUI, 10)
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
            font = (_FSB, 10) if bold else (_FUI, 10)
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
        s.configure("Toolbar.TMenubutton", font=(_FSB, 11),
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

    def _apply_table_style(self) -> None:
        """يطبّق كثافة الصفوف وحجم الخط على الجدول (قابل للتغيير حياً)."""
        rowheight = self._DENSITY.get(self._density, 26)
        size = self._FONT_SIZES.get(self._font_size, 10)
        s = self._style
        s.configure("Treeview", rowheight=rowheight, font=(_FUI, size),
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

        from . import i18n
        titles = ttk.Frame(bar, style="Toolbar.TFrame")
        titles.pack(side=RIGHT)
        ttk.Label(titles, text=i18n.tr(app_mode.label("program_season")),
                  font=(_FSB, 17),
                  foreground=TEXT, background=BG).pack(side=RIGHT)
        year_box = ttk.Combobox(
            titles, textvariable=self.season_year, state="readonly",
            width=6, font=(_FSB, 15), values=HIJRI_YEARS,
        )
        year_box.pack(side=RIGHT, padx=(8, 0))
        year_box.bind("<<ComboboxSelected>>", lambda _e: self._on_season_change())

        # حالة الجلسة والحماية أقصى اليسار
        if self.session is not None:
            info = ttk.Frame(bar, style="Toolbar.TFrame")
            info.pack(side=LEFT)
            ttk.Label(info, text=f"👤  {self.session.username}  ·  {self.session.role_label}",
                      font=(_FSB, 10), foreground=TEXT,
                      background=BG).pack(anchor="w")
            ttk.Label(info, text=i18n.tr("🔒 البيانات مشفّرة"), font=(_FUI, 9),
                      foreground=BRONZE, background=BG).pack(anchor="w")
            for text, action in (
                ("تغيير كلمة المرور", self.change_password),
                ("مفتاح استرداد جديد", self.new_recovery_key),
            ):
                link = ttk.Label(info, text=i18n.tr(text), font=(_FUI, 9, "underline"),
                                 foreground=TEXT, background=BG, cursor="hand2")
                link.pack(anchor="w")
                link.bind("<Button-1>", lambda _e, run=action: run())
            logout_btn = ttk.Button(bar, text=rtl(i18n.tr("🚪  تسجيل الخروج")),
                                    style="Ghost.TButton", command=self.do_logout)
            logout_btn.pack(side=LEFT, padx=(0, 8))
            add_tooltip(logout_btn, "حفظ البيانات والعودة إلى شاشة الدخول")
        elif self._open_mode:
            info = ttk.Frame(bar, style="Toolbar.TFrame")
            info.pack(side=LEFT)
            ttk.Label(info, text=i18n.tr("🔓 وضع مفتوح — بلا رقم سري"),
                      font=(_FSB, 10), foreground=AMBER_FG,
                      background=BG).pack(anchor="w")
            ttk.Label(info, text=i18n.tr("البيانات غير مشفّرة (مؤقتاً)"), font=(_FUI, 9),
                      foreground=MUTED, background=BG).pack(anchor="w")

        # زرّ لوحة التحكم — بارز في وسط الترويسة
        _dash = ttk.Button(bar, text=rtl(i18n.tr("🏠  لوحة التحكم")), style="Primary.TButton",
                           command=self.do_dashboard)
        _dash.pack(side=LEFT, padx=16)
        add_tooltip(_dash, "مؤشّرات سريعة + إعدادات العرض")

        # زرّ التبديل السريع بين وضعي الحج والعمرة (يعرض الوضع الآخر)
        _other = app_mode.UMRAH if app_mode.is_hajj() else app_mode.HAJJ
        _sicon = "🌙" if _other == app_mode.UMRAH else "🕋"
        _switch = ttk.Button(
            bar, style="Ghost.TButton", command=self.switch_mode,
            text=rtl(i18n.tr(f"{_sicon}  التبديل إلى {app_mode.mode_label(_other)}")))
        _switch.pack(side=LEFT, padx=(0, 8))
        add_tooltip(_switch, "الانتقال مباشرةً إلى الوضع الآخر (تُحفظ بياناتك أولاً)")

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

    # ---------------------------------------------------- الصلاحيات والحسابات
    def _can_edit(self) -> bool:
        """صلاحية تعديل البيانات — مفتوحة في الوضع المفتوح/الاختبار (بلا جلسة)."""
        return self.session is None or self.session.can_edit

    def _is_admin(self) -> bool:
        return self.session is None or self.session.can_manage_accounts

    def _require_edit(self) -> bool:
        """يتحقق من صلاحية التعديل، ويُظهر تنبيهاً إن كان الحساب «مطّلعاً»."""
        if self._can_edit():
            return True
        self.set_status("حسابك «مطّلع» — لا يملك صلاحية التعديل", warn=True)
        return False

    def manage_accounts(self) -> None:
        """يفتح نافذة إدارة الحسابات — للمدير فقط."""
        if not self._is_admin():
            self.set_status("إدارة الحسابات للمدير فقط", warn=True)
            return
        AccountsDialog(self.root, self.session)
        self._audit("إدارة الحسابات")

    # ------------------------------------------------------ القفل التلقائي
    def _setup_auto_lock(self) -> None:
        """يفعّل القفل التلقائي عند الخمول إن كانت المدّة > 0 (لوضع الدخول)."""
        self._idle_after = None
        if self.session is None:
            return
        try:
            mins = int(self._settings.get("auto_lock_min", 0) or 0)
        except (TypeError, ValueError):
            mins = 0
        self._idle_ms = max(0, mins) * 60000
        if self._idle_ms <= 0:
            return
        for seq in ("<Motion>", "<Key>", "<Button>"):
            self.root.bind_all(seq, self._reset_idle, add="+")
        self._reset_idle()

    def _reset_idle(self, _e=None) -> None:
        if getattr(self, "_idle_ms", 0) <= 0:
            return
        if self._idle_after is not None:
            try:
                self.root.after_cancel(self._idle_after)
            except Exception:
                pass
        self._idle_after = self.root.after(self._idle_ms, self._auto_lock)

    def _auto_lock(self) -> None:
        """يُقفل الجلسة بعد الخمول ويعود إلى شاشة الدخول (بلا تأكيد)."""
        if self.session is None:
            return
        try:
            self.save_data()
        except Exception:
            pass
        self._audit("قفل تلقائي بعد خمول")
        self._logout_requested = True
        self.root.destroy()

    def set_auto_lock(self) -> None:
        """يضبط مدّة القفل التلقائي بالدقائق (0 = معطّل)."""
        if self.session is None:
            self.set_status("القفل التلقائي متاح في وضع الدخول فقط", warn=True)
            return
        from tkinter import simpledialog
        current = int(self._settings.get("auto_lock_min", 0) or 0)
        mins = simpledialog.askinteger(
            "القفل التلقائي",
            "أقفل البرنامج تلقائياً بعد كم دقيقة من الخمول؟\n(0 = معطّل)",
            parent=self.root, initialvalue=current, minvalue=0, maxvalue=240)
        if mins is None:
            return
        self._settings["auto_lock_min"] = int(mins)
        try:
            save_settings(self._settings)
        except OSError:
            pass
        self._idle_ms = int(mins) * 60000
        self._audit("ضبط القفل التلقائي", f"{mins} دقيقة")
        if int(mins) > 0:
            for seq in ("<Motion>", "<Key>", "<Button>"):
                self.root.bind_all(seq, self._reset_idle, add="+")
            self._reset_idle()
            self.set_status(f"القفل التلقائي: {mins} دقيقة", ok=True)
        else:
            if getattr(self, "_idle_after", None) is not None:
                try:
                    self.root.after_cancel(self._idle_after)
                except Exception:
                    pass
                self._idle_after = None
            self.set_status("عُطّل القفل التلقائي", ok=True)

    def do_logout(self) -> None:
        """يسجّل الخروج ويعود إلى شاشة الدخول (يبقى البرنامج مفتوحاً)."""
        if self.session is None:
            return                    # الوضع المفتوح لا يتطلّب دخولاً
        if not messagebox.askyesno(
            "تسجيل الخروج",
            f"تسجيل خروج «{self.session.username}» والعودة إلى شاشة الدخول؟",
            parent=self.root,
        ):
            return
        try:
            self.save_data()          # اطمئنان: احفظ آخر تغييرات قبل الإغلاق
        except Exception:
            pass
        self._audit("تسجيل خروج")
        self._logout_requested = True
        self._exit_action = "logout"
        self.root.destroy()           # ينهي حلقة الأحداث؛ main يعيد شاشة الدخول

    def switch_mode(self) -> None:
        """يعود إلى شاشة اختيار الوضع (حج/عمرة) مع حفظ البيانات أولاً."""
        other = app_mode.UMRAH if app_mode.is_hajj() else app_mode.HAJJ
        if not messagebox.askyesno(
            "تبديل الوضع",
            f"الانتقال إلى وضع «{app_mode.mode_label(other)}»؟\n"
            "تُحفظ بياناتك الحالية، ولكلّ وضع بياناته المستقلّة.",
            parent=self.root,
        ):
            return
        try:
            self.save_data()
        except Exception:
            pass
        self._audit("تبديل الوضع", app_mode.mode_label(other))
        # ننتقل مباشرةً إلى نافذة الوضع الآخر (بلا المرور بشاشة الاختيار)
        self._exit_action = f"switch:{other}"
        self.root.destroy()

    def cycle_accent(self) -> None:
        """يبدّل لون البرنامج (accent) إلى التالي ويعيد البناء بلونه."""
        order = list(ACCENTS)
        try:
            nxt = order[(order.index(self._accent) + 1) % len(order)]
        except ValueError:
            nxt = order[0]
        self._ui["accent"] = nxt
        self._settings["ui"] = self._ui
        try:
            save_settings(self._settings)
        except OSError:
            pass
        self._audit("تغيير لون البرنامج", nxt)
        if self.session is None:
            apply_accent(nxt)
            self.set_status(f"لون البرنامج: {nxt}", ok=True)
            return
        self._exit_action = "restart"
        self.root.destroy()

    def change_language(self) -> None:
        """يختار لغة الواجهة (عربي/إنجليزي) ويعيد بناء البرنامج بها."""
        from . import i18n
        cur = i18n.get_lang()
        new = "en" if cur == "ar" else "ar"
        label = i18n.LANG_LABELS[new]
        if not messagebox.askyesno(
                "اللغة / Language",
                f"تبديل لغة الواجهة إلى «{label}»؟\nSwitch interface language to "
                f"«{label}»?\n\nسيُعاد بناء الواجهة (تبقى جلستك وبياناتك)."):
            return
        self._ui["ui_lang"] = new
        self._settings["ui"] = self._ui
        try:
            save_settings(self._settings)
        except OSError:
            pass
        self._audit("تغيير اللغة", new)
        if self.session is None:
            # وضع الاختبار/المفتوح بلا حلقة إعادة تشغيل — نطبّق فوراً قدر الإمكان
            i18n.set_lang(new)
            return
        self._exit_action = "restart"
        self.root.destroy()

    def _on_season_change(self) -> None:
        """يحفظ السنة الهجرية المختارة."""
        self._settings["season_year"] = self.season_year.get()
        try:
            save_settings(self._settings)
        except OSError:
            pass
        self.set_status(f"موسم الحج: {self.season_year.get()}هـ")

    def _programs_by_name(self) -> dict:
        """خريطة {اسم البرنامج: البرنامج} — لمرجع تاريخ السفر وتدقيق التطابق."""
        from .programs import PROGRAM_NAMES, load_programs
        return dict(zip(PROGRAM_NAMES, load_programs(self._settings)))

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
                    icon=None, tip=None):
        """زر بقائمة منسدلة (Menubutton + Menu) بعناصر (نص، أمر)، بأيقونة اختيارية.

        العناوين والعناصر تُترجَم تلقائياً حسب لغة الواجهة (i18n.tr).
        """
        from . import i18n
        mb = ttk.Menubutton(parent, text=rtl(i18n.tr(text)), style=style,
                            direction="below")
        if icon is not None:
            img = self._icon(*icon)
            if img is not None:
                mb.configure(image=img, compound="right")
        menu = tk.Menu(mb, tearoff=0, font=(_FUI, 10))
        for entry in items:
            if entry is None:
                menu.add_separator()
            else:
                label, cmd = entry
                menu.add_command(label=i18n.tr(label), command=cmd)
        mb["menu"] = menu
        self._menus.append(menu)          # نحتفظ بمرجع لمنع جمع القمامة
        if tip:
            add_tooltip(mb, tip)
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
        # ---- القوائم الرئيسية السبع (مستوحاة من نظام إدارة الحجّ) ----
        BLUE, ORANGE, GOLD = "#2C5AA0", "#C77B30", "#C9A227"
        GRAY, GREEN = "#6B6459", "#2E7D46"

        # صلاحية التعديل تحدّد أي عناصر القوائم تظهر (المطّلع يرى المقروء فقط)
        ce = self._can_edit()

        # 📋 البرامج (إعداد — للمحرّر فأعلى)
        if ce:
            programs_items = [
                ("🌙  بدء موسم جديد", self.do_new_season),
                None,
                ("🗂  برامج الحملة (الأول/الثاني/الثالث)", self.do_programs),
                ("👥  المجموعات والمرشدون", self.do_groups),
            ]
            # جدول المناسك خاص بالحج — يُخفى في وضع العمرة
            if not app_mode.is_umrah():
                programs_items.append(("🗓  جدول المناسك", self.do_itinerary))
            programs_items.append(("🧳  مواعيد وتعليمات السفر", self.do_travel_info))
            programs_mb = self._menubutton(bar, "البرامج  ▾", programs_items,
                style="Ghost.TMenubutton", icon=("columns", BRONZE),
                tip="الموسم والبرامج والمجموعات ومواعيد السفر")
            programs_mb.pack(side=RIGHT, padx=3)

        # 🪪 الحجوزات (سجلّات الحجّاج)
        book_items = []
        if ce:
            book_items += [
                ("➕  إضافة حاج يدوياً", self.add_manual),
                None,
                ("✏️  تعديل السجل", self.edit_selected),
                ("✏️  تعديل جماعي للمحدّدين", self.bulk_edit_selected),
                ("🗑  حذف المحدد", self.delete_selected),
                ("↩  تراجع  (Ctrl+Z)", self.undo),
                None,
            ]
        book_items += [
            ("📱  رسالة واتساب للمحدّدين", self.do_whatsapp),
            ("🩺  فحص جاهزية الكشف", self.do_quality_check),
            ("✅  قائمة تحقّق الجاهزية", self.do_readiness),
            ("🎫  تسجيل الحضور (مسح QR/جواز)", self.do_checkin),
            ("📄  تقرير الحضور (معاينة)", self.do_attendance_report),
        ]
        if ce:
            book_items.append(("🧹  مسح الكل", self.clear_all))
        book_mb = self._menubutton(bar, "الحجوزات  ▾", book_items,
            style="Ghost.TMenubutton", icon=("id", BLUE),
            tip="سجلّات الحجّاج: إضافة/تعديل/حذف/واتساب/فحص")
        book_mb.pack(side=RIGHT, padx=3)

        # 🏨 إدارة التسكين
        housing_items = [
            ("🛏  إشغال الغرف", self.do_occupancy),
            None,
            ("🏨  تسكين إكسل", self.do_rooming_excel),
            ("🏨  تسكين PDF", self.do_rooming_pdf),
        ]
        # خيام المشاعر (منى/عرفة) خاصة بالحج — تُخفى في وضع العمرة
        if not app_mode.is_umrah():
            housing_items.append(("⛺  خيام المخيمات", self.do_camps))
        housing_mb = self._menubutton(bar, "إدارة التسكين  ▾", housing_items,
            style="Ghost.TMenubutton", icon=("tent", ORANGE),
            tip="إشغال الغرف وكشوف التسكين")
        housing_mb.pack(side=RIGHT, padx=3)

        # 💰 المالية والمحاسبة
        fin_mb = self._menubutton(bar, "المالية والمحاسبة  ▾", [
            ("🔎  اسأل بياناتك (أسئلة بالعربية)", self.ask_data),
            ("💰  متابعة التحصيل (المتأخرون)", self.open_collections),
            None,
            ("📊  إحصاءات وملخّص مالي", self.do_stats),
            ("📈  الرسوم البيانية", self.do_charts),
            ("📄  تصدير الإحصاءات والمالية PDF", self.do_stats_pdf),
            None,
            ("💵  سجلّ دفعات الحاج (الأقساط)", self.do_payments),
            ("🧮  المصروفات والمحاسبة", self.do_expenses),
            ("📄  كشف المتأخّرات المالية (معاينة)", self.do_arrears_report),
            ("🧾  سند قبض (معاينة)", self._receipt_selected),
            ("🧾  فاتورة ضريبية (معاينة)",
             lambda: self._invoice_selected(electronic=False)),
            ("💳  فاتورة إلكترونية PEPPOL (معاينة)",
             lambda: self._invoice_selected(electronic=True)),
            ("📜  عقد خدمات حج (معاينة)", self._contract_selected),
            None,
            ("🧾  توليد جماعي للمستندات (للمعروضين)", self.do_bulk_docs),
        ], style="Ghost.TMenubutton", icon=("chart", GOLD),
            tip="الإحصاءات والسندات والفواتير والعقود")
        fin_mb.pack(side=RIGHT, padx=3)

        # 📊 التقارير
        rep_mb = self._menubutton(bar, "التقارير  ▾", [
            ("📊  تصدير إكسل", self.do_export_excel),
            ("📄  تصدير PDF", self.do_export_pdf),
            ("🖨  طباعة المعروض", self.do_print_filtered),
            None,
            ("✈  كشف الطيران وأماديوس", self.do_airline),
            ("🚌  كشف المواصلات", self.do_transport),
            None,
            ("🪪  بطاقات الحجّاج", self.do_badges),
            ("🏷  طباعة الاستيكرات (حقائب/غرف/أظرف)", self.do_stickers),
            ("🖼  طباعة الجوازات والتصاريح", self.do_print_images),
        ], style="Ghost.TMenubutton", icon=("report", BLUE),
            tip="التصدير والكشوفات والبطاقات والطباعة")
        rep_mb.pack(side=RIGHT, padx=3)

        # ⚙ لوحة الإدارة (النسخ الاحتياطية والحساب)
        admin_items = [("🛡  نسخة احتياطية الآن", self.do_backup_now)]
        if ce:
            admin_items.append(("↩  استعادة نسخة احتياطية", self.do_restore))
        admin_items.append(("📝  سجلّ التدقيق", self.do_audit))
        # التبديل بين وضعي الحج والعمرة (يعرض الوضع الآخر)
        _other = app_mode.UMRAH if app_mode.is_hajj() else app_mode.HAJJ
        _switch_label = f"🕋  التبديل إلى {app_mode.mode_label(_other)}"
        admin_items += [None,
                        (_switch_label, self.switch_mode),
                        ("🧭  معالج الإعداد", self.do_onboarding),
                        ("🏠  شاشة الترحيب", self._show_welcome),
                        (f"🎨  لون البرنامج ({self._accent})", self.cycle_accent),
                        ("⌨  اختصارات لوحة المفاتيح", self.do_shortcuts),
                        ("🔄  التحقق من التحديثات", self.do_check_updates),
                        ("ℹ  حول البرنامج", self.do_about)]
        # زرّ اللغة يُظهر اللغة الهدف (عكس الحالية) بوضوح
        from . import i18n as _i18n
        _lang_item = ("🌐  التغيير إلى الإنجليزية (English)"
                      if _i18n.get_lang() == "ar"
                      else "🌐  التغيير إلى العربية (Switch to Arabic)")
        admin_items += [None, (_lang_item, self.change_language)]
        if self._is_admin() and self.session is not None:
            admin_items += [None, ("👥  إدارة الحسابات", self.manage_accounts)]
        if self.session is not None:
            admin_items += [None,
                            ("🔑  تغيير كلمة المرور", self.change_password),
                            ("🗝  مفتاح استرداد جديد", self.new_recovery_key),
                            ("🔒  القفل التلقائي عند الخمول", self.set_auto_lock),
                            None,
                            ("🚪  تسجيل الخروج", self.do_logout)]
        admin_mb = self._menubutton(bar, "لوحة الإدارة  ▾", admin_items,
                                    style="Ghost.TMenubutton", icon=("gear", GRAY),
                                    tip="النسخ الاحتياطية وسجلّ التدقيق والحسابات")
        admin_mb.pack(side=RIGHT, padx=3)

        # 📥 استيراد البيانات (للمحرّر فأعلى)
        if ce:
            import_mb = self._menubutton(bar, "استيراد البيانات  ▾", [
                ("📁  استيراد من إكسل", self.import_from_excel),
                ("📷  إضافة جوازات (صور / PDF)", self.add_images),
            ], style="Ghost.TMenubutton", icon=("add", GREEN),
                tip="استيراد من إكسل أو قراءة الجوازات")
            import_mb.pack(side=RIGHT, padx=3)

        # شريط التقدّم يُنشأ مخفيّاً ويظهر فقط أثناء العمليات الطويلة
        self.progress = ttk.Progressbar(bar, mode="determinate", length=180)

        self._shadow_strip(self.root)     # ظلّ ناعم يفصل الشريط عمّا تحته

    def _shadow_strip(self, parent) -> None:
        """ظلّ متدرّج رفيع (ثلاثة أسطر) يوحي بعمق تحت الشريط."""
        for col in ("#CDC4B2", "#DED6C7", "#ECE6DB"):
            tk.Frame(parent, bg=col, height=1).pack(fill=X)

    # الحقول القابلة للفلترة بقائمة منسدلة (تُملأ قيمها من البيانات)
    _FILTER_FIELDS = (
        ("group", "المجموعة"),
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

        # الأزرار أقصى يسار («الأعمدة» و«العرض» انتقلا إلى لوحة التحكم؛
        # و«الترتيب» و«مسح الفلاتر» إلى لوحة الفلاتر)
        self._icon_button(row1, "طباعة المعروض", self.do_print_filtered,
                          "Ghost.TButton", ("print", TEXT)).pack(side=LEFT, padx=3)

        # مربّع البحث الحر أقصى اليمين
        self.filter_search = StringVar()
        self.filter_search.trace_add("write", lambda *_a: self.refresh())
        entry = ttk.Entry(row1, textvariable=self.filter_search, width=20,
                          justify="right", font=(_FUI, 10))
        entry.pack(side=RIGHT, padx=(0, 6))
        self._search_entry = entry
        install_entry_editing(entry)
        ttk.Label(row1, text="🔍 بحث", font=(_FUI, 9),
                  background=BG, foreground=TEXT).pack(side=RIGHT, padx=(2, 4))

        # زرّ واحد يفتح لوحة كل الفلاتر (تجميع الفلاتر في قائمة واحدة)
        self._filter_btn = self._icon_button(
            row1, "الفلاتر  ▾", self._toggle_filter_panel, "Ghost.TButton",
            ("filter", TEXT))
        self._filter_btn.pack(side=RIGHT, padx=(0, 12))

        # صفّ رقائق الفلاتر النشطة (يُملأ ويُظهَر في refresh عند وجود فلاتر)
        self._chips_row = ttk.Frame(outer, style="Toolbar.TFrame")

        self._build_filter_panel()

    def _update_chips(self) -> None:
        """يعرض الفلاتر النشطة كوسوم قابلة للإزالة بنقرة."""
        if not hasattr(self, "_chips_row"):
            return
        for w in self._chips_row.winfo_children():
            w.destroy()
        active = []
        for key, label in self._FILTER_FIELDS:
            val = self.filter_vars[key].get()
            if val != self._ALL:
                active.append((f"{label}: {val}",
                               lambda k=key: (self.filter_vars[k].set(self._ALL),
                                              self.refresh())))
        q = self.filter_search.get().strip()
        if q:
            active.append((f"بحث: {q}", lambda: self.filter_search.set("")))

        if not active:
            self._chips_row.pack_forget()
            return
        self._chips_row.pack(fill=X, pady=(5, 0))
        ttk.Label(self._chips_row, text="الفلاتر النشطة:", font=(_FUI, 9),
                  foreground=MUTED, background=BG).pack(side=RIGHT, padx=(0, 6))
        for text, clear in active:
            chip = tk.Label(self._chips_row, text=f" ✕  {text} ", bg=GHOST_BG,
                            fg=TEXT, font=(_FUI, 9), padx=2, cursor="hand2")
            chip.pack(side=RIGHT, padx=3)
            chip.bind("<Button-1>", lambda _e, c=clear: c())

    def _build_filter_panel(self) -> None:
        """لوحة منسدلة تجمع كل الفلاتر التسعة في مكان واحد."""
        panel = Toplevel(self.root)
        panel.withdraw()
        panel.overrideredirect(True)
        panel.configure(bg=BORDER)                 # إطار رفيع
        self._filter_panel = panel
        inner = ttk.Frame(panel, style="Panel.TFrame", padding=14)
        inner.pack(padx=1, pady=1)
        ttk.Label(inner, text="تصفية الكشف", font=(_FSB, 11),
                  foreground=TEXT, background=BG).grid(row=0, column=0, columnspan=6,
                                                       sticky="e", pady=(0, 8))

        self.filter_vars: dict[str, StringVar] = {}
        self.filter_boxes: dict[str, ttk.Combobox] = {}
        cols = 3
        for index, (key, label) in enumerate(self._FILTER_FIELDS):
            r = 1 + index // cols
            c = (index % cols) * 2
            ttk.Label(inner, text=label, font=(_FUI, 9), foreground=TEXT,
                      background=BG).grid(row=r, column=c + 1, sticky="e", padx=(10, 3),
                                          pady=3)
            var = StringVar(value=self._ALL)
            box = ttk.Combobox(inner, textvariable=var, state="readonly",
                               width=13, font=(_FUI, 9), values=[self._ALL])
            box.grid(row=r, column=c, sticky="e", pady=3)
            box.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
            self.filter_vars[key] = var
            self.filter_boxes[key] = box

        # «ترتيب حسب» داخل اللوحة تحت الفلاتر
        ttk.Separator(inner, orient="horizontal").grid(
            row=97, column=0, columnspan=6, sticky="ew", pady=(12, 0))
        sort_row = ttk.Frame(inner, style="Panel.TFrame")
        sort_row.grid(row=98, column=0, columnspan=6, sticky="e", pady=(8, 0))
        ttk.Label(sort_row, text="ترتيب حسب", font=(_FUI, 9),
                  background=BG, foreground=TEXT).pack(side=RIGHT, padx=(2, 6))
        self.sort_var = StringVar(value=self._SORT_NONE)
        sort_box = ttk.Combobox(
            sort_row, textvariable=self.sort_var, state="readonly", width=16,
            font=(_FUI, 9),
            values=[self._SORT_NONE, *(label for _k, label in self._SORT_FIELDS)])
        sort_box.pack(side=RIGHT, padx=(0, 4))
        sort_box.bind("<<ComboboxSelected>>", lambda _e: self._apply_sort())
        self.sort_dir_btn = ttk.Button(sort_row, text="▲", width=3,
                                       command=self._toggle_sort_dir,
                                       style="Act.TButton")
        self.sort_dir_btn.pack(side=RIGHT)
        add_tooltip(self.sort_dir_btn, "اتجاه الترتيب: تصاعدي/تنازلي")

        btns = ttk.Frame(inner, style="Panel.TFrame")
        btns.grid(row=99, column=0, columnspan=6, sticky="e", pady=(12, 0))
        self._build_columns_menubutton(btns).pack(side=RIGHT, padx=3)
        ttk.Button(btns, text=rtl("⭐ فلاتر محفوظة"), style="Ghost.TButton",
                   command=self.do_filter_presets).pack(side=RIGHT, padx=3)
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

    def _ensure_col_vars(self) -> None:
        """يهيّئ متغيّرات إظهار الأعمدة مرّة واحدة (تُشارَك بين نقاط الاستدعاء)."""
        if getattr(self, "_col_vars", None):
            return
        self._col_vars: dict[str, tk.BooleanVar] = {
            f.key: tk.BooleanVar(value=f.key not in self._hidden_cols)
            for f in self._display_columns()
        }

    def _build_columns_menubutton(self, parent):
        mb = ttk.Menubutton(parent, text=rtl("الأعمدة ▾"),
                            style="Ghost.TMenubutton", direction="below")
        _img = self._icon("columns", TEXT)
        if _img is not None:
            mb.configure(image=_img, compound="right")
        menu = tk.Menu(mb, tearoff=0, font=(_FUI, 10))
        self._ensure_col_vars()
        for f in self._display_columns():
            menu.add_checkbutton(label=f.label, variable=self._col_vars[f.key],
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
        self._ensure_col_vars()
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
        menu = tk.Menu(mb, tearoff=0, font=(_FUI, 10))
        self._density_var = tk.StringVar(value=self._density)
        dmenu = tk.Menu(menu, tearoff=0, font=(_FUI, 10))
        for name in self._DENSITY:
            dmenu.add_radiobutton(label=name, value=name,
                                  variable=self._density_var,
                                  command=self._on_density_change)
        menu.add_cascade(label="كثافة الصفوف", menu=dmenu)
        self._fontsize_var = tk.StringVar(value=self._font_size)
        fmenu = tk.Menu(menu, tearoff=0, font=(_FUI, 10))
        for name in self._FONT_SIZES:
            fmenu.add_radiobutton(label=name, value=name,
                                  variable=self._fontsize_var,
                                  command=self._on_font_change)
        menu.add_cascade(label="حجم الخط", menu=fmenu)
        menu.add_separator()
        self._theme_var = tk.StringVar(value=self._theme)
        tmenu = tk.Menu(menu, tearoff=0, font=(_FUI, 10))
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
        self.root.bind("<Control-z>", lambda _e: self.undo())
        self.root.bind("<Control-Z>", lambda _e: self.undo())
        self.root.bind("<Control-k>", lambda _e: self.do_command_palette())
        self.root.bind("<Control-K>", lambda _e: self.do_command_palette())
        self.root.bind("<F1>", lambda _e: self.do_shortcuts())
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

    def _current_filter_state(self) -> dict:
        """يلتقط حالة الفلاتر الحالية (البحث + قيم القوائم)."""
        return {"search": self.filter_search.get(),
                "vars": {k: v.get() for k, v in self.filter_vars.items()}}

    def _apply_filter_state(self, state: dict) -> None:
        """يطبّق حالة فلاتر محفوظة."""
        for key, val in (state.get("vars") or {}).items():
            if key in self.filter_vars:
                self.filter_vars[key].set(val)
        self.filter_search.set(state.get("search", ""))
        self.refresh()

    def do_filter_presets(self) -> None:
        """يفتح إدارة الفلاتر المحفوظة (حفظ الحالي/تطبيق/حذف)."""
        FilterPresetsDialog(self.root, self)

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
        from . import i18n
        self.columns = tuple(reversed(FIELDS + DIAG_FIELDS))
        self._col_labels = {f.key: i18n.field_label(f.key, f.label)
                            for f in self.columns}
        cols = [f.key for f in self.columns]
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="extended")

        for f in self.columns:
            # النقر على رأس العمود يرتّب حسبه (مع سهم اتجاه)
            self.tree.heading(f.key, text=self._col_labels[f.key],
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
        self.tree.tag_configure("due", background=DUE_BG)      # عليه متأخّرات
        self.tree.tag_configure("paid", background=PAID_BG)    # مكتمل السداد
        self.tree.tag_configure("cancelled", background="#ECE7E1",
                                foreground="#9A8F80")           # ملغى (باهت)
        self.tree.tag_configure("waitlist", background="#FBF0DC",
                                foreground="#7A5A12")           # قائمة انتظار
        self.tree.tag_configure("hover", background=HOVER_BG)
        self.tree.bind("<Double-1>", lambda _e: self.edit_selected())
        self._hover_iid = None
        self._hover_prev: tuple = ()
        self.tree.bind("<Motion>", self._on_row_hover)
        self.tree.bind("<Leave>", lambda _e: self._clear_hover())

        # قائمة يمين الفأرة على الصف
        self._row_menu = tk.Menu(self.tree, tearoff=0, font=(_FUI, 10))
        if self._can_edit():
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
        if self._can_edit():
            self._row_menu.add_command(label="💵  سجلّ دفعات الحاج",
                                       command=self.do_payments)
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
        self._row_menu.add_separator()
        self._row_menu.add_command(label="📦  حزمة مستندات الحاج (معاينة)",
                                   command=self.do_pilgrim_packet)
        self.tree.bind("<Button-3>", self._show_row_menu)

        # حالة فارغة أنيقة تظهر حين لا بيانات (تُخفى عند وجود سجلات)
        self._empty = ttk.Frame(wrap, style="Toolbar.TFrame", padding=20)
        self._empty_logo = logo_image(self.root, width=120)
        if self._empty_logo is not None:
            ttk.Label(self._empty, image=self._empty_logo,
                      background=BG).pack(pady=(0, 12))
        ttk.Label(self._empty, text="لا يوجد حجّاج بعد", background=BG,
                  font=(_FSB, 16), foreground=TEXT).pack()
        ttk.Label(self._empty, text="ابدأ بإضافة صور الجوازات أو استيراد ملف إكسل",
                  background=BG, font=(_FUI, 10), foreground=MUTED).pack(
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
        self._status_dot = tk.Label(bar, text="●", font=(_FUI, 11),
                                    fg="#8C857A", bg=BG)
        self._status_dot.pack(side=RIGHT, padx=(6, 0))
        self.status_label = ttk.Label(bar, textvariable=self.status,
                                      font=(_FUI, 10), foreground="#444")
        self.status_label.pack(side=RIGHT)
        self.count_label = ttk.Label(bar, text="", font=(_FSB, 11),
                                     foreground=TEXT)
        self.count_label.pack(side=LEFT)
        # إحصاء مالي دائم (المحصّل/المتبقّي) — يُحدَّث مع كل عملية
        self._fin_label = ttk.Label(bar, text="", font=(_FUI, 10),
                                    foreground=MUTED)
        self._fin_label.pack(side=LEFT, padx=12)
        ttk.Label(bar, text="💾 الحفظ تلقائي", font=(_FUI, 9),
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

        # تشفير فوري: إن كنّا في وضع الدخول والملف على القرص غير مشفّر
        # (كشف قديم أو مُرحّل)، نحفظه فوراً فيُشفَّر بدل انتظار أول تعديل.
        if self.session is not None and records and not self._file_is_encrypted():
            if self.save_data():
                # نحذف نسخة .bak غير المشفّرة (حالة ما قبل التحويل) لئلّا تبقى
                # بيانات صريحة على القرص؛ تُعاد مشفّرةً عند أول حفظ لاحق.
                try:
                    self.data_path.with_suffix(".bak").unlink()
                except OSError:
                    pass
                self._audit("تشفير الكشف", f"{len(records)} حاج")
                self.set_status(f"تم تشفير {len(records)} حاج وحفظهم", ok=True)

        if note:
            messagebox.showwarning("ملف البيانات", note)
            self.set_status("تم البدء بعد مشكلة في ملف البيانات", warn=True)
        elif records:
            self.set_status(f"تمت استعادة {len(records)} حاج من آخر جلسة")

    def _file_is_encrypted(self) -> bool:
        """هل ملف البيانات على القرص مشفّر فعلاً؟ (يبدأ بعلامة التشفير)."""
        try:
            from .storage import _ENCRYPTED_MAGIC
            with open(self.data_path, "rb") as fh:
                return fh.read(len(_ENCRYPTED_MAGIC)) == _ENCRYPTED_MAGIC
        except OSError:
            return True        # لا ملف بعد — لا داعي لإعادة الحفظ

    def _audit(self, action: str, details: str = "") -> None:
        """يسجّل عملية في سجلّ التدقيق (من فعل ماذا ومتى)."""
        from . import audit
        user = self.session.username if self.session is not None else "مفتوح"
        audit.record(action, details, user=user)

    def _push_undo(self, label: str) -> None:
        """يحفظ لقطة من السجلات قبل عملية مُتلِفة (تُستعاد بـ «تراجع»)."""
        import copy
        self._undo_stack.append((label, copy.deepcopy(self.records)))
        del self._undo_stack[:-20]        # نحتفظ بآخر 20 عملية فقط

    def undo(self) -> None:
        """يتراجع عن آخر عملية مُتلِفة (حذف/مسح/تعديل جماعي)."""
        if not self._require_edit():
            return
        if not self._undo_stack:
            self.set_status("لا يوجد ما يُتراجع عنه", warn=True)
            return
        label, snapshot = self._undo_stack.pop()
        self.records = snapshot
        self.refresh()
        self.save_data()
        self._audit("تراجع", label)
        self.set_status(f"تراجُع: {label} ({len(self.records)} سجلاً)", ok=True)
        self.toast(f"تراجُع عن: {label}", kind="success")

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
                     font=(_FSB, 10)).pack(ipady=9)
            win.update_idletasks()
            rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
            rw, rh = self.root.winfo_width(), self.root.winfo_height()
            ww, wh = win.winfo_width(), win.winfo_height()
            win.geometry(f"+{rx + rw - ww - 26}+{ry + rh - wh - 44}")
            win.after(ms, win.destroy)
        except Exception:
            pass

    def _row_tag(self, data: dict, shown: int) -> str:
        """وسم لون الصف: الحالة (ملغى/انتظار)، فتنبيه، فمتأخّر/مكتمل، وإلا متناوب."""
        status = str(data.get("status", "") or "").strip()
        if status == "ملغى":
            return "cancelled"
        if status == "قائمة انتظار":
            return "waitlist"
        if data.get("warnings"):
            return "warn"
        from .fields import parse_amount
        rem = parse_amount(data.get("remaining_amount"))
        prog = parse_amount(data.get("program_value"))
        if rem is not None and rem > 0.005:
            return "due"
        if prog and (rem is None or rem <= 0.005):
            return "paid"
        return "odd" if shown % 2 else "even"

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
            # الأولوية: تنبيه المراجعة، ثم الحالة المالية (متأخّر/مكتمل)، وإلا متناوب
            tag = self._row_tag(data, shown)
            self.tree.insert("", END, iid=str(orig_index[id(rec)]), values=values,
                             tags=(tag,))

        total = len(self.records)
        if self._filter_active() and shown != total:
            self.count_label.configure(text=f"المعروض: {shown} من {total}")
        else:
            self.count_label.configure(text=f"إجمالي الحجاج: {total}")

        # إحصاء مالي دائم في شريط الحالة
        if hasattr(self, "_fin_label"):
            from .fields import format_amount
            from .stats import financial_summary
            fin = financial_summary(self.records)
            self._fin_label.configure(
                text=(f"المحصّل {format_amount(fin.paid) or 0}  •  "
                      f"المتبقّي {format_amount(fin.remaining) or 0}"))

        # حالة فارغة: نُظهر اللوحة الترحيبية فوق الجدول حين لا سجلات
        if hasattr(self, "_empty"):
            if self.records:
                self._empty.place_forget()
            else:
                self._empty.place(relx=0.5, rely=0.42, anchor="center")

        self._update_heading_arrows()
        self._update_filter_button()
        self._update_chips()
        self._scroll_to_start()

    def _selected_indices(self) -> list[int]:
        return sorted(int(i) for i in self.tree.selection())

    # ------------------------------------------------------------ إضافة يدوية
    def add_manual(self) -> None:
        """يفتح سجلاً فارغاً لإدخال بيانات حاج يدوياً."""
        if not self._require_edit():
            return
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
        self._audit("إضافة يدوية", name)
        self.set_status(f"تمت إضافة: {name}", ok=True)
        self.toast(f"تمت إضافة: {name}", kind="success")

    # ------------------------------------------------------------- إضافة صور
    def add_images(self) -> None:
        if not self._require_edit():
            return
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
            self._audit("إضافة جوازات", f"{added} حاج (قراءة MRZ)")
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
        if not self._require_edit():
            return
        path = filedialog.askopenfilename(title="اختر ملف الإكسل", filetypes=EXCEL_TYPES)
        if not path:
            return
        try:
            records, notes = import_excel(path)
        except Exception as exc:
            _log.exception("فشل استيراد إكسل: %s", path)
            messagebox.showerror("خطأ في الاستيراد", f"تعذّر قراءة الملف:\n\n{exc}")
            return

        if not records:
            messagebox.showwarning("لا توجد بيانات", "\n\n".join(notes) or "الملف لا يحتوي بيانات.")
            return

        self.records.extend(records)
        self.refresh()
        self.save_data()
        self._audit("استيراد إكسل", f"{len(records)} سجل من {Path(path).name}")
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
            open_in_viewer(path)
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
            open_in_viewer(pdf_path)
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
            open_in_viewer(path)
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

    def do_occupancy(self) -> None:
        """يفتح عرض إشغال الغرف (المشغول مقابل السعة)."""
        if not self._require_records():
            return
        OccupancyDialog(self.root, self._visible_records())

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
                      programs=self._programs_by_name)

    def do_readiness(self) -> None:
        """يفتح قائمة تحقّق جاهزية الحجّاج (جواز/تأشيرة/تصريح/تطعيم/دفع)."""
        if not self._require_records():
            return
        ReadinessDialog(self.root, lambda: self.records, self._focus_record)

    def do_checkin(self) -> None:
        """يفتح تسجيل الحضور بمسح QR/الجواز لكل مرحلة (المطار/الفندق/الباص)."""
        if not self._require_edit():
            return
        if not self._require_records():
            return
        CheckInDialog(self.root, lambda: self.records, self.save_data,
                      on_export=self.do_attendance_report)

    def do_attendance_report(self) -> None:
        """يصدّر تقرير الحضور PDF (معاينة): مصفوفة كل حاج × كل مرحلة."""
        if not self._require_records():
            return
        records = self._visible_records()
        stages = list(CheckInDialog.STAGES)
        season = self.season_year.get()
        from .pdf_io import export_attendance_pdf
        self._preview_export(
            lambda p: export_attendance_pdf(records, p, stages=stages,
                                            season=season),
            f"تقرير الحضور {season}هـ", "pdf")

    _BULK_DOC_LABEL = {"receipt": "سند قبض", "invoice": "فاتورة ضريبية",
                       "einvoice": "فاتورة إلكترونية", "contract": "عقد"}

    def do_bulk_docs(self) -> None:
        """توليد جماعي لمستند (سند/فاتورة/عقد) لكل المعروضين في ملف واحد."""
        if not self._require_records():
            return
        records = self._visible_records()
        if not records:
            messagebox.showinfo("لا نتائج", "لا يوجد حاج مطابق للفلتر الحالي.")
            return
        dlg = BulkDocsDialog(self.root, len(records))
        self.root.wait_window(dlg)
        if dlg.kind is None:
            return

        import os
        import tempfile
        from .pdf_io import (export_contract_pdf, export_invoice_pdf,
                             export_receipt_pdf, merge_pdfs)
        company = self._company_info()
        season = self.season_year.get()
        tmpdir = tempfile.mkdtemp(prefix="hajj_docs_")
        out = os.path.join(tempfile.gettempdir(),
                           f"مستندات_{dlg.kind}_{date.today().isoformat()}.pdf")
        parts: list[str] = []
        try:
            for i, rec in enumerate(records):
                p = os.path.join(tmpdir, f"{i}.pdf")
                try:
                    if dlg.kind == "receipt":
                        export_receipt_pdf(
                            rec, p, season=season,
                            number=self._doc_number(rec, "receipts", "", 119))
                    elif dlg.kind == "contract":
                        export_contract_pdf(
                            rec, p, company=company, season=season,
                            number=self._doc_number(rec, "contracts", "CON-", 119))
                    else:
                        electronic = dlg.kind == "einvoice"
                        prefix = "EINV-" if electronic else "INV-"
                        export_invoice_pdf(
                            rec, p, company=company, season=season,
                            electronic=electronic,
                            number=self._doc_number(rec, "invoices", prefix, 119))
                    parts.append(p)
                except Exception:
                    continue
            if not parts:
                messagebox.showerror("تعذّر التوليد", "لم يُنشأ أيّ مستند.")
                return
            merge_pdfs(parts, out)
        finally:
            for p in parts:
                try:
                    os.remove(p)
                except OSError:
                    pass
            try:
                os.rmdir(tmpdir)
            except OSError:
                pass
        try:
            open_in_viewer(out)
        except OSError as exc:
            messagebox.showerror("تعذّر فتح المعاينة", str(exc))
            return
        self.set_status(
            f"تولّدت {len(parts)} {self._BULK_DOC_LABEL[dlg.kind]} في ملف واحد",
            ok=True)

    def do_dashboard(self) -> None:
        """يفتح لوحة التحكم الرئيسية (مؤشّرات سريعة قابلة للنقر)."""
        DashboardDialog(self.root, self)

    def ask_data(self) -> None:
        """يفتح مساعد «اسأل بياناتك» لأسئلة موسم الحج بالعربية (مكيّف للحج)."""
        from . import umrah_gui as ug
        ug.AskWindow(self.root, ug.HajjCtx(self))

    def open_collections(self) -> None:
        """يفتح متابعة تحصيل الحجّاج المتأخرين مباشرةً."""
        from . import umrah_gui as ug
        from .fields import parse_amount as _pa

        def rem(r):
            return (_pa(r.program_value) or 0) - (_pa(r.paid_amount) or 0)
        late = sorted((r for r in self.records if rem(r) > 0.5),
                      key=rem, reverse=True)
        if not late:
            messagebox.showinfo("متابعة التحصيل",
                                "لا متأخرات — الحمد لله، الجميع سدّد بالكامل.",
                                parent=self.root)
            return
        ug.DueFollowupWindow(self.root, ug.HajjCtx(self), late)

    def do_about(self) -> None:
        """يفتح نافذة «حول البرنامج»."""
        AboutDialog(self.root)

    def _show_welcome(self) -> None:
        """يفتح شاشة الترحيب (بأمان — يتجاهل الأخطاء إن أُغلقت النافذة)."""
        try:
            WelcomeDialog(self.root, self)
        except Exception:                              # noqa: BLE001
            pass

    def _show_onboarding(self) -> None:
        try:
            OnboardingWizard(self.root, self)
        except Exception:                              # noqa: BLE001
            pass

    def do_onboarding(self) -> None:
        """يعيد فتح معالج الإعداد (بيانات الشركة والموسم والبرامج)."""
        OnboardingWizard(self.root, self)

    def do_check_updates(self) -> None:
        """يتحقّق من وجود إصدار أحدث (إن ضُبط رابط في الإعدادات)، وإلا يُعلم يدوياً."""
        import hajj_app
        cur = hajj_app.__version__
        url = str(self._settings.get("update_url", "") or "").strip()
        if not url:
            messagebox.showinfo(
                "التحديثات",
                f"أنت على الإصدار {cur}.\n\nتُوزَّع التحديثات عبر المُثبِّت "
                "الجديد (HajjApp-Setup.exe).")
            return
        try:
            import urllib.request
            with urllib.request.urlopen(url, timeout=5) as resp:
                latest = resp.read().decode("utf-8").strip().split()[0]
        except Exception as exc:                       # noqa: BLE001
            messagebox.showwarning("التحديثات",
                                   f"تعذّر التحقق من التحديثات:\n{exc}")
            return
        self._audit("التحقق من التحديثات", latest)
        if latest and latest != cur:
            messagebox.showinfo(
                "تحديث متوفّر",
                f"يتوفّر إصدار أحدث: {latest}\n(أنت على {cur}).\n"
                "حمّل المُثبِّت الجديد لتحديث البرنامج.")
        else:
            messagebox.showinfo("محدَّث", f"أنت على أحدث إصدار ({cur}).")

    def do_command_palette(self) -> None:
        """يفتح البحث السريع / لوحة الأوامر (Ctrl+K)."""
        commands = [
            ("➕ إضافة حاج يدوياً", self.add_manual),
            ("📷 إضافة جوازات (صور/PDF)", self.add_images),
            ("📁 استيراد من إكسل", self.import_from_excel),
            ("📊 تصدير إكسل", self.do_export_excel),
            ("📄 تصدير PDF", self.do_export_pdf),
            ("🏠 لوحة التحكم", self.do_dashboard),
            ("📊 الإحصاءات والمالية", self.do_stats),
            ("📈 الرسوم البيانية", self.do_charts),
            ("💵 دفعات الحاج", self.do_payments),
            ("🧮 المصروفات والمحاسبة", self.do_expenses),
            ("🎫 تسجيل الحضور", self.do_checkin),
            ("📄 تقرير الحضور", self.do_attendance_report),
            ("✅ قائمة الجاهزية", self.do_readiness),
            ("🩺 فحص جاهزية الكشف", self.do_quality_check),
            ("🛏 إشغال الغرف", self.do_occupancy),
            ("🚌 كشف المواصلات", self.do_transport),
            ("🪪 بطاقات الحجّاج", self.do_badges),
            ("👥 المجموعات والمرشدون", self.do_groups),
            ("🌙 بدء موسم جديد", self.do_new_season),
            ("🛡 نسخة احتياطية الآن", self.do_backup_now),
            ("📝 سجلّ التدقيق", self.do_audit),
            ("⌨ الاختصارات", self.do_shortcuts),
            ("ℹ حول البرنامج", self.do_about),
        ]
        # جدول المناسك خاص بالحج — يُخفى من البحث السريع في وضع العمرة
        if not app_mode.is_umrah():
            commands.insert(-6, ("🗓 جدول المناسك", self.do_itinerary))
        CommandPalette(self.root, commands, list(self.records),
                       self._focus_record)

    def do_shortcuts(self) -> None:
        """يعرض اختصارات لوحة المفاتيح."""
        ShortcutsDialog(self.root)

    def do_audit(self) -> None:
        """يفتح سجلّ التدقيق (من فعل ماذا ومتى)."""
        AuditDialog(self.root)

    def do_stats(self) -> None:
        """يفتح لوحة الإحصاءات والملخّص المالي."""
        if not self._require_records():
            return
        StatsDialog(self.root, list(self.records), season=self.season_year.get())

    def do_stats_pdf(self) -> None:
        """يفتح معاينة تقرير الإحصاءات والملخّص المالي (PDF)."""
        if not self._require_records():
            return
        from .pdf_io import export_stats_pdf
        self._preview_export(
            lambda p: export_stats_pdf(list(self.records), p,
                                       season=self.season_year.get()),
            f"إحصاءات_ومالية_{date.today().isoformat()}", "pdf")

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
        if not self._require_edit():
            return
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
        self._audit("استعادة نسخة", f"{label} ({len(records)} سجل)")
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
        if not self._require_edit():
            return
        idxs = self._selected_indices()
        if len(idxs) < 2:
            messagebox.showinfo(
                "تعديل جماعي",
                "حدّد سجلين أو أكثر أولاً (استعمل Ctrl أو Shift للتحديد المتعدّد).")
            return

        def apply(changes: dict, program: str | None = None) -> None:
            self._push_undo(f"تعديل جماعي ({len(idxs)} سجل)")
            n = len(idxs)
            if changes:
                self._apply_bulk(idxs, changes)
            if program:
                self._apply_program_bulk(idxs, program)
            self.refresh()
            self.save_data()
            parts = []
            if changes:
                parts.append(f"{len(changes)} حقلاً")
            if program:
                parts.append(f"برنامج «{program}»")
            self._audit("تعديل جماعي", f"{n} سجل — {' + '.join(parts)}")
            self.set_status(f"عُدّل {n} سجلاً — {' + '.join(parts)}", ok=True)
            self.toast(f"عُدّل {n} سجلاً", kind="success")

        BulkEditDialog(self.root, len(idxs), apply)

    def _apply_bulk(self, indices: list[int], changes: dict) -> int:
        """يطبّق التغييرات على السجلات المحدّدة (قابل للاختبار). يعيد العدد."""
        for i in indices:
            rec = self.records[i]
            for key, value in changes.items():
                setattr(rec, key, value)
        return len(indices)

    def _apply_program_bulk(self, indices: list[int], program_name: str) -> int:
        """يطبّق برنامج الحملة على السجلات: تعبئة تلقائية + احتساب تكلفة كلٍّ.

        قابل للاختبار — يعيد عدد السجلات المطبّق عليها (0 إن كان البرنامج
        غير معرّف)."""
        from .fields import format_amount
        from .programs import (AUTOFILL_MAP, load_programs, program_by_name,
                               program_cost)

        prog = program_by_name(load_programs(self._settings), program_name)
        if prog is None:
            return 0
        for i in indices:
            rec = self.records[i]
            rec.program = program_name
            for pkey, rkey in AUTOFILL_MAP:
                val = str(getattr(prog, pkey, "")).strip()
                if val:
                    setattr(rec, rkey, val)
            total, _br = program_cost(
                prog, room_type=rec.room_type, wheelchair=rec.wheelchair,
                hady=rec.hady, executive_service=rec.executive_service,
                travel_class=rec.travel_class, transport=rec.transport)
            if total:
                rec.program_value = format_amount(total)
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

    def _whatsapp_cc(self) -> str:
        """رمز الدولة الافتراضي لأرقام واتساب (يبدأ الرقم بـ 0)."""
        return str(self._settings.get("whatsapp_cc", "971")).strip() or "971"

    def _save_whatsapp_cc(self, cc: str) -> None:
        self._settings["whatsapp_cc"] = str(cc).strip() or "971"
        try:
            save_settings(self._settings)
        except Exception:
            pass

    def do_whatsapp(self) -> None:
        """يفتح نافذة رسالة واتساب جماعية للحجّاج المحدّدين (عبر روابط wa.me)."""
        idxs = self._selected_indices()
        if not idxs:
            messagebox.showinfo("لم يتم التحديد",
                                "اختر حاجاً أو أكثر من الجدول أولاً.")
            return
        WhatsAppDialog(self.root, [self.records[i] for i in idxs], self)

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
        if not self._require_edit():
            return
        ProgramsDialog(self.root, self)

    def do_groups(self) -> None:
        """يفتح إدارة المجموعات والمرشدين (مرشد وهاتف لكل مجموعة)."""
        if not self._require_edit():
            return
        GroupsDialog(self.root, self)

    def do_itinerary(self) -> None:
        """يفتح جدول المناسك الزمني (قابل للتعديل والتصدير)."""
        if not self._require_edit():
            return
        ItineraryDialog(self.root, self)

    def do_travel_info(self) -> None:
        """يفتح «مواعيد وتعليمات السفر» لكل برنامج (تحرير + تصدير PDF)."""
        if not self._require_edit():
            return
        TravelInfoDialog(self.root, self)

    def do_new_season(self) -> None:
        """يبدأ موسماً جديداً: يؤرشف كشف الموسم الحالي (نسخة احتياطية) ثم
        يفرّغه، ويضبط السنة الهجرية، ثم يفتح إعداد برامج الموسم الجديد."""
        if not self._require_edit():
            return
        dialog = NewSeasonDialog(self.root, current_year=self.season_year.get(),
                                 pilgrim_count=len(self.records))
        self.root.wait_window(dialog)
        if not dialog.confirmed:
            return

        year = dialog.year
        archived = 0
        if self.records:                        # أرشفة قبل التفريغ
            try:
                from .storage import write_snapshot
                write_snapshot(self.records, self.session)
                archived = len(self.records)
            except Exception as exc:
                messagebox.showerror(
                    "تعذّرت الأرشفة",
                    f"لم يبدأ الموسم الجديد — فشلت أرشفة الكشف الحالي.\n\n{exc}")
                return

        self.records = []                       # موسم جديد بكشف فارغ
        self._undo_stack.clear()
        self.season_year.set(year)
        self._settings["season_year"] = year
        try:
            save_settings(self._settings)
        except OSError:
            pass
        self.refresh()
        self.save_data()
        self._audit("بدء موسم جديد", f"{year}هـ — أُرشف {archived} حاج")
        self.set_status(f"بدأ موسم {year}هـ — أُرشف {archived} حاج", ok=True)
        self.toast(f"بدأ موسم {year}هـ", kind="success")
        ProgramsDialog(self.root, self)         # اضبط برامج الموسم الجديد

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

    def do_payments(self) -> None:
        """يفتح سجلّ دفعات (أقساط) الحاج المحدّد."""
        if not self._require_edit():
            return
        rec = self._selected_record()
        if rec is None:
            return

        def _on_change():
            self.refresh()
            self.save_data()
            self._audit("تعديل دفعات",
                        rec.full_name_ar or rec.passport_number or "—")
            self.set_status("حُفظت دفعات الحاج", ok=True)

        PaymentsDialog(self.root, rec, _on_change)

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

    def do_pilgrim_packet(self) -> None:
        """حزمة مستندات حاج واحد: الجواز + البطاقة + سند القبض + العقد في ملف."""
        rec = self._selected_record()
        if rec is None:
            return

        import os
        import tempfile
        from . import images as imgmod
        from .pdf_io import (export_badges_pdf, export_contract_pdf,
                             export_passports_pdf, export_receipt_pdf, merge_pdfs)
        company = self._company_info()
        season = self.season_year.get()
        tmpdir = tempfile.mkdtemp(prefix="hajj_packet_")
        name = rec.full_name_ar or rec.full_name_en or "حاج"
        safe = re.sub(r'[\\/:*?"<>|]+', "-", name).strip() or "حاج"
        out = os.path.join(tempfile.gettempdir(), f"حزمة - {safe}.pdf")
        parts: list[str] = []
        imgfiles: list[str] = []
        try:
            # ١) صورة الجواز إن وُجدت
            try:
                if imgmod.has_image(rec.image_id, imgmod.PASSPORT):
                    data = imgmod.load_image(rec.image_id, imgmod.PASSPORT,
                                             self.session)
                    if data:
                        entries = []
                        for k, pb in enumerate(imgmod.render_pages_png(data), 1):
                            ip = os.path.join(tmpdir, f"pp{k}.img")
                            with open(ip, "wb") as fh:
                                fh.write(pb)
                            imgfiles.append(ip)
                            entries.append((name, ip))
                        pp = os.path.join(tmpdir, "passport.pdf")
                        export_passports_pdf(entries, pp, title="الجواز")
                        parts.append(pp)
            except Exception:
                pass
            # ٢) البطاقة
            try:
                bp = os.path.join(tmpdir, "badge.pdf")
                export_badges_pdf([rec], bp, company=company["name_ar"],
                                  session=self.session)
                parts.append(bp)
            except Exception:
                pass
            # ٣) سند القبض  ٤) العقد
            rp = os.path.join(tmpdir, "receipt.pdf")
            export_receipt_pdf(rec, rp, season=season,
                               number=self._doc_number(rec, "receipts", "", 119))
            parts.append(rp)
            cp = os.path.join(tmpdir, "contract.pdf")
            export_contract_pdf(rec, cp, company=company, season=season,
                                number=self._doc_number(rec, "contracts", "CON-", 119))
            parts.append(cp)
            merge_pdfs(parts, out)
        except Exception as exc:
            messagebox.showerror("تعذّرت الحزمة", str(exc))
            return
        finally:
            for p in imgfiles + parts:
                try:
                    os.remove(p)
                except OSError:
                    pass
            try:
                os.rmdir(tmpdir)
            except OSError:
                pass
        try:
            open_in_viewer(out)
        except OSError as exc:
            messagebox.showerror("تعذّر فتح المعاينة", str(exc))
            return
        self.set_status(f"فُتحت حزمة مستندات: {name}", ok=True)

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

    def _preview_export(self, export_fn, base_name: str, ext: str) -> None:
        """يفتح معاينة الملف في العارض (تطبع أو تحفظ منه)، ويحدّث الحالة."""
        if open_preview(self.root, export_fn, base_name, ext):
            self.set_status("فُتحت المعاينة — اطبع أو احفظ نسخةً من العارض",
                            ok=True)

    def do_expenses(self) -> None:
        """يفتح مصروفات الحملة ومحاسبتها (المحصّل − المصروفات = الصافي)."""
        if not self._require_edit():
            return
        ExpensesDialog(self.root, self)

    def do_charts(self) -> None:
        """يفتح الرسوم البيانية (توزيعات ومالية)."""
        if not self._require_records():
            return
        ChartsDialog(self.root, self._visible_records())

    def do_arrears_report(self) -> None:
        """كشف المتأخّرات المالية: الحجّاج الذين عليهم مبالغ متبقّية (معاينة)."""
        if not self._require_records():
            return
        from .stats import outstanding
        owe = [rec for rec, rem in outstanding(self._visible_records()) if rem > 0]
        if not owe:
            messagebox.showinfo("لا متأخّرات",
                                "لا يوجد حجّاج عليهم مبالغ متبقّية 👍")
            return
        self._preview_export(
            lambda p: export_excel(owe, p),
            f"كشف المتأخّرات المالية {self.season_year.get()}هـ", "xlsx")

    def do_export_excel(self) -> None:
        if not self._require_records():
            return
        self._preview_export(lambda p: export_excel(self._ordered(), p),
                             self._default_name("xlsx").rsplit(".", 1)[0], "xlsx")

    def do_export_pdf(self) -> None:
        if not self._require_records():
            return
        cards = messagebox.askyesno(
            "بطاقات تفصيلية",
            "هل تريد إضافة صفحة بطاقة مفصّلة لكل حاج بعد الجدول؟",
        )
        self._preview_export(
            lambda p: export_pdf(self._ordered(), p,
                                 title=self._report_title("كشف الحجاج"),
                                 with_cards=cards),
            self._default_name("pdf").rsplit(".", 1)[0], "pdf")

    def _rooming_scope(self):
        """يفتح نافذة اختيار الفندق ونوع الغرفة، ويعيد السجلات المطابقة أو None."""
        if not self._require_records():
            return None
        dlg = RoomingScopeDialog(self.root, self.records)
        self.root.wait_window(dlg)
        if dlg.result is None:
            return None
        from .rooming import room_category
        hotel, cat = dlg.result
        recs = list(self.records)
        if hotel is not None:
            recs = [r for r in recs if str(r.hotel or "").strip() == hotel]
        if cat is not None:
            recs = [r for r in recs if room_category(r.room_type) == cat]
        if not recs:
            messagebox.showinfo(
                "لا نتائج", "لا يوجد حاج ضمن الفندق/نوع الغرفة المختار.")
            return None
        self._rooming_label = " — ".join(
            p for p in (hotel, (cat + "ة" if cat else None)) if p)
        return recs

    def _confirm_rooming(self, records):
        """يفحص وجود غرف ويعرض ملخّصاً. يعيد عدد الغرف أو None عند الإلغاء."""
        from .rooming import group_records_by_room
        rooms, unplaced = group_records_by_room(records)
        if not rooms:
            messagebox.showinfo(
                "لا يمكن بناء كشف التسكين",
                "لا يوجد حاج له نوع غرفة أو رقم غرفة ضمن الاختيار.\n"
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

    def _rooming_title(self) -> str:
        base = self._report_title("كشف التسكين")
        scope = getattr(self, "_rooming_label", "")
        return f"{base} — {scope}" if scope else base

    def do_rooming_pdf(self) -> None:
        """يفتح معاينة كشف التسكين (PDF) — بعد اختيار الفندق ونوع الغرفة."""
        records = self._rooming_scope()
        if records is None:
            return
        if self._confirm_rooming(records) is None:
            return
        self._preview_export(
            lambda p: export_pdf(records, p, title=self._rooming_title(),
                                 group_by_room=True),
            "كشف_التسكين", "pdf")

    def do_rooming_excel(self) -> None:
        """يفتح معاينة كشف التسكين (إكسل) — بعد اختيار الفندق ونوع الغرفة."""
        records = self._rooming_scope()
        if records is None:
            return
        if self._confirm_rooming(records) is None:
            return
        from .excel_io import export_grouped_excel
        self._preview_export(
            lambda p: export_grouped_excel(records, p, title=self._rooming_title()),
            "كشف_التسكين", "xlsx")

    def _require_records(self) -> bool:
        if not self.records:
            messagebox.showinfo("لا توجد بيانات", "أضف صور جوازات أو استورد ملف إكسل أولاً.")
            return False
        return True

    # ------------------------------------------------------------ تحرير/حذف
    def edit_selected(self) -> None:
        if not self._require_edit():
            return
        idx = self._selected_indices()
        if not idx:
            messagebox.showinfo("لم يتم التحديد", "اختر سجلاً من الجدول أولاً.")
            return
        EditDialog(self.root, self.records[idx[0]], on_save=self._after_edit,
                   session=self.session)

    def _after_edit(self, rec: PassportData) -> None:
        self.refresh()
        self.save_data()
        self._audit("تعديل سجل",
                    rec.full_name_ar or rec.full_name_en or rec.passport_number or "—")
        self.set_status("تم حفظ التعديلات")

    def delete_selected(self) -> None:
        if not self._require_edit():
            return
        idx = self._selected_indices()
        if not idx:
            messagebox.showinfo("لم يتم التحديد", "اختر سجلاً أو أكثر للحذف.")
            return
        if not messagebox.askyesno("تأكيد الحذف", f"حذف {len(idx)} سجل؟"):
            return
        self._push_undo(f"حذف {len(idx)} سجل")
        from . import images as imgmod
        for i in reversed(idx):
            imgmod.delete_all(self.records[i].image_id)   # حذف صور الحاج المشفّرة
            del self.records[i]
        self.refresh()
        self.save_data()
        self._audit("حذف سجلات", f"{len(idx)} سجل")
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
                  font=(_FSB, 13), foreground=DANGER).pack(anchor="e")
        ttk.Label(frame, background=BG, foreground=TEXT, justify="right",
                  font=(_FUI, 10), wraplength=340,
                  text=(f"سيُحذف {len(self.records)} سجلاً وكل صورهم نهائياً "
                        "(تبقى نسخة احتياطية .bak).")).pack(anchor="e", pady=(8, 10))

        if use_password:
            prompt = f"للتأكيد، أدخل كلمة مرور حسابك «{self.session.username}»:"
        else:
            prompt = f"للتأكيد، اكتب كلمة «{self._CLEAR_CONFIRM_WORD}» في الحقل:"
        ttk.Label(frame, text=prompt, background=BG, foreground=TEXT,
                  font=(_FUI, 10), wraplength=340, justify="right").pack(anchor="e")

        var = StringVar()
        entry = ttk.Entry(frame, textvariable=var, width=30, justify="center",
                          show="●" if use_password else "")
        install_entry_editing(entry)
        entry.pack(anchor="e", pady=(6, 0))
        entry.focus_set()
        err = ttk.Label(frame, text="", background=BG, foreground=DANGER,
                        font=(_FUI, 9))
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
        if not self._require_edit():
            return
        if not self.records:
            return
        if not self._confirm_destructive():
            self.set_status("أُلغي المسح")
            return
        count = len(self.records)
        self._push_undo(f"مسح الكل ({count} سجل)")
        from . import images as imgmod
        for rec in self.records:
            imgmod.delete_all(rec.image_id)          # حذف كل الصور المشفّرة
        self.records.clear()
        self.refresh()
        self.save_data()
        self._audit("مسح الكل", f"{count} سجل")
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
        self._count_label = ttk.Label(top, font=(_FSB, 11),
                                      foreground=TEXT)
        self._count_label.pack(side=LEFT)
        self._flight_var = StringVar(value=self._ALL_FLIGHTS)
        box = ttk.Combobox(top, textvariable=self._flight_var, state="readonly",
                           width=24, font=(_FUI, 10),
                           values=self._flight_combo_values())
        box.pack(side=RIGHT)
        box.bind("<<ComboboxSelected>>", lambda _e: self._rebuild())
        ttk.Label(top, text="الطيران:", font=(_FUI, 10),
                  foreground=TEXT).pack(side=RIGHT, padx=(2, 5))

        ttk.Label(outer, foreground=MUTED, font=(_FUI, 9), justify="right",
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
                  font=(_FSB, 10), foreground=TEXT).pack(anchor="e")

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

    def _run(self, export_fn, ext: str) -> None:
        if open_preview(self, lambda p: export_fn(self._current(), p),
                        self._default, ext):
            self.set_title_status("فُتحت المعاينة")

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
            ttk.Label(cell, text=label, font=(_FUI, 10),
                      foreground=TEXT).pack(anchor="e")
            if combo is not None:
                w = ttk.Combobox(cell, textvariable=var, state="readonly",
                                 width=width, values=combo, font=(_FUI, 10))
                if on_change:
                    w.bind("<<ComboboxSelected>>", lambda _e: on_change())
            else:
                w = ttk.Entry(cell, textvariable=var, width=width,
                              justify="center", font=(_FUI, 10))
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
        ttk.Label(camp_row, text="اسم الحملة:", font=(_FUI, 10),
                  foreground=TEXT).pack(side=RIGHT, padx=(4, 5))
        camp_entry = ttk.Entry(camp_row, textvariable=self._campaign_var, width=32,
                               justify="right", font=(_FUI, 10))
        install_entry_editing(camp_entry)
        camp_entry.pack(side=RIGHT)

        self._summary = ttk.Label(outer, font=(_FSB, 11),
                                  foreground=TEXT)
        self._summary.pack(anchor="e", pady=(10, 2))
        ttk.Label(outer, foreground=MUTED, font=(_FUI, 9), justify="right",
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

        number = str(self._number_var.get()).strip() or "1"
        cls = self._class_var.get()
        sector = self._sector_var.get().strip()
        base = f"خيمة {number} - {cls}" + (f" - قطاع {sector}" if sector else "")

        plan = make_tent(
            self._records, self._preview, camp=self._camp_var.get(),
            sector=sector, number=number, classification_label=cls,
            capacity=self._count_var.get())
        path = open_preview(
            self, lambda p: export_tents_pdf(plan, p,
                                             campaign=self._campaign_var.get()),
            base, "pdf")
        if path is None:
            return

        # تثبيت ركّاب هذه الخيمة والانتقال للتالية
        self._assigned.update(self._preview)
        if str(number).isdigit():
            self._number_var.set(str(int(number) + 1))
        self._refresh_preview()


class BulkEditDialog(Toplevel):
    """تعديل جماعي: يضبط حقولاً مختارة لكل السجلات المحدّدة دفعةً واحدة."""

    _FIELDS = (
        ("group", "المجموعة"),
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
                  font=(_FSB, 12), foreground=TEXT,
                  background=BG).pack(anchor="e")
        ttk.Label(outer, foreground=MUTED, font=(_FUI, 9), justify="right",
                  background=BG,
                  text=rtl("علّم «طبّق» بجانب الحقل واكتب قيمته — تُطبَّق على "
                           "الجميع. الحقول غير المعلّمة تبقى كما هي.")).pack(
            anchor="e", pady=(2, 10))

        # تطبيق برنامج الحملة على الجميع (تعبئة تلقائية + احتساب تكلفة كلٍّ)
        from .programs import PROGRAM_NAMES
        prog_row = ttk.Frame(outer)
        prog_row.pack(fill=X, pady=(0, 8))
        self._prog_apply = tk.BooleanVar(value=False)
        ttk.Checkbutton(prog_row, variable=self._prog_apply,
                        text=rtl("طبّق برنامج الحملة (تعبئة + احتساب التكلفة "
                                 "لكل حاج)")).pack(side=RIGHT, padx=(8, 0))
        self._prog_var = StringVar()
        prog_cb = ttk.Combobox(prog_row, textvariable=self._prog_var,
                               state="readonly", width=14, justify="center",
                               values=[""] + list(PROGRAM_NAMES))
        prog_cb.pack(side=RIGHT)
        prog_cb.bind("<<ComboboxSelected>>",
                     lambda _e: self._prog_apply.set(True))
        ttk.Separator(outer, orient="horizontal").pack(fill=X, pady=(0, 10))

        grid = ttk.Frame(outer)
        grid.pack(fill=X)
        self._vars: dict[str, tuple[tk.BooleanVar, StringVar]] = {}
        for row, (key, label) in enumerate(self._FIELDS):
            apply_var = tk.BooleanVar(value=False)
            val_var = StringVar()
            chk = ttk.Checkbutton(grid, text=label, variable=apply_var)
            chk.grid(row=row, column=1, sticky="e", padx=(8, 0), pady=2)
            entry = ttk.Entry(grid, textvariable=val_var, width=26, justify="right",
                              font=(_FUI, 10))
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
        program = self._prog_var.get().strip() if self._prog_apply.get() else None
        if not changes and not program:
            messagebox.showinfo(
                "لا تغييرات",
                "علّم «طبّق» بجانب حقل، أو اختر برنامج الحملة.", parent=self)
            return
        self._on_apply(changes, program)
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
        self._count = ttk.Label(top, font=(_FSB, 11), foreground=TEXT)
        self._count.pack(side=LEFT)
        self._var = StringVar(value=self._ALL)
        box = ttk.Combobox(top, textvariable=self._var, state="readonly", width=24,
                           font=(_FUI, 10),
                           values=[self._ALL, *distinct_transports(records)])
        box.pack(side=RIGHT)
        box.bind("<<ComboboxSelected>>", lambda _e: self._rebuild())
        ttk.Label(top, text="الوسيلة:", font=(_FUI, 10),
                  foreground=TEXT).pack(side=RIGHT, padx=(2, 5))

        cols = ("family", "phone", "hotel", "executive", "wheelchair")
        self._tree = ttk.Treeview(outer, columns=cols, show="tree headings", height=13)
        self._tree.heading("#0", text="الباص / الحاج")
        for c, lbl, w in (("family", "رقم العائلة", 90), ("phone", "الهاتف", 120),
                          ("hotel", "الفندق", 150),
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
                                  values=(str(rec.family_number or "").strip() or "—",
                                          str(rec.phone or "").strip() or "—",
                                          str(rec.hotel or "").strip() or "—",
                                          executive_display(rec) or "—",
                                          str(rec.wheelchair or "").strip() or "—"))
        self._count.config(text=f"عدد الحجّاج: {len(records)}")

    def _run(self, export_fn, ext):
        records = self._current()
        if not records:
            messagebox.showinfo("لا نتائج", "لا يوجد حجّاج.", parent=self)
            return
        open_preview(self, lambda p: export_fn(records, p),
                     f"كشف_المواصلات_{date.today().isoformat()}", ext)

    def _excel(self):
        from .transport import export_transport_excel
        self._run(export_transport_excel, "xlsx")

    def _pdf(self):
        from .pdf_io import export_transport_pdf
        self._run(export_transport_pdf, "pdf")


class AuditDialog(Toplevel):
    """سجلّ التدقيق: يعرض العمليات (الأحدث أولاً) — من فعل ماذا ومتى."""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.title("📝 سجلّ التدقيق")
        self.configure(bg=BG)
        self.transient(parent)
        self.geometry("760x520")

        outer = ttk.Frame(self, padding=14)
        outer.pack(fill=BOTH, expand=True)
        ttk.Label(outer, text="سجلّ العمليات (الأحدث أولاً)",
                  font=(_FSB, 12), foreground=TEXT,
                  background=BG).pack(anchor="e", pady=(0, 8))

        box = ttk.Frame(outer)
        box.pack(fill=BOTH, expand=True)
        sb = ttk.Scrollbar(box, orient="vertical")
        sb.pack(side=RIGHT, fill=Y)
        self.tree = ttk.Treeview(box, columns=("user", "action", "details"),
                                 show="tree headings", height=16,
                                 yscrollcommand=sb.set)
        self.tree.heading("#0", text="التاريخ والوقت")
        self.tree.heading("user", text="المستخدم")
        self.tree.heading("action", text="العملية")
        self.tree.heading("details", text="التفاصيل")
        self.tree.column("#0", width=155, anchor="center", stretch=False)
        self.tree.column("user", width=90, anchor="center", stretch=False)
        self.tree.column("action", width=130, anchor="e", stretch=False)
        self.tree.column("details", width=310, anchor="e", stretch=True)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        sb.config(command=self.tree.yview)

        row = ttk.Frame(outer)
        row.pack(anchor="e", pady=(10, 0))
        ttk.Button(row, text=rtl("↻  تحديث"), style="Ghost.TButton",
                   command=self.refresh).pack(side=RIGHT, padx=3)
        ttk.Button(row, text=rtl("🗑  مسح السجلّ"), style="Ghost.TButton",
                   command=self._clear).pack(side=RIGHT, padx=3)
        ttk.Button(row, text="إغلاق", style="Ghost.TButton",
                   command=self.destroy).pack(side=RIGHT, padx=3)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.refresh()

    def refresh(self) -> None:
        from . import audit
        self.tree.delete(*self.tree.get_children())
        for e in audit.read_entries(1000):
            ts = str(e.get("ts", "")).replace("T", "  ")
            self.tree.insert("", END, text=ts,
                             values=(e.get("user", "—"), e.get("action", ""),
                                     e.get("details", "")))

    def _clear(self) -> None:
        if messagebox.askyesno("مسح السجلّ",
                               "مسح كل قيود سجلّ التدقيق نهائياً؟", parent=self):
            from . import audit
            audit.clear_log()
            self.refresh()


class CommandPalette(Toplevel):
    """بحث سريع / لوحة أوامر (Ctrl+K): اكتب لتصفية الأوامر والحجّاج ثم Enter."""

    def __init__(self, parent, commands, records, on_pilgrim) -> None:
        super().__init__(parent)
        self.on_pilgrim = on_pilgrim
        self.overrideredirect(True)
        self.configure(bg=BRONZE)
        frame = tk.Frame(self, bg=BG, padx=2, pady=2)
        frame.pack()
        inner = tk.Frame(frame, bg=BG, padx=10, pady=10)
        inner.pack()

        self._q = StringVar()
        entry = ttk.Entry(inner, textvariable=self._q, width=46,
                          justify="right", font=(_FSB, 13))
        entry.pack(fill=X)
        entry.focus_set()
        self.listbox = tk.Listbox(inner, height=10, width=46, font=(_FUI, 11),
                                  activestyle="dotbox", bg=PANEL, fg=TEXT,
                                  selectbackground=BRONZE, selectforeground="white",
                                  highlightthickness=0, bd=0)
        self.listbox.pack(fill=BOTH, expand=True, pady=(8, 0))

        # (النوع، النصّ المعروض، الحمولة)
        self._all = [("cmd", label, cb) for label, cb in commands]
        for i, rec in enumerate(records):
            name = rec.full_name_ar or rec.full_name_en or rec.passport_number or "—"
            self._all.append(("pil", f"👤 {name}  ·  {rec.passport_number or ''}", i))
        self._shown: list = []

        self._q.trace_add("write", lambda *_a: self._filter())
        entry.bind("<Down>", lambda _e: self._move(1))
        entry.bind("<Up>", lambda _e: self._move(-1))
        entry.bind("<Return>", lambda _e: self._run())
        self.listbox.bind("<Return>", lambda _e: self._run())
        self.listbox.bind("<Double-1>", lambda _e: self._run())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<FocusOut>", lambda _e: self.after(120, self._maybe_close))

        self._filter()
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = self.winfo_screenheight() // 5
        self.geometry(f"+{x}+{y}")

    def _maybe_close(self) -> None:
        try:
            if self.focus_get() is None:
                self.destroy()
        except Exception:
            pass

    def _filter(self) -> None:
        q = self._q.get().strip().lower()
        self.listbox.delete(0, "end")
        self._shown = []
        for kind, label, payload in self._all:
            if not q or q in label.lower():
                self._shown.append((kind, label, payload))
                self.listbox.insert("end", label)
                if len(self._shown) >= 40:
                    break
        if self._shown:
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(0)

    def _move(self, delta: int) -> None:
        if not self._shown:
            return
        cur = self.listbox.curselection()
        i = (cur[0] if cur else 0) + delta
        i = max(0, min(len(self._shown) - 1, i))
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(i)
        self.listbox.see(i)

    def _run(self) -> None:
        cur = self.listbox.curselection()
        if not cur or cur[0] >= len(self._shown):
            return
        kind, _label, payload = self._shown[cur[0]]
        self.destroy()
        if kind == "cmd":
            payload()
        else:
            self.on_pilgrim(payload)


class OnboardingWizard(Toplevel):
    """معالج أول تشغيل: بيانات الشركة، الموسم، ثم إعداد البرامج — بخطوات."""

    _COMPANY_FIELDS = (
        ("name_ar", "اسم الشركة (عربي)"),
        ("name_en", "اسم الشركة (إنجليزي)"),
        ("trn", "الرقم الضريبي (TRN)"),
        ("phone", "الهاتف"),
        ("address", "العنوان"),
    )
    STEPS = 4

    def __init__(self, parent, app) -> None:
        super().__init__(parent)
        self.app = app
        self.title("إعداد أول تشغيل")
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        self._step = 0

        co = app._company_info()
        self._v = {k: StringVar(value=str(co.get(k, "")))
                   for k, _ in self._COMPANY_FIELDS}
        self._season = StringVar(value=app.season_year.get())
        self._open_programs = tk.BooleanVar(value=True)

        body = ttk.Frame(self, padding=24)
        body.pack(fill=BOTH, expand=True)
        self._dots = ttk.Label(body, font=(_FUI, 11), foreground=BRONZE,
                               background=BG)
        self._dots.pack(anchor="e")
        self._content = ttk.Frame(body)
        self._content.pack(fill=BOTH, expand=True, pady=(8, 0))

        nav = ttk.Frame(body)
        nav.pack(fill=X, pady=(16, 0))
        self._next_btn = ttk.Button(nav, text="التالي", style="Primary.TButton",
                                    command=self._next)
        self._next_btn.pack(side=RIGHT, padx=3)
        self._back_btn = ttk.Button(nav, text="السابق", style="Ghost.TButton",
                                    command=self._back)
        self._back_btn.pack(side=RIGHT, padx=3)
        ttk.Button(nav, text="تخطّي", style="Ghost.TButton",
                   command=self._skip).pack(side=LEFT)

        self.bind("<Escape>", lambda _e: self._skip())
        self._render()
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 4
        self.geometry(f"+{x}+{y}")

    def _render(self) -> None:
        for w in self._content.winfo_children():
            w.destroy()
        self._dots.configure(text="●  " * (self._step + 1)
                             + "○  " * (self.STEPS - self._step - 1)
                             + f"   ({self._step + 1}/{self.STEPS})")
        [self._welcome, self._company, self._season_step, self._finish_step][
            self._step]()
        self._back_btn.state(["!disabled"] if self._step > 0 else ["disabled"])
        self._next_btn.configure(
            text="إنهاء" if self._step == self.STEPS - 1 else "التالي")

    def _welcome(self) -> None:
        c = self._content
        logo = logo_image(self, width=150)
        if logo is not None:
            lbl = ttk.Label(c, image=logo, background=BG)
            lbl.image = logo
            lbl.pack(pady=(0, 10))
        ttk.Label(c, text=rtl("مرحباً بك في برنامج موسم الحج"), font=(_FSB, 15),
                  foreground=TEXT, background=BG).pack()
        ttk.Label(c, justify="center", wraplength=380, font=(_FUI, 10),
                  foreground=MUTED, background=BG, text=rtl(
                      "سنضبط معاً بيانات الشركة والموسم في خطوات سريعة.\n"
                      "يمكنك تغييرها لاحقاً في أي وقت.")).pack(pady=(8, 0))

    def _company(self) -> None:
        c = self._content
        ttk.Label(c, text=rtl("بيانات الشركة (تظهر في الفواتير والعقود):"),
                  font=(_FSB, 11), foreground=TEXT, background=BG).pack(anchor="e")
        grid = ttk.Frame(c)
        grid.pack(fill=X, pady=(8, 0))
        for i, (key, label) in enumerate(self._COMPANY_FIELDS):
            ttk.Label(grid, text=label, font=(_FUI, 10), background=BG,
                      foreground=TEXT).grid(row=i, column=1, sticky="e",
                                            padx=(12, 6), pady=5)
            ttk.Entry(grid, textvariable=self._v[key], width=32,
                      justify="right").grid(row=i, column=0, pady=5)

    def _season_step(self) -> None:
        c = self._content
        ttk.Label(c, text=rtl("موسم الحج (السنة الهجرية):"), font=(_FSB, 11),
                  foreground=TEXT, background=BG).pack(anchor="e")
        ttk.Combobox(c, textvariable=self._season, values=HIJRI_YEARS,
                     state="readonly", width=10, font=(_FSB, 13),
                     justify="center").pack(anchor="e", pady=(8, 6))
        ttk.Label(c, justify="right", font=(_FUI, 9), foreground=MUTED,
                  background=BG, text=rtl(
                      "تظهر السنة في عناوين الكشوف والتقارير.\n"
                      "عملة البرنامج: الدرهم الإماراتي (AED).")).pack(anchor="e")

    def _finish_step(self) -> None:
        c = self._content
        ttk.Label(c, text=rtl("تمّ الإعداد ✓"), font=(_FSB, 15),
                  foreground=SUCCESS_FG, background=BG).pack(anchor="e")
        ttk.Label(c, justify="right", wraplength=380, font=(_FUI, 10),
                  foreground=MUTED, background=BG, text=rtl(
                      f"الشركة: {self._v['name_ar'].get() or '—'}\n"
                      f"الموسم: {self._season.get()}هـ")).pack(anchor="e",
                                                               pady=(8, 10))
        ttk.Checkbutton(c, variable=self._open_programs, text=rtl(
            "افتح إعداد برامج الحملة الآن (الرحلات والتكاليف والخدمات)")
        ).pack(anchor="e")

    def _back(self) -> None:
        if self._step > 0:
            self._step -= 1
            self._render()

    def _next(self) -> None:
        if self._step < self.STEPS - 1:
            self._step += 1
            self._render()
        else:
            self._finish()

    def _mark_done(self) -> None:
        self.app._ui["onboarded"] = True
        self.app._settings["ui"] = self.app._ui
        try:
            save_settings(self.app._settings)
        except OSError:
            pass

    def _skip(self) -> None:
        self._mark_done()
        self.destroy()

    def _finish(self) -> None:
        self.app._save_company({k: v.get().strip() for k, v in self._v.items()})
        year = self._season.get()
        self.app.season_year.set(year)
        self.app._settings["season_year"] = year
        self._mark_done()
        self.app._audit("إكمال معالج الإعداد", year)
        self.app.set_status("تم إعداد البرنامج", ok=True)
        open_progs = self._open_programs.get()
        self.destroy()
        if open_progs and self.app.session is not None:
            self.app.do_programs()


class WelcomeDialog(Toplevel):
    """شاشة ترحيب: تحية + مؤشّرات سريعة + إجراءات + آخر النشاطات."""

    def __init__(self, parent, app) -> None:
        super().__init__(parent)
        self.app = app
        self.title("مرحباً")
        self.configure(bg=BG)
        self.transient(parent)
        self.resizable(False, False)
        outer = ttk.Frame(self, padding=22)
        outer.pack(fill=BOTH, expand=True)

        user = app.session.username if app.session is not None else "ضيف"
        year = app.season_year.get()
        ttk.Label(outer, text=rtl(f"حيّاك الله، {user} 👋"), font=(_FSB, 17),
                  foreground=TEXT, background=BG).pack(anchor="e")
        ttk.Label(outer, text=rtl(f"موسم الحج {year}هـ"), font=(_FUI, 11),
                  foreground=BRONZE, background=BG).pack(anchor="e", pady=(2, 14))

        # مؤشّرات سريعة
        from .fields import format_amount
        from .stats import financial_summary
        recs = app.records
        fin = financial_summary(recs)
        try:
            from .quality import readiness_percent
            ready = (round(sum(readiness_percent(r) for r in recs) / len(recs))
                     if recs else 0)
        except Exception:                              # noqa: BLE001
            ready = 0
        kpis = [("عدد الحجّاج", f"{len(recs):,}"),
                ("نسبة الجاهزية", f"{ready}%"),
                ("المتبقّي المالي", format_amount(fin.remaining) or "0")]
        krow = ttk.Frame(outer)
        krow.pack(fill=X, pady=(0, 14))
        for label, val in kpis:
            card = tk.Frame(krow, bg=PANEL, highlightbackground=BORDER,
                            highlightthickness=1, padx=16, pady=10)
            card.pack(side=RIGHT, padx=5)
            tk.Label(card, text=val, bg=PANEL, fg=TEXT,
                     font=(_FSB, 16)).pack()
            tk.Label(card, text=label, bg=PANEL, fg=MUTED,
                     font=(_FUI, 9)).pack()

        # إجراءات سريعة
        ttk.Label(outer, text=rtl("إجراءات سريعة:"), font=(_FSB, 10),
                  foreground=TEXT, background=BG).pack(anchor="e")
        arow = ttk.Frame(outer)
        arow.pack(fill=X, pady=(6, 14))
        actions = [("➕ إضافة حاج", app.add_manual),
                   ("📷 قراءة جواز", app.add_images),
                   ("🎫 تسجيل الحضور", app.do_checkin),
                   ("🏠 لوحة التحكم", app.do_dashboard)]
        for label, cb in actions:
            ttk.Button(arow, text=rtl(label), style="Act.TButton",
                       command=lambda c=cb: (self.destroy(), c())).pack(
                side=RIGHT, padx=4)

        # آخر النشاطات
        try:
            from . import audit
            entries = audit.read_entries(limit=6)
        except Exception:                              # noqa: BLE001
            entries = []
        if entries:
            ttk.Label(outer, text=rtl("آخر النشاطات:"), font=(_FSB, 10),
                      foreground=TEXT, background=BG).pack(anchor="e")
            box = tk.Text(outer, height=5, width=52, bg=PANEL, fg=MUTED,
                          font=(_FUI, 9), relief="flat", wrap="word")
            for e in entries:
                ts = str(e.get("ts", "")).replace("T", " ")
                box.insert("end", f"• {ts}  —  {e.get('user','')}: "
                                  f"{e.get('action','')} {e.get('details','')}\n")
            box.configure(state="disabled")
            box.pack(fill=X, pady=(4, 10))

        foot = ttk.Frame(outer)
        foot.pack(fill=X, pady=(6, 0))
        self._hide = tk.BooleanVar(value=not app._ui.get("show_welcome", True))
        ttk.Checkbutton(foot, variable=self._hide, command=self._toggle_hide,
                        text=rtl("لا تُظهر هذه الشاشة عند البدء")).pack(side=RIGHT)
        ttk.Button(foot, text="ابدأ", style="Primary.TButton",
                   command=self.destroy).pack(side=LEFT)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 4
        self.geometry(f"+{x}+{y}")

    def _toggle_hide(self) -> None:
        self.app._ui["show_welcome"] = not self._hide.get()
        self.app._settings["ui"] = self.app._ui
        try:
            save_settings(self.app._settings)
        except OSError:
            pass


class AboutDialog(Toplevel):
    """نافذة «حول البرنامج»: الشعار والاسم والإصدار والحقوق."""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        from . import __release_name__, __version__
        self.title("حول البرنامج")
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        outer = ttk.Frame(self, padding=28)
        outer.pack()
        logo = logo_image(self, width=190)
        if logo is not None:
            lbl = ttk.Label(outer, image=logo, background=BG)
            lbl.image = logo
            lbl.pack(pady=(0, 12))
        ttk.Label(outer, text="المصطفى للحج والعمرة", font=(_FSB, 16),
                  foreground=TEXT, background=BG).pack()
        ttk.Label(outer, text="برنامج موسم الحج", font=(_FUI, 11),
                  foreground=MUTED, background=BG).pack(pady=(2, 8))
        ver = f"الإصدار {__version__}"
        if __release_name__:
            ver += f"   «{__release_name__}»"
        ttk.Label(outer, text=ver, font=(_FSB, 12), foreground=BRONZE,
                  background=BG).pack()
        ttk.Label(outer, justify="center", font=(_FUI, 9), foreground=MUTED,
                  background=BG, text=rtl(
                      "إدارة متكاملة لبيانات الحجّاج: الجوازات والتأشيرات، التسكين\n"
                      "والمواصلات، المالية والدفعات، الكشوف والبطاقات، والحضور.")
                  ).pack(pady=(12, 8))
        ttk.Label(outer, text=rtl("© جميع الحقوق محفوظة"), font=(_FUI, 8),
                  foreground=MUTED, background=BG).pack()
        ttk.Button(outer, text="إغلاق", style="Ghost.TButton",
                   command=self.destroy).pack(pady=(16, 0))
        self.bind("<Escape>", lambda _e: self.destroy())
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 3
        self.geometry(f"+{x}+{y}")


class ShortcutsDialog(Toplevel):
    """اختصارات لوحة المفاتيح."""

    SHORTCUTS = (
        ("Ctrl + K", "البحث السريع / لوحة الأوامر"),
        ("Ctrl + Z", "تراجع عن آخر عملية"),
        ("Delete", "حذف الحاج المحدّد"),
        ("نقر مزدوج", "تعديل بيانات الحاج"),
        ("زرّ الفأرة الأيمن", "قائمة إجراءات الصفّ"),
        ("F1  /  ؟", "عرض هذه الاختصارات"),
        ("Esc", "إغلاق النوافذ"),
    )

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.title("⌨ اختصارات لوحة المفاتيح")
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        outer = ttk.Frame(self, padding=22)
        outer.pack()
        ttk.Label(outer, text=rtl("⌨  اختصارات لوحة المفاتيح"), font=(_FSB, 14),
                  foreground=TEXT, background=BG).pack(anchor="e", pady=(0, 12))
        grid = ttk.Frame(outer)
        grid.pack(fill=BOTH, expand=True)
        for i, (key, desc) in enumerate(self.SHORTCUTS):
            ttk.Label(grid, text=desc, font=(_FUI, 10), foreground=TEXT,
                      background=BG).grid(row=i, column=1, sticky="e",
                                          padx=(18, 6), pady=5)
            chip = tk.Label(grid, text=key, bg=PANEL, fg=BRONZE,
                            font=("Consolas", 10, "bold"), padx=10, pady=3)
            chip.grid(row=i, column=0, sticky="w", pady=5)
        ttk.Button(outer, text="إغلاق", style="Ghost.TButton",
                   command=self.destroy).pack(anchor="w", pady=(14, 0))
        self.bind("<Escape>", lambda _e: self.destroy())
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 3
        self.geometry(f"+{x}+{y}")


class DashboardDialog(Toplevel):
    """لوحة التحكم الرئيسية: مؤشّرات سريعة (KPIs) قابلة للنقر تفتح التفاصيل."""

    def __init__(self, parent, app) -> None:
        super().__init__(parent)
        self.app = app
        self.title("🏠 لوحة التحكم")
        self.configure(bg=BG)
        self.transient(parent)
        self.resizable(False, False)

        self._outer = ttk.Frame(self, padding=18)
        self._outer.pack(fill=BOTH, expand=True)
        self.refresh()
        self.bind("<Escape>", lambda _e: self.destroy())

        # الحجم يتبع المحتوى (يتجنّب قصّ الأزرار) ثم توسيط النافذة
        self.update_idletasks()
        self.minsize(760, self.winfo_reqheight())
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = max(20, (self.winfo_screenheight() - self.winfo_height()) // 6)
        self.geometry(f"+{x}+{y}")

    def _card(self, parent, value, label, color, on_click=None):
        # بطاقة أنيقة: حدّ ناعم + شريط لون علوي رفيع + خلفية اللوح
        outer = tk.Frame(parent, bg=BORDER)
        tk.Frame(outer, bg=color, height=3).pack(fill="x", padx=1, pady=(1, 0))
        card = tk.Frame(outer, bg=PANEL, padx=16, pady=12)
        card.pack(fill="both", expand=True, padx=1, pady=(0, 1))
        big = tk.Label(card, text=str(value), bg=PANEL, font=(_FSB, 20), fg=color)
        big.pack(anchor="e")
        sub = tk.Label(card, text=label, bg=PANEL, fg=MUTED, font=(_FUI, 10))
        sub.pack(anchor="e")
        if on_click is not None:
            for w in (outer, card, big, sub):
                w.configure(cursor="hand2")
                w.bind("<Button-1>", lambda _e: on_click())
        return outer

    def refresh(self) -> None:
        from .fields import format_amount
        from .stats import (financial_summary, financials_by_program,
                            outstanding)
        from .quality import check_records

        for w in self._outer.winfo_children():
            w.destroy()
        recs = list(self.app.records)
        fin = financial_summary(recs)
        owe = outstanding(recs)
        report = check_records(recs, programs=self.app._programs_by_name())
        issues = len(report.issues)

        name = self.app.season_year.get().strip()
        ttk.Label(self._outer, text=f"لوحة التحكم — موسم {name}هـ" if name
                  else "لوحة التحكم", font=(_FSB, 14),
                  foreground=TEXT, background=BG).pack(anchor="e", pady=(0, 12))

        # بطاقات المؤشّرات (شبكة 3 أعمدة)
        grid = ttk.Frame(self._outer)
        grid.pack(fill=X)
        for c in range(3):
            grid.columnconfigure(c, weight=1, uniform="kpi")
        cards = [
            (fin.count, "إجمالي الحجّاج", BRONZE, None),
            (format_amount(fin.paid) or "0", "المحصّل", SUCCESS_FG,
             self.app.do_stats),
            (format_amount(fin.remaining) or "0", "المتبقّي", DANGER,
             self.app.do_stats),
            (f"{fin.collected_percent}%", "نسبة التحصيل", BRONZE,
             self.app.do_stats),
            (len(owe), "عدد المتأخّرات", AMBER_FG, self.app.do_stats),
            (issues, "تنبيهات الجودة", ("#2C5AA0" if issues == 0 else DANGER),
             self.app.do_quality_check),
        ]
        for i, (val, lbl, col, act) in enumerate(cards):
            self._card(grid, val, lbl, col,
                       (lambda a=act: (self.destroy(), a())) if act else None
                       ).grid(row=i // 3, column=i % 3, sticky="nsew",
                              padx=6, pady=6)

        # المالية حسب البرنامج
        ttk.Label(self._outer, text="المالية حسب البرنامج",
                  font=(_FSB, 11), foreground=BRONZE,
                  background=BG).pack(anchor="e", pady=(14, 4))
        tv = ttk.Treeview(self._outer, columns=("count", "paid", "remaining", "pct"),
                          show="tree headings", height=5)
        tv.heading("#0", text="البرنامج")
        for c, t, w in (("count", "الحجّاج", 80), ("paid", "المحصّل", 120),
                        ("remaining", "المتبقّي", 120), ("pct", "التحصيل", 90)):
            tv.heading(c, text=t)
            tv.column(c, width=w, anchor="center", stretch=False)
        tv.column("#0", width=160, anchor="e", stretch=True)
        for pname, pf in financials_by_program(recs):
            tv.insert("", END, text=pname,
                      values=(f"{pf.count:,}", format_amount(pf.paid) or "0",
                              format_amount(pf.remaining) or "0",
                              f"{pf.collected_percent}%"))
        tv.pack(fill=X)

        # إعدادات العرض («الأعمدة» في لوحة الفلاتر)
        view_row = ttk.Frame(self._outer)
        view_row.pack(anchor="e", pady=(14, 0))
        ttk.Label(view_row, text="إعدادات العرض:", background=BG, foreground=MUTED,
                  font=(_FUI, 9)).pack(side=RIGHT, padx=(4, 8))
        self.app._build_view_menubutton(view_row).pack(side=RIGHT, padx=3)

        row = ttk.Frame(self._outer)
        row.pack(anchor="e", pady=(8, 0))
        ttk.Button(row, text=rtl("📊  الإحصاءات"), style="Act.TButton",
                   command=lambda: (self.destroy(), self.app.do_stats())
                   ).pack(side=RIGHT, padx=3)
        ttk.Button(row, text=rtl("🩺  فحص الجودة"), style="Act.TButton",
                   command=lambda: (self.destroy(), self.app.do_quality_check())
                   ).pack(side=RIGHT, padx=3)
        ttk.Button(row, text=rtl("↻  تحديث"), style="Ghost.TButton",
                   command=self.refresh).pack(side=RIGHT, padx=3)
        ttk.Button(row, text="إغلاق", style="Ghost.TButton",
                   command=self.destroy).pack(side=RIGHT, padx=3)


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
                      font=(_FSB, 15),
                      foreground=self._CARD_COLORS.get(label, ACCENT)).pack(anchor="e")
            ttk.Label(card, text=label, background=BG, foreground=MUTED,
                      font=(_FUI, 9)).pack(anchor="e")

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
                           width=16, font=(_FUI, 10),
                           values=[lbl for _k, lbl in GROUPINGS])
        box.pack(side=RIGHT)
        box.bind("<<ComboboxSelected>>", lambda _e: self._refresh_dist())
        ttk.Label(top, text="التوزيع حسب:", font=(_FUI, 10),
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
        self._owe_total = ttk.Label(owe_tab, font=(_FSB, 11),
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

        # ---- تبويب المالية حسب البرنامج ----
        prog_tab = ttk.Frame(nb, padding=10)
        nb.add(prog_tab, text="المالية حسب البرنامج")
        self._prog = ttk.Treeview(
            prog_tab, columns=("count", "total", "paid", "remaining", "pct"),
            show="tree headings", height=12)
        self._prog.heading("#0", text="البرنامج")
        self._prog.heading("count", text="الحجّاج")
        self._prog.heading("total", text="الإجمالي")
        self._prog.heading("paid", text="المحصّل")
        self._prog.heading("remaining", text="المتبقّي")
        self._prog.heading("pct", text="التحصيل")
        self._prog.column("#0", width=150, anchor="e", stretch=True)
        for c, w in (("count", 70), ("total", 110), ("paid", 110),
                     ("remaining", 110), ("pct", 80)):
            self._prog.column(c, width=w, anchor="center", stretch=False)
        self._prog.tag_configure("paidrow", foreground=SUCCESS_FG)
        self._prog.tag_configure("duerow", foreground=DANGER)
        self._prog.pack(fill=BOTH, expand=True)

        row = ttk.Frame(outer)
        row.pack(anchor="e", pady=(10, 0))
        ttk.Button(row, text=rtl("📄  تصدير PDF"), style="Act.TButton",
                   command=self._export_pdf).pack(side=RIGHT, padx=3)
        ttk.Button(row, text="إغلاق", style="Ghost.TButton",
                   command=self.destroy).pack(side=RIGHT, padx=3)
        self.bind("<Escape>", lambda _e: self.destroy())

        self._refresh_dist()
        self._refresh_outstanding()
        self._refresh_programs()

    def _refresh_programs(self) -> None:
        from .fields import format_amount
        from .stats import financials_by_program
        self._prog.delete(*self._prog.get_children())
        for name, fin in financials_by_program(self._records):
            tag = "paidrow" if fin.remaining <= 0.005 else "duerow"
            self._prog.insert(
                "", END, text=name, tags=(tag,),
                values=(f"{fin.count:,}", format_amount(fin.total) or "0",
                        format_amount(fin.paid) or "0",
                        format_amount(fin.remaining) or "0",
                        f"{fin.collected_percent}%"))

    def _export_pdf(self) -> None:
        from .pdf_io import export_stats_pdf
        open_preview(self,
                     lambda p: export_stats_pdf(self._records, p, season=self._season),
                     f"إحصاءات_ومالية_{date.today().isoformat()}", "pdf")

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
                  font=(_FSB, 12), foreground=TEXT,
                  background=BG).pack(anchor="e")
        ttk.Label(outer, foreground=MUTED, font=(_FUI, 9), justify="right",
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
            ttk.Label(fr, text=label, font=(_FUI, 10), foreground=TEXT,
                      background=BG, width=18, anchor="e").pack(side=RIGHT, padx=(6, 0))
            e = ttk.Entry(fr, textvariable=var, width=30, justify="right",
                          font=(_FUI, 10))
            install_entry_editing(e)
            e.pack(side=RIGHT, fill=X, expand=True)

        row("اسم الحملة", self._company)
        row("رقم واعظ الحملة", self._preacher)
        row("رقم الطوارئ", self._emergency)

        ttk.Label(outer, text="الإداريون (اختياري — سطر لكل إداري):",
                  font=(_FUI, 10), foreground=TEXT, background=BG).pack(
            anchor="e", pady=(8, 2))
        self._admins = tk.Text(outer, height=3, width=44, font=(_FUI, 10),
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
        from .pdf_io import export_badges_pdf
        path = open_preview(
            self,
            lambda p: export_badges_pdf(
                self._records, p, company=self._company.get().strip(),
                session=self._session, preacher=self._preacher.get().strip(),
                admins=self._admins.get("1.0", "end").strip(),
                emergency=self._emergency.get().strip()),
            f"بطاقات_الحجاج_{date.today().isoformat()}", "pdf")
        if path is not None:
            self.destroy()


class ReadinessDialog(Toplevel):
    """قائمة تحقّق جاهزية الحجّاج: جواز/تأشيرة/تصريح/تطعيم/دفع/اتصال + النسبة."""

    def __init__(self, parent, get_records, on_select) -> None:
        super().__init__(parent)
        self.get_records = get_records
        self.on_select = on_select
        self.title("✅ قائمة تحقّق الجاهزية")
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()

        from .quality import READINESS_ITEMS
        self._items = READINESS_ITEMS

        outer = ttk.Frame(self, padding=14)
        outer.pack(fill=BOTH, expand=True)
        top = ttk.Frame(outer)
        top.pack(fill=X, pady=(0, 8))
        self._summary = ttk.Label(top, font=(_FSB, 11), foreground=TEXT)
        self._summary.pack(side=RIGHT)
        self._only_incomplete = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text=rtl("غير المكتملين فقط"),
                        variable=self._only_incomplete,
                        command=self._reload).pack(side=LEFT)

        cols = ("idx", "name") + tuple(k for k, _ in self._items) + ("pct",)
        self.tree = ttk.Treeview(outer, columns=cols, show="headings", height=16)
        self.tree.heading("idx", text="م")
        self.tree.column("idx", width=42, anchor="center")
        self.tree.heading("name", text="اسم الحاج")
        self.tree.column("name", width=200, anchor="e")
        for key, label in self._items:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=88, anchor="center")
        self.tree.heading("pct", text="الجاهزية")
        self.tree.column("pct", width=78, anchor="center")
        self.tree.tag_configure("done", background="#E8F6EC")
        self.tree.tag_configure("low", background="#FBEBEA")
        self.tree.pack(fill=BOTH, expand=True)
        self.tree.bind("<Double-1>", self._jump)

        ttk.Label(outer, foreground=MUTED, font=(_FUI, 9),
                  text=rtl("نقرة مزدوجة على الحاج لفتحه في الجدول.")
                  ).pack(anchor="e", pady=(8, 0))
        ttk.Button(outer, text="إغلاق", style="Ghost.TButton",
                   command=self.destroy).pack(anchor="w", pady=(6, 0))
        self.bind("<Escape>", lambda _e: self.destroy())
        self._reload()
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 4
        self.geometry(f"+{x}+{y}")

    def _reload(self) -> None:
        from .quality import pilgrim_readiness, readiness_percent
        self.tree.delete(*self.tree.get_children())
        recs = self.get_records()
        ready = 0
        for i, rec in enumerate(recs):
            checks = pilgrim_readiness(rec)
            complete = all(checks.values())
            if complete:
                ready += 1
            if self._only_incomplete.get() and complete:
                continue
            pct = readiness_percent(rec)
            name = (rec.full_name_ar or rec.full_name_en
                    or rec.passport_number or "—")
            vals = ([i + 1, name]
                    + ["✓" if checks[k] else "✗" for k, _ in self._items]
                    + [f"{pct}%"])
            tag = "done" if complete else ("low" if pct < 50 else "")
            self.tree.insert("", "end", iid=str(i), values=vals,
                             tags=((tag,) if tag else ()))
        self._summary.configure(
            text=rtl(f"مكتملو الجاهزية: {ready} من {len(recs)}"))

    def _jump(self, _e) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        try:
            self.on_select(int(sel[0]))
        except Exception:
            pass
        self.destroy()


class QualityDialog(Toplevel):
    """فحص جودة الكشف: يعرض مشكلات الجواز والتكرار والنقص، ويقفز للسجل."""

    _TAGS = {
        "صلاحية الجواز": ("pp", "#F7E7E5", DANGER),
        "تكرار رقم الجواز": ("dup", "#FBF0DC", AMBER_FG),
        "تكرار الاسم": ("namedup", "#FBF0DC", AMBER_FG),
        "تطابق البرنامج": ("prog", "#E8EEF6", "#2C5AA0"),
        "نقص بيانات حرجة": ("miss", "#EFEBE4", "#555555"),
    }

    def __init__(self, parent, get_records, on_select, programs=None) -> None:
        super().__init__(parent)
        self._get_records = get_records      # دالة تُعيد السجلات الحالية
        self._on_select = on_select          # (index) -> يحدّد السجل في الجدول
        self._programs = programs            # دالة تُعيد خريطة {اسم: برنامج}
        self.title("🩺 فحص جاهزية الكشف")
        self.configure(bg=BG)
        self.transient(parent)
        self.geometry("720x520")

        outer = ttk.Frame(self, padding=16)
        outer.pack(fill=BOTH, expand=True)
        self._summary = ttk.Label(outer, font=(_FSB, 12),
                                  foreground=TEXT, background=BG)
        self._summary.pack(anchor="e")
        ttk.Label(outer, foreground=MUTED, font=(_FUI, 9), justify="right",
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
        progs = self._programs() if callable(self._programs) else None
        report = check_records(self._get_records(), programs=progs)
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
                  font=(_FSB, 12), foreground=TEXT,
                  background=BG).pack(anchor="e")
        ttk.Label(outer, foreground=MUTED, font=(_FUI, 9), justify="right",
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
                  font=(_FSB, 11), foreground=TEXT).pack(
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
                  font=(_FSB, 11), foreground=TEXT).pack(
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


class TravelInfoDialog(Toplevel):
    """مواعيد وتعليمات السفر لكل برنامج: جدول الرحلة + التعليمات، مع تصدير PDF."""

    def __init__(self, parent, app) -> None:
        super().__init__(parent)
        self.app = app
        self.title("🧳 مواعيد وتعليمات السفر")
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()

        from . import travel
        from .programs import PROGRAM_NAMES
        self._travel = travel
        self._names = list(PROGRAM_NAMES)
        self._current = 0
        # برامج الحملة المُدخلة سابقاً — تُؤخذ منها الرحلة والتواريخ
        self._progs = app._load_programs()
        self._data = {i: travel.load_travel(app._settings, i, self._progs[i])
                      for i in range(len(self._names))}

        outer = ttk.Frame(self, padding=14)
        outer.pack(fill=BOTH, expand=True)

        top = ttk.Frame(outer)
        top.pack(fill=X, pady=(0, 8))
        ttk.Label(top, text="البرنامج:", font=(_FSB, 11),
                  foreground=TEXT).pack(side=RIGHT, padx=(0, 8))
        self._sel = StringVar(value="0")
        for i, name in enumerate(self._names):
            ttk.Radiobutton(top, text=name, value=str(i), variable=self._sel,
                            command=self._switch).pack(side=RIGHT, padx=4)

        nb = ttk.Notebook(outer)
        nb.pack(fill=BOTH, expand=True)
        self._flight_vars: dict[str, StringVar] = {}
        self._texts: dict[str, tk.Text] = {}

        # تبويب الرحلة
        ftab = ttk.Frame(nb, padding=12)
        nb.add(ftab, text="الرحلة (ذهاب/عودة)")
        for col, (prefix, head) in enumerate((("out_", "رحلة الذهاب"),
                                              ("ret_", "رحلة العودة"))):
            box = ttk.Labelframe(ftab, text=head, padding=8)
            box.grid(row=0, column=col, padx=8, sticky="n")
            for r, (key, label) in enumerate(travel.FLIGHT_FIELDS):
                ttk.Label(box, text=label, font=(_FUI, 9),
                          foreground=TEXT).grid(row=r, column=1, sticky="e",
                                                padx=(8, 4), pady=3)
                var = StringVar()
                self._flight_vars[prefix + key] = var
                ttk.Entry(box, textvariable=var, width=22,
                          justify="right").grid(row=r, column=0, pady=3)

        # تبويبات النصوص
        for key, label in travel.TEXT_SECTIONS:
            tab = ttk.Frame(nb, padding=8)
            nb.add(tab, text=label)
            txt = tk.Text(tab, width=70, height=14, wrap="word", font=(_FUI, 10))
            txt.pack(fill=BOTH, expand=True)
            self._texts[key] = txt

        btns = ttk.Frame(outer)
        btns.pack(fill=X, pady=(10, 0))
        ttk.Button(btns, text=rtl("📄 تصدير/معاينة PDF"), style="Primary.TButton",
                   command=self._export).pack(side=RIGHT, padx=3)
        ttk.Button(btns, text=rtl("💾 حفظ"), style="Act.TButton",
                   command=self._save).pack(side=RIGHT, padx=3)
        ttk.Button(btns, text=rtl("⤓ من بيانات البرنامج"), style="Ghost.TButton",
                   command=self._fill_from_program).pack(side=RIGHT, padx=3)
        ttk.Button(btns, text=rtl("↺ استعادة القالب"), style="Ghost.TButton",
                   command=self._reset_template).pack(side=RIGHT, padx=3)
        ttk.Button(btns, text="إغلاق", style="Ghost.TButton",
                   command=self.destroy).pack(side=LEFT, padx=3)
        self.bind("<Escape>", lambda _e: self.destroy())

        self._load_into_form(0)
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 6
        self.geometry(f"+{x}+{y}")

    def _load_into_form(self, idx: int) -> None:
        d = self._data[idx]
        flight = d.get("flight", {})
        for key, var in self._flight_vars.items():
            var.set(str(flight.get(key, "") or ""))
        for key, txt in self._texts.items():
            txt.delete("1.0", "end")
            txt.insert("1.0", str(d.get(key, "") or ""))

    def _dump_form(self, idx: int) -> None:
        self._data[idx] = {
            "flight": {k: v.get().strip() for k, v in self._flight_vars.items()},
            **{key: self._texts[key].get("1.0", "end").strip()
               for key, _ in self._travel.TEXT_SECTIONS},
        }

    def _switch(self) -> None:
        self._dump_form(self._current)
        self._current = int(self._sel.get())
        self._load_into_form(self._current)

    def _reset_template(self) -> None:
        if not messagebox.askyesno("استعادة القالب",
                                   "استبدال محتوى هذا البرنامج بالقالب الافتراضي؟",
                                   parent=self):
            return
        prog = self._progs[self._current]
        self._data[self._current] = self._travel.default_travel(
            self._current, prog)
        self._load_into_form(self._current)

    def _fill_from_program(self) -> None:
        """يملأ حقول الرحلة والتواريخ من برنامج الحملة المُدخل لهذا البرنامج."""
        flight = self._travel.from_program(self._progs[self._current])
        if not any(flight.values()):
            messagebox.showinfo(
                "لا بيانات",
                "لا توجد تواريخ/مطارات في هذا البرنامج بعد.\n"
                "أدخلها من «البرامج ← برامج الحملة» أولاً.", parent=self)
            return
        for key, val in flight.items():
            if key in self._flight_vars and str(val or "").strip():
                self._flight_vars[key].set(val)
        self.app.set_status("مُلئت الرحلة من بيانات البرنامج", ok=True)

    def _save(self) -> None:
        self._dump_form(self._current)
        for i, data in self._data.items():
            self._travel.save_travel(self.app._settings, i, data)
        try:
            save_settings(self.app._settings)
        except OSError:
            pass
        self.app._audit("حفظ مواعيد وتعليمات السفر", self._names[self._current])
        self.app.set_status("حُفظت مواعيد وتعليمات السفر", ok=True)

    def _export(self) -> None:
        self._dump_form(self._current)
        idx = self._current
        data = self._data[idx]
        name = self._names[idx]
        season = self.app.season_year.get()
        itinerary = [list(r) for r in self.app._settings.get("itinerary", [])]
        from .pdf_io import export_travel_pdf
        self.app._preview_export(
            lambda p: export_travel_pdf(p, program_name=name, data=data,
                                        itinerary=itinerary, season=season),
            f"مواعيد وتعليمات السفر — {name}", "pdf")


class ItineraryDialog(Toplevel):
    """جدول المناسك الزمني: يوم/تاريخ/النشاط/المكان/ملاحظة — يُحفظ ويُصدَّر."""

    # قالب أيام الحجّ الافتراضي (يُملأ بضغطة)
    TEMPLATE = (
        ("8 ذو الحجة", "", "التوجّه إلى منى (يوم التروية)", "منى", ""),
        ("9 ذو الحجة", "", "الوقوف بعرفة", "عرفة", "الدعاء والذكر"),
        ("9 ذو الحجة", "", "المبيت والمزدلفة وجمع الحصى", "مزدلفة", ""),
        ("10 ذو الحجة", "", "رمي جمرة العقبة، الحلق، طواف الإفاضة", "منى/مكة", "يوم النحر"),
        ("11 ذو الحجة", "", "رمي الجمرات الثلاث", "منى", "أيام التشريق"),
        ("12 ذو الحجة", "", "رمي الجمرات ثم التعجّل أو التأخّر", "منى", ""),
        ("13 ذو الحجة", "", "رمي الجمرات لمن تأخّر", "منى", ""),
        ("", "", "طواف الوداع قبل المغادرة", "مكة", ""),
    )

    def __init__(self, parent, app) -> None:
        super().__init__(parent)
        self.app = app
        self.title("🗓 جدول المناسك")
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()

        self._items = [list(x) if isinstance(x, (list, tuple)) else x
                       for x in app._settings.get("itinerary", [])]

        outer = ttk.Frame(self, padding=16)
        outer.pack(fill=BOTH, expand=True)
        ttk.Label(outer, text=rtl("🗓  جدول المناسك الزمني"), font=(_FSB, 14),
                  foreground=TEXT).pack(anchor="e", pady=(0, 8))

        cols = ("day", "date", "activity", "place", "note")
        self.tree = ttk.Treeview(outer, columns=cols, show="headings", height=10)
        for key, text, w, anc in (("day", "اليوم", 100, "center"),
                                   ("date", "التاريخ", 100, "center"),
                                   ("activity", "النشاط/المنسك", 240, "e"),
                                   ("place", "المكان", 100, "center"),
                                   ("note", "ملاحظة", 140, "e")):
            self.tree.heading(key, text=text)
            self.tree.column(key, width=w, anchor=anc)
        self.tree.pack(fill=BOTH, expand=True)
        self.tree.bind("<Double-1>", self._edit_selected)
        ttk.Label(outer, foreground=MUTED, font=(_FUI, 9),
                  text=rtl("نقرة مزدوجة على أي بند لتعديله.")).pack(anchor="e",
                                                                    pady=(4, 0))

        form = ttk.Frame(outer)
        form.pack(fill=X, pady=(10, 0))
        self._day = StringVar(); self._date = StringVar()
        self._activity = StringVar(); self._place = StringVar(); self._note = StringVar()
        for var, hint, w in ((self._day, "اليوم", 10), (self._date, "التاريخ", 10),
                             (self._activity, "النشاط", 22), (self._place, "المكان", 10),
                             (self._note, "ملاحظة", 14)):
            ttk.Entry(form, textvariable=var, width=w,
                      justify="right").pack(side=RIGHT, padx=2)
            ttk.Label(form, text=hint, foreground=MUTED).pack(side=RIGHT)

        btns = ttk.Frame(outer)
        btns.pack(fill=X, pady=(10, 0))
        ttk.Button(btns, text=rtl("➕ إضافة"), style="Primary.TButton",
                   command=self._add).pack(side=RIGHT, padx=3)
        ttk.Button(btns, text=rtl("✏️ تعديل"), style="Act.TButton",
                   command=self._edit_selected).pack(side=RIGHT, padx=3)
        ttk.Button(btns, text=rtl("🗑 حذف"), style="Ghost.TButton",
                   command=self._delete).pack(side=RIGHT, padx=3)
        ttk.Button(btns, text=rtl("📋 قالب أيام الحجّ"), style="Ghost.TButton",
                   command=self._fill_template).pack(side=RIGHT, padx=3)
        ttk.Button(btns, text=rtl("🕋 برنامج رحلة الحج (مفصّل)"),
                   style="Ghost.TButton",
                   command=self._fill_hajj_program).pack(side=RIGHT, padx=3)
        ttk.Button(btns, text=rtl("📄 تصدير/طباعة"), style="Ghost.TButton",
                   command=self._export).pack(side=LEFT, padx=3)
        ttk.Button(btns, text="إغلاق", style="Ghost.TButton",
                   command=self.destroy).pack(side=LEFT, padx=3)
        self.bind("<Escape>", lambda _e: self.destroy())
        self._reload()
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 4
        self.geometry(f"+{x}+{y}")

    def _reload(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for i, row in enumerate(self._items):
            self.tree.insert("", "end", iid=str(i), values=tuple(row))

    def _persist(self) -> None:
        self.app._settings["itinerary"] = [list(r) for r in self._items]
        try:
            save_settings(self.app._settings)
        except OSError:
            pass
        self.app._audit("تعديل جدول المناسك", f"{len(self._items)} بند")
        self._reload()

    def _add(self) -> None:
        row = [self._day.get().strip(), self._date.get().strip(),
               self._activity.get().strip(), self._place.get().strip(),
               self._note.get().strip()]
        if not any(row):
            return
        self._items.append(row)
        for v in (self._day, self._date, self._activity, self._place, self._note):
            v.set("")
        self._persist()

    def _delete(self) -> None:
        sel = self.tree.selection()
        for iid in sorted((int(s) for s in sel), reverse=True):
            if 0 <= iid < len(self._items):
                del self._items[iid]
        self._persist()

    def _edit_selected(self, _e=None) -> None:
        """يفتح محرّراً لتعديل البند المحدّد (نقرة مزدوجة أو زرّ «تعديل»)."""
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("تعديل", "اختر بنداً من الجدول أولاً.", parent=self)
            return
        idx = int(sel[0])
        if not (0 <= idx < len(self._items)):
            return
        row = list(self._items[idx]) + ["", "", "", "", ""]
        ed = Toplevel(self)
        ed.title("تعديل بند")
        ed.configure(bg=BG)
        ed.transient(self)
        ed.grab_set()
        ed.resizable(False, False)
        frm = ttk.Frame(ed, padding=16)
        frm.pack()
        labels = ("اليوم", "التاريخ", "النشاط/المنسك", "المكان", "ملاحظة")
        widths = (18, 18, 46, 18, 34)
        vs = []
        for i, (lab, w) in enumerate(zip(labels, widths)):
            ttk.Label(frm, text=lab, font=(_FUI, 10), foreground=TEXT).grid(
                row=i, column=1, sticky="e", padx=(10, 6), pady=4)
            v = StringVar(value=str(row[i]))
            vs.append(v)
            ttk.Entry(frm, textvariable=v, width=w, justify="right").grid(
                row=i, column=0, pady=4)

        def _save():
            self._items[idx] = [v.get().strip() for v in vs]
            ed.destroy()
            self._persist()
            try:
                self.tree.selection_set(str(idx))
                self.tree.see(str(idx))
            except Exception:
                pass

        bar = ttk.Frame(frm)
        bar.grid(row=99, column=0, columnspan=2, pady=(12, 0), sticky="ew")
        ttk.Button(bar, text=rtl("💾 حفظ"), style="Primary.TButton",
                   command=_save).pack(side=RIGHT, padx=3)
        ttk.Button(bar, text="إلغاء", style="Ghost.TButton",
                   command=ed.destroy).pack(side=LEFT, padx=3)
        ed.bind("<Return>", lambda _e: _save())
        ed.bind("<Escape>", lambda _e: ed.destroy())
        ed.update_idletasks()
        x = (ed.winfo_screenwidth() - ed.winfo_width()) // 2
        y = (ed.winfo_screenheight() - ed.winfo_height()) // 3
        ed.geometry(f"+{x}+{y}")

    def _fill_template(self) -> None:
        if self._items and not messagebox.askyesno(
                "قالب", "استبدال الجدول الحالي بقالب أيام الحجّ؟", parent=self):
            return
        self._items = [list(r) for r in self.TEMPLATE]
        self._persist()

    def _fill_hajj_program(self) -> None:
        """يملأ الجدول ببرنامج رحلة الحج المفصّل (من وثيقة الحملة)."""
        if self._items and not messagebox.askyesno(
                "برنامج رحلة الحج",
                "استبدال الجدول الحالي ببرنامج رحلة الحج المفصّل؟\n"
                "(عدّل التواريخ حسب موسمك عند اللزوم)", parent=self):
            return
        from .travel import DETAILED_HAJJ_PROGRAM
        self._items = [list(r) for r in DETAILED_HAJJ_PROGRAM]
        self._persist()

    def _export(self) -> None:
        """يعاين جدول المناسك PDF (تطبع أو تحفظ من العارض)."""
        if not self._items:
            messagebox.showinfo("فارغ", "أضِف بنوداً أولاً أو استعمل القالب.",
                                parent=self)
            return
        rows = [list(r) for r in self._items]
        season = self.app.season_year.get()
        from .pdf_io import export_itinerary_pdf
        if open_preview(self.master,
                        lambda p: export_itinerary_pdf(p, rows=rows, season=season),
                        "جدول المناسك", "pdf"):
            self.app.set_status("فُتحت معاينة جدول المناسك — اطبع أو احفظ", ok=True)


class ExpensesDialog(Toplevel):
    """مصروفات الحملة ومحاسبتها: موردون وفئات، مع صافي = المحصّل − المصروفات."""

    CATEGORIES = ("فنادق", "نقل", "إعاشة", "تصاريح", "رواتب", "طيران", "أخرى")

    def __init__(self, parent, app) -> None:
        super().__init__(parent)
        self.app = app
        self.title("🧮 المصروفات والمحاسبة")
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()

        self._items = list(app._settings.get("expenses", []))

        outer = ttk.Frame(self, padding=16)
        outer.pack(fill=BOTH, expand=True)
        self._totals = ttk.Label(outer, font=(_FSB, 11), foreground=TEXT,
                                 justify="right")
        self._totals.pack(anchor="e", pady=(0, 10))

        cols = ("date", "supplier", "category", "amount", "note")
        self.tree = ttk.Treeview(outer, columns=cols, show="headings", height=9)
        for key, text, w, anc in (("date", "التاريخ", 100, "center"),
                                   ("supplier", "المورّد", 150, "e"),
                                   ("category", "الفئة", 90, "center"),
                                   ("amount", "المبلغ", 100, "center"),
                                   ("note", "ملاحظة", 160, "e")):
            self.tree.heading(key, text=text)
            self.tree.column(key, width=w, anchor=anc)
        self.tree.pack(fill=BOTH, expand=True)

        form = ttk.Frame(outer)
        form.pack(fill=X, pady=(10, 0))
        from datetime import date
        self._date = StringVar(value=date.today().isoformat())
        self._supplier = StringVar()
        self._category = StringVar(value=self.CATEGORIES[0])
        self._amount = StringVar()
        self._note = StringVar()
        ttk.Entry(form, textvariable=self._amount, width=11,
                  justify="center").pack(side=RIGHT, padx=2)
        ttk.Label(form, text="المبلغ", foreground=MUTED).pack(side=RIGHT)
        ttk.Combobox(form, textvariable=self._category, values=self.CATEGORIES,
                     state="readonly", width=9).pack(side=RIGHT, padx=2)
        ttk.Entry(form, textvariable=self._supplier, width=15,
                  justify="right").pack(side=RIGHT, padx=2)
        ttk.Label(form, text="المورّد", foreground=MUTED).pack(side=RIGHT)
        ttk.Entry(form, textvariable=self._date, width=11,
                  justify="center").pack(side=RIGHT, padx=2)
        ttk.Entry(form, textvariable=self._note, width=16).pack(side=RIGHT, padx=2)

        btns = ttk.Frame(outer)
        btns.pack(fill=X, pady=(10, 0))
        ttk.Button(btns, text=rtl("➕ إضافة مصروف"), style="Primary.TButton",
                   command=self._add).pack(side=RIGHT, padx=3)
        ttk.Button(btns, text=rtl("🗑 حذف المحدّد"), style="Ghost.TButton",
                   command=self._delete).pack(side=RIGHT, padx=3)
        ttk.Button(btns, text="إغلاق", style="Ghost.TButton",
                   command=self.destroy).pack(side=LEFT, padx=3)
        self.bind("<Escape>", lambda _e: self.destroy())
        self._reload()
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 4
        self.geometry(f"+{x}+{y}")

    def _expense_total(self) -> float:
        from .fields import parse_amount
        return sum(parse_amount(e.get("amount")) or 0.0 for e in self._items)

    def _reload(self) -> None:
        from .fields import format_amount, parse_amount
        self.tree.delete(*self.tree.get_children())
        for i, e in enumerate(self._items):
            self.tree.insert("", "end", iid=str(i), values=(
                e.get("date", ""), e.get("supplier", ""), e.get("category", ""),
                e.get("amount", ""), e.get("note", "")))
        collected = sum(parse_amount(r.paid_amount) or 0.0 for r in self.app.records)
        expenses = self._expense_total()
        net = collected - expenses
        self._totals.configure(text=rtl(
            f"المحصّل من الحجّاج: {format_amount(collected) or 0}    •    "
            f"المصروفات: {format_amount(expenses) or 0}    •    "
            f"الصافي: {format_amount(net) or 0}"))

    def _persist(self) -> None:
        self.app._settings["expenses"] = self._items
        try:
            save_settings(self.app._settings)
        except OSError:
            pass
        self.app._audit("تعديل المصروفات", f"{len(self._items)} بند")
        self._reload()

    def _add(self) -> None:
        from .fields import format_amount, parse_amount
        amount = parse_amount(self._amount.get())
        if not amount:
            messagebox.showwarning("مبلغ غير صالح", "أدخل مبلغ المصروف بالأرقام.",
                                   parent=self)
            return
        self._items.append({
            "date": self._date.get().strip(),
            "supplier": self._supplier.get().strip(),
            "category": self._category.get().strip(),
            "amount": format_amount(amount),
            "note": self._note.get().strip(),
        })
        self._supplier.set("")
        self._amount.set("")
        self._note.set("")
        self._persist()

    def _delete(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        for iid in sorted((int(s) for s in sel), reverse=True):
            if 0 <= iid < len(self._items):
                del self._items[iid]
        self._persist()


class PaymentsDialog(Toplevel):
    """سجلّ دفعات الحاج (الأقساط): عرض وإضافة وحذف، ومزامنة «المبلغ المدفوع»."""

    METHODS = ("نقد", "تحويل بنكي", "شبكة/مدى", "شيك", "أخرى")

    def __init__(self, parent, record: PassportData, on_change) -> None:
        super().__init__(parent)
        self.record = record
        self.on_change = on_change
        name = record.full_name_ar or record.full_name_en or record.passport_number or "—"
        self.title(f"💵 دفعات: {name}")
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()

        outer = ttk.Frame(self, padding=16)
        outer.pack(fill=BOTH, expand=True)

        self._totals = ttk.Label(outer, font=(_FSB, 11), foreground=TEXT)
        self._totals.pack(anchor="e", pady=(0, 10))

        cols = ("date", "amount", "method", "note")
        self.tree = ttk.Treeview(outer, columns=cols, show="headings", height=8)
        for key, text, w, anc in (("date", "التاريخ", 110, "center"),
                                   ("amount", "المبلغ", 100, "center"),
                                   ("method", "الطريقة", 110, "center"),
                                   ("note", "ملاحظة", 200, "e")):
            self.tree.heading(key, text=text)
            self.tree.column(key, width=w, anchor=anc)
        self.tree.pack(fill=BOTH, expand=True)

        # نموذج إضافة دفعة
        form = ttk.Frame(outer)
        form.pack(fill=X, pady=(10, 0))
        from datetime import date
        self._date = StringVar(value=date.today().isoformat())
        self._amount = StringVar()
        self._method = StringVar(value=self.METHODS[0])
        self._note = StringVar()
        ttk.Entry(form, textvariable=self._amount, width=12,
                  justify="center").pack(side=RIGHT, padx=3)
        ttk.Label(form, text="المبلغ", foreground=MUTED).pack(side=RIGHT)
        ttk.Entry(form, textvariable=self._date, width=12,
                  justify="center").pack(side=RIGHT, padx=3)
        ttk.Label(form, text="التاريخ", foreground=MUTED).pack(side=RIGHT)
        ttk.Combobox(form, textvariable=self._method, values=self.METHODS,
                     state="readonly", width=11).pack(side=RIGHT, padx=3)
        ttk.Entry(form, textvariable=self._note, width=18).pack(side=RIGHT, padx=3)
        ttk.Label(form, text="ملاحظة", foreground=MUTED).pack(side=RIGHT)

        btns = ttk.Frame(outer)
        btns.pack(fill=X, pady=(10, 0))
        ttk.Button(btns, text=rtl("➕ إضافة دفعة"), style="Primary.TButton",
                   command=self._add).pack(side=RIGHT, padx=3)
        ttk.Button(btns, text=rtl("🗑 حذف المحدّدة"), style="Ghost.TButton",
                   command=self._delete).pack(side=RIGHT, padx=3)
        ttk.Button(btns, text="إغلاق", style="Ghost.TButton",
                   command=self.destroy).pack(side=LEFT, padx=3)

        self.bind("<Escape>", lambda _e: self.destroy())
        self._reload()
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 3
        self.geometry(f"+{x}+{y}")

    def _reload(self) -> None:
        from .fields import compute_remaining, format_amount, payment_total
        self.tree.delete(*self.tree.get_children())
        for i, p in enumerate(self.record.payments or []):
            self.tree.insert("", "end", iid=str(i), values=(
                p.get("date", ""), p.get("amount", ""),
                p.get("method", ""), p.get("note", "")))
        paid = format_amount(payment_total(self.record)) or "0"
        value = self.record.program_value or "0"
        rem = compute_remaining(self.record) or "0"
        self._totals.configure(text=rtl(
            f"قيمة البرنامج: {value}    •    المدفوع: {paid}    •    المتبقّي: {rem}"))

    def _commit(self) -> None:
        # داخل سجلّ الدفعات يصبح «المدفوع» = مجموع الدفعات دائماً (حتى صفر)
        from .fields import format_amount, payment_total
        self.record.paid_amount = format_amount(payment_total(self.record))
        self.on_change()
        self._reload()

    def _add(self) -> None:
        from .fields import parse_amount
        amount = parse_amount(self._amount.get())
        if not amount:
            messagebox.showwarning("مبلغ غير صالح",
                                   "أدخل مبلغ الدفعة بالأرقام.", parent=self)
            return
        from .fields import format_amount
        self.record.payments.append({
            "date": self._date.get().strip(),
            "amount": format_amount(amount),
            "method": self._method.get().strip(),
            "note": self._note.get().strip(),
        })
        self._amount.set("")
        self._note.set("")
        self._commit()

    def _delete(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        for iid in sorted((int(s) for s in sel), reverse=True):
            if 0 <= iid < len(self.record.payments):
                del self.record.payments[iid]
        self._commit()


class ChartsDialog(Toplevel):
    """رسوم بيانية للكشف: توزيعات (برنامج/فندق/جنسية/حالة) + المالية — أعمدة."""

    def __init__(self, parent, records) -> None:
        super().__init__(parent)
        self.title("📊 الرسوم البيانية")
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()

        from .fields import parse_amount
        from .stats import distribution

        W, section_h = 640, 24
        outer = ttk.Frame(self, padding=10)
        outer.pack(fill=BOTH, expand=True)
        canvas = tk.Canvas(outer, width=W, height=560, bg="#FFFFFF",
                           highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        sb.pack(side=LEFT, fill=Y)
        canvas.pack(side=RIGHT, fill=BOTH, expand=True)
        canvas.configure(yscrollcommand=sb.set)
        self.canvas = canvas

        datasets = []
        for key, title in (("program", "التوزيع حسب البرنامج"),
                           ("hotel", "التوزيع حسب الفندق"),
                           ("nationality_ar", "التوزيع حسب الجنسية"),
                           ("status", "التوزيع حسب الحالة")):
            buckets = distribution(records, key)[:8]
            if buckets:
                datasets.append((title, [(b.label, b.count) for b in buckets]))
        # المالية: المحصّل مقابل المتبقّي
        paid = sum(parse_amount(r.paid_amount) or 0.0 for r in records)
        value = sum(parse_amount(r.program_value) or 0.0 for r in records)
        remaining = max(0.0, value - paid)
        if value or paid:
            datasets.append(("المالية (درهم)",
                             [("المحصّل", paid), ("المتبقّي", remaining)]))

        y = 16
        for title, items in datasets:
            y = self._draw_dataset(canvas, y, title, items, W)
            y += section_h
        canvas.configure(scrollregion=(0, 0, W, max(560, y)))

        ttk.Button(outer, text="إغلاق", style="Ghost.TButton",
                   command=self.destroy)  # (لا نعبّئه — الإغلاق بـ Esc/النافذة)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        yy = (self.winfo_screenheight() - self.winfo_height()) // 6
        self.geometry(f"+{x}+{yy}")

    def _draw_dataset(self, canvas, y, title, items, W) -> int:
        canvas.create_text(W - 12, y, text=title, anchor="e",
                           font=(_FSB, 12), fill=BRONZE)
        y += 26
        maxval = max((v for _, v in items), default=1) or 1
        label_w, right, left = 150, W - 160, 30
        bar_area = right - left
        for label, val in items:
            length = int(bar_area * (val / maxval)) if maxval else 0
            x2 = right
            x1 = right - length
            canvas.create_rectangle(x1, y, x2, y + 18, fill=BRONZE, outline="")
            canvas.create_text(W - 12, y + 9, text=str(label)[:20], anchor="e",
                               font=(_FUI, 10), fill="#1a1a1a")
            shown = int(val) if float(val).is_integer() else round(val, 1)
            canvas.create_text(x1 - 6, y + 9, text=f"{shown:,}", anchor="e",
                               font=(_FUI, 9), fill="#555555")
            y += 26
        return y


class FilterPresetsDialog(Toplevel):
    """الفلاتر المحفوظة: حفظ توليفة الفلتر الحالية باسم، وتطبيقها أو حذفها."""

    def __init__(self, parent, app) -> None:
        super().__init__(parent)
        self.app = app
        self.title("⭐ الفلاتر المحفوظة")
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)

        outer = ttk.Frame(self, padding=16)
        outer.pack(fill=BOTH, expand=True)
        ttk.Label(outer, text=rtl("⭐ الفلاتر المحفوظة"), font=(_FSB, 13),
                  foreground=TEXT).pack(anchor="e", pady=(0, 8))

        self.listbox = tk.Listbox(outer, height=8, width=34, font=(_FUI, 11),
                                  activestyle="none")
        self.listbox.pack(fill=BOTH, expand=True)
        self.listbox.bind("<Double-1>", lambda _e: self._apply())

        save = ttk.Frame(outer)
        save.pack(fill=X, pady=(10, 0))
        self._preset_name = StringVar()
        ttk.Entry(save, textvariable=self._preset_name, width=20,
                  justify="right").pack(side=RIGHT, padx=(0, 4))
        ttk.Label(save, text="اسم:", foreground=MUTED).pack(side=RIGHT)
        ttk.Button(save, text=rtl("💾 حفظ الفلتر الحالي"), style="Primary.TButton",
                   command=self._save).pack(side=RIGHT, padx=4)

        btns = ttk.Frame(outer)
        btns.pack(fill=X, pady=(10, 0))
        ttk.Button(btns, text=rtl("✔ تطبيق"), style="Act.TButton",
                   command=self._apply).pack(side=RIGHT, padx=3)
        ttk.Button(btns, text=rtl("🗑 حذف"), style="Ghost.TButton",
                   command=self._delete).pack(side=RIGHT, padx=3)
        ttk.Button(btns, text="إغلاق", style="Ghost.TButton",
                   command=self.destroy).pack(side=LEFT, padx=3)
        self.bind("<Escape>", lambda _e: self.destroy())
        self._reload()
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 3
        self.geometry(f"+{x}+{y}")

    def _presets(self) -> dict:
        p = self.app._settings.get("filter_presets")
        return dict(p) if isinstance(p, dict) else {}

    def _reload(self) -> None:
        self.listbox.delete(0, "end")
        self._preset_names = sorted(self._presets().keys())
        for name in self._preset_names:
            self.listbox.insert("end", name)

    def _selected_name(self):
        sel = self.listbox.curselection()
        return self._preset_names[sel[0]] if sel else None

    def _save(self) -> None:
        name = self._preset_name.get().strip()
        if not name:
            messagebox.showwarning("الاسم مطلوب", "أدخل اسماً للفلتر.", parent=self)
            return
        presets = self._presets()
        presets[name] = self.app._current_filter_state()
        self.app._settings["filter_presets"] = presets
        try:
            save_settings(self.app._settings)
        except OSError:
            pass
        self.app._audit("حفظ فلتر", name)
        self._preset_name.set("")
        self._reload()

    def _apply(self) -> None:
        name = self._selected_name()
        if not name:
            return
        self.app._apply_filter_state(self._presets().get(name, {}))
        self.app.set_status(f"طُبّق الفلتر: {name}", ok=True)
        self.destroy()

    def _delete(self) -> None:
        name = self._selected_name()
        if not name:
            return
        presets = self._presets()
        presets.pop(name, None)
        self.app._settings["filter_presets"] = presets
        try:
            save_settings(self.app._settings)
        except OSError:
            pass
        self._reload()


class OccupancyDialog(Toplevel):
    """عرض إشغال الغرف: المشغول مقابل السعة لكل غرفة، مع تمييز التجاوز والشواغر."""

    def __init__(self, parent, records) -> None:
        super().__init__(parent)
        self.title("🛏 إشغال الغرف")
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()

        from .rooming import group_records_by_room
        rooms, unplaced = group_records_by_room(records)

        outer = ttk.Frame(self, padding=14)
        outer.pack(fill=BOTH, expand=True)
        self._summary = ttk.Label(outer, font=(_FSB, 11), foreground=TEXT)
        self._summary.pack(anchor="e", pady=(0, 8))

        cols = ("hotel", "number", "cap", "occ", "status")
        tree = ttk.Treeview(outer, columns=cols, show="headings", height=18)
        for key, text, w, anc in (("hotel", "الفندق", 180, "e"),
                                   ("number", "الغرفة", 90, "center"),
                                   ("cap", "السعة", 70, "center"),
                                   ("occ", "المشغول", 80, "center"),
                                   ("status", "الحالة", 140, "center")):
            tree.heading(key, text=text)
            tree.column(key, width=w, anchor=anc)
        tree.tag_configure("over", background="#FBEBEA")
        tree.tag_configure("full", background="#E8F6EC")
        tree.tag_configure("partial", background="#FBF0DC")
        tree.pack(fill=BOTH, expand=True)

        full = over = free_beds = 0
        for hotel, cap, number, occ in rooms:
            n = len(occ)
            cap = cap or n
            if n > cap:
                over += 1; status = f"تجاوز (+{n - cap})"; tag = "over"
            elif n == cap:
                full += 1; status = "مكتملة"; tag = "full"
            else:
                free_beds += (cap - n); status = f"شاغر {cap - n}"; tag = "partial"
            tree.insert("", "end", values=(hotel or "—", number, cap, n, status),
                        tags=(tag,))
        self._summary.configure(text=rtl(
            f"غرف: {len(rooms)}    •    مكتملة: {full}    •    متجاوِزة: {over}"
            f"    •    أسرّة شاغرة: {free_beds}    •    بلا غرفة: {len(unplaced)}"))

        ttk.Button(outer, text="إغلاق", style="Ghost.TButton",
                   command=self.destroy).pack(anchor="w", pady=(10, 0))
        self.bind("<Escape>", lambda _e: self.destroy())
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 5
        self.geometry(f"+{x}+{y}")


class CheckInDialog(Toplevel):
    """تسجيل حضور الحجّاج بمسح رمز QR للبطاقة أو إدخال الجواز/الرقم المرجعي.

    قارئات QR/الباركود تعمل كلوحة مفاتيح (تكتب الرمز ثم Enter)، فيكفي حقل نصّي.
    """

    STAGES = ("المطار", "الفندق", "الباص", "العودة")

    def __init__(self, parent, get_records, on_change, on_export=None) -> None:
        super().__init__(parent)
        self.get_records = get_records
        self.on_change = on_change
        self.on_export = on_export
        self.title("🎫 تسجيل الحضور")
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()

        outer = ttk.Frame(self, padding=16)
        outer.pack(fill=BOTH, expand=True)

        top = ttk.Frame(outer)
        top.pack(fill=X)
        ttk.Label(top, text="المرحلة:", font=(_FSB, 11),
                  foreground=TEXT).pack(side=RIGHT, padx=(0, 8))
        self._stage = StringVar(value=self.STAGES[0])
        cb = ttk.Combobox(top, textvariable=self._stage, values=self.STAGES,
                          state="readonly", width=12, font=(_FSB, 11))
        cb.pack(side=RIGHT)
        cb.bind("<<ComboboxSelected>>", lambda _e: self._refresh())

        ttk.Label(outer, text=rtl("المسح أو الإدخال:"), font=(_FSB, 11),
                  foreground=TEXT).pack(anchor="e", pady=(12, 2))
        ttk.Label(outer, foreground=MUTED, font=(_FUI, 9), justify="right",
                  wraplength=380,
                  text=rtl("امسح رمز QR على بطاقة الحاج (بقارئ USB)، أو اكتب "
                           "رقم الجواز أو الرقم المرجعي أو اسم الحاج، ثم اضغط "
                           "Enter. البطاقات تُطبع من: التقارير ← بطاقات الحجّاج.")
                  ).pack(anchor="e", pady=(0, 4))
        self._scan = StringVar()
        entry = ttk.Entry(outer, textvariable=self._scan, width=34,
                          justify="center", font=(_FSB, 13))
        entry.pack(fill=X)
        entry.bind("<Return>", lambda _e: self._submit())
        entry.focus_set()
        self._entry = entry

        self._result = ttk.Label(outer, font=(_FSB, 12), foreground=BRONZE)
        self._result.pack(anchor="e", pady=(10, 4))
        self._counts = ttk.Label(outer, font=(_FSB, 11), foreground=TEXT)
        self._counts.pack(anchor="e")

        ttk.Label(outer, text=rtl("الغائبون عن هذه المرحلة:"), font=(_FUI, 10),
                  foreground=MUTED).pack(anchor="e", pady=(10, 2))
        self.absent = ttk.Treeview(outer, columns=("name", "phone"),
                                   show="headings", height=8)
        self.absent.heading("name", text="اسم الحاج")
        self.absent.column("name", width=220, anchor="e")
        self.absent.heading("phone", text="الهاتف")
        self.absent.column("phone", width=130, anchor="center")
        self.absent.pack(fill=BOTH, expand=True)

        foot = ttk.Frame(outer)
        foot.pack(fill=X, pady=(10, 0))
        if self.on_export is not None:
            ttk.Button(foot, text=rtl("📄 تصدير تقرير الحضور"),
                       style="Act.TButton",
                       command=self.on_export).pack(side=RIGHT, padx=3)
        ttk.Button(foot, text="إغلاق", style="Ghost.TButton",
                   command=self.destroy).pack(side=LEFT, padx=3)
        self.bind("<Escape>", lambda _e: self.destroy())
        self._refresh()
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 4
        self.geometry(f"+{x}+{y}")

    def _find(self, text: str):
        """يطابق المُدخَل: رقم الجواز أو الرقم المرجعي أو اسم الحاج، أو نصّ QR."""
        import re
        t = str(text or "").strip()
        if not t:
            return None
        recs = self.get_records()
        # 1) رقم الجواز/الرقم المرجعي (يُستخرج الجواز من نصّ رمز البطاقة إن وُجد)
        m = re.search(r"الجواز[:\s]+([A-Za-z0-9]+)", t)
        key = (m.group(1) if m else t).strip().upper()
        for i, r in enumerate(recs):
            if str(r.passport_number or "").strip().upper() == key:
                return i
            if str(r.reference_number or "").strip().upper() == key:
                return i
        # 2) بالاسم (كتابة يدوية): مطابقة تامّة ثم احتواء إن كان النصّ ذا معنى
        for i, r in enumerate(recs):
            if t == str(r.full_name_ar or "").strip():
                return i
        if len(t) >= 3:
            low = t.lower()
            for i, r in enumerate(recs):
                blob = f"{r.full_name_ar or ''} {r.full_name_en or ''}".lower()
                if low in blob:
                    return i
        return None

    def _submit(self) -> None:
        text = self._scan.get()
        self._scan.set("")
        if not text.strip():
            return
        idx = self._find(text)
        if idx is None:
            self._result.configure(text=rtl(f"✗ لم يُعثر على: {text.strip()}"),
                                   foreground=DANGER)
            return
        rec = self.get_records()[idx]
        stage = self._stage.get()
        from datetime import datetime
        already = stage in (rec.checkins or {})
        if not isinstance(rec.checkins, dict):
            rec.checkins = {}
        rec.checkins[stage] = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.on_change()
        name = rec.full_name_ar or rec.full_name_en or rec.passport_number or "—"
        state = "مسجّل مسبقاً" if already else "سُجّل حضوره الآن"
        self._result.configure(text=rtl(f"✓ {name} — {state}"), foreground=BRONZE)
        self._refresh()

    def _refresh(self) -> None:
        recs = self.get_records()
        stage = self._stage.get()
        present = [r for r in recs if stage in (r.checkins or {})]
        absent = [r for r in recs if stage not in (r.checkins or {})]
        self._counts.configure(text=rtl(
            f"حضر: {len(present)}    •    غاب: {len(absent)}    •    "
            f"الإجمالي: {len(recs)}"))
        self.absent.delete(*self.absent.get_children())
        for r in absent:
            name = r.full_name_ar or r.full_name_en or r.passport_number or "—"
            self.absent.insert("", "end", values=(name, r.phone or ""))
        self._entry.focus_set()


class GroupsDialog(Toplevel):
    """المجموعات والمرشدون: إسناد مرشد/مطوّف وهاتف لكل مجموعة، مع عدد أفرادها."""

    def __init__(self, parent, app) -> None:
        super().__init__(parent)
        self.app = app
        self.title("👥 المجموعات والمرشدون")
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()

        saved = dict(app._settings.get("groups", {}))
        counts: dict[str, int] = {}
        for r in app.records:
            name = str(getattr(r, "group", "") or "").strip()
            if name:
                counts[name] = counts.get(name, 0) + 1
        names = sorted(set(counts) | set(saved))

        outer = ttk.Frame(self, padding=16)
        outer.pack(fill=BOTH, expand=True)
        ttk.Label(outer, text=rtl("👥  المجموعات والمرشدون"), font=(_FSB, 14),
                  foreground=TEXT).pack(anchor="e")
        ttk.Label(outer, foreground=MUTED, font=(_FUI, 9), justify="right",
                  text=rtl("لكل مجموعة مرشد/مطوّف وهاتف. تُحدَّد «المجموعة» في "
                           "سجلّ كل حاج.")).pack(anchor="e", pady=(4, 12))

        self._vars: dict[str, tuple] = {}
        if not names:
            ttk.Label(outer, foreground=MUTED, font=(_FUI, 10),
                      text=rtl("لا مجموعات بعد — عيّن حقل «المجموعة» في سجلّات "
                               "الحجّاج أولاً.")).pack(anchor="e", pady=8)
        else:
            grid = ttk.Frame(outer)
            grid.pack(fill=BOTH, expand=True)
            for col, head in enumerate(("المجموعة", "المرشد/المطوّف", "الهاتف")):
                ttk.Label(grid, text=head, font=(_FSB, 10), foreground=TEXT
                          ).grid(row=0, column=col, padx=6, pady=(0, 6), sticky="e")
            for i, name in enumerate(names, start=1):
                info = saved.get(name, {})
                gv = StringVar(value=str(info.get("guide", "")))
                pv = StringVar(value=str(info.get("phone", "")))
                self._vars[name] = (gv, pv)
                label = f"{name}  ({counts.get(name, 0)})"
                ttk.Label(grid, text=label, foreground=TEXT).grid(
                    row=i, column=0, padx=6, pady=3, sticky="e")
                ttk.Entry(grid, textvariable=gv, width=24, justify="right").grid(
                    row=i, column=1, padx=6, pady=3)
                ttk.Entry(grid, textvariable=pv, width=16, justify="center").grid(
                    row=i, column=2, padx=6, pady=3)

        btns = ttk.Frame(outer)
        btns.pack(fill=X, pady=(14, 0))
        if names:
            ttk.Button(btns, text=rtl("💾 حفظ"), style="Primary.TButton",
                       command=self._save).pack(side=RIGHT, padx=3)
        ttk.Button(btns, text="إغلاق", style="Ghost.TButton",
                   command=self.destroy).pack(side=LEFT, padx=3)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 3
        self.geometry(f"+{x}+{y}")

    def _save(self) -> None:
        data = {name: {"guide": gv.get().strip(), "phone": pv.get().strip()}
                for name, (gv, pv) in self._vars.items()}
        self.app._settings["groups"] = data
        try:
            save_settings(self.app._settings)
        except OSError:
            pass
        self.app._audit("تعديل المجموعات", f"{len(data)} مجموعة")
        self.app.set_status("حُفظت بيانات المجموعات والمرشدين", ok=True)
        self.destroy()


class NewSeasonDialog(Toplevel):
    """تأكيد بدء موسم جديد: اختيار السنة الهجرية والموافقة على الأرشفة."""

    def __init__(self, parent, current_year: str, pilgrim_count: int) -> None:
        super().__init__(parent)
        self.confirmed = False
        self.year = current_year
        self.title("🌙 بدء موسم جديد")
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)

        outer = ttk.Frame(self, padding=22)
        outer.pack(fill=BOTH, expand=True)
        ttk.Label(outer, text=rtl("🌙  بدء موسم حجّ جديد"), font=(_FSB, 15),
                  foreground=TEXT).pack(anchor="e")
        ttk.Label(
            outer, wraplength=390, justify="right", font=(_FUI, 10),
            foreground=MUTED,
            text=rtl("اختر السنة الهجرية للموسم الجديد. يُحفظ كشف الموسم الحالي "
                     "كنسخة احتياطية ثم يُفرَّغ لتبدأ بحجّاج جدد، ثم تُضبط برامج "
                     "الحملة."),
        ).pack(anchor="e", pady=(6, 14))

        row = ttk.Frame(outer)
        row.pack(fill=X, pady=(0, 10))
        ttk.Label(row, text="السنة الهجرية:", font=(_FSB, 11),
                  foreground=TEXT).pack(side=RIGHT, padx=(0, 8))
        try:
            nxt = str(int(current_year) + 1)
        except (TypeError, ValueError):
            nxt = current_year
        default = nxt if nxt in HIJRI_YEARS else current_year
        self._year = StringVar(value=default)
        ttk.Combobox(row, textvariable=self._year, state="readonly", width=8,
                     values=HIJRI_YEARS, font=(_FSB, 12)).pack(side=RIGHT)

        if pilgrim_count:
            ttk.Label(
                outer, wraplength=390, justify="right", font=(_FUI, 9),
                foreground=AMBER_FG,
                text=rtl(f"⚠ سيُؤرشف {pilgrim_count} حاجّاً من الموسم الحالي "
                         "(يمكن استعادتهم لاحقاً من «استعادة نسخة احتياطية»)."),
            ).pack(anchor="e", pady=(0, 10))

        self._ok = tk.BooleanVar(value=(pilgrim_count == 0))
        ttk.Checkbutton(
            outer, variable=self._ok, command=self._toggle,
            text=rtl("أفهم أنه ستُؤرشف بيانات الموسم الحالي ويُفرَّغ الكشف"),
        ).pack(anchor="e", pady=(0, 14))

        btns = ttk.Frame(outer)
        btns.pack(fill=X)
        self._start = ttk.Button(btns, text=rtl("🌙  بدء الموسم"),
                                 style="Primary.TButton", command=self._confirm)
        self._start.pack(side=RIGHT, padx=4)
        if pilgrim_count:
            self._start.state(["disabled"])
        ttk.Button(btns, text="إلغاء", style="Ghost.TButton",
                   command=self.destroy).pack(side=RIGHT, padx=4)

        self.bind("<Escape>", lambda _e: self.destroy())
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 3
        self.geometry(f"+{x}+{y}")

    def _toggle(self) -> None:
        self._start.state(["!disabled"] if self._ok.get() else ["disabled"])

    def _confirm(self) -> None:
        if not self._ok.get():
            return
        self.year = self._year.get()
        self.confirmed = True
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
        ttk.Label(top, text="البرنامج:", font=(_FSB, 11),
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
            ttk.Label(body, text=gtitle, font=(_FSB, 11),
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


class WhatsAppDialog(Toplevel):
    """رسالة واتساب جماعية عبر روابط wa.me — يفتح لكلّ حاجٍّ محادثة مملوءة.

    لا يُرسل تلقائياً (يضغط المستخدم «إرسال» في واتساب)، فلا يخالف الشروط.
    """

    def __init__(self, parent, records, app) -> None:
        super().__init__(parent)
        self.app = app
        self.records = records
        self.title("📱 رسالة واتساب جماعية")
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)

        from .whatsapp import DEFAULT_TEMPLATE, PLACEHOLDERS, TEMPLATES

        outer = ttk.Frame(self, padding=16)
        outer.pack(fill=BOTH, expand=True)
        ttk.Label(outer, text=f"إرسال إلى {len(records)} حاجاً محدَّداً",
                  font=(_FSB, 12), foreground=TEXT).pack(anchor="e")
        ttk.Label(outer, foreground=MUTED, font=(_FUI, 9),
                  text="يفتح لكلٍّ محادثة واتساب برسالة جاهزة — تضغط «إرسال» "
                       "بنفسك.").pack(anchor="e", pady=(0, 8))

        # قالب جاهز
        self._templates = TEMPLATES
        trow = ttk.Frame(outer)
        trow.pack(fill=X, pady=(0, 6))
        ttk.Label(trow, text="قالب جاهز:", foreground=TEXT).pack(side=RIGHT, padx=(6, 0))
        self.v_tpl = StringVar(value=next(iter(TEMPLATES)))
        tcb = ttk.Combobox(trow, textvariable=self.v_tpl, state="readonly",
                           width=22, values=list(TEMPLATES.keys()))
        tcb.pack(side=RIGHT)
        tcb.bind("<<ComboboxSelected>>", lambda _e: self._load_template())

        top = ttk.Frame(outer)
        top.pack(fill=X, pady=(0, 6))
        self.v_cc = StringVar(value=app._whatsapp_cc())
        ttk.Label(top, text="رمز الدولة (للأرقام التي تبدأ بـ 0):",
                  foreground=TEXT).pack(side=RIGHT, padx=(6, 0))
        cc = ttk.Entry(top, textvariable=self.v_cc, width=8, justify="center")
        cc.pack(side=RIGHT)
        cc.bind("<KeyRelease>", lambda _e: self._rebuild())

        ttk.Label(outer, text="الرسالة:", foreground=TEXT).pack(anchor="e")
        self.txt = tk.Text(outer, width=62, height=5, wrap="word",
                           font=(_FUI, 10))
        self.txt.pack(fill=X)
        self.txt.insert("1.0", DEFAULT_TEMPLATE)
        ttk.Label(outer, foreground=MUTED, font=(_FUI, 9),
                  text="عناصر نائبة تُستبدَل لكل حاج: " + "  ".join(PLACEHOLDERS)
                  ).pack(anchor="e", pady=(2, 8))

        box = ttk.Frame(outer)
        box.pack(fill=BOTH, expand=True)
        sb = ttk.Scrollbar(box, orient="vertical")
        sb.pack(side=RIGHT, fill=Y)
        self.tree = ttk.Treeview(box, columns=("phone", "status"),
                                 show="tree headings", height=8,
                                 yscrollcommand=sb.set)
        self.tree.heading("#0", text="الحاج")
        self.tree.heading("phone", text="الرقم الدولي")
        self.tree.heading("status", text="الحالة")
        self.tree.column("#0", width=250, anchor="e")
        self.tree.column("phone", width=150, anchor="center")
        self.tree.column("status", width=90, anchor="center")
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        sb.config(command=self.tree.yview)
        self.tree.tag_configure("bad", foreground=DANGER)

        btns = ttk.Frame(outer)
        btns.pack(anchor="e", pady=(10, 0))
        self.btn_next = ttk.Button(btns, text="↪ فتح التالي",
                                   style="Primary.TButton", command=self._open_next)
        self.btn_next.pack(side=RIGHT, padx=4)
        ttk.Button(btns, text="فتح الكل", style="Act.TButton",
                   command=self._open_all).pack(side=RIGHT, padx=4)
        ttk.Button(btns, text="إغلاق", style="Act.TButton",
                   command=self.destroy).pack(side=RIGHT)
        self.bind("<Escape>", lambda _e: self.destroy())

        self._pos = 0
        self._order: list = []
        self._rebuild()

        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 6
        self.geometry(f"+{x}+{y}")

    def _load_template(self) -> None:
        """يستبدل نصّ الرسالة بالقالب المختار."""
        text = self._templates.get(self.v_tpl.get(), "")
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", text)
        self._rebuild()

    def _rebuild(self) -> None:
        from .whatsapp import to_intl
        self.tree.delete(*self.tree.get_children())
        self._pos = 0
        self._order = []
        cc = self.v_cc.get()
        for rec in self.records:
            name = rec.full_name_ar or rec.full_name_en or "—"
            num = to_intl(rec.phone, cc)
            if num:
                self.tree.insert("", END, text=name, values=("+" + num, "جاهز"))
                self._order.append(rec)
            else:
                self.tree.insert("", END, text=name,
                                 values=(str(rec.phone or "—"), "بلا رقم صالح"),
                                 tags=("bad",))
        self._update_next()

    def _update_next(self) -> None:
        n = len(self._order)
        if not n:
            self.btn_next.configure(text="لا أرقام صالحة", state="disabled")
        elif self._pos >= n:
            self.btn_next.configure(text="اكتمل ✓", state="disabled")
        else:
            self.btn_next.configure(text=f"↪ فتح التالي ({self._pos + 1}/{n})",
                                    state="normal")

    def _open(self, rec) -> None:
        import webbrowser
        from .whatsapp import render_message, wa_link
        msg = render_message(self.txt.get("1.0", "end").strip(), rec)
        url = wa_link(rec.phone, msg, self.v_cc.get())
        if url:
            webbrowser.open(url)

    def _open_next(self) -> None:
        self.app._save_whatsapp_cc(self.v_cc.get())
        if self._pos < len(self._order):
            self._open(self._order[self._pos])
            self._pos += 1
            self._update_next()

    def _open_all(self) -> None:
        n = len(self._order)
        if not n:
            return
        if n > 8 and not messagebox.askyesno(
                "فتح الكل", f"سيُفتح {n} محادثة تِباعاً. متابعة؟", parent=self):
            return
        self.app._save_whatsapp_cc(self.v_cc.get())
        for i, rec in enumerate(self._order):
            self.after(i * 400, lambda r=rec: self._open(r))   # فجوة بين الفتحات
        self._pos = n
        self._update_next()


class BulkDocsDialog(Toplevel):
    """اختيار نوع المستند للتوليد الجماعي. يضبط self.kind أو None عند الإلغاء."""

    def __init__(self, parent, count: int) -> None:
        super().__init__(parent)
        self.kind: str | None = None
        self.title("توليد جماعي للمستندات")
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)

        outer = ttk.Frame(self, padding=18)
        outer.pack(fill=BOTH, expand=True)
        ttk.Label(outer, text=f"سيُنشأ مستند لكل حاج من {count} المعروضين،",
                  font=(_FSB, 11), foreground=TEXT).pack(anchor="e")
        ttk.Label(outer, text="مجموعةً في ملف PDF واحد للطباعة.",
                  foreground=MUTED, font=(_FUI, 9)).pack(anchor="e",
                                                               pady=(0, 10))

        self._choice = StringVar(value="receipt")
        for value, label in (("receipt", "🧾  سندات القبض"),
                             ("invoice", "🧾  فواتير ضريبية"),
                             ("einvoice", "💳  فواتير إلكترونية (PEPPOL)"),
                             ("contract", "📜  عقود خدمات الحج")):
            ttk.Radiobutton(outer, text=label, value=value,
                            variable=self._choice).pack(anchor="e", pady=2)

        btns = ttk.Frame(outer)
        btns.pack(anchor="e", pady=(14, 0))
        ttk.Button(btns, text="توليد ومعاينة", style="Act.TButton",
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


class RoomingScopeDialog(Toplevel):
    """اختيار الفندق ونوع الغرفة قبل عرض/طباعة كشف التسكين.

    يضبط ``self.result`` = (الفندق أو None، فئة الغرفة أو None)، أو يبقيه
    None عند الإلغاء.
    """

    _ALL = "الكل"

    def __init__(self, parent, records) -> None:
        super().__init__(parent)
        self.result = None
        self.title("نطاق كشف التسكين")
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)

        from .rooming import ROOM_CATEGORIES, room_category
        hotels = sorted({str(r.hotel or "").strip() for r in records
                         if str(r.hotel or "").strip()})
        cats = [c for c in ROOM_CATEGORIES
                if any(room_category(r.room_type) == c for r in records)]

        outer = ttk.Frame(self, padding=18)
        outer.pack(fill=BOTH, expand=True)
        ttk.Label(outer, text="اختر نطاق كشف التسكين:",
                  font=(_FSB, 11), foreground=TEXT,
                  background=BG).grid(row=0, column=0, columnspan=2, sticky="e",
                                      pady=(0, 12))

        self.v_hotel = StringVar(value=self._ALL)
        self.v_cat = StringVar(value=self._ALL)
        ttk.Label(outer, text="الفندق:", foreground=TEXT, background=BG).grid(
            row=1, column=1, sticky="e", padx=(10, 0), pady=5)
        ttk.Combobox(outer, textvariable=self.v_hotel, state="readonly",
                     width=24, values=[self._ALL, *hotels]).grid(
            row=1, column=0, sticky="ew", pady=5)
        ttk.Label(outer, text="نوع الغرفة:", foreground=TEXT, background=BG).grid(
            row=2, column=1, sticky="e", padx=(10, 0), pady=5)
        ttk.Combobox(outer, textvariable=self.v_cat, state="readonly",
                     width=24, values=[self._ALL, *cats]).grid(
            row=2, column=0, sticky="ew", pady=5)

        ttk.Label(outer, foreground=MUTED, font=(_FUI, 9),
                  text="«الكل» يشمل جميع الفنادق/الأنواع.").grid(
            row=3, column=0, columnspan=2, sticky="e", pady=(6, 12))

        btns = ttk.Frame(outer)
        btns.grid(row=4, column=0, columnspan=2, sticky="e")
        ttk.Button(btns, text="عرض / طباعة", style="Act.TButton",
                   command=self._ok).pack(side=RIGHT, padx=4)
        ttk.Button(btns, text="إلغاء", style="Act.TButton",
                   command=self.destroy).pack(side=RIGHT)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Return>", lambda _e: self._ok())

        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 3
        self.geometry(f"+{x}+{y}")

    def _ok(self) -> None:
        h = self.v_hotel.get()
        c = self.v_cat.get()
        self.result = (None if h == self._ALL else h,
                       None if c == self._ALL else c)
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
                  font=(_FSB, 11), foreground=TEXT).pack(
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
                  font=(_FSB, 12), foreground=TEXT).grid(
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
                           font=(_FUI, 10))
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
            open_in_viewer(str(path))            # يفتح في العارض الافتراضي للمعاينة
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
                  font=(_FSB, 12), foreground=TEXT).grid(
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
                           font=(_FUI, 10))
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
            open_in_viewer(str(path))
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
            open_in_viewer(str(path))
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
                  font=(_FSB, 12), foreground=TEXT).grid(
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
                           font=(_FUI, 10))
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
            open_in_viewer(str(path))
        except Exception as exc:
            messagebox.showerror("تعذّر الفتح", str(exc), parent=self)


class EditDialog(Toplevel):
    """نافذة تعديل بيانات حاج واحد، موزّعة على تبويبات حسب نوع البيانات."""

    # التبويبات ومحتواها. الحقول غير المذكورة تُضاف إلى "أخرى".
    TABS: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("بيانات الحاج", ("family_number", "reference_number", "full_name_ar",
                          "full_name_en", "phone", "program", "group", "status",
                          "mahram_name", "mahram_relation")),
        ("الجواز", ("passport_number", "nationality_ar", "sex", "birth_date",
                    "expiry_date")),
        ("التأشيرة والتصريح", ("visa_number", "visa_status", "permit_status",
                               "masar_number")),
        ("السفر", ("airline", "flight_number", "travel_class", "pnr",
                   "arrival_date", "arrival_time", "departure_date",
                   "departure_time", "transport")),
        ("الإقامة والخدمات", ("hotel", "room_type", "room_number",
                              "executive_service", "wheelchair", "hady")),
        ("الصحة والطوارئ", ("blood_type", "medical_conditions", "medications",
                            "vaccination", "insurance", "emergency_name",
                            "emergency_phone", "emergency_relation")),
        ("المالية", ("program_value", "paid_amount")),
        ("ملاحظات", ("notes", "staff")),
    )

    # تبويبات وضع العمرة — السفر والإقامة والخدمات تؤخذ من البرنامج (لا تُعرض)،
    # ولا حقول للحج ولا للصحة والطوارئ.
    UMRAH_TABS: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("بيانات المعتمر", ("family_number", "reference_number", "full_name_ar",
                            "full_name_en", "phone", "status",
                            "mahram_name", "mahram_relation")),
        ("الجواز", ("passport_number", "nationality_ar", "sex", "birth_date",
                    "expiry_date")),
        ("الإقامة والحجز", ("room_type", "room_number", "transport")),
        ("المالية", ("program_value", "paid_amount", "payment_date",
                     "payment_method")),
        ("ملاحظات", ("notes", "staff")),
    )
    # حقول تُستبعد تماماً من نافذة العمرة: حقول الحج + السفر/الفندق (تؤخذ من
    # البرنامج) + الصحة والطوارئ (أُلغيت).
    UMRAH_DROP = frozenset({
        "program", "group", "hady", "executive_service", "wheelchair",
        "visa_number", "visa_status", "permit_status", "masar_number",
        "airline", "flight_number", "travel_class", "pnr",
        "arrival_date", "arrival_time", "departure_date", "departure_time",
        "hotel",
        "blood_type", "medical_conditions", "medications", "vaccination",
        "insurance", "emergency_name", "emergency_phone", "emergency_relation",
    })
    # حقول العمرة الإضافية (ليست في FIELDS) تُبنى كحقول اصطناعية عند اللزوم
    UMRAH_EXTRA = (("payment_date", "تاريخ الدفع"), ("payment_method", "طريقة الدفع"))

    # حقول ذات قيم محدّدة تُعرض قائمةً منسدلة
    CHOICE_FIELDS = {
        "status": ("", "نشط", "ملغى", "قائمة انتظار"),
        "sex": ("", "ذكر", "أنثى"),
        "wheelchair": ("", "نعم"),
        "payment_method": ("", "نقدي", "تحويل بنكي", "بطاقة", "شيك", "رابط دفع"),
    }

    def __init__(self, parent, record: PassportData, on_save, *,
                 title: str = "تعديل بيانات الحاج",
                 save_text: str = "حفظ", session=None, umrah: bool = False,
                 trip=None) -> None:
        super().__init__(parent)
        self.record = record
        self.on_save = on_save
        self.session = session
        self._umrah = umrah
        self._trip = trip
        self.vars: dict[str, StringVar] = {}
        # عمليات الصور المؤجّلة حتى الحفظ: النوع -> مسار جديد أو "DELETE" أو None
        self._pending_images: dict[str, str | None] = {}
        self._thumb_refs: dict[str, object] = {}    # مراجع لمنع حذف الصور من الذاكرة

        self.title(title)
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()

        outer = ttk.Frame(self, padding=14)
        outer.pack(fill=BOTH, expand=True)

        notebook = ttk.Notebook(outer)
        notebook.pack(fill=BOTH, expand=True)

        tabs = self.UMRAH_TABS if umrah else self.TABS
        drop = self.UMRAH_DROP if umrah else frozenset()
        editable = [f for f in EDITABLE if f.key not in drop]
        if umrah:
            from .fields import Field as _Field
            editable += [_Field(k, lbl, 13, True, False)
                         for k, lbl in self.UMRAH_EXTRA]
        by_key = {f.key: f for f in editable}
        placed: set[str] = set()

        for tab_title, keys in tabs:
            fields = [by_key[k] for k in keys if k in by_key]
            if not fields:
                continue
            placed.update(f.key for f in fields)
            notebook.add(self._make_tab(notebook, fields), text=tab_title)

        leftover = [f for f in editable if f.key not in placed]
        if leftover:
            notebook.add(self._make_tab(notebook, leftover), text="أخرى")

        # وضع العمرة: تبويب الخدمات (اختيار وتسعير خدمات المعتمر)
        self._svc_widgets = {}
        if umrah and trip is not None and getattr(trip, "services", None):
            notebook.add(self._build_umrah_services_tab(notebook), text="الخدمات")

        notebook.add(self._build_images_tab(notebook), text="الصور")

        # المتبقي محسوب تلقائياً، فنعرضه للقراءة فقط
        self.remaining = ttk.Label(
            outer, font=(_FSB, 10), foreground=TEXT
        )
        self.remaining.pack(anchor="e", pady=(10, 0))
        self._update_remaining()
        for key in ("program_value", "paid_amount"):
            if key in self.vars:
                self.vars[key].trace_add("write", lambda *_a: self._update_remaining())

        if record.warnings:
            ttk.Label(
                outer, text="⚠ " + " | ".join(record.warnings), foreground="#B26A00",
                font=(_FUI, 9), wraplength=640, justify="right",
            ).pack(anchor="e", pady=(8, 0))

        btns = ttk.Frame(outer)
        btns.pack(anchor="e", pady=(14, 0))
        ttk.Button(btns, text=save_text, command=self._save,
                   style="Act.TButton").pack(side=RIGHT, padx=4)
        ttk.Button(btns, text="إلغاء", command=self.destroy,
                   style="Act.TButton").pack(side=RIGHT)

        self.bind("<Return>", lambda _e: self._save())
        self.bind("<Escape>", lambda _e: self.destroy())
        enable_minmax(self)              # أزرار تصغير/تكبير للنافذة المنبثقة

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
            if self._umrah:            # مسمّيات العمرة بدل الحج
                label = label.replace("الحاج", "المعتمر").replace("حاج", "معتمر")
            if f.key in MRZ_FILLED:
                label += " *"          # نجمة: مقروء من الجواز
            ttk.Label(frame, text=label, font=(_FUI, 10)).grid(
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
            if f.key in self.CHOICE_FIELDS:
                ttk.Combobox(frame, textvariable=var, state="readonly", width=24,
                             justify="center",
                             values=list(self.CHOICE_FIELDS[f.key])).grid(
                    row=row, column=col, sticky="w", pady=5)
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
        from .images import KINDS, KIND_LABELS, PASSPORT
        # العمرة: صورة الجواز فقط (الصورة الشخصية تؤخذ منه، ولا تصريح سعودي)
        kinds = (PASSPORT,) if self._umrah else KINDS
        for index, kind in enumerate(kinds):
            row, base = divmod(index, 2)
            col = 1 - base                    # RTL: أول صورة أقصى اليمين
            box = ttk.Frame(frame, padding=6)
            box.grid(row=row, column=col, padx=10, pady=4, sticky="n")
            ttk.Label(box, text=KIND_LABELS[kind], font=(_FSB, 10),
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
        if self._umrah:
            ttk.Label(frame, text=rtl("الصورة الشخصية تُؤخذ من الجواز تلقائياً."),
                      font=(_FUI, 9), foreground=MUTED).grid(
                row=1, column=0, columnspan=2, pady=(10, 0), sticky="e")
        return frame

    def _build_umrah_services_tab(self, parent) -> ttk.Frame:
        """تبويب خدمات المعتمر (وضع العمرة): اختيار الخدمات وتسعيرها لكل معتمر.

        السعر الأساس = سعر الغرفة، والإجمالي = الأساس + الخدمات المختارة.
        """
        frame = ttk.Frame(parent, padding=14)
        existing = {s.get("name", ""): str(s.get("price", ""))
                    for s in (self.record.umrah_services or [])}
        exist_sum = sum(parse_amount(p) or 0 for p in existing.values())
        pv = parse_amount(self.vars.get("program_value", StringVar()).get()) \
            if "program_value" in self.vars else parse_amount(self.record.program_value)
        if str(self.record.room_value or "").strip():
            base = parse_amount(self.record.room_value) or 0.0
        else:
            base = max(0.0, (pv or 0.0) - exist_sum)
        self._svc_base = base

        ttk.Label(frame, text=rtl(f"سعر الغرفة (الأساس): {format_amount(base)}"),
                  font=(_FSB, 10), foreground=ACCENT).grid(
            row=0, column=0, columnspan=3, sticky="e", pady=(0, 2))
        ttk.Label(frame, text=rtl("اختر خدمات المعتمر وسعّرها (درهم):"),
                  font=(_FUI, 10), foreground=TEXT).grid(
            row=1, column=0, columnspan=3, sticky="e", pady=(0, 8))

        catalog = [s.get("name", "") for s in (self._trip.services or [])
                   if s.get("name")]
        default_price = {s.get("name", ""): str(s.get("price", ""))
                         for s in (self._trip.services or [])}
        for i, name in enumerate(catalog):
            cb = tk.BooleanVar(value=name in existing)
            pvar = StringVar(value=existing.get(name, default_price.get(name, "")))
            self._svc_widgets[name] = (cb, pvar)
            ttk.Checkbutton(frame, text=rtl(name), variable=cb,
                            command=self._recalc_services).grid(
                row=i + 2, column=0, sticky="e", padx=(6, 4), pady=3)
            ttk.Entry(frame, textvariable=pvar, width=10, justify="center").grid(
                row=i + 2, column=1, sticky="w", pady=3)
            pvar.trace_add("write", lambda *_a: self._recalc_services())

        self._svc_total_lbl = ttk.Label(frame, text="", font=(_FSB, 11),
                                        foreground=ACCENT)
        self._svc_total_lbl.grid(row=len(catalog) + 2, column=0, columnspan=3,
                                 sticky="e", pady=(10, 0))
        self._recalc_services()
        return frame

    def _recalc_services(self) -> None:
        """يحدّث إجمالي الخدمات وقيمة البرنامج (الأساس + الخدمات)."""
        if not getattr(self, "_svc_widgets", None):
            return
        total = 0.0
        for _name, (cb, pvar) in self._svc_widgets.items():
            if cb.get():
                total += parse_amount(pvar.get()) or 0.0
        grand = getattr(self, "_svc_base", 0.0) + total
        if hasattr(self, "_svc_total_lbl"):
            self._svc_total_lbl.configure(text=rtl(
                f"إجمالي الخدمات: {format_amount(total)}    الإجمالي: "
                f"{format_amount(grand)}"))
        if "program_value" in self.vars:
            self.vars["program_value"].set(format_amount(grand))

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

        # احتساب قيمة البرنامج تلقائياً إن اختير برنامج ولم تُدخَل قيمة يدوياً
        if (str(self.record.program or "").strip()
                and not str(self.record.program_value or "").strip()):
            from .fields import format_amount as _fmt
            from .programs import load_programs, program_by_name, program_cost
            from .storage import load_settings as _ls
            prog = program_by_name(load_programs(_ls()),
                                   self.record.program.strip())
            if prog is not None:
                total, _br = program_cost(
                    prog, room_type=self.record.room_type,
                    wheelchair=self.record.wheelchair, hady=self.record.hady,
                    executive_service=self.record.executive_service,
                    travel_class=self.record.travel_class,
                    transport=self.record.transport)
                if total:
                    self.record.program_value = _fmt(total)

        # وضع العمرة: خزّن خدمات المعتمر وسعر الغرفة الأساس (القيمة = الأساس + الخدمات)
        if getattr(self, "_svc_widgets", None):
            chosen = []
            for name, (cb, pvar) in self._svc_widgets.items():
                if cb.get():
                    chosen.append({"name": name,
                                   "price": format_amount(parse_amount(pvar.get()) or 0)})
            self.record.umrah_services = chosen
            self.record.room_value = format_amount(getattr(self, "_svc_base", 0.0))

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
        tk.Label(frame, text=app_mode.label("splash"), bg=BG, fg=ACCENT,
                 font=(_FSB, 16)).pack(pady=(12, 0))
        from . import __version__
        release = app_mode.label("release_name")   # ميسّر الحج / ميسّر العمرة
        vtext = f"الإصدار {__version__}"
        if release:
            vtext += f"  «{release}»"
        tk.Label(frame, text=vtext, bg=BG, fg=BRONZE,
                 font=(_FUI, 9)).pack(pady=(3, 0))
        import random
        _tips = [
            "نصيحة: اضغط Ctrl+K لفتح البحث السريع.",
            "نصيحة: F1 يعرض اختصارات لوحة المفاتيح.",
            "نصيحة: بطاقات QR تُسرّع تسجيل الحضور.",
            "نصيحة: احفظ توليفة فلاترك من «⭐ فلاتر محفوظة».",
        ]
        tk.Label(frame, text=random.choice(_tips), bg=BG, fg=MUTED,
                 font=(_FUI, 9)).pack(pady=(8, 0))
        tk.Label(frame, text="جارٍ التحميل…", bg=BG, fg=MUTED,
                 font=(_FUI, 10)).pack(pady=(4, 0))
        splash.update_idletasks()
        w, h = splash.winfo_width(), splash.winfo_height()
        sw, sh = splash.winfo_screenwidth(), splash.winfo_screenheight()
        splash.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")
        splash.update()
        return splash
    except Exception:
        return None


# التشفير مُفعَّل: يطلب البرنامج الدخول (حساب MHU) ويشفّر ملف البيانات.
# للعودة إلى وضع البناء المفتوح مؤقّتاً: اجعل هذا True.
OPEN_MODE_NO_LOGIN = False


def _run_session(session, open_mode: bool) -> str | None:
    """يبني النافذة الرئيسية ويشغّلها.

    يعيد إجراء الخروج: 'logout' أو 'restart' أو None (إغلاق عادي/إنهاء).
    """
    root = Tk()
    root.withdraw()                            # نخفيها حتى تجهز، خلف شاشة البداية
    apply_window_icon(root)
    splash = _show_splash(root)
    if app_mode.is_umrah():
        from .umrah_gui import UmrahApp        # واجهة العمرة (استيراد مؤجّل)
        app = UmrahApp(root, session, open_mode=open_mode)
    else:
        app = HajjApp(root, session, open_mode=open_mode)

    def _reveal():
        if splash is not None:
            splash.destroy()
        root.deiconify()

    root.after(900, _reveal)
    root.mainloop()
    return getattr(app, "_exit_action", None)


def _choose_mode() -> str | None:
    """شاشة اختيار وضع العمل: **الحج** أو **العمرة**.

    تعيد ``'hajj'`` أو ``'umrah'``، أو ``None`` إن أُغلقت النافذة دون اختيار.
    """
    win = Tk()
    apply_window_icon(win)
    win.title("المصطفى للحج والعمرة — اختيار الوضع")
    win.configure(bg=BG)
    win.resizable(False, False)
    result: dict = {"mode": None}

    outer = tk.Frame(win, bg=BG, padx=48, pady=36)
    outer.pack()
    img = logo_image(win, width=190)
    if img is not None:
        lb = tk.Label(outer, image=img, bg=BG)
        lb.image = img                         # مرجع يمنع جمع القمامة
        lb.pack()
    tk.Label(outer, text="اختر وضع العمل", bg=BG, fg=ACCENT,
             font=(_FSB, 18)).pack(pady=(14, 2))
    tk.Label(outer, text="لكلّ وضع بياناته وإعداداته المستقلّة", bg=BG, fg=MUTED,
             font=(_FUI, 10)).pack(pady=(0, 22))

    def choose(mode: str) -> None:
        result["mode"] = mode
        win.destroy()

    btns = tk.Frame(outer, bg=BG)
    btns.pack()

    def card(emoji: str, title: str, mode: str, accent: str):
        btn = tk.Button(
            btns, text=f"{emoji}\n{title}", font=(_FSB, 19), bg=accent, fg="white",
            activebackground=accent, activeforeground="white", relief="flat",
            bd=0, width=9, height=3, cursor="hand2",
            command=lambda: choose(mode))
        btn.pack(side=RIGHT, padx=11)
        return btn

    # الكعبة للحج والهلال للعمرة (تمييز بصري)
    card("🕋", "الحج", app_mode.HAJJ, BRONZE)
    card("🌙", "العمرة", app_mode.UMRAH, ACCENT)

    tk.Label(outer, text="🕋 الحج: كل الميزات   ·   🌙 العمرة: بلا المناسك والخيام",
             bg=BG, fg=MUTED, font=(_FUI, 9)).pack(pady=(20, 0))

    win.bind("<Escape>", lambda _e: win.destroy())
    win.update_idletasks()
    w, h = win.winfo_width(), win.winfo_height()
    sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
    win.geometry(f"+{(sw - w) // 2}+{(sh - h) // 3}")
    win.mainloop()
    return result["mode"]


def _mode_loop(session, open_mode: bool) -> str | None:
    """يعرض شاشة اختيار الوضع ثم يشغّل الجلسة، مع دعم التبديل وتبديل اللغة.

    يعيد 'logout' للعودة إلى شاشة الدخول، أو None لإنهاء البرنامج.
    """
    mode = _choose_mode()
    while mode is not None:
        app_mode.set_mode(mode)
        action = _run_session(session, open_mode)
        if action == "restart":
            continue                           # تبديل اللغة/اللون — نفس الوضع
        if action and action.startswith("switch"):
            # "switch:<mode>" ينتقل مباشرةً لذلك الوضع؛ "switch" وحده = شاشة الاختيار
            target = action.split(":", 1)[1] if ":" in action else ""
            mode = target if target in (app_mode.HAJJ, app_mode.UMRAH) \
                else _choose_mode()
            continue
        if action == "logout":
            return "logout"
        return None                            # إغلاق عادي — إنهاء
    return None                                # أُغلقت شاشة الاختيار دون اختيار


def main() -> None:
    from .logging_setup import setup_logging, install_tk_excepthook
    setup_logging()
    install_tk_excepthook(tk)
    if OPEN_MODE_NO_LOGIN:
        _mode_loop(None, True)
        return

    # حلقة الدخول: تسجيل الخروج يعيد شاشة الدخول، والوضع يُختار بعد كل دخول
    while True:
        session = authenticate()               # الدخول أولاً بمفتاح فك التشفير
        if session is None:
            return
        if _mode_loop(session, False) != "logout":
            return                             # إنهاء — أو أُغلقت النوافذ عادةً

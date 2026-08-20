"""شاشة الدخول وشاشة إنشاء الحساب أول مرة.

تُعرض قبل النافذة الرئيسية. إن لم يكن هناك حساب بعد ظهرت شاشة الإعداد،
وإلا شاشة الدخول. لا يفتح البرنامج إلا بجلسة صالحة تحمل مفتاح فك التشفير.
"""

from __future__ import annotations

import shutil
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import auth
from .auth import AuthError, Session

# ألوان علامة المصطفى للحج والعمرة — مأخوذة من ملف الشعار نفسه
INK = "#111111"             # الأسود
BRONZE = "#8A6E4B"          # البرونزي
PAPER = "#FFFFFF"
MUTED = "#7A6A58"
DANGER = "#B91C1C"

from .paths import resource_dir

ASSETS = resource_dir() / "assets"

# عائلة الخطّ لشاشة الدخول — تُكتشف عند أول نافذة (Dubai/Sakkal) وإلا Segoe UI.
# نُبقيها محلّية كي لا نستورد وحدة الواجهة (gui يستورد login فيقع دَوَران).
_FUI = "Segoe UI"


def detect_font(root) -> None:
    """يختار أجمل خطّ عربي متوفّر لشاشة الدخول (مطابق لاختيار الواجهة)."""
    global _FUI
    try:
        from tkinter import font as _tkfont
        fams = set(_tkfont.families(root))
    except Exception:
        return
    for fam in ("Dubai", "Sakkal Majalla", "Segoe UI"):
        if fam in fams:
            _FUI = fam
            return

# Tk لا يطبّق خوارزمية الاتجاه الثنائي (bidi)، فالنص العربي الذي يحوي
# حروفاً لاتينية أو علامة ترقيم في آخره يظهر مقلوباً: "إكسل وPDF" تُعرض
# "PDFإكسل و". تغليف النص بعلامتي التضمين من اليمين لليسار يثبّت الاتجاه.
_RTL_EMBED, _POP = "‫", "‬"


def rtl(text: str) -> str:
    """يثبّت اتجاه النص العربي المختلط بحروف لاتينية أو ترقيم."""
    return f"{_RTL_EMBED}{text}{_POP}"

# عدد المحاولات قبل الإغلاق — يبطئ التخمين اليدوي دون إزعاج المستخدم
MAX_ATTEMPTS = 5


def logo_image(master: tk.Misc, width: int = 260) -> tk.PhotoImage | None:
    """يحمّل الشعار بعرض مناسب. يعيد None إن تعذّر — الشعار زينة لا شرط."""
    path = ASSETS / "logo.png"
    if not path.is_file():
        return None
    try:
        image = tk.PhotoImage(master=master, file=str(path))
    except tk.TclError:
        return None
    # subsample يقبل أعداداً صحيحة فقط، فنقرّب أقرب نسبة تصغير
    factor = max(1, round(image.width() / width))
    return image.subsample(factor, factor)


def apply_window_icon(window: tk.Misc) -> None:
    """يضع شعار الشركة أيقونةً للنافذة (العنوان وشريط المهام). يتجاهل الفشل."""
    icon = ASSETS / "logo.ico"
    if icon.is_file():
        try:
            window.iconbitmap(str(icon))          # لشريط المهام في ويندوز
        except tk.TclError:
            pass
    # إضافةً: iconphoto من PNG لعنوان النافذة (أوضح وعبر المنصّات)
    png = ASSETS / "logo.png"
    if png.is_file():
        try:
            img = tk.PhotoImage(master=window, file=str(png))
            factor = max(1, round(img.width() / 64))
            small = img.subsample(factor, factor)
            window.iconphoto(True, small)
            refs = getattr(window, "_icon_refs", [])
            refs.append(small)
            window._icon_refs = refs               # مرجع يمنع جمع القمامة
        except tk.TclError:
            pass


class RecoveryKeyDialog(tk.Toplevel):
    """يعرض مفتاح الاسترداد مرة واحدة ويُلزم المستخدم بحفظه.

    لا يُغلق إلا بعد تأكيد الحفظ: المفتاح لا يمكن استخراجه لاحقاً من ملف
    الحساب، ومن يفقده مع كلمة المرور يفقد البيانات نهائياً.
    """

    def __init__(self, parent: tk.Misc, recovery_key: str, *, is_new: bool = True) -> None:
        super().__init__(parent)
        self.recovery_key = recovery_key
        self.title("مفتاح الاسترداد")
        self.configure(bg=PAPER)
        self.resizable(False, False)
        apply_window_icon(self)
        self.transient(parent)

        outer = tk.Frame(self, bg=PAPER, padx=36, pady=26)
        outer.pack()

        tk.Label(outer, text="🔑  احفظ مفتاح الاسترداد", bg=PAPER, fg=INK,
                 font=(_FUI, 15, "bold")).pack()

        reason = (
            "أُنشئ حسابك بنجاح" if is_new
            else "حسابك كان بلا مفتاح استرداد — وأُنشئ له واحد الآن"
        )
        tk.Label(
            outer, bg=PAPER, fg=MUTED, font=(_FUI, 10), justify="center",
            wraplength=420,
            text=rtl(
                f"{reason}\n\n"
                "هذا المفتاح هو طريقتك الوحيدة لفتح البيانات إن نسيت كلمة المرور\n"
                "يُعرض الآن فقط، ولا يمكن استخراجه لاحقاً من البرنامج"
            ),
        ).pack(pady=(8, 16))

        # العرض بعدد المحارف لا بالبكسل: المفتاح يجب أن يظهر كاملاً مهما
        # اختلف قياس الخط على جهاز المستخدم — قطعُه يعني فقدان البيانات.
        key_box = tk.Entry(
            outer, font=("Consolas", 13, "bold"), justify="center",
            width=len(recovery_key) + 2,
            relief="solid", bd=1, fg=INK, readonlybackground="#FBF7F2",
        )
        key_box.insert(0, recovery_key)
        key_box.configure(state="readonly")
        key_box.pack(fill="x", ipady=9)

        tk.Label(
            outer, bg=PAPER, fg=BRONZE, font=(_FUI, 9), justify="center",
            wraplength=420,
            text=rtl("اطبعه أو اكتبه على ورق، واحفظه في مكان آمن بعيد عن الجهاز"),
        ).pack(pady=(10, 14))

        buttons = tk.Frame(outer, bg=PAPER)
        buttons.pack(fill="x")
        self._button(buttons, "📋  نسخ", self._copy).pack(side="right", expand=True, fill="x", padx=3)
        self._button(buttons, "💾  حفظ في ملف", self._save).pack(side="right", expand=True, fill="x", padx=3)

        self.feedback = tk.Label(outer, text="", bg=PAPER, fg=BRONZE, font=(_FUI, 9))
        self.feedback.pack(pady=(10, 0))

        self.confirmed = tk.BooleanVar(value=False)
        tk.Checkbutton(
            outer, variable=self.confirmed, bg=PAPER, fg=INK, activebackground=PAPER,
            font=(_FUI, 10), command=self._toggle, anchor="e",
            text=rtl("حفظتُ المفتاح في مكان آمن"),
        ).pack(pady=(14, 0), fill="x")

        self.done = tk.Button(
            outer, text="متابعة", command=self.destroy, state="disabled",
            bg=INK, fg=PAPER, activebackground=BRONZE, activeforeground=INK,
            disabledforeground="#AAAAAA", font=(_FUI, 11, "bold"),
            relief="flat", padx=24, pady=8, cursor="hand2",
        )
        self.done.pack(pady=(12, 0), fill="x")

        # الإغلاق بالزر أو بعلامة النافذة ممنوع قبل التأكيد
        self.protocol("WM_DELETE_WINDOW", lambda: None)
        self.grab_set()
        self._center()

    def _button(self, parent: tk.Frame, text: str, command) -> tk.Button:
        return tk.Button(
            parent, text=text, command=command, bg="#EFE9E1", fg=INK,
            activebackground=BRONZE, activeforeground=PAPER, relief="flat",
            font=(_FUI, 10), pady=7, cursor="hand2",
        )

    def _toggle(self) -> None:
        self.done.configure(state="normal" if self.confirmed.get() else "disabled")

    def _copy(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.recovery_key)
        self.feedback.configure(text="نُسخ المفتاح — الصقه في مكان آمن")

    def _save(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=".txt",
            initialfile="مفتاح الاسترداد - المصطفى للحج والعمرة.txt",
            filetypes=(("ملف نصي", "*.txt"), ("كل الملفات", "*.*")),
        )
        if not path:
            return
        try:
            Path(path).write_text(
                "المصطفى للحج والعمرة — برنامج موسم الحج\n"
                "مفتاح استرداد كلمة المرور\n\n"
                f"    {self.recovery_key}\n\n"
                "بهذا المفتاح تفتح بياناتك وتعيّن كلمة مرور جديدة إن نسيت الحالية.\n"
                "احفظه في مكان آمن، ولا تتركه على نفس الجهاز الذي عليه البرنامج.\n",
                encoding="utf-8",
            )
        except OSError as exc:
            self.feedback.configure(text=f"تعذّر الحفظ: {exc}", fg=DANGER)
            return
        self.feedback.configure(text="حُفظ المفتاح — انقله إلى مكان آمن", fg=BRONZE)

    def _center(self) -> None:
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 3
        self.geometry(f"+{x}+{y}")


class _ResetDialog(tk.Toplevel):
    """إعادة تعيين كلمة المرور بمفتاح الاسترداد."""

    def __init__(self, parent: tk.Misc, auth_path: Path | None) -> None:
        super().__init__(parent)
        self.auth_path = auth_path
        self.session: Session | None = None
        self.title("إعادة تعيين كلمة المرور")
        self.configure(bg=PAPER)
        self.resizable(False, False)
        apply_window_icon(self)
        self.transient(parent)

        outer = tk.Frame(self, bg=PAPER, padx=36, pady=26)
        outer.pack()

        tk.Label(outer, text="إعادة تعيين كلمة المرور", bg=PAPER, fg=INK,
                 font=(_FUI, 14, "bold")).pack()
        tk.Label(
            outer, bg=PAPER, fg=MUTED, font=(_FUI, 9), justify="center",
            wraplength=380,
            text=rtl("أدخل مفتاح الاسترداد الذي حفظته عند إنشاء الحساب\n"
                     "بياناتك ستبقى كما هي"),
        ).pack(pady=(8, 16))

        tk.Label(outer, text="مفتاح الاسترداد", bg=PAPER, fg=INK,
                 font=(_FUI, 10), anchor="e").pack(fill="x")
        self.key = ttk.Entry(outer, width=34, justify="center", font=("Consolas", 12))
        self.key.pack(fill="x", pady=(2, 10))

        tk.Label(outer, text="كلمة المرور الجديدة", bg=PAPER, fg=INK,
                 font=(_FUI, 10), anchor="e").pack(fill="x")
        self.password = ttk.Entry(outer, width=34, justify="right", show="●",
                                  font=(_FUI, 11))
        self.password.pack(fill="x", pady=(2, 10))

        tk.Label(outer, text="تأكيد كلمة المرور", bg=PAPER, fg=INK,
                 font=(_FUI, 10), anchor="e").pack(fill="x")
        self.confirm = ttk.Entry(outer, width=34, justify="right", show="●",
                                 font=(_FUI, 11))
        self.confirm.pack(fill="x", pady=(2, 0))

        self.message = tk.Label(outer, text="", bg=PAPER, fg=DANGER,
                                font=(_FUI, 9), wraplength=380, justify="center")
        self.message.pack(pady=(12, 0))

        tk.Button(
            outer, text="تعيين كلمة المرور والدخول", command=self._submit,
            bg=INK, fg=PAPER, activebackground=BRONZE, activeforeground=INK,
            font=(_FUI, 11, "bold"), relief="flat", padx=20, pady=9,
            cursor="hand2",
        ).pack(pady=(14, 0), fill="x")

        self.bind("<Return>", lambda _e: self._submit())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.key.focus_set()
        self.grab_set()
        self._center()

    def _center(self) -> None:
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 3
        self.geometry(f"+{x}+{y}")

    def _submit(self) -> None:
        problem = auth.password_problem(self.password.get(), self.confirm.get())
        if problem:
            self.message.configure(text=rtl(problem))
            return
        try:
            self.session = auth.reset_with_recovery_key(
                self.key.get(), self.password.get(), self.auth_path
            )
        except AuthError as exc:
            self.message.configure(text=rtl(str(exc)))
            return
        self.destroy()


class NewRecoveryKeyDialog(tk.Toplevel):
    """يطلب كلمة المرور ثم يولّد مفتاح استرداد جديداً يبطل القديم."""

    def __init__(self, parent: tk.Misc, username: str,
                 auth_path: Path | None = None) -> None:
        super().__init__(parent)
        self.username = username
        self.auth_path = auth_path
        self.recovery_key: str | None = None
        self.title("مفتاح استرداد جديد")
        self.configure(bg=PAPER)
        self.resizable(False, False)
        apply_window_icon(self)
        self.transient(parent)

        outer = tk.Frame(self, bg=PAPER, padx=36, pady=26)
        outer.pack()

        tk.Label(outer, text="مفتاح استرداد جديد", bg=PAPER, fg=INK,
                 font=(_FUI, 14, "bold")).pack()
        tk.Label(
            outer, bg=PAPER, fg=MUTED, font=(_FUI, 9), justify="center",
            wraplength=360,
            text=rtl("أدخل كلمة المرور الحالية ليُنشئ البرنامج مفتاحاً جديداً\n"
                     "المفتاح القديم سيبطل فوراً، وبياناتك لن تتأثر"),
        ).pack(pady=(8, 16))

        tk.Label(outer, text="كلمة المرور الحالية", bg=PAPER, fg=INK,
                 font=(_FUI, 10), anchor="e").pack(fill="x", pady=(0, 2))
        self.password = ttk.Entry(outer, width=32, justify="right", show="●",
                                  font=(_FUI, 11))
        self.password.pack(fill="x")

        self.message = tk.Label(outer, text="", bg=PAPER, fg=DANGER,
                                font=(_FUI, 9), wraplength=360, justify="center")
        self.message.pack(pady=(12, 0))

        tk.Button(
            outer, text="إنشاء المفتاح", command=self._submit,
            bg=INK, fg=PAPER, activebackground=BRONZE, activeforeground=INK,
            font=(_FUI, 11, "bold"), relief="flat", padx=20, pady=9,
            cursor="hand2",
        ).pack(pady=(14, 0), fill="x")

        self.bind("<Return>", lambda _e: self._submit())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.password.focus_set()
        self.grab_set()
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 3
        self.geometry(f"+{x}+{y}")

    def _submit(self) -> None:
        try:
            self.recovery_key = auth.regenerate_recovery_key(
                self.username, self.password.get(), self.auth_path
            )
        except AuthError as exc:
            self.message.configure(text=rtl(str(exc)))
            self.password.delete(0, "end")
            self.password.focus_set()
            return
        self.destroy()


class ChangePasswordDialog(tk.Toplevel):
    """تغيير كلمة المرور من داخل البرنامج، بمعرفة الكلمة الحالية."""

    def __init__(self, parent: tk.Misc, username: str,
                 auth_path: Path | None = None) -> None:
        super().__init__(parent)
        self.username = username
        self.auth_path = auth_path
        self.session: Session | None = None
        self.title("تغيير كلمة المرور")
        self.configure(bg=PAPER)
        self.resizable(False, False)
        apply_window_icon(self)
        self.transient(parent)

        outer = tk.Frame(self, bg=PAPER, padx=36, pady=26)
        outer.pack()

        tk.Label(outer, text="تغيير كلمة المرور", bg=PAPER, fg=INK,
                 font=(_FUI, 14, "bold")).pack()
        tk.Label(
            outer, bg=PAPER, fg=MUTED, font=(_FUI, 9), justify="center",
            wraplength=360,
            text=rtl(f"المستخدم: {username}\n"
                     "بياناتك لن تتأثر، ومفتاح الاسترداد يبقى صالحاً"),
        ).pack(pady=(8, 16))

        self.current = self._field(outer, "كلمة المرور الحالية")
        self.password = self._field(outer, "كلمة المرور الجديدة")
        self.confirm = self._field(outer, "تأكيد كلمة المرور الجديدة")

        self.message = tk.Label(outer, text="", bg=PAPER, fg=DANGER,
                                font=(_FUI, 9), wraplength=360, justify="center")
        self.message.pack(pady=(12, 0))

        tk.Button(
            outer, text="حفظ", command=self._submit,
            bg=INK, fg=PAPER, activebackground=BRONZE, activeforeground=INK,
            font=(_FUI, 11, "bold"), relief="flat", padx=20, pady=9,
            cursor="hand2",
        ).pack(pady=(14, 0), fill="x")

        self.bind("<Return>", lambda _e: self._submit())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.current.focus_set()
        self.grab_set()
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 3
        self.geometry(f"+{x}+{y}")

    def _field(self, parent: tk.Frame, label: str) -> ttk.Entry:
        tk.Label(parent, text=label, bg=PAPER, fg=INK, font=(_FUI, 10),
                 anchor="e").pack(fill="x", pady=(6, 2))
        entry = ttk.Entry(parent, width=32, justify="right", show="●",
                          font=(_FUI, 11))
        entry.pack(fill="x")
        return entry

    def _submit(self) -> None:
        problem = auth.password_problem(self.password.get(), self.confirm.get())
        if problem:
            self.message.configure(text=rtl(problem))
            return
        try:
            self.session = auth.change_password(
                self.username, self.current.get(), self.password.get(), self.auth_path
            )
        except AuthError as exc:
            self.message.configure(text=rtl(str(exc)))
            self.current.delete(0, "end")
            self.current.focus_set()
            return
        self.destroy()


class _AddAccountDialog(tk.Toplevel):
    """نموذج إضافة حساب: اسم، كلمة مرور، ودور. للمدير فقط."""

    def __init__(self, parent: tk.Misc, session: Session,
                 auth_path: Path | None = None) -> None:
        super().__init__(parent)
        self.session = session
        self.auth_path = auth_path
        self.recovery_key: str | None = None
        self.title("إضافة حساب")
        self.configure(bg=PAPER)
        self.resizable(False, False)
        apply_window_icon(self)
        self.transient(parent)

        outer = tk.Frame(self, bg=PAPER, padx=36, pady=26)
        outer.pack()
        tk.Label(outer, text="إضافة حساب جديد", bg=PAPER, fg=INK,
                 font=(_FUI, 14, "bold")).pack()
        tk.Label(
            outer, bg=PAPER, fg=MUTED, font=(_FUI, 9), justify="center",
            wraplength=380,
            text=rtl("سيفتح الحساب الجديد نفس بيانات الحجّاج بكلمة مروره\n"
                     "سيُعرض له مفتاح استرداد مرة واحدة — احفظه له"),
        ).pack(pady=(8, 16))

        self.username = self._field(outer, "اسم المستخدم")
        self.password = self._field(outer, "كلمة المرور", secret=True)
        self.confirm = self._field(outer, "تأكيد كلمة المرور", secret=True)

        tk.Label(outer, text="الصلاحية", bg=PAPER, fg=INK, font=(_FUI, 10),
                 anchor="e").pack(fill="x", pady=(8, 2))
        self._roles = [r for r in auth.ROLES]
        self.role = ttk.Combobox(
            outer, state="readonly", justify="right", font=(_FUI, 11),
            values=[auth.ROLE_LABELS[r] for r in self._roles],
        )
        self.role.current(self._roles.index("viewer"))
        self.role.pack(fill="x")

        self.message = tk.Label(outer, text="", bg=PAPER, fg=DANGER,
                                font=(_FUI, 9), wraplength=380, justify="center")
        self.message.pack(pady=(12, 0))
        tk.Button(
            outer, text="إضافة الحساب", command=self._submit,
            bg=INK, fg=PAPER, activebackground=BRONZE, activeforeground=INK,
            font=(_FUI, 11, "bold"), relief="flat", padx=20, pady=9,
            cursor="hand2",
        ).pack(pady=(14, 0), fill="x")

        self.bind("<Return>", lambda _e: self._submit())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.username.focus_set()
        self.grab_set()
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 3
        self.geometry(f"+{x}+{y}")

    def _field(self, parent: tk.Frame, label: str, *, secret: bool = False) -> ttk.Entry:
        tk.Label(parent, text=label, bg=PAPER, fg=INK, font=(_FUI, 10),
                 anchor="e").pack(fill="x", pady=(6, 2))
        entry = ttk.Entry(parent, width=32, justify="right",
                          show="●" if secret else "", font=(_FUI, 11))
        entry.pack(fill="x")
        return entry

    def _submit(self) -> None:
        problem = auth.password_problem(self.password.get(), self.confirm.get())
        if problem:
            self.message.configure(text=rtl(problem))
            return
        role = self._roles[self.role.current()]
        try:
            self.recovery_key = auth.add_account(
                self.session, self.username.get(), self.password.get(),
                role, self.auth_path,
            )
        except AuthError as exc:
            self.message.configure(text=rtl(str(exc)))
            return
        self.destroy()


class AccountsDialog(tk.Toplevel):
    """إدارة الحسابات: عرض/إضافة/تغيير الدور/حذف. للمدير فقط."""

    def __init__(self, parent: tk.Misc, session: Session,
                 auth_path: Path | None = None) -> None:
        super().__init__(parent)
        self.session = session
        self.auth_path = auth_path
        self.title("إدارة الحسابات")
        self.configure(bg=PAPER)
        apply_window_icon(self)
        self.transient(parent)

        outer = tk.Frame(self, bg=PAPER, padx=28, pady=22)
        outer.pack(fill="both", expand=True)
        tk.Label(outer, text="👥  إدارة الحسابات", bg=PAPER, fg=INK,
                 font=(_FUI, 15, "bold")).pack(anchor="e")
        tk.Label(
            outer, bg=PAPER, fg=MUTED, font=(_FUI, 9), justify="right",
            text=rtl("كل الحسابات تفتح البيانات نفسها؛ الدور يحدّد ما يُسمح به"),
        ).pack(anchor="e", pady=(4, 12))

        cols = ("username", "role", "updated")
        self.tree = ttk.Treeview(outer, columns=cols, show="headings", height=8)
        self.tree.heading("username", text="المستخدم")
        self.tree.heading("role", text="الصلاحية")
        self.tree.heading("updated", text="آخر تحديث")
        self.tree.column("username", width=180, anchor="e")
        self.tree.column("role", width=90, anchor="center")
        self.tree.column("updated", width=150, anchor="center")
        self.tree.pack(fill="both", expand=True)

        self.message = tk.Label(outer, text="", bg=PAPER, fg=DANGER,
                                font=(_FUI, 9), justify="right", wraplength=430)
        self.message.pack(anchor="e", pady=(8, 0))

        row = tk.Frame(outer, bg=PAPER)
        row.pack(fill="x", pady=(12, 0))
        self._button(row, "➕  إضافة حساب", self._add).pack(side="right", padx=3)
        self._button(row, "🎚  تغيير الصلاحية", self._change_role).pack(side="right", padx=3)
        self._button(row, "🗑  حذف", self._remove).pack(side="right", padx=3)
        self._button(row, "إغلاق", self.destroy).pack(side="left", padx=3)

        self._reload()
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 3
        self.geometry(f"+{x}+{y}")

    def _button(self, parent: tk.Frame, text: str, command) -> tk.Button:
        return tk.Button(
            parent, text=text, command=command, bg="#EFE9E1", fg=INK,
            activebackground=BRONZE, activeforeground=PAPER, relief="flat",
            font=(_FUI, 10), padx=12, pady=7, cursor="hand2",
        )

    def _reload(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for acc in auth.list_accounts(self.auth_path):
            me = " (أنت)" if acc["username"].lower() == self.session.username.lower() else ""
            self.tree.insert(
                "", "end", iid=acc["username"],
                values=(acc["username"] + me,
                        auth.ROLE_LABELS.get(acc["role"], acc["role"]),
                        (acc["updated_at"] or "").replace("T", "  ")),
            )

    def _selected(self) -> str | None:
        sel = self.tree.selection()
        if not sel:
            self.message.configure(text=rtl("اختر حساباً من القائمة أولاً"))
            return None
        return sel[0]

    def _add(self) -> None:
        dialog = _AddAccountDialog(self, self.session, self.auth_path)
        self.wait_window(dialog)
        if dialog.recovery_key:
            self.wait_window(RecoveryKeyDialog(self, dialog.recovery_key))
            self.message.configure(text=rtl("أُضيف الحساب — سلّم صاحبه كلمة المرور ومفتاح الاسترداد"),
                                   fg=BRONZE)
            self._reload()

    def _change_role(self) -> None:
        username = self._selected()
        if not username:
            return
        dialog = _RolePickDialog(self, username)
        self.wait_window(dialog)
        if dialog.role is None:
            return
        try:
            auth.set_role(self.session, username, dialog.role, self.auth_path)
        except AuthError as exc:
            self.message.configure(text=rtl(str(exc)), fg=DANGER)
            return
        self.message.configure(text=rtl(f"غُيّرت صلاحية «{username}»"), fg=BRONZE)
        self._reload()

    def _remove(self) -> None:
        username = self._selected()
        if not username:
            return
        from tkinter import messagebox
        if not messagebox.askyesno("حذف حساب",
                                   rtl(f"حذف الحساب «{username}» نهائياً؟"),
                                   parent=self):
            return
        try:
            auth.remove_account(self.session, username, self.auth_path)
        except AuthError as exc:
            self.message.configure(text=rtl(str(exc)), fg=DANGER)
            return
        self.message.configure(text=rtl(f"حُذف الحساب «{username}»"), fg=BRONZE)
        self._reload()


class _RolePickDialog(tk.Toplevel):
    """اختيار دور جديد لحساب."""

    def __init__(self, parent: tk.Misc, username: str) -> None:
        super().__init__(parent)
        self.role: str | None = None
        self.title("تغيير الصلاحية")
        self.configure(bg=PAPER)
        self.resizable(False, False)
        apply_window_icon(self)
        self.transient(parent)

        outer = tk.Frame(self, bg=PAPER, padx=32, pady=24)
        outer.pack()
        tk.Label(outer, text=rtl(f"صلاحية «{username}»"), bg=PAPER, fg=INK,
                 font=(_FUI, 13, "bold")).pack(pady=(0, 14))
        self._roles = [r for r in auth.ROLES]
        self._var = tk.StringVar(value="viewer")
        descs = {
            "admin": "كل شيء + إدارة الحسابات",
            "editor": "إضافة/تعديل/حذف/استيراد + تصدير",
            "viewer": "عرض وتصدير وطباعة فقط",
        }
        for r in self._roles:
            tk.Radiobutton(
                outer, variable=self._var, value=r, bg=PAPER, fg=INK,
                activebackground=PAPER, anchor="e", justify="right",
                font=(_FUI, 11), selectcolor=PAPER,
                text=rtl(f"{auth.ROLE_LABELS[r]} — {descs[r]}"),
            ).pack(fill="x", pady=2)

        tk.Button(
            outer, text="حفظ", command=self._ok, bg=INK, fg=PAPER,
            activebackground=BRONZE, activeforeground=INK,
            font=(_FUI, 11, "bold"), relief="flat", padx=20, pady=8,
            cursor="hand2",
        ).pack(pady=(16, 0), fill="x")
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 3
        self.geometry(f"+{x}+{y}")

    def _ok(self) -> None:
        self.role = self._var.get()
        self.destroy()


class _AuthWindow:
    """نافذة الدخول/الإعداد. تعيد جلسة عند النجاح أو None عند الإلغاء."""

    def __init__(self, auth_path: Path | None = None) -> None:
        self.auth_path = auth_path
        self.setup_mode = not auth.is_configured(auth_path)
        self.session: Session | None = None
        self.attempts = 0

        self.root = tk.Tk()
        self.root.title("المصطفى للحج والعمرة — الدخول")
        self.root.configure(bg=PAPER)
        self.root.resizable(False, False)
        apply_window_icon(self.root)
        detect_font(self.root)        # اختيار أجمل خطّ عربي متوفّر قبل بناء الواجهة

        self._build()
        self._center()

    # ------------------------------------------------------------ الواجهة
    def _build(self) -> None:
        outer = tk.Frame(self.root, bg=PAPER, padx=44, pady=32)
        outer.pack()

        self._logo = logo_image(self.root, width=250)
        if self._logo is not None:
            tk.Label(outer, image=self._logo, bg=PAPER).pack(pady=(0, 18))
        else:
            tk.Label(
                outer, text="المصطفى للحج والعمرة", bg=PAPER, fg=INK,
                font=(_FUI, 20, "bold"),
            ).pack(pady=(0, 18))

        title = "إنشاء حساب المسؤول" if self.setup_mode else "تسجيل الدخول"
        tk.Label(
            outer, text=title, bg=PAPER, fg=INK, font=(_FUI, 15, "bold")
        ).pack()

        subtitle = (
            "أول تشغيل — اختر اسم مستخدم وكلمة مرور\n"
            "ستُشفَّر بيانات الحجاج بهذه الكلمة، ولا يمكن استرجاعها إن نُسيت"
            if self.setup_mode else
            "أدخل بياناتك لفتح كشف الحجاج"
        )
        tk.Label(
            outer, text=rtl(subtitle), bg=PAPER, fg=MUTED, font=(_FUI, 9),
            justify="center",
        ).pack(pady=(6, 16))

        form = tk.Frame(outer, bg=PAPER)
        form.pack()

        self.username = self._field(form, 0, "اسم المستخدم")
        self.password = self._field(form, 1, "كلمة المرور", secret=True)
        self.confirm = (
            self._field(form, 2, "تأكيد كلمة المرور", secret=True)
            if self.setup_mode else None
        )
        prefill = getattr(self, "_prefill_user", "")
        if prefill:
            self.username.insert(0, prefill)

        # تذكّر كلمة المرور (وضع الدخول فقط) — تُحفظ مشفّرة بـ DPAPI
        self.remember = None
        if not self.setup_mode:
            self.remember = tk.BooleanVar(value=False)
            saved = None
            if not prefill:
                try:
                    from . import remember as _rem
                    saved = _rem.load(self.auth_path)
                except Exception:
                    saved = None
            if saved:
                _u, _pw = saved
                self.username.delete(0, "end")
                self.username.insert(0, _u)
                self.password.insert(0, _pw)
                self.remember.set(True)
            tk.Checkbutton(
                outer, variable=self.remember, bg=PAPER, fg=INK,
                activebackground=PAPER, selectcolor=PAPER, font=(_FUI, 9),
                anchor="e", cursor="hand2",
                text=rtl("تذكّر كلمة المرور على هذا الجهاز"),
            ).pack(fill="x", pady=(12, 0))

        self.message = tk.Label(
            outer, text="", bg=PAPER, fg=DANGER, font=(_FUI, 9),
            wraplength=330, justify="center",
        )
        self.message.pack(pady=(12, 0))

        action = tk.Button(
            outer,
            text="إنشاء الحساب والدخول" if self.setup_mode else "دخول",
            command=self._submit,
            bg=INK, fg=PAPER, activebackground=BRONZE, activeforeground=INK,
            font=(_FUI, 11, "bold"), relief="flat",
            padx=24, pady=9, cursor="hand2",
        )
        action.pack(pady=(16, 0), fill="x")

        if not self.setup_mode:
            forgot = tk.Label(
                outer, text="نسيت كلمة المرور؟", bg=PAPER, fg=BRONZE,
                font=(_FUI, 9, "underline"), cursor="hand2",
            )
            forgot.pack(pady=(12, 0))
            forgot.bind("<Button-1>", lambda _e: self._forgot())
        else:
            # أول تشغيل: بدل إنشاء حساب جديد، يمكن استيراد حسابات مُعدّة مسبقاً
            imp = tk.Label(
                outer, text="لديّ حساب معدّ مسبقاً — استيراد ملف الحسابات",
                bg=PAPER, fg=BRONZE, font=(_FUI, 9, "underline"),
                cursor="hand2",
            )
            imp.pack(pady=(12, 0))
            imp.bind("<Button-1>", lambda _e: self._import_prepared())

        tk.Label(
            outer, text=rtl("المصطفى للحج والعمرة © جميع الحقوق محفوظة"),
            bg=PAPER, fg=MUTED, font=(_FUI, 8),
        ).pack(pady=(18, 0))

        self.root.bind("<Return>", lambda _e: self._submit())
        self.root.bind("<Escape>", lambda _e: self.root.destroy())
        if prefill:
            self.password.focus_set()      # الاسم مملوء — ننتقل لكلمة المرور
        else:
            self.username.focus_set()

    def _field(self, parent: tk.Frame, row: int, label: str, *, secret: bool = False):
        tk.Label(
            parent, text=label, bg=PAPER, fg=INK, font=(_FUI, 10),
            anchor="e",
        ).grid(row=row * 2, column=0, sticky="ew", pady=(8, 2))
        entry = ttk.Entry(
            parent, width=32, justify="right", show="●" if secret else "",
            font=(_FUI, 11),
        )
        entry.grid(row=row * 2 + 1, column=0, sticky="ew")
        parent.columnconfigure(0, weight=1)
        return entry

    def _center(self) -> None:
        self.root.update_idletasks()
        width, height = self.root.winfo_width(), self.root.winfo_height()
        x = (self.root.winfo_screenwidth() - width) // 2
        y = (self.root.winfo_screenheight() - height) // 3
        self.root.geometry(f"+{x}+{y}")

    # ------------------------------------------------------------- المنطق
    def _fail(self, text: str) -> None:
        self.message.config(text=rtl(text), fg=DANGER)
        self.password.delete(0, "end")
        self.password.focus_set()

    def _forgot(self) -> None:
        """يفتح شاشة الاسترداد؛ نجاحها يعني دخولاً مكتملاً."""
        dialog = _ResetDialog(self.root, self.auth_path)
        self.root.wait_window(dialog)
        if dialog.session is not None:
            self.session = dialog.session
            self.root.destroy()

    def _import_prepared(self) -> None:
        """يستورد ملف حسابات مُعدّاً مسبقاً (auth.json) عند أول تشغيل.

        هكذا يُدخَل الجهاز الجديد بحساب أُعدّ على جهاز آخر بدل إنشاء حساب
        جديد. اختيارياً يُستورد ملف بيانات الحجّاج المشفّر معه. بعد الاستيراد
        تتحوّل النافذة إلى وضع الدخول ليُدخل المستخدم كلمة مروره.
        """
        from .storage import default_data_path

        picked = filedialog.askopenfilename(
            parent=self.root, title="اختر ملف الحسابات المُعدّ مسبقاً (auth.json)",
            filetypes=(("ملف الحسابات", "*.json"), ("كل الملفات", "*.*")),
        )
        if not picked:
            return

        # التحقّق أن الملف ملف حسابات صالح قبل نسخه
        try:
            accounts = auth.list_accounts(picked)
        except AuthError:
            accounts = []
        if not accounts:
            messagebox.showerror(
                "ملف غير صالح",
                rtl("الملف المختار ليس ملف حسابات صالحاً. اختر ملف auth.json "
                    "المأخوذ من جهاز فيه البرنامج."),
                parent=self.root,
            )
            return

        target = Path(self.auth_path) if self.auth_path else auth.default_auth_path()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(picked, target)
        except OSError as exc:
            messagebox.showerror("تعذّر النسخ", rtl(str(exc)), parent=self.root)
            return

        # اختيارياً: استيراد كشف الحجّاج المشفّر ليُفتح بنفس الحسابات
        if messagebox.askyesno(
            "استيراد البيانات",
            rtl("تم استيراد الحسابات.\n\nهل تريد استيراد ملف بيانات الحجّاج "
                "المشفّر (hajjaj.json) أيضاً؟\nإن لا، يبدأ البرنامج بكشف فارغ."),
            parent=self.root,
        ):
            data_pick = filedialog.askopenfilename(
                parent=self.root, title="اختر ملف بيانات الحجّاج المشفّر (hajjaj.json)",
                filetypes=(("ملف البيانات", "*.json"), ("كل الملفات", "*.*")),
            )
            if data_pick:
                try:
                    dp = default_data_path()
                    dp.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(data_pick, dp)
                except OSError as exc:
                    messagebox.showwarning(
                        "تعذّر استيراد البيانات",
                        rtl(f"استُوردت الحسابات لكن تعذّر نسخ البيانات:\n{exc}"),
                        parent=self.root,
                    )

        # التحوّل إلى وضع الدخول وإعادة بناء النافذة بالحقول المناسبة
        self.setup_mode = False
        names = [a["username"] for a in accounts]
        self._prefill_user = names[0] if len(names) == 1 else ""
        for child in self.root.winfo_children():
            child.destroy()
        self._build()
        self._center()
        self.message.config(
            text=rtl("تم استيراد الحسابات — أدخل اسم المستخدم وكلمة المرور"),
            fg=BRONZE,
        )

    def _submit(self) -> None:
        username = self.username.get().strip()
        password = self.password.get()

        if self.setup_mode:
            problem = auth.password_problem(password, self.confirm.get())
            if problem:
                self._fail(problem)
                return
            try:
                self.session, recovery_key = auth.create_account(
                    username, password, self.auth_path
                )
            except AuthError as exc:
                self._fail(str(exc))
                return
            # المفتاح يُعرض مرة واحدة فقط، ولا يُغلق العرض إلا بعد تأكيد الحفظ
            self.root.wait_window(RecoveryKeyDialog(self.root, recovery_key))
            self.root.destroy()
            return

        try:
            self.session = auth.login(username, password, self.auth_path)
        except AuthError as exc:
            self.attempts += 1
            self._log_audit("محاولة دخول فاشلة", username or "?")
            remaining = MAX_ATTEMPTS - self.attempts
            if remaining <= 0:
                self._log_audit("قفل بعد محاولات فاشلة", username or "?")
                self.message.config(text="تجاوزت عدد المحاولات — سيُغلق البرنامج.")
                self.root.after(1400, self.root.destroy)
                return
            self._fail(f"{exc}\nمحاولات متبقية: {remaining}")
            return
        self._log_audit("تسجيل دخول", self.session.username)

        # حفظ/مسح بيانات الدخول حسب خيار «تذكّر كلمة المرور»
        try:
            from . import remember as _rem
            if getattr(self, "remember", None) is not None \
                    and self.remember.get():
                _rem.save(username, password, self.auth_path)
            else:
                _rem.clear(self.auth_path)
        except Exception:
            pass

        # حساب أُنشئ قبل ميزة الاسترداد: نرقّيه الآن ونعرض مفتاحه مرة واحدة.
        # الترقية لا تعيد تشفير الكشف — تعيد تغليف المفتاح فقط.
        if self.session.needs_recovery_key:
            try:
                key = auth.upgrade_legacy(
                    username, password, self.session, self.auth_path
                )
            except (AuthError, OSError):
                key = ""        # الترقية إضافة، وفشلها لا يمنع الدخول
            if key:
                self.root.wait_window(
                    RecoveryKeyDialog(self.root, key, is_new=False)
                )

        self.root.destroy()

    def _log_audit(self, action: str, username: str) -> None:
        """يسجّل حدث دخول/محاولة في سجلّ التدقيق (سجلّ محاولات الدخول)."""
        try:
            from . import audit
            path = (Path(self.auth_path).parent / "audit.log"
                    if self.auth_path else None)
            audit.record(action, "", user=str(username or "?"), path=path)
        except Exception:                              # noqa: BLE001
            pass

    def run(self) -> Session | None:
        self.root.mainloop()
        return self.session


def authenticate(auth_path: Path | None = None) -> Session | None:
    """يعرض شاشة الدخول (أو الإعداد أول مرة) ويعيد الجلسة، أو None."""
    return _AuthWindow(auth_path).run()

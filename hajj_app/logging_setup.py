"""تسجيل الأحداث والأخطاء في ملفٍ دائم لتسهيل تشخيص أعطال المستخدمين.

يُكتب السجلّ في ``<مجلد البيانات>/logs/hajj_app.log`` مع تدوير تلقائي
(حجم محدود ونُسخ احتياطية) كي لا ينمو بلا حدود. كما تُلتقط الأخطاء غير
المُعالَجة — سواء في الخيوط العادية أو في ردود نداء Tkinter — فتُسجَّل
بتتبّعها الكامل بدل أن تختفي بصمت.

الاستخدام:

    from .logging_setup import setup_logging, get_logger
    setup_logging()                 # مرّة واحدة عند بدء البرنامج
    log = get_logger(__name__)
    log.info("بدأ التشغيل")
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

_CONFIGURED = False
_FMT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def log_dir() -> Path:
    """مجلد السجلّات داخل مجلد البيانات الدائم؛ يُنشأ عند الحاجة."""
    from .paths import data_dir
    d = data_dir() / "logs"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d


def log_file() -> Path:
    """مسار ملف السجلّ الحالي."""
    return log_dir() / "hajj_app.log"


def get_logger(name: str = "hajj_app") -> logging.Logger:
    """يعيد مُسجِّلاً باسمٍ معيّن (عادةً ``__name__``)."""
    return logging.getLogger(name)


def _excepthook(exc_type, exc_value, exc_tb) -> None:
    """يسجّل أي استثناء غير مُعالَج قبل السلوك الافتراضي."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    logging.getLogger("hajj_app").critical(
        "خطأ غير مُعالَج", exc_info=(exc_type, exc_value, exc_tb)
    )


def _thread_excepthook(args) -> None:
    """يسجّل الأخطاء غير المُعالَجة في الخيوط (Python 3.8+)."""
    if issubclass(args.exc_type, KeyboardInterrupt):
        return
    logging.getLogger("hajj_app").critical(
        "خطأ غير مُعالَج في خيط %s", getattr(args.thread, "name", "?"),
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )


def install_tk_excepthook(tk_module) -> None:
    """يوجّه أخطاء ردود نداء Tkinter إلى السجلّ بدل طباعتها في الطرفية.

    يُستدعى بعد إنشاء أول نافذة كي لا تضيع أخطاء الأزرار والأحداث.
    """
    def _report(self, exc, val, tb):  # noqa: ANN001
        logging.getLogger("hajj_app.tk").error(
            "خطأ في رد نداء الواجهة", exc_info=(exc, val, tb)
        )
    try:
        tk_module.Tk.report_callback_exception = _report
    except Exception:  # pragma: no cover - دفاعي
        pass


def setup_logging(level: int = logging.INFO) -> Path:
    """يهيّئ التسجيل مرّة واحدة ويعيد مسار ملف السجلّ.

    * ملف بتدوير تلقائي (٥١٢ ك.ب × ٥ نُسخ) بترميز UTF-8.
    * مُوجِّه للطرفية عند مستوى التحذير فأعلى (مفيد أثناء التطوير).
    * التقاط الأخطاء غير المُعالَجة في العملية والخيوط.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return log_file()

    root = logging.getLogger()
    root.setLevel(level)

    fmt = logging.Formatter(_FMT, datefmt=_DATEFMT)

    try:
        fh = logging.handlers.RotatingFileHandler(
            log_file(), maxBytes=512 * 1024, backupCount=5, encoding="utf-8"
        )
        fh.setLevel(level)
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError:
        # تعذّرت الكتابة (قرص للقراءة فقط مثلاً) — نكتفي بالطرفية
        pass

    ch = logging.StreamHandler()
    ch.setLevel(logging.WARNING)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    sys.excepthook = _excepthook
    if hasattr(sys, "excepthook"):
        try:
            import threading
            threading.excepthook = _thread_excepthook
        except Exception:  # pragma: no cover - دفاعي
            pass

    _CONFIGURED = True
    logging.getLogger("hajj_app").info("=== بدء تشغيل البرنامج ===")
    return log_file()

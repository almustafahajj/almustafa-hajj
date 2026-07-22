# -*- coding: utf-8 -*-
"""Diagnose Arabic OCR on the real UAE passport."""
import sys, io, cv2, numpy as np, pytesseract
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_HERE)
_OUTDIR = _os.path.join(_HERE, "_out")
_os.makedirs(_OUTDIR, exist_ok=True)
sys.path.insert(0, _ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from PIL import Image
from hajj_app.tesseract_setup import configure_tesseract
from hajj_app.arabic_ocr import _preprocess, _clean_line, _best_window, extract_arabic_name
configure_tesseract()

P = r"C:\Users\AymanAlShehabi\OneDrive - Nirvana Travel & Tourism\MHU\Almustafa Hajj & Umrah\Umrah Packages\Hajj 2026\جوازات الحجاج\New folder\سعيد راشد سعيد مبارك الشامسى.jpg"
img = cv2.imdecode(np.fromfile(P, dtype=np.uint8), cv2.IMREAD_COLOR)
h, w = img.shape[:2]
print(f"image: {w} x {h}")
print("current extract_arabic_name() ->", repr(extract_arabic_name(img)))

# what does the current region+preprocess pipeline actually see?
top = img[: int(h * 0.62), :]
regions = {"right40_top": top[:, int(w * 0.40):], "full_top": top}
for rname, region in regions.items():
    print(f"\n### {rname}  shape={region.shape}")
    for i, v in enumerate(_preprocess(region)):
        print(f"  -- variant {i} (upscaled to {v.shape[1]}px wide)")
        for psm in (6, 4):
            try:
                t = pytesseract.image_to_string(Image.fromarray(v), lang="ara",
                                                config=f"--psm {psm} --oem 1")
            except Exception as e:
                print("     err", e); continue
            for ln in t.splitlines():
                c = _clean_line(ln)
                if len(c) >= 4:
                    win, sc = _best_window(c)
                    print(f"     psm{psm} RAW={ln.strip()[:70]!r}")
                    if win:
                        print(f"            WIN={win!r} score={sc:.1f}")

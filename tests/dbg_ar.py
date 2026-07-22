# -*- coding: utf-8 -*-
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
from hajj_app.arabic_ocr import _preprocess, _clean_line, _score
configure_tesseract()
p = _os.path.join(_OUTDIR, "ar_passport.png")   # ينتجه test_arabic.py
img = cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_COLOR)
h = img.shape[0]
region = img[:int(h*0.62), :]
print("region shape:", region.shape)
for i, v in enumerate(_preprocess(region)):
    t = pytesseract.image_to_string(Image.fromarray(v), lang="ara", config="--psm 6 --oem 1")
    print(f"--- variant {i} ---")
    for ln in t.splitlines():
        if ln.strip():
            c = _clean_line(ln)
            print(f"  RAW={ln.strip()!r}")
            print(f"    CLEAN={c!r} SCORE={_score(c)} WORDS={[w for w in c.split() if len(w)>=2]}")

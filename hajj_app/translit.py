"""مطابقة الاسم العربي المقروء ضوئياً بالاسم اللاتيني المأخوذ من MRZ.

الاسم اللاتيني في MRZ **محمي بخانة تحقق رياضية**، أما الاسم العربي فيُقرأ
ضوئياً بلا أي حماية. فبدل الاعتماد على تكرار القراءات وحده — وهو يفشل حين
يخطئ OCR في نفس الحرف كل مرة — نستعمل الاسم اللاتيني مرجعاً صوتياً:

    الصحيح  : مصبح          MUSABBE
    قراءات  : مصيح مصيج مصيخ   ← الباء قُرئت ياءً في كل محاولة

التصويت يرمي الكلمة كلها لأن القراءات لا تتطابق. أما المطابقة الصوتية
فترى الـ B في MUSABBE فترجّح `مصبح` على `مصيح`.

هذه الوحدة **لا تخترع أسماء**: تختار فقط من بين ما قرأه OCR فعلاً.
"""

from __future__ import annotations

import re

# كل حرف عربي وما قد يقابله في كتابة الجوازات اللاتينية. القوائم مرتّبة
# بالأطول أولاً ليجرَّب `sh` قبل `s`.
ARABIC_TO_LATIN: dict[str, tuple[str, ...]] = {
    "ا": ("aa", "a", "e", "i", "o", "u"),
    "ب": ("bb", "b", "p"),
    "ت": ("tt", "t"),
    "ث": ("th", "t", "s"),
    "ج": ("dj", "j", "g"),
    "ح": ("hh", "h"),
    "خ": ("kh", "k", "h"),
    "د": ("dd", "d"),
    "ذ": ("dh", "th", "d", "z"),
    "ر": ("rr", "r"),
    "ز": ("zz", "z"),
    "س": ("ss", "s", "c"),
    "ش": ("sh", "ch", "s"),
    "ص": ("ss", "s"),
    "ض": ("dh", "dd", "d"),
    "ط": ("tt", "t"),
    "ظ": ("dh", "th", "z"),
    # العين والهمزة لا تُكتبان في اللاتينية غالباً، أو تظهران حركةً
    "ع": ("aa", "a", "e", "i", "o", "u"),
    "غ": ("gh", "g"),
    "ف": ("ff", "f", "ph", "v"),
    "ق": ("q", "k", "g"),
    "ك": ("ck", "k", "c"),
    "ل": ("ll", "l"),
    "م": ("mm", "m"),
    "ن": ("nn", "n"),
    "ه": ("h", "a", "e"),
    "و": ("ou", "oo", "aw", "w", "o", "u"),
    "ي": ("ee", "ei", "ay", "iy", "y", "i"),
    "ى": ("a", "i", "y"),
    "ة": ("ah", "at", "a", "h", "t"),
    "ء": ("a", "e", "i", "u", "o"),
}

# حروف كثيراً ما تُهمل في الكتابة اللاتينية — حذفها رخيص التكلفة.
_SILENT = frozenset("اهةىءع")

_VOWELS = frozenset("aeiou")

# تكاليف المحاذاة. الحرف غير المطابق يكلّف 1.0، وما دونه تساهل مدروس.
_DROP_SILENT = 0.25   # حذف حرف عربي كثيراً ما يُهمل لاتينياً
_DROP_LETTER = 1.0    # حذف حرف عربي جوهري — خطأ حقيقي
_SKIP_VOWEL = 0.15    # تجاهل حركة لاتينية زائدة
_SKIP_CONSONANT = 1.0

_ALEF_FORMS = re.compile(r"[أإآٱ]")
_NON_ARABIC = re.compile(r"[^ء-ي]")


def normalize_word(word: str) -> str:
    """يوحّد صور الألف والياء لتستقر المقارنة."""
    word = _ALEF_FORMS.sub("ا", word)
    return _NON_ARABIC.sub("", word)


def _alignment_cost(arabic: str, latin: str) -> float:
    """أقل تكلفة لمحاذاة كلمة عربية بكلمة لاتينية (برمجة ديناميكية).

    كل حرف عربي إمّا يطابق مقطعاً لاتينياً من جدول التقابل (بلا تكلفة)،
    أو يُحذف بتكلفة تعتمد على كونه حرفاً صامتاً شائع الإهمال أم جوهرياً.
    والحروف اللاتينية الزائدة تُتجاوز — الحركات بثمن بخس والسواكن بثمن كامل.
    """
    n, m = len(arabic), len(latin)
    inf = float("inf")
    dp = [[inf] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0

    for i in range(n + 1):
        row = dp[i]
        for j in range(m + 1):
            cost = row[j]
            if cost == inf:
                continue
            if i < n:
                char = arabic[i]
                drop = _DROP_SILENT if char in _SILENT else _DROP_LETTER
                if cost + drop < dp[i + 1][j]:
                    dp[i + 1][j] = cost + drop
                for piece in ARABIC_TO_LATIN.get(char, ()):
                    end = j + len(piece)
                    if latin[j:end] == piece and cost < dp[i + 1][end]:
                        dp[i + 1][end] = cost
            if j < m:
                skip = _SKIP_VOWEL if latin[j] in _VOWELS else _SKIP_CONSONANT
                if cost + skip < row[j + 1]:
                    row[j + 1] = cost + skip
    return dp[n][m]


def match_score(arabic: str, latin: str) -> float:
    """درجة تطابق كلمة عربية مع كلمة لاتينية، من 0 إلى 1."""
    arabic = normalize_word(arabic)
    latin = re.sub(r"[^A-Za-z]", "", latin).lower()
    if not arabic or not latin:
        return 0.0
    cost = _alignment_cost(arabic, latin)
    return max(0.0, 1.0 - cost / max(len(arabic), len(latin)))


# أدنى درجة تطابق للكلمة الواحدة. دونها نترك موضعها فارغاً.
MATCH_FLOOR = 0.55
# أدنى متوسط للاسم كله قبل اعتماده بدل نتيجة التصويت.
NAME_FLOOR = 0.70

# تكلفة تخطّي كلمة أثناء المحاذاة: كلمة عربية زائدة (ضجيج التقطه OCR)
# أو كلمة لاتينية لم يقرأ OCR مقابلها.
_SKIP_ARABIC = 0.45
_SKIP_LATIN = 0.60


# حروف عربية تشترك في نفس الرسم وتختلف بالنقاط فقط — وهي مصدر أخطاء OCR
# الأول في العربية: `مصبح` تُقرأ `مصيح`، و`حسن` تُقرأ `حسر`. الاسم اللاتيني
# يحسم الاختيار بينها لأنه يحمل الصوت الصحيح.
_DOT_CLASSES: tuple[str, ...] = (
    "بتثنيى",   # نفس السن، تختلف بعدد النقاط وموضعها
    "جحخ",
    "دذ",
    "رز",
    "سش",
    "صض",
    "طظ",
    "عغ",
    "فق",
    "هة",
)

_CONFUSABLE: dict[str, str] = {
    char: group for group in _DOT_CLASSES for char in group
}

# لا نقبل إصلاحاً إلا إذا رفع التطابق رفعاً واضحاً وبلغ حداً معتبراً،
# حتى لا نحوّل قراءة رديئة إلى اسم مخترع يبدو مقنعاً.
_REPAIR_GAIN = 0.20
_REPAIR_MIN = 0.70


def repair_word(arabic: str, latin: str) -> tuple[str, float]:
    """يصحّح خطأ نقاط واحداً في الكلمة مسترشداً بالكلمة اللاتينية.

    يجرّب استبدال كل حرف بأخيه في رسمه فقط — لا بأي حرف — فيبقى التصحيح
    ضمن أخطاء OCR المعروفة. يعيد الكلمة كما هي إن لم يجد تحسّناً مقنعاً.
    """
    base = match_score(arabic, latin)
    if base >= 1.0:
        return arabic, base

    best_word, best_score = arabic, base
    for index, char in enumerate(arabic):
        for alternative in _CONFUSABLE.get(char, ""):
            if alternative == char:
                continue
            candidate = arabic[:index] + alternative + arabic[index + 1:]
            score = match_score(candidate, latin)
            if score > best_score:
                best_word, best_score = candidate, score

    if best_score - base >= _REPAIR_GAIN and best_score >= _REPAIR_MIN:
        return best_word, best_score
    return arabic, base


def _align_words(
    arabic_words: list[str], latin_words: list[str]
) -> dict[int, tuple[str, float]]:
    """يحاذي كلمات سطر عربي بكلمات الاسم اللاتيني مع الحفاظ على الترتيب.

    يعيد: موضع الكلمة اللاتينية -> (الكلمة العربية المقابلة، درجة التطابق).

    المحاذاة **متزايدة**: لا يجوز أن نأخذ الكلمة الرابعة لموضع ثم الثانية
    لما بعده. هذا القيد هو ما يمنع تلفيق اسم من كلمات متناثرة في أسطر
    الضجيج — الاسم الحقيقي يرد متتابعاً في سطر واحد.
    """
    n, m = len(arabic_words), len(latin_words)
    inf = float("inf")
    # dp[i][j] = أقل تكلفة لمحاذاة أول i كلمة عربية بأول j كلمة لاتينية
    dp = [[inf] * (m + 1) for _ in range(n + 1)]
    back: list[list[tuple[int, int] | None]] = [[None] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0

    for i in range(n + 1):
        for j in range(m + 1):
            cost = dp[i][j]
            if cost == inf:
                continue
            if i < n and cost + _SKIP_ARABIC < dp[i + 1][j]:
                dp[i + 1][j] = cost + _SKIP_ARABIC
                back[i + 1][j] = (i, j)
            if j < m and cost + _SKIP_LATIN < dp[i][j + 1]:
                dp[i][j + 1] = cost + _SKIP_LATIN
                back[i][j + 1] = (i, j)
            if i < n and j < m:
                pair = cost + (1.0 - match_score(arabic_words[i], latin_words[j]))
                if pair < dp[i + 1][j + 1]:
                    dp[i + 1][j + 1] = pair
                    back[i + 1][j + 1] = (i, j)

    # نتتبّع المسار عكسياً لنعرف أي كلمة عربية قابلت أي كلمة لاتينية
    aligned: dict[int, tuple[str, float]] = {}
    i, j = n, m
    while (i, j) != (0, 0):
        previous = back[i][j]
        if previous is None:
            break
        pi, pj = previous
        if pi == i - 1 and pj == j - 1:
            word, score = repair_word(arabic_words[pi], latin_words[pj])
            if score >= MATCH_FLOOR:
                aligned[pj] = (word, score)
        i, j = pi, pj
    return aligned


def reconcile(candidates: list[str], latin_name: str) -> tuple[str, float]:
    """يعيد بناء الاسم العربي مسترشداً بالاسم اللاتيني المحمي بخانة تحقق.

    يحاذي **كل قراءة على حدة** بالاسم اللاتيني، ثم يأخذ لكل موضع أفضل
    كلمة وردت فيه عبر القراءات. المحاذاة داخل سطر واحد وبترتيب محفوظ،
    فلا يمكن تلفيق اسم من كلمات ضجيج متفرقة؛ والدمج بعدها يلتقط أفضل ما
    في كل قراءة — قد يقرأ سطرٌ اللقب صحيحاً وسطرٌ آخر الاسم الأول.

    يعيد (الاسم، متوسط درجة التطابق)، أو ("", 0.0) إن لم تبلغ النتيجة
    الحد الأدنى — الفراغ أأمن من اسم مخترع.
    """
    latin_words = [w for w in re.split(r"[^A-Za-z]+", latin_name) if len(w) >= 2]
    if not latin_words or not candidates:
        return "", 0.0

    best_at: dict[int, tuple[str, float]] = {}
    for candidate in candidates:
        # الكلمات كما قرأها OCR بلا توحيد: التوحيد للمقارنة فقط (تقوم به
        # `match_score` داخلياً)، أما المخرَج فيجب أن يحفظ الهمزات والألف
        # المقصورة كما وردت — `أيمن` لا تُعاد `ايمن`.
        words = [w for w in candidate.split() if len(normalize_word(w)) >= 2]
        if not words:
            continue
        for position, (word, score) in _align_words(words, latin_words).items():
            if score > best_at.get(position, ("", 0.0))[1]:
                best_at[position] = (word, score)

    # نصف كلمات الاسم على الأقل، وكلمتان فأكثر
    if len(best_at) < 2 or len(best_at) < len(latin_words) / 2:
        return "", 0.0

    ordered = [best_at[p] for p in sorted(best_at)]
    # المتوسط على كلمات الاسم اللاتيني كلها: القراءة الناقصة تُعاقَب
    mean = sum(score for _w, score in ordered) / len(latin_words)
    if mean < NAME_FLOOR:
        return "", 0.0
    return " ".join(word for word, _s in ordered), mean

import re
from typing import List, Tuple, Dict

FRENCH_UNITS = [
    "g","gr","gramme","grammes",
    "kg","kilogramme","kilogrammes",
    "ml","millilitre","millilitres",
    "cl","dl","l","litre","litres",
    "càs","cas","c. à s.","c.à s.","cuillère à soupe","cuillères à soupe",
    "càc","cac","c. à c.","c.à c.","cuillère à café","cuillères à café",
    "pincée","pincées","tranche","tranches","sachet","sachets",
    "boîte","boites","boîtes","tasse","tasses"
]

EN_UNITS = [
    "g","kg","ml","l","cup","cups","tsp","tbsp","teaspoon","teaspoons","tablespoon","tablespoons",
    "pinch","pinches","slice","slices","packet","packets","can","cans","ounce","ounces","oz","lb","lbs"
]

UNITS = set([u.lower() for u in (FRENCH_UNITS + EN_UNITS)])

FRACTION_RE = r"(?:\d+(?:[.,]\d+)?|\d+\s*/\s*\d+|½|¼|¾|⅓|⅔|⅛|⅜|⅝|⅞)"
UNIT_RE = r"|".join(re.escape(u) for u in sorted(UNITS, key=len, reverse=True))

INGREDIENT_LINE_RE = re.compile(
    rf"^\s*(?:-|\u2022|\*)?\s*({FRACTION_RE})\s*(?:({UNIT_RE})\b)?\s*(.+)$",
    re.IGNORECASE
)

def split_sentences(text: str) -> List[str]:
    # Simple multilingual sentence split
    text = text.replace("\\n", "\n")
    parts = re.split(r"(?<=[\.\!\?])\s+(?=[A-ZÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŸ0-9])", text.strip())
    # fallback if few separators
    if len(parts) == 1:
        parts = re.split(r"\s*[\n\r]+\s*", text.strip())

    segments: List[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        subparts = re.split(r"\s*[\n\r]+\s*", part)
        for sub in subparts:
            sub = sub.strip()
            if sub:
                segments.append(sub)
    return segments

def guess_ingredients_and_steps(transcript: str) -> Tuple[List[str], List[str]]:
    lines = [l.strip() for l in re.split(r"[\n\r]+", transcript) if l.strip()]
    candidates = []
    others = []
    for l in lines:
        m = INGREDIENT_LINE_RE.match(l)
        if m:
            qty = m.group(1).strip()
            unit = (m.group(2) or "").strip()
            item = m.group(3).strip()
            # remove trailing punctuation
            item = re.sub(r"[.,;:]+$", "", item)
            if unit:
                candidates.append(f"{qty} {unit} {item}".strip())
            else:
                candidates.append(f"{qty} {item}".strip())
        else:
            others.append(l)
    # steps from remaining content
    steps_text = "\n".join(others)
    steps = split_sentences(steps_text)
    # Remove ultra-short noise
    steps = [s for s in steps if len(s) > 3]
    return candidates, steps

def normalize_title(raw_title: str) -> str:
    t = raw_title.strip()
    # remove common Tiktok artefacts
    t = re.sub(r"#\w+", "", t)
    t = re.sub(r"\s+", " ", t)
    # trim extra emojis or trailing punctuation
    t = t.strip(" -—|·•")
    return t or "Untitled Recipe"

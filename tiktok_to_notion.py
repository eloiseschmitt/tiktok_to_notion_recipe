import argparse
import os
import tempfile
from pathlib import Path
import re
from typing import Optional, Tuple, List, Dict, Any
from dotenv import load_dotenv

import whisper
import yt_dlp
from recipe_parser import guess_ingredients_and_steps, normalize_title, INGREDIENT_LINE_RE
from notion_client import create_recipe_page
from recipe_models import RecipeContent, PublishingContext

TIME_PATTERNS = [
    re.compile(r"(?:(\d+)\s*h)?\s*(\d+)?\s*(?:min|mn|minutes?)", re.I),
    re.compile(r"(\d+)\s*h(?:eurs?)?", re.I)
]


def combine_title_transcript(title_hint: str, transcript: str) -> str:
    parts = []
    if title_hint:
        parts.append(title_hint.strip())
    if transcript:
        parts.append(transcript.strip())
    return "\n\n".join([p for p in parts if p])


TITLE_STOPWORDS_WORDS = {
    "recette", "recipe", "tiktok", "facile", "easy", "rapide", "quick",
    "pour", "sans", "astuce", "tips", "comment", "best"
}
TITLE_STOPWORDS_PHRASES = {"how to", "easy recipe"}


def extract_ingredients_from_title(title_hint: str) -> List[str]:
    if not title_hint:
        return []

    cleaned = re.sub(r"#\w+", "", title_hint).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        return []

    segment = cleaned
    keyword_patterns = [
        r"(?i)ingr[ée]dients?[:\-\|\s]+(.+)",
        r"(?i)(?:avec|with)\s+(.+)",
    ]
    for pat in keyword_patterns:
        m = re.search(pat, cleaned)
        if m:
            segment = m.group(1)
            break
    else:
        for sep in [":", "-", "–", "—", "|"]:
            if sep in cleaned:
                segment = cleaned.split(sep, 1)[1].strip()
                break

    segment = re.split(r"[\(\[]", segment)[0].strip()
    if not segment:
        return []

    normalized = segment
    normalized = re.sub(r"(?i)\b(et|and|avec|with)\b", ",", normalized)
    for token in [" - ", " | "]:
        normalized = normalized.replace(token, ",")
    normalized = re.sub(r",+", ",", normalized)

    parts = [p.strip(" .!?'\"") for p in normalized.split(",")]
    results: List[str] = []
    seen = set()
    for part in parts:
        if not part:
            continue
        lowered = part.lower()
        if lowered in seen:
            continue
        words = set(re.findall(r"[a-zà-ÿ]+", lowered))
        if words & TITLE_STOPWORDS_WORDS:
            continue
        if any(phrase in lowered for phrase in TITLE_STOPWORDS_PHRASES):
            continue
        if not re.search(r"[a-zà-ÿ]", lowered):
            continue
        seen.add(lowered)
        results.append(part)
    return results


LIST_PREFIX_RE = re.compile(r"^\s*(?:[-\*\u2022]|\d+[\).])\s*")


def _strip_list_prefix(text: str) -> str:
    return LIST_PREFIX_RE.sub("", text).strip()


def tidy_recipe_lists(
    ingredients: List[str],
    steps: List[str],
    title_hint: Optional[str] = None
) -> Tuple[List[str], List[str]]:
    cleaned_ingredients: List[str] = []
    ing_seen = set()
    for ing in ingredients:
        text = _strip_list_prefix(ing.strip())
        if not text:
            continue
        lowered = text.lower()
        if lowered in ing_seen:
            continue
        ing_seen.add(lowered)
        cleaned_ingredients.append(text)

    cleaned_steps: List[str] = []
    step_seen = set()
    title_lowers = set()
    if title_hint:
        raw = title_hint.strip().lower()
        if raw:
            title_lowers.add(raw)
        normalized = normalize_title(title_hint).strip().lower()
        if normalized:
            title_lowers.add(normalized)
    for step in steps:
        text = _strip_list_prefix(step.strip())
        if not text:
            continue
        lowered = text.lower()
        if title_lowers and lowered in title_lowers:
            continue
        if lowered in ing_seen:
            continue
        if INGREDIENT_LINE_RE.match(text):
            if lowered not in ing_seen:
                ing_seen.add(lowered)
                cleaned_ingredients.append(text)
            continue
        if lowered in step_seen:
            continue
        step_seen.add(lowered)
        cleaned_steps.append(text)

    return cleaned_ingredients, cleaned_steps


def heuristic_recipe(title_hint: str, combined_text: str) -> RecipeContent:
    title = normalize_title(title_hint)
    ingredients, steps = guess_ingredients_and_steps(combined_text)
    return RecipeContent(title=title, ingredients=ingredients, steps=steps)


def enrich_with_title_ingredients(recipe: RecipeContent, title_hint: str) -> None:
    extras = extract_ingredients_from_title(title_hint)
    if not extras:
        return

    existing_lower = {ing.lower() for ing in recipe.ingredients}
    for extra in extras:
        lowered = extra.lower()
        if lowered not in existing_lower:
            recipe.ingredients.append(extra)
            existing_lower.add(lowered)


def ensure_prep_minutes(recipe: RecipeContent, combined_text: str) -> None:
    if recipe.prep_minutes is None:
        recipe.prep_minutes = estimate_prep_time(combined_text, recipe.steps)


def format_prep_time(minutes: Optional[int]) -> str:
    return f"Environ {minutes} minutes" if minutes else "Temps à préciser"


def extract_thumbnail(video_meta: Any) -> Optional[str]:
    if not isinstance(video_meta, dict):
        return None
    thumbnails = video_meta.get("thumbnails") or []
    if thumbnails:
        url = thumbnails[-1].get("url")
        if url:
            return url
    return video_meta.get("thumbnail")


def estimate_prep_time(text: str, fallback_steps: Optional[List[str]] = None) -> Optional[int]:
    """Try to estimate prep time in minutes from transcript or steps."""
    normalized = text.lower()
    for pattern in TIME_PATTERNS:
        for match in pattern.finditer(normalized):
            hours = 0
            minutes = 0
            if pattern.groups >= 2:
                if match.group(1):
                    hours = int(match.group(1))
                if match.group(2):
                    minutes = int(match.group(2))
            elif pattern.groups == 1 and match.group(1):
                minutes = int(match.group(1)) * 60
            total = hours * 60 + minutes
            if total > 0:
                return total

    if fallback_steps:
        # Heuristic: ~6 minutes per step, min 10 minutes.
        estimate = max(10, len(fallback_steps) * 6)
        return estimate

    return None

# Optional GPT structuring (only used if OPENAI_API_KEY is set)
def _extract_first_json_block(text: str) -> Optional[Dict[str, Any]]:
    """Return first JSON object found in text, if any."""
    import json

    try:
        return json.loads(text)
    except Exception:
        pass

    json_match = re.search(r"\{.*\}", text, re.S)
    if not json_match:
        return None
    try:
        return json.loads(json_match.group(0))
    except Exception:
        return None


def gpt_structure(transcript: str, title_hint: str) -> RecipeContent:
    """Use GPT to structure the recipe. Falls back to heuristics on failure."""
    import requests

    api_key = os.getenv("OPENAI_API_KEY")
    combined_text = combine_title_transcript(title_hint, transcript)
    if not api_key:
        return heuristic_recipe(title_hint, combined_text)

    system = (
        "You are a meticulous culinary editor. Extract a clean recipe in French when possible, otherwise English. "
        "Return valid JSON only."
    )
    user = f"""Here is metadata for a cooking TikTok. Use everything (title + transcript) to extract a concise recipe and estimate how long the preparation takes.
Return ONLY a JSON object with the following shape (numbers in minutes):
{{
  "title": "...",
  "ingredients": ["..."],
  "steps": ["..."],
  "prep_time_minutes": 20
}}
Video title:
\"\"\"
{title_hint}
\"\"\"
Transcript:
\"\"\"
{transcript}
\"\"\""""

    try:
        # Compatible with OpenAI responses API style
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model":"gpt-4o-mini",
                "messages":[
                    {"role":"system","content":system},
                    {"role":"user","content":user}
                ],
                "temperature":0.2
            },
            timeout=60
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()

        data = _extract_first_json_block(content)
        if not data:
            raise ValueError("No JSON in GPT response")

        title = normalize_title(data.get("title") or title_hint)
        ingredients = [i.strip() for i in data.get("ingredients") or [] if i.strip()]
        steps = [s.strip() for s in data.get("steps") or [] if s.strip()]
        prep_minutes = data.get("prep_time_minutes")
        if prep_minutes is not None:
            try:
                prep_minutes = int(prep_minutes)
                if prep_minutes <= 0:
                    prep_minutes = None
            except (ValueError, TypeError):
                prep_minutes = None

        if not ingredients or not steps:
            # fallback to heuristic merge
            h_ings, h_steps = guess_ingredients_and_steps(combined_text)
            if not ingredients:
                ingredients = h_ings
            if not steps:
                steps = h_steps

        return RecipeContent(title=title, ingredients=ingredients, steps=steps, prep_minutes=prep_minutes)
    except Exception:
        return heuristic_recipe(title_hint, combined_text)


def download_audio(url: str, tmpdir: Path) -> Tuple[Path, str, Dict[str, Any]]:
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(tmpdir / "%(id)s.%(ext)s"),
        "quiet": True,
        "nocheckcertificate": True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        # force audio path (sometimes video)
        base = Path(filename).with_suffix("")
        # yt-dlp will choose ext, keep it
        audio_path = Path(filename)
        return audio_path, info.get("title") or "TikTok Recipe", info

def transcribe(audio_path: Path, model_name: str = "small") -> str:
    model = whisper.load_model(model_name)
    result = model.transcribe(str(audio_path), language=None)  # autodetect
    return result.get("text","").strip()

def render_markdown(recipe: RecipeContent, source_url: Optional[str]) -> str:
    md = [f"# {recipe.title}", ""]
    if source_url:
        md.append(f"_Source: {source_url}_")
        md.append("")
    if recipe.ingredients:
        md.append("## Ingrédients / Ingredients")
        for ing in recipe.ingredients:
            md.append(f"- {ing}")
        md.append("")
    if recipe.steps:
        md.append("## Étapes / Steps")
        for i, s in enumerate(recipe.steps, 1):
            md.append(f"{i}. {s}")
        md.append("")
    return "\n".join(md).strip() + "\n"

def export_pdf(recipe: RecipeContent, pdf_path: Path):
    # Simple A4 PDF with ReportLab
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import cm
    from reportlab.lib.utils import simpleSplit

    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    width, height = A4
    x_margin, y_margin = 2*cm, 2*cm
    y = height - y_margin

    def draw_text(block: str, font=("Helvetica", 11), leading=14):
        nonlocal y
        c.setFont(*font)
        lines = simpleSplit(block, font[0], font[1], width - 2*x_margin)
        for line in lines:
            if y < y_margin + leading:
                c.showPage()
                y = height - y_margin
                c.setFont(*font)
            c.drawString(x_margin, y, line)
            y -= leading

    # Title
    draw_text(recipe.title, font=("Helvetica-Bold", 16), leading=20)
    y -= 8

    if recipe.ingredients:
        draw_text("Ingrédients / Ingredients", font=("Helvetica-Bold", 12), leading=16)
        for ing in recipe.ingredients:
            draw_text(f"• {ing}")
        y -= 8

    if recipe.steps:
        draw_text("Étapes / Steps", font=("Helvetica-Bold", 12), leading=16)
        for i, s in enumerate(recipe.steps, 1):
            draw_text(f"{i}. {s}")

    c.save()


def build_recipe_content(transcript: str, raw_title: str, use_gpt: bool, api_key_available: bool) -> RecipeContent:
    combined_text = combine_title_transcript(raw_title, transcript)

    if use_gpt and api_key_available:
        recipe = gpt_structure(transcript, raw_title)
    else:
        recipe = heuristic_recipe(raw_title, combined_text)
        if api_key_available:
            gpt_recipe = gpt_structure(transcript, raw_title)
            if gpt_recipe.prep_minutes is not None:
                recipe.prep_minutes = gpt_recipe.prep_minutes

    enrich_with_title_ingredients(recipe, raw_title)
    recipe.ingredients, recipe.steps = tidy_recipe_lists(recipe.ingredients, recipe.steps, raw_title)
    ensure_prep_minutes(recipe, combined_text)
    return recipe


def build_publishing_context(source_url: str, recipe: RecipeContent, video_meta: Any) -> PublishingContext:
    return PublishingContext(
        source_url=source_url,
        tags=["TikTok"],
        prep_time_text=format_prep_time(recipe.prep_minutes),
        thumbnail_url=extract_thumbnail(video_meta)
    )


def main():
    load_dotenv()
    ap = argparse.ArgumentParser(description="Convert a TikTok cooking video into a printable recipe and optionally save to Notion.")
    ap.add_argument("url", help="TikTok video URL")
    ap.add_argument("--out-dir", default="./out", help="Output directory for Markdown/PDF")
    ap.add_argument("--export-pdf", action="store_true", help="Also export a simple A4 PDF")
    ap.add_argument("--to-notion", action="store_true", help="Create a Notion page in your database")
    ap.add_argument("--use-gpt", action="store_true", help="Use GPT (if OPENAI_API_KEY is set) for better structuring")
    ap.add_argument("--whisper-model", default="small", help="Whisper model size: tiny|base|small|medium|large")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        audio_path, raw_title, video_meta = download_audio(args.url, tmpdir)
        transcript = transcribe(audio_path, model_name=args.whisper_model)
    api_key_available = bool(os.getenv("OPENAI_API_KEY"))
    recipe = build_recipe_content(transcript, raw_title, args.use_gpt, api_key_available)
    context = build_publishing_context(args.url, recipe, video_meta)

    # Write Markdown
    md = render_markdown(recipe, args.url)
    md_path = out_dir / (recipe.title.replace("/", "-")[:80] + ".md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)

    pdf_path = None
    if args.export_pdf:
        pdf_path = out_dir / (recipe.title.replace("/", "-")[:80] + ".pdf")
        export_pdf(recipe, pdf_path)

    # Notion push
    if args.to_notion:
        token = os.getenv("NOTION_TOKEN")
        dbid = os.getenv("NOTION_DATABASE_ID")
        if not token or not dbid:
            raise SystemExit("Missing NOTION_TOKEN or NOTION_DATABASE_ID. Put them in .env or environment.")
        create_recipe_page(
            token=token,
            database_id=dbid,
            recipe=recipe,
            context=context
        )

    print("Done.")
    print("Markdown:", md_path)
    if pdf_path: print("PDF:", pdf_path)
    if args.to_notion: print("Pushed to Notion.")

if __name__ == "__main__":
    main()

import argparse
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple, List
from dotenv import load_dotenv

import whisper
import yt_dlp
from parser import guess_ingredients_and_steps, normalize_title
from notion_client import create_recipe_page

# Optional GPT structuring (only used if OPENAI_API_KEY is set)
def gpt_structure(transcript: str, title_hint: str) -> Tuple[str, List[str], List[str]]:
    """
    If OPENAI_API_KEY is set, try to ask GPT to produce a better structured recipe.
    Returns (title, ingredients, steps).
    Fallback to heuristic if any error.
    """
    import os
    import json
    import requests

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return normalize_title(title_hint), *guess_ingredients_and_steps(transcript)

    system = "You are a meticulous culinary editor. Extract a clean recipe in French when possible, otherwise English."
    user = f"""Here is a transcript of a cooking TikTok. Extract a concise recipe with:
- Title (short, no hashtags)
- Ingredients (bulleted list; quantities + units if present)
- Steps (numbered, 6-10 crisp steps max)
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
        content = resp.json()["choices"][0]["message"]["content"]
        # naive parse: split sections
        title = normalize_title(title_hint)
        ings, steps = [], []
        # try to find Ingredients and Steps sections
        import re
        block = content.strip()
        # extract title from first line if markdown header present
        m = re.match(r"^\s*#*\s*(.+)\n", block)
        if m:
            cand = m.group(1).strip()
            if cand and len(cand) <= 120:
                title = normalize_title(cand)
        # collect list items
        ing_sec = re.search(r"(Ingr[ée]dients|Ingredients)[:\n\r]+(.+?)(?:\n\n|Étapes|Steps|$)", block, re.S|re.I)
        if ing_sec:
            ings_text = ing_sec.group(2).strip()
            ings = [re.sub(r"^[\-\*\u2022]\s*","",l).strip() for l in ings_text.splitlines() if l.strip()]
        step_sec = re.search(r"(Étapes|Steps)[:\n\r]+(.+)$", block, re.S|re.I)
        if step_sec:
            steps_text = step_sec.group(2).strip()
            # split numbered or lines
            raw_steps = [re.sub(r"^\s*\d+[\).\-\u2022]?\s*","",l).strip() for l in steps_text.splitlines() if l.strip()]
            steps = [s for s in raw_steps if len(s)>2]
        if not ings or not steps:
            # fallback to heuristic merge
            h_ings, h_steps = guess_ingredients_and_steps(transcript)
            if not ings: ings = h_ings
            if not steps: steps = h_steps
        return title, ings, steps
    except Exception:
        return normalize_title(title_hint), *guess_ingredients_and_steps(transcript)


def download_audio(url: str, tmpdir: Path) -> Tuple[Path, str]:
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
        return audio_path, info.get("title") or "TikTok Recipe"

def transcribe(audio_path: Path, model_name: str = "small") -> str:
    model = whisper.load_model(model_name)
    result = model.transcribe(str(audio_path), language=None)  # autodetect
    return result.get("text","").strip()

def render_markdown(title: str, ingredients: List[str], steps: List[str], source_url: Optional[str]) -> str:
    md = [f"# {title}", ""]
    if source_url:
        md.append(f"_Source: {source_url}_")
        md.append("")
    if ingredients:
        md.append("## Ingrédients / Ingredients")
        for ing in ingredients:
            md.append(f"- {ing}")
        md.append("")
    if steps:
        md.append("## Étapes / Steps")
        for i, s in enumerate(steps, 1):
            md.append(f"{i}. {s}")
        md.append("")
    return "\n".join(md).strip() + "\n"

def export_pdf(title: str, ingredients: List[str], steps: List[str], pdf_path: Path):
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
    draw_text(title, font=("Helvetica-Bold", 16), leading=20)
    y -= 8

    if ingredients:
        draw_text("Ingrédients / Ingredients", font=("Helvetica-Bold", 12), leading=16)
        for ing in ingredients:
            draw_text(f"• {ing}")
        y -= 8

    if steps:
        draw_text("Étapes / Steps", font=("Helvetica-Bold", 12), leading=16)
        for i, s in enumerate(steps, 1):
            draw_text(f"{i}. {s}")

    c.save()

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
        audio_path, raw_title = download_audio(args.url, tmpdir)
        transcript = transcribe(audio_path, model_name=args.whisper_model)

    if args.use_gpt and os.getenv("OPENAI_API_KEY"):
        title, ingredients, steps = gpt_structure(transcript, raw_title)
    else:
        title = normalize_title(raw_title)
        ingredients, steps = guess_ingredients_and_steps(transcript)

    # Write Markdown
    md = render_markdown(title, ingredients, steps, args.url)
    md_path = out_dir / (title.replace("/", "-")[:80] + ".md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)

    pdf_path = None
    if args.export_pdf:
        pdf_path = out_dir / (title.replace("/", "-")[:80] + ".pdf")
        export_pdf(title, ingredients, steps, pdf_path)

    # Notion push
    if args.to_notion:
        token = os.getenv("NOTION_TOKEN")
        dbid = os.getenv("NOTION_DATABASE_ID")
        if not token or not dbid:
            raise SystemExit("Missing NOTION_TOKEN or NOTION_DATABASE_ID. Put them in .env or environment.")
        create_recipe_page(
            token=token,
            database_id=dbid,
            title=title,
            source_url=args.url,
            ingredients=ingredients,
            steps=steps,
            tags=["TikTok"]
        )

    print("Done.")
    print("Markdown:", md_path)
    if pdf_path: print("PDF:", pdf_path)
    if args.to_notion: print("Pushed to Notion.")

if __name__ == "__main__":
    main()

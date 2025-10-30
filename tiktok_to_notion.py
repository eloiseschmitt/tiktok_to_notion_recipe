import argparse
import os
import tempfile
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from dotenv import load_dotenv

import whisper
import yt_dlp
from notion_client import create_recipe_page
from recipe_models import RecipeContent
from recipe_extractor import RecipeExtractor
from publishing_context import PublishingContextBuilder

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
    extractor = RecipeExtractor(args.use_gpt, api_key_available)
    recipe = extractor.build(transcript, raw_title)
    context_builder = PublishingContextBuilder()
    context = context_builder.build(args.url, recipe, video_meta)

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

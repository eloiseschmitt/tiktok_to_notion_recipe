# TikTok → Recipe (Markdown, PDF, Notion)

A small, local-first toolchain to turn a TikTok cooking video into a clean recipe you can **print** or **save in Notion**.

- **Local mode** (no external AI): yt-dlp + Whisper transcription + heuristic parser → Markdown (+ optional PDF).
- **Optional GPT mode**: If you set `OPENAI_API_KEY`, the script will ask GPT to structure the recipe more accurately.
- **Optional Notion push**: If you set `NOTION_TOKEN` and `NOTION_DATABASE_ID`, the script can create a page in your Notion recipe database.

> Works for French & English recipes. Variables and code in English, as requested.

## Quick start

1. **Prereqs**
   - Python 3.10+
   - (Recommended) FFmpeg installed for `yt-dlp`
   - (Optional) A GPU + PyTorch for faster Whisper

2. **Install**
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Run (local heuristic mode)**
   ```bash
   python tiktok_to_notion.py "https://www.tiktok.com/@creator/video/123456789" --out-dir ./out --export-pdf
   ```

4. **Optional: Use GPT for better structuring**
   ```bash
   export OPENAI_API_KEY="sk-..."  # or set in .env
   python tiktok_to_notion.py "https://www.tiktok.com/@creator/video/123456789" --use-gpt
   ```

5. **Optional: Push to Notion**
   - Create a Notion integration and copy the **Internal Integration Token**.
   - Share your target **database** with this integration and copy the **database ID**.
   - Put them into `.env`:
     ```env
     NOTION_TOKEN=secret_xxx
     NOTION_DATABASE_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
     ```
   - Run:
     ```bash
     python tiktok_to_notion.py "https://www.tiktok.com/@creator/video/123456789" --to-notion
     ```

## Notion database schema (recommended)

- **Name** (Title)
- **Source URL** (URL)
- **Tags** (Multi-select) – e.g., "TikTok", "Quick", "Dessert"
- **Servings** (Number)
- **Prep Time (min)** (Number)
- **Cook Time (min)** (Number)

The script will try to fill these if present. Missing properties are ignored.

## Output

- `*.md` – printable Markdown (you can print/export to PDF from any Markdown viewer)
- `*.pdf` – optional, A4 simple layout via ReportLab
- Optional Notion page creation (ingredients as bullets, steps as numbered items).

## Notes & limitations

- Heuristic parsing is intentionally conservative; review quantities/units.
- Whisper accuracy depends on audio clarity. Consider `--whisper-model medium` for better results.
- Respect creator rights. Keep recipes for personal use.

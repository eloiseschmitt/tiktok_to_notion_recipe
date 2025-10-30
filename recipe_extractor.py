import os
import re
from typing import Any, List, Optional, Tuple

from constants import (
    TIME_PATTERNS,
    TITLE_STOPWORDS_WORDS,
    TITLE_STOPWORDS_PHRASES,
    LIST_PREFIX_RE,
)
from recipe_models import RecipeContent
from recipe_parser import guess_ingredients_and_steps, normalize_title, INGREDIENT_LINE_RE


def combine_title_transcript(title_hint: str, transcript: str) -> str:
    parts = []
    if title_hint:
        parts.append(title_hint.strip())
    if transcript:
        parts.append(transcript.strip())
    return "\n\n".join([p for p in parts if p])


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
        estimate = max(10, len(fallback_steps) * 6)
        return estimate

    return None


def ensure_prep_minutes(recipe: RecipeContent, combined_text: str) -> None:
    if recipe.prep_minutes is None:
        recipe.prep_minutes = estimate_prep_time(combined_text, recipe.steps)


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
    user = (
        "Here is metadata for a cooking TikTok. Use everything (title + transcript) to extract a concise recipe "
        "and estimate how long the preparation takes.\n"
        "Return ONLY a JSON object with the following shape (numbers in minutes):\n"
        "{\n"
        "  \"title\": \"...\",\n"
        "  \"ingredients\": [\"...\"],\n"
        "  \"steps\": [\"...\"],\n"
        "  \"prep_time_minutes\": 20\n"
        "}\n"
        "Video title:\n"
        f"\"\"\"\n{title_hint}\n\"\"\"\n"
        "Transcript:\n"
        f"\"\"\"\n{transcript}\n\"\"\""
    )

    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user}
                ],
                "temperature": 0.2
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
            h_ings, h_steps = guess_ingredients_and_steps(combined_text)
            if not ingredients:
                ingredients = h_ings
            if not steps:
                steps = h_steps

        return RecipeContent(title=title, ingredients=ingredients, steps=steps, prep_minutes=prep_minutes)
    except Exception:
        return heuristic_recipe(title_hint, combined_text)


def _extract_first_json_block(text: str) -> Optional[dict]:
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


class RecipeExtractor:
    """Service responsible for producing RecipeContent from TikTok inputs."""

    def __init__(self, use_gpt: bool, api_key_available: bool):
        self.use_gpt = use_gpt
        self.api_key_available = api_key_available

    def build(self, transcript: str, raw_title: str) -> RecipeContent:
        combined_text = combine_title_transcript(raw_title, transcript)
        recipe = self._primary_recipe(transcript, raw_title, combined_text)
        enrich_with_title_ingredients(recipe, raw_title)
        recipe.ingredients, recipe.steps = tidy_recipe_lists(recipe.ingredients, recipe.steps, raw_title)
        ensure_prep_minutes(recipe, combined_text)
        return recipe

    def _primary_recipe(self, transcript: str, raw_title: str, combined_text: str) -> RecipeContent:
        if self.use_gpt and self.api_key_available:
            return gpt_structure(transcript, raw_title)

        recipe = heuristic_recipe(raw_title, combined_text)
        if self.api_key_available:
            gpt_recipe = gpt_structure(transcript, raw_title)
            if gpt_recipe.prep_minutes is not None:
                recipe.prep_minutes = gpt_recipe.prep_minutes
        return recipe

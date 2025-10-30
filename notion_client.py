import os
import requests
from typing import List, Dict, Optional

from recipe_models import RecipeContent, PublishingContext

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

def _headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }

def _text(content: str) -> Dict:
    return {"type": "text", "text": {"content": content}}


def _heading(level: int, content: str) -> Dict:
    key = f"heading_{level}"
    return {
        "object": "block",
        "type": key,
        key: {"rich_text": [_text(content)]}
    }


def _paragraph(content: str) -> Dict:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": [_text(content)]}
    }


def _bulleted_items(items: List[str], placeholder: str) -> List[Dict]:
    if not items:
        return [{
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [_text(placeholder)]}
        }]
    return [{
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": [_text(item)]}
    } for item in items]


def _numbered_items(items: List[str], placeholder: str) -> List[Dict]:
    if not items:
        items = [placeholder]
    return [{
        "object": "block",
        "type": "numbered_list_item",
        "numbered_list_item": {"rich_text": [_text(item)]}
    } for item in items]


def _photo_block(thumbnail_url: Optional[str]) -> List[Dict]:
    blocks = [_heading(3, "Photo")]
    if thumbnail_url:
        blocks.append({
            "object": "block",
            "type": "image",
            "image": {
                "type": "external",
                "external": {"url": thumbnail_url}
            }
        })
    else:
        blocks.append(_paragraph("Ajouter une photo de la recette."))
    return blocks


def create_recipe_page(
    token: str,
    database_id: str,
    recipe: RecipeContent,
    context: PublishingContext
) -> Dict:
    properties: Dict[str, Dict] = {
        "Nom": {"title": [_text(recipe.title)]}
    }
    if context.source_url:
        properties["Lien vers la recette"] = {"url": context.source_url}
    if context.tags:
        properties["Tags"] = {"multi_select": [{"name": t} for t in context.tags]}
    if recipe.prep_minutes is not None:
        properties["Temps (min)"] = {"number": recipe.prep_minutes}

    children: List[Dict] = [_heading(1, "Recette")]
    children.extend(_photo_block(context.thumbnail_url))
    children.append(_heading(3, "Ingrédients"))
    children.extend(_bulleted_items(recipe.ingredients, "Ajouter les ingrédients."))
    children.append(_heading(3, "Temps de préparation"))
    children.append(_paragraph(context.prep_time_text or "@mentionn"))
    children.append(_heading(3, "Étapes"))
    children.extend(_numbered_items(recipe.steps, "Ajouter les étapes."))
    children.append(_heading(3, "Lien vers la recette originale"))
    children.append(_paragraph("Renseignez l'URL dans la propriété \"Lien vers la recette\" de cette page."))

    payload = {
        "parent": {"database_id": database_id},
        "properties": properties,
        "children": children
    }
    resp = requests.post(f"{NOTION_API_BASE}/pages", headers=_headers(token), json=payload, timeout=30)
    if not resp.ok:
        raise RuntimeError(f"Notion API error {resp.status_code}: {resp.text}")
    return resp.json()

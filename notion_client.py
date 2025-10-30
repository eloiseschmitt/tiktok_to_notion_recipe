import os
import requests
from typing import List, Dict, Optional

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

def _headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }

def create_recipe_page(
    token: str,
    database_id: str,
    title: str,
    source_url: Optional[str],
    ingredients: List[str],
    steps: List[str],
    tags: Optional[List[str]] = None,
    prep_minutes: Optional[int] = None,
    prep_time_text: Optional[str] = None,
    thumbnail_url: Optional[str] = None
) -> Dict:
    properties: Dict[str, Dict] = {
        "Nom": {"title": [{"text": {"content": title}}]}
    }
    if source_url:
        properties["Lien vers la recette"] = {"url": source_url}
    if tags:
        properties["Tags"] = {"multi_select": [{"name": t} for t in tags]}
    if prep_minutes is not None:
        properties["Temps (min)"] = {"number": prep_minutes}

    children: List[Dict] = []
    children.append({
        "object": "block",
        "type": "heading_1",
        "heading_1": {
            "rich_text": [{"type": "text", "text": {"content": "Recette"}}]
        }
    })

    # Photo section
    children.append({
        "object": "block",
        "type": "heading_3",
        "heading_3": {
            "rich_text": [{"type": "text", "text": {"content": "Photo"}}]
        }
    })
    if thumbnail_url:
        children.append({
            "object": "block",
            "type": "image",
            "image": {
                "type": "external",
                "external": {"url": thumbnail_url}
            }
        })
    else:
        children.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": "Ajouter une photo de la recette."}}]
            }
        })

    # Ingredients
    children.append({
        "object": "block",
        "type": "heading_3",
        "heading_3": {
            "rich_text": [{"type": "text", "text": {"content": "Ingrédients"}}]
        }
    })
    if ingredients:
        for ing in ingredients:
            children.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": ing}}]
                }
            })
    else:
        children.append({
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [{"type": "text", "text": {"content": "Ajouter les ingrédients."}}]
            }
        })

    # Temps de préparation
    children.append({
        "object": "block",
        "type": "heading_3",
        "heading_3": {
            "rich_text": [{"type": "text", "text": {"content": "Temps de préparation"}}]
        }
    })
    children.append({
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": prep_time_text or "@mentionn"}}]
        }
    })

    # Étapes
    children.append({
        "object": "block",
        "type": "heading_3",
        "heading_3": {
            "rich_text": [{"type": "text", "text": {"content": "Étapes"}}]
        }
    })
    if steps:
        for s in steps:
            children.append({
                "object": "block",
                "type": "numbered_list_item",
                "numbered_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": s}}]
                }
            })
    else:
        children.append({
            "object": "block",
            "type": "numbered_list_item",
            "numbered_list_item": {
                "rich_text": [{"type": "text", "text": {"content": "Ajouter les étapes."}}]
            }
        })

    # Lien vers la recette originale
    children.append({
        "object": "block",
        "type": "heading_3",
        "heading_3": {
            "rich_text": [{"type": "text", "text": {"content": "Lien vers la recette originale"}}]
        }
    })
    children.append({
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{
                "type": "text",
                "text": {
                    "content": "Renseignez l'URL dans la propriété \"Lien vers la recette\" de cette page."
                }
            }]
        }
    })

    payload = {
        "parent": {"database_id": database_id},
        "properties": properties,
        "children": children
    }
    resp = requests.post(f"{NOTION_API_BASE}/pages", headers=_headers(token), json=payload, timeout=30)
    if not resp.ok:
        raise RuntimeError(f"Notion API error {resp.status_code}: {resp.text}")
    return resp.json()

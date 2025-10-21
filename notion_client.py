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
    servings: Optional[int] = None,
    prep_minutes: Optional[int] = None,
    cook_minutes: Optional[int] = None,
    tags: Optional[List[str]] = None
) -> Dict:
    properties = {
        "Name": {"title": [{"text": {"content": title}}]}
    }
    if source_url:
        properties["Source URL"] = {"url": source_url}
    if servings is not None:
        properties["Servings"] = {"number": servings}
    if prep_minutes is not None:
        properties["Prep Time (min)"] = {"number": prep_minutes}
    if cook_minutes is not None:
        properties["Cook Time (min)"] = {"number": cook_minutes}
    if tags:
        properties["Tags"] = {"multi_select": [{"name": t} for t in tags]}

    children = []
    if ingredients:
        children.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": [{"type":"text","text":{"content":"Ingrédients / Ingredients"}}]}
        })
        for ing in ingredients:
            children.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text":[{"type":"text","text":{"content": ing}}]}
            })
    if steps:
        children.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": [{"type":"text","text":{"content":"Étapes / Steps"}}]}
        })
        for s in steps:
            children.append({
                "object": "block",
                "type": "numbered_list_item",
                "numbered_list_item": {"rich_text":[{"type":"text","text":{"content": s}}]}
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

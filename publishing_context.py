from typing import Any, List, Optional

from recipe_models import PublishingContext, RecipeContent


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


class PublishingContextBuilder:
    """Encapsulates publishing metadata creation."""

    def __init__(self, default_tags: Optional[List[str]] = None):
        self.default_tags = default_tags or ["TikTok"]

    def build(self, source_url: str, recipe: RecipeContent, video_meta: Any) -> PublishingContext:
        return PublishingContext(
            source_url=source_url,
            tags=self.default_tags,
            prep_time_text=format_prep_time(recipe.prep_minutes),
            thumbnail_url=extract_thumbnail(video_meta)
        )

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RecipeContent:
    """Structured representation of a recipe."""

    title: str
    ingredients: List[str] = field(default_factory=list)
    steps: List[str] = field(default_factory=list)
    prep_minutes: Optional[int] = None


@dataclass
class PublishingContext:
    """Metadata required when publishing a recipe to external targets."""

    source_url: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    prep_time_text: Optional[str] = None
    thumbnail_url: Optional[str] = None

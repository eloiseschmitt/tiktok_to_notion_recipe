from recipe_extractor import (
    combine_title_transcript,
    extract_ingredients_from_title,
    tidy_recipe_lists,
    estimate_prep_time,
    RecipeExtractor,
)
from publishing_context import PublishingContextBuilder
from recipe_models import RecipeContent


def test_combine_title_transcript_skips_empty_parts():
    result = combine_title_transcript("Titre", "")
    assert result == "Titre"

    result = combine_title_transcript("Titre", "Texte")
    assert result == "Titre\n\nTexte"


def test_extract_ingredients_from_title_detects_keywords():
    title = "Pizza maison - ingrédients: mozzarella, tomate, basilic"
    assert extract_ingredients_from_title(title) == ["mozzarella", "tomate", "basilic"]


def test_tidy_recipe_lists_moves_ingredient_like_steps():
    ingredients = ["- 200 g farine"]
    steps = [
        "- 1 oeuf",
        "Mélanger la pâte",
        "Recette secrète",
    ]

    cleaned_ingredients, cleaned_steps = tidy_recipe_lists(ingredients, steps, "Recette secrète")

    assert cleaned_ingredients == ["200 g farine", "1 oeuf"]
    assert cleaned_steps == ["Mélanger la pâte"]


def test_estimate_prep_time_from_text_and_steps():
    text = "Préparez en 1 h 15 min."
    assert estimate_prep_time(text, ["Étape 1"]) == 75

    text = "Pas d'indication"
    # fallback: 6 minutes per step, minimum 10
    assert estimate_prep_time(text, ["Étape 1", "Étape 2"]) == 12


def test_recipe_extractor_builds_recipe_without_gpt():
    transcript = """
    - 100 g chocolat
    - 50 g beurre
    Faire fondre le chocolat et le beurre.
    Mélanger.
    """.strip()
    extractor = RecipeExtractor(use_gpt=False, api_key_available=False)
    recipe = extractor.build(transcript, "Fondant chocolat")

    assert recipe.title == "Fondant chocolat"
    assert recipe.ingredients[:2] == ["100 g chocolat", "50 g beurre"]
    assert "Mélanger." in recipe.steps[-1]


def test_publishing_context_builder_uses_default_tags():
    recipe = RecipeContent(title="Test", ingredients=[], steps=[], prep_minutes=20)
    builder = PublishingContextBuilder()
    context = builder.build("https://example.com", recipe, {"thumbnail": "https://img"})

    assert context.tags == ["TikTok"]
    assert context.prep_time_text == "Environ 20 minutes"
    assert context.thumbnail_url == "https://img"

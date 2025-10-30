from pathlib import Path

from parser import guess_ingredients_and_steps, normalize_title
from tiktok_to_notion import (
    combine_title_transcript,
    extract_ingredients_from_title,
    tidy_recipe_lists,
    render_markdown,
)


APPROVAL_DIR = Path(__file__).parent / "approvals"


def _approval_path(name: str) -> Path:
    return APPROVAL_DIR / f"{name}.approved.txt"


def assert_approval(name: str, content: str) -> None:
    path = _approval_path(name)
    if not path.exists():
        raise AssertionError(
            f"Missing approval file for '{name}'. Create {path} with expected contents."
        )
    expected = path.read_text(encoding="utf-8")
    assert content == expected, f"Approval mismatch for '{name}'."


FIXTURE_TITLE = "Pâtes crémeuses au poulet - ingrédients: poulet, crème, parmesan"
FIXTURE_TRANSCRIPT = """
- 200 g de poulet
- 1 oignon
- 1 gousse d'ail
Faites revenir le poulet quelques minutes.
Ajoutez l'oignon et l'ail puis laissez cuire.
Versez la crème et mélangez doucement.
Parsemez de parmesan et servez chaud.
""".strip()


def run_fixture_pipeline():
    combined = combine_title_transcript(FIXTURE_TITLE, FIXTURE_TRANSCRIPT)
    ingredients, steps = guess_ingredients_and_steps(combined)

    extras = extract_ingredients_from_title(FIXTURE_TITLE)
    existing_lower = {ing.lower() for ing in ingredients}
    for extra in extras:
        lowered = extra.lower()
        if lowered not in existing_lower:
            ingredients.append(extra)
            existing_lower.add(lowered)

    ingredients, steps = tidy_recipe_lists(ingredients, steps, FIXTURE_TITLE)

    markdown = render_markdown(
        normalize_title(FIXTURE_TITLE),
        ingredients,
        steps,
        source_url="https://example.com/video",
    )

    return ingredients, steps, markdown


def test_fixture_ingredients_and_steps_match_approvals():
    ingredients, steps, markdown = run_fixture_pipeline()

    assert_approval("ingredients", "\n".join(ingredients) + "\n")
    assert_approval("steps", "\n".join(steps) + "\n")
    assert_approval("markdown", markdown)

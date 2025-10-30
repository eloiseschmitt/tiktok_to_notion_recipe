from parser import guess_ingredients_and_steps, normalize_title, split_sentences


def test_guess_ingredients_and_steps_extracts_bullets_and_sentences():
    transcript = """
    - 200 g de farine
    - 1 oeuf
    Mélangez les ingrédients.
    Faites cuire 10 minutes.
    """.strip()

    ingredients, steps = guess_ingredients_and_steps(transcript)

    assert ingredients == ["200 g de farine", "1 oeuf"]
    assert steps == ["Mélangez les ingrédients.", "Faites cuire 10 minutes."]


def test_split_sentences_handles_line_breaks_inside_paragraph():
    text = "Mélanger.\\nCuire.\\nServir."
    assert split_sentences(text) == ["Mélanger.", "Cuire.", "Servir."]


def test_normalize_title_removes_hashtags_and_whitespace():
    assert normalize_title("  #Pasta #Dinner  Recette magique!!!  ") == "Recette magique!!!"

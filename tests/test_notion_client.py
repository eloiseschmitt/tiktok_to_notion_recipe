from notion_client import create_recipe_page


class DummyResponse:
    ok = True

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return {"id": "dummy", "payload": self._payload}


def test_create_recipe_page_builds_expected_payload(monkeypatch):
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return DummyResponse(json)

    monkeypatch.setattr("notion_client.requests.post", fake_post)

    result = create_recipe_page(
        token="secret-token",
        database_id="db123",
        title="Tarte aux pommes",
        source_url="https://example.com",
        ingredients=["2 pommes", "100 g sucre"],
        steps=["Couper les pommes", "Cuire"],
        tags=["Dessert"],
        prep_minutes=30,
        prep_time_text="Environ 30 minutes",
        thumbnail_url="https://image.example.com"
    )

    assert result["id"] == "dummy"
    payload = captured["json"]

    assert payload["parent"] == {"database_id": "db123"}
    assert payload["properties"]["Nom"]["title"][0]["text"]["content"] == "Tarte aux pommes"
    assert payload["properties"]["Lien vers la recette"]["url"] == "https://example.com"
    assert payload["properties"]["Tags"]["multi_select"] == [{"name": "Dessert"}]
    assert payload["properties"]["Temps (min)"]["number"] == 30

    # Check ingredients preserved as bulleted list
    ingredient_blocks = [
        block for block in payload["children"] if block["type"] == "bulleted_list_item"
    ]
    assert [
        block["bulleted_list_item"]["rich_text"][0]["text"]["content"]
        for block in ingredient_blocks
    ] == ["2 pommes", "100 g sucre"]

    # Ensure steps are numbered
    step_blocks = [
        block for block in payload["children"] if block["type"] == "numbered_list_item"
    ]
    assert [
        block["numbered_list_item"]["rich_text"][0]["text"]["content"]
        for block in step_blocks
    ] == ["Couper les pommes", "Cuire"]

    # Thumbnail block should be an external image
    image_block = next(block for block in payload["children"] if block["type"] == "image")
    assert image_block["image"]["external"]["url"] == "https://image.example.com"

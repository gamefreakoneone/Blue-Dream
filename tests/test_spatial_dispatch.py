import asyncio
from types import SimpleNamespace


def test_qwen_coordinate_conversion_both_conventions():
    from Blue_dream_agents.spatial import qwen_box_to_gemini

    normalized = qwen_box_to_gemini(
        [100, 200, 700, 800], image_width=2000, image_height=1000
    )
    absolute = qwen_box_to_gemini(
        [200, 200, 1400, 800],
        image_width=2000,
        image_height=1000,
        convention="absolute_pixels",
    )
    assert normalized.box_2d == [200, 100, 800, 700]
    assert absolute.box_2d == [200, 100, 800, 700]


def test_qwen_spatial_dispatch_and_render(monkeypatch, tmp_path):
    from PIL import Image
    from Blue_dream_agents import spatial

    image_path = tmp_path / "book.jpg"
    Image.new("RGB", (200, 100)).save(image_path)
    captured = {}

    async def localize(**kwargs):
        captured["task"] = kwargs["task"]
        return spatial.QwenSpatialPayload(
            bbox_2d=[100, 200, 700, 800], label="story book"
        )

    async def render(**kwargs):
        captured["box"] = kwargs["bounding_box"].box_2d
        return "Storage/highlighted/storybook.png"

    monkeypatch.setattr(
        spatial,
        "get_provider_settings",
        lambda: SimpleNamespace(spatial_provider="qwen"),
    )
    monkeypatch.setattr(spatial, "invoke_multimodal_structured", localize)
    monkeypatch.setattr(spatial, "render_highlighted_image", render)
    result = asyncio.run(spatial.highlight_object(str(image_path), "story book"))
    assert result == "Storage/highlighted/storybook.png"
    assert captured == {"task": "spatial", "box": [200, 100, 800, 700]}


def test_qwen_spatial_failure_falls_back_to_gemini(monkeypatch):
    from Blue_dream_agents import spatial

    async def fail(*args, **kwargs):
        raise RuntimeError("Qwen unavailable")

    async def gemini(**kwargs):
        return "Storage/highlighted/gemini.png"

    monkeypatch.setattr(
        spatial,
        "get_provider_settings",
        lambda: SimpleNamespace(spatial_provider="qwen"),
    )
    monkeypatch.setattr(spatial, "_highlight_with_qwen", fail)
    monkeypatch.setattr(spatial, "highlight_object_with_gemini", gemini)
    result = asyncio.run(spatial.highlight_object("image.jpg", "story book"))
    assert result == "Storage/highlighted/gemini.png"


def test_gemini_spatial_reuses_fenced_and_embedded_json_hardening():
    from Blue_dream_agents.gemini_spatial import parse_gemini_spatial_response

    responses = (
        '```json\n[{"box_2d":[10,20,300,400],"label":"book"}]\n```',
        'Result: {"boxes":[{"box_2d":[10,20,300,400],"label":"book"}]} done.',
    )
    for raw_text in responses:
        result = parse_gemini_spatial_response(raw_text)
        assert result.found is True
        assert result.bounding_box.box_2d == [10, 20, 300, 400]
        assert result.bounding_box.label == "book"

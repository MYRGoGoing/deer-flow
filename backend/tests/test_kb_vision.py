from types import SimpleNamespace

import httpx
import pytest

from deerflow.community.kb_search.config import VisionConfig
from deerflow.community.kb_search.vision import (
    OpenAICompatibleVisionExtractor,
    get_vision_extractor,
)


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


def test_openai_compatible_vision_sends_data_uri_and_returns_text():
    requests = []

    def post(url, json):
        requests.append((url, json))
        return FakeResponse({"choices": [{"message": {"content": "主轴温度上限为 80 摄氏度"}}]})

    extractor = OpenAICompatibleVisionExtractor(
        VisionConfig(
            backend="openai",
            base_url="https://example.invalid/v1",
            model="vision-model",
            max_retries=0,
        ),
        "secret",
        client=SimpleNamespace(post=post),
    )

    result = extractor.extract(b"png-bytes", "image/png", context="manual.pdf 第 2 页")

    assert result == "主轴温度上限为 80 摄氏度"
    assert requests[0][0] == "https://example.invalid/v1/chat/completions"
    content = requests[0][1]["messages"][0]["content"]
    assert "manual.pdf 第 2 页" in content[0]["text"]
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_openai_compatible_vision_retries_transport_error(monkeypatch):
    calls = 0

    def post(_url, json):
        nonlocal calls
        del json
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("temporary failure")
        return FakeResponse({"choices": [{"message": {"content": "recovered"}}]})

    monkeypatch.setattr("deerflow.community.kb_search.vision.time.sleep", lambda _delay: None)
    extractor = OpenAICompatibleVisionExtractor(
        VisionConfig(backend="openai", model="vision-model", max_retries=1),
        "secret",
        client=SimpleNamespace(post=post),
    )

    assert extractor.extract(b"image", "image/png") == "recovered"
    assert calls == 2


def test_openai_compatible_vision_rejects_invalid_response():
    extractor = OpenAICompatibleVisionExtractor(
        VisionConfig(backend="openai", model="vision-model", max_retries=0),
        "secret",
        client=SimpleNamespace(post=lambda *_args, **_kwargs: FakeResponse({"choices": []})),
    )

    with pytest.raises(RuntimeError, match="Vision extraction request failed"):
        extractor.extract(b"image", "image/png")


def test_get_vision_extractor_requires_model_and_key(monkeypatch):
    for name in ("KB_VISION_API_KEY", "SILICONFLOW_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(RuntimeError, match="requires KB_VISION_MODEL"):
        get_vision_extractor(VisionConfig(backend="openai"))
    with pytest.raises(RuntimeError, match="requires KB_VISION_API_KEY"):
        get_vision_extractor(VisionConfig(backend="openai", model="vision-model"))


def test_get_vision_extractor_none_backend_needs_no_credentials():
    assert get_vision_extractor(VisionConfig()) is None

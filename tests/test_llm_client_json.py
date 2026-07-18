import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import BaseModel


class StructuredResult(BaseModel):
    answer: str
    count: int


class ChatStub:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        content = next(self.responses)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )


class EmbeddingStub:
    def __init__(self, dimension):
        self.dimension = dimension
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            data=[
                SimpleNamespace(index=index, embedding=[float(index)] * self.dimension)
                for index, _ in enumerate(kwargs["input"])
            ]
        )


def _configure_qwen(monkeypatch, **extra):
    from Blue_dream_agents.llm.model_registry import get_model_registry
    from Blue_dream_agents.llm.settings import get_provider_settings

    values = {
        "LLM_PROVIDER": "qwen",
        "EMBEDDING_PROVIDER": "qwen",
        "DASHSCOPE_API_KEY": "test-key",
    }
    values.update(extra)
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    get_provider_settings.cache_clear()
    get_model_registry.cache_clear()


def _fake_client(chat=None, embeddings=None, transcriptions=None):
    return SimpleNamespace(
        chat=SimpleNamespace(completions=chat),
        embeddings=embeddings,
        audio=SimpleNamespace(transcriptions=transcriptions),
    )


@pytest.mark.parametrize(
    "raw",
    [
        '```json\n{"answer":"ok","count":1}\n```',
        'Here is the result: {"answer":"ok","count":1} thanks.',
    ],
)
def test_structured_json_fences_and_embedded_payload(monkeypatch, raw):
    _configure_qwen(monkeypatch)
    from Blue_dream_agents.llm import client

    chat = ChatStub([raw])
    monkeypatch.setattr(client, "_get_client", lambda target: _fake_client(chat=chat))
    result = asyncio.run(
        client.invoke_structured(
            prompt="return data",
            output_model=StructuredResult,
            system_prompt="system",
        )
    )
    assert result == StructuredResult(answer="ok", count=1)
    assert chat.calls[0]["response_format"] == {"type": "json_object"}
    assert chat.calls[0]["extra_body"] == {"enable_thinking": False}


def test_structured_invalid_then_valid_strict_retry(monkeypatch):
    _configure_qwen(monkeypatch)
    from Blue_dream_agents.llm import client

    chat = ChatStub(['{"answer":"missing count"}', '{"answer":"ok","count":2}'])
    monkeypatch.setattr(client, "_get_client", lambda target: _fake_client(chat=chat))
    result = asyncio.run(
        client.invoke_structured(
            prompt="return data",
            output_model=StructuredResult,
            system_prompt="system",
        )
    )
    assert result.count == 2
    assert len(chat.calls) == 2
    assert "previous response was not valid JSON" in chat.calls[1]["messages"][-1]["content"]


def test_multimodal_and_video_message_shapes(monkeypatch, tmp_path):
    _configure_qwen(monkeypatch, VIDEO_PROVIDER="qwen")
    from Blue_dream_agents.llm import client

    image_path = tmp_path / "frame.jpg"
    image_path.write_bytes(b"jpeg-bytes")
    chat = ChatStub(
        [
            '{"answer":"image","count":1}',
            '{"answer":"video","count":2}',
            '{"answer":"frames","count":3}',
        ]
    )
    monkeypatch.setattr(client, "_get_client", lambda target: _fake_client(chat=chat))

    asyncio.run(
        client.invoke_multimodal_structured(
            text_prompt="inspect",
            image_path=str(image_path),
            output_model=StructuredResult,
        )
    )
    asyncio.run(
        client.invoke_video_structured(
            video_url="https://example.test/video.mp4",
            output_model=StructuredResult,
        )
    )
    asyncio.run(
        client.invoke_video_structured(
            frame_paths=[image_path],
            output_model=StructuredResult,
        )
    )

    image_content = chat.calls[0]["messages"][-1]["content"]
    assert image_content[1]["type"] == "image_url"
    assert image_content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    video_content = chat.calls[1]["messages"][-1]["content"]
    assert video_content[1] == {
        "type": "video_url",
        "video_url": {"url": "https://example.test/video.mp4"},
    }
    frame_content = chat.calls[2]["messages"][-1]["content"]
    assert "sequential frames" in frame_content[0]["text"]
    assert frame_content[1]["type"] == "image_url"


def test_embed_batching_and_dimension_validation(monkeypatch):
    _configure_qwen(
        monkeypatch,
        LLM_EMBEDDING_DIM="3",
        EMBED_BATCH_SIZE="2",
    )
    from Blue_dream_agents.llm import client

    embeddings = EmbeddingStub(3)
    monkeypatch.setattr(
        client, "_get_client", lambda target: _fake_client(embeddings=embeddings)
    )
    result = asyncio.run(client.embed_texts(["a", "b", "c", "d", "e"]))
    assert len(result) == 5
    assert [len(call["input"]) for call in embeddings.calls] == [2, 2, 1]
    assert all(call["dimensions"] == 3 for call in embeddings.calls)

    bad_embeddings = EmbeddingStub(2)
    monkeypatch.setattr(
        client,
        "_get_client",
        lambda target: _fake_client(embeddings=bad_embeddings),
    )
    with pytest.raises(ValueError, match="returned 2 dimensions; expected 3"):
        asyncio.run(client.embed_texts(["bad dimension"]))


def test_embed_texts_restores_sdk_index_order_across_batches(monkeypatch):
    _configure_qwen(
        monkeypatch,
        LLM_EMBEDDING_DIM="2",
        EMBED_BATCH_SIZE="2",
    )
    from Blue_dream_agents.llm import client

    class ReverseOrderEmbeddingStub:
        async def create(self, **kwargs):
            rows = [
                SimpleNamespace(index=index, embedding=[float(ord(text)), 0.0])
                for index, text in enumerate(kwargs["input"])
            ]
            return SimpleNamespace(data=list(reversed(rows)))

    monkeypatch.setattr(
        client,
        "_get_client",
        lambda target: _fake_client(embeddings=ReverseOrderEmbeddingStub()),
    )
    result = asyncio.run(client.embed_texts(["a", "b", "c"]))
    assert [embedding[0] for embedding in result] == [97.0, 98.0, 99.0]


def test_openai_and_qwen_transcription_payload_shapes(monkeypatch, tmp_path):
    from Blue_dream_agents.llm import client
    from Blue_dream_agents.llm.model_registry import get_model_registry
    from Blue_dream_agents.llm.settings import get_provider_settings

    audio_path = tmp_path / "Recording.m4a"
    audio_path.write_bytes(b"audio")

    class TranscriptionStub:
        def __init__(self):
            self.calls = []

        async def create(self, **kwargs):
            self.calls.append((kwargs["model"], Path(kwargs["file"].name).name))
            return SimpleNamespace(text="hello")

    transcription = TranscriptionStub()
    monkeypatch.setenv("TRANSCRIBE_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_TRANSCRIBE_API_KEY", "test-key")
    get_provider_settings.cache_clear()
    get_model_registry.cache_clear()
    monkeypatch.setattr(
        client,
        "_get_client",
        lambda target: _fake_client(transcriptions=transcription),
    )
    assert asyncio.run(client.transcribe_audio(audio_path)) == "hello"
    assert transcription.calls == [("gpt-4o-transcribe", "Recording.m4a")]

    monkeypatch.setenv("TRANSCRIBE_PROVIDER", "qwen")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    get_provider_settings.cache_clear()
    get_model_registry.cache_clear()
    chat = ChatStub(["hello from qwen"])
    monkeypatch.setattr(client, "_get_client", lambda target: _fake_client(chat=chat))
    assert asyncio.run(client.transcribe_audio(audio_path)) == "hello from qwen"
    call = chat.calls[0]
    assert call["model"] == "qwen3-asr-flash"
    audio_part = call["messages"][0]["content"][0]
    assert audio_part["type"] == "input_audio"
    assert audio_part["input_audio"]["data"].startswith(
        "data:audio/mp4;base64,"
    )

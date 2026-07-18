import pytest


def _reset(monkeypatch, **values):
    from Blue_dream_agents.llm.model_registry import get_model_registry
    from Blue_dream_agents.llm.settings import get_provider_settings

    for name, value in values.items():
        monkeypatch.setenv(name, value)
    get_provider_settings.cache_clear()
    get_model_registry.cache_clear()


def test_qwen_presets_and_key_fallback(monkeypatch):
    _reset(
        monkeypatch,
        LLM_PROVIDER="qwen",
        EMBEDDING_PROVIDER="qwen",
        DASHSCOPE_API_KEY="",
        QWEN_APIKEY="fallback-key",
    )
    from Blue_dream_agents.llm.model_registry import resolve

    assert resolve("router").model == "qwen3.7-plus"
    assert resolve("router").disable_thinking is True
    assert resolve("judge").disable_thinking is True
    assert resolve("synthesis").model == "qwen3.7-plus"
    assert resolve("vision").model == "qwen3-vl-flash"
    assert resolve("spatial").model == "qwen3-vl-plus"
    assert resolve("video").model == "qwen3-vl-flash"
    embedding = resolve("embedding")
    assert embedding.model == "text-embedding-v4"
    assert embedding.embedding_dim == 1024
    assert embedding.api_key == "fallback-key"
    assert embedding.supports_json_object is True
    assert resolve("transcribe").model == "qwen3-asr-flash"


def test_capability_override_precedence(monkeypatch):
    _reset(
        monkeypatch,
        LLM_PROVIDER="qwen",
        EMBEDDING_PROVIDER="openai",
        DASHSCOPE_API_KEY="qwen-key",
        OPENAI_API_KEY="openai-key",
        LLM_EMBEDDING_MODEL="custom-embedding",
        LLM_EMBEDDING_DIM="42",
    )
    from Blue_dream_agents.llm.model_registry import resolve

    assert resolve("text").provider == "qwen"
    target = resolve("embedding")
    assert target.provider == "openai"
    assert target.model == "custom-embedding"
    assert target.embedding_dim == 42


def test_ollama_endpoint_is_openai_compatible(monkeypatch):
    _reset(
        monkeypatch,
        LLM_PROVIDER="ollama",
        EMBEDDING_PROVIDER="ollama",
        OLLAMA_BASE_URL="http://localhost:11434/",
    )
    from Blue_dream_agents.llm.model_registry import resolve

    target = resolve("judge")
    assert target.base_url == "http://localhost:11434/v1"
    assert target.api_key == "ollama"
    assert target.model == "gemma4:e2b"


def test_missing_provider_key_names_the_variable(monkeypatch):
    _reset(
        monkeypatch,
        LLM_PROVIDER="qwen",
        DASHSCOPE_API_KEY="",
        QWEN_APIKEY="",
    )
    from Blue_dream_agents.llm.model_registry import resolve

    with pytest.raises(RuntimeError, match="DASHSCOPE_API_KEY.*QWEN_APIKEY"):
        resolve("router")


def test_transcribe_uses_legacy_dedicated_openai_key(monkeypatch):
    _reset(
        monkeypatch,
        TRANSCRIBE_PROVIDER="openai",
        OPENAI_TRANSCRIBE_API_KEY="transcribe-key",
        OPENAI_API_KEY="",
    )
    from Blue_dream_agents.llm.model_registry import resolve

    target = resolve("transcribe")
    assert target.model == "gpt-4o-transcribe"
    assert target.api_key == "transcribe-key"


def test_gemini_and_none_targets_are_resolvable(monkeypatch):
    _reset(
        monkeypatch,
        VIDEO_PROVIDER="gemini",
        GEMINI_API_KEY="gemini-key",
        TTS_PROVIDER="none",
    )
    from Blue_dream_agents.llm.model_registry import resolve

    assert resolve("video").provider == "gemini"
    assert resolve("tts").provider == "none"

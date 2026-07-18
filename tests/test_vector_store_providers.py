def _configure(monkeypatch, provider, persist_dir):
    from Blue_dream_agents.llm.model_registry import get_model_registry
    from Blue_dream_agents.llm.settings import get_provider_settings

    monkeypatch.setenv("LLM_PROVIDER", provider)
    monkeypatch.setenv("EMBEDDING_PROVIDER", provider)
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(persist_dir))
    monkeypatch.setenv("DASHSCOPE_API_KEY", "qwen-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.delenv("LLM_EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("LLM_EMBEDDING_DIM", raising=False)
    get_provider_settings.cache_clear()
    get_model_registry.cache_clear()


def test_provider_switch_creates_sibling_collections(monkeypatch, tmp_path):
    from Blue_dream_agents import vector_store

    vector_store.clear_cached_clients()
    _configure(monkeypatch, "qwen", tmp_path)
    qwen = vector_store.get_event_collection()
    assert qwen.name == "memory_events__qwen__text-embedding-v4__1024"

    _configure(monkeypatch, "openai", tmp_path)
    openai = vector_store.get_event_collection()
    assert openai.name == "memory_events__openai__text-embedding-3-small__1536"

    names = {item.name for item in vector_store.get_chroma_client().list_collections()}
    assert qwen.name in names
    assert openai.name in names

    vector_store.reset_active_event_collection()
    names_after = {
        item.name for item in vector_store.get_chroma_client().list_collections()
    }
    assert qwen.name in names_after
    assert openai.name in names_after


def test_metadata_mismatch_recreates_only_active_collection(monkeypatch, tmp_path):
    from Blue_dream_agents import vector_store

    vector_store.clear_cached_clients()
    _configure(monkeypatch, "qwen", tmp_path)
    client = vector_store.get_chroma_client()
    name = vector_store.get_event_collection_name()
    client.create_collection(
        name=name,
        metadata={"provider": "wrong", "model": "wrong", "dim": 1},
    )

    collection = vector_store.get_event_collection()
    assert collection.metadata["provider"] == "qwen"
    assert collection.metadata["model"] == "text-embedding-v4"
    assert collection.metadata["dim"] == 1024

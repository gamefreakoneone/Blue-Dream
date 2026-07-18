# Blue-Dream Memory Architecture Reference

> This document describes the **current** memory architecture for benchmarking and migration reference. It is accurate as of the validated Phase 2.6 baseline.

---

## 1. High-Level Overview

The system uses a **two-tier storage model**:

1. **MongoDB** — Source of truth for all memory events.
2. **ChromaDB** — Semantic vector index for similarity-based recall only.

The query layer is **agentic and LLM-driven**:
- A central router (`jeeves.py`) classifies each user query into an intent.
- Each intent dispatches to a specialized retrieval path.
- Retrieved evidence is fed back into an LLM for synthesis and patient-facing answers.

---

## 2. Memory Event Schema

The canonical model is **`MemoryEvent`** (`Blue_dream_agents/memory_schema.py`).

### Fields

| Field | Type | Source |
|-------|------|--------|
| `event_id` | `str` | Mongo `ObjectId` as string |
| `timestamp` | `datetime.datetime` | Local-timezone normalized |
| `room_number` | `int` | Shared map: `0 = Bedroom`, `1 = Living Room` |
| `room_name` | `str` | Derived from `room_number` via `ROOMS` map |
| `video_description` | `str` | Gemini full-video analysis |
| `room_objects` | `list[str]` | Objects detected in the video |
| `audio_transcript` | `str` | OpenAI `gpt-4o-transcribe` |
| `screenshot_path` | `str` | Last frame image file path |
| `video_path` | `str` | Recording file path (used for idempotency) |
| `audio_path` | `str` | Audio file path |
| `semantic_text` | `str` | **Auto-built at ingestion** (see below) |

### `semantic_text` Construction

`semantic_text` is **not** passed by the caller. It is assembled inside `new_memory_event()` by calling `build_semantic_text(event)`:

```
Room: {room_name}
Time: {timestamp formatted as '%Y-%m-%d %I:%M %p'}
Video: {video_description}   ← omitted if blank
Audio: {audio_transcript}     ← omitted if blank
Objects: {comma-joined room_objects}  ← omitted if empty
```

This concatenated string is what gets embedded into ChromaDB and is the primary text representation used by semantic search.

### Legacy Normalization

`memory_event_from_mongo()` normalizes legacy documents at read time:
- Missing `event_id` falls back to `_id`
- Missing `room_name` falls back to the shared `ROOMS` map
- Missing `semantic_text` is rebuilt from the other fields

---

## 3. Storage Layer Details

### 3a. MongoDB

- **Database:** `dementia_assistance`
- **Collection:** `events`
- **Driver:** `motor` (async MongoDB driver)
- **Document format:** BSON; `ObjectId` is stored in `_id`

**Indexes** (created at API startup and consolidator ingestion):
```python
{ "timestamp": 1 }
{ "room_number": 1, "timestamp": -1 }
{ "event_id": 1 }
{ "video_path": 1 }
```

The `video_path` index supports ingestion idempotency: reprocessing the same video skips duplicate inserts.

### 3b. ChromaDB

- **Purpose:** Semantic similarity search **only**
- **Persistence:** Local filesystem under `Storage/chroma`
- **Collection name:** `memory_events` (configurable via `CHROMA_COLLECTION_NAME`)
- **Active embedding model:** `nomic-embed-text` via Ollama (768-D)
- **Legacy embedding model:** `amazon.nova-2-multimodal-embeddings-v1:0` via Bedrock

**What Chroma stores per event:**
- `event_id` (as the Chroma document ID)
- `embeddings` — the vector
- `metadatas` — lightweight dict:
  ```json
  {
    "event_id": "...",
    "room_number": 1,
    "room_name": "Living Room",
    "timestamp": "2026-04-18T14:30:00",
    "has_screenshot": true,
    "embedding_provider": "ollama",
    "embedding_model": "nomic-embed-text",
    "embedding_dimension": 768
  }
  ```

**Critical behavior:** Chroma is used for **pure similarity search only**.

The query flow is:
1. Embed the user query text → produces a query vector.
2. Call `collection.query(query_embeddings=[vector], n_results=top_k)`.
3. Chroma returns the closest vectors ordered by distance (no metadata filtering happens here).
4. The system extracts `event_id` from the returned metadata.
5. Full event records are fetched from MongoDB by `event_id`.

Chroma does **not** filter by room, timestamp, or any metadata during search. It is exclusively a nearest-neighbor engine.

---

## 4. Query Paths

### 4a. Semantic Search Path

**Trigger:** Fuzzy recall questions (e.g., *"Did I mention buying groceries?"*, *"What was I talking about earlier?"*)

**Pipeline (`semantic_search.py`):**
1. `ensure_semantic_index_synced()` — checks if Chroma index matches Mongo state, rebuilds if stale/mismatched.
2. `embed_text(query, "query", dimension)` — produces query embedding.
3. `query_similar_embeddings(query_embedding, top_k)` — Chroma nearest-neighbor search.
4. `_fetch_events_by_ids(matched_ids)` — Mongo lookup by `event_id` and `_id`.
5. Stale vectors (event IDs not found in Mongo) are detected and deleted from Chroma.
6. Returns `SemanticSearchResult` containing matches with `score`, `semantic_text`, `audio_transcript`, `video_description`, etc.

**Two entry points:**
- `run_semantic_retrieval(query)` → returns raw matches **without** LLM synthesis.
- `run_semantic_query(query)` → returns matches **with** LLM-summarized answer.

The `jeeves.py` path uses `run_semantic_retrieval` so it can apply its own judge logic before synthesis.

### 4b. Time-Based Path

**Trigger:** Timeline, activity history, transcript recall, or date-qualified questions (e.g., *"What was I doing today?"*, *"What did I say yesterday?"*)

**Pipeline (`time_agent.py`):**
1. Query planning:
   - Deterministic shortcuts first: speech-recall keywords (`talk`, `said`, `conversation`) + time reference → route to `transcripts` intent.
   - Otherwise, structured LLM call (`TimeQueryPlan`) extracts intent, time range, room, activity.
2. Time range parsing (`_build_time_filter`):
   - Supports: `today`, `yesterday`, `recently`, `last N hours/days`, ISO dates (`2026-04-18`), natural dates (`April 18 2026`).
3. Mongo query: `{ "timestamp": { "$gte": start, "$lte": end }, "room_number": ... }`
4. Events are sorted ascending by `timestamp`.
5. Prompt budgeting (`prompt_budget.py`) compacts event lists to a character budget before LLM calls.
6. An LLM synthesizes a warm, patient-facing summary (2–3 sentences) grounded in the events.

**Four intents:**
- `timeline` — activity history over a period
- `transcripts` — what was said/discussed
- `activity_check` — verify whether a specific activity happened
- `general` — fallback direct answer

### 4c. Object Search Path (Not Benchmarked)

**Trigger:** Lost physical items (e.g., *"Where are my keys?"*)

**Pipeline (`object_detector.py`):**
1. Parse query intent (`ObjectQueryIntent`) to extract target object and optional room.
2. Fetch latest snapshot per room from MongoDB (aggregation pipeline: sort by timestamp desc, group by room_number).
3. Multimodal vision check: send screenshot + prompt to local Gemma/Ollama to determine if object is visible.
4. If found: attempt Gemini spatial highlighting for bounding box.
5. If not found: fetch recent events (last 48h) and run structured LLM reasoning for last-known location.

This path requires vision/multimodal capabilities and is excluded from the time/semantic benchmark.

---

## 5. Routing Logic (`jeeves.py`)

### 5a. Conversation Context Resolution
- If `session_id` is provided, the query is rewritten into a standalone query using recent chat turns (`conversation_memory.py`).
- Object/time/semantic tools receive only the resolved standalone query.
- Full conversation history is used only for rewrite context and general-chat responses.

### 5b. Intent Routing

**Deterministic shortcuts (fast path):**
- Speech recall terms (`talk`, `said`, `conversation`, etc.) + time reference → `time` intent.

**Structured LLM router (`QueryRoute`):**
- `object` — lost physical item searches
- `time` — explicit time ranges, dates, activity history, room history
- `semantic` — fuzzy conversational recall, not primarily timeline-based
- `general` — greetings, unsupported chat

### 5c. Semantic Evidence Judge (`SemanticDecision`)

For `semantic` queries, after raw retrieval, a second structured LLM call decides:
- `use_semantic_only` — evidence is strong enough to answer directly.
- `use_semantic_plus_time_window` — evidence is relevant but needs timeline grounding around an anchor event → fetches `±20 min` window from Mongo.
- `use_direct_time_reasoning` — evidence is weak → fallback to time agent.
- `insufficient_evidence` — too weak to answer.

### 5d. Response Synthesis

A final LLM call (`_synthesize_semantic_answer`) consumes the evidence bundle (semantic matches + optional time window) and produces the patient-facing answer.

---

## 6. LLM Abstraction

### Text & Structured Calls
- **Entry point:** `Blue_dream_agents/llm/client.py`
- **Dispatch:** `LLM_PROVIDER=qwen|openai|ollama`, with per-capability overrides.
- **Protocol:** one cached `AsyncOpenAI` client per endpoint and credential pair.
- **Structured behavior:** provider JSON mode where supported, Markdown-fence
  stripping, embedded JSON extraction, Pydantic validation, and one strict retry.
- **Multimodal:** OpenAI-compatible base64 `image_url` content parts.

### Embeddings
- **Entry point:** `Blue_dream_agents/llm/client.py::embed_texts`
- **Protocol:** async OpenAI-compatible `/embeddings`, chunked and dimension-validated.
- **Collections:** `memory_events__{provider}__{model_slug}__{dim}` preserves
  sibling vector spaces when providers change.

---

## 7. Ingestion Pipeline (Brief)

The pipeline that produces events is **not** part of the benchmark runtime but is the source of the data:

```
Capture/camera_feed.py  → records video + audio when motion detected
  └─> Capture/video_processing_queue.py
        └─> consolidator_agent(video_path, audio_path, screenshot_path, room_number)
              ├─> Video_Agent (Gemini) → video_description + room_objects
              ├─> Audio_agent (OpenAI) → audio_transcript
              └─> new_memory_event(...) → MongoDB insert + Chroma index
```

The consolidator skips duplicate `video_path` inserts and persists partial results if one modality fails.

---

## 8. Configuration Summary (Production Defaults)

| Env Var | Default | Purpose |
|---------|---------|---------|
| `MONGODB_URI` | `mongodb://localhost:27017` | MongoDB connection |
| `LLM_PROVIDER` | `qwen` | Text reasoning backend |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint |
| `LLM_TEXT_MODEL` | provider preset | Router / synthesis / judge override |
| `LLM_VISION_MODEL` | provider preset | Object presence override |
| `EMBEDDING_PROVIDER` | `LLM_PROVIDER` | Embedding backend |
| `LLM_EMBEDDING_MODEL` | provider preset | Embedding model override |
| `LLM_EMBEDDING_DIM` | provider preset | Vector dimension override |
| `CHROMA_PERSIST_DIR` | `Storage/chroma` | Chroma filesystem path |
| `SEMANTIC_SEARCH_TOP_K` | `5` | Number of semantic matches |

---

## 9. Key Takeaways for Mem0 Benchmarking

1. **MongoDB stores the full event.** Chroma stores only the vector + `event_id`. Any Mem0 replacement must preserve or replace this two-tier pattern.
2. **Semantic search is pure vector similarity.** No metadata filtering in Chroma. Room/time filtering for semantic queries happens **after** retrieval or through the separate time agent.
3. **Time queries hit MongoDB directly** with timestamp ranges; the LLM is only used for summarization.
4. **The router (`jeeves.py`) is the brain.** It decides whether a question needs semantic recall, time lookup, or object search. Mem0’s temporal reasoning would need to demonstrate it can replace or improve upon this agentic routing + retrieval + synthesis stack.

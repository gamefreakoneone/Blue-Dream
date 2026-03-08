# Blue-Dream Overhaul Plan

## Purpose
- This file is the active execution roadmap for the Blue-Dream overhaul.
- Work proceeds feature-by-feature so changes can be validated in isolation.
- Only one feature should be actively implemented at a time unless explicitly coordinated.
- After each completed feature:
  - validate it
  - commit it
  - update `PLANS.md`
  - update `AGENTS.md`

## Execution Workflow
1. Select the next feature marked `Planned`.
2. Implement all required code and supporting tools for that feature.
3. Run targeted validation for that feature.
4. If stable, commit the feature to Git.
5. Update `PLANS.md`:
   - feature status
   - decisions made
   - follow-up tasks
6. Update `AGENTS.md`:
   - current architecture baseline
   - new source-of-truth files
   - new interfaces or constraints
7. Move to the next feature.

## Global Architecture Target
- The patient web app remains the only app surface.
- FastAPI remains the backend.
- MongoDB remains the source of truth for memory events.
- ChromaDB is added as the vector index.
- Amazon Nova is the primary reasoning stack for:
  - routing
  - semantic embeddings
  - semantic answer synthesis
  - voice
- Gemini remains the exception for:
  - video understanding
  - image bounding/localization

## Feature Status Legend
- `Planned`
- `In Progress`
- `Validated`
- `Committed`
- `Blocked`

## Feature Roadmap

### Feature 1: Nova Provider Integration and Routing Refactor
**Status:** Planned

**Goal**
- Replace hard-wired model usage with a provider abstraction so the backend can use Nova cleanly without breaking the current API contract.

**Primary outcome**
- `/query` still works.
- Routing and answer synthesis can use Nova.
- Current UI contract remains unchanged.

**Files expected to change**
- `Blue_dream_agents/jeeves.py`
- `Blue_dream_agents/api.py`
- new provider/client module
- possibly `requirements.txt`

**Required work**
- introduce a provider abstraction layer
- add Nova text client configuration
- refactor orchestrator logic to use provider methods instead of directly coupling to current OpenAI/Gemini paths where avoidable
- preserve the current `JeevesResponse` shape
- preserve object/time tool compatibility

**Acceptance criteria**
- existing text queries still return valid responses
- API contract is unchanged at the top level
- Nova can be used for routing and/or synthesis without frontend changes

**Commit gate**
- smoke test `/query`
- confirm object and time questions still route correctly

**AGENTS update after completion**
- update environment/secrets section with Nova credentials
- update architecture map to show provider abstraction
- update source-of-truth file list if new modules were added

### Feature 2: Canonical Memory Event Schema
**Status:** Planned

**Goal**
- Standardize how one memory event is represented across ingestion and retrieval.

**Primary outcome**
- Ingestion no longer relies only on an ad hoc raw dict.
- Retrieval logic can depend on one canonical event model.

**Files expected to change**
- `Blue_dream_agents/consolidator.py`
- `Blue_dream_agents/time_agent.py`
- `Blue_dream_agents/object_detector.py`
- new shared schema/model module

**Required work**
- introduce a canonical event model, recommended name: `MemoryEvent`
- include:
  - `event_id`
  - `timestamp`
  - `room_number`
  - `room_name`
  - `video_description`
  - `room_objects`
  - `audio_transcript`
  - `screenshot_path`
  - `video_path`
  - `audio_path`
  - `semantic_text`
- keep current Mongo collection and field compatibility
- adapt time/object read-models from this canonical event model where practical

**Acceptance criteria**
- consolidator inserts remain backward compatible
- time queries still work
- object queries still work

**Commit gate**
- verify Mongo insert payload still contains baseline required fields
- verify existing reads do not break

**AGENTS update after completion**
- update event ingestion contract
- document canonical event model as the new baseline

### Feature 3: Semantic Search Foundation
**Status:** Planned

**Goal**
- Add semantic memory retrieval using Nova Multimodal Embeddings and ChromaDB.

**Primary outcome**
- Semantic memory search exists as a first-class retrieval mode.

**Files expected to change**
- `Blue_dream_agents/consolidator.py`
- new `semantic_search` module
- new vector store module or helper
- `requirements.txt`

**Required work**
- add `semantic_text` generation during ingestion
- generate Nova embeddings for each event
- store vectors in ChromaDB keyed by Mongo event ID
- keep MongoDB as the source of truth
- retrieve top-k event IDs from Chroma
- fetch full records from Mongo for synthesis

**Storage rules**
- MongoDB stores full events.
- ChromaDB stores:
  - vector
  - event ID
  - lightweight metadata
- do not duplicate full event storage in Chroma

**Acceptance criteria**
- a semantic query can return relevant prior events
- vector index stays consistent with Mongo event IDs
- no existing time/object functionality regresses

**Commit gate**
- test at least 3 semantic queries against recorded data
- verify retrieved events map correctly back to Mongo records

**AGENTS update after completion**
- add ChromaDB to architecture map
- update environment/dependency notes
- document semantic retrieval flow

### Feature 4: Semantic-to-Time Fallback Reasoning
**Status:** Planned

**Goal**
- Add the multi-step analysis path where semantic retrieval can fall back to time-based context when needed.

**Primary outcome**
- Semantic answers become more grounded and less brittle.

**Files expected to change**
- `Blue_dream_agents/jeeves.py`
- `Blue_dream_agents/time_agent.py`
- `Blue_dream_agents/semantic_search.py`
- new query-routing or retrieval-policy module if needed

**Required work**
- classify queries into:
  - time
  - object
  - semantic
  - mixed
- for semantic or mixed queries:
  - run semantic retrieval first
  - analyze retrieval quality in structured form
  - decide whether fallback is needed
  - if needed, pull time-context events
  - synthesize final grounded answer
- define explicit fallback triggers:
  - low semantic confidence
  - weak similarity hits
  - transcript-poor results for conversation questions
  - temporal inconsistency
  - explicit time language in user query

**Acceptance criteria**
- semantic-only questions work
- mixed questions work
- fallback improves weak semantic answers instead of degrading them

**Commit gate**
- test:
  - `What was I talking to my son about today?`
  - `What was I doing in the bedroom this morning?`
  - one case where fallback is intentionally triggered

**AGENTS update after completion**
- update assistant request pipeline to include semantic and mixed retrieval
- document fallback logic as a project behavior

### Feature 5: Gemini Spatial Localization Replacement
**Status:** Planned

**Goal**
- Replace SAM3-based active object-highlighting logic with Gemini-based image bounding/localization.

**Primary outcome**
- Object localization is faster and simpler.
- Highlighted screenshots still work with the current frontend.

**Files expected to change**
- `Blue_dream_agents/object_detector.py`
- any SAM3-dependent modules
- image highlight utility
- possibly new Gemini spatial helper module

**Required work**
- remove SAM3 from the primary active path
- use Gemini to produce bounding box coordinates for the target object
- generate highlighted image server-side
- preserve returned `image_path`
- preserve `/capture` and `/storage` compatibility

**Acceptance criteria**
- object search still returns a useful highlighted image
- UI renders the result without changes
- latency is improved or at least simpler operationally than SAM3

**Commit gate**
- run multiple object-finding queries against stored screenshots
- confirm highlighted image paths resolve through the current static mounts

**AGENTS update after completion**
- remove SAM3 from active architecture notes
- note Gemini spatial localization as the current baseline

### Feature 6: Voice Support with Nova
**Status:** Planned

**Goal**
- Let the patient speak to Memoria instead of typing.

**Primary outcome**
- At least one stable end-to-end voice query path exists.

**Files expected to change**
- backend voice endpoint(s)
- `UI/index.html`
- `UI/script.js`
- optional styles update
- provider client module

**Required work**
- add browser audio capture
- send utterance to backend
- transcribe/process with Nova voice stack
- route the resulting query through the same retrieval system
- return text response and, if implemented, spoken response

**Acceptance criteria**
- one spoken query can complete end-to-end
- voice uses the same retrieval/routing stack as text
- text fallback remains available

**Commit gate**
- test at least:
  - one object voice query
  - one semantic or time voice query

**AGENTS update after completion**
- add voice support to architecture map
- add any new API endpoints and UI assumptions

### Feature 7: Demo and Submission Readiness
**Status:** Planned

**Goal**
- Prepare the project for the hackathon submission package.

**Primary outcome**
- Project can be demonstrated cleanly and documented accurately.

**Files expected to change**
- `README.md`
- `AGENTS.md`
- `PLANS.md`
- optional demo assets or scripts

**Required work**
- record a clean multi-room demo sequence
- finalize test instructions
- update README to match actual runtime commands and env vars
- prepare elevator pitch, description, and demo narrative
- document what changed during the submission period

**Acceptance criteria**
- demo can be reproduced locally
- documentation matches the real implementation
- submission narrative clearly states how Nova is used

**Commit gate**
- run through the full demo script once from scratch
- verify repo instructions are accurate

**AGENTS update after completion**
- treat the new architecture as the current baseline
- remove obsolete planned notes that are now implemented

## Update Rules After Each Feature
- change feature status in `PLANS.md`
- record implementation notes
- record any deferred follow-ups
- update `AGENTS.md` if any of the following changed:
  - architecture
  - source-of-truth files
  - interfaces
  - environment variables
  - runtime commands
  - known quirks
  - validation steps

## First Feature To Start With
- `Feature 1: Nova Provider Integration and Routing Refactor`

Reason:
- it is the foundation for semantic search and voice
- it reduces later rewrite churn
- it preserves the current API/UI while upgrading the intelligence layer

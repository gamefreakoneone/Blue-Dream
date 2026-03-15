from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Optional

try:
    from aws_sdk_bedrock_runtime.client import (
        BedrockRuntimeClient,
        InvokeModelWithBidirectionalStreamOperationInput,
    )
    from aws_sdk_bedrock_runtime.config import Config as BedrockRuntimeConfig
    from aws_sdk_bedrock_runtime.models import (
        BidirectionalInputPayloadPart,
        InvokeModelWithBidirectionalStreamInputChunk,
    )
    try:
        from aws_sdk_bedrock_runtime.config import (
            HTTPAuthSchemeResolver,
            SigV4AuthScheme,
        )
    except ImportError:
        HTTPAuthSchemeResolver = None
        SigV4AuthScheme = None

    try:
        from smithy_aws_core.identity import EnvironmentCredentialsResolver
    except ImportError:
        from smithy_aws_core.identity.environment import EnvironmentCredentialsResolver
except ImportError:
    BedrockRuntimeClient = None
    InvokeModelWithBidirectionalStreamOperationInput = None
    BedrockRuntimeConfig = None
    BidirectionalInputPayloadPart = None
    InvokeModelWithBidirectionalStreamInputChunk = None
    EnvironmentCredentialsResolver = None
    HTTPAuthSchemeResolver = None
    SigV4AuthScheme = None

try:
    from ..llm.model_registry import get_model_registry
    from ..llm.settings import get_provider_settings
    from .tool_adapter import (
        QUERY_MEMORIA_TOOL_NAME,
        VOICE_SYSTEM_PROMPT,
        execute_query_memoria,
        get_query_memoria_tool_spec,
    )
except ImportError:
    from llm.model_registry import get_model_registry
    from llm.settings import get_provider_settings
    from voice.tool_adapter import (
        QUERY_MEMORIA_TOOL_NAME,
        VOICE_SYSTEM_PROMPT,
        execute_query_memoria,
        get_query_memoria_tool_spec,
    )


INPUT_SAMPLE_RATE_HZ = 16000
OUTPUT_SAMPLE_RATE_HZ = 24000
INPUT_CONTENT_TYPE = "audio/lpcm"
TEXT_CONTENT_TYPE = "text/plain"


class VoiceSessionError(RuntimeError):
    """Base class for voice session failures."""


class VoiceSessionUnavailableError(VoiceSessionError):
    """Raised when the runtime cannot start a voice session."""


class VoiceSessionExpiredError(VoiceSessionError):
    """Raised when the session has exceeded the configured lifetime."""


@dataclass
class _ContentMeta:
    role: str = ""
    type: str = ""
    generation_stage: str = ""


@dataclass
class _TurnState:
    user_final: str = ""
    assistant_partial: str = ""
    assistant_final: str = ""
    response_payload: Optional[dict[str, Any]] = None
    tool_requested: bool = False
    assistant_final_sent: bool = False
    turn_complete_sent: bool = False
    history_appended: bool = False


class NovaSonicVoiceSession:
    def __init__(self) -> None:
        self.settings = get_provider_settings()
        self.registry = get_model_registry()
        self.prompt_name = str(uuid.uuid4())
        self.audio_content_name = str(uuid.uuid4())
        self.created_at = time.monotonic()
        self.client_events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.chat_history: list[dict[str, str]] = []

        self._client: Any = None
        self._stream_response: Any = None
        self._receive_task: Optional[asyncio.Task[None]] = None
        self._tool_task: Optional[asyncio.Task[None]] = None

        self._opened = False
        self._closed = False
        self._turn_open = False
        self._assistant_busy = False

        self._turn_state: Optional[_TurnState] = None
        self._content_meta: dict[str, _ContentMeta] = {}
        self._pending_tool_use: Optional[dict[str, Any]] = None
        self._last_content_id: Optional[str] = None

    @classmethod
    def ensure_supported(cls) -> None:
        settings = get_provider_settings()
        if not settings.voice_mode_enabled:
            raise VoiceSessionUnavailableError(
                "Voice mode requires standard AWS credentials for Bedrock "
                "bidirectional streaming."
            )
        missing: list[str] = []
        if BedrockRuntimeClient is None:
            missing.append("aws_sdk_bedrock_runtime")
        if EnvironmentCredentialsResolver is None:
            missing.append("smithy_aws_core")
        if missing:
            raise VoiceSessionUnavailableError(
                "Voice mode dependencies are missing. Install "
                + ", ".join(missing)
                + "."
            )

    def is_expired(self) -> bool:
        return (
            time.monotonic() - self.created_at
            >= float(self.settings.voice_session_max_seconds)
        )

    async def open(self) -> None:
        self.ensure_supported()
        if self._opened:
            return

        config_kwargs: dict[str, Any] = dict(
            endpoint_uri=(
                f"https://bedrock-runtime.{self.settings.bedrock_region}.amazonaws.com"
            ),
            region=self.settings.bedrock_region,
            aws_credentials_identity_resolver=EnvironmentCredentialsResolver(),
        )
        if HTTPAuthSchemeResolver is not None and SigV4AuthScheme is not None:
            config_kwargs["auth_scheme_resolver"] = HTTPAuthSchemeResolver()
            config_kwargs["auth_schemes"] = {
                "aws.auth#sigv4": SigV4AuthScheme(service="bedrock")
            }

        config = BedrockRuntimeConfig(
            **config_kwargs
        )
        self._client = BedrockRuntimeClient(config=config)

        last_error: Exception | None = None
        for model_id in self._candidate_model_ids():
            try:
                self._stream_response = await asyncio.wait_for(
                    self._client.invoke_model_with_bidirectional_stream(
                        InvokeModelWithBidirectionalStreamOperationInput(
                            model_id=model_id
                        )
                    ),
                    timeout=20.0,
                )
                break
            except Exception as exc:
                last_error = exc
                self._stream_response = None

        if self._stream_response is None:
            raise VoiceSessionUnavailableError(
                "Unable to open a Nova Sonic streaming session. "
                f"Last error: {last_error}"
            )

        await self._send_event(self._session_start_event())
        await self._send_event(self._prompt_start_event())
        await self._send_text_block(
            role="SYSTEM",
            content=VOICE_SYSTEM_PROMPT,
            interactive=False,
        )
        self._receive_task = asyncio.create_task(self._receive_loop())
        self._opened = True
        await self.client_events.put(
            {
                "type": "session.ready",
                "sample_rate_hz": OUTPUT_SAMPLE_RATE_HZ,
                "voice_id": self.settings.nova_sonic_voice_id,
            }
        )

    async def start_turn(self) -> None:
        self._ensure_open()
        self._ensure_not_expired()
        if self._turn_open or self._assistant_busy:
            raise VoiceSessionError("A voice turn is already in progress.")

        self._turn_open = True
        self._assistant_busy = False
        self._turn_state = _TurnState()
        self._pending_tool_use = None
        self._content_meta.clear()
        self._last_content_id = None
        self.audio_content_name = str(uuid.uuid4())
        await self._send_event(self._audio_content_start_event())

    async def send_audio_chunk(self, pcm_bytes: bytes) -> None:
        self._ensure_open()
        self._ensure_not_expired()
        if not self._turn_open:
            raise VoiceSessionError("Voice audio was sent without an active turn.")
        if not pcm_bytes:
            return

        await self._send_event(self._audio_input_event(pcm_bytes))

    async def end_turn(self) -> None:
        self._ensure_open()
        self._ensure_not_expired()
        if not self._turn_open:
            raise VoiceSessionError("No active voice turn to end.")

        self._turn_open = False
        self._assistant_busy = True
        await self._send_event(self._content_end_event(self.audio_content_name))

    async def next_client_event(self) -> dict[str, Any]:
        return await self.client_events.get()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True

        if self._opened:
            try:
                await self._send_event(self._content_end_event(self.audio_content_name))
                await self._send_event(self._prompt_end_event())
                await self._send_event(self._session_end_event())
            except Exception:
                pass

        if self._receive_task is not None:
            self._receive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._receive_task
        if self._tool_task is not None:
            self._tool_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._tool_task

    def _ensure_open(self) -> None:
        if not self._opened or self._closed or self._stream_response is None:
            raise VoiceSessionError("Voice session is not open.")

    def _ensure_not_expired(self) -> None:
        if self.is_expired():
            raise VoiceSessionExpiredError(
                "Voice session expired. Start a fresh session to continue."
            )

    def _candidate_model_ids(self) -> list[str]:
        configured = (self.registry.sonic or "").strip()
        candidates = [
            configured,
            "us.amazon.nova-2-sonic-v1:0",
            "global.amazon.nova-2-sonic-v1:0",
            "amazon.nova-2-sonic-v1:0",
        ]
        ordered: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            ordered.append(candidate)
        return ordered

    async def _receive_loop(self) -> None:
        try:
            while not self._closed:
                try:
                    output = await self._stream_response.await_output()
                    result = await output[1].receive()
                except StopAsyncIteration:
                    break

                if not result.value or not result.value.bytes_:
                    continue

                payload = result.value.bytes_.decode("utf-8")
                try:
                    data = json.loads(payload)
                except json.JSONDecodeError:
                    continue

                event = data.get("event") or {}
                if "contentStart" in event:
                    self._handle_content_start(event["contentStart"])
                elif "textOutput" in event:
                    await self._handle_text_output(event["textOutput"])
                elif "audioOutput" in event:
                    await self._handle_audio_output(event["audioOutput"])
                elif "toolUse" in event:
                    self._pending_tool_use = event["toolUse"]
                    if self._turn_state is not None:
                        self._turn_state.tool_requested = True
                elif "contentEnd" in event:
                    await self._handle_content_end(event["contentEnd"])
                elif "completionEnd" in event:
                    await self._handle_completion_end()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self.client_events.put(
                {
                    "type": "error",
                    "code": "voice_session_error",
                    "message": str(exc),
                }
            )
        finally:
            self._assistant_busy = False
            self._turn_open = False

    def _handle_content_start(self, content_start: dict[str, Any]) -> None:
        content_id = content_start.get("contentId") or content_start.get("contentName")
        if not content_id:
            return

        generation_stage = ""
        additional_fields = content_start.get("additionalModelFields")
        if additional_fields:
            try:
                generation_stage = json.loads(additional_fields).get(
                    "generationStage", ""
                )
            except json.JSONDecodeError:
                generation_stage = ""

        self._content_meta[content_id] = _ContentMeta(
            role=content_start.get("role", ""),
            type=content_start.get("type", ""),
            generation_stage=generation_stage,
        )
        self._last_content_id = content_id

    async def _handle_text_output(self, text_output: dict[str, Any]) -> None:
        content_id = text_output.get("contentId") or self._last_content_id
        meta = self._content_meta.get(content_id or "", _ContentMeta())
        role = text_output.get("role") or meta.role
        generation_stage = meta.generation_stage or "FINAL"
        text = str(text_output.get("content", "")).strip()

        if not text:
            return

        if role == "USER":
            if self._turn_state is not None:
                self._turn_state.user_final = text
            await self.client_events.put({"type": "transcript.user.final", "text": text})
            return

        if role != "ASSISTANT":
            return

        if generation_stage == "SPECULATIVE":
            if self._turn_state is not None:
                self._turn_state.assistant_partial = text
            await self.client_events.put(
                {"type": "transcript.assistant.partial", "text": text}
            )
            return

        await self._emit_assistant_final(text)

    async def _handle_audio_output(self, audio_output: dict[str, Any]) -> None:
        audio_payload = audio_output.get("content")
        if not audio_payload:
            return
        await self.client_events.put(
            {
                "type": "audio.chunk",
                "pcm16_base64": audio_payload,
                "sample_rate_hz": OUTPUT_SAMPLE_RATE_HZ,
            }
        )

    async def _handle_content_end(self, content_end: dict[str, Any]) -> None:
        content_type = content_end.get("type", "")
        stop_reason = content_end.get("stopReason", "")
        if content_type == "TOOL" and stop_reason == "TOOL_USE" and self._pending_tool_use:
            if self._tool_task is None or self._tool_task.done():
                pending_tool = self._pending_tool_use
                self._pending_tool_use = None
                self._tool_task = asyncio.create_task(
                    self._execute_tool_and_respond(pending_tool)
                )

    async def _handle_completion_end(self) -> None:
        if self._turn_state is None:
            return

        if not self._turn_state.assistant_final_sent:
            fallback_text = None
            if self._turn_state.response_payload is not None:
                fallback_text = str(
                    self._turn_state.response_payload.get("text", "")
                ).strip()

            if fallback_text:
                await self._emit_assistant_final(fallback_text)
            elif not self._turn_state.user_final:
                await self.client_events.put(
                    {
                        "type": "error",
                        "code": "no_speech",
                        "message": "I couldn't hear a clear question. Please try again.",
                    }
                )

        if not self._turn_state.turn_complete_sent:
            self._turn_state.turn_complete_sent = True
            self._append_history_if_ready()
            await self.client_events.put({"type": "turn.complete"})

        self._assistant_busy = False

    async def _emit_assistant_final(self, text: str) -> None:
        if self._turn_state is None or self._turn_state.assistant_final_sent:
            return

        self._turn_state.assistant_final = text
        self._turn_state.assistant_final_sent = True

        response_payload = self._turn_state.response_payload or {}
        await self.client_events.put(
            {
                "type": "transcript.assistant.final",
                "text": text,
                "response_type": response_payload.get("response_type", "general"),
                "image_path": response_payload.get("image_path"),
                "data": response_payload.get("data"),
            }
        )
        self._append_history_if_ready()

    def _append_history_if_ready(self) -> None:
        if self._turn_state is None or self._turn_state.history_appended:
            return
        if not self._turn_state.user_final:
            return
        if not self._turn_state.assistant_final:
            return

        self.chat_history.append({"role": "USER", "text": self._turn_state.user_final})
        self.chat_history.append(
            {"role": "ASSISTANT", "text": self._turn_state.assistant_final}
        )
        self._turn_state.history_appended = True

    async def _execute_tool_and_respond(self, tool_use: dict[str, Any]) -> None:
        tool_name = tool_use.get("toolName")
        tool_use_id = str(tool_use.get("toolUseId", "")).strip()
        raw_content = tool_use.get("content")

        if tool_name != QUERY_MEMORIA_TOOL_NAME:
            tool_result: dict[str, Any] = {
                "error": f"Unsupported Sonic tool: {tool_name or 'unknown'}"
            }
        else:
            try:
                tool_result = await execute_query_memoria(raw_content)
            except Exception as exc:
                tool_result = {"error": f"query_memoria failed: {exc}"}

        if self._turn_state is not None and "response_type" in tool_result:
            self._turn_state.response_payload = tool_result

        tool_content_name = str(uuid.uuid4())
        await self._send_event(self._tool_content_start_event(tool_content_name, tool_use_id))
        await self._send_event(self._tool_result_event(tool_content_name, tool_result))
        await self._send_event(self._content_end_event(tool_content_name))

    async def _send_text_block(
        self, *, role: str, content: str, interactive: bool
    ) -> None:
        content_name = str(uuid.uuid4())
        await self._send_event(
            {
                "event": {
                    "contentStart": {
                        "promptName": self.prompt_name,
                        "contentName": content_name,
                        "type": "TEXT",
                        "interactive": interactive,
                        "role": role,
                        "textInputConfiguration": {"mediaType": TEXT_CONTENT_TYPE},
                    }
                }
            }
        )
        await self._send_event(
            {
                "event": {
                    "textInput": {
                        "promptName": self.prompt_name,
                        "contentName": content_name,
                        "content": content,
                    }
                }
            }
        )
        await self._send_event(self._content_end_event(content_name))

    async def _send_event(self, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload)
        event = InvokeModelWithBidirectionalStreamInputChunk(
            value=BidirectionalInputPayloadPart(bytes_=raw.encode("utf-8"))
        )
        await self._stream_response.input_stream.send(event)

    def _session_start_event(self) -> dict[str, Any]:
        return {
            "event": {
                "sessionStart": {
                    "inferenceConfiguration": {
                        "maxTokens": 1024,
                        "topP": 0.9,
                        "temperature": 0.2,
                    },
                    "turnDetectionConfiguration": {
                        "endpointingSensitivity": "LOW"
                    },
                }
            }
        }

    def _prompt_start_event(self) -> dict[str, Any]:
        return {
            "event": {
                "promptStart": {
                    "promptName": self.prompt_name,
                    "textOutputConfiguration": {"mediaType": TEXT_CONTENT_TYPE},
                    "audioOutputConfiguration": {
                        "mediaType": INPUT_CONTENT_TYPE,
                        "sampleRateHertz": OUTPUT_SAMPLE_RATE_HZ,
                        "sampleSizeBits": 16,
                        "channelCount": 1,
                        "voiceId": self.settings.nova_sonic_voice_id,
                        "encoding": "base64",
                        "audioType": "SPEECH",
                    },
                    "toolUseOutputConfiguration": {
                        "mediaType": "application/json"
                    },
                    "toolConfiguration": {
                        "tools": [get_query_memoria_tool_spec()]
                    },
                }
            }
        }

    def _audio_content_start_event(self) -> dict[str, Any]:
        return {
            "event": {
                "contentStart": {
                    "promptName": self.prompt_name,
                    "contentName": self.audio_content_name,
                    "type": "AUDIO",
                    "interactive": True,
                    "role": "USER",
                    "audioInputConfiguration": {
                        "mediaType": INPUT_CONTENT_TYPE,
                        "sampleRateHertz": INPUT_SAMPLE_RATE_HZ,
                        "sampleSizeBits": 16,
                        "channelCount": 1,
                        "audioType": "SPEECH",
                        "encoding": "base64",
                    },
                }
            }
        }

    def _audio_input_event(self, pcm_bytes: bytes) -> dict[str, Any]:
        return {
            "event": {
                "audioInput": {
                    "promptName": self.prompt_name,
                    "contentName": self.audio_content_name,
                    "content": base64.b64encode(pcm_bytes).decode("ascii"),
                }
            }
        }

    def _tool_content_start_event(
        self, content_name: str, tool_use_id: str
    ) -> dict[str, Any]:
        return {
            "event": {
                "contentStart": {
                    "promptName": self.prompt_name,
                    "contentName": content_name,
                    "interactive": False,
                    "type": "TOOL",
                    "role": "TOOL",
                    "toolResultInputConfiguration": {
                        "toolUseId": tool_use_id,
                        "type": "TEXT",
                        "textInputConfiguration": {"mediaType": TEXT_CONTENT_TYPE},
                    },
                }
            }
        }

    def _tool_result_event(
        self, content_name: str, tool_result: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "event": {
                "toolResult": {
                    "promptName": self.prompt_name,
                    "contentName": content_name,
                    "content": json.dumps(tool_result),
                }
            }
        }

    def _content_end_event(self, content_name: str) -> dict[str, Any]:
        return {
            "event": {
                "contentEnd": {
                    "promptName": self.prompt_name,
                    "contentName": content_name,
                }
            }
        }

    def _prompt_end_event(self) -> dict[str, Any]:
        return {"event": {"promptEnd": {"promptName": self.prompt_name}}}

    def _session_end_event(self) -> dict[str, Any]:
        return {"event": {"sessionEnd": {}}}

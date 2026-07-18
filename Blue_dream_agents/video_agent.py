import asyncio
import logging
import os
import time

from google import genai
from pydantic import BaseModel, Field

try:
    from .llm.client import invoke_video_structured
    from .llm.model_registry import resolve
    from .llm.settings import get_provider_settings, load_project_env
    from .oss_media import presigned_url
except ImportError:
    from llm.client import invoke_video_structured
    from llm.model_registry import resolve
    from llm.settings import get_provider_settings, load_project_env
    from oss_media import presigned_url

load_project_env()
logger = logging.getLogger(__name__)

VIDEO_ANALYSIS_TIMEOUT_SECONDS = float(
    os.getenv("VIDEO_ANALYSIS_TIMEOUT_SECONDS", "300")
)


VIDEO_ANALYSIS_PROMPT = """
You are a dementia assistance agent. Your job is to monitor the actions of the patient in the video and describe their actions in detail. If only one unlabeled person is visible, refer to that person as the patient. If another person is explicitly visible, preserve that separate identity. If the patient is interacting with the environment,
describe the objects they are interacting with. Once the user is done using the object and deposits back in the environment, describe the new location of the object relative to the environment.
Also describe if the patient has added new objects to the environment (and their respective location wrt to the environment) or removed objects from the environment.
You will write these results in the video description, and the objects that the user interacted with in the room in the room_objects list. 
Objects that have been removed from the environment will not be in the room_objects list.
Also provide factual safety observations only. Do not make the final alert decision. If a room contains a possible unattended cooking or kitchen hazard, such as a stove, burner, pan, pot, boiling liquid, smoke, flame, or active cooking after the patient leaves the room/frame, set danger_candidate to true and describe the evidence in observed_hazards and scene_end_state. If the scene is ambiguous, describe that in uncertainties instead of inventing danger.

Output Example:
{
    "video_description": "The patient, wearing a blue and yellow hoodie, blue jeans, and black headphones, is initially standing. They reach down to a brown office chair and pick up a black smartphone. The patient then sits on the brown office chair, holding the smartphone and looking at its screen, appearing to speak or react to its content. After a few moments, they place the black smartphone and the headphones on the white bed, next to a white baseball cap. Immediately after, the patient picks up the white baseball cap from the bed, stands up, and walks out of the frame.",
    "room_objects": ["headphones", "black smartphone"],
    "danger_candidate": false,
    "scene_end_state": "The patient leaves the room. The bed and chair remain visible with no obvious active hazard.",
    "observed_hazards": [],
    "uncertainties": []
}
"""


class video_results(BaseModel):
    video_description: str = Field(
        default="",
        description="Detailed description of the monitored patient's actions in the video. If another person is explicitly visible, preserve that separate identity.",
    )
    room_objects: list[str] = Field(
        default_factory=list,
        description="List of objects present in the video which the user interacted with, or have added to environment and is still in the room and not removed from the scene.",
    )
    danger_candidate: bool = Field(
        default=False,
        description="Whether the video contains factual visual evidence that may need a safety review.",
    )
    scene_end_state: str = Field(
        default="",
        description="Factual description of the final visible state of the room and whether the patient left the room or frame.",
    )
    observed_hazards: list[str] = Field(
        default_factory=list,
        description="Factual hazards visible in the video, without deciding whether to alert.",
    )
    uncertainties: list[str] = Field(
        default_factory=list,
        description="Important uncertainties or ambiguous observations in the video.",
    )


class Video_Agent:
    def __init__(self):
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        configured_model = os.getenv(
            "GEMINI_VIDEO_MODEL", "gemini-3-flash-preview"
        ).strip()
        fallback_models = [
            value.strip()
            for value in os.getenv(
                "GEMINI_VIDEO_FALLBACK_MODELS", "gemini-2.5-flash"
            ).split(",")
            if value.strip()
        ]
        self.max_retries = max(1, int(os.getenv("GEMINI_VIDEO_MAX_RETRIES", "3")))
        self.retry_base_seconds = max(
            0.0, float(os.getenv("GEMINI_VIDEO_RETRY_BASE_SECONDS", "4"))
        )
        self.model_candidates = []
        for model in [configured_model, *fallback_models]:
            for candidate in self._model_name_variants(model):
                if candidate and candidate not in self.model_candidates:
                    self.model_candidates.append(candidate)

    def _model_name_variants(self, model_name: str) -> list[str]:
        if not model_name:
            return []
        if model_name.startswith("models/"):
            return [model_name, model_name.split("/", 1)[1]]
        return [model_name, f"models/{model_name}"]

    def _is_transient_generation_error(self, error: Exception) -> bool:
        text = str(error).lower()
        transient_markers = (
            "503",
            "unavailable",
            "high demand",
            "try again later",
            "429",
            "resource_exhausted",
            "rate limit",
            "timeout",
            "temporarily",
        )
        return any(marker in text for marker in transient_markers)

    def _upload_video(self, video_path):
        myfile = self.client.files.upload(file=video_path)
        deadline = time.monotonic() + VIDEO_ANALYSIS_TIMEOUT_SECONDS
        print("Processing video...")
        while myfile.state == "PROCESSING":
            if time.monotonic() > deadline:
                raise TimeoutError(
                    "Gemini file processing exceeded "
                    f"{VIDEO_ANALYSIS_TIMEOUT_SECONDS:g}s"
                )
            print(".", end="", flush=True)
            time.sleep(1)
            myfile = self.client.files.get(name=myfile.name)
        if myfile.state == "FAILED":
            raise Exception("File processing failed.")
        print("\nFile is ready!")
        return myfile

    def _generate_video_summary(self, myfile):
        last_error = None
        for model_name in self.model_candidates:
            for attempt in range(1, self.max_retries + 1):
                try:
                    return self.client.models.generate_content(
                        model=model_name,
                        contents=[myfile, VIDEO_ANALYSIS_PROMPT],
                        config={
                            "response_mime_type": "application/json",
                            "response_json_schema": video_results.model_json_schema(),
                        },
                    )
                except Exception as exc:
                    last_error = exc
                    print(
                        "Gemini video generation failed with "
                        f"model {model_name} (attempt {attempt}/{self.max_retries}): {exc}"
                    )
                    if (
                        attempt >= self.max_retries
                        or not self._is_transient_generation_error(exc)
                    ):
                        break
                    sleep_seconds = self.retry_base_seconds * attempt
                    if sleep_seconds:
                        print(
                            f"Retrying Gemini video generation in {sleep_seconds:.1f}s..."
                        )
                        time.sleep(sleep_seconds)

        raise RuntimeError(
            f"Gemini video generation failed for all candidate models {self.model_candidates}: {last_error}"
        )

    def video_description(self, video_path):
        myfile = self._upload_video(video_path)
        response = self._generate_video_summary(myfile)
        result = video_results.model_validate_json(response.text)
        return result


async def describe_video(
    video_path: str, *, video_oss_key: str | None = None
) -> video_results:
    """Analyze one complete video, with full-video Gemini as Qwen's fallback."""

    configured_provider = get_provider_settings().video_provider
    if configured_provider == "gemini":
        return await asyncio.to_thread(Video_Agent().video_description, video_path)

    try:
        target = resolve("video")
        if target.provider != "qwen":
            raise RuntimeError(f"Unsupported video provider: {target.provider}")
        if not video_oss_key:
            raise RuntimeError("Qwen video analysis requires an uploaded OSS object key.")
        url = await asyncio.to_thread(presigned_url, video_oss_key)
        return await invoke_video_structured(
            video_url=url,
            output_model=video_results,
            text_prompt=VIDEO_ANALYSIS_PROMPT,
            model_id=target.model,
            task="video",
        )
    except Exception as exc:
        logger.warning(
            "Qwen/OSS video analysis failed; trying full-video Gemini fallback: %s",
            exc,
        )
        return await asyncio.to_thread(Video_Agent().video_description, video_path)

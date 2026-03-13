import os
from openai import OpenAI
try:
    from .llm.settings import load_project_env
except ImportError:
    from llm.settings import load_project_env

load_project_env()


class Audio_agent:
    def __init__(self):
        api_key = os.getenv("OPENAI_TRANSCRIBE_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Audio transcription requires OPENAI_TRANSCRIBE_API_KEY. "
                "OPENAI_API_KEY is only supported as a backward-compatible fallback."
            )
        self.client = OpenAI(api_key=api_key)

    def transcribe_audio(self, audio_file):
        with open(audio_file, "rb") as audio:
            transcript = self.client.audio.transcriptions.create(
                model="gpt-4o-transcribe", file=audio
            )
        return transcript.text

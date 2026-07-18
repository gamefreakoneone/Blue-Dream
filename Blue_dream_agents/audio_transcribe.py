try:
    from .llm.client import transcribe_audio
except ImportError:
    from llm.client import transcribe_audio


class Audio_agent:
    """Compatibility wrapper for the provider-switched transcription client."""

    async def transcribe_audio(self, audio_file):
        return await transcribe_audio(audio_file)

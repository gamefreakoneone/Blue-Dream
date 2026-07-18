import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest


class BucketStub:
    def __init__(self, *, exists=False):
        self.exists = exists
        self.uploads = []
        self.signs = []

    def object_exists(self, key):
        return self.exists

    def put_object_from_file(self, key, path):
        self.uploads.append((key, path))

    def sign_url(self, method, key, ttl):
        self.signs.append((method, key, ttl))
        return f"https://memoria.example/{key}?Signature=secret"


def test_endpoint_key_and_missing_configuration():
    from Blue_dream_agents import oss_media
    from Blue_dream_agents.llm.settings import ProviderSettings

    assert oss_media.normalize_oss_endpoint("oss.example.com/") == "https://oss.example.com"
    assert oss_media.object_key_for_video(
        r"C:\repo\Storage\video_recordings\camera_1\clip.mp4"
    ) == "Storage/video_recordings/camera_1/clip.mp4"
    with pytest.raises(RuntimeError, match="OSS_ACCESS_KEY_ID"):
        oss_media._get_bucket(ProviderSettings())


def test_upload_deduplicates_and_presigns(monkeypatch, tmp_path):
    from Blue_dream_agents import oss_media
    from Blue_dream_agents.llm.settings import ProviderSettings

    video = tmp_path / "clip.mp4"
    video.write_bytes(b"video")
    bucket = BucketStub(exists=True)
    settings = ProviderSettings(
        oss_access_key_id="id",
        oss_access_key_secret="secret",
        oss_presign_ttl_seconds=900,
    )
    monkeypatch.setattr(oss_media, "to_fs_path", lambda path: video)
    monkeypatch.setattr(
        oss_media,
        "to_stored_path",
        lambda path: "Storage/video_recordings/camera_1/clip.mp4",
    )
    monkeypatch.setattr(oss_media, "_get_bucket", lambda config=None: bucket)
    monkeypatch.setattr(oss_media, "get_provider_settings", lambda: settings)

    key = oss_media.upload_video(str(video))
    url = oss_media.presigned_url(key)
    assert key == "Storage/video_recordings/camera_1/clip.mp4"
    assert bucket.uploads == []
    assert bucket.signs == [("GET", key, 900)]
    assert url.startswith("https://memoria.example/Storage/")


def test_qwen_failure_falls_directly_to_full_video_gemini(monkeypatch):
    from Blue_dream_agents import video_agent
    from Blue_dream_agents.video_agent import video_results

    expected = video_results(video_description="Gemini saw the complete video.")

    class GeminiStub:
        def video_description(self, path):
            assert path == "clip.mp4"
            return expected

    monkeypatch.setattr(
        video_agent,
        "get_provider_settings",
        lambda: SimpleNamespace(video_provider="qwen"),
    )
    monkeypatch.setattr(
        video_agent,
        "resolve",
        lambda task: SimpleNamespace(provider="qwen", model="qwen3-vl-flash"),
    )
    monkeypatch.setattr(
        video_agent, "presigned_url", lambda key: (_ for _ in ()).throw(RuntimeError("OSS down"))
    )
    monkeypatch.setattr(video_agent, "Video_Agent", GeminiStub)

    result = asyncio.run(
        video_agent.describe_video("clip.mp4", video_oss_key="Storage/clip.mp4")
    )
    assert result == expected

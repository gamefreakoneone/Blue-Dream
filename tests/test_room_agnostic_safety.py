import argparse
import asyncio
from types import SimpleNamespace

import pytest

from Blue_dream_agents.memory_schema import MemoryEvent
from Blue_dream_agents.safety_agent import SafetyAssessment
from Blue_dream_agents.timezone_utils import now_local


def _event(**updates):
    values = {
        "event_id": "room-hazard",
        "timestamp": now_local(),
        "room_number": 0,
        "room_name": "Bedroom",
        "video_description": "The patient left the room.",
    }
    values.update(updates)
    return MemoryEvent(**values)


def test_structured_hazard_object_is_primary_and_backward_compatible():
    from Blue_dream_agents.alert_service import choose_highlight_target

    legacy = SafetyAssessment.model_validate(
        {"warning_needed": True, "severity": "medium", "hazard_type": "hazard"}
    )
    assert legacy.hazard_object == ""

    event = _event(
        room_objects=["bed", "kitchen knife"],
        observed_hazards=["A kitchen knife is lying on the bed."],
    )
    assessment = SafetyAssessment(
        warning_needed=True,
        severity="medium",
        hazard_type="sharp_object_left_unsafe",
        hazard_object="  kitchen knife  ",
    )
    assert choose_highlight_target(event, assessment) == "kitchen knife"


def test_unambiguous_room_object_fallback_uses_whole_words():
    from Blue_dream_agents.alert_service import choose_highlight_target

    event = _event(room_objects=["ceramic space heater"])
    assessment = SafetyAssessment(
        hazard_type="unsafe_heat_source",
        patient_message="Please move the ceramic space heater away from the blanket.",
    )
    assert choose_highlight_target(event, assessment) == "ceramic space heater"


def test_alias_fallback_prefers_knife_over_context_surface():
    from Blue_dream_agents.alert_service import choose_highlight_target

    event = _event(
        room_objects=["bed", "kitchen knife"],
        observed_hazards=["A sharp knife was left on the bed after the patient exited."],
    )
    assessment = SafetyAssessment(
        hazard_type="sharp_object_left_unsafe",
        patient_message="Please move the knife from the bed.",
    )
    assert choose_highlight_target(event, assessment) == "kitchen knife"


@pytest.mark.parametrize(
    "text",
    [
        "A utensil was spotted near the doorway.",
        "The companion panicked after the conversation expanded.",
        "The fireplace is visible in the living room.",
    ],
)
def test_substrings_do_not_create_false_highlight_targets(text):
    from Blue_dream_agents.alert_service import choose_highlight_target

    assert choose_highlight_target(_event(video_description=text), SafetyAssessment()) is None


def test_spotted_knife_targets_knife_not_pot():
    from Blue_dream_agents.alert_service import choose_highlight_target

    event = _event(video_description="A knife was spotted on the bedroom floor.")
    assert choose_highlight_target(event, SafetyAssessment()) == "knife"


def test_legacy_cooking_aliases_remain_boundary_safe():
    from Blue_dream_agents.alert_service import choose_highlight_target

    assert (
        choose_highlight_target(
            _event(video_description="Water is boiling unattended."),
            SafetyAssessment(),
        )
        == "pot"
    )
    assert (
        choose_highlight_target(
            _event(video_description="A small fire is visible."), SafetyAssessment()
        )
        == "flame"
    )


def test_patient_alert_gate_keeps_falls_and_geofence_out_of_patient_path():
    from Blue_dream_agents.alert_service import is_patient_actionable_safety_assessment

    for hazard_type in ("fall", "possible_fall", "patient_fall", "geofence_exit"):
        assessment = SafetyAssessment(
            warning_needed=True,
            severity="critical",
            hazard_type=hazard_type,
        )
        assert not is_patient_actionable_safety_assessment(assessment, "medium")

    assert is_patient_actionable_safety_assessment(
        SafetyAssessment(
            warning_needed=True,
            severity="medium",
            hazard_type="sharp_object_left_unsafe",
            hazard_object="knife",
        ),
        "medium",
    )


def test_video_and_safety_prompts_distinguish_safe_use_from_unsafe_end_state():
    from Blue_dream_agents import safety_agent, video_agent

    video_prompt = video_agent.VIDEO_ANALYSIS_PROMPT.casefold()
    safety_prompt = safety_agent._system_prompt().casefold()
    for prompt in (video_prompt, safety_prompt):
        assert "cutting fruit" in prompt
        assert "knife left on a bed" in prompt
    assert "any monitored room" in video_prompt
    assert "do not classify falls or geofence" in safety_prompt


def test_knife_candidate_reaches_mocked_safety_provider(monkeypatch, tmp_path):
    from Blue_dream_agents import safety_agent

    screenshot = tmp_path / "knife.jpg"
    screenshot.write_bytes(b"image")
    captured = {}

    async def assess(**kwargs):
        captured.update(kwargs)
        return SafetyAssessment(
            warning_needed=True,
            severity="medium",
            hazard_type="sharp_object_left_unsafe",
            hazard_object="knife",
            patient_message="Please move the knife to a safe place.",
        )

    monkeypatch.setattr(safety_agent, "safety_agent_enabled", lambda: True)
    monkeypatch.setattr(safety_agent, "to_fs_path", lambda value: screenshot)
    monkeypatch.setattr(
        safety_agent,
        "get_model_registry",
        lambda: SimpleNamespace(
            vision="vision-model", vision_fallback=None, synthesis="text-model"
        ),
    )
    monkeypatch.setattr(safety_agent, "invoke_multimodal_structured", assess)

    event = _event(
        danger_candidate=True,
        screenshot_path="Storage/screenshots/knife.jpg",
        room_objects=["knife"],
        scene_end_state="The knife remains on the bed after the patient exits.",
        observed_hazards=["A sharp knife is left on the bed."],
    )
    result = asyncio.run(safety_agent.assess_event_safety(event))

    assert result.hazard_object == "knife"
    assert captured["output_model"] is SafetyAssessment
    assert "sharp_object_left_unsafe" in captured["text_prompt"]


def test_no_hazard_short_circuits_without_provider(monkeypatch):
    from Blue_dream_agents import safety_agent

    monkeypatch.setattr(safety_agent, "safety_agent_enabled", lambda: True)

    async def should_not_run(**kwargs):
        raise AssertionError("provider should not be called")

    monkeypatch.setattr(safety_agent, "invoke_structured", should_not_run)
    result = asyncio.run(
        safety_agent.assess_event_safety(
            _event(
                video_description="The patient safely cuts fruit while holding a knife.",
                room_objects=["knife"],
            )
        )
    )
    assert result.warning_needed is False


def test_alert_image_uses_structured_target_and_full_grounding(monkeypatch, tmp_path):
    from Blue_dream_agents import alert_service

    screenshot = tmp_path / "knife.jpg"
    screenshot.write_bytes(b"image")
    captured = {}

    async def highlight(**kwargs):
        captured.update(kwargs)
        return "Storage/highlighted/knife-box.jpg"

    monkeypatch.setattr(alert_service, "to_fs_path", lambda value: screenshot)
    monkeypatch.setattr(alert_service, "highlight_object", highlight)
    event = _event(
        screenshot_path="Storage/screenshots/knife.jpg",
        observed_hazards=["A sharp knife is visible on the bed."],
        scene_end_state="The patient exited and the knife remains on the bed.",
    )
    assessment = SafetyAssessment(
        warning_needed=True,
        severity="medium",
        hazard_type="sharp_object_left_unsafe",
        hazard_object="knife",
        detailed_explanation="The knife could cause an injury.",
    )
    fields = asyncio.run(alert_service.build_alert_image_fields(event, assessment))

    assert fields == {
        "image_path": "Storage/highlighted/knife-box.jpg",
        "original_image_path": "Storage/screenshots/knife.jpg",
        "highlight_target": "knife",
        "highlight_status": "generated",
    }
    assert captured["object_name"] == "knife"
    assert "could cause an injury" in captured["grounding_text"]
    assert "sharp knife" in captured["grounding_text"]
    assert "patient exited" in captured["grounding_text"]


def test_alert_image_keeps_original_when_spatial_grounding_fails(
    monkeypatch, tmp_path
):
    from Blue_dream_agents import alert_service

    screenshot = tmp_path / "knife.jpg"
    screenshot.write_bytes(b"image")

    async def no_box(**kwargs):
        return None

    monkeypatch.setattr(alert_service, "to_fs_path", lambda value: screenshot)
    monkeypatch.setattr(alert_service, "highlight_object", no_box)
    fields = asyncio.run(
        alert_service.build_alert_image_fields(
            _event(screenshot_path="Storage/screenshots/knife.jpg"),
            SafetyAssessment(hazard_object="knife"),
        )
    )
    assert fields["image_path"] == "Storage/screenshots/knife.jpg"
    assert fields["highlight_target"] == "knife"
    assert fields["highlight_status"] == "fallback_original"


def _cli_args(video, screenshot):
    return argparse.Namespace(
        video=str(video), room="bedroom", screenshot=str(screenshot)
    )


def _patch_cli_pipeline(
    monkeypatch,
    tmp_path,
    *,
    assessment,
    image_fields=None,
    video_provider="qwen",
):
    from scripts import check_hazard_video
    from Blue_dream_agents.video_agent import video_results

    monkeypatch.setattr(check_hazard_video, "resolve_output_dir", lambda value: tmp_path)
    monkeypatch.setattr(
        check_hazard_video,
        "get_provider_settings",
        lambda: SimpleNamespace(
            llm_provider="qwen",
            video_provider=video_provider,
            spatial_provider="qwen",
            safety_alert_min_severity="medium",
        ),
    )
    upload_calls = []
    monkeypatch.setattr(
        check_hazard_video,
        "upload_video",
        lambda path: upload_calls.append(path) or "Storage/hazard_checks/test/video.mp4",
    )

    async def describe(*args, **kwargs):
        return video_results(
            video_description="The patient leaves a knife on the bed and exits.",
            room_objects=["knife"],
            danger_candidate=True,
            scene_end_state="The knife remains on the bed.",
            observed_hazards=["A sharp knife is left on the bed."],
        )

    async def assess(event):
        return assessment

    async def build(event, result):
        if image_fields is None:
            raise AssertionError("highlighting should not run")
        return image_fields

    monkeypatch.setattr(check_hazard_video, "describe_video", describe)
    monkeypatch.setattr(check_hazard_video, "assess_event_safety", assess)
    monkeypatch.setattr(check_hazard_video, "build_alert_image_fields", build)
    return check_hazard_video, upload_calls


def test_cli_dry_run_alert_and_highlight(monkeypatch, tmp_path):
    video = tmp_path / "knife.mp4"
    screenshot = tmp_path / "knife.jpg"
    video.write_bytes(b"video")
    screenshot.write_bytes(b"image")
    image_fields = {
        "image_path": "Storage/highlighted/knife.jpg",
        "original_image_path": "Storage/screenshots/knife.jpg",
        "highlight_target": "knife",
        "highlight_status": "generated",
    }
    module, upload_calls = _patch_cli_pipeline(
        monkeypatch,
        tmp_path,
        assessment=SafetyAssessment(
            warning_needed=True,
            severity="medium",
            hazard_type="sharp_object_left_unsafe",
            hazard_object="knife",
        ),
        image_fields=image_fields,
    )

    exit_code, report = asyncio.run(
        module.run_hazard_check(_cli_args(video, screenshot))
    )

    assert exit_code == module.EXIT_ALERT_WITH_HIGHLIGHT
    assert report["mode"] == "dry_run_no_persistence_or_delivery"
    assert report["alert_would_fire"] is True
    assert report["highlight_target"] == "knife"
    assert upload_calls
    assert (tmp_path / "result.json").exists()


def test_cli_no_alert_skips_highlighting(monkeypatch, tmp_path):
    video = tmp_path / "safe.mp4"
    screenshot = tmp_path / "safe.jpg"
    video.write_bytes(b"video")
    screenshot.write_bytes(b"image")
    module, upload_calls = _patch_cli_pipeline(
        monkeypatch,
        tmp_path,
        assessment=SafetyAssessment(reason="ordinary knife use"),
        video_provider="gemini",
    )

    exit_code, report = asyncio.run(
        module.run_hazard_check(_cli_args(video, screenshot))
    )

    assert exit_code == module.EXIT_NO_ALERT
    assert report["highlight_status"] == "not_attempted"
    assert upload_calls == []


def test_cli_oss_failure_requests_existing_video_fallback(monkeypatch, tmp_path):
    video = tmp_path / "knife.mp4"
    screenshot = tmp_path / "knife.jpg"
    video.write_bytes(b"video")
    screenshot.write_bytes(b"image")
    module, _ = _patch_cli_pipeline(
        monkeypatch,
        tmp_path,
        assessment=SafetyAssessment(reason="fallback completed without a warning"),
    )
    monkeypatch.setattr(
        module,
        "upload_video",
        lambda path: (_ for _ in ()).throw(RuntimeError("OSS unavailable")),
    )
    captured = {}
    original_describe = module.describe_video

    async def capture_describe(*args, **kwargs):
        captured.update(kwargs)
        return await original_describe(*args, **kwargs)

    monkeypatch.setattr(module, "describe_video", capture_describe)

    exit_code, report = asyncio.run(
        module.run_hazard_check(_cli_args(video, screenshot))
    )

    assert exit_code == module.EXIT_NO_ALERT
    assert captured["video_oss_key"] is None
    assert report["video_bridge_status"] == "upload_failed_fallback_requested"


def test_cli_alert_without_box_returns_partial_exit(monkeypatch, tmp_path):
    video = tmp_path / "knife.mp4"
    screenshot = tmp_path / "knife.jpg"
    video.write_bytes(b"video")
    screenshot.write_bytes(b"image")
    module, _ = _patch_cli_pipeline(
        monkeypatch,
        tmp_path,
        assessment=SafetyAssessment(
            warning_needed=True,
            severity="high",
            hazard_type="sharp_object_left_unsafe",
            hazard_object="knife",
        ),
        image_fields={
            "image_path": "Storage/screenshots/knife.jpg",
            "original_image_path": "Storage/screenshots/knife.jpg",
            "highlight_target": "knife",
            "highlight_status": "fallback_original",
        },
    )

    exit_code, report = asyncio.run(
        module.run_hazard_check(_cli_args(video, screenshot))
    )
    assert exit_code == module.EXIT_ALERT_WITHOUT_HIGHLIGHT
    assert report["highlighted_image_path"] is None


def test_cli_runtime_failure_exit(monkeypatch, tmp_path):
    from scripts import check_hazard_video

    monkeypatch.setattr(
        check_hazard_video,
        "parse_args",
        lambda argv=None: argparse.Namespace(
            video=str(tmp_path / "missing.mp4"),
            room="bedroom",
            screenshot=None,
        ),
    )
    assert check_hazard_video.main([]) == check_hazard_video.EXIT_RUNTIME_FAILURE

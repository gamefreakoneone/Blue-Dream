"""Dry-run one recorded room event through Memoria's production safety models.

This utility intentionally stops before MongoDB, Chroma, proactive-message, and
push delivery. It stages non-Storage media under Storage/hazard_checks, runs the
configured full-video, safety, and spatial providers, and writes an inspectable
result.json beside the extracted final frame.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STORAGE_ROOT = PROJECT_ROOT / "Storage"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Blue_dream_agents.alert_service import (  # noqa: E402
    build_alert_image_fields,
    is_patient_actionable_safety_assessment,
)
from Blue_dream_agents.llm.settings import get_provider_settings  # noqa: E402
from Blue_dream_agents.media_paths import (  # noqa: E402
    resolve_output_dir,
    to_fs_path,
    to_stored_path,
)
from Blue_dream_agents.memory_schema import new_memory_event  # noqa: E402
from Blue_dream_agents.oss_media import upload_video  # noqa: E402
from Blue_dream_agents.safety_agent import assess_event_safety  # noqa: E402
from Blue_dream_agents.timezone_utils import now_local  # noqa: E402
from Blue_dream_agents.video_agent import describe_video  # noqa: E402
from Capture.camera_feed import save_last_frame_screenshot  # noqa: E402


ROOMS = {
    "bedroom": (0, "Bedroom"),
    "living-room": (1, "Living Room"),
}
EXIT_ALERT_WITH_HIGHLIGHT = 0
EXIT_RUNTIME_FAILURE = 1
EXIT_NO_ALERT = 2
EXIT_ALERT_WITHOUT_HIGHLIGHT = 3


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Dry-run a video through Memoria's configured video, safety, and "
            "spatial providers without writing to MongoDB or sending notifications."
        )
    )
    parser.add_argument("--video", required=True, help="Path to the completed video.")
    parser.add_argument(
        "--room",
        required=True,
        choices=sorted(ROOMS),
        help="Room represented by the recording.",
    )
    parser.add_argument(
        "--screenshot",
        help=(
            "Optional final-state screenshot. When omitted, the final video frame "
            "is extracted with the capture pipeline's production helper."
        ),
    )
    return parser.parse_args(argv)


def _resolve_input(path_text: str, *, label: str) -> Path:
    path = Path(path_text).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"{label} does not exist or is not a file.")
    return path


def _is_under_storage(path: Path) -> bool:
    try:
        path.relative_to(STORAGE_ROOT.resolve())
        return True
    except ValueError:
        return False


def _stage_if_needed(source: Path, run_dir: Path) -> Path:
    if _is_under_storage(source):
        return source
    destination = run_dir / source.name
    shutil.copy2(source, destination)
    return destination


def _filesystem_path(stored_path: str | None) -> str | None:
    resolved = to_fs_path(stored_path)
    return str(resolved) if resolved is not None else None


def _exit_code(*, alert_would_fire: bool, highlight_status: str) -> int:
    if not alert_would_fire:
        return EXIT_NO_ALERT
    if highlight_status == "generated":
        return EXIT_ALERT_WITH_HIGHLIGHT
    return EXIT_ALERT_WITHOUT_HIGHLIGHT


async def run_hazard_check(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    source_video = _resolve_input(args.video, label="Video")
    source_screenshot = (
        _resolve_input(args.screenshot, label="Screenshot")
        if args.screenshot
        else None
    )
    run_id = f"{now_local().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    run_dir = resolve_output_dir(f"Storage/hazard_checks/{run_id}")
    video_path = _stage_if_needed(source_video, run_dir)

    if source_screenshot is not None:
        screenshot_path = _stage_if_needed(source_screenshot, run_dir)
    else:
        screenshot_path = await asyncio.to_thread(
            save_last_frame_screenshot, video_path, run_dir
        )
        if screenshot_path is None:
            raise RuntimeError("The final video frame could not be extracted.")

    settings = get_provider_settings()
    stored_video_path = to_stored_path(video_path) or ""
    stored_screenshot_path = to_stored_path(screenshot_path) or ""
    video_oss_key: str | None = None
    video_bridge_status = "not_required"
    if settings.video_provider == "qwen":
        try:
            video_oss_key = await asyncio.to_thread(upload_video, stored_video_path)
            video_bridge_status = "uploaded"
        except Exception:
            # Passing no key into describe_video deliberately enters the production
            # Qwen-to-full-video-Gemini fallback without exposing provider details.
            video_bridge_status = "upload_failed_fallback_requested"

    observations = await describe_video(
        str(video_path), video_oss_key=video_oss_key
    )
    room_number, room_name = ROOMS[args.room]
    event = new_memory_event(
        timestamp=now_local(),
        room_number=room_number,
        video_description=observations.video_description,
        room_objects=observations.room_objects,
        audio_transcript="",
        screenshot_path=stored_screenshot_path,
        video_path=stored_video_path,
        audio_path="",
        video_oss_key=video_oss_key,
        danger_candidate=observations.danger_candidate,
        scene_end_state=observations.scene_end_state,
        observed_hazards=observations.observed_hazards,
        uncertainties=observations.uncertainties,
    )
    assessment = await assess_event_safety(event)
    alert_would_fire = is_patient_actionable_safety_assessment(
        assessment, settings.safety_alert_min_severity
    )

    if alert_would_fire:
        image_fields = await build_alert_image_fields(event, assessment)
    else:
        image_fields = {
            "image_path": stored_screenshot_path,
            "original_image_path": stored_screenshot_path,
            "highlight_target": None,
            "highlight_status": "not_attempted",
        }

    highlighted_path = (
        image_fields["image_path"]
        if image_fields["highlight_status"] == "generated"
        else None
    )
    report: dict[str, Any] = {
        "mode": "dry_run_no_persistence_or_delivery",
        "run_id": run_id,
        "room": {"number": room_number, "name": room_name},
        "providers": {
            "llm": settings.llm_provider,
            "video": settings.video_provider,
            "spatial": settings.spatial_provider,
        },
        "staged_video_path": stored_video_path,
        "video_oss_key": video_oss_key,
        "video_bridge_status": video_bridge_status,
        "observations": observations.model_dump(mode="json"),
        "assessment": assessment.model_dump(mode="json"),
        "alert_would_fire": alert_would_fire,
        "safety_alert_min_severity": settings.safety_alert_min_severity,
        "hazard_object": assessment.hazard_object,
        "highlight_target": image_fields["highlight_target"],
        "highlight_status": image_fields["highlight_status"],
        "original_frame_path": image_fields["original_image_path"],
        "original_frame_fs_path": _filesystem_path(
            image_fields["original_image_path"]
        ),
        "highlighted_image_path": highlighted_path,
        "highlighted_image_fs_path": _filesystem_path(highlighted_path),
        "artifact_directory": str(run_dir),
        "result_path": str(run_dir / "result.json"),
    }
    result_path = run_dir / "result.json"
    result_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return (
        _exit_code(
            alert_would_fire=alert_would_fire,
            highlight_status=str(image_fields["highlight_status"]),
        ),
        report,
    )


def _print_summary(exit_code: int, report: dict[str, Any]) -> None:
    if exit_code == EXIT_ALERT_WITH_HIGHLIGHT:
        outcome = "ALERT WOULD FIRE; HIGHLIGHT GENERATED"
    elif exit_code == EXIT_NO_ALERT:
        outcome = "NO ACTIONABLE ALERT"
    else:
        outcome = "ALERT WOULD FIRE; HIGHLIGHT FELL BACK TO ORIGINAL FRAME"
    print(f"RESULT: {outcome}")
    print(f"Severity: {report['assessment']['severity']}")
    print(f"Hazard object: {report['hazard_object'] or 'none'}")
    print(f"Highlight target: {report['highlight_target'] or 'none'}")
    print(f"Report: {report['result_path']}")
    if report["highlighted_image_fs_path"]:
        print(f"Highlighted image: {report['highlighted_image_fs_path']}")
    print(json.dumps(report, indent=2))


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    print(
        "Memoria hazard check: dry run only; MongoDB, Chroma, proactive messages, "
        "and push delivery will not be used."
    )
    try:
        exit_code, report = asyncio.run(run_hazard_check(args))
    except Exception:
        print(
            "Hazard check failed before a result could be produced. No alert or "
            "notification was persisted.",
            file=sys.stderr,
        )
        return EXIT_RUNTIME_FAILURE
    _print_summary(exit_code, report)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

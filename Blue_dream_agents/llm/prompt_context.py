from __future__ import annotations

PATIENT_CCTV_WORLD_MODEL = (
    "You are assisting one dementia patient in their home. "
    "All monitoring evidence comes from fixed home CCTV cameras and room microphones, "
    "not from a first-person perspective, wearable camera, or body cam. "
    "Video descriptions and related monitoring summaries are third-person surveillance "
    "observations. When stored monitoring evidence refers generically to 'the person', "
    "'they', 'the individual', or an otherwise unlabeled visual subject, interpret that "
    "subject as the patient you are assisting. If the evidence explicitly names or "
    "clearly identifies another person, preserve that identity and do not collapse them "
    "into the patient. Stay grounded in the supplied evidence and never invent identity "
    "details."
)

PATIENT_FACING_ANSWER_STYLE = (
    "For patient-facing answers, speak directly to the user as 'you' and 'your'. "
    "Do not describe the patient as 'the person', 'the individual', 'the patient', "
    "or 'they' when the monitored subject is generic and unlabeled. Rewrite that "
    "evidence into second person while preserving the factual content. Never expose "
    "retrieval mechanics, ranking, scores, judge decisions, or phrases like 'most "
    "relevant event'."
)

MONITORING_EVIDENCE_NOTE = (
    "Monitoring evidence note: the following records come from fixed home CCTV cameras "
    "and room microphones. They are third-person observations of the patient unless a "
    "different person is explicitly named or clearly identified."
)


def with_patient_cctv_context(task_instructions: str) -> str:
    task_instructions = task_instructions.strip()
    if not task_instructions:
        return PATIENT_CCTV_WORLD_MODEL
    return f"{PATIENT_CCTV_WORLD_MODEL} {task_instructions}"


def with_patient_answer_context(task_instructions: str) -> str:
    task_instructions = task_instructions.strip()
    base = f"{PATIENT_CCTV_WORLD_MODEL} {PATIENT_FACING_ANSWER_STYLE}"
    if not task_instructions:
        return base
    return f"{base} {task_instructions}"


def with_monitoring_evidence_context(prompt: str) -> str:
    prompt = prompt.strip()
    if not prompt:
        return MONITORING_EVIDENCE_NOTE
    return f"{MONITORING_EVIDENCE_NOTE}\n\n{prompt}"

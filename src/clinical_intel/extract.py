import re
from dataclasses import dataclass


@dataclass(frozen=True)
class StudyRecord:
    study_id: str | None
    phase: str | None
    participants: int | None
    intervention: str | None
    primary_endpoint: str | None


def _capture(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    return (match.group(1).strip() or None) if match else None


def extract(text: str) -> StudyRecord:
    participants = _capture(r"^participants?[ \t]*:[ \t]*([^\r\n]*)", text)
    if participants is not None and not re.fullmatch(r"-?\d+", participants):
        raise ValueError("participants must be an integer, without trailing text")
    phase = _capture(r"^phase[ \t]*:[ \t]*([^\r\n]*)", text)
    phase = (
        {"I": "1", "II": "2", "III": "3", "IV": "4"}.get(phase.upper(), phase) if phase else None
    )
    return StudyRecord(
        study_id=_capture(r"^study[ \t]*(?:id)?[ \t]*:[ \t]*([^\r\n]*)", text),
        phase=phase,
        participants=int(participants) if participants else None,
        intervention=_capture(r"^intervention[ \t]*:[ \t]*([^\r\n]*)", text),
        primary_endpoint=_capture(r"^primary endpoint[ \t]*:[ \t]*([^\r\n]*)", text),
    )


def validate(record: StudyRecord) -> list[str]:
    errors: list[str] = []
    if record.participants is not None and record.participants <= 0:
        errors.append("participants must be positive")
    if record.study_id is None:
        errors.append("study_id missing")
    if record.phase is not None and record.phase not in {"1", "2", "3", "4"}:
        errors.append("phase must be 1, 2, 3 or 4")
    return errors

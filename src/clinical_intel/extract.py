import re
from dataclasses import dataclass


@dataclass(frozen=True)
class StudyRecord:
    study_id: str | None
    phase: str | None
    participants: int | None
    intervention: str | None
    primary_endpoint: str | None
    sponsor: str | None = None
    condition: str | None = None
    study_type: str | None = None
    secondary_endpoint: str | None = None


def _capture(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    return (match.group(1).strip() or None) if match else None


def extract(text: str) -> StudyRecord:
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    participants = _capture(
        r"^(?:participants?|enrollment|sample size)[ \t]*:[ \t]*([^\r\n]*)",
        text,
    )
    if participants is not None:
        cleaned = participants.replace(",", "").strip()
        if not re.fullmatch(r"-?\d+", cleaned):
            raise ValueError("participants must be an integer, without trailing text")
        participants_value = int(cleaned)
    else:
        participants_value = None

    phase = _capture(r"^phase[ \t]*:[ \t]*([^\r\n]*)", text)
    phase = (
        {"I": "1", "II": "2", "III": "3", "IV": "4"}.get(phase.upper(), phase) if phase else None
    )
    return StudyRecord(
        study_id=_capture(
            r"^(?:study[ \t]*(?:id)?|trial id|protocol id)[ \t]*:[ \t]*([^\r\n]*)",
            text,
        ),
        phase=phase,
        participants=participants_value,
        intervention=_capture(
            r"^(?:intervention|treatment)[ \t]*:[ \t]*([^\r\n]*)",
            text,
        ),
        primary_endpoint=_capture(
            r"^(?:primary endpoint|primary outcome)[ \t]*:[ \t]*([^\r\n]*)",
            text,
        ),
        sponsor=_capture(r"^sponsor[ \t]*:[ \t]*([^\r\n]*)", text),
        condition=_capture(
            r"^(?:condition|disease)[ \t]*:[ \t]*([^\r\n]*)",
            text,
        ),
        study_type=_capture(
            r"^(?:study type|study design|design)[ \t]*:[ \t]*([^\r\n]*)",
            text,
        ),
        secondary_endpoint=_capture(
            r"^(?:secondary endpoint|secondary outcome)[ \t]*:[ \t]*([^\r\n]*)",
            text,
        ),
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

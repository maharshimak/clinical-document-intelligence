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


# A label must start a line. ``(?<![^\r\n])`` matches at the start of the text or
# directly after CR or LF, so LF, CRLF and lone-CR line endings all work without
# translating newlines (which would change character offsets).
_LINE_START = r"(?<![^\r\n])"
_VALUE = r"[ \t]*:[ \t]*([^\r\n]*)"

FIELD_LABELS: dict[str, str] = {
    "study_id": r"(?:study[ \t]*(?:id)?|trial id|protocol id)",
    "phase": r"phase",
    "participants": r"(?:participants?|enrollment|sample size)",
    "intervention": r"(?:intervention|treatment)",
    "primary_endpoint": r"(?:primary endpoint|primary outcome)",
    "sponsor": r"sponsor",
    "condition": r"(?:condition|disease)",
    "study_type": r"(?:study type|study design|design)",
    "secondary_endpoint": r"(?:secondary endpoint|secondary outcome)",
}

FIELD_PATTERNS: dict[str, re.Pattern[str]] = {
    field: re.compile(_LINE_START + label + _VALUE, re.IGNORECASE)
    for field, label in FIELD_LABELS.items()
}

FIELDS: tuple[str, ...] = tuple(FIELD_LABELS)

_ROMAN_PHASES = {"I": "1", "II": "2", "III": "3", "IV": "4"}
# Plain digits, or digits grouped in threes by commas ("1,250"). ASCII only.
_PARTICIPANTS = re.compile(r"-?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)")


@dataclass(frozen=True, slots=True)
class LabeledValue:
    """A labeled value located in the source text.

    ``start``/``end`` are Unicode code point offsets into the exact text that was
    searched, trimmed so that ``text[start:end] == raw_value``.
    """

    field: str
    raw_value: str
    start: int
    end: int


def _trimmed(field: str, match: re.Match[str]) -> LabeledValue | None:
    captured = match.group(1)
    raw_value = captured.strip()
    if not raw_value:
        return None
    start = match.start(1) + (len(captured) - len(captured.lstrip()))
    return LabeledValue(field, raw_value, start, start + len(raw_value))


def find_labeled_values(field: str, text: str) -> list[LabeledValue]:
    """Return every non-empty occurrence of ``field``'s label, in document order."""
    found = (_trimmed(field, match) for match in FIELD_PATTERNS[field].finditer(text))
    return [item for item in found if item is not None]


def find_labeled_value(field: str, text: str) -> LabeledValue | None:
    """Return the first labeled line for ``field`` (empty values yield ``None``)."""
    match = FIELD_PATTERNS[field].search(text)
    return _trimmed(field, match) if match else None


def normalize_phase(raw_value: str) -> str:
    cleaned = raw_value.strip()
    return _ROMAN_PHASES.get(cleaned.upper(), cleaned)


def parse_participants(raw_value: str) -> int:
    """Parse a participant count; reject decimals, trailing text and bad grouping."""
    cleaned = raw_value.strip()
    if not _PARTICIPANTS.fullmatch(cleaned):
        raise ValueError("participants must be an integer, without trailing text")
    return int(cleaned.replace(",", ""))


def _capture(field: str, text: str) -> str | None:
    found = find_labeled_value(field, text)
    return found.raw_value if found else None


def extract(text: str) -> StudyRecord:
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    participants = _capture("participants", text)
    phase = _capture("phase", text)
    return StudyRecord(
        study_id=_capture("study_id", text),
        phase=normalize_phase(phase) if phase else None,
        participants=parse_participants(participants) if participants is not None else None,
        intervention=_capture("intervention", text),
        primary_endpoint=_capture("primary_endpoint", text),
        sponsor=_capture("sponsor", text),
        condition=_capture("condition", text),
        study_type=_capture("study_type", text),
        secondary_endpoint=_capture("secondary_endpoint", text),
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

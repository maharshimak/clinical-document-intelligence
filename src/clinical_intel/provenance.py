import re
from dataclasses import dataclass

from clinical_intel.extract import StudyRecord, extract


@dataclass(frozen=True, slots=True)
class FieldEvidence:
    field: str
    raw_value: str
    normalized_value: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class ExtractionProvenance:
    record: StudyRecord
    evidence: tuple[FieldEvidence, ...]
    evidence_coverage: float
    schema_coverage: float


_PATTERNS = {
    "study_id": re.compile(
        r"^study[ \t]*(?:id)?[ \t]*:[ \t]*([^\r\n]*)", re.IGNORECASE | re.MULTILINE
    ),
    "phase": re.compile(r"^phase[ \t]*:[ \t]*([^\r\n]*)", re.IGNORECASE | re.MULTILINE),
    "participants": re.compile(
        r"^participants?[ \t]*:[ \t]*([^\r\n]*)", re.IGNORECASE | re.MULTILINE
    ),
    "intervention": re.compile(
        r"^intervention[ \t]*:[ \t]*([^\r\n]*)", re.IGNORECASE | re.MULTILINE
    ),
    "primary_endpoint": re.compile(
        r"^primary endpoint[ \t]*:[ \t]*([^\r\n]*)", re.IGNORECASE | re.MULTILINE
    ),
}


def _normalize(field: str, raw_value: str) -> str:
    cleaned = raw_value.strip()
    if field == "phase":
        return {"I": "1", "II": "2", "III": "3", "IV": "4"}.get(
            cleaned.upper(),
            cleaned,
        )
    return cleaned


def extract_with_provenance(text: str) -> ExtractionProvenance:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    record = extract(text)
    evidence: list[FieldEvidence] = []
    for field, pattern in _PATTERNS.items():
        match = pattern.search(text)
        if match is None or not match.group(1).strip():
            continue
        evidence.append(
            FieldEvidence(
                field=field,
                raw_value=match.group(1).strip(),
                normalized_value=_normalize(field, match.group(1)),
                start=match.start(1),
                end=match.end(1),
            )
        )

    non_null_fields = sum(
        value is not None
        for value in (
            record.study_id,
            record.phase,
            record.participants,
            record.intervention,
            record.primary_endpoint,
        )
    )
    evidence_coverage = len(evidence) / non_null_fields if non_null_fields else 0.0
    return ExtractionProvenance(
        record=record,
        evidence=tuple(evidence),
        evidence_coverage=evidence_coverage,
        schema_coverage=len(evidence) / len(_PATTERNS),
    )

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
    extended_schema_coverage: float = 0.0


_PATTERNS = {
    "study_id": re.compile(
        r"^(?:study[ \t]*(?:id)?|trial id|protocol id)[ \t]*:[ \t]*([^\r\n]*)",
        re.IGNORECASE | re.MULTILINE,
    ),
    "phase": re.compile(r"^phase[ \t]*:[ \t]*([^\r\n]*)", re.IGNORECASE | re.MULTILINE),
    "participants": re.compile(
        r"^(?:participants?|enrollment|sample size)[ \t]*:[ \t]*([^\r\n]*)",
        re.IGNORECASE | re.MULTILINE,
    ),
    "intervention": re.compile(
        r"^(?:intervention|treatment)[ \t]*:[ \t]*([^\r\n]*)",
        re.IGNORECASE | re.MULTILINE,
    ),
    "primary_endpoint": re.compile(
        r"^(?:primary endpoint|primary outcome)[ \t]*:[ \t]*([^\r\n]*)",
        re.IGNORECASE | re.MULTILINE,
    ),
    "sponsor": re.compile(r"^sponsor[ \t]*:[ \t]*([^\r\n]*)", re.IGNORECASE | re.MULTILINE),
    "condition": re.compile(
        r"^(?:condition|disease)[ \t]*:[ \t]*([^\r\n]*)",
        re.IGNORECASE | re.MULTILINE,
    ),
    "study_type": re.compile(
        r"^(?:study type|study design|design)[ \t]*:[ \t]*([^\r\n]*)",
        re.IGNORECASE | re.MULTILINE,
    ),
    "secondary_endpoint": re.compile(
        r"^(?:secondary endpoint|secondary outcome)[ \t]*:[ \t]*([^\r\n]*)",
        re.IGNORECASE | re.MULTILINE,
    ),
}
_CORE_FIELDS = {"study_id", "phase", "participants", "intervention", "primary_endpoint"}


def _normalize(field: str, raw_value: str) -> str:
    cleaned = raw_value.strip()
    if field == "phase":
        return {"I": "1", "II": "2", "III": "3", "IV": "4"}.get(
            cleaned.upper(),
            cleaned,
        )
    if field == "participants":
        return cleaned.replace(",", "")
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

    record_values = (
        record.study_id,
        record.phase,
        record.participants,
        record.intervention,
        record.primary_endpoint,
        record.sponsor,
        record.condition,
        record.study_type,
        record.secondary_endpoint,
    )
    non_null_fields = sum(value is not None for value in record_values)
    core_evidence = sum(item.field in _CORE_FIELDS for item in evidence)
    evidence_coverage = len(evidence) / non_null_fields if non_null_fields else 0.0
    return ExtractionProvenance(
        record=record,
        evidence=tuple(evidence),
        evidence_coverage=evidence_coverage,
        schema_coverage=core_evidence / len(_CORE_FIELDS),
        extended_schema_coverage=len(evidence) / len(_PATTERNS),
    )

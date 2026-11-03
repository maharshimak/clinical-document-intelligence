from dataclasses import dataclass

from clinical_intel.extract import (
    FIELD_PATTERNS,
    FIELDS,
    StudyRecord,
    extract,
    find_labeled_value,
    normalize_phase,
)


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


_PATTERNS = FIELD_PATTERNS
_CORE_FIELDS = {"study_id", "phase", "participants", "intervention", "primary_endpoint"}


def _normalize(field: str, raw_value: str) -> str:
    cleaned = raw_value.strip()
    if field == "phase":
        return normalize_phase(cleaned)
    if field == "participants":
        return cleaned.replace(",", "")
    return cleaned


def extract_with_provenance(text: str) -> ExtractionProvenance:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    record = extract(text)
    evidence: list[FieldEvidence] = []
    for field in FIELDS:
        found = find_labeled_value(field, text)
        if found is None:
            continue
        evidence.append(
            FieldEvidence(
                field=field,
                raw_value=found.raw_value,
                normalized_value=_normalize(field, found.raw_value),
                start=found.start,
                end=found.end,
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

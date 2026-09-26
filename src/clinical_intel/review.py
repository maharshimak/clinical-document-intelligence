from __future__ import annotations

from dataclasses import dataclass

from clinical_intel.extract import StudyRecord, validate


@dataclass(frozen=True, slots=True)
class FieldEvidence:
    field: str
    confidence: float
    evidence: str

    def __post_init__(self) -> None:
        if not self.field.strip():
            raise ValueError("field is required")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if not self.evidence.strip():
            raise ValueError("evidence is required")


@dataclass(frozen=True, slots=True)
class ReviewDecision:
    requires_review: bool
    reasons: tuple[str, ...]
    minimum_confidence: float | None
    missing_evidence_fields: tuple[str, ...]


def review_gate(
    record: StudyRecord,
    evidence: list[FieldEvidence],
    *,
    confidence_threshold: float = 0.8,
    critical_fields: tuple[str, ...] = ("study_id", "phase", "participants", "primary_endpoint"),
) -> ReviewDecision:
    """Route uncertain or structurally invalid extractions to human review."""
    if not 0 <= confidence_threshold <= 1:
        raise ValueError("confidence_threshold must be between 0 and 1")

    reasons = list(validate(record))
    by_field = {item.field: item for item in evidence}
    missing_evidence: list[str] = []
    confidences: list[float] = []

    for field in critical_fields:
        value = getattr(record, field, None)
        if value is None:
            reasons.append(f"critical field missing: {field}")
            continue
        field_evidence = by_field.get(field)
        if field_evidence is None:
            missing_evidence.append(field)
            reasons.append(f"critical field has no provenance: {field}")
            continue
        confidences.append(field_evidence.confidence)
        if field_evidence.confidence < confidence_threshold:
            reasons.append(
                f"low confidence for {field}: {field_evidence.confidence:.3f} "
                f"< {confidence_threshold:.3f}"
            )

    minimum = min(confidences) if confidences else None
    return ReviewDecision(
        requires_review=bool(reasons),
        reasons=tuple(dict.fromkeys(reasons)),
        minimum_confidence=minimum,
        missing_evidence_fields=tuple(missing_evidence),
    )

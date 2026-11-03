"""Field-level extraction results that are bound to verified source evidence.

Invariant: every non-null field produced by an extractor (rule-based or model)
carries an ``EvidenceSpan`` with ``document.text[start:end] == span.text``.
A non-null field without evidence is only allowed when its origin is ``human``.

Confidence is explicit about where it came from:

* ``not_estimated`` - no score exists (the rule-based extractor matches labels; it
  does not produce a probability, so none is invented);
* ``model_self_reported`` - a number returned by a model, not calibrated here;
* ``human_asserted`` - a value entered by a reviewer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from clinical_intel.document import SourceDocument, utf16_offset
from clinical_intel.extract import (
    FIELDS,
    find_labeled_values,
    normalize_phase,
    parse_participants,
)
from clinical_intel.schema import validate_field

Origin = Literal["rule_based", "model", "human"]
ConfidenceOrigin = Literal["not_estimated", "model_self_reported", "human_asserted"]
ORIGINS: tuple[str, ...] = ("rule_based", "model", "human")
CONFIDENCE_ORIGINS: tuple[str, ...] = ("not_estimated", "model_self_reported", "human_asserted")
CRITICAL_FIELDS: tuple[str, ...] = ("study_id", "phase", "participants", "primary_endpoint")
RULE_EXTRACTOR_ID = "rule_based:labeled-lines.v1"


class EvidenceError(ValueError):
    """Raised when evidence does not reference the exact source text."""


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True, slots=True)
class EvidenceSpan:
    """Half-open code point span ``[start, end)`` and the exact text it covers."""

    start: int
    end: int
    text: str

    def __post_init__(self) -> None:
        if not _is_int(self.start) or not _is_int(self.end):
            raise EvidenceError("evidence offsets must be integers")
        if not 0 <= self.start < self.end:
            raise EvidenceError("evidence span must satisfy 0 <= start < end")
        if not isinstance(self.text, str) or len(self.text) != self.end - self.start:
            raise EvidenceError("evidence text length must equal end - start")

    @classmethod
    def from_source(cls, source: str, start: int, end: int) -> EvidenceSpan:
        if not _is_int(start) or not _is_int(end) or not 0 <= start < end <= len(source):
            raise EvidenceError("evidence span is outside the document")
        return cls(start, end, source[start:end])

    def verify(self, source: str) -> None:
        if self.end > len(source) or source[self.start : self.end] != self.text:
            raise EvidenceError(
                f"evidence [{self.start}, {self.end}) does not match the source text"
            )

    def to_dict(self) -> dict[str, object]:
        return {"start": self.start, "end": self.end, "text": self.text}

    @classmethod
    def from_dict(cls, payload: object) -> EvidenceSpan:
        if not isinstance(payload, dict) or set(payload) != {"start", "end", "text"}:
            raise EvidenceError("evidence must be an object with start, end and text")
        return cls(payload["start"], payload["end"], payload["text"])


@dataclass(frozen=True, slots=True)
class ExtractedField:
    field: str
    value: str | int | None
    origin: Origin
    evidence: EvidenceSpan | None
    confidence: float | None = None
    confidence_origin: ConfidenceOrigin = "not_estimated"

    def __post_init__(self) -> None:
        if self.field not in FIELDS:
            raise ValueError(f"unknown field: {self.field}")
        if self.origin not in ORIGINS:
            raise ValueError(f"unknown origin: {self.origin}")
        if self.confidence_origin not in CONFIDENCE_ORIGINS:
            raise ValueError(f"unknown confidence origin: {self.confidence_origin}")
        if self.evidence is not None and not isinstance(self.evidence, EvidenceSpan):
            raise TypeError("evidence must be an EvidenceSpan or None")
        if self.value is None:
            if self.evidence is not None:
                raise EvidenceError(f"null field {self.field} cannot carry evidence")
            if self.confidence is not None:
                raise ValueError(f"null field {self.field} cannot carry confidence")
        elif self.origin != "human" and self.evidence is None:
            raise EvidenceError(
                f"{self.origin} field {self.field} requires evidence or must be human-supplied"
            )
        if self.confidence is not None:
            if isinstance(self.confidence, bool) or not isinstance(self.confidence, int | float):
                raise ValueError("confidence must be a number")
            if not 0.0 <= float(self.confidence) <= 1.0:
                raise ValueError("confidence must be between 0 and 1")
        expected = {
            "rule_based": ("not_estimated",),
            "model": ("not_estimated", "model_self_reported"),
            "human": ("human_asserted",),
        }[self.origin]
        if self.confidence_origin not in expected:
            raise ValueError(
                f"confidence origin {self.confidence_origin} is not valid for {self.origin}"
            )
        if self.confidence is not None and self.confidence_origin != "model_self_reported":
            raise ValueError("only model-reported confidence may carry a numeric value")

    def verify(self, document: SourceDocument) -> None:
        if self.evidence is not None:
            self.evidence.verify(document.text)

    def to_dict(self, document: SourceDocument | None = None) -> dict[str, object]:
        evidence: dict[str, object] | None = None
        if self.evidence is not None:
            evidence = {**self.evidence.to_dict(), "unit": "unicode_code_point"}
            if document is not None:
                evidence["utf16_start"] = utf16_offset(document.text, self.evidence.start)
                evidence["utf16_end"] = utf16_offset(document.text, self.evidence.end)
        return {
            "field": self.field,
            "value": self.value,
            "origin": self.origin,
            "evidence": evidence,
            "confidence": self.confidence,
            "confidence_origin": self.confidence_origin,
            "validation_errors": validate_field(self.field, self.value),
        }


@dataclass(frozen=True, slots=True)
class ExtractionIssue:
    field: str
    code: str
    message: str
    span: tuple[int, int] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "field": self.field,
            "code": self.code,
            "message": self.message,
            "span": list(self.span) if self.span else None,
        }


def review_reasons(
    fields: dict[str, ExtractedField] | tuple[ExtractedField, ...],
    issues: tuple[ExtractionIssue, ...] = (),
) -> tuple[str, ...]:
    by_field = fields if isinstance(fields, dict) else {item.field: item for item in fields}
    reasons = [f"{issue.field}: {issue.message}" for issue in issues]
    for name in FIELDS:
        item = by_field.get(name)
        if item is not None:
            reasons.extend(validate_field(name, item.value))
    for name in CRITICAL_FIELDS:
        item = by_field.get(name)
        if item is None or item.value is None:
            reasons.append(f"critical field missing: {name}")
    return tuple(dict.fromkeys(reasons))


@dataclass(frozen=True, slots=True)
class DocumentExtraction:
    document_sha256: str
    extractor: str
    fields: tuple[ExtractedField, ...]
    issues: tuple[ExtractionIssue, ...] = ()

    def __post_init__(self) -> None:
        if tuple(item.field for item in self.fields) != FIELDS:
            raise ValueError("extraction must contain every schema field exactly once, in order")

    def field(self, name: str) -> ExtractedField:
        for item in self.fields:
            if item.field == name:
                return item
        raise KeyError(name)

    @property
    def review_reasons(self) -> tuple[str, ...]:
        return review_reasons(self.fields, self.issues)

    @property
    def requires_review(self) -> bool:
        return bool(self.review_reasons)

    def verify(self, document: SourceDocument) -> None:
        document.require_version(self.document_sha256)
        for item in self.fields:
            item.verify(document)


def _rule_value(field: str, raw_value: str) -> str | int:
    if field == "phase":
        return normalize_phase(raw_value)
    if field == "participants":
        return parse_participants(raw_value)
    return raw_value


def extract_document(document: SourceDocument) -> DocumentExtraction:
    """Rule-based extraction where every non-null field cites its labeled line.

    Unlike :func:`clinical_intel.extract.extract`, an unparseable value does not abort
    the whole document: the field stays null and an issue records the source span.
    Repeated labels with different values are reported as a conflict (the first
    occurrence is kept, matching ``extract``).
    """
    if not isinstance(document, SourceDocument):
        raise TypeError("document must be a SourceDocument")
    text = document.text
    fields: list[ExtractedField] = []
    issues: list[ExtractionIssue] = []
    for name in FIELDS:
        occurrences = find_labeled_values(name, text)
        if not occurrences:
            fields.append(ExtractedField(name, None, "rule_based", None))
            continue
        first = occurrences[0]
        distinct = dict.fromkeys(item.raw_value for item in occurrences)
        if len(distinct) > 1:
            other = next(item for item in occurrences if item.raw_value != first.raw_value)
            issues.append(
                ExtractionIssue(
                    name,
                    "CONFLICTING_VALUES",
                    f"label appears {len(occurrences)} times with {len(distinct)} different "
                    "values; first occurrence used",
                    (other.start, other.end),
                )
            )
        try:
            value = _rule_value(name, first.raw_value)
        except ValueError as error:
            issues.append(
                ExtractionIssue(name, "UNPARSEABLE_VALUE", str(error), (first.start, first.end))
            )
            fields.append(ExtractedField(name, None, "rule_based", None))
            continue
        span = EvidenceSpan(first.start, first.end, first.raw_value)
        fields.append(ExtractedField(name, value, "rule_based", span))
    result = DocumentExtraction(document.sha256, RULE_EXTRACTOR_ID, tuple(fields), tuple(issues))
    result.verify(document)
    return result


def from_model_result(document: SourceDocument, result: object) -> DocumentExtraction:
    """Bind a :class:`ModelExtractionResult` to a document version, verifying every span.

    Offsets reported by the model adapter are re-checked against the exact source
    text; a span that does not reproduce its evidence string is rejected.
    """
    fields: list[ExtractedField] = []
    by_field = {row.field: row for row in result.evidence}  # type: ignore[attr-defined]
    for name in FIELDS:
        row = by_field.get(name)
        if row is None or row.value is None:
            fields.append(ExtractedField(name, None, "model", None))
            continue
        if row.start is None or row.end is None or row.evidence is None:
            raise EvidenceError(f"model field {name} has no evidence offsets")
        span = EvidenceSpan(row.start, row.end, row.evidence)
        span.verify(document.text)
        fields.append(ExtractedField(name, row.value, "model", span))
    extraction = DocumentExtraction(document.sha256, "model:openai_compatible", tuple(fields))
    extraction.verify(document)
    return extraction


_PHASE_TOKEN = re.compile(r"(?<![0-9A-Za-z])(IV|I{1,3}|[1-4])(?![0-9A-Za-z.])", re.IGNORECASE)
_COUNT_TOKEN = re.compile(r"(?<![0-9,.])(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?![0-9,.])")


def _normalize_text(value: str) -> str:
    return re.sub(r"[^\w]+", " ", value.casefold()).strip()


def value_supported_by(field: str, value: object, evidence_text: str) -> bool:
    """Whether ``evidence_text`` literally supports ``value`` (used for cited corrections)."""
    if value is None:
        return False
    if field == "phase":
        tokens = {normalize_phase(token) for token in _PHASE_TOKEN.findall(evidence_text)}
        return str(value) in tokens
    if field == "participants":
        tokens = {int(token.replace(",", "")) for token in _COUNT_TOKEN.findall(evidence_text)}
        return value in tokens
    needle = _normalize_text(str(value))
    # Whole-word containment: "Drug A" is not supported by "Drug AB".
    return bool(needle) and f" {needle} " in f" {_normalize_text(evidence_text)} "

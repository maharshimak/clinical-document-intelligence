"""Append-only human review history bound to one document version.

A ``ReviewLog`` is immutable: ``correct`` and ``confirm`` return a new log whose
events start with every event of the old one. Each event stores the SHA-256 of the
previous event, so edits to serialized history are detected by ``from_events``.
The hash chain detects accidental or naive edits; it is not a signature and does
not authenticate reviewers.

A correction never inherits the citation of the value it replaces: it carries
either evidence explicitly cited by the reviewer (verified against the document
and checked to literally support the corrected value) or no evidence, in which
case the field is marked ``origin="human"``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from hashlib import sha256
from typing import Literal

from clinical_intel.document import DocumentVersionError, SourceDocument
from clinical_intel.evidence import (
    CONFIDENCE_ORIGINS,
    ORIGINS,
    DocumentExtraction,
    EvidenceError,
    EvidenceSpan,
    ExtractedField,
    value_supported_by,
)
from clinical_intel.extract import FIELDS
from clinical_intel.schema import validate_field

EventKind = Literal["extraction", "correction", "confirmation"]
_KINDS = ("extraction", "correction", "confirmation")
_EVENT_KEYS = {
    "sequence",
    "kind",
    "document_sha256",
    "field",
    "value",
    "origin",
    "evidence",
    "confidence",
    "confidence_origin",
    "actor",
    "reason",
    "recorded_at",
    "previous_hash",
    "event_hash",
}
MAX_EVENTS = 10_000


class ReviewHistoryError(ValueError):
    """Raised when serialized review history is malformed or has been altered."""


def _canonical_hash(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _require_text(name: str, value: object, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} must be a non-empty string of at most {limit} characters")
    return value


@dataclass(frozen=True, slots=True)
class ReviewEvent:
    sequence: int
    kind: EventKind
    document_sha256: str
    field: str
    value: str | int | None
    origin: str
    evidence: EvidenceSpan | None
    confidence: float | None
    confidence_origin: str
    actor: str
    reason: str | None
    recorded_at: str | None
    previous_hash: str | None
    event_hash: str = ""

    def body(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "kind": self.kind,
            "document_sha256": self.document_sha256,
            "field": self.field,
            "value": self.value,
            "origin": self.origin,
            "evidence": self.evidence.to_dict() if self.evidence else None,
            "confidence": self.confidence,
            "confidence_origin": self.confidence_origin,
            "actor": self.actor,
            "reason": self.reason,
            "recorded_at": self.recorded_at,
            "previous_hash": self.previous_hash,
        }

    def sealed(self) -> ReviewEvent:
        return replace(self, event_hash=_canonical_hash(self.body()))

    def to_dict(self) -> dict[str, object]:
        return {**self.body(), "event_hash": self.event_hash}

    def as_field(self) -> ExtractedField:
        return ExtractedField(
            self.field,
            self.value,
            self.origin,  # type: ignore[arg-type]
            self.evidence,
            self.confidence,
            self.confidence_origin,  # type: ignore[arg-type]
        )


@dataclass(frozen=True, slots=True)
class ReviewLog:
    document_sha256: str
    events: tuple[ReviewEvent, ...]

    # -- construction -----------------------------------------------------------------
    @classmethod
    def from_extraction(cls, extraction: DocumentExtraction) -> ReviewLog:
        log = cls(extraction.document_sha256, ())
        for item in extraction.fields:
            log = log._append(
                kind="extraction",
                item=item,
                actor=extraction.extractor,
                reason=None,
                recorded_at=None,
            )
        return log

    @classmethod
    def from_events(cls, document: SourceDocument, events: object) -> ReviewLog:
        """Rebuild and verify serialized history against ``document``."""
        if not isinstance(events, list) or not events:
            raise ReviewHistoryError("events must be a non-empty list")
        if len(events) > MAX_EVENTS:
            raise ReviewHistoryError(f"history exceeds {MAX_EVENTS} events")
        rebuilt: list[ReviewEvent] = []
        previous: str | None = None
        for index, raw in enumerate(events):
            if not isinstance(raw, dict) or set(raw) != _EVENT_KEYS:
                raise ReviewHistoryError(f"event {index} has missing or unknown keys")
            if raw["document_sha256"] != document.sha256:
                raise DocumentVersionError(f"event {index} is bound to a different document")
            if raw["sequence"] != index or raw["kind"] not in _KINDS:
                raise ReviewHistoryError(f"event {index} has an invalid sequence or kind")
            if raw["previous_hash"] != previous:
                raise ReviewHistoryError(f"event {index} does not chain to the previous event")
            if raw["origin"] not in ORIGINS or raw["confidence_origin"] not in CONFIDENCE_ORIGINS:
                raise ReviewHistoryError(f"event {index} has an invalid origin")
            try:
                evidence = (
                    EvidenceSpan.from_dict(raw["evidence"]) if raw["evidence"] is not None else None
                )
                if evidence is not None:
                    evidence.verify(document.text)
                event = ReviewEvent(
                    sequence=index,
                    kind=raw["kind"],
                    document_sha256=raw["document_sha256"],
                    field=raw["field"],
                    value=raw["value"],
                    origin=raw["origin"],
                    evidence=evidence,
                    confidence=raw["confidence"],
                    confidence_origin=raw["confidence_origin"],
                    actor=raw["actor"],
                    reason=raw["reason"],
                    recorded_at=raw["recorded_at"],
                    previous_hash=previous,
                )
                event.as_field()  # enforce field-level invariants
            except (EvidenceError, TypeError, ValueError) as error:
                raise ReviewHistoryError(f"event {index} is invalid: {error}") from error
            sealed = event.sealed()
            if sealed.event_hash != raw["event_hash"]:
                raise ReviewHistoryError(f"event {index} hash does not match its content")
            rebuilt.append(sealed)
            previous = sealed.event_hash
        log = cls(document.sha256, tuple(rebuilt))
        leading = [(e.kind, e.field) for e in log.events[: len(FIELDS)]]
        extraction_events = sum(e.kind == "extraction" for e in log.events)
        if leading != [("extraction", name) for name in FIELDS] or extraction_events != len(
            FIELDS
        ):
            raise ReviewHistoryError("history must start with one extraction event per field")
        return log

    # -- queries ----------------------------------------------------------------------
    def current_fields(self) -> dict[str, ExtractedField]:
        current: dict[str, ExtractedField] = {}
        for event in self.events:
            if event.kind != "confirmation":
                current[event.field] = event.as_field()
        return current

    def review_status(self) -> dict[str, str]:
        status = {name: "unreviewed" for name in FIELDS}
        for event in self.events:
            if event.kind == "correction":
                status[event.field] = "corrected"
            elif event.kind == "confirmation" and status[event.field] == "unreviewed":
                status[event.field] = "confirmed"
        return status

    def to_events(self) -> list[dict[str, object]]:
        return [event.to_dict() for event in self.events]

    # -- appends ----------------------------------------------------------------------
    def _append(
        self,
        *,
        kind: EventKind,
        item: ExtractedField,
        actor: str,
        reason: str | None,
        recorded_at: str | None,
    ) -> ReviewLog:
        if len(self.events) >= MAX_EVENTS:
            raise ReviewHistoryError(f"history exceeds {MAX_EVENTS} events")
        previous = self.events[-1].event_hash if self.events else None
        event = ReviewEvent(
            sequence=len(self.events),
            kind=kind,
            document_sha256=self.document_sha256,
            field=item.field,
            value=item.value,
            origin=item.origin,
            evidence=item.evidence,
            confidence=item.confidence,
            confidence_origin=item.confidence_origin,
            actor=actor,
            reason=reason,
            recorded_at=recorded_at,
            previous_hash=previous,
        ).sealed()
        return ReviewLog(self.document_sha256, (*self.events, event))

    def correct(
        self,
        document: SourceDocument,
        field: str,
        value: str | int | None,
        *,
        reviewer: str,
        reason: str,
        evidence: tuple[int, int] | None = None,
        recorded_at: str | None = None,
    ) -> ReviewLog:
        """Append a human correction.

        ``evidence`` is an optional ``(start, end)`` span the reviewer cites. It must
        lie inside ``document`` and literally support ``value``. Without it the
        corrected field has no evidence and ``origin="human"``.
        """
        document.require_version(self.document_sha256)
        if field not in FIELDS:
            raise ValueError(f"unknown field: {field}")
        _require_text("reviewer", reviewer, 128)
        _require_text("reason", reason, 1000)
        if recorded_at is not None:
            _require_text("recorded_at", recorded_at, 64)
        errors = validate_field(field, value)
        if errors:
            raise ValueError("; ".join(errors))
        span: EvidenceSpan | None = None
        if evidence is not None:
            if value is None:
                raise EvidenceError("a correction to null cannot cite evidence")
            if not isinstance(evidence, tuple | list) or len(evidence) != 2:
                raise EvidenceError("evidence must be a (start, end) pair")
            span = EvidenceSpan.from_source(document.text, evidence[0], evidence[1])
            if not value_supported_by(field, value, span.text):
                raise EvidenceError(
                    f"cited evidence {span.text!r} does not support the corrected value"
                )
        current = self.current_fields()[field]
        if current.value == value and current.evidence == span and current.origin == "human":
            raise ValueError("correction does not change the field")
        corrected = ExtractedField(field, value, "human", span, None, "human_asserted")
        return self._append(
            kind="correction",
            item=corrected,
            actor=reviewer,
            reason=reason,
            recorded_at=recorded_at,
        )

    def confirm(
        self,
        field: str,
        *,
        reviewer: str,
        recorded_at: str | None = None,
    ) -> ReviewLog:
        """Record that a reviewer accepted the current value (and its evidence) as is."""
        if field not in FIELDS:
            raise ValueError(f"unknown field: {field}")
        _require_text("reviewer", reviewer, 128)
        if recorded_at is not None:
            _require_text("recorded_at", recorded_at, 64)
        return self._append(
            kind="confirmation",
            item=self.current_fields()[field],
            actor=reviewer,
            reason=None,
            recorded_at=recorded_at,
        )

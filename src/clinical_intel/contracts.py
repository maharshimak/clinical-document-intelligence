"""``makma.v1`` execution envelope for clinical-document-intelligence.

Pydantic is not a dependency of this package, so the envelope is a frozen dataclass
with explicit validation (as permitted by the shared contract). Conformance is
checked in tests against ``contracts/makma.v1.schema.json``.

All operations are pure, offline and rule-based: ``execution_mode`` is always
``deterministic_offline``. No operation calls a model or the network.
"""

from __future__ import annotations

import json
import re
import secrets
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from importlib import metadata
from typing import Any

from clinical_intel.document import DocumentVersionError, SourceDocument
from clinical_intel.evaluation import (
    BUNDLED_DATASETS,
    MAX_EXAMPLES,
    evaluate,
    load_bundled,
    load_examples,
)
from clinical_intel.evidence import RULE_EXTRACTOR_ID, EvidenceError, extract_document
from clinical_intel.export import export_review
from clinical_intel.extract import FIELDS
from clinical_intel.review_log import ReviewHistoryError, ReviewLog

CONTRACT_VERSION = "makma.v1"
SYSTEM = "clinical-document-intelligence"
EXECUTION_MODE = "deterministic_offline"
MAX_TEXT_CHARS = 200_000
_OPERATION_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_STATUSES = ("ok", "error", "blocked", "pending_approval")
_PROVENANCE_KINDS = ("document", "chunk", "artifact", "dataset", "model", "query", "record")


def _package_version() -> str:
    try:
        return metadata.version("clinical-document-intelligence")
    except metadata.PackageNotFoundError:
        return "0.0.0+unknown"


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(encoded.encode("utf-8")).hexdigest()


# -- envelope ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProvenanceRef:
    kind: str
    id: str
    sha256: str | None = None
    span: tuple[int, int] | None = None
    uri: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in _PROVENANCE_KINDS:
            raise ValueError(f"invalid provenance kind: {self.kind}")
        if not self.id:
            raise ValueError("provenance id is required")
        if self.sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", self.sha256):
            raise ValueError("provenance sha256 must be 64 lowercase hex characters")
        if self.span is not None and (
            len(self.span) != 2 or any(not isinstance(i, int) or i < 0 for i in self.span)
        ):
            raise ValueError("provenance span must be two non-negative integers")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "id": self.id,
            "sha256": self.sha256,
            "span": list(self.span) if self.span is not None else None,
            "uri": self.uri,
        }


@dataclass(frozen=True, slots=True)
class ContractError:
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", self.code):
            raise ValueError("error code must be UPPER_SNAKE")

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message[:2000],
            "retryable": self.retryable,
            "details": self.details,
        }


@dataclass(frozen=True, slots=True)
class Envelope:
    operation: str
    run_id: str
    correlation_id: str
    trace_id: str
    span_id: str
    status: str
    data: Any
    error: ContractError | None
    provenance: tuple[ProvenanceRef, ...]
    started_at: str
    duration_ms: float
    execution_mode: str = EXECUTION_MODE
    policy: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not _OPERATION_NAME.fullmatch(self.operation):
            raise ValueError("invalid operation name")
        for name in ("run_id", "correlation_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not 1 <= len(value) <= 128:
                raise ValueError(f"{name} must be 1-128 characters")
        if not re.fullmatch(r"[0-9a-f]{32}", self.trace_id):
            raise ValueError("trace_id must be 32 lowercase hex characters")
        if not re.fullmatch(r"[0-9a-f]{16}", self.span_id):
            raise ValueError("span_id must be 16 lowercase hex characters")
        if self.status not in _STATUSES:
            raise ValueError("invalid status")
        if self.execution_mode not in ("deterministic_offline", "local_model", "remote_model"):
            raise ValueError("invalid execution_mode")
        if (self.status == "ok") != (self.error is None):
            raise ValueError("status 'ok' if and only if error is null")
        if self.status in ("error", "blocked") and self.data is not None:
            raise ValueError("data must be null when status is error or blocked")
        if self.status == "pending_approval" and (
            not self.policy or self.policy.get("decision") != "requires_approval"
        ):
            raise ValueError("pending_approval requires policy.decision == requires_approval")
        if self.duration_ms < 0:
            raise ValueError("duration_ms must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": CONTRACT_VERSION,
            "system": SYSTEM,
            "operation": self.operation,
            "run_id": self.run_id,
            "correlation_id": self.correlation_id,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "status": self.status,
            "execution_mode": self.execution_mode,
            "data": self.data,
            "error": self.error.to_dict() if self.error else None,
            "provenance": [ref.to_dict() for ref in self.provenance],
            "policy": self.policy,
            "started_at": self.started_at,
            "duration_ms": self.duration_ms,
        }


# -- input validation helpers -----------------------------------------------------------


class InvalidInput(ValueError):
    pass


def _object(payload: object, required: set[str], optional: set[str], where: str) -> dict:
    if not isinstance(payload, Mapping):
        raise InvalidInput(f"{where} must be an object")
    keys = set(payload)
    missing, unknown = required - keys, keys - required - optional
    if missing:
        raise InvalidInput(f"{where} is missing: {', '.join(sorted(missing))}")
    if unknown:
        raise InvalidInput(f"{where} has unknown keys: {', '.join(sorted(unknown))}")
    return dict(payload)


def _document(payload: dict) -> SourceDocument:
    text = payload["text"]
    if not isinstance(text, str) or not text or len(text) > MAX_TEXT_CHARS:
        raise InvalidInput(f"text must be a string of 1-{MAX_TEXT_CHARS} characters")
    try:
        return SourceDocument.from_text(text)
    except ValueError as error:
        raise InvalidInput(str(error)) from error


def _log_for(document: SourceDocument, history: object | None):
    extraction = extract_document(document)
    if history is None:
        return ReviewLog.from_extraction(extraction), extraction.issues
    log = ReviewLog.from_events(document, history)
    issues = extraction.issues if log.events[0].actor == RULE_EXTRACTOR_ID else ()
    return log, issues


def _field_provenance(document: SourceDocument, export: dict) -> list[ProvenanceRef]:
    refs = [ProvenanceRef("document", f"sha256:{document.sha256}", document.sha256)]
    for row in export["fields"]:
        evidence = row["evidence"]
        if evidence is None:
            continue
        refs.append(
            ProvenanceRef(
                "chunk",
                f"sha256:{document.sha256}#field={row['field']}",
                sha256(evidence["text"].encode("utf-8")).hexdigest(),
                (evidence["start"], evidence["end"]),
            )
        )
    return refs


# -- operations ---------------------------------------------------------------------------

_TEXT_SCHEMA = {"type": "string", "minLength": 1, "maxLength": MAX_TEXT_CHARS}
_HISTORY_SCHEMA = {
    "type": "array",
    "minItems": len(FIELDS),
    "items": {"type": "object"},
    "description": "Review events returned as data.history by a previous call.",
}


def _op_extract(payload: object) -> tuple[Any, list[ProvenanceRef]]:
    body = _object(payload, {"text"}, set(), "payload")
    document = _document(body)
    log, issues = _log_for(document, None)
    export = export_review(document, log, issues=issues)
    return export, _field_provenance(document, export)


def _op_apply_correction(payload: object) -> tuple[Any, list[ProvenanceRef]]:
    body = _object(payload, {"text", "correction"}, {"history"}, "payload")
    document = _document(body)
    correction = _object(
        body["correction"],
        {"field", "reviewer"},
        {"action", "value", "reason", "evidence_span", "recorded_at"},
        "correction",
    )
    action = correction.get("action", "correct")
    log, issues = _log_for(document, body.get("history"))
    if action == "correct":
        if "value" not in correction or "reason" not in correction:
            raise InvalidInput("a correction requires value and reason")
        span = correction.get("evidence_span")
        log = log.correct(
            document,
            correction["field"],
            correction["value"],
            reviewer=correction["reviewer"],
            reason=correction["reason"],
            evidence=tuple(span) if isinstance(span, list) else span,
            recorded_at=correction.get("recorded_at"),
        )
    elif action == "confirm":
        if {"value", "evidence_span"} & set(correction):
            raise InvalidInput("a confirmation cannot change value or evidence")
        log = log.confirm(
            correction["field"],
            reviewer=correction["reviewer"],
            recorded_at=correction.get("recorded_at"),
        )
    else:
        raise InvalidInput("correction.action must be 'correct' or 'confirm'")
    export = export_review(document, log, issues=issues)
    return export, _field_provenance(document, export)


def _op_export(payload: object) -> tuple[Any, list[ProvenanceRef]]:
    body = _object(payload, {"text"}, {"history", "include_history"}, "payload")
    include_history = body.get("include_history", True)
    if not isinstance(include_history, bool):
        raise InvalidInput("include_history must be a boolean")
    document = _document(body)
    log, issues = _log_for(document, body.get("history"))
    export = export_review(document, log, issues=issues, include_history=include_history)
    return export, _field_provenance(document, export)


def _op_evaluate(payload: object) -> tuple[Any, list[ProvenanceRef]]:
    body = _object(payload, set(), {"dataset", "examples"}, "payload")
    if ("dataset" in body) == ("examples" in body):
        raise InvalidInput("provide exactly one of dataset or examples")
    if "dataset" in body:
        if body["dataset"] not in BUNDLED_DATASETS:
            raise InvalidInput(f"dataset must be one of: {', '.join(BUNDLED_DATASETS)}")
        name = body["dataset"]
        raw_examples = load_bundled(name)["examples"]
    else:
        name = "inline"
        raw_examples = body["examples"]
    examples = load_examples(raw_examples)
    for example in examples:
        if len(example.text) > MAX_TEXT_CHARS:
            raise InvalidInput(f"example {example.id} exceeds {MAX_TEXT_CHARS} characters")
    report = evaluate(examples)
    report["dataset"] = name
    report["predictor"] = RULE_EXTRACTOR_ID
    digest = _canonical_sha256(
        [{"id": e.id, "text": e.text, "gold": e.gold} for e in examples]
    )
    return report, [ProvenanceRef("dataset", name, digest)]


@dataclass(frozen=True, slots=True)
class Operation:
    name: str
    handler: Callable[[object], tuple[Any, list[ProvenanceRef]]]
    input_schema: dict[str, Any]
    side_effects: bool = False
    requires_approval: bool = False
    timeout_s: int = 30


_FIELD_NAME_SCHEMA = {"enum": list(FIELDS)}

OPERATIONS: dict[str, Operation] = {
    op.name: op
    for op in (
        Operation(
            "extract",
            _op_extract,
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["text"],
                "properties": {"text": _TEXT_SCHEMA},
            },
        ),
        Operation(
            "apply_correction",
            _op_apply_correction,
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["text", "correction"],
                "properties": {
                    "text": _TEXT_SCHEMA,
                    "history": _HISTORY_SCHEMA,
                    "correction": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["field", "reviewer"],
                        "properties": {
                            "action": {"enum": ["correct", "confirm"], "default": "correct"},
                            "field": _FIELD_NAME_SCHEMA,
                            "value": {"type": ["string", "integer", "null"]},
                            "reason": {"type": "string", "minLength": 1, "maxLength": 1000},
                            "reviewer": {"type": "string", "minLength": 1, "maxLength": 128},
                            "evidence_span": {
                                "type": ["array", "null"],
                                "items": {"type": "integer", "minimum": 0},
                                "minItems": 2,
                                "maxItems": 2,
                            },
                            "recorded_at": {"type": "string", "maxLength": 64},
                        },
                    },
                },
            },
        ),
        Operation(
            "export",
            _op_export,
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["text"],
                "properties": {
                    "text": _TEXT_SCHEMA,
                    "history": _HISTORY_SCHEMA,
                    "include_history": {"type": "boolean", "default": True},
                },
            },
        ),
        Operation(
            "evaluate",
            _op_evaluate,
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "dataset": {"enum": list(BUNDLED_DATASETS)},
                    "examples": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": MAX_EXAMPLES,
                        "items": {
                            "type": "object",
                            "required": ["id", "text", "gold"],
                            "properties": {
                                "id": {"type": "string", "minLength": 1},
                                "text": {"type": "string", "maxLength": MAX_TEXT_CHARS},
                                "gold": {"type": "object", "required": list(FIELDS)},
                            },
                        },
                    },
                },
                "oneOf": [{"required": ["dataset"]}, {"required": ["examples"]}],
            },
            timeout_s=60,
        ),
    )
}


def capabilities() -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "system": SYSTEM,
        "version": _package_version(),
        "operations": [
            {
                "name": op.name,
                "side_effects": op.side_effects,
                "requires_approval": op.requires_approval,
                "input_schema": op.input_schema,
                "timeout_s": op.timeout_s,
            }
            for op in OPERATIONS.values()
        ],
    }


def _valid_id(value: object) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= 128


def run_operation(
    operation: str,
    payload: dict,
    *,
    run_id: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Run one operation in-process and return a ``makma.v1`` envelope as a dict."""
    started = time.perf_counter()
    started_at = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    error: ContractError | None = None
    data: Any = None
    provenance: list[ProvenanceRef] = []

    resolved_run_id = run_id if _valid_id(run_id) else uuid.uuid4().hex
    resolved_correlation = correlation_id if _valid_id(correlation_id) else resolved_run_id
    name = operation if isinstance(operation, str) and _OPERATION_NAME.fullmatch(operation) else ""
    op = OPERATIONS.get(name)

    if run_id is not None and not _valid_id(run_id):
        error = ContractError("INVALID_INPUT", "run_id must be a string of 1-128 characters")
    elif correlation_id is not None and not _valid_id(correlation_id):
        error = ContractError(
            "INVALID_INPUT", "correlation_id must be a string of 1-128 characters"
        )
    elif op is None:
        error = ContractError(
            "UNKNOWN_OPERATION",
            "unknown operation",
            details={
                "operation": str(operation)[:128],
                "available": sorted(OPERATIONS),
            },
        )
    else:
        try:
            data, provenance = op.handler(payload)
        except DocumentVersionError as exc:
            error = ContractError("DOCUMENT_VERSION_MISMATCH", str(exc))
        except ReviewHistoryError as exc:
            error = ContractError("INVALID_HISTORY", str(exc))
        except EvidenceError as exc:
            error = ContractError("EVIDENCE_MISMATCH", str(exc))
        except (InvalidInput, TypeError, ValueError, KeyError) as exc:
            error = ContractError("INVALID_INPUT", str(exc))
        except Exception as exc:  # noqa: BLE001 - never leak a traceback through the envelope
            error = ContractError(
                "INTERNAL_ERROR", "operation failed", details={"type": type(exc).__name__}
            )

    if error is not None:
        data, provenance = None, []
    envelope = Envelope(
        operation=name or "unknown",
        run_id=resolved_run_id,
        correlation_id=resolved_correlation,
        trace_id=uuid.uuid4().hex,
        span_id=secrets.token_hex(8),
        status="ok" if error is None else "error",
        data=data,
        error=error,
        provenance=tuple(provenance),
        started_at=started_at,
        duration_ms=round((time.perf_counter() - started) * 1000, 3),
    )
    return envelope.to_dict()

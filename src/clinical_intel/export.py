"""Structured JSON export of a reviewed extraction."""

from __future__ import annotations

from clinical_intel.document import SourceDocument
from clinical_intel.evidence import ExtractionIssue, review_reasons
from clinical_intel.review_log import ReviewLog
from clinical_intel.schema import SCHEMA_VERSION

EXPORT_VERSION = "clinical-intel.export.v1"


def export_review(
    document: SourceDocument,
    log: ReviewLog,
    *,
    issues: tuple[ExtractionIssue, ...] = (),
    include_history: bool = True,
) -> dict[str, object]:
    """Return a JSON-serializable export of the current field values and their history.

    Every evidence span is re-verified against ``document`` before export.
    Extraction ``issues`` (e.g. conflicting labels) keep a field in review until a
    reviewer confirms or corrects that field.
    """
    document.require_version(log.document_sha256)
    current = log.current_fields()
    for item in current.values():
        item.verify(document)
    status = log.review_status()
    open_issues = tuple(issue for issue in issues if status.get(issue.field) == "unreviewed")
    fields = []
    for name, item in current.items():
        row = item.to_dict(document)
        row["review_status"] = status[name]
        fields.append(row)
    reasons = review_reasons(current, open_issues)
    payload: dict[str, object] = {
        "export_version": EXPORT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "document": {
            "sha256": document.sha256,
            "source_sha256": document.source_sha256,
            "media_type": document.media_type,
            "length": len(document.text),
            "offset_unit": "unicode_code_point",
        },
        "extractor": log.events[0].actor if log.events else None,
        "fields": fields,
        "issues": [issue.to_dict() for issue in issues],
        "requires_review": bool(reasons),
        "review_reasons": list(reasons),
        "history_head": log.events[-1].event_hash if log.events else None,
    }
    if include_history:
        payload["history"] = log.to_events()
    return payload

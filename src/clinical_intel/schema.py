"""Per-field validation for the study-metadata extraction schema.

These checks describe the *shape* of a value (type, length, allowed vocabulary).
They do not judge whether a value is clinically correct.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

SCHEMA_VERSION = "study-metadata.v1"


@dataclass(frozen=True, slots=True)
class FieldSpec:
    kind: str  # "text" | "integer" | "enum"
    max_length: int = 500
    allowed: tuple[str, ...] = ()
    pattern: str | None = None
    minimum: int | None = None


FIELD_SPECS: dict[str, FieldSpec] = {
    "study_id": FieldSpec("text", max_length=64, pattern=r"[A-Za-z0-9][A-Za-z0-9._/:-]*"),
    "phase": FieldSpec("enum", allowed=("1", "2", "3", "4")),
    "participants": FieldSpec("integer", minimum=1),
    "intervention": FieldSpec("text"),
    "primary_endpoint": FieldSpec("text"),
    "sponsor": FieldSpec("text", max_length=200),
    "condition": FieldSpec("text"),
    "study_type": FieldSpec("text", max_length=200),
    "secondary_endpoint": FieldSpec("text"),
}


def _has_control_characters(value: str) -> bool:
    return any(unicodedata.category(char) == "Cc" for char in value)


def validate_field(field: str, value: object) -> list[str]:
    """Return human-readable validation errors for one field value (``None`` is valid)."""
    spec = FIELD_SPECS.get(field)
    if spec is None:
        return [f"{field}: unknown field"]
    if value is None:
        return []
    if spec.kind == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            return [f"{field}: must be an integer"]
        if spec.minimum is not None and value < spec.minimum:
            return [f"{field}: must be at least {spec.minimum}"]
        return []
    if not isinstance(value, str):
        return [f"{field}: must be a string"]
    if spec.kind == "enum":
        if value not in spec.allowed:
            return [f"{field}: must be one of {', '.join(spec.allowed)}"]
        return []
    errors: list[str] = []
    if not value.strip() or value != value.strip():
        errors.append(f"{field}: must be non-empty without surrounding whitespace")
    if len(value) > spec.max_length:
        errors.append(f"{field}: exceeds {spec.max_length} characters")
    if _has_control_characters(value):
        errors.append(f"{field}: contains control characters")
    if spec.pattern and value.strip() and not re.fullmatch(spec.pattern, value):
        errors.append(f"{field}: does not match identifier pattern {spec.pattern}")
    return errors

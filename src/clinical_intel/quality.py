import json
from dataclasses import asdict, dataclass
from hashlib import sha256

from clinical_intel.extract import StudyRecord, validate

DEFAULT_REQUIRED_FIELDS = (
    "study_id",
    "phase",
    "participants",
    "intervention",
    "primary_endpoint",
)


@dataclass(frozen=True, slots=True)
class ExtractionQuality:
    completeness: float
    production_ready: bool
    missing_fields: tuple[str, ...]
    validation_errors: tuple[str, ...]
    record_fingerprint: str


def record_fingerprint(record: StudyRecord) -> str:
    payload = json.dumps(
        asdict(record),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return sha256(payload).hexdigest()


def assess_extraction(
    record: StudyRecord,
    *,
    required_fields: tuple[str, ...] = DEFAULT_REQUIRED_FIELDS,
    min_completeness: float = 0.8,
) -> ExtractionQuality:
    if not required_fields:
        raise ValueError("required_fields cannot be empty")
    if not 0 <= min_completeness <= 1:
        raise ValueError("min_completeness must be between 0 and 1")
    unknown = [field for field in required_fields if not hasattr(record, field)]
    if unknown:
        raise ValueError("Unknown StudyRecord field(s): " + ", ".join(sorted(unknown)))

    missing = tuple(field for field in required_fields if getattr(record, field) is None)
    completeness = 1.0 - (len(missing) / len(required_fields))
    errors = tuple(validate(record))
    return ExtractionQuality(
        completeness=completeness,
        production_ready=not errors and completeness >= min_completeness,
        missing_fields=missing,
        validation_errors=errors,
        record_fingerprint=record_fingerprint(record),
    )

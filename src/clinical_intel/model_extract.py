from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib import request

from clinical_intel.extract import StudyRecord, validate

_FIELDS = (
    "study_id",
    "phase",
    "participants",
    "intervention",
    "primary_endpoint",
    "sponsor",
    "condition",
    "study_type",
    "secondary_endpoint",
)


@dataclass(frozen=True, slots=True)
class ModelFieldEvidence:
    field: str
    value: str | int | None
    evidence: str | None
    start: int | None
    end: int | None


@dataclass(frozen=True, slots=True)
class ModelExtractionResult:
    record: StudyRecord
    evidence: tuple[ModelFieldEvidence, ...]
    validation_errors: tuple[str, ...]
    grounded_fields: int
    evidence_coverage: float = 0.0
    requires_review: bool = False
    review_reasons: tuple[str, ...] = ()


@dataclass(slots=True)
class OpenAICompatibleClinicalExtractor:
    """Model-backed structured extraction with fail-closed evidence anchoring."""

    base_url: str
    model: str
    api_key: str = ""
    timeout_seconds: float = 60.0

    def __post_init__(self) -> None:
        if not self.base_url.strip() or not self.model.strip():
            raise ValueError("base_url and model are required.")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")

    def extract(self, text: str) -> ModelExtractionResult:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("document text must be non-empty.")
        if len(text) > 200_000:
            raise ValueError("document text exceeds 200000 characters.")

        system = (
            "Extract clinical study metadata from the supplied document. Return only JSON "
            "with a top-level 'fields' object. Each supported field must map to an object "
            "with 'value' and 'evidence'. Evidence must be a verbatim substring from the "
            "source supporting that value. Use null when unsupported. Never infer missing "
            "facts. Supported fields: " + ", ".join(_FIELDS) + "."
        )
        payload = json.dumps(
            {
                "model": self.model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": text},
                ],
            }
        ).encode()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        endpoint = self.base_url.rstrip("/") + "/chat/completions"
        req = request.Request(endpoint, data=payload, headers=headers, method="POST")
        with request.urlopen(req, timeout=self.timeout_seconds) as response:
            body = json.loads(response.read().decode())
        raw = str(body["choices"][0]["message"]["content"]).strip()
        return self.parse(text, raw)

    def parse(self, source_text: str, raw_json: str) -> ModelExtractionResult:
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError as error:
            raise ValueError("Clinical extractor returned invalid JSON.") from error
        fields = payload.get("fields")
        if not isinstance(fields, dict):
            raise TypeError("Clinical extraction JSON must contain a fields object.")
        unknown = sorted(set(fields) - set(_FIELDS))
        if unknown:
            raise ValueError("Unknown extracted field(s): " + ", ".join(unknown))

        values: dict[str, object] = {field: None for field in _FIELDS}
        evidence_rows: list[ModelFieldEvidence] = []
        grounded = 0

        for field in _FIELDS:
            item = fields.get(field, {"value": None, "evidence": None})
            if not isinstance(item, dict):
                raise TypeError(f"Field {field} must be an object.")
            value = item.get("value")
            evidence = item.get("evidence")

            if value is None:
                if evidence not in (None, ""):
                    raise ValueError(f"Null field {field} cannot carry evidence.")
                evidence_rows.append(ModelFieldEvidence(field, None, None, None, None))
                continue

            if not isinstance(evidence, str) or not evidence.strip():
                raise ValueError(f"Field {field} requires verbatim evidence.")
            start = source_text.casefold().find(evidence.strip().casefold())
            if start < 0:
                raise ValueError(f"Evidence for {field} is not present in the source.")
            end = start + len(evidence.strip())

            if field == "participants":
                if isinstance(value, bool):
                    raise ValueError("participants must be an integer.")
                try:
                    value = int(str(value).replace(",", "").strip())
                except ValueError as error:
                    raise ValueError("participants must be an integer.") from error
                evidence_numbers = {
                    int(token.replace(",", ""))
                    for token in re.findall(r"\b\d[\d,]*\b", evidence)
                }
                if value not in evidence_numbers:
                    raise ValueError(
                        "participants value is not supported by its evidence span."
                    )
            elif field == "phase":
                rendered = str(value).strip()
                value = {"I": "1", "II": "2", "III": "3", "IV": "4"}.get(
                    rendered.upper(), rendered
                )
                evidence_phase = evidence.upper()
                supported = {
                    "1": ("PHASE 1", "PHASE I"),
                    "2": ("PHASE 2", "PHASE II"),
                    "3": ("PHASE 3", "PHASE III"),
                    "4": ("PHASE 4", "PHASE IV"),
                }.get(str(value), ())
                if supported and not any(token in evidence_phase for token in supported):
                    raise ValueError("phase value is not supported by its evidence span.")
            else:
                value = str(value).strip()
                if not value:
                    raise ValueError(f"Field {field} cannot be empty.")

                normalized_value = re.sub(
                    r"[^\w]+",
                    " ",
                    value.casefold(),
                    flags=re.UNICODE,
                ).strip()
                normalized_evidence = re.sub(
                    r"[^\w]+",
                    " ",
                    evidence.casefold(),
                    flags=re.UNICODE,
                ).strip()

                if normalized_value not in normalized_evidence:
                    raise ValueError(
                        f"{field} value is not supported by its evidence span."
                    )

            values[field] = value
            grounded += 1
            evidence_rows.append(
                ModelFieldEvidence(field, value, evidence.strip(), start, end)
            )

        record = StudyRecord(**values)
        validation_errors = tuple(validate(record))
        populated_fields = sum(value is not None for value in values.values())
        evidence_coverage = grounded / populated_fields if populated_fields else 0.0
        critical_fields = ("study_id", "phase", "participants", "primary_endpoint")
        review_reasons = list(validation_errors)
        for field in critical_fields:
            if getattr(record, field) is None:
                review_reasons.append(f"critical field missing: {field}")

        return ModelExtractionResult(
            record=record,
            evidence=tuple(evidence_rows),
            validation_errors=validation_errors,
            grounded_fields=grounded,
            evidence_coverage=evidence_coverage,
            requires_review=bool(review_reasons),
            review_reasons=tuple(dict.fromkeys(review_reasons)),
        )

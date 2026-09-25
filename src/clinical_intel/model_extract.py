from __future__ import annotations

import json
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
            elif field == "phase":
                rendered = str(value).strip()
                value = {"I": "1", "II": "2", "III": "3", "IV": "4"}.get(
                    rendered.upper(), rendered
                )
            else:
                value = str(value).strip()
                if not value:
                    raise ValueError(f"Field {field} cannot be empty.")

            values[field] = value
            grounded += 1
            evidence_rows.append(
                ModelFieldEvidence(field, value, evidence.strip(), start, end)
            )

        record = StudyRecord(**values)
        return ModelExtractionResult(
            record=record,
            evidence=tuple(evidence_rows),
            validation_errors=tuple(validate(record)),
            grounded_fields=grounded,
        )

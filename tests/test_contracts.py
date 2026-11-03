"""makma.v1 envelope conformance: real run_operation outputs validated by JSON Schema."""

import json
from datetime import datetime
from hashlib import sha256
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from clinical_intel.contracts import SYSTEM, capabilities, run_operation

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "contracts" / "makma.v1.schema.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())

TEXT = (
    "Study ID: SYN-500\n"
    "Phase: II\n"
    "Participants: 64\n"
    "Intervention: Example compound\n"
    "Primary Endpoint: Synthetic score\n"
)


def assert_envelope(envelope: dict, status: str) -> dict:
    errors = sorted(VALIDATOR.iter_errors(envelope), key=lambda e: list(e.path))
    assert not errors, [f"{list(e.path)}: {e.message}" for e in errors]
    assert envelope["system"] == SYSTEM
    assert envelope["status"] == status
    assert envelope["execution_mode"] == "deterministic_offline"
    assert envelope["started_at"].endswith("Z")
    started = datetime.fromisoformat(envelope["started_at"])
    assert started.utcoffset() is not None and started.utcoffset().total_seconds() == 0
    json.dumps(envelope)  # must be JSON serializable
    return envelope


def _extract() -> dict:
    return assert_envelope(run_operation("extract", {"text": TEXT}), "ok")


def test_schema_file_is_a_valid_draft_2020_12_schema() -> None:
    Draft202012Validator.check_schema(SCHEMA)
    assert SCHEMA["$id"].endswith("makma.v1.schema.json")


def test_capabilities_declare_valid_input_schemas() -> None:
    caps = capabilities()
    assert caps["contract_version"] == "makma.v1"
    assert caps["system"] == SYSTEM
    names = [op["name"] for op in caps["operations"]]
    assert names == ["extract", "apply_correction", "export", "evaluate"]
    for op in caps["operations"]:
        Draft202012Validator.check_schema(op["input_schema"])
        assert op["side_effects"] is False
        assert op["requires_approval"] is False
        assert op["timeout_s"] > 0


def test_example_payloads_satisfy_declared_input_schemas() -> None:
    schemas = {op["name"]: op["input_schema"] for op in capabilities()["operations"]}
    payloads = {
        "extract": {"text": TEXT},
        "apply_correction": {
            "text": TEXT,
            "correction": {"field": "phase", "value": "3", "reviewer": "r", "reason": "x"},
        },
        "export": {"text": TEXT, "include_history": False},
        "evaluate": {"dataset": "synthetic_v1"},
    }
    for name, payload in payloads.items():
        Draft202012Validator(schemas[name]).validate(payload)
        assert_envelope(run_operation(name, payload), "ok")


def test_extract_returns_verified_evidence_and_provenance() -> None:
    envelope = _extract()
    data = envelope["data"]
    document_sha = sha256(TEXT.encode("utf-8")).hexdigest()
    assert data["document"]["sha256"] == document_sha
    for row in data["fields"]:
        if row["value"] is not None:
            evidence = row["evidence"]
            assert TEXT[evidence["start"] : evidence["end"]] == evidence["text"]
            assert row["origin"] == "rule_based"
            assert row["confidence"] is None
    provenance = envelope["provenance"]
    assert provenance[0] == {
        "kind": "document",
        "id": f"sha256:{document_sha}",
        "sha256": document_sha,
        "span": None,
        "uri": None,
    }
    for ref in provenance[1:]:
        start, end = ref["span"]
        assert ref["sha256"] == sha256(TEXT[start:end].encode("utf-8")).hexdigest()


def test_apply_correction_chains_history_and_drops_old_citation() -> None:
    history = _extract()["data"]["history"]
    envelope = assert_envelope(
        run_operation(
            "apply_correction",
            {
                "text": TEXT,
                "history": history,
                "correction": {
                    "field": "participants",
                    "value": 65,
                    "reviewer": "reviewer-1",
                    "reason": "count updated in source table",
                },
            },
            run_id="run-123",
            correlation_id="corr-9",
        ),
        "ok",
    )
    assert envelope["run_id"] == "run-123"
    assert envelope["correlation_id"] == "corr-9"
    data = envelope["data"]
    participants = next(r for r in data["fields"] if r["field"] == "participants")
    assert participants["value"] == 65
    assert participants["origin"] == "human"
    assert participants["evidence"] is None
    assert data["history"][: len(history)] == history
    assert not any(ref["id"].endswith("#field=participants") for ref in envelope["provenance"])

    confirmed = assert_envelope(
        run_operation(
            "apply_correction",
            {
                "text": TEXT,
                "history": data["history"],
                "correction": {"action": "confirm", "field": "study_id", "reviewer": "r2"},
            },
        ),
        "ok",
    )
    rows = {r["field"]: r for r in confirmed["data"]["fields"]}
    assert rows["study_id"]["review_status"] == "confirmed"


def test_export_without_history_is_deterministic() -> None:
    first = assert_envelope(run_operation("export", {"text": TEXT, "include_history": False}), "ok")
    second = run_operation("export", {"text": TEXT, "include_history": False})
    assert first["data"] == second["data"]
    assert "history" not in first["data"]


def test_evaluate_reports_measured_metrics_with_dataset_hash() -> None:
    envelope = assert_envelope(run_operation("evaluate", {"dataset": "synthetic_v1"}), "ok")
    assert envelope["data"]["documents"] >= 10
    assert envelope["provenance"][0]["kind"] == "dataset"
    assert len(envelope["provenance"][0]["sha256"]) == 64


@pytest.mark.parametrize(
    ("operation", "payload", "code"),
    [
        ("extract", {}, "INVALID_INPUT"),
        ("extract", {"text": ""}, "INVALID_INPUT"),
        ("extract", {"text": 5}, "INVALID_INPUT"),
        ("extract", {"text": "x" * 200_001}, "INVALID_INPUT"),
        ("extract", {"text": "a", "extra": 1}, "INVALID_INPUT"),
        ("extract", ["not", "an", "object"], "INVALID_INPUT"),
        ("extract", {"text": "Study ID: " + chr(0xD800)}, "INVALID_INPUT"),
        ("apply_correction", {"text": TEXT, "correction": {"field": "phase"}}, "INVALID_INPUT"),
        (
            "apply_correction",
            {"text": TEXT, "correction": {"field": "phase", "value": "9", "reviewer": "r",
                                          "reason": "x"}},
            "INVALID_INPUT",
        ),
        (
            "apply_correction",
            {"text": TEXT, "correction": {"field": "phase", "value": "2", "reviewer": "r",
                                          "reason": "x", "evidence_span": [0, 5]}},
            "EVIDENCE_MISMATCH",
        ),
        (
            "apply_correction",
            {"text": TEXT, "history": [{}] * 9,
             "correction": {"action": "confirm", "field": "phase", "reviewer": "r"}},
            "INVALID_HISTORY",
        ),
        ("evaluate", {}, "INVALID_INPUT"),
        ("evaluate", {"dataset": "missing"}, "INVALID_INPUT"),
        ("evaluate", {"dataset": "synthetic_v1", "examples": []}, "INVALID_INPUT"),
    ],
)
def test_invalid_input_returns_error_envelope(operation, payload, code) -> None:
    envelope = assert_envelope(run_operation(operation, payload), "error")
    assert envelope["error"]["code"] == code
    assert envelope["data"] is None
    assert envelope["provenance"] == []


def test_history_for_a_different_document_version_is_rejected() -> None:
    history = _extract()["data"]["history"]
    envelope = assert_envelope(
        run_operation("export", {"text": TEXT.replace("64", "65"), "history": history}), "error"
    )
    assert envelope["error"]["code"] == "DOCUMENT_VERSION_MISMATCH"


@pytest.mark.parametrize("name", ["summarize", "Bad Op!", "", "x" * 300])
def test_unknown_operation(name) -> None:
    envelope = assert_envelope(run_operation(name, {}), "error")
    assert envelope["error"]["code"] == "UNKNOWN_OPERATION"
    assert "extract" in envelope["error"]["details"]["available"]


def test_invalid_run_id_is_reported_without_breaking_the_envelope() -> None:
    envelope = assert_envelope(run_operation("extract", {"text": TEXT}, run_id=""), "error")
    assert envelope["error"]["code"] == "INVALID_INPUT"
    assert envelope["correlation_id"] == envelope["run_id"]


def test_correlation_defaults_to_run_id() -> None:
    envelope = run_operation("extract", {"text": TEXT}, run_id="abc")
    assert envelope["correlation_id"] == "abc"

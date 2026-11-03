import json

import pytest

from clinical_intel.evaluation import (
    Counts,
    Example,
    evaluate,
    load_bundled,
    load_examples,
    main,
)
from clinical_intel.extract import FIELDS


def _gold(**values):
    return {field: values.get(field) for field in FIELDS}


def test_counts_follow_the_documented_definitions() -> None:
    counts = Counts()
    counts.add("A", "A")  # TP
    counts.add("A", "B")  # FP + FN
    counts.add("A", None)  # FN
    counts.add(None, "B")  # FP
    counts.add(None, None)  # TN
    summary = counts.summary()
    assert (summary["tp"], summary["fp"], summary["fn"], summary["tn"]) == (1, 2, 2, 1)
    assert summary["pairs"] == 5
    assert summary["precision"] == pytest.approx(1 / 3, abs=1e-6)
    assert summary["recall"] == pytest.approx(1 / 3, abs=1e-6)
    assert summary["f1"] == pytest.approx(1 / 3, abs=1e-6)
    assert summary["exact_match"] == pytest.approx(2 / 5)


def test_undefined_ratios_are_none_not_zero() -> None:
    summary = Counts(tn=3, mismatched=0).summary()
    assert summary["precision"] is None
    assert summary["recall"] is None
    assert summary["f1"] is None
    assert summary["exact_match"] == 1.0


def test_evaluate_with_fixed_predictor() -> None:
    examples = [
        Example("a", "", _gold(study_id="A", phase="2")),
        Example("b", "", _gold(study_id="B")),
    ]
    predictions = {
        "a": {"study_id": "A", "phase": "3"},
        "b": {"study_id": "B"},
    }
    texts = iter(["a", "b"])
    report = evaluate(examples, predictor=lambda _text: predictions[next(texts)])
    assert report["documents"] == 2
    assert report["document_exact_match"] == 0.5
    assert report["per_field"]["study_id"]["tp"] == 2
    phase = report["per_field"]["phase"]
    assert (phase["tp"], phase["fp"], phase["fn"], phase["tn"]) == (0, 1, 1, 1)
    assert report["micro"]["pairs"] == 2 * len(FIELDS)
    assert report["mismatches"] == [
        {"example": "a", "field": "phase", "gold": "2", "predicted": "3"}
    ]


def test_bundled_dataset_is_well_formed_and_labels_every_field() -> None:
    dataset = load_bundled("synthetic_v1")
    examples = load_examples(dataset["examples"])
    assert len(examples) >= 10
    for example in examples:
        assert set(example.gold) == set(FIELDS)


def test_rule_based_results_on_bundled_dataset_are_reproducible() -> None:
    report = evaluate(load_examples(load_bundled("synthetic_v1")["examples"]))
    # Known limitations of the labeled-line extractor are encoded in the dataset:
    missed = {(m["example"], m["field"]) for m in report["mismatches"]}
    assert ("syn-010-prose", "study_id") in missed
    assert ("syn-011-markdown-bold-labels", "phase") in missed
    assert ("syn-009-generic-study-label", "study_id") in missed
    for example_id in ("syn-003-crlf", "syn-004-lone-cr", "syn-005-unicode",
                       "syn-006-trailing-whitespace", "syn-008-not-exact-count"):
        assert not any(m["example"] == example_id for m in report["mismatches"])
    assert report == evaluate(load_examples(load_bundled("synthetic_v1")["examples"]))


@pytest.mark.parametrize(
    "examples",
    [
        [],
        [{"id": "x", "text": "t", "gold": {"study_id": "X"}}],
        [{"id": "x", "text": "t", "gold": _gold(phase="9")}],
        [{"id": "x", "text": 1, "gold": _gold()}],
        [{"id": "x", "text": "t", "gold": _gold()}, {"id": "x", "text": "u", "gold": _gold()}],
    ],
)
def test_invalid_examples_are_rejected(examples) -> None:
    with pytest.raises((TypeError, ValueError)):
        load_examples(examples)


def test_unknown_bundled_dataset_is_rejected() -> None:
    with pytest.raises(ValueError):
        load_bundled("../secrets")


def test_cli_prints_json_report(capsys) -> None:
    assert main([]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["dataset"] == "synthetic_v1"
    assert report["documents"] == len(load_bundled("synthetic_v1")["examples"])

"""Field-level evaluation of extraction against hand-labelled synthetic examples.

Definitions, per (document, field) pair, comparing predicted ``p`` to gold ``g``
with exact equality of normalized values (phase "1"-"4", participants as int,
strings verbatim):

* true positive  - ``g`` is not null and ``p == g``
* false positive - ``p`` is not null and ``p != g``
* false negative - ``g`` is not null and ``p != g`` (a wrong value counts as both
  a false positive and a false negative)
* true negative  - both null

precision = TP / (TP + FP), recall = TP / (TP + FN) (``None`` when undefined),
field exact match = (TP + TN) / pairs, document exact match = share of documents
whose every field matches.

Usage: ``python -m clinical_intel.evaluation [dataset.json]`` (defaults to the
bundled ``synthetic_v1`` set).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from importlib import resources
from typing import Any

from clinical_intel.document import SourceDocument
from clinical_intel.evidence import extract_document
from clinical_intel.extract import FIELDS
from clinical_intel.schema import validate_field

BUNDLED_DATASETS = ("synthetic_v1",)
MAX_EXAMPLES = 1_000


@dataclass(frozen=True, slots=True)
class Example:
    id: str
    text: str
    gold: dict[str, object]


@dataclass(slots=True)
class Counts:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0
    mismatched: int = 0

    def add(self, gold: object, predicted: object) -> None:
        if predicted == gold:
            if gold is None:
                self.tn += 1
            else:
                self.tp += 1
            return
        self.mismatched += 1
        if predicted is not None:
            self.fp += 1
        if gold is not None:
            self.fn += 1

    def summary(self) -> dict[str, object]:
        pairs = self.tp + self.tn + self.mismatched
        return {
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "tn": self.tn,
            "precision": _ratio(self.tp, self.tp + self.fp),
            "recall": _ratio(self.tp, self.tp + self.fn),
            "f1": _f1(self.tp, self.fp, self.fn),
            "exact_match": _ratio(self.tp + self.tn, pairs),
            "pairs": pairs,
        }


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _f1(tp: int, fp: int, fn: int) -> float | None:
    denominator = 2 * tp + fp + fn
    return round(2 * tp / denominator, 6) if denominator else None


def _validate_example(raw: object, index: int) -> Example:
    if not isinstance(raw, Mapping):
        raise TypeError(f"example {index} must be an object")
    example_id, text, gold = raw.get("id"), raw.get("text"), raw.get("gold")
    if not isinstance(example_id, str) or not example_id:
        raise ValueError(f"example {index}: id must be a non-empty string")
    if not isinstance(text, str):
        raise TypeError(f"example {example_id}: text must be a string")
    if not isinstance(gold, Mapping) or set(gold) != set(FIELDS):
        raise ValueError(f"example {example_id}: gold must label every field exactly once")
    for field in FIELDS:
        errors = validate_field(field, gold[field])
        if errors:
            raise ValueError(f"example {example_id}: invalid gold value: {'; '.join(errors)}")
    return Example(example_id, text, dict(gold))


def load_examples(raw_examples: object) -> list[Example]:
    if not isinstance(raw_examples, list) or not raw_examples:
        raise ValueError("examples must be a non-empty list")
    if len(raw_examples) > MAX_EXAMPLES:
        raise ValueError(f"at most {MAX_EXAMPLES} examples are supported")
    examples = [_validate_example(item, index) for index, item in enumerate(raw_examples)]
    ids = [example.id for example in examples]
    if len(set(ids)) != len(ids):
        raise ValueError("example ids must be unique")
    return examples


def load_bundled(name: str) -> dict[str, Any]:
    if name not in BUNDLED_DATASETS:
        raise ValueError(f"unknown bundled dataset: {name}")
    source = resources.files("clinical_intel").joinpath("evalsets", f"{name}.json")
    return json.loads(source.read_text(encoding="utf-8"))


def rule_based_predictor(text: str) -> dict[str, object]:
    extraction = extract_document(SourceDocument.from_text(text))
    return {item.field: item.value for item in extraction.fields}


def evaluate(
    examples: Iterable[Example],
    predictor: Callable[[str], Mapping[str, object]] = rule_based_predictor,
) -> dict[str, Any]:
    per_field = {field: Counts() for field in FIELDS}
    overall = Counts()
    documents = 0
    documents_exact = 0
    mismatches: list[dict[str, object]] = []
    for example in examples:
        predicted = predictor(example.text)
        documents += 1
        all_match = True
        for field in FIELDS:
            gold, guess = example.gold[field], predicted.get(field)
            for counts in (per_field[field], overall):
                counts.add(gold, guess)
            if guess != gold:
                all_match = False
                mismatches.append(
                    {"example": example.id, "field": field, "gold": gold, "predicted": guess}
                )
        documents_exact += all_match
    return {
        "documents": documents,
        "document_exact_match": _ratio(documents_exact, documents),
        "micro": overall.summary(),
        "per_field": {field: counts.summary() for field, counts in per_field.items()},
        "mismatches": mismatches,
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args:
        with open(args[0], encoding="utf-8") as handle:
            dataset = json.load(handle)
    else:
        dataset = load_bundled("synthetic_v1")
    report = evaluate(load_examples(dataset["examples"]))
    report["dataset"] = dataset.get("dataset")
    report["predictor"] = "rule_based:labeled-lines.v1"
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

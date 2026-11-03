# Clinical Document Intelligence

**A MAK'MA Studio Product · MAK'MA Labs**

[Live Product Demo](https://maharshimak.github.io/makma-ai-os/projects/clinical-document-intelligence/) · [MAK'MA Labs](https://maharshimak.github.io/makma-ai-os/projects/)

Evidence-grounded clinical document extraction with a deterministic baseline, optional model-backed structured extraction, human review provenance and an optional Docling document-understanding pipeline.


## Product contract — engineering upgrade

**Problem and audience:** A human-review workspace for document engineers extracting study metadata with traceable source evidence.

**Live tool:** https://maharshimak.github.io/makma-ai-os/projects/clinical-document-intelligence/

**Implemented browser workflow:** Labeled metadata extraction, source highlights and offsets, normalized record, completeness/schema/evidence coverage, validation gate, original-versus-human-corrected values and JSON export. Corrections never inherit extracted evidence.

**Backend and parity contract:** Python extraction and provenance now consume whole labeled lines; blank fields cannot capture the next line and fractional participant counts cannot be truncated. Python rejects malformed counts; the browser preserves their text and displays a validation error to support correction. Browser offsets are UTF-16 code units; Python offsets are Unicode code points.

**Architecture:** `makma-ai-os/demo` is the shared web product source and Pages deployment. This repository owns its Python domain package. The central `tests/e2e` suite exercises all nine products; `tests/fixtures/python-parity.json` plus `scripts/generate_parity.py` guard shared mathematical contracts. Backend revisions used for regeneration are pinned in the central `backend-lock.json`.

**Safety and limitations:** Synthetic document engineering demonstration. Not medical advice and not a clinical decision system. The lightweight baseline ingests bounded UTF-8 text/Markdown and text-bearing PDFs and applies deterministic evidence-backed extraction. An optional OpenAI-compatible extractor can handle unstructured prose but every non-null field must be anchored to a verbatim source span. An optional Docling pipeline can provide richer layout/OCR-aware ingestion when the `document-ai` extra is installed. No extraction result should be treated as a diagnosis or medical recommendation.

**Verification:** Run `python -m ruff check .` and `python -m pytest -q`. `tests/test_engineering_upgrade.py` protects the new rejection/correctness paths. Central web checks: `npm ci`, `npm test`, `npm run build`, `npx playwright install --with-deps chromium`, `npm run test:e2e`. CI gates publishing on browser interactions and validates all public URLs after deployment.

**Highest-value next work:** Independently adjudicated extraction-quality datasets.

**Provenance:** Independent MAK’MA Studio engineering implementation; examples are synthetic and no employer code or data is included. Existing MIT license applies.


## Implemented now

- Extract study/protocol ID, phase, participant/enrollment count, intervention/treatment, primary endpoint/outcome, secondary endpoint/outcome, sponsor, condition/disease and study type/design from labeled lines (a label must start a line; LF, CRLF and lone-CR line endings are recognised).
- Normalize Roman-numeral phases I–IV to 1–4. Participant counts must be plain ASCII digits or digits grouped in threes (`1,250`); `1,2,5,0`, decimals and trailing text are rejected.
- Field-level evidence (`clinical_intel.evidence`): every non-null field produced by an extractor carries an evidence span `[start, end)` checked with `source[start:end] == evidence.text`. A non-null field without evidence is only allowed when its origin is `human`. Unparseable values and repeated labels with different values are reported as issues instead of aborting the document.
- Document versions (`clinical_intel.document.SourceDocument`): the text is bound to the SHA-256 of its UTF-8 encoding. Evidence, review history and exports name that hash, and history for a different version is rejected. Text is never normalized (NFC and NFD forms are different versions).
- Per-field schema validation (`clinical_intel.schema`, `study-metadata.v1`): type, allowed phases, positive counts, identifier pattern, length and control-character checks. Corrections must pass it.
- Explicit confidence origin: `not_estimated` (the rule-based extractor produces no score, so none is invented), `model_self_reported` (uncalibrated) or `human_asserted`.
- Append-only review history (`clinical_intel.review_log.ReviewLog`): extraction, correction and confirmation events, each hash-chained to the previous one. A correction never inherits the replaced prediction's citation: it either cites a reviewer-supplied span that is verified against the document and literally supports the new value, or it has no evidence and `origin="human"`.
- Structured JSON export (`clinical_intel.export.export_review`) with current values, evidence (code point and UTF-16 offsets), review status, validation errors, open issues and full history.
- Field-level evaluation (`clinical_intel.evaluation`) with tested precision/recall/F1/exact-match code and a small bundled synthetic set (`synthetic_v1`, 12 documents).
- Ingest bounded `.txt`, `.md` (strict UTF-8, leading BOM removed, no newline translation) and text-bearing `.pdf` documents before extraction.
- Optional OpenAI-compatible model extraction for unstructured prose, with fail-closed verbatim evidence anchoring. `evidence.from_model_result` re-verifies its offsets against the exact source before they enter review.
- Optional Docling ingestion for richer document structure/OCR workflows when installed via `pip install -e ".[document-ai]"`.

## Offsets

Python offsets are Unicode code point indices into `SourceDocument.text`. Exports also include `utf16_start`/`utf16_end` for JavaScript consumers (an astral character such as an emoji is one code point but two UTF-16 units). Combining marks are separate code points. Tests cover NFC/NFD text, combining marks, astral characters, CRLF and lone CR, plus a seeded randomized check that every non-null field reproduces its evidence.

## `makma.v1` operations

`clinical_intel.contracts` implements the shared MAK'MA execution envelope (`contracts/makma.v1.schema.json`). Pydantic is not a dependency of this package, so the envelope is a frozen dataclass with explicit validation; tests validate real outputs against the JSON Schema. Entry points: `capabilities()` and `run_operation(operation, payload, *, run_id=None, correlation_id=None)`.

| Operation | Input | `data` |
| --- | --- | --- |
| `extract` | `text` | Export of the rule-based extraction: document hash, fields with evidence, issues, review reasons and the initial `history`. |
| `apply_correction` | `text`, optional `history`, `correction` {`field`, `reviewer`, `action`: `correct` (with `value`, `reason`, optional `evidence_span`) or `confirm`} | Export after appending the event; `history` is the new append-only log. |
| `export` | `text`, optional `history`, optional `include_history` | Export of the current state. |
| `evaluate` | `dataset` (`synthetic_v1`) or inline `examples` | Per-field and micro counts, precision, recall, F1, exact match and mismatches. |

All operations are pure and offline; `execution_mode` is always `deterministic_offline`. Errors use `INVALID_INPUT`, `UNKNOWN_OPERATION`, `DOCUMENT_VERSION_MISMATCH`, `INVALID_HISTORY` and `EVIDENCE_MISMATCH`. Provenance lists the document (`sha256` of its UTF-8 text) and one `chunk` per cited field (span plus `sha256` of the evidence text); `evaluate` lists the dataset with the SHA-256 of its canonical JSON. The package has no HTTP layer, so there are no `/v1` routes.

## Measured evaluation

Command: `python -m clinical_intel.evaluation` (Windows 11, Python 3.12.10). Rule-based extractor on the bundled `synthetic_v1` set (12 documents x 9 fields = 108 pairs):

| Metric | Value |
| --- | --- |
| Micro precision | 0.98 (TP 49, FP 1) |
| Micro recall | 0.844828 (FN 9) |
| Field exact match | 0.916667 |
| Document exact match | 0.75 (9 of 12) |

The misses are deliberate limitation cases in the set: unlabelled prose (5 fields), Markdown bold labels (3 fields) and a generic `Study:` title line read as the study ID (1 false positive and 1 false negative; the repeated label is also flagged as a `CONFLICTING_VALUES` issue). The set is small, synthetic and hand-labelled by its author; these numbers describe this set only and say nothing about real documents.

## Scope and limitations

The deterministic baseline only reads labeled lines; unstructured prose is not interpreted. The hash chain in review history detects edits to serialized history but is not a signature and does not authenticate reviewers; `recorded_at` is caller-supplied. Unicode line separators (U+2028, U+0085) are not treated as line breaks. Model-backed extraction and Docling ingestion are optional adapters; model confidence is never calibrated here. Validation checks value shape, not clinical correctness. No real patient or employer documents are included. This is not a clinical decision tool.

## Installation and development

Requires Python 3.12 or newer. Run from this project directory.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m ruff check .
python -m pytest -q
python -m pip wheel --no-deps . -w dist
```

On Windows, activate with `.venv\Scripts\Activate.ps1`.

## Library usage

```python
from dataclasses import asdict
from clinical_intel.extract import extract, validate
text = "Study ID: SYN-101\nPhase: III\nParticipants: 120\nIntervention: Example compound"
record = extract(text)
print(asdict(record))
print(validate(record))
```

Evidence-bound extraction, a correction and an export:

```python
from clinical_intel.document import SourceDocument
from clinical_intel.evidence import extract_document
from clinical_intel.export import export_review
from clinical_intel.review_log import ReviewLog

document = SourceDocument.from_text("Study ID: SYN-101\nPhase: III\nParticipants: 120\n")
extraction = extract_document(document)
log = ReviewLog.from_extraction(extraction)
log = log.correct(document, "participants", 210, reviewer="reviewer-1", reason="typo")
print(export_review(document, log, issues=extraction.issues)["fields"][2])
```

## Configuration

Configuration is supplied through Python function/constructor arguments. No credentials or environment file are needed for the offline example.

## Container

```bash
docker build -t clinical-document-intelligence .
docker run --rm clinical-document-intelligence
```

## Repository structure

| Path | Purpose |
| --- | --- |
| `src/clinical_intel/` | Implementation |
| `tests/` | Offline unit and regression tests |
| `contracts/makma.v1.schema.json` | Shared execution-envelope schema (identical across MAK'MA repositories) |
| `src/clinical_intel/evalsets/` | Bundled synthetic evaluation set |
| `docs/DESIGN.md` | Architecture and trust boundaries |
| `.github/workflows/ci.yml` | Install, lint, tests, wheel and container build |
| `pyproject.toml` | Dependencies and package configuration |

## Next engineering work

A larger, independently adjudicated synthetic evaluation set; reviewer authentication if review history crosses trust boundaries; OCR as an explicit optional adapter. These are planned work, not current capabilities.

## Contributing and security

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md). CI runs on every push and pull request through `.github/workflows/ci.yml`.

## License and provenance

[MIT](LICENSE), copyright 2026 Maharshi Patel. This public portfolio implementation is independent of employer systems and contains no confidential employer code or data. Examples and test fixtures are synthetic.

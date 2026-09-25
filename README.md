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

**Highest-value next work:** Versioned review records, document ingestion and adjudicated extraction-quality datasets.

**Provenance:** Independent MAK’MA Studio engineering implementation; examples are synthetic and no employer code or data is included. Existing MIT license applies.


## Implemented now

- Extract study/protocol ID, phase, participant/enrollment count, intervention/treatment, primary endpoint/outcome, secondary endpoint/outcome, sponsor, condition/disease and study type/design.
- Normalize Roman-numeral phases I–IV to 1–4.
- Validate study identifier presence, positive participant counts and supported phases.
- Preserve source evidence spans and normalized values for every recognized extracted field.
- Ingest bounded `.txt`, `.md`, and text-bearing `.pdf` documents before extraction.
- Optional OpenAI-compatible model extraction for unstructured prose, with fail-closed verbatim evidence anchoring for every extracted field.
- Optional Docling ingestion for richer document structure/OCR workflows when installed via `pip install -e ".[document-ai]"`.

## Scope and limitations

The deterministic regex baseline still expects labeled fields in plain text. Model-backed extraction and Docling ingestion are optional adapters, not required dependencies; calibrated confidence scoring and clinical interpretation are still out of scope. Evidence spans are preserved for recognized fields, including common aliases, but unstructured prose is not semantically interpreted. Validation is deliberately narrow; missing fields other than study ID can remain null. No real patient or employer documents are included. This is not a clinical decision tool.

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
| `docs/DESIGN.md` | Architecture and trust boundaries |
| `.github/workflows/ci.yml` | Install, lint, tests, wheel and container build |
| `pyproject.toml` | Dependencies and package configuration |

## Next engineering work

Richer synthetic fixtures, versioned review records, extraction-quality evaluation, OCR as an explicit optional adapter, and an optional structured model adapter with evidence mapping and human review. These are planned work, not current capabilities.

## Contributing and security

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md). CI runs on every push and pull request through `.github/workflows/ci.yml`.

## License and provenance

[MIT](LICENSE), copyright 2026 Maharshi Patel. This public portfolio implementation is independent of employer systems and contains no confidential employer code or data. Examples and test fixtures are synthetic.

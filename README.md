# Clinical Document Intelligence

Rule-based extraction and validation of structured study fields from synthetic clinical-style text.

## Implemented now

- Extract study ID, phase, participant count, intervention and primary endpoint.
- Normalize Roman-numeral phases I–IV to 1–4.
- Validate study identifier presence, positive participant counts and supported phases.

## Scope and limitations

Regex rules expect labeled fields in plain text. There is no OCR, model-based NLP, confidence scoring, evidence-span extraction or clinical interpretation. Validation is deliberately narrow; missing fields other than study ID can remain null. No real patient or employer documents are included. This is not a clinical decision tool.

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

Evidence offsets; richer synthetic fixtures; schema validation; extraction evaluation; optional model adapter with human review. These are planned work, not current capabilities.

## Contributing and security

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md). The standalone CI workflow runs after migration; while nested in the profile repository, the parent CI validates this project.

## License and provenance

[MIT](LICENSE), copyright 2026 Maharshi Patel. This public portfolio implementation is independent of employer systems and contains no confidential employer code or data. Examples and test fixtures are synthetic.

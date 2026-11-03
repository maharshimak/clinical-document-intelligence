# Design and operating boundaries

Rule-based extraction and validation of structured study fields from synthetic clinical-style text.

## Scope

Regex rules expect labeled fields in plain text. Every non-null machine-extracted field carries an evidence span verified against the exact document text, which is bound to its SHA-256. Human corrections go into an append-only, hash-chained history and never inherit the replaced prediction's citation. The rule-based path produces no confidence score. Model extraction and Docling ingestion are optional adapters; there is no built-in OCR and no clinical interpretation. Validation is deliberately narrow; missing fields other than study ID can remain null. No real patient or employer documents are included. This is not a clinical decision tool.

## Interfaces

Implementation lives in `src/clinical_intel/`. Public examples in the README use its Python API. This project is a library, without a service layer. `clinical_intel.contracts` exposes `extract`, `apply_correction`, `export` and `evaluate` through the shared `makma.v1` envelope for in-process callers.

## Validation

Tests include synthetic regression fixtures. Package and container checks verify installation separately from source-tree imports. Tests do not certify general model quality, clinical correctness or multi-tenant isolation.

## Planned evolution

Larger, independently adjudicated synthetic evaluation sets; reviewer authentication if review history crosses trust boundaries.

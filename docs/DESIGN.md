# Design and operating boundaries

Rule-based extraction and validation of structured study fields from synthetic clinical-style text.

## Scope

Regex rules expect labeled fields in plain text. There is no OCR, model-based NLP, confidence scoring, evidence-span extraction or clinical interpretation. Validation is deliberately narrow; missing fields other than study ID can remain null. No real patient or employer documents are included. This is not a clinical decision tool.

## Interfaces

Implementation lives in `src/clinical_intel/`. Public examples in the README use its Python API. This project is a library, without a service layer.

## Validation

Tests include synthetic regression fixtures. Package and container checks verify installation separately from source-tree imports. Tests do not certify general model quality, clinical correctness or multi-tenant isolation.

## Planned evolution

Evidence offsets; richer synthetic fixtures; schema validation; extraction evaluation; optional model adapter with human review.

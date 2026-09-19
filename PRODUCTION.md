# Production engineering

Clinical document extraction now has an explicit quality layer in `clinical_intel.quality`.

`assess_extraction` separates structural completeness from domain validation, records missing fields, carries validation errors, and produces a deterministic fingerprint for the normalized record. This supports traceable comparisons across extractor versions without claiming medical-grade validation.

## Operational practice

- Keep source-document provenance outside the normalized record and link it by a stable document ID.
- Set completeness thresholds by document type.
- Route validation failures for review rather than silently coercing values.
- Never treat this example pipeline as clinical decision support without independent validation, governance and regulatory review.

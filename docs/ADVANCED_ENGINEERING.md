# Advanced engineering: extraction provenance

`clinical_intel.provenance` makes rule-based extraction auditable.

Alongside the normalized `StudyRecord`, it returns the exact raw value and character span that
supported each extracted field. Phase values demonstrate why both forms matter: raw `II` can be
retained as evidence while the normalized record stores `2`.

Two coverage measures are exposed: evidence coverage across non-null extracted fields, and schema
coverage across the five supported fields. This enables downstream review queues to distinguish
"field missing" from "field extracted without traceable evidence".

from clinical_intel.provenance import extract_with_provenance


def test_expanded_schema_supports_common_trial_labels_with_evidence() -> None:
    text = (
        "Protocol ID: P-2026-17\n"
        "Phase: III\n"
        "Enrollment: 1,250\n"
        "Treatment: Therapy X\n"
        "Primary outcome: Overall survival\n"
        "Secondary outcome: Progression-free survival\n"
        "Sponsor: Example Research Foundation\n"
        "Condition: Example disease\n"
        "Study design: Randomized controlled trial\n"
    )

    result = extract_with_provenance(text)

    assert result.record.study_id == "P-2026-17"
    assert result.record.participants == 1250
    assert result.record.sponsor == "Example Research Foundation"
    assert result.record.secondary_endpoint == "Progression-free survival"
    assert result.evidence_coverage == 1.0
    assert result.extended_schema_coverage == 1.0
    assert {item.field for item in result.evidence} == {
        "study_id",
        "phase",
        "participants",
        "intervention",
        "primary_endpoint",
        "secondary_endpoint",
        "sponsor",
        "condition",
        "study_type",
    }

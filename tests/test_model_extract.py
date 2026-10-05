import pytest

from clinical_intel.model_extract import OpenAICompatibleClinicalExtractor


def extractor():
    return OpenAICompatibleClinicalExtractor(
        base_url="http://localhost",
        model="clinical-model",
    )


def test_model_extraction_anchors_every_non_null_field():
    source = "Protocol ABC-1 is a Phase III study with 180 participants."
    result = extractor().parse(
        source,
        """
        {
          "fields": {
            "study_id": {"value":"ABC-1","evidence":"ABC-1"},
            "phase": {"value":"III","evidence":"Phase III"},
            "participants": {"value":180,"evidence":"180 participants"}
          }
        }
        """,
    )
    assert result.record.study_id == "ABC-1"
    assert result.record.phase == "3"
    assert result.record.participants == 180
    assert result.grounded_fields == 3


def test_model_extraction_rejects_unanchored_claims():
    with pytest.raises(ValueError, match="not present"):
        extractor().parse(
            "Protocol ABC-1.",
            """
            {
              "fields": {
                "study_id": {"value":"ABC-1","evidence":"ABC-1"},
                "phase": {"value":"III","evidence":"Phase III"}
              }
            }
            """,
        )


def test_model_extraction_requires_value_to_be_inside_endpoint_evidence():
    with pytest.raises(ValueError, match="primary_endpoint value is not supported"):
        extractor().parse(
            "Primary endpoint: Overall survival at 12 months.",
            """
            {
              "fields": {
                "primary_endpoint": {
                  "value":"Progression-free survival",
                  "evidence":"Primary endpoint: Overall survival at 12 months."
                }
              }
            }
            """,
        )


def test_model_extraction_surfaces_review_state_for_missing_critical_fields():
    source = "Protocol ABC-1 is a Phase III study with 180 participants."
    result = extractor().parse(
        source,
        """
        {
          "fields": {
            "study_id": {"value":"ABC-1","evidence":"ABC-1"},
            "phase": {"value":"III","evidence":"Phase III"},
            "participants": {"value":180,"evidence":"180 participants"}
          }
        }
        """,
    )

    assert result.evidence_coverage == 1.0
    assert result.requires_review is True
    assert "critical field missing: primary_endpoint" in result.review_reasons

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

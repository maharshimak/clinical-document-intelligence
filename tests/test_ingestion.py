from clinical_intel.ingest import ingest_document


def test_ingest_text_document_with_provenance(tmp_path) -> None:
    path = tmp_path / "study.txt"
    path.write_text(
        "Study ID: SYN-900\nPhase: II\nParticipants: 42\n"
        "Intervention: Example compound\nPrimary Endpoint: Synthetic outcome\n",
        encoding="utf-8",
    )

    document = ingest_document(path)

    assert document.media_type == "text/plain"
    assert document.extraction.record.study_id == "SYN-900"
    assert document.extraction.record.participants == 42
    assert document.extraction.evidence_coverage == 1.0

"""Confirmed defects in span offsets/ingestion and Unicode offset invariants."""

import random
import unicodedata

import pytest

from clinical_intel.document import (
    DocumentVersionError,
    SourceDocument,
    text_sha256,
    utf16_offset,
)
from clinical_intel.evidence import extract_document
from clinical_intel.extract import FIELDS, extract, find_labeled_value
from clinical_intel.ingest import ingest_document
from clinical_intel.provenance import extract_with_provenance

# -- confirmed defects (each failed on main before this change) ---------------------------


def test_provenance_span_excludes_surrounding_whitespace() -> None:
    # main: span covered "X-1   " and "10\t" while raw_value was "X-1" / "10".
    text = "Study ID: X-1   \nParticipants: 10\t\nIntervention: Drug A \n"
    result = extract_with_provenance(text)
    assert {item.field for item in result.evidence} == {"study_id", "participants", "intervention"}
    for item in result.evidence:
        assert text[item.start : item.end] == item.raw_value


@pytest.mark.parametrize("value", ["1,2,5,0", "12,34", "1,2345", ",120", "120,"])
def test_participants_reject_misplaced_thousands_separators(value: str) -> None:
    # main: "1,2,5,0" was silently read as 1250.
    with pytest.raises(ValueError, match="participants"):
        extract("Study ID: X\nParticipants: " + value)


@pytest.mark.parametrize("value,expected", [("1,250", 1250), ("120", 120), ("12,345,678", 12345678)])
def test_participants_accept_well_formed_counts(value: str, expected: int) -> None:
    assert extract("Participants: " + value).participants == expected


def test_participants_reject_non_ascii_digits() -> None:
    with pytest.raises(ValueError):
        extract("Participants: １２０")  # fullwidth "120"


def test_ingest_utf8_bom_does_not_hide_first_field(tmp_path) -> None:
    # main: the BOM preceded "Study ID" so the first-line label was never matched.
    path = tmp_path / "bom.txt"
    data = "﻿Study ID: BOM-1\nPhase: 2\n".encode()
    path.write_bytes(data)
    document = ingest_document(path)
    assert document.extraction.record.study_id == "BOM-1"
    assert document.document is not None
    assert document.document.source_sha256 == __import__("hashlib").sha256(data).hexdigest()
    assert document.document.sha256 == text_sha256(document.text)


def test_ingest_preserves_crlf_so_offsets_match_hashed_text(tmp_path) -> None:
    path = tmp_path / "crlf.txt"
    data = b"Study ID: CR-1\r\nPhase: III\r\nParticipants: 7\r\n"
    path.write_bytes(data)
    document = ingest_document(path)
    assert document.text == data.decode()
    assert document.document.sha256 == document.document.source_sha256
    for item in document.extraction.evidence:
        assert document.text[item.start : item.end] == item.raw_value
    assert document.extraction.record.phase == "3"


def test_lone_cr_line_endings_are_line_breaks() -> None:
    # main: only the first line was recognised in-memory for "\r" separated text.
    record = extract("Study ID: A-1\rPhase: 2\rParticipants: 5")
    assert (record.study_id, record.phase, record.participants) == ("A-1", "2", 5)


def test_label_must_start_a_line() -> None:
    assert find_labeled_value("phase", "Note Phase: 3") is None
    assert find_labeled_value("phase", "x\nPhase: 3").raw_value == "3"


# -- document versions ---------------------------------------------------------------------


def test_document_hash_binds_exact_text() -> None:
    nfc = unicodedata.normalize("NFC", "Intervention: Café")
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfc != nfd
    assert SourceDocument.from_text(nfc).sha256 != SourceDocument.from_text(nfd).sha256
    with pytest.raises(DocumentVersionError):
        SourceDocument(nfc, SourceDocument.from_text(nfd).sha256)


def test_lone_surrogate_text_is_rejected() -> None:
    with pytest.raises(ValueError, match="surrogate"):
        SourceDocument.from_text("Study ID: \ud800")


def test_invalid_utf8_bytes_are_rejected() -> None:
    with pytest.raises(ValueError, match="UTF-8"):
        SourceDocument.from_utf8_bytes(b"Study ID: \xff")


# -- Unicode offsets -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "prefix",
    [
        "",
        "ßß\n",  # sharp s: changes length under casefold()
        "é́ combining marks\n",
        "\U0001F9EA\U0001F9EA astral\n",
        "İstanbul\r\n",  # dotted capital I: changes length under lower()
        "ﬃ ligature\r",
    ],
)
@pytest.mark.parametrize("form", ["NFC", "NFD"])
def test_evidence_offsets_are_exact_for_any_unicode_prefix(prefix: str, form: str) -> None:
    text = unicodedata.normalize(
        form, prefix + "Study ID: SYN-é\nIntervention: Café \U0001F9EA\n"
    )
    document = SourceDocument.from_text(text)
    extraction = extract_document(document)
    for name in ("study_id", "intervention"):
        item = extraction.field(name)
        assert item.evidence is not None
        assert text[item.evidence.start : item.evidence.end] == item.evidence.text == item.value


def test_utf16_offsets_count_astral_characters_as_two_units() -> None:
    text = "\U0001F9EA\nStudy ID: A\U0001F9EAB\n"
    document = SourceDocument.from_text(text)
    item = extract_document(document).field("study_id")
    exported = item.to_dict(document)["evidence"]
    assert (exported["start"], exported["end"]) == (12, 15)
    assert (exported["utf16_start"], exported["utf16_end"]) == (13, 17)
    assert text.encode("utf-16-le")[26:34].decode("utf-16-le") == item.evidence.text
    with pytest.raises(ValueError):
        utf16_offset(text, len(text) + 1)


_ALPHABET = [
    "a", "Z", "0", "7", " ", "\t", ":", ",", "-", "\n", "\r", "\r\n",
    "é", "é", "ß", "\U0001F9EA", " ", " ", "﻿",
]
_LABELS = ["Study ID", "Phase", "Participants", "Intervention", "Primary endpoint",
           "Sponsor", "Condition", "Design", "Secondary outcome", "Enrollment"]


def _random_document(rng: random.Random) -> str:
    parts: list[str] = []
    for _ in range(rng.randint(0, 12)):
        if rng.random() < 0.5:
            parts.append(rng.choice(["\n", "\r\n", "\r", ""]) + rng.choice(_LABELS) + ":")
        parts.append("".join(rng.choice(_ALPHABET) for _ in range(rng.randint(0, 8))))
    return "".join(parts)


def test_property_every_non_null_field_reproduces_its_evidence() -> None:
    rng = random.Random(20261103)
    checked = 0
    for _ in range(2000):
        text = _random_document(rng)
        document = SourceDocument.from_text(text)
        extraction = extract_document(document)  # must never raise on arbitrary text
        assert tuple(item.field for item in extraction.fields) == FIELDS
        for item in extraction.fields:
            if item.value is None:
                assert item.evidence is None
                continue
            checked += 1
            span = item.evidence
            assert text[span.start : span.end] == span.text
            assert span.text == span.text.strip()
            assert "\n" not in span.text and "\r" not in span.text
    assert checked > 500  # the generator really exercises non-null fields

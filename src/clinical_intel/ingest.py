from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from pypdf import PdfReader

from clinical_intel.document import SourceDocument
from clinical_intel.provenance import ExtractionProvenance, extract_with_provenance


class DocumentIngestionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class IngestedDocument:
    source_path: str
    media_type: str
    text: str
    extraction: ExtractionProvenance
    document: SourceDocument | None = None
    """Versioned text that ``extraction`` offsets refer to (``document.text == text``)."""


def _read_text(path: Path, max_bytes: int) -> SourceDocument:
    size = path.stat().st_size
    if size > max_bytes:
        raise DocumentIngestionError(f"Document exceeds {max_bytes} byte limit.")
    # Decode the exact bytes: no newline translation, so offsets and the document
    # hash describe the same text; a leading UTF-8 BOM is removed (see SourceDocument).
    try:
        return SourceDocument.from_utf8_bytes(path.read_bytes())
    except ValueError as error:
        raise DocumentIngestionError(str(error)) from error


def _read_pdf(path: Path, max_bytes: int, max_pages: int) -> str:
    size = path.stat().st_size
    if size > max_bytes:
        raise DocumentIngestionError(f"Document exceeds {max_bytes} byte limit.")
    reader = PdfReader(str(path))
    if len(reader.pages) > max_pages:
        raise DocumentIngestionError(f"PDF exceeds {max_pages} page limit.")
    pages: list[str] = []
    for page in reader.pages:
        extracted = page.extract_text() or ""
        if extracted.strip():
            pages.append(extracted)
    if not pages:
        raise DocumentIngestionError(
            "PDF contained no extractable text. OCR is not enabled in this project."
        )
    return "\n\n".join(pages)


def ingest_document(
    path: str | Path,
    *,
    max_bytes: int = 10_000_000,
    max_pages: int = 100,
) -> IngestedDocument:
    """Load a bounded text/PDF document and run evidence-backed extraction."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
        raise ValueError("max_bytes must be a positive integer.")
    if isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages <= 0:
        raise ValueError("max_pages must be a positive integer.")

    suffix = source.suffix.casefold()
    if suffix in {".txt", ".md"}:
        document = _read_text(source, max_bytes)
    elif suffix == ".pdf":
        text = _read_pdf(source, max_bytes, max_pages)
        try:
            document = SourceDocument.from_text(
                text,
                media_type="application/pdf",
                source_sha256=sha256(source.read_bytes()).hexdigest(),
            )
        except ValueError as error:
            raise DocumentIngestionError(str(error)) from error
    else:
        raise DocumentIngestionError("Supported document types are .txt, .md and .pdf.")

    return IngestedDocument(
        source_path=str(source),
        media_type=document.media_type,
        text=document.text,
        extraction=extract_with_provenance(document.text),
        document=document,
    )

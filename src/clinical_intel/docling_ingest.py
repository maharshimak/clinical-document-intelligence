from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from clinical_intel.model_extract import (
    ModelExtractionResult,
    OpenAICompatibleClinicalExtractor,
)


class DoclingUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class IntelligentDocument:
    source_path: str
    markdown: str
    extraction: ModelExtractionResult


@dataclass(slots=True)
class DoclingClinicalPipeline:
    """Optional layout/OCR-aware ingestion backed by Docling + model extraction.

    Docling is imported lazily so the lightweight baseline package and CI remain
    dependency-small. Install Docling in deployments that need OCR, tables,
    reading order and richer PDF understanding.
    """

    extractor: OpenAICompatibleClinicalExtractor

    def ingest(self, path: str | Path) -> IntelligentDocument:
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(source)
        try:
            from docling.document_converter import DocumentConverter
        except ImportError as error:
            raise DoclingUnavailableError(
                "Docling is not installed. Install the optional document-understanding "
                "runtime before using DoclingClinicalPipeline."
            ) from error

        result = DocumentConverter().convert(str(source))
        markdown = result.document.export_to_markdown()
        if not markdown.strip():
            raise ValueError("Docling produced no document text.")
        extraction = self.extractor.extract(markdown)
        return IntelligentDocument(
            source_path=str(source),
            markdown=markdown,
            extraction=extraction,
        )

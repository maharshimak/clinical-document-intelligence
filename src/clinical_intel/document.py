"""Versioned source documents.

Evidence offsets are only meaningful against one exact text. A ``SourceDocument``
binds that text to the SHA-256 of its UTF-8 encoding so every span, correction and
export can name the document version it refers to.

Offsets throughout this package are Unicode code point indices into
``SourceDocument.text`` (Python ``str`` indexing). Text is never normalized
(no NFC/NFD folding, no newline translation): a composed ``é`` and a decomposed
``e`` + U+0301 are different documents with different hashes and offsets.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

_BOM = "\ufeff"


class DocumentVersionError(ValueError):
    """Raised when evidence or history is bound to a different document version."""


def text_sha256(text: str) -> str:
    """SHA-256 of the strict UTF-8 encoding of ``text``.

    Raises ``ValueError`` for strings that cannot be encoded (lone surrogates).
    """
    try:
        encoded = text.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError("document text is not valid Unicode (lone surrogate).") from error
    return sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class SourceDocument:
    text: str
    sha256: str
    media_type: str = "text/plain"
    source_sha256: str | None = None
    """SHA-256 of the original file bytes when loaded from bytes (may differ from
    ``sha256`` when a UTF-8 byte-order mark was removed or the source was a PDF)."""

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise TypeError("document text must be a string")
        if text_sha256(self.text) != self.sha256:
            raise DocumentVersionError("sha256 does not match the document text.")

    @classmethod
    def from_text(
        cls,
        text: str,
        *,
        media_type: str = "text/plain",
        source_sha256: str | None = None,
    ) -> SourceDocument:
        if not isinstance(text, str):
            raise TypeError("document text must be a string")
        return cls(text, text_sha256(text), media_type, source_sha256)

    @classmethod
    def from_utf8_bytes(cls, data: bytes, *, media_type: str = "text/plain") -> SourceDocument:
        """Decode strict UTF-8 without newline translation.

        A single leading byte-order mark is removed so a label on the first line is
        recognised; ``source_sha256`` still records the hash of the original bytes.
        """
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("Text document must be UTF-8 encoded.") from error
        if text.startswith(_BOM):
            text = text[1:]
        return cls.from_text(text, media_type=media_type, source_sha256=sha256(data).hexdigest())

    def require_version(self, sha: str) -> None:
        if sha != self.sha256:
            raise DocumentVersionError(
                f"evidence is bound to document {sha[:12]}..., "
                f"not this document {self.sha256[:12]}..."
            )


def utf16_offset(text: str, index: int) -> int:
    """Convert a code point offset to a UTF-16 code unit offset (JavaScript strings)."""
    if not 0 <= index <= len(text):
        raise ValueError("offset outside document")
    return len(text[:index].encode("utf-16-le")) // 2

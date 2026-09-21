from __future__ import annotations

import base64
import binascii
from io import BytesIO
import re

from pypdf import PdfReader


MAX_PDF_BYTES = 2 * 1024 * 1024
MAX_PDF_PAGES = 40
MAX_PDF_TEXT_CHARS = 20_000
_PDF_DATA_URL_PREFIX = "data:application/pdf;base64,"


class PdfContextError(ValueError):
    """Raised when an uploaded PDF cannot be safely ingested as project context."""


def _decode_pdf_data_url(data_url: str, *, max_bytes: int = MAX_PDF_BYTES) -> bytes:
    value = str(data_url or "").strip()
    if not value.lower().startswith(_PDF_DATA_URL_PREFIX):
        raise PdfContextError("PDF attachments must be uploaded as an application/pdf data URL.")

    encoded = value.split(",", 1)[1]
    try:
        payload = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise PdfContextError("The uploaded PDF data is not valid base64.") from exc

    if not payload.startswith(b"%PDF"):
        raise PdfContextError("The uploaded file does not appear to be a valid PDF.")
    if len(payload) > max_bytes:
        raise PdfContextError(
            f"PDF attachments are limited to {max_bytes // (1024 * 1024)} MB for context ingestion."
        )
    return payload


def _normalize_page_text(value: str) -> str:
    text = str(value or "").replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pdf_text_from_data_url(
    data_url: str,
    *,
    max_bytes: int = MAX_PDF_BYTES,
    max_pages: int = MAX_PDF_PAGES,
    max_chars: int = MAX_PDF_TEXT_CHARS,
) -> str:
    """Extract bounded text from a user-uploaded PDF data URL.

    The raw PDF bytes are intentionally transient. Callers should persist only
    the attachment metadata plus the returned text.
    """

    payload = _decode_pdf_data_url(data_url, max_bytes=max_bytes)

    try:
        reader = PdfReader(BytesIO(payload), strict=False)
    except Exception as exc:
        raise PdfContextError("Forma could not read that PDF. Try exporting it again.") from exc

    if reader.is_encrypted:
        try:
            unlocked = reader.decrypt("")
        except Exception as exc:
            raise PdfContextError("Password-protected PDFs are not supported yet.") from exc
        if not unlocked:
            raise PdfContextError("Password-protected PDFs are not supported yet.")

    if len(reader.pages) > max_pages:
        raise PdfContextError(
            f"PDF attachments are limited to {max_pages} pages for context ingestion."
        )

    chunks: list[str] = []
    remaining = max_chars
    truncated = False

    for index, page in enumerate(reader.pages, start=1):
        try:
            page_text = _normalize_page_text(page.extract_text() or "")
        except Exception as exc:
            raise PdfContextError(f"Forma could not extract text from PDF page {index}.") from exc
        if not page_text:
            continue

        chunk = f"[PDF page {index}]\n{page_text}"
        if len(chunk) > remaining:
            if remaining > 0:
                chunks.append(chunk[:remaining].rstrip())
            truncated = True
            break

        chunks.append(chunk)
        remaining -= len(chunk)
        if remaining <= 0:
            truncated = True
            break

    text = "\n\n".join(chunks).strip()
    if not text:
        raise PdfContextError(
            "This PDF has no extractable text. Scanned/image-only PDFs need OCR before Forma can ingest them."
        )

    if truncated:
        text = f"{text}\n\n[PDF text truncated to {max_chars} characters.]"
    return text

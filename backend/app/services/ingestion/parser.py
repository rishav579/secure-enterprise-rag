from pathlib import Path
from typing import List, NamedTuple, Optional

import pypdf
import pypdf.errors

from backend.app.services.ingestion.exceptions import (
    EmptyPDFError,
    EncryptedPDFError,
    InvalidPDFError,
    PDFPageLimitExceededError,
)

PDF_MAGIC_BYTES = b"%PDF-"


class ExtractedPage(NamedTuple):
    page_number: int  # 1-indexed
    text: str


class PDFParseResult(NamedTuple):
    pages: List[ExtractedPage]
    total_pages: int
    total_chars: int


class SafePDFParser:
    """Safe page-by-page PDF parser.
    
    Security Boundary Note:
    We do NOT treat '%PDF-' magic-byte validation as standalone proof of safety.
    The complete security boundary consists of:
    1. Declared MIME validation ('application/pdf')
    2. Magic-byte verification ('%PDF-')
    3. Strict size and page count resource ceilings
    4. Isolated parsing with pypdf (plain text extraction only, no execution of embedded JavaScript/actions).
    """

    def __init__(self, max_pages: int = 100) -> None:
        self.max_pages = max_pages

    @staticmethod
    def validate_header(
        header_bytes: bytes,
        declared_content_type: Optional[str] = None,
    ) -> None:
        """Validate declared MIME type and leading magic bytes."""
        if declared_content_type and declared_content_type.lower() != "application/pdf":
            raise InvalidPDFError(
                f"Invalid MIME type '{declared_content_type}'. Only 'application/pdf' is accepted."
            )

        if not header_bytes.startswith(PDF_MAGIC_BYTES):
            raise InvalidPDFError("File does not start with PDF magic header '%PDF-'.")

    def parse_file(self, file_path: str | Path) -> PDFParseResult:
        """Parse a local PDF file page by page and extract clean text.
        
        Enforces maximum page limits and handles malformed/corrupt files cleanly.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {file_path}")

        # Quick magic-byte sanity pre-check
        with open(path, "rb") as f:
            header = f.read(8)
        self.validate_header(header)

        try:
            reader = pypdf.PdfReader(str(path))
        except pypdf.errors.PdfReadError as exc:
            raise InvalidPDFError(f"Malformed or corrupt PDF document: {exc}") from exc
        except Exception as exc:
            raise InvalidPDFError(f"Failed to read PDF structure: {exc}") from exc

        if reader.is_encrypted:
            raise EncryptedPDFError("Encrypted or password-protected PDFs are not supported.")

        num_pages = len(reader.pages)
        if num_pages == 0:
            raise EmptyPDFError("PDF contains 0 pages.")

        if num_pages > self.max_pages:
            raise PDFPageLimitExceededError(
                f"PDF exceeds maximum page limit of {self.max_pages} pages ({num_pages} pages detected)."
            )

        pages: List[ExtractedPage] = []
        total_chars = 0

        for idx, page in enumerate(reader.pages):
            page_num = idx + 1
            try:
                raw_text = page.extract_text() or ""
            except Exception as exc:
                raise InvalidPDFError(f"Failed to extract text from page {page_num}: {exc}") from exc

            cleaned_text = raw_text.strip()
            total_chars += len(cleaned_text)
            pages.append(ExtractedPage(page_number=page_num, text=cleaned_text))

        if total_chars == 0:
            raise EmptyPDFError("PDF contains no extractable text.")

        return PDFParseResult(
            pages=pages,
            total_pages=num_pages,
            total_chars=total_chars,
        )

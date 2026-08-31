import io
from pathlib import Path
import pytest
import pypdf

from backend.app.services.ingestion.exceptions import (
    EmptyPDFError,
    InvalidPDFError,
    PDFPageLimitExceededError,
)
from backend.app.services.ingestion.parser import SafePDFParser


def create_test_pdf_bytes(pages_text: list[str]) -> bytes:
    """Create an in-memory valid PDF with given text for each page."""
    writer = pypdf.PdfWriter()
    for text in pages_text:
        # Create a page with standard dimensions (612 x 792) and add annotation / text
        page = writer.add_blank_page(width=612, height=792)
        # Note: blank page in pypdf doesn't have text by default; we can use annotation or direct stream
        # Or write standard minimal PDF with text object:
    buffer = io.BytesIO()
    writer.write(buffer)
    # If we need extractable text from pypdf:
    # A standard raw minimal valid PDF with text stream:
    return buffer.getvalue()


def create_minimal_text_pdf(pages: list[str]) -> bytes:
    """Construct a minimal valid PDF byte string containing extractable text for each page."""
    # Build standard PDF object structure
    objects = []
    # 1: Catalog, 2: Pages
    page_obj_ids = []
    current_id = 3

    page_contents = []
    for text in pages:
        font_id = current_id
        current_id += 1
        stream_id = current_id
        current_id += 1
        page_id = current_id
        current_id += 1
        page_obj_ids.append(page_id)

        # Stream content: BT /F1 12 Tf 50 700 Td (text) Tj ET
        escaped_text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream_data = f"BT /F1 12 Tf 50 700 Td ({escaped_text}) Tj ET".encode("latin-1")

        font_obj = f"{font_id} 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        stream_obj = (
            f"{stream_id} 0 obj\n<< /Length {len(stream_data)} >>\nstream\n"
            + stream_data.decode("latin-1")
            + "\nendstream\nendobj\n"
        )
        page_obj = (
            f"{page_id} 0 obj\n"
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
            f"/Contents {stream_id} 0 R >>\nendobj\n"
        )
        page_contents.extend([font_obj, stream_obj, page_obj])

    kids = " ".join(f"{pid} 0 R" for pid in page_obj_ids)
    pages_obj = f"2 0 obj\n<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>\nendobj\n"
    catalog_obj = "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"

    all_objs = [catalog_obj, pages_obj] + page_contents

    # Assemble PDF with xref table
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = [0]
    for obj_str in all_objs:
        offsets.append(out.tell())
        out.write(obj_str.encode("latin-1"))

    xref_offset = out.tell()
    out.write(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode("latin-1"))
    for off in offsets[1:]:
        out.write(f"{off:010d} 00000 n \n".encode("latin-1"))

    out.write(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode("latin-1")
    )
    return out.getvalue()


def test_pdf_parser_valid_multi_page(tmp_path: Path):
    parser = SafePDFParser()
    pdf_bytes = create_minimal_text_pdf(["Page 1 Enterprise Text", "Page 2 Compliance Text"])
    pdf_path = tmp_path / "valid.pdf"
    pdf_path.write_bytes(pdf_bytes)

    result = parser.parse_file(pdf_path)
    assert result.total_pages == 2
    assert len(result.pages) == 2
    assert result.pages[0].page_number == 1
    assert "Page 1 Enterprise Text" in result.pages[0].text
    assert result.pages[1].page_number == 2
    assert "Page 2 Compliance Text" in result.pages[1].text


def test_pdf_parser_header_validation():
    # Valid header
    SafePDFParser.validate_header(b"%PDF-1.7 ...", "application/pdf")

    # Invalid MIME
    with pytest.raises(InvalidPDFError, match="Invalid MIME type"):
        SafePDFParser.validate_header(b"%PDF-1.7", "application/octet-stream")

    # Invalid magic bytes
    with pytest.raises(InvalidPDFError, match="magic header"):
        SafePDFParser.validate_header(b"NOT_A_PDF_HEADER", "application/pdf")


def test_pdf_parser_corrupt_file(tmp_path: Path):
    parser = SafePDFParser()
    corrupt_path = tmp_path / "corrupt.pdf"
    corrupt_path.write_bytes(b"%PDF-1.4\nCorrupted binary payload content that is not a valid PDF")

    with pytest.raises(InvalidPDFError):
        parser.parse_file(corrupt_path)


def test_pdf_parser_page_limit_exceeded(tmp_path: Path):
    parser = SafePDFParser(max_pages=3)
    pdf_bytes = create_minimal_text_pdf(["P1", "P2", "P3", "P4"])  # 4 pages > 3 max
    pdf_path = tmp_path / "too_many_pages.pdf"
    pdf_path.write_bytes(pdf_bytes)

    with pytest.raises(PDFPageLimitExceededError):
        parser.parse_file(pdf_path)


def test_pdf_parser_empty_text_rejected(tmp_path: Path):
    parser = SafePDFParser()
    # PDF with blank pages (no text)
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=100, height=100)
    buf = io.BytesIO()
    writer.write(buf)

    pdf_path = tmp_path / "blank.pdf"
    pdf_path.write_bytes(buf.getvalue())

    with pytest.raises(EmptyPDFError):
        parser.parse_file(pdf_path)

class IngestionError(Exception):
    """Base exception for all document ingestion and parsing errors."""
    pass


class InvalidPDFError(IngestionError):
    """Raised when uploaded file is not a valid PDF or has invalid magic bytes."""
    pass


class PDFSizeLimitExceededError(IngestionError):
    """Raised when file exceeds the maximum allowed upload size."""
    pass


class PDFPageLimitExceededError(IngestionError):
    """Raised when PDF exceeds the maximum allowed page count."""
    pass


class EncryptedPDFError(IngestionError):
    """Raised when PDF is password protected or encrypted."""
    pass


class EmptyPDFError(IngestionError):
    """Raised when PDF has 0 pages or contains no extractable text."""
    pass


class PathTraversalError(IngestionError):
    """Raised when a client-supplied identifier attempts path traversal."""
    pass

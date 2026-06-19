"""AILIZA Dokumenten-Workflow MVP."""
from .document_handler import (
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE_MB,
    DocumentScanResult,
    scan_document,
)

__all__ = ["ALLOWED_EXTENSIONS", "MAX_FILE_SIZE_MB", "DocumentScanResult", "scan_document"]

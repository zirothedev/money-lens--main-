"""Validation of uploaded statement files (type, size, content signature)."""
import os

from django.conf import settings

from .exceptions import InvalidStatementFile
from .models import StatementProcessing

PDF_MAGIC = b'%PDF-'


def validate_statement_upload(uploaded_file) -> str:
    """Validate an uploaded file and return its file type ('pdf' or 'csv')."""
    if uploaded_file is None:
        raise InvalidStatementFile('No file was uploaded.', code='missing_file')

    if uploaded_file.size == 0:
        raise InvalidStatementFile('The uploaded file is empty.', code='empty_file')

    if uploaded_file.size > settings.STATEMENT_MAX_UPLOAD_BYTES:
        limit_mb = settings.STATEMENT_MAX_UPLOAD_BYTES / (1024 * 1024)
        raise InvalidStatementFile(f'The file is too large. The maximum size is {limit_mb:g} MB.', code='file_too_large')

    extension = os.path.splitext(uploaded_file.name or '')[1].lower().lstrip('.')
    if extension not in settings.STATEMENT_ALLOWED_EXTENSIONS:
        raise InvalidStatementFile('Only PDF and CSV files are supported.', code='unsupported_type')

    # Never trust the extension or the client-sent content type alone.
    head = _read_head(uploaded_file)
    if extension == 'pdf':
        if not head.startswith(PDF_MAGIC):
            raise InvalidStatementFile('This file does not look like a valid PDF.', code='content_mismatch')
        return StatementProcessing.FileType.PDF
    if b'\x00' in head or head.startswith(PDF_MAGIC):
        raise InvalidStatementFile('This file does not look like a valid CSV.', code='content_mismatch')
    return StatementProcessing.FileType.CSV


def _read_head(uploaded_file, size: int = 2048) -> bytes:
    uploaded_file.seek(0)
    head = uploaded_file.read(size)
    uploaded_file.seek(0)
    return head

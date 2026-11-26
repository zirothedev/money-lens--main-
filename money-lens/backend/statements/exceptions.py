class StatementUploadError(Exception):
    """Base class for upload problems that are safe to show to the user."""

    code = 'upload_error'

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class InvalidStatementFile(StatementUploadError):
    code = 'invalid_file'


class DuplicateStatementError(StatementUploadError):
    code = 'duplicate_upload'

    def __init__(self, message: str, existing_job):
        super().__init__(message)
        self.existing_job = existing_job

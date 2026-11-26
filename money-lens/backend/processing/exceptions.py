class StatementExtractionError(Exception):
    """The statement could not be read at all (as opposed to individual bad rows)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

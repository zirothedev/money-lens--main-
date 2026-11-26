"""Public entry point of the extraction layer."""
from .csv_extractor import read_csv
from .exceptions import StatementExtractionError
from .normalizer import normalize
from .pdf_extractor import read_pdf
from .schema import ExtractionResult


def extract_statement(path, file_type: str) -> ExtractionResult:
    """Read a statement file from disk and return validated, normalized transactions.

    Raises StatementExtractionError if the file cannot be read or contains no transactions.
    Individual unusable rows are reported in result.rejected instead of failing the file.
    """
    if file_type == 'pdf':
        output = read_pdf(str(path))
    elif file_type == 'csv':
        with open(path, 'rb') as fh:
            output = read_csv(fh.read())
    else:
        raise StatementExtractionError('unsupported_type', 'Unsupported statement type.')

    result = normalize(output)
    if not result.transactions:
        raise StatementExtractionError('no_transactions', 'No transactions could be found in this statement.')
    return result

import csv
import io

from .columns import find_header
from .parsing import find_labelled_currency, find_statement_period
from .exceptions import StatementExtractionError
from .schema import ReaderOutput
from .table_reader import fields_from_rows


def _decode(data: bytes) -> str:
    if data.startswith((b'\xff\xfe', b'\xfe\xff')):
        try:
            return data.decode('utf-16')
        except UnicodeError:
            pass
    try:
        return data.decode('utf-8-sig')
    except UnicodeError:
        return data.decode('latin-1')


def read_csv(data: bytes) -> ReaderOutput:
    text = _decode(data)
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=',;\t|')
    except csv.Error:
        dialect = csv.excel
    try:
        rows = [list(r) for r in csv.reader(io.StringIO(text), dialect)]
    except csv.Error as exc:
        raise StatementExtractionError('csv_unreadable', 'The CSV file could not be read.') from exc

    found = find_header(rows)
    if found is None:
        raise StatementExtractionError(
            'csv_no_header', 'Could not find a transaction table (date and amount columns) in this CSV.')
    header_index, cmap = found
    out = fields_from_rows(rows[header_index + 1:], cmap, start_index=header_index + 1,
                           header_cells=rows[header_index], header_text=' '.join(rows[header_index]))
    preamble = rows[:header_index]
    out.currency = out.currency or find_labelled_currency(preamble) or ''
    out.period = find_statement_period(' '.join(' '.join(r) for r in preamble))
    return out

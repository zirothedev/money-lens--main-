"""PDF statement reading with pdfplumber: table mode first, text-line mode as a fallback."""
import logging
import re
from decimal import Decimal

from .columns import find_header
from .exceptions import StatementExtractionError
from .parsing import detect_currency, find_labelled_currency, find_statement_period, parse_amount
from .pdf_positioned import read_positioned_table
from .schema import RawFields, ReaderOutput, RejectedRecord
from .table_reader import fields_from_rows

logger = logging.getLogger(__name__)

_DATE_AT_START = re.compile(
    r'^(?P<date>\d{4}-\d{2}-\d{2}|\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{1,2}[ -][A-Za-z]{3,9}[ -,]*\d{2,4})\b\s*')
_AMOUNT_TOKEN = r'(?:[₦$£€]\s?)?\(?-?\d[\d,]*\.\d{2}\)?(?:\s?(?:CR|DR)\b)?'
_TRAILING_AMOUNTS = re.compile(rf'(?:\s+{_AMOUNT_TOKEN})+\s*$', re.I)
_AMOUNT_FINDER = re.compile(_AMOUNT_TOKEN, re.I)
_OPENING = re.compile(r'(opening balance|balance b/?f|brought forward)', re.I)
_FOOTER = re.compile(r'^(page\s+\d+(\s+(of|/)\s+\d+)?|\d+\s+of\s+\d+)$', re.I)


def read_pdf(path_or_file) -> ReaderOutput:
    import pdfplumber

    try:
        pdf = pdfplumber.open(path_or_file)
    except Exception as exc:
        code = 'pdf_encrypted' if 'password' in type(exc).__name__.lower() else 'pdf_unreadable'
        logger.warning('PDF could not be opened (%s)', type(exc).__name__)
        raise StatementExtractionError(code, 'The PDF could not be read. It may be corrupted or password protected.') from exc

    try:
        with pdf:
            table_rows: list[list[str]] = []
            lines: list[str] = []
            for page in pdf.pages:
                for table in page.extract_tables() or []:
                    table_rows.extend([[_clean_cell(c) for c in row] for row in table])
                lines.extend((page.extract_text() or '').splitlines())
            best = _read_transactions(table_rows, lines)
            if _looks_unreliable(best):                 # ragged or missing ruling lines: rebuild the table from positions
                sections = read_positioned_table(pdf)
                if sections:
                    alternative = _read_positioned(sections)
                    if _score(alternative) > _score(best):
                        best = alternative
    except StatementExtractionError:
        raise
    except Exception as exc:
        logger.warning('PDF extraction failed (%s)', type(exc).__name__)
        raise StatementExtractionError('pdf_unreadable', 'The PDF could not be read.') from exc

    if not table_rows and not any(l.strip() for l in lines):
        raise StatementExtractionError(
            'pdf_no_text', 'No readable text was found in this PDF. Scanned statements are not supported yet.')

    header_currency = find_labelled_currency(table_rows) or ''
    stated_period = (find_statement_period('\n'.join(lines))
                     or find_statement_period(' '.join(' '.join(r) for r in table_rows)))

    out = best
    out.currency = out.currency or header_currency       # only what the statement itself states
    out.period = stated_period
    return out


def _looks_unreliable(out: ReaderOutput) -> bool:
    """No rows at all, or more than 5% of the rows it saw were unusable."""
    seen = len(out.rows) + len(out.rejected)
    return not out.rows or len(out.rejected) > 0.05 * seen


def _score(out: ReaderOutput) -> int:
    return len(out.rows) - len(out.rejected)


def _read_positioned(sections) -> ReaderOutput:
    """Read every section with its own header, then combine them."""
    combined = ReaderOutput()
    offset = 0
    for header, cmap, rows in sections:
        part = fields_from_rows(rows, cmap, start_index=offset, header_cells=header, header_text=' '.join(header))
        combined.rows.extend(part.rows)
        combined.rejected.extend(part.rejected)
        combined.skipped_rows += part.skipped_rows
        combined.currency = combined.currency or part.currency
        offset += len(rows)
    return combined


def _read_transactions(table_rows, lines) -> ReaderOutput:
    found = find_header(table_rows)
    if found is not None:
        header_index, cmap = found
        header = table_rows[header_index]
        out = fields_from_rows(table_rows[header_index + 1:], cmap, start_index=header_index + 1,
                               header_cells=header, header_text=' '.join(header))
        if out.rows:
            return out
    return read_text_lines(lines)


def _clean_cell(cell) -> str:
    return re.sub(r'\s+', ' ', (cell or '').replace('\n', ' ')).strip()


def read_text_lines(lines: list[str]) -> ReaderOutput:
    """Fallback for PDFs without detectable tables: one transaction per dated line.

    Direction is only set when the statement makes it explicit (separate debit/credit
    amounts, a CR/DR marker, or a running balance that moves by exactly the amount).
    Otherwise the line is rejected rather than guessed.
    """
    full_text = '\n'.join(lines)
    detected = {c for c in (detect_currency(full_text),) if c}
    out = ReaderOutput(currency=next(iter(detected), ''))
    previous: RawFields | None = None
    prev_balance: Decimal | None = None

    for number, raw in enumerate(lines, start=1):
        line = re.sub(r'\s+', ' ', raw).strip()
        if not line or _FOOTER.match(line):
            continue
        date_match = _DATE_AT_START.match(line)
        if not date_match:
            opening = _OPENING.search(line)
            amounts = _AMOUNT_FINDER.findall(line)
            if opening and amounts:
                try:
                    prev_balance = parse_amount(amounts[-1])[0]
                except ValueError:
                    pass
                out.skipped_rows += 1
            elif previous is not None and not amounts:
                previous.description = f'{previous.description} {line}'.strip()
            continue

        rest = line[date_match.end():]
        second = _DATE_AT_START.match(rest)  # optional value date
        if second:
            rest = rest[second.end():]
        tail = _TRAILING_AMOUNTS.search(rest)
        if not tail:
            out.rejected.append(RejectedRecord(number, 'no_amount'))
            continue
        description = rest[:tail.start()].strip()
        tokens = _AMOUNT_FINDER.findall(tail.group(0))
        fields = _fields_from_tokens(number, date_match.group('date'), description, tokens, prev_balance, out)
        if fields is None:
            continue
        if fields.balance is not None:
            prev_balance = fields.balance
        out.rows.append(fields)
        previous = fields
    return out


def _fields_from_tokens(number, date_text, description, tokens, prev_balance, out) -> RawFields | None:
    def reject(reason):
        out.rejected.append(RejectedRecord(number, reason))
        return None

    try:
        parsed = [parse_amount(t) for t in tokens]
    except ValueError:
        return reject('invalid_amount')

    debit = credit = balance = None
    if len(parsed) >= 3:
        (d, _), (c, _), (balance, _) = parsed[-3:]
        d_on, c_on = bool(d), bool(c)
        if d_on == c_on:
            return reject('ambiguous_direction')
        debit, credit = (abs(d), None) if d_on else (None, abs(c))
    elif len(parsed) == 2:
        (amount, marker), (balance, _) = parsed
        direction = 'debit' if marker == 'DR' else 'credit' if marker == 'CR' else None
        if direction is None and amount < 0:
            direction = 'debit'
        if direction is None and prev_balance is not None:
            if prev_balance - abs(amount) == balance:
                direction = 'debit'
            elif prev_balance + abs(amount) == balance:
                direction = 'credit'
        if direction is None:
            return reject('unknown_direction')
        debit, credit = (abs(amount), None) if direction == 'debit' else (None, abs(amount))
    else:
        (amount, marker), = parsed
        direction = 'debit' if marker == 'DR' or amount < 0 else 'credit' if marker == 'CR' else None
        if direction is None:
            return reject('unknown_direction')
        debit, credit = (abs(amount), None) if direction == 'debit' else (None, abs(amount))

    return RawFields(row_number=number, date_text=date_text, description=description,
                     debit=debit, credit=credit, balance=balance,
                     currency=detect_currency(' '.join(tokens)) or '')

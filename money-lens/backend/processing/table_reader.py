"""Turn rows of a table (CSV, or a PDF table) into RawFields using a ColumnMap."""
import re

from .columns import ColumnMap, normalize_header
from .parsing import detect_currency, parse_amount
from .schema import RawFields, ReaderOutput, RejectedRecord

_SUMMARY_ROW = re.compile(
    r'^\s*(opening|closing|brought forward|carried forward|balance (b/?f|c/?f|brought|carried)|b/?f\b|c/?f\b|total|totals|'
    r'summary|statement)\b', re.I)
_DEBIT_WORDS = {'dr', 'd', 'debit', 'withdrawal', 'out', 'debited'}
_CREDIT_WORDS = {'cr', 'c', 'credit', 'deposit', 'in', 'credited'}


def _is_zero(value) -> bool:
    return value is None or value == 0


def fields_from_rows(rows: list[list[str]], cmap: ColumnMap, start_index: int = 0,
                     header_cells: list[str] | None = None, header_text: str = '') -> ReaderOutput:
    out = ReaderOutput(currency=detect_currency(header_text) or '')
    header_norm = [normalize_header(c) for c in header_cells] if header_cells else None

    # Signed-amount statements are only trusted if the file actually contains negatives.
    signed_mode = cmap.has('amount') and not (cmap.has('debit') or cmap.has('credit')) and not cmap.has('type')
    has_negative = False
    if signed_mode:
        for row in rows:
            try:
                value, marker = parse_amount(cmap.get(row, 'amount'))
            except ValueError:
                continue
            if marker is None and value is not None and value < 0:
                has_negative = True
                break

    previous: RawFields | None = None
    for offset, row in enumerate(rows):
        row_number = start_index + offset + 1
        cells = [(c or '').strip() for c in row]
        if not any(cells):
            continue
        if header_norm is not None and [normalize_header(c) for c in cells] == header_norm:
            out.skipped_rows += 1  # header repeated on a new PDF page
            continue

        date_text = cmap.get(row, 'date')
        description = re.sub(r'\s+', ' ', cmap.get(row, 'description'))
        if _SUMMARY_ROW.match(date_text):
            out.skipped_rows += 1
            continue
        if not date_text:
            amounts_present = any(cmap.get(row, r) for r in ('debit', 'credit', 'amount'))
            if description and not amounts_present and previous is not None:
                previous.description = f'{previous.description} {description}'.strip()  # wrapped text
            elif _SUMMARY_ROW.match(description or ' '.join(cells)):
                out.skipped_rows += 1
            else:
                out.rejected.append(RejectedRecord(row_number, 'missing_date'))
            continue
        if _SUMMARY_ROW.match(description):
            out.skipped_rows += 1
            continue

        if header_cells is not None and len(cells) > len(header_cells):
            out.rejected.append(RejectedRecord(row_number, 'column_mismatch'))  # misquoted/misaligned row
            continue
        fields = _build_fields(row, row_number, cmap, date_text, description, signed_mode, has_negative, out)
        if fields is not None:
            out.rows.append(fields)
            previous = fields
    return out


def _build_fields(row, row_number, cmap, date_text, description, signed_mode, has_negative, out) -> RawFields | None:
    def reject(reason):
        out.rejected.append(RejectedRecord(row_number, reason))
        return None

    try:
        debit_val, debit_marker = parse_amount(cmap.get(row, 'debit'))
        credit_val, credit_marker = parse_amount(cmap.get(row, 'credit'))
        amount_val, amount_marker = parse_amount(cmap.get(row, 'amount'))
        balance_val, _ = parse_amount(cmap.get(row, 'balance'))
    except ValueError:
        return reject('invalid_amount')

    debit = credit = None
    if cmap.has('debit') or cmap.has('credit'):
        debit = abs(debit_val) if not _is_zero(debit_val) else None
        credit = abs(credit_val) if not _is_zero(credit_val) else None
        if debit and credit:
            return reject('ambiguous_direction')
        if not debit and not credit:
            return reject('no_amount')
    else:
        if _is_zero(amount_val):
            return reject('no_amount')
        direction = _direction_from_type(cmap.get(row, 'type')) if cmap.has('type') else None
        if cmap.has('type') and direction is None and amount_marker is None:
            return reject('unknown_direction')
        if amount_marker:
            direction = 'debit' if amount_marker == 'DR' else 'credit'
        if direction is None:
            if not (signed_mode and has_negative):
                return reject('unknown_direction')
            direction = 'debit' if amount_val < 0 else 'credit'
        if direction == 'debit':
            debit = abs(amount_val)
        else:
            credit = abs(amount_val)

    amount_text = ' '.join(cmap.get(row, r) for r in ('debit', 'credit', 'amount'))
    currency = cmap.get(row, 'currency').upper() or detect_currency(amount_text) or ''
    return RawFields(
        row_number=row_number, date_text=date_text, description=description,
        debit=debit, credit=credit,
        narration_text=re.sub(r'\s+', ' ', cmap.get(row, 'narration_only')),
        recipient_text=cmap.get(row, 'recipient'), sender_text=cmap.get(row, 'sender'),
        reference=cmap.get(row, 'reference'), currency=currency, balance=balance_val,
        via_text=re.sub(r'\s+', ' ', cmap.get(row, 'institution')),
        description_is_narration=cmap.description_header == 'narration',
    )


def _direction_from_type(value: str) -> str | None:
    word = re.sub(r'[^a-z]', '', (value or '').lower())
    if word in _DEBIT_WORDS:
        return 'debit'
    if word in _CREDIT_WORDS:
        return 'credit'
    return None

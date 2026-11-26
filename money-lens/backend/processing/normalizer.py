"""RawFields -> validated NormalizedTransaction, with duplicate protection."""
import dataclasses
from collections import Counter

from .parsing import parse_date
from .recipients import clean_name, parse_description
from .schema import ExtractionResult, NormalizedTransaction, RawFields, ReaderOutput, RejectedRecord
from .validation import validate_transaction


def normalize(output: ReaderOutput, dayfirst: bool = True) -> ExtractionResult:
    result = ExtractionResult(
        rejected=list(output.rejected), skipped_rows=output.skipped_rows, currency=output.currency)
    if output.period:
        result.period_start, result.period_end = output.period
    candidates: list[NormalizedTransaction] = []
    for fields in output.rows:
        tx = _to_transaction(fields, output.currency, dayfirst)
        if isinstance(tx, str):
            result.rejected.append(RejectedRecord(fields.row_number, tx))
            continue
        reason = validate_transaction(tx)
        if reason:
            result.rejected.append(RejectedRecord(fields.row_number, reason))
            continue
        candidates.append(tx)
    unique, result.duplicates_removed = remove_duplicates(candidates)
    result.transactions = unify_spellings(unique)
    return result


def _to_transaction(f: RawFields, default_currency: str, dayfirst: bool) -> NormalizedTransaction | str:
    parsed_date = parse_date(f.date_text, dayfirst=dayfirst)
    if parsed_date is None:
        return 'invalid_date'
    outgoing = f.debit is not None

    parsed = parse_description(f.description, outgoing, via_hint=f.via_text)
    explicit = clean_name(f.recipient_text if outgoing else f.sender_text)
    # A recognised bank format is read from the full text; otherwise the statement's own name column wins.
    name = parsed.name if parsed.known and parsed.name else (explicit or parsed.name)
    from_column = bool(explicit) and name == explicit and not parsed.known
    narration = f.narration_text or parsed.narration  # a dedicated narration column wins
    if not narration and from_column and f.description_is_narration:
        narration = f.description                     # the 'Narration' column is what the sender wrote
    via = parsed.via or (f.via_text if outgoing and from_column else '')

    return NormalizedTransaction(
        date=parsed_date,
        description=f.description,
        debit=f.debit,
        credit=f.credit,
        recipient=name if outgoing else None,
        sender=None if outgoing else name,
        narration=narration or '',
        reference=f.reference,
        currency=f.currency or default_currency,
        balance=f.balance,
        via=via if outgoing else '',
        merchant_id=parsed.merchant_id,
    )


def remove_duplicates(transactions: list[NormalizedTransaction]) -> tuple[list[NormalizedTransaction], int]:
    """Drop rows that are the SAME ledger entry extracted twice (e.g. a repeated PDF page).

    Two identical-looking transfers on one day are often genuinely separate payments, so a
    row is only treated as a duplicate when it carries something that makes it unique in the
    statement: a reference number or a running balance. Rows with neither are always kept.
    """
    seen: set[tuple] = set()
    unique: list[NormalizedTransaction] = []
    removed = 0
    for tx in transactions:
        if tx.reference or tx.balance is not None:
            key = (tx.date, tx.debit, tx.credit, tx.description, tx.reference, tx.balance)
            if key in seen:
                removed += 1
                continue
            seen.add(key)
        unique.append(tx)
    return unique, removed


def unify_spellings(transactions: list[NormalizedTransaction]) -> list[NormalizedTransaction]:
    """Give every transaction that shares a statement-stated merchant id the same written name.

    Some card text blanks a random letter in the merchant name, so one merchant appears under dozens of
    spellings. Rows are matched ONLY by the merchant id the statement itself prints, and all of them take the
    most common spelling written in the statement (earliest wins a tie). No name is invented.
    """
    spellings: dict[str, Counter] = {}
    first_seen: dict[tuple[str, str], str] = {}
    for tx in transactions:
        if tx.merchant_id and tx.recipient:
            key = ' '.join(tx.recipient.split()).casefold()
            spellings.setdefault(tx.merchant_id, Counter())[key] += 1
            first_seen.setdefault((tx.merchant_id, key), tx.recipient)
    chosen: dict[str, str] = {}
    for merchant_id, counts in spellings.items():
        top = max(counts.values())
        best = next(k for k in counts if counts[k] == top)      # Counter keeps first-seen order
        chosen[merchant_id] = first_seen[(merchant_id, best)]
    return [dataclasses.replace(tx, recipient=chosen[tx.merchant_id])
            if tx.merchant_id in chosen and tx.recipient else tx for tx in transactions]

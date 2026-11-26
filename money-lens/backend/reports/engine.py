"""Deterministic report calculations. Pure Python + Decimal: no database, no I/O, no AI.

Every number in a report is computed here from the normalized transactions.
"""
import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from processing.schema import NormalizedTransaction
from processing.version import PARSER_VERSION

ZERO = Decimal('0.00')


class ReportError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class RecipientSummary:
    name: str
    total_sent: Decimal
    transaction_count: int
    rank: int
    transactions: tuple[NormalizedTransaction, ...]


@dataclass(frozen=True)
class ReportData:
    period_start: date | None
    period_end: date | None
    currency: str
    total_received: Decimal
    total_sent: Decimal
    incoming_count: int
    outgoing_count: int
    recipients: tuple[RecipientSummary, ...]
    unidentified_total: Decimal
    unidentified_count: int
    transactions: tuple[NormalizedTransaction, ...]
    fingerprint: str


def recipient_key(name: str) -> str:
    """Grouping key: 'AHMED  Musa' and 'Ahmed Musa' are the same recipient."""
    return re.sub(r'\s+', ' ', name).strip().casefold()


def _sort_key(tx: NormalizedTransaction):
    return (tx.date, tx.description, tx.reference, str(tx.debit), str(tx.credit), tx.narration)


def build_report_data(transactions: list[NormalizedTransaction],
                      stated_period: tuple[date, date] | None = None) -> ReportData:
    if not transactions:
        raise ReportError('no_transactions', 'There are no transactions to report on.')

    currencies = {t.currency for t in transactions if t.currency}
    if len(currencies) > 1:
        raise ReportError('multiple_currencies',
                          'This statement contains more than one currency, which is not supported yet.')

    ordered = tuple(sorted(transactions, key=_sort_key))  # makes output independent of input order
    period_start, period_end = ordered[0].date, ordered[-1].date
    if stated_period and stated_period[0] <= period_start and period_end <= stated_period[1]:
        period_start, period_end = stated_period   # the statement's own printed period, if it covers every transaction
    outgoing = [t for t in ordered if t.is_outgoing]
    incoming = [t for t in ordered if not t.is_outgoing]

    groups: dict[str, list[NormalizedTransaction]] = {}
    unidentified: list[NormalizedTransaction] = []
    for tx in outgoing:
        if tx.recipient:
            groups.setdefault(recipient_key(tx.recipient), []).append(tx)
        else:
            unidentified.append(tx)

    summaries = []
    for txs in groups.values():
        spellings = Counter(t.recipient for t in txs)
        top = max(spellings.values())
        display = next(t.recipient for t in txs if spellings[t.recipient] == top)  # most common, earliest wins ties
        summaries.append((display, sum((t.debit for t in txs), ZERO), tuple(txs)))
    summaries.sort(key=lambda s: (-s[1], -len(s[2]), s[0].casefold()))
    recipients = tuple(
        RecipientSummary(name=name, total_sent=total, transaction_count=len(txs), rank=i, transactions=txs)
        for i, (name, total, txs) in enumerate(summaries, start=1)
    )

    return ReportData(
        period_start=period_start,
        period_end=period_end,
        currency=next(iter(currencies), ''),
        total_received=sum((t.credit for t in incoming), ZERO),
        total_sent=sum((t.debit for t in outgoing), ZERO),
        incoming_count=len(incoming),
        outgoing_count=len(outgoing),
        recipients=recipients,
        unidentified_total=sum((t.debit for t in unidentified), ZERO),
        unidentified_count=len(unidentified),
        transactions=ordered,
        fingerprint=compute_fingerprint(ordered),
    )


def compute_fingerprint(ordered: tuple[NormalizedTransaction, ...]) -> str:
    """Hash of the statement's transactions; identifies 'the same statement' for duplicate protection."""
    digest = hashlib.sha256()
    digest.update(PARSER_VERSION.encode())
    for t in ordered:
        digest.update('|'.join([t.date.isoformat(), str(t.debit), str(t.credit), t.description, t.reference]).encode())
        digest.update(b'\n')
    return digest.hexdigest()

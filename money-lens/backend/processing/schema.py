"""Normalized transaction schema shared by every extractor and the report engine.

Data rules (non-negotiable):
- narration is "" when the statement has none; it is never filled with placeholder text.
- recipient / sender is None when the statement does not clearly identify one.
- nothing here is ever inferred or generated; every value comes from the statement.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class NormalizedTransaction:
    date: date
    description: str            # full transaction text exactly as in the statement
    debit: Decimal | None       # money out (positive number) or None
    credit: Decimal | None      # money in (positive number) or None
    recipient: str | None       # who received the money (debits only); None if not identified
    narration: str = ''         # narration present in the statement, else ""
    reference: str = ''
    currency: str = ''
    sender: str | None = None   # who sent the money (credits only); None if not identified
    balance: Decimal | None = None
    via: str = ''               # bank/wallet the statement says the money went through (e.g. OPAY)
    merchant_id: str = ''       # stable id stated in the statement; only used to group spelling variants

    @property
    def is_outgoing(self) -> bool:
        return self.debit is not None

    @property
    def amount(self) -> Decimal:
        return self.debit if self.debit is not None else self.credit


@dataclass(frozen=True)
class RejectedRecord:
    """A row that could not be turned into a valid transaction. Holds no financial data."""

    row_number: int
    reason: str


@dataclass
class ExtractionResult:
    transactions: list[NormalizedTransaction] = field(default_factory=list)
    rejected: list[RejectedRecord] = field(default_factory=list)
    duplicates_removed: int = 0
    skipped_rows: int = 0   # non-transaction rows such as opening/closing balance lines
    currency: str = ''
    period_start: date | None = None   # the statement's own stated period, when it prints one
    period_end: date | None = None


@dataclass
class RawFields:
    """Intermediate, not-yet-normalized fields read from one statement row."""

    row_number: int
    date_text: str
    description: str
    debit: Decimal | None = None
    credit: Decimal | None = None
    narration_text: str = ''
    recipient_text: str = ''
    sender_text: str = ''
    reference: str = ''
    currency: str = ''
    balance: Decimal | None = None
    via_text: str = ''                 # the statement's destination-institution column, if it has one
    description_is_narration: bool = False   # the text column is headed 'Narration'


@dataclass
class ReaderOutput:
    """What a reader (CSV table / PDF table / PDF text) hands to the normalizer."""

    rows: list[RawFields] = field(default_factory=list)
    rejected: list[RejectedRecord] = field(default_factory=list)
    skipped_rows: int = 0
    currency: str = ''
    period: tuple[date, date] | None = None

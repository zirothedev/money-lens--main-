from decimal import Decimal

from .schema import NormalizedTransaction

MAX_AMOUNT = Decimal('9999999999999.99')  # fits Report DecimalField(16, 2)


def validate_transaction(tx: NormalizedTransaction) -> str | None:
    """Return a reason code if the transaction is invalid, else None."""
    if (tx.debit is None) == (tx.credit is None):
        return 'ambiguous_direction'
    amount = tx.amount
    if amount is None or amount <= 0:
        return 'non_positive_amount'
    if amount > MAX_AMOUNT:
        return 'amount_too_large'
    if tx.date.year < 1990 or tx.date.year > 2100:
        return 'implausible_date'
    return None

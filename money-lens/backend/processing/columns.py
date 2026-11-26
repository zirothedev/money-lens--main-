"""Header detection and column mapping for tabular statements (CSV and PDF tables)."""
import re
from dataclasses import dataclass, field

# Role -> accepted normalized header names, in priority order where it matters.
_ALIASES: dict[str, tuple[str, ...]] = {
    'date': ('transaction date', 'trans time', 'transaction time', 'trans date', 'txn date', 'tran date', 'date', 'posting date', 'post date',
             'booking date', 'value date'),
    'description': ('description', 'transaction description', 'transaction details', 'details', 'particulars',
                    'narrative', 'narration'),
    'narration_only': ('remarks', 'remark', 'note', 'notes', 'memo', 'customer narration', 'user narration'),
    'debit': ('debit', 'debits', 'debit amount', 'settlement debit', 'withdrawal', 'withdrawals', 'money out', 'paid out', 'dr'),
    'credit': ('credit', 'credits', 'credit amount', 'settlement credit', 'deposit', 'deposits', 'money in', 'paid in', 'cr'),
    'amount': ('amount', 'transaction amount'),
    'type': ('type', 'dr cr', 'drcr', 'cr dr', 'debit credit', 'transaction type', 'direction'),
    'balance': ('balance', 'balance after', 'running balance', 'closing balance', 'available balance'),
    'reference': ('reference', 'ref', 'ref no', 'reference number', 'transaction reference', 'transaction id',
                  'session id', 'trans ref', 'txn id', 'transaction ref'),
    'currency': ('currency', 'ccy'),
    'recipient': ('beneficiary', 'beneficiary name', 'recipient', 'recipient name', 'payee', 'receiver',
                  'counterparty', 'counterparty name'),
    'sender': ('sender', 'sender name', 'originator'),
    'institution': ('beneficiary institution', 'beneficiary bank', 'recipient bank', 'destination bank'),
}
_NOISE_WORDS = {'ngn', 'usd', 'gbp', 'eur', 'naira', 'n'}


def normalize_header(cell: str | None) -> str:
    text = re.sub(r'[^a-z0-9/ ]+', ' ', (cell or '').lower()).replace('/', ' ')
    words = [w for w in text.split() if w not in _NOISE_WORDS]
    return ' '.join(words)


@dataclass
class ColumnMap:
    indices: dict[str, int] = field(default_factory=dict)
    description_header: str = ''   # normalized header of the description column, e.g. 'narration'

    def get(self, row: list[str], role: str) -> str:
        idx = self.indices.get(role)
        if idx is None or idx >= len(row):
            return ''
        return (row[idx] or '').strip()

    def has(self, role: str) -> bool:
        return role in self.indices

    @property
    def is_usable(self) -> bool:
        return self.has('date') and (self.has('debit') or self.has('credit') or self.has('amount'))


def map_columns(header_cells: list[str]) -> ColumnMap:
    normalized = [normalize_header(c) for c in header_cells]
    indices: dict[str, int] = {}
    used: set[int] = set()
    for role, aliases in _ALIASES.items():
        for alias in aliases:
            hit = next((i for i, n in enumerate(normalized) if n == alias and i not in used), None)
            if hit is not None:
                indices[role] = hit
                used.add(hit)
                break

    # A lone "Narration" column holds the full text (description); it is only a separate
    # narration when another description-like column also exists.
    if 'narration_only' in indices and 'description' not in indices:
        indices['description'] = indices.pop('narration_only')
    return ColumnMap(indices, description_header=normalized[indices['description']] if 'description' in indices else '')


def find_header(rows: list[list[str]], max_scan: int = 30) -> tuple[int, ColumnMap] | None:
    """Find the first row that looks like a transaction-table header."""
    for i, row in enumerate(rows[:max_scan]):
        cmap = map_columns(row)
        if cmap.is_usable:
            return i, cmap
    return None

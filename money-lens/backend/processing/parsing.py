"""Pure parsing helpers: dates, amounts, currency. No Django, no I/O."""
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

_DATE_FORMATS_DAYFIRST = [
    '%Y-%m-%d', '%Y/%m/%d', '%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y', '%d/%m/%y', '%d-%m-%y',
    '%d %b %Y', '%d %B %Y', '%d-%b-%Y', '%d-%B-%Y', '%d-%b-%y', '%d %b %y', '%d/%b/%Y',
    '%b %d, %Y', '%B %d, %Y', '%b %d %Y', '%B %d %Y',
]
_DATE_FORMATS_MONTHFIRST = ['%m/%d/%Y', '%m-%d-%Y', '%m/%d/%y'] + _DATE_FORMATS_DAYFIRST
_TIME_SUFFIX = re.compile(r'(?:[T\s]+)\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?\s*(?:[AaPp][Mm])?\s*(?:Z|[+-]\d{2}:?\d{2})?$')


def parse_date(raw: str | None, dayfirst: bool = True) -> date | None:
    """Parse a date in any supported format; None if it cannot be parsed.

    Dates with no year (e.g. "03 Sep") are deliberately NOT guessed.
    Ambiguous numeric dates are read day-first unless dayfirst=False.
    """
    text = (raw or '').strip()
    if not text:
        return None
    compact = re.sub(r'\s+', '', text)           # a wrapped cell reads '2026- 08- 18T18: 08:55'
    iso = re.match(r'^(\d{4})-(\d{2})-(\d{2})(?:T|$)', compact)
    if iso:
        try:
            return date(int(iso[1]), int(iso[2]), int(iso[3]))
        except ValueError:
            return None
    text = _TIME_SUFFIX.sub('', text).strip()
    text = re.sub(r'\bsept\b', 'Sep', text, flags=re.I)
    text = re.sub(r'(?<=\d)(st|nd|rd|th)\b', '', text)
    formats = _DATE_FORMATS_DAYFIRST if dayfirst else _DATE_FORMATS_MONTHFIRST
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


_CURRENCY_SYMBOLS = {'₦': 'NGN', '$': 'USD', '£': 'GBP', '€': 'EUR'}
_CURRENCY_CODE_RE = re.compile(r'\b(NGN|USD|GBP|EUR)\b', re.I)


_CURRENCY_NAMES = {
    'NIGERIAN NAIRA': 'NGN', 'NAIRA': 'NGN', 'US DOLLAR': 'USD', 'US DOLLARS': 'USD', 'UNITED STATES DOLLAR': 'USD',
    'BRITISH POUND': 'GBP', 'POUND STERLING': 'GBP', 'POUNDS STERLING': 'GBP', 'EURO': 'EUR', 'EUROS': 'EUR',
}


def currency_from_name(value: str | None) -> str | None:
    """'NIGERIAN NAIRA' / 'NGN' -> 'NGN'. Only a whole-value match, never a guess."""
    text = re.sub(r'\s+', ' ', (value or '').strip()).upper().strip(' :.')
    if text in _CURRENCY_NAMES:
        return _CURRENCY_NAMES[text]
    return text if re.fullmatch(r'NGN|USD|GBP|EUR', text) else None


def find_labelled_currency(rows) -> str | None:
    """Find a 'Currency | <value>' pair in header-block rows (lists of cells)."""
    for row in rows:
        cells = [(c or '').strip() for c in row]
        for i, cell in enumerate(cells):
            if re.fullmatch(r'currency\s*:?', cell, re.I):
                for value in cells[i + 1:]:
                    if value:
                        return currency_from_name(value)
    return None


_PERIOD = re.compile(r'(?:Statement\s+Period|^\s*Date)\s*:?\s*(?P<a>\d\S*)\s*(?:to|-|–|—)\s*(?P<b>\d\S*)', re.I | re.M)


_PERIOD_WORDS = re.compile(r'Period\s*:?\s*(?P<a>\d{1,2} [A-Za-z]{3,9} \d{4})\s*(?:to|-|–|—)\s*(?P<b>\d{1,2} [A-Za-z]{3,9} \d{4})', re.I)


def find_statement_period(text: str | None):
    """'Statement Period :01-Aug-2026 to 26-Sep-2026' -> (date, date), or None."""
    m = _PERIOD.search(text or '') or _PERIOD_WORDS.search(text or '')
    if not m:
        return None
    start, end = parse_date(m['a']), parse_date(m['b'])
    return (start, end) if start and end and start <= end else None


def detect_currency(text: str | None) -> str | None:
    """Return an ISO code if the text states a currency, else None."""
    if not text:
        return None
    m = _CURRENCY_CODE_RE.search(text)
    if m:
        return m.group(1).upper()
    for symbol, code in _CURRENCY_SYMBOLS.items():
        if symbol in text:
            return code
    return None


_STRIP_CURRENCY = re.compile(r'₦|\bNGN\b|\bUSD\b|\bGBP\b|\bEUR\b|[$£€]|^N(?=\s*\d)', re.I)
_THOUSANDS = re.compile(r'^\d{1,3}(,\d{3})*(\.\d+)?$')
_PLAIN = re.compile(r'^\d+(\.\d+)?$')
_EU_DECIMAL = re.compile(r'^\d+,\d{1,2}$')
_EU_FULL = re.compile(r'^\d{1,3}(\.\d{3})+,\d+$')
_MARKER = re.compile(r'(?<![A-Za-z])(CR|DR)(?![A-Za-z])', re.I)
_MINUS = '-−–'


def parse_amount(raw: str | None) -> tuple[Decimal | None, str | None]:
    """Parse a money cell into (signed Decimal, 'CR'/'DR' marker).

    Returns (None, None) for an empty cell. Raises ValueError on anything that is
    not clearly a number, rather than guessing.
    """
    text = (raw or '').replace('\xa0', ' ').strip()
    if not text or text in {'-', '--', '—', '–'}:
        return None, None

    marker = None
    m = _MARKER.search(text)
    if m:
        marker = m.group(1).upper()
        text = text[:m.start()] + text[m.end():]

    text = _STRIP_CURRENCY.sub('', text).strip()
    negative = False
    if text.startswith('(') and text.endswith(')'):
        negative, text = True, text[1:-1].strip()
    if text and text[0] in _MINUS:
        negative, text = True, text[1:].strip()
    elif text and text[-1] in _MINUS:
        negative, text = True, text[:-1].strip()
    text = text.lstrip('+').replace(' ', '')

    if _THOUSANDS.match(text):
        number = text.replace(',', '')
    elif _PLAIN.match(text):
        number = text
    elif _EU_FULL.match(text):
        number = text.replace('.', '').replace(',', '.')
    elif _EU_DECIMAL.match(text):
        number = text.replace(',', '.')
    else:
        raise ValueError('not a number')

    try:
        value = Decimal(number)
    except InvalidOperation as exc:
        raise ValueError('not a number') from exc
    quantized = value.quantize(Decimal('0.01'))
    if quantized != value:
        raise ValueError('more than two decimal places')
    return (-quantized if negative else quantized), marker

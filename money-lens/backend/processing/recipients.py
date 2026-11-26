"""Conservative recipient / sender / narration extraction from a transaction description.

Only EXPLICIT statements are recognised:
  debit  : "<transfer-ish word> ... TO <name>"
  credit : "<transfer-ish word> ... FROM <name>"
Anything else yields None. Nothing is inferred; unrecognised formats stay unidentified.
Text after the name (introduced by a separator such as "/", "|", " - ", ":" or the words
FOR / BEING / NARRATION) is returned as the narration, minus reference-number-like segments.
"""
import re
from dataclasses import dataclass

_CHANNEL = r'(?:TRANSFER|TRF|NIP|IFT|FIP|PAYMENT|PYMT|PMT|SENT|SEND|PAID|USSD|MOBILE|WEB|NEFT|RTGS|BILL|DEPOSIT|CREDIT|RECEIVED|INWARD|OUTWARD)'
_OUT_RE = re.compile(rf'\b{_CHANNEL}\b[^/|]{{0,40}}?\bTO\b\s*[:\-]?\s*(?P<rest>.+)$', re.I | re.S)
_IN_RE = re.compile(rf'\b{_CHANNEL}\b[^/|]{{0,40}}?\bFROM\b\s*[:\-]?\s*(?P<rest>.+)$', re.I | re.S)

_L = r"[^\W\d_]"  # any Unicode letter
_TOKEN = rf"{_L}(?:{_L}|[.'&\-])*"
_NAME_RE = re.compile(rf'\s*(?P<name>{_TOKEN}(?:[ \t]+{_TOKEN}){{0,7}})')
_TOKEN_RE = re.compile(_TOKEN)

_STOP_WORDS = {'FOR', 'REF', 'REFERENCE', 'BEING', 'NARRATION', 'NARR', 'ON', 'VIA', 'FROM', 'AT', 'TO',
               'WITH', 'CHARGES', 'FEE', 'FEES', 'SESSION', 'PAYMENT', 'TRANSFER'}
_GENERIC_WORDS = {'ACCOUNT', 'ACCT', 'AC', 'SELF', 'OWN', 'CUSTOMER', 'BENEFICIARY', 'BANK', 'WALLET',
                  'SAVINGS', 'CURRENT', 'THE', 'A', 'AN', 'ANOTHER', 'YOUR', 'MY', 'NA', 'N/A', 'UNKNOWN', 'NONE'}
_NARRATION_LEAD = re.compile(r'^(?:FOR|BEING|NARRATION|NARR)\b[\s:\-]*', re.I)
_LEADING_SEPARATORS = re.compile(r'^[\s/|:\-]+')
_SEGMENT_SPLIT = re.compile(r'\s*[/|]\s*|\s+-\s+')


@dataclass(frozen=True)
class ParsedDescription:
    name: str | None
    narration: str
    via: str = ''
    merchant_id: str = ''
    known: bool = False     # read from a recognised bank format (so it outranks the statement's name columns)


def parse_description(description: str, outgoing: bool, via_hint: str = '') -> ParsedDescription:
    """Extract (name, narration) from a description. Name is None when not clearly stated."""
    text = (description or '').strip()
    if not text:
        return ParsedDescription(None, '')
    from .formats import parse_known_format
    known = parse_known_format(text, outgoing, via_hint)
    if known is not None:
        return ParsedDescription(known.name, known.narration, known.via, known.merchant_id, known=True)
    match = (_OUT_RE if outgoing else _IN_RE).search(text)
    if not match:
        return ParsedDescription(None, '')

    rest = match.group('rest')
    name_match = _NAME_RE.match(rest)
    if not name_match:
        return ParsedDescription(None, '')

    tokens = list(_TOKEN_RE.finditer(name_match.group('name')))
    cut = len(tokens)
    for i, tok in enumerate(tokens):
        if tok.group(0).upper().strip('.-') in _STOP_WORDS:
            cut = i
            break
    if cut == 0:
        return ParsedDescription(None, '')

    kept = tokens[:cut]
    name = clean_name(' '.join(t.group(0) for t in kept))
    if name is None:
        return ParsedDescription(None, '')

    end = name_match.start('name') + kept[-1].end()
    return ParsedDescription(name, _clean_narration(rest[end:]))


def clean_name(raw: str | None) -> str | None:
    """Tidy a name found in the statement; None if it is empty or not a real name."""
    name = re.sub(r'\s+', ' ', (raw or '')).strip(" .-'/|:")
    if len(name) < 2 or not re.search(r'[^\W\d_]', name):
        return None
    words = {w.upper().strip('.') for w in name.split()}
    if words <= _GENERIC_WORDS:
        return None
    return name


def _looks_like_reference(segment: str) -> bool:
    compact = segment.replace(' ', '')
    if not re.search(r'[^\W\d_]', compact):
        return True  # digits/punctuation only
    return len(compact) >= 12 and bool(re.search(r'\d', compact)) and ' ' not in segment.strip()


def _clean_narration(remainder: str) -> str:
    text = _LEADING_SEPARATORS.sub('', remainder)
    text = _NARRATION_LEAD.sub('', text)
    parts = [p.strip() for p in _SEGMENT_SPLIT.split(text)]
    parts = [_NARRATION_LEAD.sub('', p).strip() for p in parts]
    return ' '.join(p for p in parts if p and not _looks_like_reference(p))

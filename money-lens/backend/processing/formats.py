"""Bank-specific description formats.

Some banks write structured text into the description (e.g. GTBank's
``TRANSFER TO <BANK> - <NAME>``). Where a format is recognised with confidence, the names it
states are read exactly as written. Nothing is guessed: a description that matches no format here
falls through to the generic rules in ``recipients.py``.

Each handler is keyed on text that is distinctive for that format (a fixed prefix), so a format
from another bank that merely looks similar is never mis-read.
"""
import re
from dataclasses import dataclass

# Cities the card networks append after a merchant name. Used only to drop a trailing location
# from a POS/web merchant string. Extend freely.
_CITIES = {
    'LAGOS', 'LA', 'ABUJA', 'ABJ', 'BAUCHI', 'KADUNA', 'KANO', 'JOS', 'IBADAN', 'ENUGU', 'ASABA', 'BENIN',
    'WARRI', 'ABA', 'AWKA', 'AKURE', 'ILORIN', 'OWERRI', 'UYO', 'CALABAR', 'MAIDUGURI', 'SOKOTO', 'YOLA',
    'MINNA', 'LOKOJA', 'MAKURDI', 'GOMBE', 'ABEOKUTA', 'OSOGBO', 'ADO EKITI', 'UMUAHIA', 'ONITSHA', 'NNEWI',
    'PORT HARCOURT', 'PH', 'IKEJA', 'LEKKI', 'VICTORIA ISLAND', 'OTHER',
}
_NAME_FIELD_WIDTH = 23   # card acceptor name field is fixed-width; longer text is name + glued city


@dataclass(frozen=True)
class FormatResult:
    name: str | None
    narration: str = ''
    via: str = ''           # institution/wallet the bank states the money went through (e.g. OPAY)
    merchant_id: str = ''   # stable id stated in the statement; used only to group spelling variants


def parse_known_format(description: str, outgoing: bool, via_hint: str = '') -> FormatResult | None:
    text = re.sub(r'\s+', ' ', description or '').strip()
    if not text:
        return None
    handlers = (_nip_outward, _airtime, _nips_direct_debit, _gtworld_transfer, _card_merchant, _moniepoint, _opay)
    for handler in handlers:
        result = handler(text, outgoing, via_hint)
        if result is not None:
            return result
    return None


# --- helpers ---------------------------------------------------------------------------------------

def _clean(name: str | None) -> str | None:
    from .recipients import clean_name
    return clean_name(name)


_SEPARATOR = re.compile(r'\s+-\s*|\s*-\s+')   # a hyphen with whitespace on at least one side


def _narration_text(text: str) -> str:
    from .recipients import _NARRATION_LEAD
    return _NARRATION_LEAD.sub('', text.strip(' -/|:')).strip()


# --- GTBank: "Instant Payment Outward <ref> [note] NIP TRANSFER TO <BANK> - <NAME>" ------------------------

_NIP_OUTWARD = re.compile(
    r'^Instant Payment Outward\s+(?P<ref>\d{10,})\s*(?P<pre>.*?)\s*\bTO\s+(?P<inst>[A-Za-z0-9&.]+)\s+-\s*(?P<rest>.+)$',
    re.I)
_TRANSFER_SUFFIX = re.compile(r'\s*\b(?:(?:NIP|OUTWARD)\s+)?TRANSFER$', re.I)


def _nip_outward(text: str, outgoing: bool, hint: str = '') -> FormatResult | None:
    if not outgoing:
        return None
    m = _NIP_OUTWARD.match(text)
    if not m:
        return None
    parts = [p for p in _SEPARATOR.split(m['rest'].strip()) if p.strip()]
    name = _clean(parts[-1]) if parts else None
    if name is None:
        return None
    note = _TRANSFER_SUFFIX.sub('', m['pre']).strip()
    extra = ' '.join(parts[:-1])          # e.g. "POS TRANSFER" written before the name
    narration = _narration_text(' '.join(x for x in (note, extra) if x))
    return FormatResult(name=name, narration=narration, via=m['inst'].upper())


# --- Airtime / data: "Airtime Purchase ... FROM <payer> TO <NETWORK> AIRTIME COLLECTION SALES" ---------------

def _airtime(text: str, outgoing: bool, hint: str = '') -> FormatResult | None:
    if not outgoing or not text.lower().startswith('airtime purchase') or ' TO ' not in text:
        return None
    name = _clean(text.rsplit(' TO ', 1)[1])
    return FormatResult(name=name) if name else None


# --- NIPS direct debit: "NIPS DIRECT DEBIT ... FROM <payer> TO <COMPANY> [FROM<digits>...] - <note>" --------

_NAME_STOP = re.compile(r'(?:FROM(?=\d|\s|$)|\d|:|\s-\s)')


def _nips_direct_debit(text: str, outgoing: bool, hint: str = '') -> FormatResult | None:
    if not outgoing or not text.upper().startswith('NIPS DIRECT DEBIT') or ' TO ' not in text:
        return None
    after = text.split(' TO ', 1)[1]
    stop = _NAME_STOP.search(after)
    name = _clean(after[:stop.start()] if stop else after)
    if name is None:
        return None
    note = after.split(' - ', 1)[1] if ' - ' in after else ''
    return FormatResult(name=name, narration=_narration_text(note))


# --- GTWorld app transfer: "TRANSFER BETWEEN CUSTOMERS VIA GTWORLD [note] FROM <payer> TO <payee>" -----------

_GTWORLD = re.compile(
    r'^TRANSFER BETWEEN CUSTOMERS VIA GTWORLD\s*(?P<note>.*?)\s*\bFROM\s+(?P<payer>.+?)\s+TO\s+(?P<payee>.+)$', re.I)


def _gtworld_transfer(text: str, outgoing: bool, hint: str = '') -> FormatResult | None:
    m = _GTWORLD.match(text)
    if not m:
        return None
    name = _clean(m['payee'] if outgoing else m['payer'])
    return FormatResult(name=name, narration=_narration_text(m['note'])) if name else None


# --- Card acquirer text: "... POS PUR [T] <MERCHANT><CITY> <ST>NG <stan> ..." / "... WEB PUR ..." -------------

_CARD = re.compile(r'\b(?P<kind>POS|WEB) (?:PUR|WD)\b(?:\s+T\b)?\s+(?P<body>.+?)\s(?:[A-Z]{2}NG|NG)\s+\d{6}\b')
_TERMINAL = re.compile(r'\b(?P<term>[0-9A-Z]{8})539983')


def _card_merchant(text: str, outgoing: bool, hint: str = '') -> FormatResult | None:
    if not outgoing:
        return None
    m = _CARD.search(text)
    if not m:
        return None
    body = m['body'].strip()
    terminal = _TERMINAL.search(text)
    term = terminal['term'] if terminal else ''

    tokens = body.split()
    if term and tokens and tokens[-1] == term:           # "<NAME> <random code> <terminal id>"
        tokens = tokens[:-1]
        if len(tokens) > 1 and 4 <= len(tokens[-1]) <= 6:
            tokens = tokens[:-1]
    name_part = ' '.join(tokens)

    merchant_id = ''
    if m['kind'] == 'WEB':
        id_match = re.match(r'^(?P<id>[0-9A-Z]{8})\s+(?P<rest>.+)$', name_part)
        if id_match and re.search(r'\d', id_match['id']):
            merchant_id = id_match['id']
            name_part = id_match['rest']
    name = _clean(_split_city(name_part))
    return FormatResult(name=name, merchant_id=merchant_id) if name else None


def _split_city(value: str) -> str:
    """Remove the city that card networks append to the fixed-width merchant name field."""
    value = value.strip()
    # City glued onto a full-width name: "...ENTEBauchi", "...ENTERPRISLAGOS"
    if len(value) > _NAME_FIELD_WIDTH and value[_NAME_FIELD_WIDTH - 1].isalpha() and value[_NAME_FIELD_WIDTH].isalpha():
        remainder = value[_NAME_FIELD_WIDTH:]
        if remainder.upper() in _CITIES or re.fullmatch(r'[A-Z][a-z]+(?: [A-Z][a-z]+)*', remainder):
            return value[:_NAME_FIELD_WIDTH]
    # City as its own trailing word(s): "... LAGOS", "... LA", "... Bauchi"
    words = value.split()
    for take in (2, 1):
        if len(words) > take and ' '.join(words[-take:]).upper() in _CITIES:
            return ' '.join(words[:-take])
    return value


# --- Moniepoint: the Narration column ---------------------------------------------------------------------
# via_hint is the statement's "Beneficiary Institution" cell. It can carry a few stray characters of an
# overflowing name, so it is only used as the END of the narration's "<name> <institution> *****1234" text.

_MP_POS = re.compile(r'^POS purchase at (?:T\s+)?(?P<name>.+?)(?:\s+\d{3,6})?$', re.I)
_MP_TRANSFER_TO = re.compile(r'^TRANSFER TO\s+(?P<body>.+?)\s*\*{3,}\d+', re.I)
_MP_INTERNAL = re.compile(r'^(?P<payer>.+?)\s+TO\s+(?P<payee>.+?)\s+MONIEPOINT\s*\*{3,}\d+', re.I)
_MP_AIRTIME = re.compile(r'^AIRTIME TO\s+(?P<phone>\d{7,})\s+(?P<network>[A-Za-z0-9]+)', re.I)
_MP_BILL = re.compile(r'^BILL PAYMENT FOR\s+.+?\s\d{6,}\b', re.I)
_MP_POS_TRANSFER = re.compile(r'^(?P<note>POS Transfer)\s*-\s*(?P<name>.+)$', re.I)
_MP_LABELS = {'stamp duty', 'value added tax', 'card request and delivery'}


def _strip_institution(body: str, hint: str) -> tuple[str | None, str]:
    hint = ' '.join((hint or '').split())
    for k in range(len(hint)):
        suffix = hint[k:]
        if len(suffix) >= 3 and body.lower().endswith(' ' + suffix.lower()):
            return body[:-(len(suffix) + 1)].strip(), suffix
    return None, ''


def _moniepoint(text: str, outgoing: bool, hint: str = '') -> FormatResult | None:
    if text.lower() in _MP_LABELS or text.upper().startswith('CARD REQUEST AND DELIVERY'):
        label = 'CARD REQUEST AND DELIVERY' if text.upper().startswith('CARD REQUEST') else text   # fee rows the statement labels itself
        return FormatResult(name=_clean(label)) if outgoing else None
    m = _MP_TRANSFER_TO.match(text)
    if m and outgoing:
        body, institution = _strip_institution(m['body'].strip(), hint)
        if not body:
            return None                                          # can't split name from bank safely: use the columns
        note = ''
        pos = _MP_POS_TRANSFER.match(body)
        if pos:
            note, body = pos['note'], pos['name']
        name = _clean(body)
        return FormatResult(name=name, narration=note, via=institution) if name else None
    m = _MP_INTERNAL.match(text)
    if m:
        name = _clean(m['payee'] if outgoing else m['payer'])
        return FormatResult(name=name, via=' '.join(hint.split()) if outgoing else '') if name else None
    if not outgoing:
        return None
    m = _MP_POS.match(text)
    if m:
        name = _clean(m['name'])
        return FormatResult(name=name) if name else None
    m = _MP_AIRTIME.match(text)
    if m:
        return FormatResult(name=f"{m['phone']} {m['network']}")
    if _MP_BILL.match(text):
        name = _clean(hint)                                      # the biller, e.g. "Jos Electricity Distribution Prepaid"
        return FormatResult(name=name) if name else None
    return None


# --- OPay: pipe-delimited descriptions -------------------------------------------------------------------

_OP_TRANSFER = re.compile(r'^Transfer (?P<dir>to|from)\s+(?P<name>[^|]+?)\s*\|\s*(?P<inst>[^|]+?)\s*\|\s*(?P<acct>[\d*]+)\s*(?:\|\s*(?P<note>.*))?$', re.I)
_OP_CARD = re.compile(r'^OPay Card Payment\s*\|\s*[^|]*\|\s*(?P<term>[^|]+?)\s*\|\s*[^|]*\|\s*(?P<rest>.+)$', re.I)
_OP_SERVICE = re.compile(r'^(?:Airtime|Mobile Data)\s*\|\s*(?P<phone>\d{7,})\s*\|\s*(?P<network>[^|]+?)\s*(?:\|\s*(?P<plan>.+))?$', re.I)
_OP_AUTOSAVE = re.compile(r'^Auto-save to (?P<name>OWealth Balance)$', re.I)
_OP_LABELS = {'ussd charge', 'vat on transfer fee', 'owealth interest earned', 'owealth withdrawal (transaction payment)'}
_LONG_DIGITS = re.compile(r'\b\d{10,}\b')


def _opay(text: str, outgoing: bool, hint: str = '') -> FormatResult | None:
    m = _OP_TRANSFER.match(text)
    if m and (m['dir'].lower() == 'to') == outgoing:
        name_text, note = m['name'].strip(), ''
        pos = _MP_POS_TRANSFER.match(name_text)
        if pos:
            name_text, note = pos['name'], pos['note']
        name = _clean(name_text)
        if not name:
            return None
        if m['note'] and not outgoing:                  # credits can carry the sender's note and the bank's own text
            note = _narration_text(_LONG_DIGITS.sub('', m['note']).strip(' .'))
        return FormatResult(name=name, narration=note, via=m['inst'].strip())
    m = _OP_CARD.match(text)
    if m and outgoing:
        rest = re.sub(r'\s[A-Z]{2}NG$', '', m['rest'].strip())            # state + country, e.g. LANG
        term = m['term'].strip()
        if term and rest.endswith(' ' + term):
            rest = rest[: -len(term)].strip()
            rest = re.sub(r'\s\d{6}$', '', rest)                         # transaction counter
        rest = re.sub(r'^T\s+', '', rest)                                # terminal-type flag
        name = _clean(_split_city(rest))
        return FormatResult(name=name) if name else None
    m = _OP_SERVICE.match(text)
    if m and outgoing:
        return FormatResult(name=f"{m['phone']} {m['network']}", narration=(m['plan'] or '').strip())
    m = _OP_AUTOSAVE.match(text)
    if m:
        return FormatResult(name=m['name'], narration='Auto-save')
    label = re.sub(r'(\w)\(', r'\1 (', text)
    if label.lower() in _OP_LABELS:                                          # labels this statement gives itself
        return FormatResult(name=label)
    return None

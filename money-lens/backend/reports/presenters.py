"""Turns saved report data into template-ready values. Display formatting only.

All numbers come straight from the stored Report (calculated by reports.engine).
The only derived value here is the bar width: each recipient's total as a
percentage of the largest recipient's total.
"""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings

from . import services

CURRENCY_SYMBOLS = {'NGN': '₦', 'USD': '$', 'GBP': '£', 'EUR': '€'}
MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September',
               'October', 'November', 'December']
MONTH_ABBR = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def currency_symbol(code: str) -> str:
    code = code or settings.REPORT_FALLBACK_CURRENCY
    if not code:
        return ''
    return CURRENCY_SYMBOLS.get(code, f'{code} ')


def _full_date(d: date) -> str:
    return f'{d.day:02d} {MONTH_ABBR[d.month - 1]} {d.year}'


def format_period(start: date | None, end: date | None) -> tuple[str, str]:
    """Return (period label, one-line intro). Wording follows the real period, never 'this month' by default."""
    if not start or not end:
        return '', "Here's where your money went."
    if start == end:
        return _full_date(start), f"Here's where your money went on {_full_date(start)}."
    if (start.year, start.month) == (end.year, end.month):
        label = f'{MONTH_NAMES[start.month - 1]} {start.year}'
        return label, f"Here's where your money went in {label}."
    label = f'{_full_date(start)} – {_full_date(end)}'
    return label, f"Here's where your money went between {_full_date(start)} and {_full_date(end)}."


def _tx_detail(t: dict) -> dict:
    return {'date': date.fromisoformat(t['date']), 'amount': Decimal(t['amount']), 'narration': t['narration']}


def build_report_context(report) -> dict:
    data = services.report_to_dict(report)
    start = report.period_start
    end = report.period_end
    label, intro = format_period(start, end)

    totals = [Decimal(r['total_sent']) for r in data['recipients']]
    top = max(totals, default=None)
    recipients = []
    for r in data['recipients']:
        total = Decimal(r['total_sent'])
        percent = int((total / top * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP)) if top else 0
        recipients.append({
            'rank': r['rank'], 'name': r['name'], 'total_sent': total, 'transaction_count': r['transaction_count'],
            'percent': percent, 'transactions': [_tx_detail(t) for t in r['transactions']],
        })

    transactions = [
        {'date': date.fromisoformat(t['date']), 'amount': Decimal(t['amount']), 'direction': t['direction'],
         'name': t['counterparty'] or None, 'narration': t['narration'], 'via': t['via']}
        for t in data['transactions']
    ]
    unidentified_txs = [t for t in transactions if t['direction'] == 'out' and not t['name']]

    return {
        'report': report,
        'currency': currency_symbol(report.currency),
        'period_label': label,
        'intro': intro,
        'show_year': bool(start and end and start.year != end.year),
        'total_received': report.total_received,
        'incoming_count': report.incoming_count,
        'total_sent': report.total_sent,
        'outgoing_count': report.outgoing_count,
        'recipients': recipients,
        'unidentified': {
            'count': report.unidentified_count, 'total': report.unidentified_total,
            'transactions': unidentified_txs,
        },
        'transactions': transactions,
    }


def build_history_context(reports) -> dict:
    items = []
    for r in reports:
        label, _ = format_period(r.period_start, r.period_end)
        items.append({'report': r, 'period_label': label or 'Statement report', 'currency': currency_symbol(r.currency)})
    return {'items': items}

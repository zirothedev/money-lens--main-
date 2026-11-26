"""Display filters for report templates. Formatting only; never calculates anything."""
from datetime import date
from decimal import Decimal

from django import template

register = template.Library()

MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


@register.filter
def money(value, symbol=''):
    """Decimal -> '₦15,000' (cents shown only when non-zero)."""
    if value is None or value == '':
        return ''
    amount = Decimal(value)
    text = f'{amount:,.0f}' if amount == amount.to_integral_value() else f'{amount:,.2f}'
    return f'{symbol}{text}'


@register.filter
def short_date(value: date, with_year=False):
    """date -> '03 Sep' (or '03 Sep 2025' when with_year)."""
    if not value:
        return ''
    text = f'{value.day:02d} {MONTHS[value.month - 1]}'
    return f'{text} {value.year}' if with_year else text

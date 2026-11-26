from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from processing.parsing import detect_currency, parse_amount, parse_date


class DateTests(SimpleTestCase):
    def test_formats(self):
        expected = date(2025, 9, 3)
        for raw in ['2025-09-03', '03/09/2025', '03-09-2025', '03 Sep 2025', '03-Sep-2025', '3 September 2025',
                    'Sep 3, 2025', '2025-09-03 14:22:10', '03-Sep-2025 14:22', '03/09/25', '3rd Sep 2025', '03.09.2025']:
            self.assertEqual(parse_date(raw), expected, raw)

    def test_dayfirst_ambiguity(self):
        self.assertEqual(parse_date('04/05/2025'), date(2025, 5, 4))
        self.assertEqual(parse_date('04/05/2025', dayfirst=False), date(2025, 4, 5))

    def test_invalid_and_yearless_not_guessed(self):
        for raw in ['', None, 'not a date', '31/02/2025', '03 Sep']:
            self.assertIsNone(parse_date(raw), raw)


class AmountTests(SimpleTestCase):
    def test_formats(self):
        cases = {
            '15000': Decimal('15000.00'), '15,000.00': Decimal('15000.00'), '₦15,000.00': Decimal('15000.00'),
            'NGN 1,250,000.50': Decimal('1250000.50'), 'N 5,000': Decimal('5000.00'),
            '1.234,56': Decimal('1234.56'), '1500,50': Decimal('1500.50'), '$ 99.9': Decimal('99.90'),
            '(1,200.50)': Decimal('-1200.50'), '-3000': Decimal('-3000.00'), '3,000.00-': Decimal('-3000.00'),
            '0.00': Decimal('0.00'),
        }
        for raw, value in cases.items():
            self.assertEqual(parse_amount(raw)[0], value, raw)

    def test_markers(self):
        self.assertEqual(parse_amount('5,000.00 DR'), (Decimal('5000.00'), 'DR'))
        self.assertEqual(parse_amount('5,000.00CR'), (Decimal('5000.00'), 'CR'))

    def test_empty(self):
        for raw in ['', None, '-', '  ']:
            self.assertEqual(parse_amount(raw), (None, None))

    def test_garbage_raises_instead_of_guessing(self):
        for raw in ['abc', '1.234', '12x', '1,2,3', '15,000.005']:
            with self.assertRaises(ValueError, msg=raw):
                parse_amount(raw)

    def test_decimal_exactness(self):
        total = sum(parse_amount(x)[0] for x in ['0.10', '0.20', '0.30'])
        self.assertEqual(total, Decimal('0.60'))

    def test_currency(self):
        self.assertEqual(detect_currency('₦5,000'), 'NGN')
        self.assertEqual(detect_currency('Debit (NGN)'), 'NGN')
        self.assertEqual(detect_currency('USD'), 'USD')
        self.assertIsNone(detect_currency('5,000'))

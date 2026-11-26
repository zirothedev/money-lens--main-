"""OPay-style statements: two account sections, pipe-delimited descriptions. All names are fictional."""
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pdfplumber
from django.test import SimpleTestCase
from reportlab.pdfgen import canvas

from processing.formats import parse_known_format
from processing.parsing import find_statement_period
from processing.pdf_positioned import read_positioned_table
from processing.pipeline import extract_statement
from processing.tests import helpers

WALLET = [
    ('26 Sep 2026 06:56:26', 'Transfer to ADA OBI | OPay | 8012345678', '2,500.00', ''),
    ('26 Sep 2026 07:10:00', 'Transfer to POS Transfer-JANE ROE | MONIE POINT | 6012345678', '500.00', ''),
    ('27 Sep 2026 08:00:00', 'Transfer to EMMANUEL - SUNDAY | OPay | 7012345678', '1,000.00', ''),
    ('27 Sep 2026 09:30:00', 'OPay Card Payment | MONIE POINT | 2IST4FFQ | 260927nCxkkL | T NGOZI GRACE TEST 003934 2IST4FFQ LANG', '300.00', ''),
    ('27 Sep 2026 10:30:00', 'OPay Card Payment | OPay | 257ZZJQ9 | 2610256744734 | OPAY DIGITAL SERVICES LIMITED LA LANG', '250.00', ''),
    ('28 Sep 2026 11:00:00', 'Mobile Data | 8059653881 | Glo | 1GB 7 Days Plan', '1,000.00', ''),
    ('28 Sep 2026 11:05:00', 'Airtime | 8059653881 | MTN', '200.00', ''),
    ('28 Sep 2026 12:00:00', 'Auto-save to OWealth Balance', '5,000.00', ''),
    ('29 Sep 2026 12:30:00', 'USSD Charge', '10.00', ''),
    ('29 Sep 2026 12:31:00', 'VAT on Transfer Fee', '0.70', ''),
    ('29 Sep 2026 13:00:00', 'Transfer from JOHN ROE | OPay | 903****273 | Purchase of Airtime', '', '9,000.00'),
    ('29 Sep 2026 14:00:00', 'OWealth Withdrawal(Transaction Payment)', '', '3,000.00'),
]
SAVINGS = [
    ('26 Sep 2026 09:00:00', 'Auto-save to OWealth Balance', '', '5,000.00'),
    ('27 Sep 2026 09:00:00', 'OWealth Interest Earned', '', '6.27'),
    ('29 Sep 2026 14:00:00', 'OWealth Withdrawal (Transaction Payment)', '3,000.00', ''),
]


class OpayStylePdfTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.path = Path(tempfile.mkdtemp()) / 'o.pdf'
        cls.printed = helpers.build_opay_style_pdf(
            cls.path, [{'title': 'Wallet Account', 'opening': '50,000.00', 'rows': WALLET},
                       {'title': 'Savings Account', 'opening': '1,000.00', 'rows': SAVINGS}])
        cls.result = extract_statement(cls.path, 'pdf')
        cls.tx = cls.result.transactions

    def test_both_sections_are_found_each_with_its_own_header(self):
        with pdfplumber.open(self.path) as pdf:
            sections = read_positioned_table(pdf)
        self.assertEqual([len(rows) for _, _, rows in sections], [len(WALLET), len(SAVINGS)])

    def test_every_row_is_read_and_totals_reconcile_with_both_summaries(self):
        self.assertEqual(len(self.tx), len(WALLET) + len(SAVINGS))
        self.assertEqual(self.result.rejected, [])
        want_debit = sum(p['total_debit'] for p in self.printed)
        want_credit = sum(p['total_credit'] for p in self.printed)
        self.assertEqual(sum((t.debit for t in self.tx if t.debit), Decimal(0)), want_debit)
        self.assertEqual(sum((t.credit for t in self.tx if t.credit), Decimal(0)), want_credit)

    def test_date_period_and_currency(self):
        self.assertEqual(self.tx[0].date, date(2026, 9, 26))
        self.assertEqual((self.result.period_start, self.result.period_end), (date(2026, 9, 26), date(2026, 10, 25)))

    def by_desc(self, text):
        return next(t for t in self.tx if text in t.description)

    def test_transfers_name_the_person_and_show_the_bank(self):
        t = self.by_desc('ADA OBI')
        self.assertEqual((t.recipient, t.via, t.narration), ('ADA OBI', 'OPay', ''))
        t = self.by_desc('JANE ROE')
        self.assertEqual((t.recipient, t.via, t.narration), ('JANE ROE', 'MONIE POINT', 'POS Transfer'))

    def test_a_dash_inside_a_name_is_kept(self):
        self.assertEqual(self.by_desc('EMMANUEL').recipient, 'EMMANUEL - SUNDAY')

    def test_card_merchants_are_read_as_written(self):
        self.assertEqual(self.by_desc('NGOZI GRACE').recipient, 'NGOZI GRACE TEST')
        self.assertEqual(self.by_desc('OPAY DIGITAL').recipient, 'OPAY DIGITAL SERVICES LIMITED')

    def test_data_airtime_and_labelled_rows(self):
        t = self.by_desc('Mobile Data')
        self.assertEqual((t.recipient, t.narration), ('8059653881 Glo', '1GB 7 Days Plan'))
        self.assertEqual(self.by_desc('Airtime |').recipient, '8059653881 MTN')
        self.assertEqual(self.by_desc('USSD Charge').recipient, 'USSD Charge')
        self.assertEqual(self.by_desc('VAT on Transfer Fee').recipient, 'VAT on Transfer Fee')
        savings_debit = next(t for t in self.tx if t.debit == Decimal('3000.00'))
        self.assertEqual(savings_debit.recipient, 'OWealth Withdrawal (Transaction Payment)')

    def test_auto_save_and_credits(self):
        t = next(t for t in self.tx if t.debit == Decimal('5000.00'))
        self.assertEqual((t.recipient, t.narration), ('OWealth Balance', 'Auto-save'))
        c = self.by_desc('JOHN ROE')
        self.assertEqual((c.sender, c.narration), ('JOHN ROE', 'Purchase of Airtime'))
        self.assertEqual(next(t for t in self.tx if t.credit == Decimal('6.27')).sender, 'OWealth Interest Earned')

    def test_no_outgoing_transaction_is_unidentified(self):
        self.assertEqual([t.description for t in self.tx if t.debit and not t.recipient], [])


class OpayFormatTests(SimpleTestCase):
    def test_credit_note_drops_the_banks_long_reference_numbers(self):
        r = parse_known_format('Transfer from JOHN ROE | GTBank | 308****2 | Outward Transfer to JANE. 000013260920100000000123456', False)
        self.assertEqual((r.name, r.narration), ('JOHN ROE', 'Outward Transfer to JANE'))

    def test_direction_must_match(self):
        self.assertIsNone(parse_known_format('Transfer to ADA OBI | OPay | 8012345678', False))
        self.assertIsNone(parse_known_format('Transfer from ADA OBI | OPay | 8012345678', True))

    def test_card_payment_without_the_terminal_repeat_still_names_the_merchant(self):
        r = parse_known_format('OPay Card Payment | OPay | 257ZZJQ9 | 261025 | SOME SHOP LIMITED LA LANG', True)
        self.assertEqual(r.name, 'SOME SHOP LIMITED')

    def test_other_banks_fee_text_is_not_named_by_the_opay_rules(self):
        for text in ['SMS ALERT FEE', 'VAT ON CHARGES', 'Maintenance Fee', 'ATM WITHDRAWAL']:
            self.assertIsNone(parse_known_format(text, True), text)

    def test_period_written_in_words(self):
        self.assertEqual(find_statement_period('Wallet Account Period: 26 Sep 2026 - 25 Oct 2026'), (date(2026, 9, 26), date(2026, 10, 25)))


class RowHeadStrandedOnThePreviousPageTests(SimpleTestCase):
    """The first line(s) of a row can land at the bottom of one page, with the dated line on the next."""

    def make_pdf(self):
        path = Path(tempfile.mkdtemp()) / 'head.pdf'
        c = canvas.Canvas(str(path), pagesize=(700, 400))
        c.setFont('Helvetica', 6)
        columns = [('Trans. Time', 20), ('Value Date', 100), ('Description', 170), ('Debit(N)', 330), ('Credit(N)', 390),
                   ('Balance After(N)', 450), ('Channel', 540), ('Transaction Reference', 600)]
        for label, x in columns:
            c.drawString(x, 350, label)

        def line(top, parts):
            for (_, x), text in zip(columns, parts):
                if text:
                    c.drawString(x, top, text)
        line(300, ['26 Sep 2026', '26 Sep 2026', 'Transfer to SHOP ONE | OPay | 8012345678', '100.00', '--', '900.00', 'Mobile', 'REF1'])
        line(30, ['', '', 'Transfer from SHOP TWO | OPay |', '', '', '', '', ''])        # head of the next row, bottom of page 1
        c.showPage()
        c.setFont('Helvetica', 6)
        line(380, ['27 Sep 2026', '27 Sep 2026', '903****273', '--', '50.00', '950.00', 'Mobile', 'REF2'])
        c.save()
        return path

    def test_head_is_attached_to_its_row(self):
        with pdfplumber.open(self.make_pdf()) as pdf:
            rows = read_positioned_table(pdf)[0][2]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][2], 'Transfer from SHOP TWO | OPay | 903****273')

    def test_extraction_names_both_rows(self):
        result = extract_statement(self.make_pdf(), 'pdf')
        self.assertEqual([(t.recipient, t.sender) for t in result.transactions], [('SHOP ONE', None), (None, 'SHOP TWO')])

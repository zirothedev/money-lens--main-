"""Moniepoint-style statements: borderless shaded table, wrapped cells, 19 columns. All names are fictional."""
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pdfplumber
from django.test import SimpleTestCase
from reportlab.pdfgen import canvas

from processing.columns import find_header
from processing.parsing import find_statement_period, parse_date
from processing.pdf_positioned import read_positioned_table
from processing.pipeline import extract_statement
from processing.tests import helpers

E = [
    dict(when='2026-08-18T18:08:55', ref='TRF|2MPTj26ss|2089761468517171200_CBA_CREDIT_0', credit='215.00', amount='215.00', ben='TEST USER ONE', inst='Moniepoint MFB', source='6067204709', src_inst='Moniepoint MFB', narration='ADA OBI TO TEST USER ONE MONIEPOINT *****23949 /TRF|2MPTj26ss|2089761468517171200_CBA'),
    dict(when='2026-08-18T18:11:09', ref='ECR|CS|5311023949|7459980972|1787073069_DEBIT_0', debit='200.00', narration='CARD REQUEST AND DELIVERY|ECR|CS|5311023949|7459980972|1787073069'),
    dict(when='2026-08-19T08:52:27', ref='CDS-19082026085227|2070W69F|20000|000183_DEBIT_0', debit='200.00', narration='POS purchase at T JANE ROE STORES 000'),
    dict(when='2026-08-19T10:39:50', ref='CDS-19082026103949|257ZHRCT|25000|005649_DEBIT_0', debit='250.00', narration='POS purchase at OPAY DIGITAL SERVICES L'),
    dict(when='2026-08-20T10:13:33', ref='TRF|2MPTspwh8|2094648817575981056_DEBIT_0', type='TRANSFER', debit='2,510.00', amount='2,500.00', charge='10.00', ben='ADA OBI', inst='OPay', narration='TRANSFER TO ADA OBI OPay *****41388 /TRF|2MPTspwh8|2094648817575981056'),
    dict(when='2026-08-20T10:13:33', ref='TRF|2MPTspwh8|2094648817575981056_DEBIT_1', type='TRANSFER', debit='0.75', amount='0.75', narration='Value Added Tax'),
    dict(when='2026-08-20T10:13:33', ref='TRF|2MPTspwh8|2094648817575981056_DEBIT_2', type='TRANSFER', debit='50.00', amount='50.00', narration='Stamp duty'),
    dict(when='2026-08-21T16:24:07', ref='ATP|2MPTspwfo|2098431557816684544_DEBIT_0', type='AIRTIME', debit='100.00', amount='100.00', ben='08030000000', inst='MTN', narration='AIRTIME TO 08030000000 MTN /ATP|2MPTspwfo|2098431557816684544'),
    dict(when='2026-08-22T21:32:33', ref='BPT|2MPTspwfo|2096335701246689280_DEBIT_0', type='BILL_PAYMENT', debit='1,000.00', amount='1,000.00', ben='45160735572', inst='Jos Electricity Distribution Prepaid', narration='BILL PAYMENT FOR TEST CUSTOMER 4 Jos Electricity Distribution Prepaid 45160735572 /BPT|2MPTspwfo|2096335701246689280'),
    dict(when='2026-08-23T12:49:15', ref='TRF|2MPTspwh8|2098853785897046016_DEBIT_0', type='TRANSFER', debit='500.00', amount='500.00', ben='POS Transfer- ADA OBI', inst='Moniepoint MFB', narration='TRANSFER TO POS Transfer- ADA OBI Moniepoint MFB *****54528 /TRF|2MPTspwh8|2098853785897046016'),
    dict(when='2026-08-24T13:25:42', ref='TRF|2MPTspwh8|2109968817165557760_DEBIT_0', type='TRANSFER', debit='410.00', amount='400.00', charge='10.00', ben='MARY OKON', inst='OPay', narration='Transportation'),
    dict(when='2026-08-25T09:15:30', ref='TRF|2MPTspwh8|2094745854805327872_CBA_DEBIT_0', type='TRANSFER', debit='2,000.00', amount='2,000.00', ben='JOHN ROE', inst='Moniepoint MFB', narration='TEST USER ONE TO JOHN ROE MONIEPOINT *****94601 /TRF|2MPTspwh8|2094745854805327872_CBA'),
    dict(when='2026-08-26T14:35:20', ref='MIT|HBP|100004260826131226174049736980|2113625227604017152_CREDIT_0', credit='1,000.00', source='7030041388', src_inst='OPay', narration='Transfer from JANE ROE'),
    dict(when='2026-08-27T10:00:00', ref='TRF|2MPTspwh8|2109632956219981824_DEBIT_0', type='TRANSFER', debit='710.00', amount='700.00', charge='10.00', ben='MUHAMMAD AHMAD EL-KUFAHN', inst='Jaiz Bank', narration='TRANSFER TO MUHAMMAD AHMAD EL-KUFAHN Jaiz Bank *****57206 /TRF|2MPTspwh8|2109632956219981824'),
]


class MoniepointStylePdfTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.path = Path(tempfile.mkdtemp()) / 'm.pdf'
        cls.printed = helpers.build_moniepoint_style_pdf(cls.path, E)
        cls.result = extract_statement(cls.path, 'pdf')
        cls.tx = cls.result.transactions

    def test_the_ruled_table_detector_cannot_read_this_layout(self):
        """Guards the premise: if a library upgrade made normal table detection work, this fallback may be unneeded."""
        with pdfplumber.open(self.path) as pdf:
            rows = [[c or '' for c in r] for t in pdf.pages[0].extract_tables() for r in t]
        self.assertIsNone(find_header(rows))

    def test_header_and_every_row_recovered(self):
        with pdfplumber.open(self.path) as pdf:
            sections = read_positioned_table(pdf)
        self.assertEqual(len(sections), 1)
        header, cmap, rows = sections[0]
        self.assertEqual(header[0], 'Date')
        self.assertEqual(header[9:13], ['Settlement Debit', 'Settlement Credit', 'Balance Before', 'Balance After'])
        self.assertEqual(header[-1], 'Narration')
        self.assertEqual(len(header), 19)
        self.assertEqual(len(rows), len(E))
        self.assertTrue(all(len(r) == 19 for r in rows))

    def test_totals_reconcile_with_the_statements_summary(self):
        self.assertEqual(len(self.tx), len(E))
        self.assertEqual(self.result.rejected, [])
        self.assertEqual(sum((t.debit for t in self.tx if t.debit), Decimal(0)), self.printed['total_debit'])
        self.assertEqual(sum((t.credit for t in self.tx if t.credit), Decimal(0)), self.printed['total_credit'])
        self.assertEqual(self.tx[-1].balance, self.printed['closing'])

    def test_wrapped_dates_and_the_statements_own_period(self):
        self.assertEqual(self.tx[0].date, date(2026, 8, 18))
        self.assertEqual((self.result.period_start, self.result.period_end), (date(2026, 7, 28), date(2026, 10, 26)))

    def by_ref(self, text):
        return next(t for t in self.tx if text in t.reference)

    def test_transfers_use_the_person_and_show_the_bank(self):
        t = self.by_ref('2094648817575981056_DEBIT_0')
        self.assertEqual((t.recipient, t.via, t.debit), ('ADA OBI', 'OPay', Decimal('2510.00')))
        t = self.by_ref('2109632956219981824_DEBIT_0')
        self.assertEqual((t.recipient, t.via), ('MUHAMMAD AHMAD EL-KUFAHN', 'Jaiz Bank'))       # hyphen kept

    def test_pos_transfer_note_becomes_narration(self):
        t = self.by_ref('2098853785897046016_DEBIT_0')
        self.assertEqual((t.recipient, t.narration, t.via), ('ADA OBI', 'POS Transfer', 'Moniepoint MFB'))

    def test_internal_moniepoint_transfer(self):
        t = self.by_ref('2094745854805327872_CBA_DEBIT_0')
        self.assertEqual((t.recipient, t.via), ('JOHN ROE', 'Moniepoint MFB'))

    def test_pos_purchases_use_the_merchant_as_written(self):
        self.assertEqual(self.by_ref('CDS-19082026085227').recipient, 'JANE ROE STORES')
        self.assertEqual(self.by_ref('CDS-19082026103949').recipient, 'OPAY DIGITAL SERVICES L')

    def test_airtime_bill_payment_and_fees_are_named_from_the_statement(self):
        self.assertEqual(self.by_ref('ATP|2MPTspwfo').recipient, '08030000000 MTN')
        self.assertEqual(self.by_ref('BPT|2MPTspwfo').recipient, 'Jos Electricity Distribution Prepaid')
        self.assertEqual(self.by_ref('_DEBIT_1').recipient, 'Value Added Tax')
        self.assertEqual(self.by_ref('_DEBIT_2').recipient, 'Stamp duty')
        self.assertEqual(self.by_ref('ECR|CS').recipient, 'CARD REQUEST AND DELIVERY')

    def test_the_senders_own_note_is_kept_as_narration(self):
        t = self.by_ref('2109968817165557760_DEBIT_0')
        self.assertEqual((t.recipient, t.via, t.narration), ('MARY OKON', 'OPay', 'Transportation'))

    def test_system_text_is_not_mistaken_for_a_narration(self):
        for t in self.tx:
            self.assertNotIn('TRANSFER TO', t.narration.upper())
            self.assertNotIn('POS purchase', t.narration)

    def test_credits_read_the_sender(self):
        self.assertEqual(self.by_ref('CREDIT_0').sender, 'ADA OBI')
        self.assertEqual(next(t for t in self.tx if t.credit == Decimal('1000.00')).sender, 'JANE ROE')

    def test_no_outgoing_transaction_is_unidentified(self):
        self.assertEqual([t.description[:50] for t in self.tx if t.debit and not t.recipient], [])


class RowSplitAcrossPagesTests(SimpleTestCase):
    """A row can be cut by a page break, its tail landing at the top of the next page."""

    def make_pdf(self):
        path = Path(tempfile.mkdtemp()) / 'split.pdf'
        c = canvas.Canvas(str(path), pagesize=(900, 400))
        c.setFont('Helvetica', 7)
        columns = [('Date', 20), ('Transaction Status', 80), ('Transaction Ref', 160), ('Settlement Debit', 300),
                   ('Settlement Credit', 380), ('Balance After', 460), ('Narration', 540)]
        for label, x in columns:
            c.drawString(x, 350, label)
        def row(top, parts):
            for (label, x), text in zip(columns, parts):
                for i, line in enumerate(text.split('\n')):
                    c.drawString(x, top - 8 * i, line)
        row(300, ['2026-\n08-\n18T09:\n10:11', 'COMPLETED', 'REF-ONE_DEBIT_0', '100.00', '0.00', '900.00', 'POS purchase at T SHOP ONE 001'])
        # second row is cut by the page break after its first two date lines
        row(60, ['2026-\n08-', 'COMPLETED', 'REF-TWO_DEBIT_0', '50.00', '0.00', '850.00', 'POS purchase at T SHOP TWO'])
        c.showPage()
        c.setFont('Helvetica', 7)
        row(380, ['19T10:\n20:21', '', '', '', '', '', '002'])      # the tail of row two, at the top of page 2
        row(300, ['2026-\n08-\n20T09:\n30:00', 'COMPLETED', 'REF-THREE_DEBIT_0', '25.00', '0.00', '825.00', 'POS purchase at T SHOP THREE 003'])
        c.save()
        return path

    def test_the_tail_is_merged_back_into_the_row_it_belongs_to(self):
        with pdfplumber.open(self.make_pdf()) as pdf:
            header, cmap, rows = read_positioned_table(pdf)[0]
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1][0].replace(' ', ''), '2026-08-19T10:20:21')

    def test_extraction_keeps_all_three_transactions_with_the_right_dates(self):
        result = extract_statement(self.make_pdf(), 'pdf')
        self.assertEqual([(t.date, t.debit) for t in result.transactions],
                         [(date(2026, 8, 18), Decimal('100.00')), (date(2026, 8, 19), Decimal('50.00')), (date(2026, 8, 20), Decimal('25.00'))])
        self.assertEqual([t.recipient for t in result.transactions], ['SHOP ONE', 'SHOP TWO', 'SHOP THREE'])


class DateAndPeriodHelpersTests(SimpleTestCase):
    def test_wrapped_iso_dates(self):
        self.assertEqual(parse_date('2026- 08- 18T18: 08:55'), date(2026, 8, 18))
        self.assertEqual(parse_date('2026- 08- 19T08:'), date(2026, 8, 19))          # time cut off by a page break
        self.assertEqual(parse_date('2026-09-\n01T05:47:54'), date(2026, 9, 1))
        self.assertIsNone(parse_date('2026- 13- 40T10:00'))

    def test_period_written_as_a_date_range(self):
        self.assertEqual(find_statement_period('Account Number 1\nDate 28/07/2026 - 26/10/2026\nAddress X'),
                         (date(2026, 7, 28), date(2026, 10, 26)))

    def test_a_table_header_line_is_not_mistaken_for_a_period(self):
        self.assertIsNone(find_statement_period('Date Account Name Transaction Type'))

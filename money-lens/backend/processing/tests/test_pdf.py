import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.test import SimpleTestCase

from processing.exceptions import StatementExtractionError
from processing.normalizer import normalize
from processing.pdf_extractor import read_pdf

from . import helpers


class PdfTests(SimpleTestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def extract(self, path):
        return normalize(read_pdf(str(path)))

    def test_table_pdf(self):
        r = self.extract(helpers.build_table_pdf(self.dir / 't.pdf'))
        t = r.transactions
        self.assertEqual(len(t), 4)
        self.assertEqual((t[0].date, t[0].debit, t[0].recipient, t[0].narration),
                         (date(2025, 9, 3), Decimal('15000.00'), 'AHMED MUSA', 'School fees'))
        self.assertEqual((t[2].credit, t[2].sender), (Decimal('50000.00'), 'GRACE OKAFOR'))
        self.assertEqual((t[3].recipient, t[3].narration), (None, ''))

    def test_table_pdf_repeated_page_is_deduplicated(self):
        r = self.extract(helpers.build_table_pdf(self.dir / 'd.pdf', repeat_page=True))
        self.assertEqual(len(r.transactions), 4)
        self.assertEqual(r.duplicates_removed, 4)
        self.assertEqual(r.rejected, [])  # the repeated header row is skipped, not rejected

    def test_text_pdf_debit_credit_balance_columns(self):
        lines = [
            'Statement of Account  (NGN)',
            'Date Description Debit Credit Balance',
            '03 Sep 2025 NIP TRANSFER TO AHMED MUSA/School fees 15,000.00 0.00 985,000.00',
            '09 Sep 2025 NIP TRANSFER FROM GRACE OKAFOR 0.00 50,000.00 1,035,000.00',
            'Page 1 of 1',
        ]
        r = self.extract(helpers.build_text_pdf(self.dir / 'x.pdf', lines))
        self.assertEqual([(t.debit, t.credit) for t in r.transactions],
                         [(Decimal('15000.00'), None), (None, Decimal('50000.00'))])
        self.assertEqual(r.currency, 'NGN')
        self.assertEqual(r.transactions[0].narration, 'School fees')

    def test_text_pdf_direction_from_running_balance(self):
        lines = [
            'Opening Balance 1,000,000.00',
            '03 Sep 2025 TRANSFER TO AHMED MUSA 15,000.00 985,000.00',
            '04 Sep 2025 TRANSFER FROM GRACE OKAFOR 50,000.00 1,035,000.00',
            '05 Sep 2025 SOMETHING ODD 7,777.00 900,000.00',
        ]
        r = self.extract(helpers.build_text_pdf(self.dir / 'b.pdf', lines))
        self.assertEqual([t.is_outgoing for t in r.transactions], [True, False])
        self.assertEqual([x.reason for x in r.rejected], ['unknown_direction'])  # balance doesn't reconcile: not guessed

    def test_text_pdf_wrapped_description(self):
        lines = ['03 Sep 2025 TRANSFER TO AHMED 15,000.00 0.00 985,000.00', 'MUSA']
        r = self.extract(helpers.build_text_pdf(self.dir / 'w.pdf', lines))
        self.assertEqual(r.transactions[0].recipient, 'AHMED MUSA')

    def test_corrupt_pdf_raises_extraction_error(self):
        bad = self.dir / 'bad.pdf'
        bad.write_bytes(b'%PDF-1.4 this is not really a pdf')
        with self.assertRaises(StatementExtractionError) as cm:
            read_pdf(str(bad))
        self.assertEqual(cm.exception.code, 'pdf_unreadable')

    def test_blank_pdf_raises_no_text(self):
        with self.assertRaises(StatementExtractionError) as cm:
            read_pdf(str(helpers.build_blank_pdf(self.dir / 'blank.pdf')))
        self.assertEqual(cm.exception.code, 'pdf_no_text')

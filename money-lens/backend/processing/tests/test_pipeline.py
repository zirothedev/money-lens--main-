import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from processing.exceptions import StatementExtractionError
from processing.pipeline import extract_statement

from . import helpers


class PipelineTests(SimpleTestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def test_csv_end_to_end(self):
        r = extract_statement(helpers.FIXTURES / 'gtb_style.csv', 'csv')
        self.assertEqual(len(r.transactions), 7)

    def test_pdf_end_to_end(self):
        r = extract_statement(helpers.build_table_pdf(self.dir / 'a.pdf'), 'pdf')
        self.assertEqual(len(r.transactions), 4)

    def test_pdf_extraction_failure(self):
        bad = self.dir / 'bad.pdf'
        bad.write_bytes(b'%PDF-1.7 garbage')
        with self.assertRaises(StatementExtractionError):
            extract_statement(bad, 'pdf')

    def test_file_with_only_invalid_rows_raises(self):
        f = self.dir / 'x.csv'
        f.write_bytes(b'Date,Description,Debit,Credit\nbad,x,1.00,\n')
        with self.assertRaises(StatementExtractionError) as cm:
            extract_statement(f, 'csv')
        self.assertEqual(cm.exception.code, 'no_transactions')

    def test_unsupported_type(self):
        with self.assertRaises(StatementExtractionError):
            extract_statement(self.dir / 'a.xls', 'xls')

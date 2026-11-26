from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from processing.csv_extractor import read_csv
from processing.exceptions import StatementExtractionError
from processing.normalizer import normalize

from .helpers import FIXTURES


def run(data: bytes):
    return normalize(read_csv(data))


class RealisticCsvTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.result = run((FIXTURES / 'gtb_style.csv').read_bytes())
        cls.txs = cls.result.transactions

    def test_preamble_skipped_and_all_transactions_found(self):
        self.assertEqual(len(self.txs), 7)
        self.assertEqual(self.result.rejected, [])
        self.assertEqual(self.result.skipped_rows, 1)  # the "Total" row is not a transaction
        self.assertEqual(self.result.currency, 'NGN')

    def test_outgoing_with_narration(self):
        t = self.txs[0]
        self.assertEqual((t.date, t.debit, t.credit), (date(2025, 9, 3), Decimal('15000.00'), None))
        self.assertEqual((t.recipient, t.narration, t.reference), ('AHMED MUSA', 'School fees', 'REF0001'))
        self.assertTrue(t.is_outgoing)

    def test_missing_narration_is_empty_string(self):
        t = self.txs[1]
        self.assertEqual(t.recipient, 'AHMED MUSA')
        self.assertEqual(t.narration, '')

    def test_incoming_transaction(self):
        t = self.txs[2]
        self.assertEqual((t.debit, t.credit), (None, Decimal('50000.00')))
        self.assertEqual((t.sender, t.recipient, t.narration), ('GRACE OKAFOR', None, 'rent'))
        self.assertFalse(t.is_outgoing)

    def test_multiple_to_same_recipient(self):
        names = [t.recipient for t in self.txs if (t.recipient or '').casefold() == 'ahmed musa']
        self.assertEqual(len(names), 3)

    def test_missing_recipient_is_none_and_narration_empty(self):
        for idx in (4, 6):  # POS purchase, airtime
            self.assertIsNone(self.txs[idx].recipient)
            self.assertEqual(self.txs[idx].narration, '')
            self.assertIsNotNone(self.txs[idx].debit)

    def test_description_preserved_verbatim(self):
        self.assertEqual(self.txs[4].description, 'POS PURCHASE SHOPRITE ABUJA')

    def test_the_statements_stated_period_is_read_from_the_preamble(self):
        self.assertEqual((self.result.period_start, self.result.period_end), (date(2025, 9, 1), date(2025, 9, 30)))

    def test_currency_set_on_transactions(self):
        self.assertTrue(all(t.currency == 'NGN' for t in self.txs))


class CsvVariantTests(SimpleTestCase):
    def test_signed_amount_semicolon_european_format(self):
        r = normalize(read_csv((FIXTURES / 'signed_amount.csv').read_bytes()))
        self.assertEqual([(t.debit, t.credit) for t in r.transactions],
                         [(Decimal('15000.00'), None), (None, Decimal('50000.00'))])
        self.assertEqual(r.transactions[0].currency, 'NGN')

    def test_amount_plus_type_column(self):
        r = run(b'Date,Details,Amount,Type\n2025-09-03,Transfer to Ahmed Musa,"1,000.00",DR\n2025-09-04,Transfer from Bola,200.00,CR\n')
        self.assertEqual([t.is_outgoing for t in r.transactions], [True, False])

    def test_unsigned_amount_without_direction_is_rejected_not_guessed(self):
        r = run(b'Date,Description,Amount\n2025-09-03,Transfer to Ahmed Musa,1000.00\n')
        self.assertEqual(r.transactions, [])
        self.assertEqual([x.reason for x in r.rejected], ['unknown_direction'])

    def test_separate_narration_column_and_beneficiary_column(self):
        r = run(b'Date,Description,Beneficiary,Remarks,Debit,Credit\n03/09/2025,NIP TRANSFER,Ahmed Musa,School fees,"1,000.00",\n')
        t = r.transactions[0]
        self.assertEqual((t.recipient, t.narration), ('Ahmed Musa', 'School fees'))

    def test_different_date_and_amount_formats_in_one_file(self):
        r = run(b'Date,Description,Debit,Credit\n03-Sep-2025,A,\"NGN 1,000.00\",\n2025-09-04,B,\"\xe2\x82\xa62,500\",\n05/09/2025,C,"(300.00)",\n')
        self.assertEqual([t.date for t in r.transactions], [date(2025, 9, 3), date(2025, 9, 4), date(2025, 9, 5)])
        self.assertEqual([t.debit for t in r.transactions], [Decimal('1000.00'), Decimal('2500.00'), Decimal('300.00')])

    def test_garbled_and_invalid_rows_rejected_but_valid_kept(self):
        data = (b'Date,Description,Debit,Credit\n'
                b'03/09/2025,Good,"1,000.00",\n'
                b'not-a-date,Bad date,500.00,\n'
                b'04/09/2025,Bad amount,abc,\n'
                b'05/09/2025,Both,100.00,100.00\n'
                b'06/09/2025,No amount,,\n'
                b'31/02/2025,Impossible date,10.00,\n')
        r = run(data)
        self.assertEqual(len(r.transactions), 1)
        self.assertEqual(sorted(x.reason for x in r.rejected),
                         ['ambiguous_direction', 'invalid_amount', 'invalid_date', 'invalid_date', 'no_amount'])

    def test_wrapped_description_lines_are_joined(self):
        r = run(b'Date,Description,Debit,Credit\n03/09/2025,TRANSFER TO AHMED,"1,000.00",\n,MUSA,,\n')
        self.assertEqual(r.transactions[0].description, 'TRANSFER TO AHMED MUSA')
        self.assertEqual(r.transactions[0].recipient, 'AHMED MUSA')

    def test_misquoted_row_with_extra_cells_is_rejected_not_misread(self):
        r = run(b'Date,Description,Debit,Credit\n03/09/2025,A,1,000.00,\n04/09/2025,B,5.00,\n')
        self.assertEqual(len(r.transactions), 1)
        self.assertEqual([x.reason for x in r.rejected], ['column_mismatch'])

    def test_zero_amount_rejected(self):
        r = run(b'Date,Description,Debit,Credit\n03/09/2025,X,0.00,0.00\n04/09/2025,Y,5.00,\n')
        self.assertEqual(len(r.transactions), 1)

    def test_encodings_and_bom(self):
        data = '\ufeffDate,Description,Debit,Credit\n03/09/2025,Transfer to Chidi Électricals,"1,000.00",\n'.encode('utf-8')
        self.assertEqual(run(data).transactions[0].recipient, 'Chidi Électricals')
        latin = 'Date,Description,Debit,Credit\n03/09/2025,Caf\xe9,"1,000.00",\n'.encode('latin-1')
        self.assertEqual(len(run(latin).transactions), 1)

    def test_no_header_raises(self):
        with self.assertRaises(StatementExtractionError) as cm:
            read_csv(b'hello,world\n1,2\n')
        self.assertEqual(cm.exception.code, 'csv_no_header')


class DuplicateTests(SimpleTestCase):
    def test_same_row_with_same_reference_or_balance_is_duplicate(self):
        row = b'03/09/2025,TRF TO AHMED MUSA,"1,000.00",,"9,000.00",R1\n'
        r = run(b'Date,Description,Debit,Credit,Balance,Reference\n' + row + row)
        self.assertEqual(len(r.transactions), 1)
        self.assertEqual(r.duplicates_removed, 1)

    def test_identical_payments_without_reference_or_balance_are_kept(self):
        row = b'03/09/2025,TRF TO AHMED MUSA,"1,000.00",\n'
        r = run(b'Date,Description,Debit,Credit\n' + row + row)
        self.assertEqual(len(r.transactions), 2)
        self.assertEqual(r.duplicates_removed, 0)

    def test_same_amount_different_balance_is_not_duplicate(self):
        d = (b'Date,Description,Debit,Credit,Balance\n'
             b'03/09/2025,TRF TO AHMED MUSA,"1,000.00",,"9,000.00"\n'
             b'03/09/2025,TRF TO AHMED MUSA,"1,000.00",,"8,000.00"\n')
        self.assertEqual(len(run(d).transactions), 2)

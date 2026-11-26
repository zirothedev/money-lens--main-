"""End to end: a GTBank-style PDF (anonymised) -> names, via, narration, currency, period, reconciliation."""
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

from processing.pipeline import extract_statement
from processing.tests import helpers
from reports.engine import build_report_data

ENTRIES = [
    ('01-Aug-2026', "'296960FOS", '1,050.00', '', 'Cash withdrawal by Self via POS POS PUR T JANE ROE FiZOFB 20338BOD LANG 296960 260801FiZOFB 20338BOD539983*********6603'),
    ('01-Aug-2026', "'GTW", '2,500.00', '', 'Instant Payment Outward 000013260801112746000108527582 NIP TRANSFER TO OPAY - ADA OBI'),
    ('01-Aug-2026', "'GTW", '500.00', '', 'Instant Payment Outward 000013260801115547000108527999 NIP TRANSFER TO MOMO - TEST USER ONE'),
    ('01-Aug-2026', "'6422580686AIR", '200.00', '', 'Airtime Purchase VIA AIRTIME VIA GTWORLD 101CT0000000006422580686-2347044197672-AIRTIME FROM TEST , USER ONE TO MTN AIRTIME COLLECTION SALES'),
    ('02-Aug-2026', "'9999992608020503 4161NIP", '50.00', '', 'NIPS DIRECT DEBIT VIA NIP 999999260802050341614248944559NIPMINI/09056 72608020503415504 51237897/MONT:FROM TEST USER ONE TO MONO TECHNOLOGIES NIGER76389542 8231: - SCHEDULED PIGGYBANK AUTOSAVE DEBI'),
    ('02-Aug-2026', "'0000162026080120 0938NIP", '', '10,000.00', 'TRANSFER BETWEEN CUSTOMERS 00001620260801200938002464944043001-TEST USER ONE/NONE-FBN-JOHN DOE .'),
    ('03-Aug-2026', "'857546FOS", '4,100.00', '', 'POSWEB PURCHASE TRANSACTION POS PUR OPAY KURE BUSINESS ENTEBauchi BANG 857546 001776099175 4001LUJW539983*********6603'),
    ('03-Aug-2026', "'398973FEB", '50.00', '', 'POSWEB PURCHASE TRANSACTION WEB PUR 3PG00001 PIGG Y EST LANG 398973 GIPS MRA4FY 3PG00001539983*********6603'),
    ('03-Aug-2026', "'785224FEB", '50.00', '', 'POSWEB PURCHASE TRANSACTION WEB PUR 3PG00001 PI GG VEST LANG 785224 GIPS MRWU8L 3PG00001539983*********6603'),
    ('03-Aug-2026', "'040630FEB", '50.00', '', 'POSWEB PURCHASE TRANSACTION WEB PUR 3PG00001 PIGG Y EST LANG 040630 GIPS MSC32B 3PG00001539983*********6603'),
    ('04-Aug-2026', "'GTW", '1,000.00', '', 'Instant Payment Outward 000013260909192109000082407401 ICE CREAM TO KMB - MARY OKON'),
    ('04-Aug-2026', "'GTW", '700.00', '', 'Instant Payment Outward 000013260804125620000008825554 NIP TRANSFER TO OPAY - ADA OBI'),
]


class GtcoStylePdfTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.dir = Path(tempfile.mkdtemp())
        cls.path = cls.dir / 'gtco.pdf'
        cls.printed = helpers.build_gtco_style_pdf(cls.path, ENTRIES)
        cls.result = extract_statement(cls.path, 'pdf')
        cls.txs = cls.result.transactions

    def test_every_row_is_read_and_reconciles_with_the_totals_the_statement_prints(self):
        self.assertEqual(len(self.txs), len(ENTRIES))
        self.assertEqual(self.result.rejected, [])
        self.assertEqual(sum((t.debit for t in self.txs if t.debit), Decimal(0)), self.printed['total_debit'])
        self.assertEqual(sum((t.credit for t in self.txs if t.credit), Decimal(0)), self.printed['total_credit'])

    def test_currency_comes_from_the_statement_header(self):
        self.assertEqual(self.result.currency, 'NGN')
        self.assertTrue(all(t.currency == 'NGN' for t in self.txs))

    def test_the_statements_own_period_is_read(self):
        self.assertEqual((self.result.period_start, self.result.period_end), (date(2026, 8, 1), date(2026, 9, 26)))

    def test_no_outgoing_transaction_is_left_unidentified(self):
        self.assertEqual([t.description[:60] for t in self.txs if t.debit and not t.recipient], [])

    def test_names_and_via(self):
        by_ref = {i: t for i, t in enumerate(self.txs)}
        self.assertEqual(by_ref[0].recipient, 'JANE ROE')
        self.assertEqual((by_ref[1].recipient, by_ref[1].via), ('ADA OBI', 'OPAY'))
        self.assertEqual((by_ref[2].recipient, by_ref[2].via), ('TEST USER ONE', 'MOMO'))
        self.assertEqual(by_ref[3].recipient, 'MTN AIRTIME COLLECTION SALES')
        self.assertEqual((by_ref[4].recipient, by_ref[4].narration), ('MONO TECHNOLOGIES NIGER', 'SCHEDULED PIGGYBANK AUTOSAVE DEBI'))
        self.assertEqual(by_ref[6].recipient, 'OPAY KURE BUSINESS ENTE')
        self.assertEqual((by_ref[10].recipient, by_ref[10].via, by_ref[10].narration), ('MARY OKON', 'KMB', 'ICE CREAM'))

    def test_the_bank_name_is_never_the_recipient(self):
        banks = {'OPAY', 'MOMO', 'KMB', 'FCMB', 'MONIEMFB', 'SMARTCASH', 'PALMPAY'}
        self.assertFalse({t.recipient for t in self.txs} & banks)

    def test_garbled_merchant_spellings_become_one_recipient(self):
        piggy = {t.recipient for t in self.txs if t.merchant_id == '3PG00001'}
        self.assertEqual(piggy, {'PIGG Y EST'})                    # the most common written spelling (2 of 3)

    def test_missing_narration_is_empty_not_a_placeholder(self):
        self.assertEqual(self.txs[1].narration, '')
        self.assertEqual(self.txs[6].narration, '')

    def test_report_ranks_real_people_and_merchants(self):
        report = build_report_data(self.txs, stated_period=(self.result.period_start, self.result.period_end))
        names = [r.name for r in report.recipients]
        self.assertEqual(report.unidentified_count, 0)
        self.assertEqual(names[0], 'OPAY KURE BUSINESS ENTE')       # 4,100 is the largest single recipient
        self.assertIn('ADA OBI', names)
        ada = next(r for r in report.recipients if r.name == 'ADA OBI')
        self.assertEqual((ada.transaction_count, ada.total_sent), (2, Decimal('3200.00')))   # two different transfers, one person
        self.assertEqual((report.period_start, report.period_end), (date(2026, 8, 1), date(2026, 9, 26)))
        self.assertEqual(report.currency, 'NGN')
        self.assertEqual(report.total_sent, self.printed['total_debit'])

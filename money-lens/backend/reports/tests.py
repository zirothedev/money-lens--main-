import random
import shutil
import tempfile
from unittest import mock
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import Http404
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from processing.exceptions import StatementExtractionError
from processing.schema import NormalizedTransaction
from reports import services
from reports.engine import ReportError, build_report_data
from reports.models import Report, ReportRecipient, ReportTransaction
from statements import services as statement_services
from statements.models import StatementProcessing

D = Decimal


def out(day, amount, recipient=None, narration='', **kw):
    return NormalizedTransaction(date=date(2025, 9, day), description=f'TRF {recipient}', debit=D(amount),
                                 credit=None, recipient=recipient, narration=narration, **kw)


def inc(day, amount, sender=None, narration='', **kw):
    return NormalizedTransaction(date=date(2025, 9, day), description=f'FROM {sender}', debit=None,
                                 credit=D(amount), recipient=None, sender=sender, narration=narration, **kw)


class EngineTests(SimpleTestCase):
    def test_spec_example_aggregation(self):
        r = build_report_data([out(1, '20000', 'Ahmed Musa'), out(2, '30000', 'Ahmed Musa'), out(3, '50000', 'Ahmed Musa')])
        self.assertEqual(len(r.recipients), 1)
        top = r.recipients[0]
        self.assertEqual((top.name, top.total_sent, top.transaction_count, top.rank), ('Ahmed Musa', D('100000.00'), 3, 1))

    def test_totals_and_counts_incoming_vs_outgoing(self):
        r = build_report_data([inc(1, '500000', 'Employer'), inc(2, '1000.50'), out(3, '15000', 'A'), out(4, '2500.25')])
        self.assertEqual((r.total_received, r.incoming_count), (D('501000.50'), 2))
        self.assertEqual((r.total_sent, r.outgoing_count), (D('17500.25'), 2))

    def test_incoming_senders_never_become_recipients(self):
        r = build_report_data([inc(1, '100', 'Grace Okafor'), out(2, '50', 'Ahmed')])
        self.assertEqual([x.name for x in r.recipients], ['Ahmed'])

    def test_recipient_ranking_by_total_with_deterministic_ties(self):
        r = build_report_data([out(1, '10', 'Zed'), out(2, '10', 'Amy'), out(3, '500', 'Big'), out(4, '30', 'Mid')])
        self.assertEqual([x.name for x in r.recipients], ['Big', 'Mid', 'Amy', 'Zed'])
        self.assertEqual([x.rank for x in r.recipients], [1, 2, 3, 4])

    def test_tie_on_total_broken_by_count(self):
        r = build_report_data([out(1, '50', 'Few'), out(2, '25', 'Many'), out(3, '25', 'Many')])
        self.assertEqual([x.name for x in r.recipients], ['Many', 'Few'])

    def test_multiple_recipients_counts(self):
        r = build_report_data([out(1, '100', 'Ahmed Musa')] * 8 + [out(2, '65000', 'Grace Okafor')] * 5)
        counts = {x.name: x.transaction_count for x in r.recipients}
        self.assertEqual(counts, {'Ahmed Musa': 8, 'Grace Okafor': 5})

    def test_unidentified_recipients(self):
        r = build_report_data([out(1, '10000.00'), out(2, '8500.00'), out(3, '100', 'Ahmed')])
        self.assertEqual((r.unidentified_total, r.unidentified_count), (D('18500.00'), 2))
        self.assertEqual(r.recipients[0].total_sent, D('100.00'))  # not mixed into named recipients
        self.assertEqual(r.total_sent, D('18600.00'))             # but still counted in total sent

    def test_no_unidentified_means_zero(self):
        r = build_report_data([out(1, '10', 'A')])
        self.assertEqual((r.unidentified_total, r.unidentified_count), (D('0.00'), 0))

    def test_empty_narration_stays_empty(self):
        r = build_report_data([out(1, '10', 'A'), out(2, '10', 'A', narration='School fees')])
        self.assertEqual([t.narration for t in r.recipients[0].transactions], ['', 'School fees'])
        self.assertEqual([t.narration for t in r.transactions], ['', 'School fees'])

    def test_decimal_accuracy(self):
        r = build_report_data([out(1, '0.10', 'A'), out(2, '0.20', 'A'), inc(3, '0.10'), inc(4, '0.20')])
        self.assertEqual(r.total_sent, D('0.30'))
        self.assertEqual(r.total_received, D('0.30'))
        big = build_report_data([out(1, '9999999999.99', 'A'), out(2, '0.01', 'A')])
        self.assertEqual(big.total_sent, D('10000000000.00'))
        self.assertIsInstance(big.total_sent, Decimal)

    def test_recipient_case_and_spacing_grouped(self):
        r = build_report_data([out(1, '10', 'AHMED MUSA'), out(2, '10', 'Ahmed  Musa'), out(3, '10', 'AHMED MUSA')])
        self.assertEqual(len(r.recipients), 1)
        self.assertEqual((r.recipients[0].name, r.recipients[0].transaction_count), ('AHMED MUSA', 3))

    def test_period_and_currency(self):
        r = build_report_data([out(20, '1', 'A', currency='NGN'), out(3, '1', 'A', currency='NGN')])
        self.assertEqual((r.period_start, r.period_end, r.currency), (date(2025, 9, 3), date(2025, 9, 20), 'NGN'))

    def test_mixed_currencies_refused(self):
        with self.assertRaises(ReportError) as cm:
            build_report_data([out(1, '1', 'A', currency='NGN'), out(2, '1', 'A', currency='USD')])
        self.assertEqual(cm.exception.code, 'multiple_currencies')

    def test_empty_refused(self):
        with self.assertRaises(ReportError):
            build_report_data([])

    def test_deterministic_regardless_of_input_order(self):
        txs = [out(d, str(d * 7), f'R{d % 3}') for d in range(1, 20)] + [inc(5, '999')]
        baseline = build_report_data(txs)
        for seed in range(5):
            shuffled = txs[:]
            random.Random(seed).shuffle(shuffled)
            self.assertEqual(build_report_data(shuffled), baseline)


class PersistenceTestCase(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        o = override_settings(PRIVATE_UPLOAD_ROOT=Path(self.tmp))
        o.enable()
        self.addCleanup(o.disable)
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.alice = User.objects.create_user('alice', password='x')
        self.bob = User.objects.create_user('bob', password='x')

    CSV = (b'Date,Description,Debit,Credit,Balance\n'
           b'03/09/2025,NIP TRANSFER TO AHMED MUSA/School fees,"15,000.00",,"985,000.00"\n'
           b'08/09/2025,TRF TO AHMED MUSA,"10,000.00",,"975,000.00"\n'
           b'09/09/2025,NIP TRANSFER FROM GRACE OKAFOR,,"50,000.00","1,025,000.00"\n'
           b'10/09/2025,POS PURCHASE SHOPRITE,"4,500.00",,"1,020,500.00"\n')

    def upload(self, user=None, data=None):
        return statement_services.create_statement_job(
            user or self.alice, SimpleUploadedFile('s.csv', data or self.CSV, content_type='text/csv'))

    def files(self):
        return list(Path(self.tmp).iterdir())


class GenerationTests(PersistenceTestCase):
    def test_full_lifecycle_report_saved_and_temporaries_deleted(self):
        job = self.upload()
        self.assertEqual(len(self.files()), 1)
        report = services.generate_report_for_job(job)

        self.assertEqual(self.files(), [])                                    # physical file gone
        self.assertFalse(StatementProcessing.objects.filter(pk=job.pk).exists())  # temp record gone
        self.assertEqual((report.total_sent, report.total_received), (D('29500.00'), D('50000.00')))
        self.assertEqual((report.outgoing_count, report.incoming_count), (3, 1))
        self.assertEqual((report.unidentified_total, report.unidentified_count), (D('4500.00'), 1))
        r = report.recipients.get()
        self.assertEqual((r.name, r.total_sent, r.transaction_count, r.rank), ('AHMED MUSA', D('25000.00'), 2, 1))

    def test_report_persists_independently_of_statement(self):
        report = services.generate_report_for_job(self.upload())
        fresh = services.get_report_for_user(self.alice, report.id)
        self.assertEqual(fresh.transactions.count(), 4)
        self.assertEqual(len(services.report_to_dict(fresh)['transactions']), 4)
        self.assertEqual(list(services.list_reports_for_user(self.alice)), [report])

    def test_persisted_transactions_keep_empty_narration_and_none_recipient(self):
        report = services.generate_report_for_job(self.upload())
        txs = {t.date: t for t in report.transactions.all()}
        self.assertEqual(txs[date(2025, 9, 3)].narration, 'School fees')
        self.assertEqual(txs[date(2025, 9, 8)].narration, '')
        pos = txs[date(2025, 9, 10)]
        self.assertIsNone(pos.counterparty)
        self.assertIsNone(pos.recipient)
        self.assertEqual(txs[date(2025, 9, 9)].direction, 'in')
        self.assertEqual(txs[date(2025, 9, 9)].counterparty, 'GRACE OKAFOR')

    def test_recipient_detail_transactions_linked(self):
        report = services.generate_report_for_job(self.upload())
        data = services.report_to_dict(report)
        self.assertEqual([t['amount'] for t in data['recipients'][0]['transactions']], ['15000.00', '10000.00'])
        self.assertEqual([t['narration'] for t in data['recipients'][0]['transactions']], ['School fees', ''])

    def test_no_original_statement_content_stored_in_report_tables(self):
        report = services.generate_report_for_job(self.upload())
        blob = ' '.join(str(v) for t in report.transactions.values() for v in t.values())
        self.assertNotIn('NIP TRANSFER', blob)  # raw descriptions are not retained
        self.assertNotIn('985,000', blob)       # nor balances

    def test_duplicate_statement_returns_same_report(self):
        first = services.generate_report_for_job(self.upload())
        second = services.generate_report_for_job(self.upload())
        self.assertEqual(first.id, second.id)
        self.assertEqual(Report.objects.count(), 1)
        self.assertEqual(ReportTransaction.objects.count(), 4)
        self.assertEqual(self.files(), [])  # the second upload's temporaries are still cleaned up

    def test_same_statement_for_two_users_gives_two_reports(self):
        a = services.generate_report_for_job(self.upload(self.alice))
        b = services.generate_report_for_job(self.upload(self.bob))
        self.assertNotEqual(a.id, b.id)

    def test_user_data_isolation(self):
        report = services.generate_report_for_job(self.upload(self.alice))
        with self.assertRaises(Http404):
            services.get_report_for_user(self.bob, report.id)
        self.assertEqual(list(services.list_reports_for_user(self.bob)), [])
        self.client.force_login(self.bob)
        self.assertEqual(self.client.get(reverse('reports:data', args=[report.id])).status_code, 404)
        self.assertEqual(self.client.get(reverse('reports:list')).json(), {'reports': []})
        self.client.force_login(self.alice)
        self.assertEqual(self.client.get(reverse('reports:data', args=[report.id])).status_code, 200)

    def test_report_endpoints_require_login(self):
        report = services.generate_report_for_job(self.upload())
        self.assertEqual(self.client.get(reverse('reports:data', args=[report.id])).status_code, 302)

    def test_double_processing_blocked(self):
        job = self.upload()
        services.generate_report_for_job(job)
        stale = StatementProcessing(pk=job.pk)
        with self.assertRaises(services.ProcessingNotAllowed):
            services.generate_report_for_job(stale)

    def test_job_already_processing_is_not_started_twice(self):
        job = self.upload()
        StatementProcessing.objects.filter(pk=job.pk).update(status='processing')
        with self.assertRaises(services.ProcessingNotAllowed):
            services.generate_report_for_job(job)

    def test_expired_job_not_processed(self):
        job = self.upload()
        StatementProcessing.objects.filter(pk=job.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        with self.assertRaises(services.ProcessingNotAllowed):
            services.generate_report_for_job(job)
        self.assertEqual(self.files(), [])
        self.assertEqual(Report.objects.count(), 0)

    def test_extraction_failure_marks_failed_and_removes_file_but_creates_no_report(self):
        job = self.upload(data=b'Date,Description,Debit,Credit\nbad,x,1.00,\n')
        with self.assertRaises(StatementExtractionError):
            services.generate_report_for_job(job)
        job.refresh_from_db()
        self.assertEqual((job.status, job.error_code, job.temp_file_name), ('failed', 'no_transactions', ''))
        self.assertEqual(self.files(), [])
        self.assertEqual(Report.objects.count(), 0)

    def test_failed_job_record_is_removed_on_expiry(self):
        job = self.upload(data=b'Date,Description,Debit,Credit\nbad,x,1.00,\n')
        with self.assertRaises(StatementExtractionError):
            services.generate_report_for_job(job)
        StatementProcessing.objects.filter(pk=job.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        statement_services.cleanup_expired_jobs()
        self.assertFalse(StatementProcessing.objects.exists())

    def test_mixed_currency_statement_fails_cleanly(self):
        data = b'Date,Description,Debit,Credit,Currency\n03/09/2025,TRF TO A,1.00,,NGN\n04/09/2025,TRF TO B,1.00,,USD\n'
        job = self.upload(data=data)
        with self.assertRaises(ReportError):
            services.generate_report_for_job(job)
        job.refresh_from_db()
        self.assertEqual(job.error_code, 'multiple_currencies')
        self.assertEqual(self.files(), [])

    def test_missing_package_is_named_in_the_log_but_not_shown_to_the_user(self):
        import sys
        job = self.upload()
        sys.modules['pdfplumber'] = None   # makes `import pdfplumber` raise ModuleNotFoundError
        self.addCleanup(sys.modules.pop, 'pdfplumber', None)
        pdf_job = statement_services.create_statement_job(
            self.alice, SimpleUploadedFile('s.pdf', b'%PDF-1.4 x', content_type='application/pdf'))
        with self.assertLogs('reports.services', level='ERROR') as logs:
            with self.assertRaises(ImportError):
                services.generate_report_for_job(pdf_job)
        self.assertIn('missing package: pdfplumber', logs.output[0])
        self.client.force_login(self.alice)
        pdf_job2 = statement_services.create_statement_job(
            self.alice, SimpleUploadedFile('t.pdf', b'%PDF-1.4 y', content_type='application/pdf'))
        r = Client(raise_request_exception=False)
        r.force_login(self.alice)
        resp = r.post(reverse('statements:process', args=[pdf_job2.id]))
        self.assertEqual(resp.status_code, 500)
        self.assertNotIn('pdfplumber', resp.content.decode())   # users never see internals

    def test_failure_during_saving_leaves_no_partial_report(self):
        from unittest import mock
        job = self.upload()
        with mock.patch('reports.services.ReportTransaction.objects.bulk_create', side_effect=RuntimeError('boom')):
            with self.assertRaises(RuntimeError):
                services.generate_report_for_job(job)
        self.assertEqual((Report.objects.count(), ReportRecipient.objects.count()), (0, 0))  # rolled back
        job.refresh_from_db()
        self.assertEqual(job.status, 'failed')
        self.assertEqual(self.files(), [])


class ProcessEndpointTests(PersistenceTestCase):
    def test_upload_process_fetch_flow(self):
        self.client.force_login(self.alice)
        up = self.client.post(reverse('statements:upload'),
                              {'statement': SimpleUploadedFile('s.csv', self.CSV, content_type='text/csv')})
        job_id = up.json()['id']
        done = self.client.post(reverse('statements:process', args=[job_id]))
        self.assertEqual(done.status_code, 200)
        data = self.client.get(reverse('reports:data', args=[done.json()['report_id']])).json()
        self.assertEqual((data['total_sent'], data['total_received']), ('29500.00', '50000.00'))
        self.assertEqual(data['unidentified'], {'total_sent': '4500.00', 'transaction_count': 1})
        self.assertEqual(data['recipients'][0]['name'], 'AHMED MUSA')
        self.assertEqual(self.files(), [])
        # the temporary job no longer exists
        self.assertEqual(self.client.get(reverse('statements:status', args=[job_id])).status_code, 404)

    def test_cannot_process_another_users_job(self):
        job = self.upload(self.alice)
        self.client.force_login(self.bob)
        self.assertEqual(self.client.post(reverse('statements:process', args=[job.id])).status_code, 404)
        job.refresh_from_db()
        self.assertEqual(job.status, 'uploaded')
        self.assertEqual(len(self.files()), 1)

    def test_processing_twice_returns_404_or_409_never_two_reports(self):
        self.client.force_login(self.alice)
        job = self.upload()
        self.assertEqual(self.client.post(reverse('statements:process', args=[job.id])).status_code, 200)
        self.assertEqual(self.client.post(reverse('statements:process', args=[job.id])).status_code, 404)
        self.assertEqual(Report.objects.count(), 1)

    def test_bad_statement_returns_422_with_code(self):
        self.client.force_login(self.alice)
        job = self.upload(data=b'Date,Description,Debit,Credit\nbad,x,1.00,\n')
        r = self.client.post(reverse('statements:process', args=[job.id]))
        self.assertEqual((r.status_code, r.json()['error']), (422, 'no_transactions'))

    def test_get_not_allowed(self):
        self.client.force_login(self.alice)
        job = self.upload()
        self.assertEqual(self.client.get(reverse('statements:process', args=[job.id])).status_code, 405)


class StatedPeriodAndParserVersionTests(SimpleTestCase):
    def txs(self):
        return [out(5, '10', 'A'), out(9, '10', 'A')]

    def test_statement_period_is_used_when_it_covers_every_transaction(self):
        r = build_report_data(self.txs(), stated_period=(date(2025, 9, 1), date(2025, 9, 30)))
        self.assertEqual((r.period_start, r.period_end), (date(2025, 9, 1), date(2025, 9, 30)))

    def test_statement_period_is_ignored_if_a_transaction_falls_outside_it(self):
        r = build_report_data(self.txs(), stated_period=(date(2025, 9, 6), date(2025, 9, 30)))
        self.assertEqual((r.period_start, r.period_end), (date(2025, 9, 5), date(2025, 9, 9)))

    def test_without_a_stated_period_it_is_derived_as_before(self):
        r = build_report_data(self.txs())
        self.assertEqual((r.period_start, r.period_end), (date(2025, 9, 5), date(2025, 9, 9)))

    def test_fingerprint_depends_on_the_parser_version(self):
        from reports import engine
        a = build_report_data(self.txs()).fingerprint
        with mock.patch.object(engine, 'PARSER_VERSION', 'next'):
            b = build_report_data(self.txs()).fingerprint
        self.assertNotEqual(a, b)
        self.assertEqual(a, build_report_data(self.txs()).fingerprint)    # stable for the same version


class ViaPersistenceTests(PersistenceTestCase):
    NIP_CSV = (b'Date,Description,Debit (NGN),Credit (NGN),Balance,Reference\n'
               b'03/09/2025,Instant Payment Outward 000013260801112746000108527582 NIP TRANSFER TO OPAY - ADA OBI,"2,500.00",,"97,500.00",R1\n'
               b'04/09/2025,Instant Payment Outward 000013260804112746000108527583 NIP TRANSFER TO MOMO - ADA OBI,"500.00",,"97,000.00",R2\n')

    def make_report(self, data=None):
        return services.generate_report_for_job(self.upload(data=data))

    def test_the_person_is_the_recipient_and_the_bank_is_stored_as_via(self):
        report = self.make_report(data=self.NIP_CSV)
        recipient = report.recipients.get()
        self.assertEqual((recipient.name, recipient.transaction_count, recipient.total_sent), ('ADA OBI', 2, Decimal('3000.00')))
        self.assertEqual(sorted(report.transactions.values_list('via', flat=True)), ['MOMO', 'OPAY'])

    def test_via_is_shown_on_the_report_page_and_in_the_json(self):
        report = self.make_report(data=self.NIP_CSV)
        self.client.force_login(self.alice)
        page = self.client.get(reverse('reports:detail', args=[report.id])).content.decode()
        self.assertIn('<span class="tx__via">via OPAY</span>', page)
        self.assertIn('<span class="tx__via">via MOMO</span>', page)
        self.assertNotIn('data-testid="recipient"> OPAY', page)
        data = self.client.get(reverse('reports:data', args=[report.id])).json()
        self.assertEqual({t['via'] for t in data['transactions']}, {'OPAY', 'MOMO'})

    def test_statements_without_a_bank_in_the_text_have_no_via(self):
        report = self.make_report()
        self.assertEqual(set(report.transactions.values_list('via', flat=True)), {''})
        self.client.force_login(self.alice)
        self.assertNotIn('tx__via">', self.client.get(reverse('reports:detail', args=[report.id])).content.decode())

    def test_reuploading_after_a_parser_upgrade_creates_a_fresh_report(self):
        from reports import engine
        first = self.make_report(data=self.NIP_CSV)
        same = self.make_report(data=self.NIP_CSV)
        self.assertEqual(first.id, same.id)                         # same parser: duplicate protection still works
        with mock.patch.object(engine, 'PARSER_VERSION', 'upgraded'):
            newer = self.make_report(data=self.NIP_CSV)
        self.assertNotEqual(first.id, newer.id)

"""Phase 5: the HTML report pages render real backend data and enforce access rules."""
import re
import shutil
import tempfile
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from reports import services
from reports.models import Report, ReportRecipient, ReportTransaction
from reports.presenters import currency_symbol, format_period
from reports.templatetags.report_extras import money, short_date
from statements import services as statement_services

CSV = (b'Date,Description,Debit (NGN),Credit (NGN),Balance,Reference\n'
       b'03/09/2025,NIP TRANSFER TO AHMED MUSA/School fees,"15,000.00",,"985,000.00",R1\n'
       b'08/09/2025,TRF TO AHMED MUSA,"10,000.00",,"975,000.00",R2\n'
       b'09/09/2025,NIP TRANSFER FROM GRACE OKAFOR,,"50,000.00","1,025,000.00",R3\n'
       b'10/09/2025,POS PURCHASE SHOPRITE,"4,500.00",,"1,020,500.00",R4\n')

PLACEHOLDERS = ['No narration', 'Purpose unknown', 'Unknown', 'Personal', 'Other', 'N/A']


class PageTestCase(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        o = override_settings(PRIVATE_UPLOAD_ROOT=Path(self.tmp))
        o.enable()
        self.addCleanup(o.disable)
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.alice = User.objects.create_user('alice', password='x')
        self.bob = User.objects.create_user('bob', password='x')

    def make_report(self, user=None, data=CSV):
        job = statement_services.create_statement_job(
            user or self.alice, SimpleUploadedFile('s.csv', data, content_type='text/csv'))
        return services.generate_report_for_job(job)

    def html(self, response):
        return response.content.decode()


class ReportPageContentTests(PageTestCase):
    def setUp(self):
        super().setUp()
        self.report = self.make_report()
        self.client.force_login(self.alice)
        self.response = self.client.get(reverse('reports:detail', args=[self.report.id]))
        self.page = self.html(self.response)

    def test_renders_with_header_period_and_intro(self):
        self.assertEqual(self.response.status_code, 200)
        self.assertIn("Where'd My Money Go?</h1>", self.page)
        self.assertIn('September 2025', self.page)
        self.assertIn('where your money went in September 2025', self.page)

    def test_totals_come_from_the_saved_report(self):
        self.assertRegex(self.page, r'data-testid="total-received">₦50,000<')
        self.assertRegex(self.page, r'data-testid="total-sent">₦29,500<')
        self.assertIn('1 transaction</p>', self.page)   # singular for received
        self.assertIn('3 transactions</p>', self.page)

    def test_recipient_ranked_with_total_and_count(self):
        self.assertIn('AHMED MUSA', self.page)
        self.assertIn('2 transactions', self.page)
        self.assertIn('₦25,000', self.page)
        self.assertEqual(self.page.count('data-testid="recipient"'), 1)

    def test_recipient_detail_rows_and_empty_narration_stays_empty(self):
        details = re.search(r'id="rcpt-1".*?</table>', self.page, re.S).group(0)
        rows = re.findall(r'<tr><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td></tr>', details)
        self.assertEqual(rows, [('03 Sep', '₦15,000', 'School fees'), ('08 Sep', '₦10,000', '')])

    def test_no_placeholder_text_replaces_missing_narration(self):
        for text in PLACEHOLDERS:
            self.assertNotIn(text, self.page, text)

    def test_unidentified_section(self):
        self.assertIn('Unidentified recipients', self.page)
        self.assertRegex(self.page, r'data-testid="unidentified-count">1 transaction<')
        self.assertRegex(self.page, r'data-testid="unidentified-total">₦4,500<')
        self.assertIn("doesn't give enough information to identify the recipient", self.page.replace('&#x27;', "'"))

    def test_all_transactions_listed_with_direction_and_sign(self):
        self.assertEqual(self.page.count('data-tx-row'), 4)
        self.assertEqual(self.page.count('pill pill--in'), 1)
        self.assertEqual(self.page.count('pill pill--out'), 3)
        self.assertIn('+₦50,000', self.page)
        self.assertIn('−₦15,000', self.page)
        self.assertIn('from</span> GRACE OKAFOR', self.page)           # incoming shows the sender
        self.assertIn('Recipient unidentified', self.page)             # POS purchase

    def test_expected_columns(self):
        head = re.search(r'<thead>\s*<tr>(.*?)</tr>', self.page.split('data-tx-table')[1], re.S).group(1)
        self.assertEqual(re.findall(r'>([^<]+)</th>', head), ['Date', 'Recipient', 'Amount', 'Direction', 'Narration'])

    def test_page_is_accessible_by_structure(self):
        self.assertEqual(self.page.count('<h1'), 1)
        self.assertIn('aria-expanded="false"', self.page)
        self.assertIn('aria-controls="rcpt-1"', self.page)
        self.assertIn('<label class="visually-hidden" for="tx-search">', self.page)
        self.assertIn('lang="en"', self.page)

    def test_privacy_note_present_and_no_advice_wording(self):
        self.assertIn('No additional information has been added or inferred', self.page)
        for phrase in ['you should', 'overspend', 'budget', 'save more', 'good job']:
            self.assertNotIn(phrase, self.page.lower())

    def test_loads_page_assets(self):
        self.assertIn('/static/css/style.css', self.page)
        self.assertIn('/static/js/report.js', self.page)


class CurrencyDisplayTests(PageTestCase):
    NO_CURRENCY = CSV.replace(b' (NGN)', b'')

    def test_statement_currency_shown(self):
        self.assertIn('₦', self.html(self.client_get(self.make_report())))

    def test_no_symbol_when_statement_states_no_currency(self):
        report = self.make_report(data=self.NO_CURRENCY)
        page = self.html(self.client_get(report))
        self.assertNotIn('₦', page)
        self.assertRegex(page, r'data-testid="total-sent">29,500<')

    @override_settings(REPORT_FALLBACK_CURRENCY='NGN')
    def test_optional_fallback_setting(self):
        page = self.html(self.client_get(self.make_report(data=self.NO_CURRENCY)))
        self.assertRegex(page, r'data-testid="total-sent">₦29,500<')

    def client_get(self, report):
        self.client.force_login(self.alice)
        return self.client.get(reverse('reports:detail', args=[report.id]))


class AccessControlTests(PageTestCase):
    def test_anonymous_redirected_to_login(self):
        report = self.make_report()
        r = self.client.get(reverse('reports:detail', args=[report.id]))
        self.assertEqual(r.status_code, 302)
        self.assertIn('/accounts/login/', r['Location'])

    def test_other_users_report_shows_friendly_404_without_leaking_data(self):
        report = self.make_report(self.alice)
        self.client.force_login(self.bob)
        r = self.client.get(reverse('reports:detail', args=[report.id]))
        page = self.html(r)
        self.assertEqual(r.status_code, 404)
        self.assertIn('data-testid="report-not-found"', page)
        self.assertIn("We couldn't find that report", page.replace('&#x27;', "'"))
        for secret in ['AHMED MUSA', '29,500', '50,000', 'September']:
            self.assertNotIn(secret, page)

    def test_unknown_report_looks_identical_to_someone_elses(self):
        report = self.make_report(self.alice)
        self.client.force_login(self.bob)
        other = self.client.get(reverse('reports:detail', args=[report.id]))
        missing = self.client.get(reverse('reports:detail', args=[uuid.uuid4()]))
        self.assertEqual((other.status_code, missing.status_code), (404, 404))
        strip = lambda r: re.sub(r'(csrf-token" content|csrfmiddlewaretoken" value)="[^"]+"', r'\1=""', r.content.decode())
        self.assertEqual(strip(other), strip(missing))  # same page: existence of a report is never revealed

    def test_no_traceback_or_internal_terms_in_error_page(self):
        self.client.force_login(self.bob)
        page = self.html(self.client.get(reverse('reports:detail', args=[uuid.uuid4()])))
        for leak in ['Traceback', 'Http404', 'DoesNotExist', 'django', 'Exception']:
            self.assertNotIn(leak, page)

    def test_history_lists_only_own_reports(self):
        mine = self.make_report(self.alice)
        theirs = self.make_report(self.bob, data=CSV.replace(b'AHMED MUSA', b'SOMEONE ELSE').replace(b'R1', b'Q1'))
        self.client.force_login(self.alice)
        page = self.html(self.client.get(reverse('reports:history')))
        self.assertIn(str(mine.id), page)
        self.assertNotIn(str(theirs.id), page)
        self.assertEqual(page.count('data-testid="history-item"'), 1)

    def test_history_empty_state(self):
        self.client.force_login(self.alice)
        page = self.html(self.client.get(reverse('reports:history')))
        self.assertIn('No reports yet', page)

    def test_history_requires_login(self):
        self.assertEqual(self.client.get(reverse('reports:history')).status_code, 302)

    def test_existing_json_endpoints_unchanged(self):
        report = self.make_report()
        self.client.force_login(self.alice)
        data = self.client.get(reverse('reports:data', args=[report.id])).json()
        self.assertEqual(data['total_sent'], '29500.00')
        self.assertEqual(self.client.get(reverse('reports:list')).json()['reports'][0]['id'], str(report.id))


class EscapingTests(PageTestCase):
    def test_statement_text_is_escaped_not_executed(self):
        report = Report.objects.create(
            user=self.alice, period_start=date(2025, 9, 1), period_end=date(2025, 9, 2), currency='NGN',
            total_received=Decimal('0'), total_sent=Decimal('10'), incoming_count=0, outgoing_count=1,
            unidentified_total=Decimal('0'), unidentified_count=0, fingerprint='x' * 64)
        rcpt = ReportRecipient.objects.create(report=report, name='<script>alert(1)</script>', total_sent=Decimal('10'),
                                              transaction_count=1, rank=1)
        ReportTransaction.objects.create(report=report, recipient=rcpt, date=date(2025, 9, 1), amount=Decimal('10'),
                                         direction='out', counterparty=rcpt.name,
                                         narration='<img src=x onerror=alert(1)>')
        self.client.force_login(self.alice)
        page = self.html(self.client.get(reverse('reports:detail', args=[report.id])))
        self.assertNotIn('<script>alert(1)', page)
        self.assertNotIn('<img src=x', page)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', page)
        self.assertIn('&lt;img src=x onerror=alert(1)&gt;', page)


class MultiYearAndEdgeTests(PageTestCase):
    def test_year_shown_when_period_spans_years(self):
        data = (b'Date,Description,Debit,Credit\n30/12/2025,TRF TO A B,"1,000.00",\n02/01/2026,TRF TO A B,"2,000.00",\n')
        report = self.make_report(data=data)
        self.client.force_login(self.alice)
        page = self.html(self.client.get(reverse('reports:detail', args=[report.id])))
        self.assertIn('30 Dec 2025', page)
        self.assertIn('02 Jan 2026', page)
        self.assertIn('between 30 Dec 2025 and 02 Jan 2026', page)

    def test_all_unidentified_statement(self):
        data = b'Date,Description,Debit,Credit\n03/09/2025,POS PURCHASE X,"1,000.00",\n'
        report = self.make_report(data=data)
        self.client.force_login(self.alice)
        page = self.html(self.client.get(reverse('reports:detail', args=[report.id])))
        self.assertIn("doesn't name a recipient for any outgoing transaction", page.replace('&#x27;', "'"))
        self.assertIn('data-testid="unidentified-count">1 transaction<', page)

    def test_no_unidentified_message(self):
        data = b'Date,Description,Debit,Credit\n03/09/2025,TRF TO AHMED MUSA,"1,000.00",\n'
        report = self.make_report(data=data)
        self.client.force_login(self.alice)
        page = self.html(self.client.get(reverse('reports:detail', args=[report.id])))
        self.assertIn('Every outgoing transaction in your statement names a recipient', page)

    def test_unknown_url_gets_friendly_404(self):
        r = self.client.get('/definitely/not/here/')
        self.assertEqual(r.status_code, 404)
        self.assertIn("couldn't find that page", r.content.decode().replace('&#x27;', "'"))


class FormattingTests(SimpleTestCase):
    def test_money(self):
        self.assertEqual(money(Decimal('450000.00'), '₦'), '₦450,000')
        self.assertEqual(money(Decimal('6850.50'), '₦'), '₦6,850.50')
        self.assertEqual(money(Decimal('0.30'), ''), '0.30')
        self.assertEqual(money(Decimal('1234567.89'), '$'), '$1,234,567.89')

    def test_short_date(self):
        self.assertEqual(short_date(date(2025, 9, 3)), '03 Sep')
        self.assertEqual(short_date(date(2025, 9, 3), True), '03 Sep 2025')

    def test_period_wording(self):
        self.assertEqual(format_period(date(2026, 9, 1), date(2026, 9, 30))[0], 'September 2026')
        self.assertEqual(format_period(date(2026, 9, 5), date(2026, 9, 5))[0], '05 Sep 2026')
        label, intro = format_period(date(2026, 8, 20), date(2026, 9, 10))
        self.assertEqual(label, '20 Aug 2026 – 10 Sep 2026')
        self.assertNotIn('this month', intro)

    def test_currency_symbols(self):
        self.assertEqual(currency_symbol('NGN'), '₦')
        self.assertEqual(currency_symbol('USD'), '$')
        self.assertEqual(currency_symbol('CHF'), 'CHF ')
        self.assertEqual(currency_symbol(''), '')

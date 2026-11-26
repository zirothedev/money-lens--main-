"""Phase 5 browser tests: real Chromium (Playwright) against a live Django server.

Run with the rest of the suite:  python manage.py test
Skipped automatically if Playwright/Chromium isn't installed.
"""
import os
import shutil
import tempfile
import time
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest import mock

os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')   # Playwright's sync API shares the thread with the ORM

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings

from accounts.models import User
from reports import services as report_services
from reports.models import Report, ReportRecipient, ReportTransaction
from statements import services as statement_services
from statements.models import StatementProcessing

try:
    from playwright.sync_api import expect, sync_playwright
    _pw = sync_playwright().start()
    _probe = _pw.chromium.launch()
    _probe.close()
    _pw.stop()
    BROWSER_OK = True
except Exception:   # pragma: no cover - depends on the machine
    BROWSER_OK = False

GOOD_CSV = (b'Date,Description,Debit (NGN),Credit (NGN),Balance,Reference\n'
            b'03/09/2025,NIP TRANSFER TO AHMED MUSA/School fees,"15,000.00",,"985,000.00",R1\n'
            b'08/09/2025,TRF TO AHMED MUSA,"10,000.00",,"975,000.00",R2\n'
            b'09/09/2025,NIP TRANSFER FROM GRACE OKAFOR,,"50,000.00","1,025,000.00",R3\n'
            b'10/09/2025,POS PURCHASE SHOPRITE,"4,500.00",,"1,020,500.00",R4\n')
NO_TX_CSV = b'Date,Description,Debit,Credit\nnot-a-date,x,1.00,\n'
MIXED_CCY_CSV = b'Date,Description,Debit,Credit,Currency\n03/09/2025,TRF TO A,1.00,,NGN\n04/09/2025,TRF TO B,1.00,,USD\n'
STEP_TEXTS = ['Reading your statement…', 'Finding your transactions…', 'Organizing your money…',
              'Identifying recipients…', 'Adding up your transfers…', 'Preparing your report…']
DESKTOP = {'width': 1440, 'height': 900}
TABLET = {'width': 820, 'height': 1100}
MOBILE = {'width': 390, 'height': 844}

csv_file = lambda data=GOOD_CSV, name='statement.csv': {'name': name, 'mimeType': 'text/csv', 'buffer': data}


def pdf_bytes(tmp, build):
    path = Path(tmp) / 'f.pdf'
    build(path)
    return path.read_bytes()


@unittest.skipUnless(BROWSER_OK, 'Playwright Chromium is not available')
class BrowserTestCase(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        super().tearDownClass()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        override = override_settings(PRIVATE_UPLOAD_ROOT=Path(self.tmp))
        override.enable()
        self.addCleanup(override.disable)
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.alice = User.objects.create_user('alice', password='pw-Alice-123')
        self.bob = User.objects.create_user('bob', password='pw-Bob-12345')
        self.errors = []

    def tearDown(self):
        self.assertEqual(self.errors, [], 'JavaScript errors were logged in the browser')

    # ---- helpers ----
    def new_page(self, user=None, viewport=DESKTOP):
        context = self.browser.new_context(viewport=viewport)
        self.addCleanup(context.close)
        if user:
            client = Client()
            client.force_login(user)
            context.add_cookies([{'name': 'sessionid', 'value': client.cookies['sessionid'].value, 'url': self.live_server_url}])
        page = context.new_page()
        page.set_default_timeout(15000)
        page.on('pageerror', lambda e: self.errors.append(str(e)))
        page.on('console', lambda m: self.errors.append(m.text) if m.type == 'error' and 'Failed to load resource' not in m.text else None)
        self.context = context
        return page

    def url(self, path='/'):
        return self.live_server_url + path

    def open_modal(self, page):
        page.goto(self.url('/'))
        page.get_by_role('button', name='Upload Statement').click()
        expect(page.get_by_role('dialog')).to_be_visible()
        page.wait_for_function("document.getAnimations().every(a => a.playState === 'finished')")   # measure layout, not motion

    def choose(self, page, file):
        page.set_input_files('#statement-file', file)

    def make_report(self, user=None, data=GOOD_CSV):
        job = statement_services.create_statement_job(user or self.alice, SimpleUploadedFile('s.csv', data, content_type='text/csv'))
        return report_services.generate_report_for_job(job)

    def no_horizontal_overflow(self, page):
        return page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')

    def private_files(self):
        return list(Path(self.tmp).iterdir())


# ======================================================================================== landing + modal
class LandingAndModalTests(BrowserTestCase):
    def test_landing_page_loads(self):
        page = self.new_page(self.alice)
        page.goto(self.url('/'))
        expect(page.get_by_role('heading', level=1)).to_contain_text('Your bank statement, finally understandable.')
        expect(page.get_by_role('button', name='Upload Statement')).to_be_visible()
        expect(page.get_by_text('PDF and CSV statements supported.')).to_be_visible()
        self.assertEqual(page.title(), "Where'd My Money Go?")

    def test_anonymous_cta_leads_to_login_then_opens_the_modal(self):
        page = self.new_page()
        page.goto(self.url('/'))
        page.get_by_role('link', name='Upload Statement').click()
        page.wait_for_url('**/accounts/login/**')
        page.fill('#id_username', 'alice')
        page.fill('#id_password', 'pw-Alice-123')
        page.get_by_role('button', name='Log in').click()
        expect(page.get_by_role('dialog')).to_be_visible()      # came back with the modal already open
        self.assertNotIn('upload=1', page.url)

    def test_modal_opens_with_blurred_background_and_is_about_70_percent_wide(self):
        page = self.new_page(self.alice)
        self.open_modal(page)
        box = page.get_by_role('dialog').bounding_box()
        self.assertGreater(box['width'] / DESKTOP['width'], 0.6)
        self.assertLess(box['width'] / DESKTOP['width'], 0.75)
        self.assertGreater(box['height'] / DESKTOP['height'], 0.6)
        blur = page.evaluate("getComputedStyle(document.querySelector('.modal__backdrop')).backdropFilter")
        self.assertIn('blur', blur)
        expect(page.get_by_role('dialog').get_by_role('heading', name='Upload your statement')).to_be_visible()
        expect(page.get_by_text('PDF or CSV · Max 10 MB')).to_be_visible()

    def test_modal_closes_with_button_escape_and_backdrop(self):
        page = self.new_page(self.alice)
        dialog = page.get_by_role('dialog')
        self.open_modal(page)
        page.get_by_role('button', name='Close').first.click()
        expect(dialog).to_be_hidden()
        page.get_by_role('button', name='Upload Statement').click()
        page.keyboard.press('Escape')
        expect(dialog).to_be_hidden()
        page.get_by_role('button', name='Upload Statement').click()
        page.mouse.click(5, 5)
        expect(dialog).to_be_hidden()

    def test_focus_is_trapped_and_restored(self):
        page = self.new_page(self.alice)
        page.goto(self.url('/'))
        trigger = page.get_by_role('button', name='Upload Statement')
        trigger.focus()
        page.keyboard.press('Enter')
        expect(page.get_by_role('dialog')).to_be_visible()
        for _ in range(12):
            page.keyboard.press('Tab')
            self.assertTrue(page.evaluate("!!document.activeElement.closest('#upload-modal')"), 'focus escaped the modal')
        page.keyboard.press('Escape')
        self.assertTrue(page.evaluate("document.activeElement.matches('[data-open-upload]')"))

    def test_select_pdf_shows_name_size_and_type(self):
        page = self.new_page(self.alice)
        self.open_modal(page)
        analyze = page.get_by_role('button', name='Analyze Statement')
        expect(analyze).to_be_disabled()
        from processing.tests import helpers
        data = pdf_bytes(self.tmp, helpers.build_table_pdf)
        self.choose(page, {'name': 'September_2026.pdf', 'mimeType': 'application/pdf', 'buffer': data})
        card = page.locator('[data-file-card]')
        expect(card).to_be_visible()
        expect(card.locator('[data-file-name]')).to_have_text('September_2026.pdf')
        expect(card.locator('[data-file-size]')).to_contain_text('KB')
        expect(card.locator('[data-file-type]')).to_have_text('PDF')
        expect(analyze).to_be_enabled()

    def test_select_csv(self):
        page = self.new_page(self.alice)
        self.open_modal(page)
        self.choose(page, csv_file(name='statement.csv'))
        expect(page.locator('[data-file-type]')).to_have_text('CSV')
        expect(page.get_by_role('button', name='Analyze Statement')).to_be_enabled()

    def test_invalid_file_type_is_rejected_immediately(self):
        page = self.new_page(self.alice)
        self.open_modal(page)
        self.choose(page, {'name': 'notes.txt', 'mimeType': 'text/plain', 'buffer': b'hello'})
        expect(page.locator('[data-file-error]')).to_contain_text('Only PDF and CSV statements are supported')
        expect(page.locator('[data-file-card]')).to_be_hidden()
        expect(page.get_by_role('button', name='Analyze Statement')).to_be_disabled()

    def test_oversized_file_is_rejected_immediately(self):
        page = self.new_page(self.alice)
        self.open_modal(page)
        self.choose(page, csv_file(b'a,b\n' * (3 * 1024 * 1024), name='huge.csv'))   # ~12 MB
        expect(page.locator('[data-file-error]')).to_contain_text('too large')
        expect(page.locator('[data-file-error]')).to_contain_text('10 MB')
        expect(page.get_by_role('button', name='Analyze Statement')).to_be_disabled()

    def test_empty_file_is_rejected(self):
        page = self.new_page(self.alice)
        self.open_modal(page)
        self.choose(page, csv_file(b'', name='empty.csv'))
        expect(page.locator('[data-file-error]')).to_contain_text('empty')

    def test_remove_file_resets_the_form(self):
        page = self.new_page(self.alice)
        self.open_modal(page)
        self.choose(page, csv_file())
        page.get_by_role('button', name='Remove selected file').click()
        expect(page.locator('[data-file-card]')).to_be_hidden()
        expect(page.get_by_role('button', name='Analyze Statement')).to_be_disabled()

    def test_a_valid_file_after_an_invalid_one_clears_the_error(self):
        page = self.new_page(self.alice)
        self.open_modal(page)
        self.choose(page, {'name': 'a.txt', 'mimeType': 'text/plain', 'buffer': b'x'})
        self.choose(page, csv_file())
        expect(page.locator('[data-file-error]')).to_be_hidden()
        expect(page.get_by_role('button', name='Analyze Statement')).to_be_enabled()

    def test_drag_and_drop(self):
        page = self.new_page(self.alice)
        self.open_modal(page)
        page.evaluate("""() => {
            const dt = new DataTransfer();
            dt.items.add(new File(['Date,Description,Debit,Credit\\n'], 'dropped.csv', {type: 'text/csv'}));
            document.querySelector('[data-dropzone]').dispatchEvent(new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true}));
        }""")
        expect(page.locator('[data-file-name]')).to_have_text('dropped.csv')

    def test_dropping_several_files_is_refused(self):
        page = self.new_page(self.alice)
        self.open_modal(page)
        page.evaluate("""() => {
            const dt = new DataTransfer();
            dt.items.add(new File(['a'], 'a.csv')); dt.items.add(new File(['b'], 'b.csv'));
            document.querySelector('[data-dropzone]').dispatchEvent(new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true}));
        }""")
        expect(page.locator('[data-file-error]')).to_contain_text('single statement')

    def test_dragover_highlights_the_drop_area(self):
        page = self.new_page(self.alice)
        self.open_modal(page)
        page.evaluate("document.querySelector('[data-dropzone]').dispatchEvent(new DragEvent('dragover', {bubbles: true, cancelable: true}))")
        self.assertTrue(page.evaluate("document.querySelector('[data-dropzone]').classList.contains('is-dragover')"))

    def test_disabled_analyze_sends_nothing(self):
        page = self.new_page(self.alice)
        calls = []
        page.on('request', lambda r: calls.append(r.url) if '/statements/' in r.url else None)
        self.open_modal(page)
        page.get_by_role('button', name='Analyze Statement').click(force=True)
        time.sleep(.5)
        self.assertEqual(calls, [])


# ======================================================================================== processing flow
def slow_extract(delay):
    from processing.pipeline import extract_statement as real

    def wrapper(*args, **kwargs):
        time.sleep(delay)
        return real(*args, **kwargs)
    return wrapper


class ProcessingFlowTests(BrowserTestCase):
    def test_successful_flow_shows_processing_ready_then_redirects_to_the_real_report(self):
        page = self.new_page(self.alice)
        self.open_modal(page)
        self.choose(page, csv_file())
        with mock.patch('reports.services.extract_statement', side_effect=slow_extract(1.5)):
            page.get_by_role('button', name='Analyze Statement').click()
            processing = page.locator('[data-state="processing"]')
            expect(processing).to_be_visible()
            expect(page.get_by_role('heading', name='Analyzing your statement')).to_be_visible()
            expect(page.locator('.spinner')).to_be_visible()
            expect(processing.locator('[data-step]')).to_have_text(STEP_TEXTS)   # all six, in order
            body = page.inner_text('#upload-modal').lower()
            for banned in ['why you spent', 'lifestyle', 'categoriz']:
                self.assertNotIn(banned, body)
            # the Close button is hidden while the request is in flight
            expect(page.locator('.modal__close')).to_be_hidden()
            expect(page.get_by_role('heading', name='Your report is ready.')).to_be_visible()
        page.wait_for_url('**/reports/*/')
        expect(page.get_by_test_id('total-sent')).to_have_text('₦29,500')
        # temporary data is gone
        self.assertEqual(self.private_files(), [])
        self.assertFalse(StatementProcessing.objects.exists())
        self.assertEqual(Report.objects.filter(user=self.alice).count(), 1)

    def test_view_report_button_goes_straight_to_the_report(self):
        page = self.new_page(self.alice)
        self.open_modal(page)
        self.choose(page, csv_file())
        page.get_by_role('button', name='Analyze Statement').click()
        page.get_by_role('link', name='View Report').click()
        page.wait_for_url('**/reports/*/')
        expect(page.get_by_test_id('total-received')).to_have_text('₦50,000')

    def test_close_on_the_ready_screen_cancels_the_automatic_redirect(self):
        page = self.new_page(self.alice)
        self.open_modal(page)
        self.choose(page, csv_file())
        page.get_by_role('button', name='Analyze Statement').click()
        expect(page.get_by_role('heading', name='Your report is ready.')).to_be_visible()
        page.locator('[data-state="ready"]').get_by_role('button', name='Close').click()
        time.sleep(3)
        self.assertNotIn('/reports/', page.url)
        self.assertEqual(Report.objects.count(), 1)   # the report still exists and is reachable from Reports

    def test_pdf_flow_end_to_end(self):
        from processing.tests import helpers
        page = self.new_page(self.alice)
        self.open_modal(page)
        self.choose(page, {'name': 'S.pdf', 'mimeType': 'application/pdf', 'buffer': pdf_bytes(self.tmp, helpers.build_table_pdf)})
        page.get_by_role('button', name='Analyze Statement').click()
        page.get_by_role('link', name='View Report').click()
        page.wait_for_url('**/reports/*/')
        expect(page.get_by_test_id('total-sent')).to_have_text('29,500')   # PDF states no currency: no symbol is invented

    def test_duplicate_upload_continues_with_the_waiting_job(self):
        statement_services.create_statement_job(self.alice, SimpleUploadedFile('s.csv', GOOD_CSV, content_type='text/csv'))
        page = self.new_page(self.alice)
        self.open_modal(page)
        self.choose(page, csv_file())
        page.get_by_role('button', name='Analyze Statement').click()
        expect(page.get_by_role('heading', name='Your report is ready.')).to_be_visible()
        self.assertEqual(Report.objects.count(), 1)

    # ---- error states ----
    def analyze_expecting_error(self, data, name='bad.csv', mime='text/csv'):
        page = self.new_page(self.alice)
        self.open_modal(page)
        self.choose(page, {'name': name, 'mimeType': mime, 'buffer': data})
        page.get_by_role('button', name='Analyze Statement').click()
        error = page.locator('[data-state="error"]')
        expect(error).to_be_visible()
        return page, error

    def assert_clean(self, error):
        text = error.inner_text()
        for leak in ['Traceback', 'Exception', 'Django', 'Error:', 'undefined', 'null']:
            self.assertNotIn(leak, text)

    def test_statement_with_no_readable_transactions(self):
        page, error = self.analyze_expecting_error(NO_TX_CSV)
        expect(error.get_by_role('heading')).to_have_text("We couldn't find any transactions")
        self.assert_clean(error)
        self.assertEqual(self.private_files(), [])      # nothing is left behind on failure

    def test_pdf_without_selectable_text(self):
        from processing.tests import helpers
        page, error = self.analyze_expecting_error(pdf_bytes(self.tmp, helpers.build_blank_pdf), 'scan.pdf', 'application/pdf')
        expect(error).to_contain_text("We couldn't read this statement.")
        expect(error).to_contain_text('selectable text')
        self.assert_clean(error)

    def test_corrupt_pdf(self):
        page, error = self.analyze_expecting_error(b'%PDF-1.4 definitely not a real pdf', 'bad.pdf', 'application/pdf')
        expect(error).to_contain_text("We couldn't read this statement.")
        self.assert_clean(error)

    def test_csv_that_is_not_a_statement(self):
        page, error = self.analyze_expecting_error(b'hello,world\n1,2\n')
        expect(error).to_contain_text('date and amount columns')

    def test_multiple_currencies(self):
        page, error = self.analyze_expecting_error(MIXED_CCY_CSV)
        expect(error).to_contain_text('more than one currency')

    def test_pdf_extension_with_wrong_content_is_caught_by_the_server_and_shown_inline(self):
        page = self.new_page(self.alice)
        self.open_modal(page)
        self.choose(page, {'name': 'fake.pdf', 'mimeType': 'application/pdf', 'buffer': b'this is not a pdf'})
        page.get_by_role('button', name='Analyze Statement').click()
        expect(page.locator('[data-file-error]')).to_contain_text("doesn't look like a valid PDF or CSV")
        expect(page.locator('[data-state="select"]')).to_be_visible()

    def test_unexpected_server_error_is_friendly(self):
        page = self.new_page(self.alice)
        self.open_modal(page)
        self.choose(page, csv_file())
        page.route('**/process/', lambda route: route.fulfill(status=500, content_type='text/html', body='Traceback (most recent call last)'))
        page.get_by_role('button', name='Analyze Statement').click()
        error = page.locator('[data-state="error"]')
        expect(error).to_contain_text('Something went wrong on our side')
        self.assert_clean(error)

    def test_network_failure_returns_to_the_form_so_the_user_can_retry(self):
        page = self.new_page(self.alice)
        self.open_modal(page)
        self.choose(page, csv_file())
        page.route('**/statements/upload/', lambda route: route.abort())
        page.get_by_role('button', name='Analyze Statement').click()
        expect(page.locator('[data-file-error]')).to_contain_text("couldn't reach the server")
        expect(page.get_by_role('button', name='Analyze Statement')).to_be_enabled()
        expect(page.locator('[data-file-name]')).to_have_text('statement.csv')   # file is kept

    def test_session_expired(self):
        page = self.new_page(self.alice)
        self.open_modal(page)
        self.choose(page, csv_file())
        self.context.clear_cookies()
        page.get_by_role('button', name='Analyze Statement').click()
        error = page.locator('[data-state="error"]')
        expect(error.get_by_role('heading')).to_have_text('Your session has expired')
        expect(error.get_by_role('link', name='Log in again')).to_be_visible()
        expect(error.get_by_role('button', name='Try another file')).to_be_hidden()

    def test_try_another_file_returns_to_a_clean_form(self):
        page, error = self.analyze_expecting_error(NO_TX_CSV)
        error.get_by_role('button', name='Try another file').click()
        expect(page.locator('[data-state="select"]')).to_be_visible()
        expect(page.locator('[data-file-card]')).to_be_hidden()
        expect(page.get_by_role('button', name='Analyze Statement')).to_be_disabled()


# ======================================================================================== report page
class ReportPageBrowserTests(BrowserTestCase):
    def setUp(self):
        super().setUp()
        self.report = self.make_report()

    def open_report(self, user=None, viewport=DESKTOP):
        page = self.new_page(user or self.alice, viewport)
        page.goto(self.url(f'/reports/{self.report.id}/'))
        return page

    def test_header_and_overview_use_real_backend_numbers(self):
        page = self.open_report()
        expect(page.get_by_role('heading', level=1)).to_have_text("Where'd My Money Go?")
        expect(page.get_by_test_id('report-period')).to_have_text('September 2025')
        expect(page.get_by_test_id('total-received')).to_have_text('₦50,000')
        expect(page.get_by_test_id('total-sent')).to_have_text('₦29,500')
        expect(page.locator('.stat').nth(0)).to_contain_text('1 transaction')
        expect(page.locator('.stat').nth(1)).to_contain_text('3 transactions')

    def test_recipients_ranked_with_totals_counts_and_bars(self):
        page = self.open_report()
        rows = page.get_by_test_id('recipient')
        expect(rows).to_have_count(1)
        expect(rows.first).to_contain_text('AHMED MUSA')
        expect(rows.first).to_contain_text('2 transactions')
        expect(rows.first).to_contain_text('₦25,000')
        width = page.evaluate("getComputedStyle(document.querySelector('.bar__fill')).width")
        time.sleep(1)
        width = page.evaluate("parseFloat(getComputedStyle(document.querySelector('.bar__fill')).width)")
        self.assertGreater(width, 20)

    def test_recipient_details_expand_and_empty_narration_stays_empty(self):
        page = self.open_report()
        button = page.locator('[data-toggle]').first
        panel = page.locator('#rcpt-1')
        expect(panel).to_be_hidden()
        expect(button).to_have_attribute('aria-expanded', 'false')
        button.click()
        expect(panel).to_be_visible()
        expect(button).to_have_attribute('aria-expanded', 'true')
        cells = panel.locator('tbody tr').evaluate_all("rows => rows.map(r => [...r.cells].map(c => c.textContent.trim()))")
        self.assertEqual(cells, [['03 Sep', '₦15,000', 'School fees'], ['08 Sep', '₦10,000', '']])
        button.click()
        expect(panel).to_be_hidden()

    def test_recipient_details_work_from_the_keyboard(self):
        page = self.open_report()
        page.locator('[data-toggle]').first.focus()
        page.keyboard.press('Enter')
        expect(page.locator('#rcpt-1')).to_be_visible()
        page.keyboard.press('Space')
        expect(page.locator('#rcpt-1')).to_be_hidden()

    def test_unidentified_section(self):
        page = self.open_report()
        expect(page.get_by_test_id('unidentified-count')).to_have_text('1 transaction')
        expect(page.get_by_test_id('unidentified-total')).to_have_text('₦4,500')
        page.get_by_role('button', name='View transactions').click()
        expect(page.locator('#unid-details')).to_contain_text('10 Sep')
        expect(page.locator('#unid-details')).to_contain_text('₦4,500')

    def test_transaction_list_columns_directions_and_blank_narration(self):
        page = self.open_report()
        table = page.locator('[data-tx-table]')
        expect(table.locator('thead th')).to_have_text(['Date', 'Recipient', 'Amount', 'Direction', 'Narration'])
        rows = table.locator('tbody tr')
        expect(rows).to_have_count(4)
        expect(rows.nth(0)).to_contain_text('AHMED MUSA')
        expect(rows.nth(0)).to_contain_text('−₦15,000')
        expect(rows.nth(0)).to_contain_text('Money out')
        expect(rows.nth(2)).to_contain_text('GRACE OKAFOR')
        expect(rows.nth(2)).to_contain_text('+₦50,000')
        expect(rows.nth(2)).to_contain_text('Money in')
        expect(rows.nth(3)).to_contain_text('Recipient unidentified')
        narrations = rows.evaluate_all("rs => rs.map(r => r.querySelector('.tx__narr').textContent.trim())")
        self.assertEqual(narrations, ['School fees', '', '', ''])
        body = page.inner_text('main')
        for banned in ['No narration', 'Purpose unknown', 'Unknown', 'Personal']:
            self.assertNotIn(banned, body)

    def test_search_and_direction_filter(self):
        page = self.open_report()
        rows = page.locator('[data-tx-row]:visible')
        page.get_by_label('Search transactions').fill('ahmed')
        expect(rows).to_have_count(2)
        page.get_by_label('Search transactions').fill('school')
        expect(rows).to_have_count(1)
        page.get_by_label('Search transactions').fill('zzz')
        expect(page.get_by_text('No transactions match your search.')).to_be_visible()
        page.get_by_label('Search transactions').fill('')
        page.get_by_role('button', name='Money in').click()
        expect(rows).to_have_count(1)
        expect(page.get_by_role('button', name='Money in')).to_have_attribute('aria-pressed', 'true')
        page.get_by_role('button', name='Money out').click()
        expect(rows).to_have_count(3)
        page.get_by_role('button', name='All', exact=True).click()
        expect(rows).to_have_count(4)

    def test_show_more_for_long_statements(self):
        report = self.report
        ReportTransaction.objects.bulk_create([
            ReportTransaction(report=report, date=date(2025, 9, 11), amount=Decimal('100'), direction='out', narration=f'n{i}')
            for i in range(60)])
        page = self.new_page(self.alice)
        page.goto(self.url(f'/reports/{report.id}/'))
        rows = page.locator('[data-tx-row]:visible')
        expect(rows).to_have_count(25)
        expect(page.locator('[data-tx-count]')).to_contain_text('Showing 25 of 64')
        page.get_by_role('button', name='Show more').click()
        expect(rows).to_have_count(50)
        page.get_by_role('button', name='Show more').click()
        expect(rows).to_have_count(64)
        expect(page.get_by_role('button', name='Show more')).to_be_hidden()

    def test_reports_list_and_navigation(self):
        page = self.new_page(self.alice)
        page.goto(self.url('/reports/history/'))
        page.get_by_test_id('history-item').click()
        page.wait_for_url(f'**/reports/{self.report.id}/')
        page.get_by_role('link', name='All reports').click()
        page.wait_for_url('**/reports/history/')
        page.get_by_role('link', name='Home').click()
        expect(page.get_by_role('heading', level=1)).to_contain_text('finally understandable')

    def test_new_statement_link_opens_the_upload_modal(self):
        page = self.open_report()
        page.get_by_role('link', name='New statement').click()
        expect(page.get_by_role('dialog')).to_be_visible()

    def test_people_are_recipients_and_the_bank_is_shown_as_via(self):
        data = (b'Date,Description,Debit (NGN),Credit (NGN),Balance,Reference\n'
                b'03/09/2025,Instant Payment Outward 000013260801112746000108527582 NIP TRANSFER TO OPAY - ADA OBI,"2,500.00",,"97,500.00",R1\n'
                b'04/09/2025,Instant Payment Outward 000013260804112746000108527583 NIP TRANSFER TO MOMO - ADA OBI,"500.00",,"97,000.00",R2\n'
                b'05/09/2025,POSWEB PURCHASE TRANSACTION POS PUR OPAY KURE BUSINESS ENTEBauchi BANG 857546 001776099175 4001LUJW539983*********6603,"4,100.00",,"92,900.00",R3\n')
        self.report = self.make_report(data=data)
        page = self.open_report()
        rows = page.get_by_test_id('recipient')
        expect(rows).to_have_count(2)
        expect(rows.nth(0)).to_contain_text('OPAY KURE BUSINESS ENTE')        # largest, exactly as the statement writes it
        expect(rows.nth(1)).to_contain_text('ADA OBI')
        expect(rows.nth(1)).to_contain_text('2 transactions')
        expect(rows.nth(1)).to_contain_text('₦3,000')
        expect(page.get_by_test_id('unidentified-count')).to_have_count(0)    # nothing is left unidentified
        ada = page.locator('[data-tx-row]').filter(has_text='ADA OBI').first
        expect(ada.locator('.tx__via')).to_have_text('via OPAY')
        names = page.locator('.recipient__name').all_inner_texts()
        self.assertNotIn('OPAY', names)                                       # a bank is never listed as a recipient

    # ---- access control ----
    def test_another_user_cannot_view_the_report(self):
        page = self.open_report(self.bob)
        expect(page.get_by_test_id('report-not-found')).to_be_visible()
        expect(page.get_by_role('heading', level=1)).to_have_text("We couldn't find that report")
        content = page.content()
        for secret in ['AHMED MUSA', '29,500', '50,000']:
            self.assertNotIn(secret, content)

    def test_anonymous_visitor_is_sent_to_login(self):
        page = self.new_page()
        page.goto(self.url(f'/reports/{self.report.id}/'))
        page.wait_for_url('**/accounts/login/**')
        expect(page.get_by_role('heading', name='Welcome back')).to_be_visible()

    def test_report_not_found(self):
        page = self.new_page(self.alice)
        page.goto(self.url('/reports/11111111-1111-1111-1111-111111111111/'))
        expect(page.get_by_test_id('report-not-found')).to_be_visible()
        expect(page.get_by_role('link', name='Go to your reports')).to_be_visible()


# ======================================================================================== responsive layout
class ResponsiveTests(BrowserTestCase):
    def setUp(self):
        super().setUp()
        self.report = self.make_report()
        ReportTransaction.objects.bulk_create([
            ReportTransaction(report=self.report, date=date(2025, 9, 11), amount=Decimal('1234567.5'), direction='out',
                              counterparty='A VERY LONG NAMED RECIPIENT ENTERPRISES NIGERIA LIMITED', narration='Bulk order for the new warehouse extension')])

    def check_no_overflow(self, viewport):
        page = self.new_page(self.alice, viewport)
        for path in ['/', f'/reports/{self.report.id}/', '/reports/history/']:
            page.goto(self.url(path))
            self.assertTrue(self.no_horizontal_overflow(page), f'horizontal overflow on {path} at {viewport}')
        return page

    def test_desktop_has_no_horizontal_overflow(self):
        self.check_no_overflow(DESKTOP)

    def test_tablet_has_no_horizontal_overflow(self):
        self.check_no_overflow(TABLET)

    def test_mobile_has_no_horizontal_overflow(self):
        self.check_no_overflow(MOBILE)

    def test_desktop_layout_uses_sidebar_and_a_table(self):
        page = self.new_page(self.alice, DESKTOP)
        page.goto(self.url(f'/reports/{self.report.id}/'))
        sidebar = page.locator('.sidebar').bounding_box()
        self.assertGreater(sidebar['height'], 800)
        self.assertLess(sidebar['width'], 260)
        expect(page.locator('[data-tx-table] thead')).to_be_visible()
        stats = page.locator('.stat').evaluate_all('els => els.map(e => e.getBoundingClientRect().top)')
        self.assertEqual(stats[0], stats[1])    # received + sent sit side by side

    def test_mobile_cards_stack_and_table_becomes_cards(self):
        page = self.new_page(self.alice, MOBILE)
        page.goto(self.url(f'/reports/{self.report.id}/'))
        tops = page.locator('.stat').evaluate_all('els => els.map(e => e.getBoundingClientRect().top)')
        self.assertLess(tops[0], tops[1])       # stacked
        self.assertEqual(page.evaluate("getComputedStyle(document.querySelector('.tx-table tbody tr')).display"), 'grid')
        # each transaction card still shows date, name, amount and direction
        first = page.locator('[data-tx-row]').first
        for cls in ['.tx__date', '.tx__name', '.tx__amount', '.tx__dir']:
            expect(first.locator(cls)).to_be_visible()
        widest = page.evaluate("Math.max(...[...document.querySelectorAll('[data-tx-row]')].map(r => r.getBoundingClientRect().right))")
        self.assertLessEqual(widest, MOBILE['width'])

    def test_mobile_navigation_links_keep_accessible_names(self):
        page = self.new_page(self.alice, MOBILE)
        page.goto(self.url('/'))
        expect(page.get_by_role('link', name='Home')).to_be_visible()
        expect(page.get_by_role('link', name='Reports')).to_be_visible()
        expect(page.get_by_role('button', name='Log out')).to_be_visible()
        expect(page.get_by_role('link', name="Where'd My Money Go?")).to_be_visible()

    def test_mobile_modal_fits_the_viewport_and_all_states_are_usable(self):
        page = self.new_page(self.alice, MOBILE)
        self.open_modal(page)
        box = page.get_by_role('dialog').bounding_box()
        self.assertLessEqual(box['x'] + box['width'], MOBILE['width'] + 1)
        self.assertLessEqual(box['y'] + box['height'], MOBILE['height'] + 1)
        self.choose(page, csv_file())
        analyze = page.get_by_role('button', name='Analyze Statement')
        self.assertTrue(analyze.is_visible())
        ab = analyze.bounding_box()
        self.assertGreaterEqual(ab['height'], 44)                    # comfortable tap target
        self.assertLessEqual(ab['y'] + ab['height'], MOBILE['height'])
        with mock.patch('reports.services.extract_statement', side_effect=slow_extract(1.5)):
            analyze.click()
            expect(page.locator('[data-state="processing"]')).to_be_visible()
            self.assertTrue(self.no_horizontal_overflow(page))
            pb = page.get_by_role('dialog').bounding_box()
            self.assertLessEqual(pb['y'] + pb['height'], MOBILE['height'] + 1)
            expect(page.get_by_role('heading', name='Your report is ready.')).to_be_visible()

    def test_mobile_error_state_fits(self):
        page = self.new_page(self.alice, MOBILE)
        self.open_modal(page)
        self.choose(page, csv_file(NO_TX_CSV))
        page.get_by_role('button', name='Analyze Statement').click()
        expect(page.locator('[data-state="error"]')).to_be_visible()
        box = page.get_by_role('dialog').bounding_box()
        self.assertLessEqual(box['y'] + box['height'], MOBILE['height'] + 1)

    def test_text_stays_readable_on_mobile(self):
        page = self.new_page(self.alice, MOBILE)
        page.goto(self.url(f'/reports/{self.report.id}/'))
        smallest = page.evaluate("""() => Math.min(...[...document.querySelectorAll('main p, main td, main a, main button, main span, main h1, main h2')]
            .filter(e => e.offsetParent && e.textContent.trim() && !e.closest('.sr-only, .visually-hidden'))
            .map(e => parseFloat(getComputedStyle(e).fontSize)))""")
        self.assertGreaterEqual(smallest, 11)

    def test_reduced_motion_is_respected(self):
        context = self.browser.new_context(viewport=DESKTOP, reduced_motion='reduce')
        self.addCleanup(context.close)
        client = Client(); client.force_login(self.alice)
        context.add_cookies([{'name': 'sessionid', 'value': client.cookies['sessionid'].value, 'url': self.live_server_url}])
        page = context.new_page()
        page.goto(self.url('/'))
        page.get_by_role('button', name='Upload Statement').click()
        duration = page.evaluate("getComputedStyle(document.querySelector('.modal__panel')).animationDuration")
        self.assertIn(duration, ('0.001s', '1e-06s', '0s'))


# ======================================================================================== auth pages
class AuthBrowserTests(BrowserTestCase):
    def test_login_wrong_password_shows_a_readable_error(self):
        page = self.new_page()
        page.goto(self.url('/accounts/login/'))
        page.fill('#id_username', 'alice')
        page.fill('#id_password', 'nope')
        page.get_by_role('button', name='Log in').click()
        expect(page.get_by_role('alert')).to_contain_text('Please enter a correct username and password')

    def test_logout_from_the_sidebar(self):
        page = self.new_page(self.alice)
        page.goto(self.url('/'))
        page.get_by_role('button', name='Log out').click()
        page.goto(self.url('/'))
        expect(page.get_by_role('link', name='Log in')).to_be_visible()

    def test_auth_pages_have_no_overflow_on_mobile(self):
        page = self.new_page(viewport=MOBILE)
        for path in ['/accounts/login/', '/accounts/register/']:
            page.goto(self.url(path))
            self.assertTrue(self.no_horizontal_overflow(page), path)

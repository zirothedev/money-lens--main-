"""Phase 5: landing page, upload modal markup, auth pages and static assets."""
import re

from django.contrib.staticfiles import finders
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User

FORBIDDEN_COPY = ['Understanding why', 'lifestyle', 'Categoriz', 'Purpose unknown', 'financial advice']
STEP_TEXTS = ['Reading your statement…', 'Finding your transactions…', 'Organizing your money…',
              'Identifying recipients…', 'Adding up your transfers…', 'Preparing your report…']


class LandingPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('ziro', password='x')

    def page(self, logged_in=False):
        if logged_in:
            self.client.force_login(self.user)
        r = self.client.get(reverse('home'))
        self.assertEqual(r.status_code, 200)
        return r.content.decode()

    def test_landing_content(self):
        page = self.page()
        self.assertIn("Where'd My Money Go?", page)
        self.assertIn('Your bank statement,', page)
        self.assertIn('finally understandable.', page)
        self.assertIn('Upload Statement', page)
        self.assertIn('PDF and CSV statements supported.', page)

    def test_no_forbidden_copy(self):
        for text in FORBIDDEN_COPY:
            self.assertNotIn(text.lower(), self.page(True).lower())

    def test_example_report_is_labelled_as_an_example(self):
        self.assertIn('Example report', self.page())

    def test_anonymous_cta_goes_to_login_and_returns_to_upload(self):
        page = self.page()
        self.assertIn('/accounts/login/?next=/%3Fupload%3D1', page)
        self.assertNotIn('id="upload-modal"', page)

    def test_authenticated_page_contains_the_upload_modal(self):
        page = self.page(True)
        self.assertIn('id="upload-modal"', page)
        self.assertIn('data-open-upload', page)
        self.assertIn('role="dialog" aria-modal="true" aria-labelledby="upload-title"', page)

    def test_modal_file_input_and_limits(self):
        page = self.page(True)
        self.assertIn('accept=".pdf,.csv,application/pdf,text/csv"', page)
        self.assertIn('Max 10 MB', page)
        self.assertIn('data-max-bytes="10485760"', page)
        self.assertRegex(page, r'<label class="btn btn--outline" for="statement-file">Choose file</label>')
        self.assertRegex(page, r'data-analyze disabled')

    @override_settings(STATEMENT_MAX_UPLOAD_BYTES=5 * 1024 * 1024)
    def test_modal_limit_follows_backend_setting(self):
        page = self.page(True)
        self.assertIn('Max 5 MB', page)
        self.assertIn('data-max-bytes="5242880"', page)

    def test_modal_points_at_existing_endpoints(self):
        page = self.page(True)
        self.assertIn(f'data-upload-url="{reverse("statements:upload")}"', page)
        self.assertRegex(page, r'data-process-url="/statements/0{8}-0{4}-0{4}-0{4}-0{12}/process/"')
        self.assertRegex(page, r'data-report-url="/reports/0{8}-0{4}-0{4}-0{4}-0{12}/"')

    def test_processing_messages_present_in_order(self):
        page = self.page(True)
        positions = [page.index(t) for t in STEP_TEXTS]
        self.assertEqual(positions, sorted(positions))

    def test_all_four_modal_states_exist(self):
        page = self.page(True)
        for state in ['select', 'processing', 'ready', 'error']:
            self.assertIn(f'data-state="{state}"', page)
        self.assertIn('Your report is ready.', page)

    def test_modal_accessibility_hooks(self):
        page = self.page(True)
        self.assertIn('aria-label="Close"', page)
        self.assertIn('aria-label="Remove selected file"', page)
        self.assertIn('role="alert"', page)
        self.assertIn('aria-live="polite"', page)

    def test_csrf_meta_and_cookie_available_to_javascript(self):
        r = self.client.get(reverse('home'))
        self.assertRegex(r.content.decode(), r'<meta name="csrf-token" content="[A-Za-z0-9]+"')
        self.assertIn('csrftoken', r.cookies)

    def test_scripts_loaded_in_dependency_order(self):
        page = self.page(True)
        order = [page.index(f'js/{n}.js') for n in ['validation', 'messages', 'api', 'modal', 'upload']]
        self.assertEqual(order, sorted(order))

    def test_no_inline_styles_or_scripts_in_templates(self):
        for page in (self.page(), self.page(True)):
            self.assertNotRegex(page, r'<[^>]+\sstyle="')
            self.assertNotRegex(page, r'<script(?![^>]*src=)[^>]*>')

    def test_semantic_landmarks(self):
        page = self.page(True)
        for tag in ['<header class="lp-header"', '<main id="main"', '<nav ', '<footer', '<h1', 'class="skip-link"']:
            self.assertIn(tag, page)
        self.assertEqual(page.count('<h1'), 1)

    def test_sidebar_logout_is_a_post_form(self):
        page = self.page(True)
        self.assertRegex(page, r'<form method="post" action="/accounts/logout/"')

    def test_images_have_alt_text_and_icons_are_hidden_from_screen_readers(self):
        for page in (self.page(), self.page(True)):
            for img in re.findall(r'<img[^>]*>', page):
                self.assertIn('alt=', img)


class AuthPageTests(TestCase):
    def test_login_page(self):
        page = self.client.get(reverse('accounts:login')).content.decode()
        self.assertRegex(page, r'<label for="id_username">')
        self.assertRegex(page, r'<label for="id_password">')
        self.assertIn('brand-banner.jpg', page)

    def test_login_error_is_human_readable(self):
        r = self.client.post(reverse('accounts:login'), {'username': 'nobody', 'password': 'wrong'})
        page = r.content.decode()
        self.assertEqual(r.status_code, 200)
        self.assertIn('role="alert"', page)
        self.assertNotIn('Traceback', page)

    def test_login_preserves_upload_redirect(self):
        User.objects.create_user('ziro', password='Sup3r-secret-pass')
        r = self.client.post(reverse('accounts:login'),
                             {'username': 'ziro', 'password': 'Sup3r-secret-pass', 'next': '/?upload=1'})
        self.assertRedirects(r, '/?upload=1', fetch_redirect_response=False)

    def test_register_page_shows_field_errors(self):
        r = self.client.post(reverse('accounts:register'), {'username': 'a', 'password1': '1', 'password2': '2'})
        self.assertContains(r, 'field__error')

    def test_register_page_loads(self):
        self.assertEqual(self.client.get(reverse('accounts:register')).status_code, 200)


class StaticAssetTests(TestCase):
    def test_all_referenced_assets_exist(self):
        for path in ['css/style.css', 'img/favicon.svg', 'img/brand-banner.jpg',
                     'fonts/plus-jakarta-sans-latin-wght-normal.woff2', 'fonts/plus-jakarta-sans-latin-ext-wght-normal.woff2',
                     'js/boot.js', 'js/validation.js', 'js/messages.js', 'js/api.js', 'js/modal.js', 'js/upload.js',
                     'js/report.js']:
            self.assertIsNotNone(finders.find(path), path)

    def test_stylesheet_defines_design_tokens_and_uses_the_brand_purple(self):
        css = open(finders.find('css/style.css'), encoding='utf-8').read()
        for token in ['--primary:', '--background:', '--text-primary:', '--text-secondary:', '--border:', '--card-radius:']:
            self.assertIn(token, css)
        self.assertIn('--primary: #7837ec', css)
        self.assertNotRegex(css.lower(), r'#(00ff|39ff|0f0|7cfc)')   # the old neon green is gone

    def test_no_third_party_requests_in_stylesheet_or_templates(self):
        css = open(finders.find('css/style.css'), encoding='utf-8').read()
        self.assertNotRegex(css, r'https?://')
        self.assertNotIn('googleapis', css)

    def test_every_css_url_resolves(self):
        css = open(finders.find('css/style.css'), encoding='utf-8').read()
        for rel in re.findall(r"url\('\.\./([^']+)'\)", css):
            self.assertIsNotNone(finders.find(rel), rel)

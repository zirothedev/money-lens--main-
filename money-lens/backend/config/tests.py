from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from accounts.models import User


class FoundationTests(TestCase):
    def test_health_check(self):
        r = self.client.get(reverse('health'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {'status': 'ok', 'database': 'ok'})

    def test_home_renders(self):
        r = self.client.get(reverse('home'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Where'd My Money Go?")

    def test_custom_user_model(self):
        self.assertEqual(settings.AUTH_USER_MODEL, 'accounts.User')
        self.assertTrue(User.objects.create_user('a', password='x12345678!').check_password('x12345678!'))

    def test_apps_installed(self):
        for app in ('accounts', 'statements', 'reports', 'processing'):
            self.assertIn(app, settings.INSTALLED_APPS)

    def test_database_is_sqlite_by_default_and_env_driven(self):
        self.assertIn('sqlite', settings.DATABASES['default']['ENGINE'])

    def test_private_upload_root_not_under_static_or_media(self):
        root = settings.PRIVATE_UPLOAD_ROOT.resolve()
        for static_dir in settings.STATICFILES_DIRS:
            self.assertNotIn(static_dir.resolve(), [root, *root.parents])

    def test_login_page_and_registration(self):
        self.assertEqual(self.client.get(reverse('accounts:login')).status_code, 200)
        r = self.client.post(reverse('accounts:register'), {
            'username': 'newuser', 'email': 'n@example.com',
            'password1': 'Sup3r-secret-pass', 'password2': 'Sup3r-secret-pass'})
        self.assertRedirects(r, reverse('home'))
        self.assertTrue(User.objects.filter(username='newuser').exists())

    def test_csrf_enforced_on_login(self):
        from django.test import Client
        c = Client(enforce_csrf_checks=True)
        r = c.post(reverse('accounts:login'), {'username': 'x', 'password': 'y'})
        self.assertEqual(r.status_code, 403)

    def test_admin_requires_login(self):
        self.assertEqual(self.client.get('/admin/').status_code, 302)

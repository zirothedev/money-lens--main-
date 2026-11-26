import os
import shutil
import tempfile
import time
from datetime import timedelta
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from statements import services, storage
from statements.exceptions import DuplicateStatementError, InvalidStatementFile
from statements.models import StatementProcessing

PDF_BYTES = b'%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF'
CSV_BYTES = b'Date,Description,Debit,Credit\n2025-09-03,TRF to Ahmed Musa,15000,\n'


class PrivateStorageTestCase(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.override = override_settings(PRIVATE_UPLOAD_ROOT=Path(self.tmp))
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.user = User.objects.create_user('alice', password='pw-Alice-123')
        self.other = User.objects.create_user('bob', password='pw-Bob-12345')

    def files(self):
        return os.listdir(self.tmp)

    @staticmethod
    def pdf(name='statement.pdf', data=PDF_BYTES):
        return SimpleUploadedFile(name, data, content_type='application/pdf')

    @staticmethod
    def csv(name='statement.csv', data=CSV_BYTES):
        return SimpleUploadedFile(name, data, content_type='text/csv')


class UploadServiceTests(PrivateStorageTestCase):
    def test_valid_pdf(self):
        job = services.create_statement_job(self.user, self.pdf())
        self.assertEqual(job.file_type, 'pdf')
        self.assertEqual(job.status, StatementProcessing.Status.UPLOADED)
        self.assertEqual(job.user, self.user)

    def test_valid_csv(self):
        job = services.create_statement_job(self.user, self.csv())
        self.assertEqual(job.file_type, 'csv')

    def test_invalid_file_type(self):
        with self.assertRaises(InvalidStatementFile) as cm:
            services.create_statement_job(self.user, SimpleUploadedFile('a.exe', b'MZ...'))
        self.assertEqual(cm.exception.code, 'unsupported_type')
        self.assertEqual(self.files(), [])
        self.assertEqual(StatementProcessing.objects.count(), 0)

    def test_pdf_extension_with_non_pdf_content_rejected(self):
        with self.assertRaises(InvalidStatementFile) as cm:
            services.create_statement_job(self.user, self.pdf(data=b'not a pdf at all'))
        self.assertEqual(cm.exception.code, 'content_mismatch')

    def test_csv_extension_with_binary_content_rejected(self):
        with self.assertRaises(InvalidStatementFile):
            services.create_statement_job(self.user, self.csv(data=b'a,b\x00\x01\x02'))

    @override_settings(STATEMENT_MAX_UPLOAD_BYTES=100)
    def test_oversized_file(self):
        with self.assertRaises(InvalidStatementFile) as cm:
            services.create_statement_job(self.user, self.csv(data=b'a,b\n' * 100))
        self.assertEqual(cm.exception.code, 'file_too_large')
        self.assertEqual(self.files(), [])

    def test_missing_file(self):
        with self.assertRaises(InvalidStatementFile) as cm:
            services.create_statement_job(self.user, None)
        self.assertEqual(cm.exception.code, 'missing_file')

    def test_empty_file(self):
        with self.assertRaises(InvalidStatementFile) as cm:
            services.create_statement_job(self.user, self.csv(data=b''))
        self.assertEqual(cm.exception.code, 'empty_file')

    def test_temporary_file_creation_is_private_and_safely_named(self):
        job = services.create_statement_job(self.user, self.pdf(name='../../etc/passwd.pdf'))
        self.assertEqual(len(self.files()), 1)
        name = self.files()[0]
        self.assertEqual(name, job.temp_file_name)
        self.assertRegex(name, r'^[0-9a-f]{32}\.pdf$')  # random; original filename never used
        path = Path(self.tmp) / name
        self.assertEqual(path.read_bytes(), PDF_BYTES)
        self.assertEqual(path.stat().st_mode & 0o077, 0)  # owner-only permissions

    def test_unique_filenames_for_different_uploads(self):
        a = services.create_statement_job(self.user, self.csv())
        b = services.create_statement_job(self.user, self.csv(data=CSV_BYTES + b'2025-09-04,x,1,\n'))
        self.assertNotEqual(a.temp_file_name, b.temp_file_name)

    def test_duplicate_active_upload_blocked_and_leaves_no_extra_file(self):
        services.create_statement_job(self.user, self.csv())
        with self.assertRaises(DuplicateStatementError):
            services.create_statement_job(self.user, self.csv())
        self.assertEqual(len(self.files()), 1)
        self.assertEqual(StatementProcessing.objects.count(), 1)

    def test_same_file_by_different_user_is_allowed(self):
        services.create_statement_job(self.user, self.csv())
        services.create_statement_job(self.other, self.csv())
        self.assertEqual(StatementProcessing.objects.count(), 2)

    def test_expiration_time_set(self):
        job = services.create_statement_job(self.user, self.csv())
        self.assertGreater(job.expires_at, timezone.now())
        self.assertFalse(job.is_expired)

    @override_settings(STATEMENT_EXPIRY_MINUTES=5)
    def test_expiry_is_configurable(self):
        job = services.create_statement_job(self.user, self.csv())
        self.assertLess(job.expires_at - timezone.now(), timedelta(minutes=5, seconds=5))


class DeletionAndCleanupTests(PrivateStorageTestCase):
    def test_temporary_file_deletion(self):
        job = services.create_statement_job(self.user, self.csv())
        services.delete_statement_job(job)
        self.assertEqual(self.files(), [])
        self.assertFalse(StatementProcessing.objects.exists())

    def test_deleting_already_missing_file_is_safe(self):
        job = services.create_statement_job(self.user, self.csv())
        os.unlink(Path(self.tmp) / job.temp_file_name)
        services.delete_statement_job(job)
        self.assertFalse(StatementProcessing.objects.exists())

    def test_expired_cleanup_removes_only_expired(self):
        old = services.create_statement_job(self.user, self.csv())
        fresh = services.create_statement_job(self.user, self.pdf())
        StatementProcessing.objects.filter(pk=old.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        result = services.cleanup_expired_jobs()
        self.assertEqual(result['expired_jobs'], 1)
        self.assertEqual(self.files(), [fresh.temp_file_name])
        self.assertEqual(list(StatementProcessing.objects.all()), [fresh])

    def test_expired_failed_job_is_cleaned(self):
        job = services.create_statement_job(self.user, self.csv())
        services.mark_failed(job, 'parse_error')
        StatementProcessing.objects.filter(pk=job.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        services.cleanup_expired_jobs()
        self.assertEqual(self.files(), [])

    def test_orphan_files_cleaned_only_when_old(self):
        young = Path(self.tmp) / ('a' * 32 + '.csv')
        old = Path(self.tmp) / ('b' * 32 + '.csv')
        stranger = Path(self.tmp) / 'keep-me.txt'
        for p in (young, old, stranger):
            p.write_bytes(b'x')
        past = time.time() - 10 * 3600
        os.utime(old, (past, past))
        services.cleanup_expired_jobs()
        self.assertTrue(young.exists())
        self.assertFalse(old.exists())
        self.assertTrue(stranger.exists())  # never touches files it didn't create

    def test_cleanup_management_command(self):
        job = services.create_statement_job(self.user, self.csv())
        StatementProcessing.objects.filter(pk=job.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        call_command('cleanup_expired_statements', stdout=open(os.devnull, 'w'))
        self.assertEqual(self.files(), [])

    def test_path_traversal_refused(self):
        for bad in ('../x.csv', '/etc/passwd', 'abc.csv', ''):
            with self.assertRaises(ValueError):
                storage.resolve_temp_path(bad)
        self.assertFalse(storage.delete_temp_file('../../etc/passwd'))


class UploadEndpointTests(PrivateStorageTestCase):
    def test_login_required(self):
        r = self.client.post(reverse('statements:upload'), {'statement': self.csv()})
        self.assertEqual(r.status_code, 302)
        self.assertIn('/accounts/login/', r['Location'])
        self.assertEqual(self.files(), [])

    def test_upload_success(self):
        self.client.force_login(self.user)
        r = self.client.post(reverse('statements:upload'), {'statement': self.pdf()})
        self.assertEqual(r.status_code, 201)
        body = r.json()
        self.assertEqual(body['status'], 'uploaded')
        self.assertNotIn('temp_file_name', body)  # internal storage name never exposed
        self.assertEqual(len(self.files()), 1)

    def test_upload_errors_have_proper_status(self):
        self.client.force_login(self.user)
        url = reverse('statements:upload')
        self.assertEqual(self.client.post(url, {}).status_code, 400)
        self.assertEqual(self.client.post(url, {'statement': SimpleUploadedFile('x.txt', b'hi')}).status_code, 400)
        with override_settings(STATEMENT_MAX_UPLOAD_BYTES=10):
            self.assertEqual(self.client.post(url, {'statement': self.csv()}).status_code, 413)

    def test_duplicate_returns_409(self):
        self.client.force_login(self.user)
        url = reverse('statements:upload')
        self.assertEqual(self.client.post(url, {'statement': self.csv()}).status_code, 201)
        self.assertEqual(self.client.post(url, {'statement': self.csv()}).status_code, 409)

    def test_get_not_allowed_on_upload(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('statements:upload')).status_code, 405)

    def test_unauthorized_access_to_other_users_job(self):
        job = services.create_statement_job(self.user, self.csv())
        url = reverse('statements:status', args=[job.id])
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_anonymous_cannot_view_job(self):
        job = services.create_statement_job(self.user, self.csv())
        r = self.client.get(reverse('statements:status', args=[job.id]))
        self.assertEqual(r.status_code, 302)

    def test_service_level_isolation(self):
        from django.http import Http404
        job = services.create_statement_job(self.user, self.csv())
        with self.assertRaises(Http404):
            services.get_job_for_user(self.other, job.id)

    def test_uploads_not_reachable_via_static_or_any_url(self):
        job = services.create_statement_job(self.user, self.csv())
        self.client.force_login(self.user)
        for url in (f'/static/{job.temp_file_name}', f'/media/{job.temp_file_name}', f'/{job.temp_file_name}'):
            self.assertEqual(self.client.get(url).status_code, 404)

    def test_csrf_enforced_on_upload(self):
        from django.test import Client
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.user)
        r = c.post(reverse('statements:upload'), {'statement': self.csv()})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.files(), [])

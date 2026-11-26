"""Business logic for the temporary statement lifecycle."""
import logging

from django.conf import settings
from django.db import transaction
from django.http import Http404
from django.utils import timezone

from . import storage
from .exceptions import DuplicateStatementError
from .models import StatementProcessing
from .validators import validate_statement_upload

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = (StatementProcessing.Status.UPLOADED, StatementProcessing.Status.PROCESSING)


def create_statement_job(user, uploaded_file) -> StatementProcessing:
    """Validate and store an upload privately, then create its processing record."""
    file_type = validate_statement_upload(uploaded_file)
    temp_name, file_hash = storage.save_temp_file(uploaded_file, file_type)

    try:
        with transaction.atomic():
            existing = (
                StatementProcessing.objects.select_for_update()
                .filter(user=user, file_hash=file_hash, status__in=ACTIVE_STATUSES, expires_at__gt=timezone.now())
                .first()
            )
            if existing:
                raise DuplicateStatementError('This statement is already being processed.', existing)
            job = StatementProcessing.objects.create(
                user=user,
                temp_file_name=temp_name,
                file_type=file_type,
                file_size=uploaded_file.size,
                file_hash=file_hash,
            )
    except Exception:
        storage.delete_temp_file(temp_name)
        raise

    logger.info('Statement job %s created (%s)', job.id, file_type)  # no financial data in logs
    return job


def get_job_for_user(user, job_id) -> StatementProcessing:
    """Return the user's own job, or 404. Other users' jobs are indistinguishable from missing ones."""
    try:
        return StatementProcessing.objects.get(pk=job_id, user=user)
    except (StatementProcessing.DoesNotExist, ValueError, TypeError):
        raise Http404('Statement not found.')


def delete_statement_job(job: StatementProcessing) -> None:
    """Delete the physical file and the temporary record."""
    storage.delete_temp_file(job.temp_file_name)
    job.delete()


def mark_failed(job: StatementProcessing, error_code: str) -> None:
    """Record a failure. The private file is deleted right away; the small status record
    stays until it expires so the user can be told what went wrong."""
    storage.delete_temp_file(job.temp_file_name)
    job.temp_file_name = ''
    job.status = StatementProcessing.Status.FAILED
    job.error_code = error_code[:50]
    job.save(update_fields=['status', 'error_code', 'temp_file_name'])


def cleanup_expired_jobs() -> dict:
    """Delete expired jobs (file + record) and orphaned files. Safe to run repeatedly."""
    expired = list(StatementProcessing.objects.filter(expires_at__lte=timezone.now()))
    for job in expired:
        delete_statement_job(job)
    orphans = storage.remove_orphan_files(settings.STATEMENT_EXPIRY_MINUTES * 60)
    return {'expired_jobs': len(expired), 'orphan_files': orphans}

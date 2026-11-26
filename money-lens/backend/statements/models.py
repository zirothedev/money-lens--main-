import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


def default_expiry():
    return timezone.now() + timedelta(minutes=settings.STATEMENT_EXPIRY_MINUTES)


class StatementProcessing(models.Model):
    """TEMPORARY record of an uploaded statement being processed.

    This row and its physical file are deleted as soon as a report is saved, or
    when it expires. It must never be treated as persistent user data.
    """

    class Status(models.TextChoices):
        UPLOADED = 'uploaded', 'Uploaded'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    class FileType(models.TextChoices):
        PDF = 'pdf', 'PDF'
        CSV = 'csv', 'CSV'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='statement_jobs')
    # Name of the file inside PRIVATE_UPLOAD_ROOT (never a user-supplied name).
    temp_file_name = models.CharField(max_length=100, blank=True)
    file_type = models.CharField(max_length=3, choices=FileType.choices)
    file_size = models.PositiveBigIntegerField()
    # SHA-256 of the upload; only used to block duplicate processing while the job is alive.
    file_hash = models.CharField(max_length=64, db_index=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.UPLOADED, db_index=True)
    error_code = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=default_expiry, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.id} ({self.status})'

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

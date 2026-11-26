import uuid

from django.conf import settings
from django.db import models


class Report(models.Model):
    """Persistent report. Holds only what is needed to display it, never the original statement."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reports')
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, blank=True)
    total_received = models.DecimalField(max_digits=16, decimal_places=2)
    total_sent = models.DecimalField(max_digits=16, decimal_places=2)
    incoming_count = models.PositiveIntegerField()
    outgoing_count = models.PositiveIntegerField()
    unidentified_total = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    unidentified_count = models.PositiveIntegerField(default=0)
    # Hash of the normalized transactions; blocks saving the same statement twice per user.
    fingerprint = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['user', 'fingerprint'], name='unique_report_per_user_statement'),
        ]

    def __str__(self):
        return f'Report {self.id}'


class ReportRecipient(models.Model):
    """An identifiable recipient and their outgoing totals within one report."""

    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name='recipients')
    name = models.CharField(max_length=255)
    total_sent = models.DecimalField(max_digits=16, decimal_places=2)
    transaction_count = models.PositiveIntegerField()
    rank = models.PositiveIntegerField()

    class Meta:
        ordering = ['rank']
        constraints = [
            models.UniqueConstraint(fields=['report', 'name'], name='unique_recipient_per_report'),
        ]

    def __str__(self):
        return f'{self.name}: {self.total_sent}'


class ReportTransaction(models.Model):
    class Direction(models.TextChoices):
        IN = 'in', 'Money in'
        OUT = 'out', 'Money out'

    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name='transactions')
    # Set only for outgoing transactions with an identified recipient.
    recipient = models.ForeignKey(ReportRecipient, null=True, blank=True, on_delete=models.CASCADE, related_name='transactions')
    date = models.DateField()
    amount = models.DecimalField(max_digits=16, decimal_places=2)  # always positive
    direction = models.CharField(max_length=3, choices=Direction.choices)
    # Name exactly as found in the statement (recipient for out, sender for in); None if not identifiable.
    counterparty = models.CharField(max_length=255, null=True, blank=True)
    narration = models.TextField(blank=True, default='')
    reference = models.CharField(max_length=100, blank=True, default='')
    # Bank/wallet the statement says the money went through (e.g. OPAY); empty when it doesn't say.
    via = models.CharField(max_length=100, blank=True, default='')

    class Meta:
        ordering = ['date', 'id']

    def __str__(self):
        return f'{self.direction} {self.amount} on {self.date}'

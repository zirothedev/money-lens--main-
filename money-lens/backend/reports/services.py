"""Persisting reports and running the statement -> report lifecycle."""
import logging

from django.db import IntegrityError, transaction
from django.http import Http404

from processing.exceptions import StatementExtractionError
from processing.pipeline import extract_statement
from statements import services as statement_services
from statements import storage
from statements.models import StatementProcessing

from .engine import ReportData, ReportError, build_report_data
from .models import Report, ReportRecipient, ReportTransaction

logger = logging.getLogger(__name__)


class ProcessingNotAllowed(Exception):
    """The statement job is already being (or has been) processed, or has expired."""


@transaction.atomic
def save_report(user, data: ReportData) -> Report:
    """Persist report data. Saving the same statement twice returns the existing report."""
    existing = Report.objects.filter(user=user, fingerprint=data.fingerprint).first()
    if existing:
        return existing

    report = Report.objects.create(
        user=user, period_start=data.period_start, period_end=data.period_end, currency=data.currency,
        total_received=data.total_received, total_sent=data.total_sent,
        incoming_count=data.incoming_count, outgoing_count=data.outgoing_count,
        unidentified_total=data.unidentified_total, unidentified_count=data.unidentified_count,
        fingerprint=data.fingerprint,
    )

    by_transaction_id: dict[int, ReportRecipient] = {}
    for summary in data.recipients:
        recipient = ReportRecipient.objects.create(
            report=report, name=summary.name, total_sent=summary.total_sent,
            transaction_count=summary.transaction_count, rank=summary.rank)
        for tx in summary.transactions:
            by_transaction_id[id(tx)] = recipient

    ReportTransaction.objects.bulk_create([
        ReportTransaction(
            report=report,
            recipient=by_transaction_id.get(id(tx)),
            date=tx.date,
            amount=tx.amount,
            direction=ReportTransaction.Direction.OUT if tx.is_outgoing else ReportTransaction.Direction.IN,
            counterparty=tx.recipient if tx.is_outgoing else tx.sender,
            narration=tx.narration,
            reference=tx.reference,
            via=tx.via,
        )
        for tx in data.transactions
    ])
    return report


def generate_report_for_job(job: StatementProcessing) -> Report:
    """Process a temporary statement into a saved report, then delete every temporary trace."""
    claimed = StatementProcessing.objects.filter(
        pk=job.pk, status=StatementProcessing.Status.UPLOADED).update(status=StatementProcessing.Status.PROCESSING)
    if not claimed:
        raise ProcessingNotAllowed('This statement has already been processed or is being processed.')
    job.refresh_from_db()
    if job.is_expired:
        statement_services.mark_failed(job, 'expired')
        raise ProcessingNotAllowed('This upload has expired. Please upload the statement again.')

    try:
        result = extract_statement(storage.resolve_temp_path(job.temp_file_name), job.file_type)
        stated = (result.period_start, result.period_end) if result.period_start and result.period_end else None
        report = save_report(job.user, build_report_data(result.transactions, stated_period=stated))
    except (StatementExtractionError, ReportError) as exc:
        statement_services.mark_failed(job, exc.code)
        raise
    except Exception as exc:
        # Class name only (never the message: it could contain statement data). The one exception is a
        # missing package, whose name is safe and tells the developer exactly what to install.
        missing = f" - missing package: {exc.name}" if isinstance(exc, ImportError) and exc.name else ''
        logger.error('Report generation failed for job %s (%s)%s', job.id, type(exc).__name__, missing)
        statement_services.mark_failed(job, 'internal_error')
        raise

    statement_services.delete_statement_job(job)  # file + temporary record, immediately
    logger.info('Report %s generated; statement job %s deleted', report.id, job.id)
    return report


def get_report_for_user(user, report_id) -> Report:
    try:
        return Report.objects.get(pk=report_id, user=user)
    except (Report.DoesNotExist, ValueError, TypeError):
        raise Http404('Report not found.')


def list_reports_for_user(user):
    return Report.objects.filter(user=user)


def report_to_dict(report: Report) -> dict:
    """JSON-safe representation (Decimals as strings so no precision is lost)."""
    def money(v):
        return str(v)

    recipients = list(report.recipients.all())
    transactions = list(report.transactions.select_related('recipient'))
    return {
        'id': str(report.id),
        'period_start': report.period_start.isoformat() if report.period_start else None,
        'period_end': report.period_end.isoformat() if report.period_end else None,
        'currency': report.currency,
        'total_received': money(report.total_received),
        'total_sent': money(report.total_sent),
        'incoming_count': report.incoming_count,
        'outgoing_count': report.outgoing_count,
        'recipients': [
            {
                'rank': r.rank, 'name': r.name, 'total_sent': money(r.total_sent),
                'transaction_count': r.transaction_count,
                'transactions': [
                    {'date': t.date.isoformat(), 'amount': money(t.amount), 'narration': t.narration}
                    for t in transactions if t.recipient_id == r.id
                ],
            }
            for r in recipients
        ],
        'unidentified': {'total_sent': money(report.unidentified_total), 'transaction_count': report.unidentified_count},
        'transactions': [
            {
                'date': t.date.isoformat(), 'amount': money(t.amount), 'direction': t.direction,
                'counterparty': t.counterparty, 'narration': t.narration, 'via': t.via,
            }
            for t in transactions
        ],
    }

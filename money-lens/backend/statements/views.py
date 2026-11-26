from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from processing.exceptions import StatementExtractionError
from reports.engine import ReportError
from reports.services import ProcessingNotAllowed, generate_report_for_job

from . import services
from .exceptions import DuplicateStatementError, StatementUploadError


def _job_payload(job) -> dict:
    return {
        'id': str(job.id),
        'status': job.status,
        'file_type': job.file_type,
        'file_size': job.file_size,
        'expires_at': job.expires_at.isoformat(),
    }


@login_required
@require_POST
def upload_statement(request):
    try:
        job = services.create_statement_job(request.user, request.FILES.get('statement'))
    except DuplicateStatementError as exc:
        return JsonResponse({'error': exc.code, 'message': exc.message, 'job': _job_payload(exc.existing_job)}, status=409)
    except StatementUploadError as exc:
        status = 413 if exc.code == 'file_too_large' else 400
        return JsonResponse({'error': exc.code, 'message': exc.message}, status=status)
    return JsonResponse(_job_payload(job), status=201)


@login_required
@require_GET
def job_status(request, job_id):
    job = services.get_job_for_user(request.user, job_id)
    return JsonResponse(_job_payload(job))


@login_required
@require_POST
def process_statement(request, job_id):
    """Synchronous MVP processing: statement -> saved report -> temporary data deleted."""
    job = services.get_job_for_user(request.user, job_id)
    try:
        report = generate_report_for_job(job)
    except ProcessingNotAllowed as exc:
        return JsonResponse({'error': 'not_allowed', 'message': str(exc)}, status=409)
    except (StatementExtractionError, ReportError) as exc:
        return JsonResponse({'error': exc.code, 'message': exc.message}, status=422)
    except Exception:
        return JsonResponse({'error': 'internal_error', 'message': 'Something went wrong while processing the statement.'}, status=500)
    return JsonResponse({'report_id': str(report.id)})

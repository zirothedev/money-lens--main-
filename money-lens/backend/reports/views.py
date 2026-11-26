from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from . import presenters, services


@login_required
@require_GET
def report_list(request):
    reports = services.list_reports_for_user(request.user)
    return JsonResponse({'reports': [
        {'id': str(r.id), 'period_start': r.period_start and r.period_start.isoformat(),
         'period_end': r.period_end and r.period_end.isoformat(), 'created_at': r.created_at.isoformat()}
        for r in reports
    ]})


@login_required
@require_GET
def report_data(request, report_id):
    report = services.get_report_for_user(request.user, report_id)
    return JsonResponse(services.report_to_dict(report))


# --- HTML pages (Phase 5). They read the same service layer as the JSON endpoints above. ---

@login_required
@require_GET
def report_detail(request, report_id):
    """The report dashboard. Other users' reports and missing ones look identical (404 page)."""
    try:
        report = services.get_report_for_user(request.user, report_id)
    except Http404:
        return render(request, 'reports/not_found.html', {'active_nav': 'reports'}, status=404)
    context = presenters.build_report_context(report)
    context['active_nav'] = 'reports'
    return render(request, 'report.html', context)


@login_required
@require_GET
def report_history(request):
    context = presenters.build_history_context(services.list_reports_for_user(request.user))
    context['active_nav'] = 'reports'
    return render(request, 'reports/history.html', context)

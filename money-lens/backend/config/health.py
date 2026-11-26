from django.db import connection
from django.http import JsonResponse


def health_check(request):
    """Liveness + database connectivity. Exposes no sensitive information."""
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        db = 'ok'
    except Exception:
        db = 'error'
    status = 200 if db == 'ok' else 503
    return JsonResponse({'status': 'ok' if db == 'ok' else 'error', 'database': db}, status=status)

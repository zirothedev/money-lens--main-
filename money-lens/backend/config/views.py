from django.conf import settings
from django.shortcuts import render


def _size_label(num_bytes: int) -> str:
    mb = num_bytes / (1024 * 1024)
    return f'{mb:g} MB'


def home(request):
    """Landing page. Only supplies the limits the upload modal shows; the server still validates."""
    return render(request, 'home.html', {
        'active_nav': 'home',
        'max_upload_bytes': settings.STATEMENT_MAX_UPLOAD_BYTES,
        'max_upload_label': _size_label(settings.STATEMENT_MAX_UPLOAD_BYTES),
    })

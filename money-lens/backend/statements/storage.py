"""Private, temporary file storage for uploaded statements.

Files live in settings.PRIVATE_UPLOAD_ROOT, outside static/media, under
server-generated names. Nothing here ever serves a file over HTTP.
"""
import hashlib
import os
import re
import time
import uuid
from pathlib import Path

from django.conf import settings

_SAFE_NAME = re.compile(r'^[0-9a-f]{32}\.(pdf|csv)$')


def private_root() -> Path:
    root = Path(settings.PRIVATE_UPLOAD_ROOT)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def generate_temp_name(file_type: str) -> str:
    return f'{uuid.uuid4().hex}.{file_type}'


def resolve_temp_path(temp_file_name: str) -> Path:
    """Map a stored name to an absolute path, refusing anything outside the private root."""
    if not _SAFE_NAME.match(temp_file_name or ''):
        raise ValueError('Unsafe temporary file name.')
    root = private_root().resolve()
    path = (root / temp_file_name).resolve()
    if path.parent != root:
        raise ValueError('Path escapes private upload root.')
    return path


def save_temp_file(uploaded_file, file_type: str) -> tuple[str, str]:
    """Write the upload to private storage. Returns (temp_file_name, sha256_hex)."""
    name = generate_temp_name(file_type)
    path = resolve_temp_path(name)
    digest = hashlib.sha256()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'wb') as out:
            for chunk in uploaded_file.chunks():
                digest.update(chunk)
                out.write(chunk)
    except Exception:
        delete_temp_file(name)
        raise
    return name, digest.hexdigest()


def delete_temp_file(temp_file_name: str) -> bool:
    """Delete a temporary file. Returns True if a file was removed."""
    if not temp_file_name:
        return False
    try:
        path = resolve_temp_path(temp_file_name)
    except ValueError:
        return False
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False


def open_temp_file(temp_file_name: str):
    """Open a temporary file for server-side processing (binary mode)."""
    return open(resolve_temp_path(temp_file_name), 'rb')


def remove_orphan_files(max_age_seconds: int) -> int:
    """Delete files in private storage that are older than max_age and have no DB record."""
    from .models import StatementProcessing

    known = set(StatementProcessing.objects.values_list('temp_file_name', flat=True))
    removed = 0
    cutoff = time.time() - max_age_seconds
    for path in private_root().iterdir():
        if not _SAFE_NAME.match(path.name) or path.name in known:
            continue
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except FileNotFoundError:
            continue
    return removed

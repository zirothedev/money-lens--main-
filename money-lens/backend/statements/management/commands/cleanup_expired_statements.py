from django.core.management.base import BaseCommand

from statements.services import cleanup_expired_jobs


class Command(BaseCommand):
    help = 'Delete expired temporary statement jobs and their private files.'

    def handle(self, *args, **options):
        result = cleanup_expired_jobs()
        self.stdout.write(f"Removed {result['expired_jobs']} expired job(s) and {result['orphan_files']} orphan file(s).")

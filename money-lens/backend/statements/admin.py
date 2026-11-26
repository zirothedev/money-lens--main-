from django.contrib import admin

from .models import StatementProcessing


@admin.register(StatementProcessing)
class StatementProcessingAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'file_type', 'status', 'created_at', 'expires_at')
    list_filter = ('status', 'file_type')
    # Deliberately hide file name/hash: admins don't need them.
    exclude = ('temp_file_name', 'file_hash')
    readonly_fields = ('id', 'created_at')

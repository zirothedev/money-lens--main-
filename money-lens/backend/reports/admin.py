from django.contrib import admin

from .models import Report, ReportRecipient, ReportTransaction


class RecipientInline(admin.TabularInline):
    model = ReportRecipient
    extra = 0
    can_delete = False


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'period_start', 'period_end', 'created_at')
    inlines = [RecipientInline]
    readonly_fields = ('id', 'fingerprint', 'created_at')


admin.site.register(ReportTransaction)

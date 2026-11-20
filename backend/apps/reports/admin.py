from django.contrib import admin

from apps.reports.models import Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    """Denúncias recebidas (US69/US70). A análise pelo admin fica na US74."""

    list_display = (
        "id",
        "created_at",
        "reporter",
        "target_type",
        "company",
        "worker",
        "reason",
        "status",
    )
    list_filter = ("status", "target_type", "reason")
    readonly_fields = (
        "reporter",
        "reporter_company",
        "target_type",
        "company",
        "vacancy",
        "worker",
        "assignment",
        "reason",
        "description",
        "status",
        "created_at",
        "decided_at",
        "decided_by",
        "decision",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

from django.contrib import admin

from apps.core.suspension_admin import SuspensionAdminMixin
from apps.workers.models import Worker, WorkerDocument


class WorkerDocumentInline(admin.TabularInline):
    model = WorkerDocument
    extra = 0


@admin.register(Worker)
class WorkerAdmin(SuspensionAdminMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "full_name",
        "masked_cpf",
        "verification_status",
        "suspended_until",
        "suspension_actions",
    )
    list_filter = ("verification_status",)
    search_fields = ("full_name",)
    # CPF e PIX nunca aparecem em claro; status e suspensão só mudam pelo serviço de domínio.
    exclude = ("cpf", "pix_key")
    readonly_fields = (
        "verification_status",
        "suspended_until",
        "suspension_indefinite",
        "masked_cpf",
        "masked_pix_key",
    )
    inlines = [WorkerDocumentInline]

    @admin.display(description="CPF")
    def masked_cpf(self, obj):
        return obj.masked_cpf

    @admin.display(description="Chave PIX")
    def masked_pix_key(self, obj):
        return obj.masked_pix_key

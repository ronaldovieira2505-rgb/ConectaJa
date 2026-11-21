from django.contrib import admin
from django.utils.html import format_html

from apps.core.admin_files import private_file_link
from apps.core.suspension_admin import SuspensionAdminMixin
from apps.reports import review
from apps.workers.models import Worker, WorkerDocument


class WorkerDocumentInline(admin.TabularInline):
    """Documentos só para conferência: o envio e a troca passam pela API (validação da imagem)."""

    model = WorkerDocument
    extra = 0
    fields = ("kind", "file_link", "uploaded_at")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Arquivo")
    def file_link(self, obj):
        if not obj.pk or not obj.file:
            return "—"
        return private_file_link(f"/api/workers/{obj.worker_id}/documents/{obj.kind}/")


@admin.register(Worker)
class WorkerAdmin(SuspensionAdminMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "full_name",
        "masked_cpf",
        "verification_status",
        "suspended_until",
        "upheld_reports",
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
        "upheld_reports",
    )
    inlines = [WorkerDocumentInline]

    @admin.display(description="Denúncias procedentes")
    def upheld_reports(self, obj):
        """Alerta com 3 ou mais denúncias procedentes (US74, decisão do PO)."""
        count = review.upheld_count(obj)
        if count >= review.UPHELD_ALERT_THRESHOLD:
            return format_html('<strong style="color:#b00020">⚠ {}</strong>', count)
        return count

    @admin.display(description="CPF")
    def masked_cpf(self, obj):
        return obj.masked_cpf

    @admin.display(description="Chave PIX")
    def masked_pix_key(self, obj):
        return obj.masked_pix_key

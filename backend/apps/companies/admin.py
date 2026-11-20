from django.contrib import admin
from django.utils.html import format_html

from apps.companies.models import Company, CompanyMember
from apps.core.suspension_admin import SuspensionAdminMixin
from apps.reports import review


class CompanyMemberInline(admin.TabularInline):
    model = CompanyMember
    extra = 0


@admin.register(Company)
class CompanyAdmin(SuspensionAdminMixin, admin.ModelAdmin):
    list_display = (
        "legal_name",
        "trade_name",
        "cnpj",
        "verification_status",
        "data_unverified",
        "suspended_until",
        "upheld_reports",
        "suspension_actions",
        "created_at",
    )
    list_filter = ("verification_status", "data_unverified", "tax_regime")
    search_fields = ("legal_name", "trade_name", "cnpj")
    # Status e suspensão só mudam pelo serviço de domínio (grava a auditoria).
    readonly_fields = (
        "verification_status",
        "suspended_until",
        "suspension_indefinite",
        "upheld_reports",
    )
    inlines = [CompanyMemberInline]

    @admin.display(description="Denúncias procedentes")
    def upheld_reports(self, obj):
        """Alerta com 3 ou mais denúncias procedentes (US74, decisão do PO)."""
        count = review.upheld_count(obj)
        if count >= review.UPHELD_ALERT_THRESHOLD:
            return format_html('<strong style="color:#b00020">⚠ {}</strong>', count)
        return count

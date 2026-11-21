from django.contrib import admin
from django.utils.html import format_html

from apps.companies.models import Company, CompanyMember
from apps.companies.profile_views import logo_url
from apps.core.admin_files import private_file_link
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
        "premium",
        "suspension_actions",
        "created_at",
    )
    list_filter = ("verification_status", "data_unverified", "tax_regime", "premium")
    search_fields = ("legal_name", "trade_name", "cnpj")
    # Status e suspensão só mudam pelo serviço de domínio (grava a auditoria).
    # A logo fica no armazenamento privado: aparece como link e só se troca pela API.
    exclude = ("logo",)
    readonly_fields = (
        "logo_link",
        "verification_status",
        "suspended_until",
        "suspension_indefinite",
        "upheld_reports",
        "premium",
        "premium_since",
    )
    inlines = [CompanyMemberInline]

    @admin.display(description="Denúncias procedentes")
    def upheld_reports(self, obj):
        """Alerta com 3 ou mais denúncias procedentes (US74, decisão do PO)."""
        count = review.upheld_count(obj)
        if count >= review.UPHELD_ALERT_THRESHOLD:
            return format_html('<strong style="color:#b00020">⚠ {}</strong>', count)
        return count

    @admin.display(description="Logo")
    def logo_link(self, obj):
        return private_file_link(logo_url(obj), "Ver logo")

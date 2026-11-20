from django.contrib import admin

from apps.companies.models import Company, CompanyMember
from apps.core.suspension_admin import SuspensionAdminMixin


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
        "suspension_actions",
        "created_at",
    )
    list_filter = ("verification_status", "data_unverified", "tax_regime")
    search_fields = ("legal_name", "trade_name", "cnpj")
    # Status e suspensão só mudam pelo serviço de domínio (grava a auditoria).
    readonly_fields = ("verification_status", "suspended_until", "suspension_indefinite")
    inlines = [CompanyMemberInline]

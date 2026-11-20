from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.template.response import TemplateResponse
from django.urls import path

from apps.accounts.models import Role
from apps.companies.models import Company
from apps.core.admin import ReadOnlyAdmin, _parse_date
from apps.payments.finance import compute_finance, default_period
from apps.payments.models import Custody, LedgerEntry


@admin.register(Custody)
class CustodyAdmin(admin.ModelAdmin):
    """Também hospeda a página “Financeiro” (US77)."""

    change_list_template = "admin/payments/custody_changelist.html"
    list_display = ("id", "vacancy", "amount_cents", "status", "psp_reference")
    list_filter = ("status",)
    readonly_fields = ("idempotency_key", "psp_reference")

    def get_urls(self):
        custom = [
            path(
                "financeiro/",
                self.admin_site.admin_view(self.finance_view),
                name="finance",
            )
        ]
        return custom + super().get_urls()

    def finance_view(self, request):
        if request.user.role != Role.ADMIN:
            raise PermissionDenied
        default_start, default_end = default_period()
        errors = []
        start = _parse_date(request.GET.get("inicio"), default_start, errors)
        end = _parse_date(request.GET.get("fim"), default_end, errors)
        if start > end:
            errors.append("A data inicial não pode ser posterior à final.")
            start, end = default_start, default_end
        company_id = None
        raw_company = request.GET.get("empresa", "")
        if raw_company:
            if raw_company.isdecimal() and Company.objects.filter(pk=raw_company).exists():
                company_id = int(raw_company)
            else:
                errors.append("Empresa inválida.")
        totals, rows = compute_finance(start, end, company_id=company_id)
        context = {
            **self.admin_site.each_context(request),
            "title": "Financeiro",
            "start": start,
            "end": end,
            "company_id": company_id,
            "companies": Company.objects.order_by("legal_name"),
            "errors": errors,
            "totals": totals,
            "rows": rows,
        }
        return TemplateResponse(request, "admin/payments/finance.html", context)


@admin.register(LedgerEntry)
class LedgerEntryAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "custody", "assignment", "kind", "amount_cents")
    list_filter = ("kind",)

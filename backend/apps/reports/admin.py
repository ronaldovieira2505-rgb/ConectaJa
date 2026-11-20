"""Painel "Denúncias" (US74): lista com filtros e a tela de análise de cada denúncia."""

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from apps.accounts.models import Role
from apps.core.exceptions import DomainError
from apps.core.suspension import MAX_DAYS, MIN_DAYS, suspend_account
from apps.reports import review
from apps.reports.models import Report


class OverdueReportFilter(admin.SimpleListFilter):
    title = "prazo"
    parameter_name = "atrasadas"

    def lookups(self, request, model_admin):
        return [("sim", "Abertas há mais de 48 h")]

    def queryset(self, request, queryset):
        if self.value() != "sim":
            return queryset
        limit = timezone.now() - review.OPEN_ALERT_AFTER
        return queryset.filter(status__in=Report.OPEN_STATUSES, created_at__lt=limit)


class ConcludeForm(forms.Form):
    result = forms.ChoiceField(
        label="Conclusão",
        choices=[("procedente", "Procedente"), ("improcedente", "Improcedente")],
        widget=forms.RadioSelect,
    )
    decision = forms.CharField(
        label="Parecer (obrigatório)",
        widget=forms.Textarea(attrs={"rows": 4, "cols": 60}),
        error_messages={"required": "O parecer é obrigatório."},
    )
    suspend = forms.BooleanField(
        label="Suspender a conta do denunciado (só se procedente)", required=False
    )
    days = forms.IntegerField(
        label="Dias de suspensão", min_value=MIN_DAYS, max_value=MAX_DAYS, required=False
    )
    indefinite = forms.BooleanField(label="Por tempo indeterminado", required=False)

    def clean_decision(self):
        decision = self.cleaned_data["decision"].strip()
        if not decision:
            raise forms.ValidationError("O parecer é obrigatório.")
        return decision

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("suspend"):
            return cleaned
        if cleaned.get("result") != "procedente":
            raise forms.ValidationError("Só é possível suspender quando a denúncia é procedente.")
        if cleaned.get("indefinite") and cleaned.get("days") is not None:
            raise forms.ValidationError("Informe os dias ou tempo indeterminado, não os dois.")
        if not cleaned.get("indefinite") and cleaned.get("days") is None:
            raise forms.ValidationError("Informe os dias de suspensão ou tempo indeterminado.")
        return cleaned


def reporter_label(report):
    """Quem denunciou, como o admin precisa ver (o denunciado nunca vê)."""
    if report.reporter_company_id:
        return f"{report.reporter_company} (empresa)"
    worker = getattr(report.reporter, "worker", None)
    if worker is not None:
        return f"{worker.full_name} (prestador)"
    return report.reporter.get_username()


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "sent_at",
        "reporter_display",
        "target_display",
        "reason",
        "status",
        "review_link",
    )
    list_filter = ("status", "target_type", "reason", OverdueReportFilter)
    list_select_related = ("reporter", "reporter_company", "company", "vacancy", "worker")
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

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Data", ordering="created_at")
    def sent_at(self, obj):
        text = f"{timezone.localtime(obj.created_at):%d/%m/%Y %H:%M}"
        if review.is_overdue(obj):
            return format_html('<strong style="color:#b00020">⚠ {} (mais de 48 h)</strong>', text)
        return text

    @admin.display(description="Quem denunciou")
    def reporter_display(self, obj):
        return reporter_label(obj)

    @admin.display(description="Alvo")
    def target_display(self, obj):
        return obj.target_label

    @admin.display(description="Análise")
    def review_link(self, obj):
        url = reverse("admin:reports_report_review", args=[obj.pk])
        label = "Analisar" if obj.status in Report.OPEN_STATUSES else "Ver"
        return format_html('<a href="{}">{}</a>', url, label)

    def get_urls(self):
        custom = [
            path(
                "<int:pk>/analisar/",
                self.admin_site.admin_view(self.review_view),
                name="reports_report_review",
            )
        ]
        return custom + super().get_urls()

    def _suspend_url(self, subject):
        if subject is None:
            return None
        info = subject._meta.app_label, subject._meta.model_name
        return reverse("admin:%s_%s_suspend" % info, args=[subject.pk])

    def _conclude(self, request, report, form):
        data = form.cleaned_data
        upheld = data["result"] == "procedente"
        report = review.conclude(
            report, actor=request.user, upheld=upheld, decision=data["decision"]
        )
        self.message_user(request, f"Denúncia concluída como {data['result']}.", messages.SUCCESS)
        if not data.get("suspend"):
            return
        subject = review.target_subject(report)
        try:
            suspend_account(
                subject,
                actor=request.user,
                reason=f"Denúncia #{report.pk} procedente: {data['decision']}",
                days=data.get("days"),
                indefinite=bool(data.get("indefinite")),
            )
        except DomainError as error:
            self.message_user(request, f"A conta não foi suspensa: {error}", messages.WARNING)
        else:
            self.message_user(request, "Conta do denunciado suspensa.", messages.SUCCESS)

    def review_view(self, request, pk):
        if request.user.role != Role.ADMIN:
            raise PermissionDenied
        report = get_object_or_404(
            Report.objects.select_related(
                "reporter", "reporter_company", "company", "vacancy", "worker", "assignment"
            ),
            pk=pk,
        )
        action = request.POST.get("action")
        form = ConcludeForm(request.POST if action == "conclude" else None)
        if request.method == "POST":
            try:
                if action == "start":
                    review.start_review(report, actor=request.user)
                    self.message_user(
                        request, "Denúncia marcada como em análise.", messages.SUCCESS
                    )
                    return HttpResponseRedirect(request.path)
                if action == "conclude" and form.is_valid():
                    self._conclude(request, report, form)
                    return HttpResponseRedirect(request.path)
            except DomainError as error:
                self.message_user(request, str(error), messages.ERROR)
                return HttpResponseRedirect(request.path)
        vacancy = report.vacancy or (report.assignment.vacancy if report.assignment_id else None)
        subject = review.target_subject(report)
        context = {
            **self.admin_site.each_context(request),
            "title": f"Denúncia #{report.pk}",
            "report": report,
            "reporter": reporter_label(report),
            "overdue": review.is_overdue(report),
            "history": review.target_history(report),
            "vacancy": vacancy,
            "vacancy_history_url": vacancy
            and reverse("admin:vacancies_vacancy_full_history", args=[vacancy.pk]),
            "is_open": report.status in Report.OPEN_STATUSES,
            "can_start": report.status == Report.Status.OPEN,
            "form": form,
            "suspend_url": self._suspend_url(subject),
            "subject_suspended": subject is not None and subject.is_suspended(timezone.now()),
            "changelist_url": reverse("admin:reports_report_changelist"),
        }
        return TemplateResponse(request, "admin/reports/review.html", context)

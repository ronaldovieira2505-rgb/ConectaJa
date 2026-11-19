import logging
from datetime import timedelta

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseBadRequest, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from apps.core.exceptions import DomainError
from apps.core.models import StateTransition
from apps.vacancies import assignment_services as assignments
from apps.vacancies import history
from apps.vacancies.models import Application, Assignment, Review, Vacancy, VacancyChange
from integrations.payments import PaymentGatewayError

logger = logging.getLogger(__name__)

# Contestações abertas há mais tempo que isto são destacadas (docs/maquina-de-estados.md §3).
CONTEST_ALERT_AFTER = timedelta(hours=48)


@admin.register(VacancyChange)
class VacancyChangeAdmin(admin.ModelAdmin):
    list_display = ("vacancy", "field", "old_value", "new_value", "user", "changed_at")
    list_filter = ("field",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Vacancy)
class VacancyAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "starts_at", "positions", "status", "reopened")
    list_filter = ("status", "category")
    search_fields = ("title",)
    readonly_fields = ("status", "reopened")

    def get_urls(self):
        custom = [
            path(
                "<int:pk>/historico/",
                self.admin_site.admin_view(self.history_view),
                name="vacancies_vacancy_full_history",
            )
        ]
        return custom + super().get_urls()

    def history_view(self, request, pk):
        if not request.user.has_perm("vacancies.view_vacancy"):
            raise PermissionDenied
        vacancy = Vacancy.objects.select_related("company").filter(pk=pk).first()
        if vacancy is None:
            raise Http404
        context = {
            **self.admin_site.each_context(request),
            "title": f"Histórico completo — {vacancy.title}",
            "vacancy": vacancy,
            "events": history.build_history(vacancy),
            "summary": history.financial_summary(vacancy),
        }
        return TemplateResponse(request, "admin/vacancies/vacancy_history.html", context)


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("id", "vacancy", "worker", "status", "created_at")
    list_filter = ("status",)
    readonly_fields = ("status",)


def _contested_at(assignment):
    entry = (
        StateTransition.objects.filter(
            entity_type="Assignment",
            entity_id=assignment.pk,
            to_state=Assignment.Status.CONTESTED,
        )
        .order_by("-created_at", "-id")
        .first()
    )
    return entry.created_at if entry else None


class OverdueContestFilter(admin.SimpleListFilter):
    title = "contestação"
    parameter_name = "contestacao"

    def lookups(self, request, model_admin):
        return (("atrasada", "Abertas há mais de 48 h"),)

    def queryset(self, request, queryset):
        if self.value() != "atrasada":
            return queryset
        old_ids = StateTransition.objects.filter(
            entity_type="Assignment",
            to_state=Assignment.Status.CONTESTED,
            created_at__lte=timezone.now() - CONTEST_ALERT_AFTER,
        ).values("entity_id")
        return queryset.filter(status=Assignment.Status.CONTESTED, pk__in=old_ids)


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "vacancy",
        "worker",
        "status",
        "check_in_at",
        "check_out_at",
        "contest_info",
        "worker_response",
        "decision",
    )
    list_filter = ("status", OverdueContestFilter)
    readonly_fields = ("status", "contest_response", "contest_response_at")

    @admin.display(description="Contestação")
    def contest_info(self, obj):
        if obj.status != Assignment.Status.CONTESTED:
            return "—"
        since = _contested_at(obj)
        if since is None:
            return "Contestada"
        text = f"Contestada em {timezone.localtime(since):%d/%m/%Y %H:%M}"
        if timezone.now() - since > CONTEST_ALERT_AFTER:
            return format_html('<strong style="color:#b00020">⚠ {} (mais de 48 h)</strong>', text)
        return text

    @admin.display(description="Resposta do prestador")
    def worker_response(self, obj):
        if obj.contest_response_at is None:
            return "—"
        sent = f"{timezone.localtime(obj.contest_response_at):%d/%m/%Y %H:%M}"
        return format_html("{} <small>({})</small>", obj.contest_response, sent)

    @admin.display(description="Decisão")
    def decision(self, obj):
        if obj.status != Assignment.Status.CONTESTED:
            return ""
        url = reverse("admin:vacancies_assignment_resolve_contest", args=[obj.pk])
        return format_html('<a href="{}">Decidir contestação</a>', url)

    def get_urls(self):
        custom = [
            path(
                "<int:pk>/resolver-contestacao/",
                self.admin_site.admin_view(self.resolve_contest_view),
                name="vacancies_assignment_resolve_contest",
            )
        ]
        return custom + super().get_urls()

    def resolve_contest_view(self, request, pk):
        if not request.user.has_perm("vacancies.change_assignment"):
            raise PermissionDenied
        assignment = (
            Assignment.objects.select_related("vacancy__company", "worker__user")
            .filter(pk=pk)
            .first()
        )
        if assignment is None:
            raise Http404
        changelist = reverse("admin:vacancies_assignment_changelist")
        if request.method == "POST":
            decision = request.POST.get("decision")
            if decision not in ("worker", "company"):
                return HttpResponseBadRequest("Decisão inválida.")
            try:
                assignment = assignments.resolve_contest(
                    assignment,
                    in_favor_of_worker=decision == "worker",
                    reason=request.POST.get("reason", ""),
                    actor=request.user,
                )
            except DomainError as error:
                self.message_user(request, str(error), messages.ERROR)
                return HttpResponseRedirect(request.path)
            except PaymentGatewayError as error:
                self.message_user(request, str(error), messages.ERROR)
                return HttpResponseRedirect(request.path)
            if decision == "worker":
                try:
                    assignments.settle(assignment)
                except (DomainError, PaymentGatewayError) as error:
                    logger.warning(
                        "Liquidação adiada para a alocação #%s: %s", assignment.pk, error
                    )
                    self.message_user(
                        request,
                        "Decidido a favor do prestador. O pagamento será liberado no próximo "
                        "processamento de prazos.",
                        messages.WARNING,
                    )
                else:
                    self.message_user(
                        request,
                        "Decidido a favor do prestador. Pagamento liberado.",
                        messages.SUCCESS,
                    )
            else:
                self.message_user(
                    request,
                    "Decidido a favor da empresa. O valor da posição foi devolvido.",
                    messages.SUCCESS,
                )
            return HttpResponseRedirect(changelist)

        if assignment.status != Assignment.Status.CONTESTED:
            self.message_user(request, "Esta alocação não está contestada.", messages.ERROR)
            return HttpResponseRedirect(changelist)
        context = {
            **self.admin_site.each_context(request),
            "title": "Decidir contestação",
            "assignment": assignment,
            "contested_at": _contested_at(assignment),
            "company_reason": assignments.contest_reason(assignment),
        }
        return TemplateResponse(request, "admin/vacancies/resolve_contest.html", context)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("id", "assignment", "direction", "rating", "author", "created_at")
    list_filter = ("direction", "rating")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

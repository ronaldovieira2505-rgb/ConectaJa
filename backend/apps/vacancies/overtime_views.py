"""API da hora extra (US52): a empresa pede que o prestador fique mais tempo."""

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework.response import Response

from apps.core.exceptions import DomainError
from apps.core.models import PlatformParameters
from apps.vacancies import overtime
from apps.vacancies.models import Assignment
from apps.vacancies.views import CompanyAreaView, forbidden_company


def serialize_overtime(request, params=None):
    if request is None:
        return None
    params = params or PlatformParameters.get()
    return {
        "id": request.pk,
        "assignment_id": request.assignment_id,
        "minutes": request.minutes,
        "minutes_label": overtime.minutes_label(request.minutes),
        "amount_cents": request.amount_cents,
        "net_cents": params.worker_net_cents(request.amount_cents),
        "status": request.status,
        "status_label": request.get_status_display(),
        "created_at": request.created_at.isoformat(),
        "expires_at": request.expires_at.isoformat(),
        "responded_at": request.responded_at and request.responded_at.isoformat(),
    }


def company_overtime_info(assignment, params, now):
    """Para a equipe da vaga: pedido atual, se pode pedir e as durações com o valor mínimo."""
    if assignment.status != Assignment.Status.IN_PROGRESS:
        return {"can_request_overtime": False, "overtime": None, "overtime_options": []}
    allowed = overtime.can_request(assignment, now=now)
    return {
        "can_request_overtime": allowed,
        "overtime": serialize_overtime(overtime.current_request(assignment), params),
        "overtime_options": overtime.options(assignment.vacancy) if allowed else [],
    }


@method_decorator(csrf_protect, name="dispatch")
class OvertimeRequestView(CompanyAreaView):
    """`POST /api/assignments/<id>/overtime/` com `minutes` e `amount_cents` (US52).

    Outra empresa: 404. Duração ou valor inválidos: 400. Turno fora de `EM_EXECUCAO`, já
    terminado ou com pedido pendente/extensão aceita: 409.
    """

    def post(self, request, pk):
        company = self.company(request)
        denied = forbidden_company(company)
        if denied:
            return denied
        assignment = (
            Assignment.objects.select_related("vacancy")
            .filter(pk=pk, vacancy__company=company)
            .first()
        )
        if assignment is None:
            return Response({"detail": "Alocação não encontrada."}, status=404)
        minutes, amount = request.data.get("minutes"), request.data.get("amount_cents")
        try:
            overtime.clean(assignment.vacancy, minutes, amount)
        except DomainError as error:
            return Response({"detail": str(error)}, status=400)
        try:
            created = overtime.request_overtime(
                assignment, minutes=minutes, amount_cents=amount, actor=request.user
            )
        except DomainError as error:
            return Response({"detail": str(error)}, status=409)
        return Response(serialize_overtime(created), status=201)

"""API da hora extra: a empresa pede (US52) e o prestador aceita ou recusa (US53)."""

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework.response import Response

from apps.core.exceptions import DomainError
from apps.vacancies import overtime
from apps.vacancies.models import Assignment, OvertimeRequest
from apps.vacancies.views import CompanyAreaView, forbidden_company
from apps.vacancies.worker_views import WorkerAreaView


def company_overtime_info(assignment, params, now):
    """Para a equipe da vaga: pedido atual, se pode pedir e as durações com o valor mínimo."""
    if assignment.status != Assignment.Status.IN_PROGRESS:
        return {"can_request_overtime": False, "overtime": None, "overtime_options": []}
    allowed = overtime.can_request(assignment, now=now)
    return {
        "can_request_overtime": allowed,
        "overtime": overtime.serialize(overtime.current_request(assignment), params),
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
        return Response(overtime.serialize(created), status=201)


class OvertimeResponseView(WorkerAreaView):
    """Base de `POST /api/overtime/<id>/accept/` e `/decline/` (US53).

    Só o prestador da alocação responde (outro: 404). Pedido expirado ou já respondido,
    turno fora de execução ou falha do PSP: 409.
    """

    respond = None

    def post(self, request, pk):
        worker = self.worker(request)
        found = None
        if worker:
            found = OvertimeRequest.objects.filter(pk=pk, assignment__worker=worker).first()
        if found is None:
            return Response({"detail": "Pedido de hora extra não encontrado."}, status=404)
        try:
            result = type(self).respond(found, actor=request.user)
        except DomainError as error:
            return Response({"detail": str(error)}, status=409)
        return Response(overtime.serialize(result))


@method_decorator(csrf_protect, name="dispatch")
class OvertimeAcceptView(OvertimeResponseView):
    respond = staticmethod(overtime.accept)


@method_decorator(csrf_protect, name="dispatch")
class OvertimeDeclineView(OvertimeResponseView):
    respond = staticmethod(overtime.decline)

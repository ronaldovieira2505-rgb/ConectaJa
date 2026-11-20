"""API da empresa para conferir as horas e liberar o pagamento (US56/US59)."""

import logging
from datetime import timedelta

from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework.response import Response

from apps.core.exceptions import DomainError
from apps.core.models import PlatformParameters
from apps.vacancies import arrival, overtime
from apps.vacancies import assignment_services as assignments
from apps.vacancies import review_services as reviews
from apps.vacancies.models import ArrivalJustification, Assignment, Review
from apps.vacancies.views import NO_COMPANY, CompanyAreaView, forbidden_company
from integrations.payments import PaymentGatewayError

logger = logging.getLogger(__name__)

NOT_FOUND = "Alocação não encontrada."


def _first_name(worker):
    parts = worker.full_name.split()
    return parts[0] if parts else ""


def serialize_pending_assignment(assignment, params, now):
    """Horas a conferir: previsto × registrado, distância e prazo da aprovação automática."""
    vacancy = assignment.vacancy
    auto_approve_at = assignment.check_out_at + timedelta(minutes=params.contest_window_minutes)
    remaining = max(0, int((auto_approve_at - now).total_seconds()))
    extension = overtime.accepted_request(assignment)
    return {
        "id": assignment.pk,
        "vacancy_id": vacancy.pk,
        "vacancy_title": vacancy.title,
        "worker_first_name": _first_name(assignment.worker),
        "starts_at": vacancy.starts_at.isoformat(),
        "ends_at": (assignment.extended_until or vacancy.ends_at).isoformat(),
        "overtime_minutes": extension.minutes if extension else 0,
        "check_in_at": assignment.check_in_at and assignment.check_in_at.isoformat(),
        "check_out_at": assignment.check_out_at.isoformat(),
        "check_out_auto": assignment.check_out_auto,
        "check_in_distance_m": assignment.check_in_distance_m,
        "gross_cents": vacancy.pay_per_person_cents + (extension.amount_cents if extension else 0),
        "status": assignment.status,
        "status_label": assignment.get_status_display(),
        "auto_approve_at": auto_approve_at.isoformat(),
        "auto_approve_in_seconds": remaining,
        "can_contest": assignments.can_contest(assignment, now=now, params=params),
    }


def serialize_contested_assignment(assignment):
    """Alocação contestada: motivo da empresa e a versão do prestador, se já respondeu (US58)."""
    vacancy = assignment.vacancy
    return {
        "id": assignment.pk,
        "vacancy_id": vacancy.pk,
        "vacancy_title": vacancy.title,
        "worker_first_name": _first_name(assignment.worker),
        "status": assignment.status,
        "status_label": assignment.get_status_display(),
        "contest_reason": assignments.contest_reason(assignment),
        "contest_response": assignment.contest_response,
        "contest_response_at": assignment.contest_response_at
        and assignment.contest_response_at.isoformat(),
    }


def serialize_arrival_justification(justification):
    """Pedido de confirmação de chegada aguardando a empresa (US51)."""
    assignment = justification.assignment
    vacancy = assignment.vacancy
    return {
        "id": justification.pk,
        "assignment_id": assignment.pk,
        "vacancy_id": vacancy.pk,
        "vacancy_title": vacancy.title,
        "worker_first_name": _first_name(assignment.worker),
        "starts_at": vacancy.starts_at.isoformat(),
        "ends_at": vacancy.ends_at.isoformat(),
        "reason": justification.reason,
        "reason_label": justification.get_reason_display(),
        "text": justification.text,
        "created_at": justification.created_at.isoformat(),
    }


class CompanyPendingAssignmentsView(CompanyAreaView):
    """`GET /api/company/assignments/pending/`: alocações AGUARDANDO_VALIDACAO das minhas vagas.

    Filtro opcional `?vacancy=<id>` para a seção dentro da vaga. Traz também, em `contested`,
    as alocações `CONTESTADA` com o motivo e a resposta do prestador (US58) e, em
    `arrival_justifications`, os pedidos de confirmação de chegada aguardando resposta (US51).
    """

    def get(self, request):
        company = self.company(request)
        if company is None:
            return Response({"detail": NO_COMPANY}, status=403)
        owned = Assignment.objects.filter(vacancy__company=company).select_related(
            "vacancy", "worker"
        )
        vacancy_id = request.query_params.get("vacancy")
        if vacancy_id:
            if not vacancy_id.isdigit():
                return Response({"detail": "Vaga inválida."}, status=400)
            owned = owned.filter(vacancy_id=int(vacancy_id))
        queryset = owned.filter(
            status=Assignment.Status.AWAITING_VALIDATION, check_out_at__isnull=False
        ).prefetch_related("overtime_requests")
        contested = owned.filter(status=Assignment.Status.CONTESTED)
        justifications = ArrivalJustification.objects.filter(
            assignment__in=owned,
            assignment__status=Assignment.Status.CONFIRMED,
            status=ArrivalJustification.Status.PENDING,
        ).select_related("assignment__vacancy", "assignment__worker")
        params = PlatformParameters.get()
        now = timezone.now()
        items = [
            serialize_pending_assignment(a, params, now)
            for a in queryset.order_by("check_out_at", "pk")
        ]
        return Response(
            {
                "results": items,
                "contested": [
                    serialize_contested_assignment(a) for a in contested.order_by("pk")
                ],
                "arrival_justifications": [
                    serialize_arrival_justification(j)
                    for j in justifications.order_by("created_at", "pk")
                ],
            }
        )


@method_decorator(csrf_protect, name="dispatch")
class AssignmentApproveView(CompanyAreaView):
    """`POST /api/assignments/<id>/approve/`: aprova as horas e tenta liquidar o pagamento.

    Alocação de outra empresa responde 404. Se o PSP falhar, a alocação continua `APROVADA`
    e o próximo processamento de prazos tenta de novo, sem duplicar lançamentos.
    """

    def post(self, request, pk):
        company = self.company(request)
        denied = forbidden_company(company)
        if denied:
            return denied
        assignment = (
            Assignment.objects.select_related("vacancy__company", "worker__user")
            .filter(pk=pk, vacancy__company=company)
            .first()
        )
        if assignment is None:  # de outra empresa: não revela que existe
            return Response({"detail": NOT_FOUND}, status=404)
        try:
            assignment = assignments.approve_hours(assignment, actor=request.user)
        except DomainError as error:  # inclui InvalidTransition
            return Response({"detail": str(error)}, status=409)
        payment_pending = False
        try:
            assignment = assignments.settle(assignment)
        except (DomainError, PaymentGatewayError) as error:
            payment_pending = True
            logger.warning("Liquidação adiada para a alocação #%s: %s", assignment.pk, error)
        return Response(
            {
                "id": assignment.pk,
                "status": assignment.status,
                "status_label": assignment.get_status_display(),
                "payment_pending": payment_pending,
            }
        )


@method_decorator(csrf_protect, name="dispatch")
class ArrivalJustificationDecideView(CompanyAreaView):
    """`POST /api/assignments/<id>/arrival-justification/decide/` (US51).

    `{"confirm": true}` confirma a chegada (`CONFIRMADA → EM_EXECUCAO`, check-in no horário do
    pedido); `{"confirm": false, "reason": "..."}` recusa. Outra empresa: 404. Sem motivo: 400.
    """

    def post(self, request, pk):
        company = self.company(request)
        denied = forbidden_company(company)
        if denied:
            return denied
        justification = (
            ArrivalJustification.objects.select_related("assignment")
            .filter(assignment_id=pk, assignment__vacancy__company=company)
            .first()
        )
        if justification is None:
            return Response({"detail": "Justificativa não encontrada."}, status=404)
        confirm = request.data.get("confirm")
        if not isinstance(confirm, bool):
            return Response({"detail": "Informe se confirma a chegada."}, status=400)
        reason = request.data.get("reason", "")
        if not isinstance(reason, str):
            reason = ""
        if not confirm and not reason.strip():
            return Response({"detail": "Informe o motivo da recusa."}, status=400)
        try:
            justification = arrival.decide_by_company(
                justification, confirm=confirm, reason=reason, actor=request.user
            )
        except DomainError as error:  # inclui InvalidTransition
            return Response({"detail": str(error)}, status=409)
        assignment = Assignment.objects.get(pk=justification.assignment_id)
        return Response(
            {
                "id": justification.pk,
                "status": justification.status,
                "status_label": justification.get_status_display(),
                "assignment_status": assignment.status,
                "assignment_status_label": assignment.get_status_display(),
            }
        )


@method_decorator(csrf_protect, name="dispatch")
class AssignmentContestView(CompanyAreaView):
    """`POST /api/assignments/<id>/contest/` com `{"reason": "..."}` (US57).

    Só a empresa dona da vaga (outra responde 404). Motivo vazio: 400. Fora de
    `AGUARDANDO_VALIDACAO` ou com a janela de contestação encerrada: 409.
    """

    def post(self, request, pk):
        company = self.company(request)
        denied = forbidden_company(company)
        if denied:
            return denied
        assignment = (
            Assignment.objects.select_related("vacancy__company", "worker__user")
            .filter(pk=pk, vacancy__company=company)
            .first()
        )
        if assignment is None:
            return Response({"detail": NOT_FOUND}, status=404)
        reason = request.data.get("reason", "")
        if not isinstance(reason, str):
            reason = ""
        try:
            assignment = assignments.contest(assignment, reason=reason, actor=request.user)
        except DomainError as error:  # inclui InvalidTransition
            status = 400 if not reason.strip() else 409
            return Response({"detail": str(error)}, status=status)
        return Response(
            {
                "id": assignment.pk,
                "status": assignment.status,
                "status_label": assignment.get_status_display(),
            }
        )


@method_decorator(csrf_protect, name="dispatch")
class AssignmentCancelByCompanyView(CompanyAreaView):
    """`POST /api/assignments/<id>/cancel-by-company/` com `{"reason": "..."}` (US71).

    Só a empresa dona da vaga; outra empresa responde 404. Dentro do prazo gratuito de
    cancelamento a empresa não cancela pelo app (409, "Fale com o suporte").
    """

    def post(self, request, pk):
        company = self.company(request)
        denied = forbidden_company(company)
        if denied:
            return denied
        assignment = (
            Assignment.objects.select_related(
                "vacancy__company", "vacancy__custody", "worker__user"
            )
            .filter(pk=pk, vacancy__company=company)
            .first()
        )
        if assignment is None:
            return Response({"detail": NOT_FOUND}, status=404)
        reason = request.data.get("reason", "")
        if not isinstance(reason, str):
            reason = ""
        try:
            assignment = assignments.cancel_by_company(
                assignment, reason=reason, actor=request.user
            )
        except PaymentGatewayError as error:
            return Response({"detail": str(error)}, status=502)
        except DomainError as error:  # inclui InvalidTransition
            status = 400 if not reason.strip() else 409
            return Response({"detail": str(error)}, status=status)
        return Response(
            {
                "id": assignment.pk,
                "status": assignment.status,
                "status_label": assignment.get_status_display(),
            }
        )


def serialize_review(review):
    return {
        "id": review.pk,
        "assignment_id": review.assignment_id,
        "rating": review.rating,
        "comment": review.comment,
        "created_at": review.created_at.isoformat(),
    }


@method_decorator(csrf_protect, name="dispatch")
class AssignmentReviewView(CompanyAreaView):
    """`POST /api/assignments/<id>/review/` com `{"rating": 1-5, "comment": "..."}` (US63).

    Só a empresa dona da vaga (outra responde 404). Nota fora de 1 a 5 ou comentário acima de
    500 caracteres: 400. Fora de `APROVADA`/`PAGA`, já avaliada ou com o prazo
    (`review_window_days`) encerrado: 409. A avaliação é definitiva.
    """

    def post(self, request, pk):
        company = self.company(request)
        denied = forbidden_company(company)
        if denied:
            return denied
        assignment = (
            Assignment.objects.select_related("vacancy__company", "worker__user")
            .filter(pk=pk, vacancy__company=company)
            .first()
        )
        if assignment is None:
            return Response({"detail": NOT_FOUND}, status=404)
        try:
            rating = reviews.validate_rating(request.data.get("rating"))
            comment = reviews.validate_comment(request.data.get("comment"))
        except DomainError as error:
            return Response({"detail": str(error)}, status=400)
        try:
            review = reviews.review_worker(
                assignment, author=request.user, rating=rating, comment=comment
            )
        except DomainError as error:
            return Response({"detail": str(error)}, status=409)
        return Response(serialize_review(review), status=201)


class CompanyReviewsView(CompanyAreaView):
    """`GET /api/company/reviews/`: avaliações que a empresa recebeu dos prestadores (US64).

    O prestador aparece como "Ana S."; nunca CPF nem sobrenome completo.
    """

    def get(self, request):
        company = self.company(request)
        if company is None:
            return Response({"detail": NO_COMPANY}, status=403)
        found = (
            Review.objects.filter(
                direction=Review.Direction.WORKER_TO_COMPANY,
                assignment__vacancy__company=company,
            )
            .select_related("assignment__vacancy", "assignment__worker")
            .order_by("-created_at", "-pk")
        )
        items = [
            {
                "id": r.pk,
                "rating": r.rating,
                "comment": r.comment,
                "created_at": r.created_at.isoformat(),
                "vacancy_title": r.assignment.vacancy.title,
                "reviewer": reviews.reviewer_display_name(r.assignment.worker),
            }
            for r in found
        ]
        return Response({"summary": reviews.company_rating(company.pk), "results": items})

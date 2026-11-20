"""API do prestador: candidatar-se, desistir e acompanhar os trabalhos (US37/US38)."""

from datetime import timedelta

from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import DomainError, InvalidTransition
from apps.core.models import PlatformParameters
from apps.core.permissions import IsWorkerUser
from apps.vacancies import application_services as applications
from apps.vacancies import arrival, favorites
from apps.vacancies import assignment_services as assignments
from apps.vacancies import review_services as reviews
from apps.vacancies import waitlist_services as waitlist
from apps.vacancies.models import Application, ArrivalJustification, Assignment, Vacancy
from apps.vacancies.photos import photo_url

AS = Assignment.Status
AP = Application.Status

# Grupos da página "Meus trabalhos" (US38).
IN_PROGRESS_STATUSES = (AS.IN_PROGRESS, AS.AWAITING_VALIDATION, AS.CONTESTED, AS.APPROVED)
CLOSED_ASSIGNMENT_STATUSES = (
    AS.NO_SHOW,
    AS.REFUNDED,
    AS.CANCELLED_BY_WORKER,
    AS.CANCELLED_BY_COMPANY,
)
CLOSED_APPLICATION_STATUSES = (AP.REJECTED, AP.WITHDRAWN, AP.EXPIRED)


class WorkerAreaView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsWorkerUser]

    def worker(self, request):
        return getattr(request.user, "worker", None)


def _cancel_info(assignment, params, now):
    """Botão "Cancelar participação" (US72): só em `CONFIRMADA`, com aviso se for tardio."""
    can_cancel = assignment.status == AS.CONFIRMED
    late = can_cancel and assignments.is_late_worker_cancel(
        assignment.vacancy, now=now, params=params
    )
    return {
        "can_cancel": can_cancel,
        "cancel_is_late": late,
        "cancel_warning": assignments.late_cancel_warning(params) if late else "",
    }


def _execution_info(assignment, params, now):
    """Janela de check-in e horários registrados, para os botões de "Meus trabalhos"."""
    vacancy = assignment.vacancy
    opens_at = vacancy.starts_at - timedelta(minutes=params.checkin_open_minutes_before)
    closes_at = vacancy.starts_at + timedelta(minutes=params.no_show_tolerance_minutes)
    return {
        "check_in_opens_at": opens_at.isoformat(),
        "check_in_closes_at": closes_at.isoformat(),
        "can_check_in": assignment.status == AS.CONFIRMED and opens_at <= now <= closes_at,
        "can_check_out": assignment.status == AS.IN_PROGRESS,
        **_cancel_info(assignment, params, now),
        "check_in_at": assignment.check_in_at and assignment.check_in_at.isoformat(),
        "check_out_at": assignment.check_out_at and assignment.check_out_at.isoformat(),
        "check_out_auto": assignment.check_out_auto,
        "contest_reason": (
            assignments.contest_reason(assignment) if assignment.status == AS.CONTESTED else ""
        ),
        "can_respond_to_contest": assignments.can_respond_to_contest(assignment),
        "contest_response": assignment.contest_response,
        "contest_response_at": assignment.contest_response_at
        and assignment.contest_response_at.isoformat(),
        **_review_info(assignment, params, now),
        **_arrival_info(assignment, params, now),
    }


def serialize_justification(justification):
    if justification is None:
        return None
    return {
        "id": justification.pk,
        "reason": justification.reason,
        "reason_label": justification.get_reason_display(),
        "text": justification.text,
        "status": justification.status,
        "status_label": justification.get_status_display(),
        "decision_reason": justification.decision_reason,
        "created_at": justification.created_at.isoformat(),
    }


def _justification_of(assignment):
    try:
        return assignment.arrival_justification
    except ArrivalJustification.DoesNotExist:
        return None


def _arrival_info(assignment, params, now):
    """Botão "Não consigo registrar a chegada" (US51) e a situação do pedido, se houver."""
    justification = _justification_of(assignment)
    return {
        "can_justify_arrival": justification is None
        and arrival.can_justify(assignment, now=now, params=params),
        "arrival_justification": serialize_justification(justification),
        "check_in_confirmed_by_company": assignment.check_in_confirmed_by_company,
    }


def _review_info(assignment, params, now):
    """Botão "Avaliar empresa" (US64): `APROVADA`/`PAGA`, sem avaliação e dentro do prazo."""
    if assignment.status not in reviews.REVIEWABLE_STATUSES:
        return {"can_review": False, "review_deadline": None, "my_review": None}
    mine = reviews.worker_review(assignment)
    deadline = reviews.review_deadline(assignment, params)
    return {
        "can_review": reviews.can_worker_review(assignment, now=now, params=params),
        "review_deadline": deadline and deadline.isoformat(),
        "my_review": mine and {"rating": mine.rating, "comment": mine.comment},
    }


def serialize_assignment(assignment, params=None, now=None):
    params = params or PlatformParameters.get()
    item = _item("assignment", assignment, assignment.vacancy, params)
    item.update(_execution_info(assignment, params, now or timezone.now()))
    return item


def _item(kind, obj, vacancy, params):
    return {
        "kind": kind,
        "id": obj.pk,
        "vacancy_id": vacancy.pk,
        "title": vacancy.title,
        "category": vacancy.category,
        "photo_url": photo_url(vacancy),
        "company_name": vacancy.company.trade_name or vacancy.company.legal_name,
        "starts_at": vacancy.starts_at.isoformat(),
        "ends_at": vacancy.ends_at.isoformat(),
        "gross_cents": vacancy.pay_per_person_cents,
        "net_cents": params.worker_net_cents(vacancy.pay_per_person_cents),
        "status": obj.status,
        "status_label": obj.get_status_display(),
        "can_withdraw": kind == "application" and obj.status == AP.PENDING,
    }


def serialize_application(application, params=None):
    params = params or PlatformParameters.get()
    item = _item("application", application, application.vacancy, params)
    position = waitlist.waitlist_position(application)
    item["waitlist_position"] = position
    if position is not None:
        item["status_label"] = waitlist.waitlist_label(position)
    return item


@method_decorator(csrf_protect, name="dispatch")
class VacancyApplyView(WorkerAreaView):
    """`POST /api/vacancies/<id>/apply/`: candidatura com um clique."""

    def post(self, request, pk):
        worker = self.worker(request)
        if worker is None:
            return Response({"detail": "Acesso restrito a prestadores."}, status=403)
        vacancy = Vacancy.objects.select_related("company").filter(pk=pk).first()
        if vacancy is None:
            return Response({"detail": "Vaga não encontrada."}, status=404)
        try:
            application = applications.apply_to_vacancy(vacancy, worker, actor=request.user)
        except DomainError as error:
            return Response({"detail": str(error)}, status=409)
        return Response(serialize_application(application), status=201)


@method_decorator(csrf_protect, name="dispatch")
class ApplicationWithdrawView(WorkerAreaView):
    """`POST /api/applications/<id>/withdraw/`: desistência sem penalidade."""

    def post(self, request, pk):
        worker = self.worker(request)
        application = None
        if worker:
            application = (
                Application.objects.select_related("vacancy__company")
                .filter(pk=pk, worker=worker)
                .first()
            )
        if application is None:  # de outro prestador: não revela que existe
            return Response({"detail": "Candidatura não encontrada."}, status=404)
        try:
            application = applications.withdraw_application(application, actor=request.user)
        except InvalidTransition:
            return Response(
                {"detail": "Só é possível desistir de uma candidatura pendente."}, status=409
            )
        return Response(serialize_application(application))


class WorkerJobsView(WorkerAreaView):
    """`GET /api/workers/me/jobs/`: candidaturas e alocações agrupadas por situação."""

    def get(self, request):
        worker = self.worker(request)
        if worker is None:
            return Response({"detail": "Acesso restrito a prestadores."}, status=403)
        params = PlatformParameters.get()
        now = timezone.now()
        groups = {"waiting": [], "upcoming": [], "in_progress": [], "completed": [], "closed": []}
        for application in worker.applications.select_related("vacancy__company"):
            if application.status == AP.PENDING:
                key = "waiting"
            elif application.status in CLOSED_APPLICATION_STATUSES:
                key = "closed"
            else:  # APROVADA: o acompanhamento continua na alocação
                continue
            groups[key].append(serialize_application(application, params))
        for assignment in worker.assignments.select_related(
            "vacancy__company", "arrival_justification"
        ):
            if assignment.status == AS.CONFIRMED:
                key = "upcoming"
            elif assignment.status in IN_PROGRESS_STATUSES:
                key = "in_progress"
            elif assignment.status == AS.PAID:
                key = "completed"
            else:
                key = "closed"
            groups[key].append(serialize_assignment(assignment, params, now))
        for key, items in groups.items():
            newest_first = key in ("completed", "closed")
            items.sort(key=lambda i: (i["starts_at"], i["id"]), reverse=newest_first)
        return Response({"groups": groups})


class AssignmentActionView(WorkerAreaView):
    """Base das ações do prestador sobre a própria alocação (404 para a de outro)."""

    def post(self, request, pk):
        worker = self.worker(request)
        assignment = None
        if worker:
            assignment = (
                Assignment.objects.select_related("vacancy__company")
                .filter(pk=pk, worker=worker)
                .first()
            )
        if assignment is None:
            return Response({"detail": "Alocação não encontrada."}, status=404)
        try:
            assignment = self.run(request, assignment)
        except DomainError as error:  # inclui InvalidTransition
            return Response({"detail": str(error)}, status=409)
        return Response(serialize_assignment(assignment))


@method_decorator(csrf_protect, name="dispatch")
class AssignmentCheckInView(AssignmentActionView):
    """`POST /api/assignments/<id>/check-in/` com `lat`, `lng` e `accuracy` (m).

    A distância é calculada no servidor (Haversine); a precisão é só informativa.
    """

    def run(self, request, assignment):
        lat, lng = request.data.get("lat"), request.data.get("lng")
        if lat is None or lng is None:
            raise DomainError("Informe a sua localização para registrar a chegada.")
        return assignments.check_in(assignment, lat=lat, lng=lng, actor=request.user)


@method_decorator(csrf_protect, name="dispatch")
class ArrivalJustificationView(AssignmentActionView):
    """`POST /api/assignments/<id>/arrival-justification/` com `reason` e `text` (US51).

    Para quando o check-in pelo celular não funciona: a empresa confirma ou recusa a chegada.
    """

    def run(self, request, assignment):
        arrival.submit(
            assignment, reason=request.data.get("reason"), text=request.data.get("text", "")
        )
        return Assignment.objects.select_related("vacancy__company").get(pk=assignment.pk)


@method_decorator(csrf_protect, name="dispatch")
class AssignmentCancelByWorkerView(AssignmentActionView):
    """`POST /api/assignments/<id>/cancel-by-worker/`: cancela a própria alocação (US72)."""

    def run(self, request, assignment):
        return assignments.cancel_by_worker(assignment, actor=request.user)


@method_decorator(csrf_protect, name="dispatch")
class AssignmentCheckOutView(AssignmentActionView):
    """`POST /api/assignments/<id>/check-out/`: encerra o turno."""

    def run(self, request, assignment):
        return assignments.check_out(assignment, actor=request.user)

@method_decorator(csrf_protect, name="dispatch")
class AssignmentContestResponseView(WorkerAreaView):
    """`POST /api/assignments/<id>/contest-response/` com `{"text": "..."}` (US58).

    Só o prestador da alocação (outro usuário responde 404). Texto vazio, com menos de 10 ou mais
    de 1.000 caracteres: 400. Fora de `CONTESTADA` ou já respondida: 409. A resposta é única,
    definitiva e não muda o estado da alocação.
    """

    def post(self, request, pk):
        worker = self.worker(request)
        assignment = None
        if worker:
            assignment = (
                Assignment.objects.select_related("vacancy__company")
                .filter(pk=pk, worker=worker)
                .first()
            )
        if assignment is None:
            return Response({"detail": "Alocação não encontrada."}, status=404)
        try:
            text = assignments.clean_contest_response(request.data.get("text"))
        except DomainError as error:
            return Response({"detail": str(error)}, status=400)
        try:
            assignment = assignments.respond_to_contest(
                assignment, text=text, actor=request.user
            )
        except DomainError as error:
            return Response({"detail": str(error)}, status=409)
        return Response(serialize_assignment(assignment))


@method_decorator(csrf_protect, name="dispatch")
class AssignmentReviewCompanyView(WorkerAreaView):
    """`POST /api/assignments/<id>/review-company/` com `{"rating": 1-5, "comment": "..."}` (US64).

    Só o prestador da alocação (outro responde 404). Nota ou comentário inválidos: 400. Fora de
    `APROVADA`/`PAGA`, já avaliada ou com o prazo (`review_window_days`) encerrado: 409.
    """

    def post(self, request, pk):
        worker = self.worker(request)
        assignment = None
        if worker:
            assignment = (
                Assignment.objects.select_related("vacancy__company", "worker")
                .filter(pk=pk, worker=worker)
                .first()
            )
        if assignment is None:
            return Response({"detail": "Alocação não encontrada."}, status=404)
        try:
            rating = reviews.validate_rating(request.data.get("rating"))
            comment = reviews.validate_comment(request.data.get("comment"))
        except DomainError as error:
            return Response({"detail": str(error)}, status=400)
        try:
            review = reviews.review_company(
                assignment, author=request.user, rating=rating, comment=comment
            )
        except DomainError as error:
            return Response({"detail": str(error)}, status=409)
        return Response(
            {
                "id": review.pk,
                "assignment_id": assignment.pk,
                "rating": review.rating,
                "comment": review.comment,
                "created_at": review.created_at.isoformat(),
            },
            status=201,
        )


@method_decorator(csrf_protect, name="dispatch")
class VacancyFavoriteView(WorkerAreaView):
    """`POST`/`DELETE /api/vacancies/<id>/favorite/` (US18). Repetir não duplica nem falha."""

    def post(self, request, pk):
        worker = self.worker(request)
        if worker is None:
            return Response({"detail": "Acesso restrito a prestadores."}, status=403)
        vacancy = Vacancy.objects.filter(pk=pk, status__in=favorites.FAVORITABLE_STATUSES).first()
        if vacancy is None:
            return Response({"detail": "Vaga não encontrada."}, status=404)
        created = favorites.add_favorite(worker, vacancy)
        return Response(
            {"vacancy_id": vacancy.pk, "favorite": True}, status=201 if created else 200
        )

    def delete(self, request, pk):
        worker = self.worker(request)
        if worker is None:
            return Response({"detail": "Acesso restrito a prestadores."}, status=403)
        favorites.remove_favorite(worker, pk)
        return Response(status=204)


class WorkerFavoritesView(WorkerAreaView):
    """`GET /api/workers/me/favorites/`: só as favoritas do próprio prestador (US18)."""

    def get(self, request):
        worker = self.worker(request)
        if worker is None:
            return Response({"detail": "Acesso restrito a prestadores."}, status=403)
        return Response({"results": favorites.favorites_payload(worker)})

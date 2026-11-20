"""API da empresa para selecionar candidatos: listar, aprovar e recusar (US42)."""

from django.http import FileResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework.response import Response

from apps.core.exceptions import DomainError, InvalidTransition
from apps.core.models import PlatformParameters
from apps.vacancies import application_services as applications
from apps.vacancies import review_services as reviews
from apps.vacancies import waitlist_services as waitlist
from apps.vacancies.models import Application, Assignment, Vacancy
from apps.vacancies.overtime_views import company_overtime_info
from apps.vacancies.views import NO_COMPANY, CompanyAreaView, forbidden_company
from apps.workers.availability import summary as availability_summary
from apps.workers.models import Worker, WorkerDocument
from apps.workers.portfolio import serialize_photos
from apps.workers.skills import serialize_skills

NOT_FOUND = "Candidatura não encontrada."


def _worker_has_selfie(worker):
    return any(d.kind == WorkerDocument.Kind.SELFIE for d in worker.documents.all())


def _first_name(worker):
    parts = worker.full_name.split()
    return parts[0] if parts else ""


def serialize_candidate(application, params=None):
    """Só o que a empresa pode ver antes da alocação: sem CPF, telefone nem PIX."""
    worker = application.worker
    rating = reviews.worker_rating(worker)
    return {
        "id": application.pk,
        "name": _first_name(worker),
        "photo_url": (
            f"/api/applications/{application.pk}/photo/" if _worker_has_selfie(worker) else None
        ),
        "verified": worker.verification_status == Worker.VerificationStatus.APPROVED,
        "completed_shifts": worker.assignments.filter(status=Assignment.Status.PAID).count(),
        "no_shows_30d": reviews.worker_no_shows_recent(worker, params=params),
        "rating_avg": rating["average"],
        "rating_count": rating["count"],
        "recent_reviews": reviews.worker_recent_reviews(worker),
        # Habilidades (US08): a categoria da vaga vem destacada quando o candidato a marcou.
        "skills": serialize_skills(worker.skills, application.vacancy.category),
        "bio": worker.bio,
        # Fotos de trabalhos anteriores (US41), servidas só pela API.
        "portfolio": serialize_photos(worker),
        # Disponibilidade (US10), só informativa: "Seg–Sex · manhã e tarde".
        "availability_summary": availability_summary(worker),
        "applied_at": application.created_at.isoformat(),
    }


def serialize_team_member(assignment, params=None, now=None):
    """Contato liberado só após a alocação: primeiro nome e telefone. Inclui a hora extra (US52)."""
    worker = assignment.worker
    params = params or PlatformParameters.get()
    return {
        "id": assignment.pk,
        "first_name": _first_name(worker),
        "phone": worker.phone,
        "status": assignment.status,
        "status_label": assignment.get_status_display(),
        **company_overtime_info(assignment, params, now or timezone.now()),
    }


class CandidateAreaView(CompanyAreaView):
    def own_vacancy(self, request, pk):
        """(vaga, resposta de erro). Vaga de outra empresa responde 404."""
        company = self.company(request)
        if company is None:
            return None, Response({"detail": NO_COMPANY}, status=403)
        vacancy = Vacancy.objects.filter(pk=pk, company=company).first()
        if vacancy is None:
            return None, Response({"detail": "Vaga não encontrada."}, status=404)
        return vacancy, None

    def own_application(self, request, pk):
        company = self.company(request)
        if company is None:
            return None, Response({"detail": NO_COMPANY}, status=403)
        application = (
            Application.objects.select_related("vacancy", "worker__user")
            .filter(pk=pk, vacancy__company=company)
            .first()
        )
        if application is None:  # de outra empresa: não revela que existe
            return None, Response({"detail": NOT_FOUND}, status=404)
        return application, None


class VacancyCandidatesView(CandidateAreaView):
    """`GET /api/vacancies/<id>/candidates/`: pendentes + equipe já alocada."""

    def get(self, request, pk):
        vacancy, error = self.own_vacancy(request, pk)
        if error:
            return error
        pending = (
            vacancy.applications.filter(status=Application.Status.PENDING)
            .select_related("worker")
            .prefetch_related("worker__documents", "worker__portfolio")
            .order_by("created_at", "pk")
        )
        team = (
            vacancy.assignments.filter(status__in=Assignment.ACTIVE_STATUSES)
            .select_related("worker")
            .order_by("pk")
        )
        filled = vacancy.filled_positions
        params = PlatformParameters.get()
        team_complete = waitlist.is_team_complete(vacancy)
        candidates = []
        for index, application in enumerate(pending, start=1):
            item = serialize_candidate(application, params)
            # Equipe completa: os pendentes são a lista de espera, numerada pela ordem.
            item["waitlist_position"] = index if team_complete else None
            candidates.append(item)
        return Response(
            {
                "positions": vacancy.positions,
                "filled_positions": filled,
                "team_complete": team_complete,
                "auto_call_waitlist": vacancy.auto_call_waitlist,
                "free_cancel_minutes_before": params.free_cancel_minutes_before,
                "no_show_window_days": params.no_show_window_days,
                "candidates": candidates,
                "team": [serialize_team_member(a, params) for a in team],
            }
        )


@method_decorator(csrf_protect, name="dispatch")
class VacancyWaitlistSettingView(CandidateAreaView):
    """`POST /api/vacancies/<id>/waitlist-auto-call/` com `{"enabled": true|false}` (US43)."""

    def post(self, request, pk):
        company = self.company(request)
        denied = forbidden_company(company) if company is not None else None
        if denied:
            return denied
        vacancy, error = self.own_vacancy(request, pk)
        if error:
            return error
        enabled = request.data.get("enabled")
        if not isinstance(enabled, bool):
            return Response({"detail": "Informe se a chamada automática fica ligada."}, status=400)
        vacancy.auto_call_waitlist = enabled
        vacancy.save(update_fields=["auto_call_waitlist"])
        return Response({"auto_call_waitlist": vacancy.auto_call_waitlist})


class DecisionView(CandidateAreaView):
    def post(self, request, pk):
        denied = None
        company = self.company(request)
        if company is not None:
            denied = forbidden_company(company)
        if denied:
            return denied
        application, error = self.own_application(request, pk)
        if error:
            return error
        try:
            return Response(self.decide(application, request))
        except InvalidTransition:
            return Response({"detail": "Esta candidatura já foi decidida."}, status=409)
        except DomainError as exc:
            return Response({"detail": str(exc)}, status=409)

    def decide(self, application, request):
        raise NotImplementedError


@method_decorator(csrf_protect, name="dispatch")
class ApplicationApproveView(DecisionView):
    """`POST /api/applications/<id>/approve/`."""

    def decide(self, application, request):
        assignment = applications.approve_application(application, actor=request.user)
        return {
            "application_id": application.pk,
            "status": Application.Status.APPROVED,
            "assignment": serialize_team_member(assignment),
        }


@method_decorator(csrf_protect, name="dispatch")
class ApplicationRejectView(DecisionView):
    """`POST /api/applications/<id>/reject/`."""

    def decide(self, application, request):
        application = applications.reject_application(application, actor=request.user)
        return {"application_id": application.pk, "status": application.status}


class ApplicationPhotoView(CandidateAreaView):
    """`GET /api/applications/<id>/photo/`: selfie verificada, só para a empresa da vaga."""

    def get(self, request, pk):
        application, error = self.own_application(request, pk)
        if error:
            return error
        document = (
            application.worker.documents.filter(kind=WorkerDocument.Kind.SELFIE)
            .order_by("-uploaded_at", "-pk")
            .first()
        )
        if document is None:
            return Response({"detail": "Foto não encontrada."}, status=404)
        return FileResponse(document.file.open("rb"))

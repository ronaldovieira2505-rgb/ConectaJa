"""API de convites da empresa a prestadores que já trabalharam com ela (US44)."""

from django.http import FileResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework.response import Response

from apps.core.exceptions import DomainError
from apps.vacancies import invites
from apps.vacancies.models import Assignment, Vacancy
from apps.vacancies.views import NO_COMPANY, CompanyAreaView, forbidden_company
from apps.workers.models import Worker, WorkerDocument

VACANCY_NOT_FOUND = "Vaga não encontrada."
WORKER_NOT_FOUND = "Prestador não encontrado."


class CompanyPastWorkersView(CompanyAreaView):
    """`GET /api/company/past-workers/?vacancy=<id>`: quem já trabalhou com a empresa."""

    def get(self, request):
        company = self.company(request)
        if company is None:
            return Response({"detail": NO_COMPANY}, status=403)
        vacancy_id = request.query_params.get("vacancy", "")
        if not vacancy_id.isdigit():
            return Response({"detail": "Informe a vaga."}, status=400)
        vacancy = Vacancy.objects.filter(pk=int(vacancy_id), company=company).first()
        if vacancy is None:
            return Response({"detail": VACANCY_NOT_FOUND}, status=404)
        return Response(invites.invite_list(vacancy))


@method_decorator(csrf_protect, name="dispatch")
class VacancyInviteView(CompanyAreaView):
    """`POST /api/vacancies/<id>/invite/` com `{"worker_id": n}`."""

    def post(self, request, pk):
        company = self.company(request)
        denied = forbidden_company(company)
        if denied:
            return denied
        vacancy = Vacancy.objects.filter(pk=pk, company=company).first()
        if vacancy is None:
            return Response({"detail": VACANCY_NOT_FOUND}, status=404)
        worker_id = request.data.get("worker_id")
        worker = (
            Worker.objects.filter(pk=worker_id).first()
            if isinstance(worker_id, int) and not isinstance(worker_id, bool)
            else None
        )
        if worker is None:
            return Response({"detail": WORKER_NOT_FOUND}, status=404)
        try:
            invites.invite(vacancy, worker, actor=request.user)
        except invites.NotAPastWorker:
            return Response({"detail": WORKER_NOT_FOUND}, status=404)
        except DomainError as error:
            return Response({"detail": str(error)}, status=409)
        return Response({"worker_id": worker.pk, "invited": True}, status=201)


class CompanyWorkerPhotoView(CompanyAreaView):
    """`GET /api/company/workers/<id>/photo/`: selfie de quem já teve turno pago com a empresa."""

    def get(self, request, worker_id):
        company = self.company(request)
        if company is None:
            return Response({"detail": NO_COMPANY}, status=403)
        worked = Assignment.objects.filter(
            worker_id=worker_id, vacancy__company=company, status=Assignment.Status.PAID
        ).exists()
        document = (
            WorkerDocument.objects.filter(worker_id=worker_id, kind=WorkerDocument.Kind.SELFIE)
            .order_by("-uploaded_at", "-pk")
            .first()
            if worked
            else None
        )
        if document is None:
            return Response({"detail": "Foto não encontrada."}, status=404)
        response = FileResponse(document.file.open("rb"))
        response["Cache-Control"] = "private, no-store"
        return response

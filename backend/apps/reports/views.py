"""`POST /api/reports/`: denúncia de vaga ou empresa (US69) e de prestador (US70)."""

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.core.exceptions import DomainError
from apps.reports import services
from apps.reports.models import Report
from apps.vacancies.views import company_of

T = Report.Target
ONLY_WORKERS = "Só prestadores podem denunciar vagas e empresas."
ONLY_COMPANIES = "Só empresas podem denunciar prestadores."


@method_decorator(csrf_protect, name="dispatch")
class ReportCreateView(APIView):
    """Corpo: `target_type`, `target_id`, `reason` e `description`.

    - `VAGA` / `EMPRESA` (US69): `target_id` é a vaga ou a empresa; só prestador denuncia.
    - `PRESTADOR` (US70): `target_id` é a alocação do prestador numa vaga da empresa; só
      membro da empresa denuncia.

    Perfil errado: 403. Dados inválidos: 400. Alvo inexistente ou sem vínculo: 404. Denúncia
    aberta sobre o mesmo alvo: 409. A resposta não expõe nada do denunciado.
    """

    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        target_type = request.data.get("target_type")
        if target_type not in T.values:
            return Response({"detail": "Tipo de alvo inválido."}, status=400)
        company = None
        if target_type == T.WORKER:
            company = company_of(request.user) if request.user.role == Role.COMPANY else None
            if company is None:
                return Response({"detail": ONLY_COMPANIES}, status=403)
        elif request.user.role != Role.WORKER or not hasattr(request.user, "worker"):
            return Response({"detail": ONLY_WORKERS}, status=403)
        target_id = request.data.get("target_id")
        if not isinstance(target_id, int) or isinstance(target_id, bool):
            return Response({"detail": "Alvo inválido."}, status=400)
        reason, description = request.data.get("reason"), request.data.get("description")
        try:
            services.clean(reason, description, target_type)
        except DomainError as error:
            return Response({"detail": str(error)}, status=400)
        try:
            if target_type == T.WORKER:
                report = services.report_worker(
                    request.user,
                    company,
                    assignment_id=target_id,
                    reason=reason,
                    description=description,
                )
            else:
                report = services.report_vacancy_or_company(
                    request.user,
                    target_type=target_type,
                    target_id=target_id,
                    reason=reason,
                    description=description,
                )
        except services.TargetNotFound as error:
            return Response({"detail": str(error)}, status=404)
        except DomainError as error:
            return Response({"detail": str(error)}, status=409)
        return Response(
            {"id": report.pk, "status": report.status, "detail": services.SENT}, status=201
        )

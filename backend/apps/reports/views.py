"""`POST /api/reports/`: denunciar uma vaga ou empresa (US69)."""

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

T = Report.Target


@method_decorator(csrf_protect, name="dispatch")
class ReportCreateView(APIView):
    """Corpo: `target_type` (`VAGA` ou `EMPRESA`), `target_id`, `reason` e `description`.

    Só prestador denuncia vaga ou empresa (outros perfis: 403). Dados inválidos: 400. Alvo
    inexistente: 404. Denúncia aberta sobre o mesmo alvo: 409. A resposta não expõe nada do
    denunciado.
    """

    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        target_type = request.data.get("target_type")
        if target_type not in (T.VACANCY, T.COMPANY):
            return Response({"detail": "Tipo de alvo inválido."}, status=400)
        if request.user.role != Role.WORKER or not hasattr(request.user, "worker"):
            return Response(
                {"detail": "Só prestadores podem denunciar vagas e empresas."}, status=403
            )
        target_id = request.data.get("target_id")
        if not isinstance(target_id, int) or isinstance(target_id, bool):
            return Response({"detail": "Alvo inválido."}, status=400)
        reason, description = request.data.get("reason"), request.data.get("description")
        try:
            services.clean(reason, description)
        except DomainError as error:
            return Response({"detail": str(error)}, status=400)
        try:
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

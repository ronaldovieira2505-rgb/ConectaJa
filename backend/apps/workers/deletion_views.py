"""`POST /api/workers/me/delete/`: o prestador exclui a própria conta (US11)."""

from django.contrib.auth import logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.core.exceptions import DomainError
from apps.workers import deletion
from apps.workers.views import RESTRICTED, worker_or_403


@method_decorator(csrf_protect, name="dispatch")
class WorkerDeleteView(APIView):
    """Confirma com a senha atual. Senha errada: 403; turno em andamento: 409."""

    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    # Mesmo limite de tentativas do login: a senha é conferida aqui.
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        worker = worker_or_403(request)
        if worker is None:
            return Response({"detail": RESTRICTED}, status=403)
        try:
            deletion.delete_worker_account(worker, password=request.data.get("password"))
        except deletion.WrongPassword as error:
            return Response({"detail": str(error)}, status=403)
        except DomainError as error:
            return Response({"detail": str(error)}, status=409)
        logout(request)
        return Response(status=204)

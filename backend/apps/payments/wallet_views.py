"""Carteira (US60) e extrato (US61) do prestador autenticado."""

from django.http import HttpResponse
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import DomainError
from apps.core.permissions import IsWorkerUser
from apps.payments.statement import build_csv, parse_period, statement_filename, statement_rows
from apps.payments.wallet import wallet_for

RESTRICTED = "Acesso restrito a prestadores."


class WorkerAreaView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsWorkerUser]


class WorkerWalletView(WorkerAreaView):
    """`GET /api/workers/me/wallet/`."""

    def get(self, request):
        worker = getattr(request.user, "worker", None)
        if worker is None:
            return Response({"detail": RESTRICTED}, status=403)
        return Response(wallet_for(worker))


class WorkerStatementView(WorkerAreaView):
    """`GET /api/workers/me/statement.csv?from=AAAA-MM-DD&to=AAAA-MM-DD`: extrato em CSV."""

    def get(self, request):
        worker = getattr(request.user, "worker", None)
        if worker is None:
            return Response({"detail": RESTRICTED}, status=403)
        try:
            start, end = parse_period(
                request.query_params.get("from"), request.query_params.get("to")
            )
        except DomainError as error:
            return Response({"detail": str(error)}, status=400)
        response = HttpResponse(
            build_csv(statement_rows(worker, start, end)), content_type="text/csv; charset=utf-8"
        )
        response["Content-Disposition"] = f'attachment; filename="{statement_filename(end)}"'
        response["Cache-Control"] = "private, no-store"
        return response

from django.db import connection
from django.db.utils import Error as DatabaseError
from django.http import JsonResponse


def health_response(*, check_database=True):
    """Resposta das sondas de saúde.

    `/api/health/` (prontidão) também confere o banco; `/api/health/live/` (vida) só confirma
    que o processo responde, para a hospedagem não reiniciar o contêiner quando o banco oscila.
    """
    if check_database:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except DatabaseError:
            return JsonResponse({"status": "error", "detail": "database unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


def health(request):
    """Verifica que a API responde e que o banco está acessível.

    Normalmente quem responde é o `HealthCheckMiddleware`; a rota fica para o roteamento.
    """
    return health_response()


def health_live(request):
    """Sonda de vida: só confirma que o processo responde (não consulta o banco)."""
    return health_response(check_database=False)

"""Página pública da empresa (US15): aberta a qualquer pessoa, como a busca de vagas."""

from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.companies import public
from apps.companies.models import Company
from apps.core.models import PlatformParameters
from apps.vacancies import search

NOT_FOUND = "Empresa não encontrada."


class CompanyPublicView(APIView):
    """`GET /api/companies/<id>/public/`: dados públicos, vagas abertas e avaliações recentes.

    Empresa inexistente, pendente, rejeitada ou suspensa responde 404.
    """

    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]

    def get(self, request, pk):
        company = Company.objects.filter(pk=pk).first()
        if company is None or not public.is_public(company):
            return Response({"detail": NOT_FOUND}, status=404)
        data = public.company_summary(company)
        params = PlatformParameters.get()
        ratings = {company.pk: data["rating"]}
        open_vacancies = [v for v in search.searchable_vacancies() if v.company_id == company.pk]
        open_vacancies.sort(key=lambda v: (v.starts_at, v.pk))
        data["open_vacancies"] = [
            search.serialize_card(v, None, params, ratings) for v in open_vacancies
        ]
        data["recent_reviews"] = public.recent_reviews(company)
        return Response(data)

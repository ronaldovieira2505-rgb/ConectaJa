"""Perfil da empresa: dados do cadastro, logo, números e apresentação."""

import uuid

from django.db.models import Sum
from django.http import FileResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.companies.models import Company
from apps.companies.views import first_error
from apps.core.exceptions import DomainError
from apps.core.images import content_type_of, validate_image, version_of
from apps.core.permissions import IsCompanyUser
from apps.payments.models import LedgerEntry
from apps.vacancies.models import Assignment, Vacancy

NO_COMPANY = "Acesso restrito a empresas."


def logo_url(company):
    if not company.logo:
        return None
    return f"/api/companies/{company.pk}/logo/?v={version_of(company.logo.name)}"


def company_stats(company):
    vacancies = Vacancy.objects.filter(company=company)
    paid = LedgerEntry.objects.filter(
        custody__vacancy__company=company,
        kind__in=(LedgerEntry.Kind.WORKER_PAYOUT, LedgerEntry.Kind.PLATFORM_FEE),
    ).aggregate(total=Sum("amount_cents"))["total"]
    return {
        "published_vacancies": vacancies.exclude(
            status=Vacancy.Status.AWAITING_PAYMENT
        ).count(),
        "finished_vacancies": vacancies.filter(status=Vacancy.Status.FINISHED).count(),
        "completed_shifts": Assignment.objects.filter(
            vacancy__company=company, status=Assignment.Status.PAID
        ).count(),
        "total_paid_cents": paid or 0,
    }


def serialize_company(company):
    suspended = company.is_suspended(timezone.now())
    return {
        "id": company.pk,
        "name": company.trade_name or company.legal_name,
        "legal_name": company.legal_name,
        "trade_name": company.trade_name,
        "cnpj": company.cnpj,
        "state_registration": company.state_registration,
        "tax_regime_label": company.get_tax_regime_display(),
        "registration_status": company.registration_status,
        "street": company.street,
        "number": company.number,
        "complement": company.complement,
        "district": company.district,
        "city": company.city,
        "state": company.state,
        "zip_code": company.zip_code,
        "phone": company.phone,
        "payment_method_label": company.get_preferred_payment_method_display(),
        "verification_status": company.verification_status,
        "verification_label": company.get_verification_status_display(),
        "is_suspended": suspended,
        "suspension_message": company.suspension_message if suspended else "",
        "description": company.description,
        "logo_url": logo_url(company),
        "member_since": company.created_at.isoformat(),
        "stats": company_stats(company),
    }


class CompanyProfileSerializer(serializers.Serializer):
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)


class CompanyProfileView(APIView):
    """Base: sessão, papel EMPRESA e vínculo com a empresa."""

    authentication_classes = [SessionAuthentication]
    permission_classes = [IsCompanyUser]

    def company(self, request):
        membership = request.user.company_memberships.select_related("company").first()
        return membership.company if membership else None


@method_decorator(csrf_protect, name="dispatch")
class CompanyMeView(CompanyProfileView):
    """`GET/PATCH /api/companies/me/`: a empresa vê o cadastro e edita a apresentação."""

    parser_classes = [JSONParser]

    def get(self, request):
        company = self.company(request)
        if company is None:
            return Response({"detail": NO_COMPANY}, status=403)
        return Response(serialize_company(company))

    def patch(self, request):
        company = self.company(request)
        if company is None:
            return Response({"detail": NO_COMPANY}, status=403)
        serializer = CompanyProfileSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(
                {"detail": first_error(serializer.errors), "errors": serializer.errors}, status=400
            )
        # Só a apresentação muda aqui; os dados fiscais vêm do cadastro verificado.
        for field, value in serializer.validated_data.items():
            setattr(company, field, value.strip())
        company.save(update_fields=list(serializer.validated_data))
        return Response(serialize_company(company))


@method_decorator(csrf_protect, name="dispatch")
class CompanyLogoView(CompanyProfileView):
    """`POST/DELETE /api/companies/me/logo/` (multipart, campo `logo`)."""

    parser_classes = [MultiPartParser]

    def post(self, request):
        company = self.company(request)
        if company is None:
            return Response({"detail": NO_COMPANY}, status=403)
        uploaded = request.FILES.get("logo")
        try:
            extension = validate_image(uploaded)
        except DomainError as invalid:
            return Response({"detail": str(invalid)}, status=400)
        old_name = company.logo.name
        company.logo.save(f"{company.pk}-{uuid.uuid4().hex[:12]}.{extension}", uploaded, save=True)
        if old_name:
            company.logo.storage.delete(old_name)
        return Response(serialize_company(company))

    def delete(self, request):
        company = self.company(request)
        if company is None:
            return Response({"detail": NO_COMPANY}, status=403)
        if company.logo:
            company.logo.delete(save=True)
        return Response(serialize_company(company))


class CompanyLogoFileView(APIView):
    """`GET /api/companies/<id>/logo/`: a logo é pública, como o nome da empresa na vaga."""

    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]

    def get(self, request, pk):
        company = Company.objects.filter(pk=pk).exclude(logo="").first()
        if company is None:
            return Response({"detail": "Logo não encontrada."}, status=404)
        try:
            handle = company.logo.open("rb")
        except FileNotFoundError:
            return Response({"detail": "Logo não encontrada."}, status=404)
        response = FileResponse(handle, content_type=content_type_of(company.logo.name))
        response["Cache-Control"] = "public, max-age=86400"
        return response

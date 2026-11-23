import re
from datetime import datetime, timedelta
from io import StringIO
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone

from apps.accounts.models import Role
from apps.companies.models import Company
from apps.core.deadlines import process_deadlines
from apps.core.models import Notification, PlatformParameters
from apps.core.validators import is_valid_cnpj, is_valid_cpf
from apps.payments.models import Custody, LedgerEntry
from apps.vacancies.models import Application, Assignment, Review, Vacancy
from apps.workers.models import Worker

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture(autouse=True)
def private_media(settings, tmp_path):
    # Logos e documentos de exemplo vão para uma pasta temporária, não para o repositório.
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"


def run_seed(*args):
    out = StringIO()
    call_command("seed_demo", *args, stdout=out)
    return out.getvalue()


def test_creates_demo_data_on_empty_database():
    output = run_seed()

    assert User.objects.filter(role=Role.ADMIN, is_superuser=True).count() == 1
    approved_companies = Company.objects.filter(verification_status="APROVADA")
    assert approved_companies.count() == 4
    assert Company.objects.filter(verification_status="PENDENTE").count() == 1
    approved_workers = Worker.objects.filter(verification_status="APROVADO")
    assert approved_workers.count() == 6
    assert all(w.pix_key for w in approved_workers)
    assert Worker.objects.filter(verification_status="EM_ANALISE").count() == 1

    vacancies = Vacancy.objects.all()
    assert vacancies.count() == 28
    assert len({v.status for v in vacancies}) >= 2
    for vacancy in vacancies:
        assert -24.1 < float(vacancy.latitude) < -23.2
        assert -46.9 < float(vacancy.longitude) < -46.3
    assert Assignment.objects.filter(status="CONFIRMADA").count() == 3

    assert "admin@exemplo.com" in output
    assert "Demo@12345" in output


def test_demo_data_has_valid_documents_and_fake_emails():
    run_seed()

    assert all(is_valid_cnpj(c.cnpj) for c in Company.objects.all())
    assert all(is_valid_cpf(w.cpf) for w in Worker.objects.all())
    assert all(u.email.endswith("@exemplo.com") for u in User.objects.all())


def test_running_twice_does_not_duplicate():
    run_seed()
    counts = (
        User.objects.count(),
        Company.objects.count(),
        Worker.objects.count(),
        Vacancy.objects.count(),
        Assignment.objects.count(),
    )

    run_seed()

    assert counts == (
        User.objects.count(),
        Company.objects.count(),
        Worker.objects.count(),
        Vacancy.objects.count(),
        Assignment.objects.count(),
    )


def test_short_deadlines_sets_minutes_parameters():
    run_seed("--prazos-curtos")

    params = PlatformParameters.get()
    assert params.min_publish_lead_minutes == 1
    assert params.applications_close_minutes_before == 1
    assert params.no_show_tolerance_minutes == 2
    assert params.contest_window_minutes == 2
    assert params.auto_checkout_minutes_after_end == 2


def test_without_flag_keeps_default_deadlines():
    run_seed()

    params = PlatformParameters.get()
    assert params.min_publish_lead_minutes == 720
    assert params.contest_window_minutes == 1440


def test_credentials_can_log_in(client):
    output = run_seed()
    password = re.search(r"Senha de todos os usuários: (\S+)", output).group(1)

    response = client.post(
        "/api/auth/login/",
        {"email": "prestador1@exemplo.com", "password": password},
        content_type="application/json",
    )

    assert response.status_code == 200


def test_catalog_has_varied_published_ads_with_urgent_one():
    run_seed()

    published = Vacancy.objects.filter(status=Vacancy.Status.PUBLISHED)
    assert published.count() >= 12
    assert len({v.category for v in published}) >= 5
    assert len({v.company_id for v in published}) >= 4
    assert published.filter(reopened=True).count() == 1
    assert all(v.starts_at > timezone.now() for v in published)


def test_catalog_respects_lead_time_when_run_at_night():
    # 20:00 em São Paulo: os turnos de "amanhã" às 6h e 7h ficariam a menos de 12h.
    night = datetime(2026, 10, 19, 20, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))

    with patch("django.utils.timezone.now", return_value=night):
        run_seed()

    lead = timedelta(minutes=PlatformParameters.get().min_publish_lead_minutes)
    future = Vacancy.objects.filter(
        status__in=[Vacancy.Status.PUBLISHED, Vacancy.Status.AWAITING_PAYMENT]
    )
    assert future.count() == 14
    assert all(v.starts_at >= night + lead for v in future)


def test_history_has_paid_shifts_reviews_a_no_show_and_hours_to_confirm():
    run_seed()

    assert Vacancy.objects.filter(status=Vacancy.Status.FINISHED).count() >= 12
    assert Assignment.objects.filter(status=Assignment.Status.PAID).count() >= 25
    assert Assignment.objects.filter(status=Assignment.Status.NO_SHOW).count() == 1
    assert Assignment.objects.filter(status=Assignment.Status.AWAITING_VALIDATION).count() == 2
    assert Review.objects.count() >= 40
    assert all(v.starts_at < timezone.now() for v in Vacancy.objects.filter(status="FINALIZADA"))
    # Turnos recentes ainda sem avaliação, para demonstrar a US63 e a US64 ao vivo.
    recent = Assignment.objects.filter(status="PAGA", vacancy__title="Pintura de muro e fachada")
    assert recent.exists() and not Review.objects.filter(
        assignment__in=recent, direction=Review.Direction.WORKER_TO_COMPANY
    ).exists()


def test_history_keeps_every_closed_custody_balanced():
    run_seed()

    for custody in Custody.objects.filter(status="ENCERRADA"):
        totals = {}
        for entry in custody.entries.all():
            totals[entry.kind] = totals.get(entry.kind, 0) + entry.amount_cents
        retained = totals.get(LedgerEntry.Kind.RETENTION, 0)
        released = sum(
            totals.get(kind, 0)
            for kind in (
                LedgerEntry.Kind.WORKER_PAYOUT,
                LedgerEntry.Kind.PLATFORM_FEE,
                LedgerEntry.Kind.COMPANY_REFUND,
            )
        )
        assert retained == released


def test_history_does_not_flood_the_notification_bell():
    run_seed()

    assert Notification.objects.count() < 30


def test_open_applications_show_ratings_and_a_waitlist():
    run_seed()

    pending = Application.objects.filter(status="PENDENTE")
    assert pending.filter(vacancy__title="Apoio de salão em evento corporativo").count() == 4
    assert pending.filter(vacancy__title="Fotógrafo para lançamento de produto").count() == 1


def test_deadline_processing_after_seed_logs_no_warnings(caplog):
    run_seed()

    with caplog.at_level("WARNING", logger="apps.core.deadlines"):
        process_deadlines()

    assert not caplog.records


def test_running_again_days_later_refreshes_the_catalog():
    # No site publicado o seed roda uma vez; dias depois as vagas já passaram.
    run_seed()
    later = timezone.now() + timedelta(days=10)
    with patch("django.utils.timezone.now", return_value=later):
        process_deadlines()
        run_seed()

        published = Vacancy.objects.filter(
            status=Vacancy.Status.PUBLISHED, starts_at__gt=later
        )
        assert published.count() >= 12
        assert published.filter(reopened=True).count() >= 1
        in_progress = Vacancy.objects.filter(status=Vacancy.Status.IN_PROGRESS)
        assert in_progress.filter(title="Conferência de mercadorias no recebimento").exists()
        pending = Application.objects.filter(
            status="PENDENTE", vacancy__starts_at__gt=later
        )
        assert pending.exists()

        counts = Vacancy.objects.count()
        run_seed()
        assert Vacancy.objects.count() == counts


def test_demo_shifts_start_on_the_hour():
    run_seed()

    for vacancy in Vacancy.objects.filter(status=Vacancy.Status.PUBLISHED):
        local = timezone.localtime(vacancy.starts_at)
        assert (local.minute, local.second) == (0, 0)

"""Selo "Contratante premium" (US66).

Critérios (valores em `PlatformParameters`):
- turnos pagos ≥ `premium_min_paid_shifts` (todo o histórico);
- nota média dada pelos prestadores ≥ `premium_min_rating` (a média exibida, 1 casa decimal;
  sem avaliações não há nota e o critério não é cumprido);
- nenhuma contestação perdida (decidida a favor do prestador) na janela `premium_window_days`;
- nenhuma denúncia procedente contra a empresa (ou vagas dela) concluída na janela.

O recálculo roda no `processar_prazos`, é idempotente e só avisa quando o selo muda.
"""

from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Avg, Count
from django.utils import timezone

from apps.companies.models import Company
from apps.core.models import PlatformParameters, StateTransition
from apps.core.notifications import notify_company

EXPLANATION = (
    "Contratante premium: empresa com histórico de turnos pagos, boas avaliações dos "
    "prestadores e nenhuma contestação perdida nem denúncia procedente nos últimos 90 dias."
)


@dataclass(frozen=True)
class Metrics:
    paid_shifts: int
    rating: Decimal | None
    lost_contests: int
    upheld_reports: int


def metrics(company, *, now=None, params=None):
    # Importados aqui: vagas e denúncias dependem de empresas, não o contrário.
    from apps.reports.models import Report
    from apps.vacancies.models import Assignment, Review

    now = now or timezone.now()
    params = params or PlatformParameters.get()
    since = now - timedelta(days=params.premium_window_days)
    S = Assignment.Status
    own = Assignment.objects.filter(vacancy__company=company)
    row = Review.objects.filter(
        assignment__vacancy__company=company, direction=Review.Direction.WORKER_TO_COMPANY
    ).aggregate(avg=Avg("rating"), total=Count("pk"))
    rating = None
    if row["total"]:
        rating = Decimal(str(row["avg"])).quantize(Decimal("0.1"), ROUND_HALF_UP)
    lost = StateTransition.objects.filter(
        entity_type="Assignment",
        entity_id__in=own.values("pk"),
        from_state=S.CONTESTED,
        to_state=S.APPROVED,
        created_at__gte=since,
    ).count()
    upheld = Report.objects.filter(
        company=company, status=Report.Status.UPHELD, decided_at__gte=since
    ).count()
    return Metrics(
        paid_shifts=own.filter(status=S.PAID).count(),
        rating=rating,
        lost_contests=lost,
        upheld_reports=upheld,
    )


def _rating_text(value):
    return f"{value:.1f}".replace(".", ",")


def missing(m, params):
    """O que falta para o selo, em frases curtas (vazio = cumpre tudo)."""
    items = []
    if m.paid_shifts < params.premium_min_paid_shifts:
        count = params.premium_min_paid_shifts - m.paid_shifts
        items.append(f"{count} {'turno pago' if count == 1 else 'turnos pagos'}")
    minimum = _rating_text(params.premium_min_rating)
    if m.rating is None:
        items.append(f"nota média de pelo menos {minimum} (ainda sem avaliações)")
    elif m.rating < params.premium_min_rating:
        items.append(f"nota média de pelo menos {minimum} (hoje {_rating_text(m.rating)})")
    days = params.premium_window_days
    if m.lost_contests:
        items.append(f"nenhuma contestação perdida nos últimos {days} dias")
    if m.upheld_reports:
        items.append(f"nenhuma denúncia procedente nos últimos {days} dias")
    return items


def qualifies(company, *, now=None, params=None):
    params = params or PlatformParameters.get()
    m = metrics(company, now=now, params=params)
    return not missing(m, params), m


def serialize(company, *, now=None, params=None):
    """Para o perfil da empresa: se tem o selo e, se não, o que falta."""
    params = params or PlatformParameters.get()
    m = metrics(company, now=now, params=params)
    return {
        "active": company.premium,
        "since": company.premium_since and company.premium_since.isoformat(),
        "missing": [] if company.premium else missing(m, params),
        "explanation": EXPLANATION,
    }


@transaction.atomic
def recalculate(company, *, now=None, params=None):
    """Concede ou retira o selo. Devolve "GANHOU", "PERDEU" ou "" (sem mudança)."""
    now = now or timezone.now()
    params = params or PlatformParameters.get()
    company = Company.objects.select_for_update().get(pk=company.pk)
    m = metrics(company, now=now, params=params)
    pending = missing(m, params)
    earned = not pending
    if earned == company.premium:
        return ""
    company.premium = earned
    company.premium_since = now if earned else None
    company.save(update_fields=["premium", "premium_since"])
    StateTransition.objects.create(
        entity_type="CompanyPremium",
        entity_id=company.pk,
        from_state="SEM_SELO" if earned else "PREMIUM",
        to_state="PREMIUM" if earned else "SEM_SELO",
        reason="Critérios cumpridos" if earned else "; ".join(pending),
        created_at=now,
    )
    if earned:
        notify_company(
            company,
            "PREMIUM",
            "Sua empresa agora é Contratante premium",
            "O selo aparece ao lado do nome da empresa na busca e no detalhe das vagas.",
            link="/empresa/perfil",
        )
        return "GANHOU"
    notify_company(
        company,
        "PREMIUM",
        "Sua empresa perdeu o selo de Contratante premium",
        f"Motivo: falta {'; '.join(pending)}.",
        link="/empresa/perfil",
    )
    return "PERDEU"


def recalculate_all(*, now=None):
    """Passo do `processar_prazos`: empresas aprovadas e as que hoje têm o selo."""
    params = PlatformParameters.get()
    done = {"GANHOU": 0, "PERDEU": 0}
    candidates = Company.objects.filter(verification_status=Company.VerificationStatus.APPROVED)
    for company in candidates | Company.objects.filter(premium=True):
        change = recalculate(company, now=now, params=params)
        if change:
            done[change] += 1
    return done

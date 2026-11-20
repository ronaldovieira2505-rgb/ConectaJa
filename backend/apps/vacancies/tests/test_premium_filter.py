"""US67: filtro "Só contratantes premium" na busca de vagas."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.companies.models import Company
from apps.core.tests.factories import make_company, make_published_vacancy, make_worker

pytestmark = pytest.mark.django_db

URL = "/api/vacancies/"


def premium_company():
    company = make_company()
    Company.objects.filter(pk=company.pk).update(premium=True)
    company.refresh_from_db()
    return company


def ids(response):
    assert response.status_code == 200
    return [v["id"] for v in response.json()["results"]]


def test_only_premium_companies_when_the_filter_is_on():
    now = timezone.now()
    gold = make_published_vacancy(company=premium_company(), now=now)
    plain = make_published_vacancy(company=make_company(), now=now)
    client = APIClient()  # funciona sem login
    assert set(ids(client.get(URL))) == {gold.pk, plain.pk}
    assert ids(client.get(URL, {"premium": "1"})) == [gold.pk]
    assert ids(client.get(URL, {"premium": "true"})) == [gold.pk]
    assert set(ids(client.get(URL, {"premium": "0"}))) == {gold.pk, plain.pk}


def test_premium_combines_with_text_category_dates_pay_and_distance():
    now = timezone.now()
    company = premium_company()
    match = make_published_vacancy(
        company=company,
        now=now,
        title="Limpeza de galpão",
        category="LIMPEZA",
        pay_per_person_cents=20000,
    )
    other_category = make_published_vacancy(company=company, now=now, category="CARGA_DESCARGA")
    later = make_published_vacancy(
        company=company,
        now=now,
        starts_in_hours=24 * 10,
        title="Limpeza de vitrine",
        category="LIMPEZA",
        pay_per_person_cents=20000,
    )
    cheap = make_published_vacancy(
        company=company,
        now=now,
        title="Limpeza rápida",
        category="LIMPEZA",
        pay_per_person_cents=5000,
    )
    not_premium = make_published_vacancy(
        company=make_company(),
        now=now,
        title="Limpeza geral",
        category="LIMPEZA",
        pay_per_person_cents=20000,
    )
    day = timezone.localtime(match.starts_at).date()
    params = {
        "premium": "1",
        "q": "limpeza",
        "category": "LIMPEZA",
        "date_from": day.isoformat(),
        "date_to": (day + timedelta(days=1)).isoformat(),
        "min_pay": "10000",
        "lat": "-23.550520",
        "lng": "-46.633308",
    }
    found = ids(APIClient().get(URL, params))
    assert found == [match.pk]
    assert other_category.pk not in found
    assert later.pk not in found
    assert cheap.pk not in found
    assert not_premium.pk not in found


def test_logged_in_worker_can_use_the_filter_too():
    now = timezone.now()
    gold = make_published_vacancy(company=premium_company(), now=now)
    make_published_vacancy(company=make_company(), now=now)
    client = APIClient()
    client.force_login(make_worker().user)
    assert ids(client.get(URL, {"premium": "1"})) == [gold.pk]

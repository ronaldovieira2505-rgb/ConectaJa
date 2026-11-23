import pytest
from django.urls import reverse

from apps.core.tests.factories import make_admin, make_paid_ready_assignment, make_user
from apps.vacancies import assignment_services as assignments
from apps.vacancies.history import build_history, financial_summary

pytestmark = pytest.mark.django_db


@pytest.fixture
def settled():
    assignment = make_paid_ready_assignment()
    assignments.settle(assignment)
    assignment.refresh_from_db()
    return assignment


def _url(vacancy):
    return reverse("admin:vacancies_vacancy_full_history", args=[vacancy.pk])


def test_history_is_chronological_and_complete(settled):
    events = build_history(settled.vacancy)
    times = [e.at for e in events]
    assert times == sorted(times)

    descriptions = " | ".join(f"{e.category}:{e.description}:{e.to_state}" for e in events)
    assert "Vaga:Vaga" in descriptions and "Publicada" in descriptions
    assert "Candidatura" in descriptions and "Aprovada" in descriptions
    assert "Alocação" in descriptions and "Em execução" in descriptions
    assert "Paga" in descriptions
    assert "Custódia" in descriptions
    assert "Livro-razão: Retenção" in descriptions
    assert "Livro-razão: Repasse ao prestador" in descriptions
    assert "Livro-razão: Taxa da plataforma" in descriptions

    first = events[0]
    assert first.category == "Vaga" and first.to_state == "Aguardando pagamento"
    check_in = next(e for e in events if e.detail.startswith("Check-in a "))
    assert check_in.to_state == "Em execução"


def test_history_shows_actor_and_states(settled):
    events = build_history(settled.vacancy)
    assert any(e.actor == "SISTEMA" for e in events)
    paid = next(e for e in events if e.category == "Alocação" and e.to_state == "Paga")
    assert paid.from_state == "Aprovada"
    assert paid.reason == "Liquidação do turno"


def test_financial_summary_balances(settled):
    summary = financial_summary(settled.vacancy)
    assert summary["retained_cents"] == 10000
    assert summary["paid_out_cents"] == 9700
    assert summary["fees_cents"] == 300
    assert summary["refunded_cents"] == 0
    assert summary["balanced"] is True


def test_admin_page_renders_masked_data(client, settled):
    client.force_login(make_admin())
    response = client.get(_url(settled.vacancy))
    assert response.status_code == 200
    html = response.content.decode()
    assert "Resumo financeiro" in html
    assert "Fecha" in html
    assert "R$ 97,00" in html
    worker = settled.worker
    assert worker.cpf not in html
    assert worker.pix_key not in html
    assert worker.masked_cpf in html
    assert worker.masked_pix_key in html


def test_change_form_links_to_history(client, settled):
    client.force_login(make_admin())
    response = client.get(reverse("admin:vacancies_vacancy_change", args=[settled.vacancy.pk]))
    assert "Ver histórico completo" in response.content.decode()
    assert _url(settled.vacancy) in response.content.decode()


def test_non_admin_cannot_access(client, settled):
    client.force_login(settled.worker.user)
    response = client.get(_url(settled.vacancy))
    assert response.status_code in (302, 403)
    if response.status_code == 302:
        assert "/admin/login/" in response["Location"]


def test_anonymous_is_redirected_to_login(client, settled):
    response = client.get(_url(settled.vacancy))
    assert response.status_code == 302
    assert "/admin/login/" in response["Location"]


def test_company_user_cannot_access(client, settled):
    client.force_login(make_user())
    assert client.get(_url(settled.vacancy)).status_code in (302, 403)


def test_unknown_vacancy_returns_404(client):
    client.force_login(make_admin())
    url = reverse("admin:vacancies_vacancy_full_history", args=[9999])
    assert client.get(url).status_code == 404


def test_open_vacancy_shows_amount_still_held_instead_of_not_balanced(client):
    """Com a vaga em andamento, a diferença é o valor ainda retido, e não um erro de conta."""
    assignment = make_paid_ready_assignment()  # horas aprovadas, ainda sem liquidação
    vacancy = assignment.vacancy
    vacancy.refresh_from_db()
    summary = financial_summary(vacancy)
    assert summary["balanced"] is False
    assert summary["open"] is True
    assert summary["held_display"] == "R$ 100,00"
    client.force_login(make_admin())
    html = client.get(_url(vacancy)).content.decode()
    assert "Em aberto: R$ 100,00 ainda retido" in html
    assert "Não fecha" not in html

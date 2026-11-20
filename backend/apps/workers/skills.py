"""Habilidades e experiência do prestador (US08): categorias das vagas e um resumo curto.

O resumo não pode ter e-mail nem telefone: o contato só é liberado depois da alocação
(`docs/regras-de-negocio.md` §5). A validação é simples, como decidiu o PO.
"""

import re

from django.db import transaction

from apps.core.exceptions import DomainError

MAX_SKILLS = 7
BIO_MAX_LENGTH = 500
MIN_PHONE_DIGITS = 8

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Sequência de números com separadores comuns de telefone: (11) 98888-7777, 11 9888 7777...
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{6,}\d")

CONTACT_ERROR = (
    "Não coloque e-mail nem telefone no resumo: o contato só é liberado depois da alocação."
)


def category_labels():
    # Importado aqui: vagas dependem de prestadores, não o contrário.
    from apps.vacancies.models import Vacancy

    return dict(Vacancy.Category.choices)


def clean_skills(value):
    labels = category_labels()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise DomainError("Envie as habilidades como uma lista de categorias.")
    if len(value) > MAX_SKILLS:
        raise DomainError(f"Escolha no máximo {MAX_SKILLS} categorias.")
    if len(set(value)) != len(value):
        raise DomainError("Cada categoria só pode aparecer uma vez.")
    unknown = [item for item in value if item not in labels]
    if unknown:
        raise DomainError("Categoria inexistente: escolha entre as categorias das vagas.")
    return value


def has_contact(text):
    if EMAIL_RE.search(text):
        return True
    return any(
        sum(c.isdigit() for c in match.group()) >= MIN_PHONE_DIGITS
        for match in PHONE_RE.finditer(text)
    )


def clean_bio(value):
    if not isinstance(value, str):
        raise DomainError("Resumo inválido.")
    value = value.strip()
    if len(value) > BIO_MAX_LENGTH:
        raise DomainError(f"O resumo pode ter no máximo {BIO_MAX_LENGTH} caracteres.")
    if has_contact(value):
        raise DomainError(CONTACT_ERROR)
    return value


@transaction.atomic
def update_skills(worker, changes):
    """Atualiza só os campos enviados (`skills`, `bio`). Erro em qualquer um: nada é salvo."""
    cleaned = {}
    if "skills" in changes:
        cleaned["skills"] = clean_skills(changes["skills"])
    if "bio" in changes:
        cleaned["bio"] = clean_bio(changes["bio"])
    if not cleaned:
        raise DomainError("Informe as habilidades ou o resumo.")
    for field, value in cleaned.items():
        setattr(worker, field, value)
    worker.save(update_fields=list(cleaned))
    return worker


def serialize_skills(skills, vacancy_category=None):
    """Categorias com o rótulo; `matches_vacancy` destaca a categoria da vaga (empresa)."""
    labels = category_labels()
    items = []
    for value in skills or []:
        if value not in labels:
            continue
        item = {"value": value, "label": labels[value]}
        if vacancy_category is not None:
            item["matches_vacancy"] = value == vacancy_category
        items.append(item)
    return items

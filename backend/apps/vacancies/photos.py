"""Foto do local do turno: troca e remoção do arquivo."""

import uuid

from django.core.files.base import ContentFile

from apps.core.exceptions import DomainError
from apps.core.images import content_type_of, validate_image, version_of
from apps.vacancies.models import Vacancy

__all__ = [
    "PhotoLockedError",
    "content_type_of",
    "copy_photo",
    "photo_url",
    "remove_photo",
    "set_photo",
]

LOCKED_STATUSES = (Vacancy.Status.FINISHED, Vacancy.Status.CANCELLED)
LOCKED = "Não é possível alterar a foto de uma vaga encerrada."


class PhotoLockedError(DomainError):
    """A vaga já terminou ou foi cancelada: a foto não muda mais."""


def set_photo(vacancy, uploaded):
    """Grava a foto enviada no lugar da anterior."""
    if vacancy.status in LOCKED_STATUSES:
        raise PhotoLockedError(LOCKED)
    extension = validate_image(uploaded)
    old_name = vacancy.photo.name
    # Nome novo a cada envio: o endereço muda e o navegador não mostra a foto antiga do cache.
    vacancy.photo.save(f"{vacancy.pk}-{uuid.uuid4().hex[:12]}.{extension}", uploaded, save=True)
    if old_name:
        vacancy.photo.storage.delete(old_name)
    return vacancy


def remove_photo(vacancy):
    if vacancy.status in LOCKED_STATUSES:
        raise PhotoLockedError(LOCKED)
    if vacancy.photo:
        vacancy.photo.delete(save=True)
    return vacancy


def copy_photo(source, target):
    """Vaga duplicada (US25): copia o arquivo da foto, para cada vaga ter o seu.

    Sem foto na original (ou arquivo sumido do disco), a vaga nova fica sem foto.
    Devolve se copiou.
    """
    if not source.photo:
        return False
    try:
        with source.photo.open("rb") as handle:
            content = handle.read()
    except FileNotFoundError:
        return False
    extension = source.photo.name.rsplit(".", 1)[-1].lower()
    target.photo.save(
        f"{target.pk}-{uuid.uuid4().hex[:12]}.{extension}", ContentFile(content), save=True
    )
    return True


def photo_url(vacancy):
    """Endereço da foto servida pela API; None quando a vaga não tem foto."""
    if not vacancy.photo:
        return None
    return f"/api/vacancies/{vacancy.pk}/photo/?v={version_of(vacancy.photo.name)}"

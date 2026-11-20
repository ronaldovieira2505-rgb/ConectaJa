"""Fotos de trabalhos anteriores do prestador (US09).

Ficam em armazenamento privado e só são servidas pela API: ao próprio prestador, ao admin e às
empresas em que ele tem candidatura ou alocação.
"""

import uuid

from django.db import transaction

from apps.accounts.models import Role
from apps.core.exceptions import DomainError
from apps.core.images import validate_image
from apps.workers.models import PortfolioPhoto

MAX_PHOTOS = 8


def clean_caption(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise DomainError("Legenda inválida.")
    value = value.strip()
    if len(value) > PortfolioPhoto.CAPTION_MAX_LENGTH:
        raise DomainError(
            f"A legenda pode ter no máximo {PortfolioPhoto.CAPTION_MAX_LENGTH} caracteres."
        )
    return value


@transaction.atomic
def add_photo(worker, uploaded, caption=""):
    """Valida (JPG, PNG ou WebP até 5 MB), respeita o limite de 8 e grava."""
    caption = clean_caption(caption)
    extension = validate_image(uploaded)
    # Trava as fotos do prestador para dois envios simultâneos não passarem do limite.
    count = PortfolioPhoto.objects.select_for_update().filter(worker=worker).count()
    if count >= MAX_PHOTOS:
        raise DomainError(f"Você já tem {MAX_PHOTOS} fotos. Remova uma para adicionar outra.")
    photo = PortfolioPhoto(worker=worker, caption=caption)
    photo.file.save(f"{worker.pk}-{uuid.uuid4().hex[:12]}.{extension}", uploaded, save=True)
    return photo


def remove_photo(photo):
    stored = photo.file
    photo.delete()
    transaction.on_commit(lambda: stored.delete(save=False))


def photo_url(photo):
    return f"/api/workers/portfolio/{photo.pk}/file/"


def serialize_photos(worker):
    return [
        {
            "id": photo.pk,
            "caption": photo.caption,
            "url": photo_url(photo),
            "created_at": photo.created_at.isoformat(),
        }
        for photo in worker.portfolio.all()
    ]


def can_view(user, worker):
    """Dono, admin ou empresa em que o prestador tem candidatura ou alocação."""
    if not (user and user.is_authenticated):
        return False
    if user.is_staff or user.role == Role.ADMIN:
        return True
    if user.role == Role.WORKER:
        return getattr(user, "worker", None) is not None and user.worker.pk == worker.pk
    if user.role == Role.COMPANY:
        company_ids = user.company_memberships.values("company_id")
        return worker.applications.filter(vacancy__company_id__in=company_ids).exists()
    return False

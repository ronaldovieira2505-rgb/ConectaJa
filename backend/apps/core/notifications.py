"""Notificações dentro do app."""

from django.db import IntegrityError, transaction

from apps.core.models import Notification


def notify(user, kind, title, message="", link=""):
    return Notification.objects.create(
        user=user, kind=kind, title=title, message=message, link=link
    )


def notify_once(user, dedup_key, kind, title, message="", link=""):
    """Cria a notificação só se ainda não existe uma com a mesma chave. Devolve se criou.

    A chave é única no banco: duas execuções simultâneas não geram aviso duplicado.
    """
    try:
        with transaction.atomic():
            _, created = Notification.objects.get_or_create(
                dedup_key=dedup_key,
                defaults={
                    "user": user,
                    "kind": kind,
                    "title": title,
                    "message": message,
                    "link": link,
                },
            )
    except IntegrityError:
        return False
    return created


def notify_company(company, kind, title, message="", link=""):
    for member in company.members.select_related("user"):
        notify(member.user, kind, title, message, link)


def notify_admins(kind, title, message="", link=""):
    from django.contrib.auth import get_user_model

    for admin in get_user_model().objects.filter(is_staff=True, is_active=True):
        notify(admin, kind, title, message, link)

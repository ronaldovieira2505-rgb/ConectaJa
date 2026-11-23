#!/bin/sh
# Ponto de entrada da imagem Docker (veja o Dockerfile na raiz).
#   web            -> migrações, dados de demonstração opcionais e gunicorn (padrão)
#   prazos [args]  -> processar_prazos uma vez, ou em laço com "--loop SEGUNDOS"
#   outro comando  -> executado como veio (ex.: "python manage.py createsuperuser")
set -e

command="${1:-web}"

case "$command" in
    web)
        if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
            python manage.py migrate --noinput
        fi

        if [ "$SEED_DEMO" = "true" ]; then
            # Um erro nos dados de demonstração não pode derrubar o site.
            python manage.py seed_demo || echo "seed_demo falhou; o site sobe mesmo assim" >&2
        fi

        # A senha do admin do seed_demo é pública (README); em produção ela vem do ambiente.
        if [ -n "$ADMIN_PASSWORD" ]; then
            python manage.py shell -c "import os; from django.contrib.auth import get_user_model; u = get_user_model().objects.filter(email__iexact='admin@exemplo.com').first(); u and (u.set_password(os.environ['ADMIN_PASSWORD']), u.save())"
        fi

        exec gunicorn config.wsgi \
            --bind "0.0.0.0:${PORT:-8000}" \
            --workers "${WEB_CONCURRENCY:-2}" \
            --threads "${GUNICORN_THREADS:-4}" \
            --timeout 120 \
            --access-logfile -
        ;;
    prazos)
        shift
        exec python manage.py processar_prazos "$@"
        ;;
    *)
        exec "$@"
        ;;
esac

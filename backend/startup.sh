#!/bin/sh
# Inicialização no Azure App Service (Linux). Comando de inicialização do app: "sh startup.sh".
# Variáveis esperadas nas App Settings: veja docs/deploy-azure.md.
set -e

mkdir -p /home/data
python manage.py migrate --noinput
python manage.py collectstatic --noinput

if [ "$SEED_DEMO" = "true" ]; then
    python manage.py seed_demo
fi

# A senha do admin do seed_demo é pública (README); em produção ela vem da App Setting.
if [ -n "$ADMIN_PASSWORD" ]; then
    python manage.py shell -c "import os; from django.contrib.auth import get_user_model; u = get_user_model().objects.filter(email__iexact='admin@exemplo.com').first(); u and (u.set_password(os.environ['ADMIN_PASSWORD']), u.save())"
fi

# Prazos (encerrar candidaturas, falta, check-out e aprovação automáticos). No plano gratuito
# o app dorme quando fica ocioso; os prazos vencidos são aplicados quando ele acorda.
python manage.py processar_prazos --loop 60 &

exec gunicorn config.wsgi --bind=0.0.0.0:"${PORT:-8000}" --workers 1 --threads 4 \
    --timeout 120 --access-logfile -

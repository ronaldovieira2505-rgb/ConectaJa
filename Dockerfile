# Imagem única do Conecta Já: a API Django serve também o frontend compilado (mesma origem).
# A mesma imagem roda o site (padrão) e o processamento de prazos (`prazos`).
# Build:  docker build -t conecta-ja .
# Rodar:  veja docker-compose.yml (perfil "app") e docs/deploy-container-apps.md.

# ─── 1. Frontend: compila o React ────────────────────────────────────────────
FROM node:22-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ─── 2. Aplicação: Python + gunicorn ─────────────────────────────────────────
FROM python:3.12-slim AS app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000 \
    FRONTEND_DIST=/app/frontend_dist \
    PRIVATE_MEDIA_ROOT=/data/private_media

WORKDIR /app

# Usuário sem privilégios; o uid fixo é o mesmo usado nas opções de montagem do Azure Files.
RUN useradd --create-home --uid 10001 app

COPY backend/requirements.txt ./
RUN pip install -r requirements.txt

COPY backend/ ./
COPY --from=frontend /frontend/dist ./frontend_dist

# Os arquivos estáticos do Django (admin, DRF) vão para a imagem; a chave abaixo só existe no build.
RUN SECRET_KEY=build-only-not-a-secret DATABASE_URL=sqlite:////tmp/build.sqlite3 \
        python manage.py collectstatic --noinput \
    && rm -f /tmp/build.sqlite3 \
    && mkdir -p /data/private_media \
    && chown -R app:app /data

USER app
EXPOSE 8000

# Usado pelo Docker e pelo docker compose; no Azure valem as sondas configuradas no app.
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/api/health/live/', timeout=4)"

ENTRYPOINT ["sh", "docker-entrypoint.sh"]
CMD ["web"]

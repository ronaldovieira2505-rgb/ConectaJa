# Deploy no Azure (plano gratuito)

> Este é o deploy simplificado, por zip no App Service F1 com SQLite, bom só para
> demonstração. O caminho recomendado é a imagem Docker no Azure Container Apps com
> PostgreSQL: veja [deploy-container-apps.md](deploy-container-apps.md).

Um único **App Service Linux F1 (Free)** roda o Django com gunicorn e serve também o build do
React (WhiteNoise). Frontend e API ficam na mesma origem, então a sessão e o CSRF funcionam sem
CORS. O banco é **SQLite** no disco persistente do App Service (`/home/data`).

Limites do F1: 60 min de CPU por dia, 1 GB de RAM, sem "Always On" (o app dorme depois de
~20 min sem acesso e a primeira requisição seguinte demora alguns segundos). SQLite serve para a
demonstração com pouco tráfego; para uso real, troque `DATABASE_URL` por um PostgreSQL.

## 1. Criar o aplicativo web (portal)

Portal do Azure → **Criar um recurso → Aplicativo Web**.

- **Básico**: assinatura *Azure for Students*; grupo de recursos novo `rg-conectaja`; nome único
  (ex.: `conectaja`); **Publicar: Código**; **Pilha de runtime: Python 3.12**; **Sistema
  operacional: Linux**; **Região: Brazil South**; plano novo `plan-conectaja` com **Plano de
  preços: Gratuito F1**.
- **Implantação**: deixe a implantação contínua **desabilitada**.
- **Monitoramento**: Application Insights **Não**.
- **Revisar + criar → Criar**.

## 2. Variáveis de ambiente

No app: **Configurações → Variáveis de ambiente → Configurações de aplicativo → + Adicionar**,
uma por vez (ou **Edição avançada** e cole tudo como JSON). Depois **Aplicar → Confirmar**.

| Nome | Valor |
|---|---|
| `SECRET_KEY` | texto aleatório longo (ex.: `python -c "import secrets; print(secrets.token_urlsafe(50))"`) |
| `DEBUG` | `false` |
| `ALLOWED_HOSTS` | `.azurewebsites.net` |
| `CSRF_TRUSTED_ORIGINS` | `https://*.azurewebsites.net` |
| `DATABASE_URL` | `sqlite:////home/data/db.sqlite3` |
| `PRIVATE_MEDIA_ROOT` | `/home/data/private_media` |
| `SEED_DEMO` | `true` (cria os dados de demonstração; idempotente) |
| `ADMIN_PASSWORD` | senha forte para `admin@exemplo.com` (a do seed é pública) |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | `true` |
| `DISABLE_COLLECTSTATIC` | `true` |

Opcionais (os padrões já servem): `SECURE_HSTS_SECONDS` (`3600`), `LOGIN_THROTTLE_RATE`
(`10/min`), `LOG_LEVEL` (`WARNING`). Com `DEBUG=false` o app redireciona HTTP para HTTPS e
marca os cookies como seguros; `/api/health/` continua respondendo por HTTP para a sonda do
Azure.

Nunca use `seed_demo --prazos-curtos` aqui: ele troca os parâmetros da plataforma no banco.

## 3. Comando de inicialização

**Configurações → Configuração → Configurações gerais → Comando de inicialização:**
`sh startup.sh` → **Salvar → Continuar**.

## 4. Publicar pelo VS Code

1. Instale a extensão **Azure App Service** no VS Code e entre na conta do Azure (ícone do Azure
   na barra lateral → *Sign in to Azure*).
2. Gere o build do frontend dentro do backend (PowerShell, na raiz do repositório):

   ```powershell
   .\scripts\build-frontend.ps1
   ```

3. Ícone do Azure → **App Service** → assinatura → clique com o botão direito no app →
   **Deploy to Web App...** → confirme. O `.vscode/settings.json` do repositório faz enviar só a
   pasta `backend` (sem banco local nem uploads).

A primeira inicialização instala as dependências e roda as migrations: leva de 2 a 5 minutos.
Acompanhe em **Monitoramento → Fluxo de log** e teste
`https://<nome-do-app>.azurewebsites.net/api/health/` (deve responder `{"status": "ok"}`).
Para publicar uma nova versão, repita os passos 2 e 3.

## O que roda na inicialização (`backend/startup.sh`)

1. `migrate` e `collectstatic`.
2. `seed_demo`, se `SEED_DEMO=true`.
3. Troca a senha do `admin@exemplo.com` pela `ADMIN_PASSWORD`.
4. `processar_prazos --loop 60` em segundo plano. Com o app dormindo, os prazos vencidos são
   aplicados quando ele acorda.
5. gunicorn (1 worker, 4 threads).

## Problemas comuns

- **Application Error / 503 logo após publicar**: espere a primeira inicialização terminar e veja
  o **Fluxo de log**.
- **Página do React não aparece (404 em `/`)**: faltou o passo 4.2 antes de publicar.
- **Recomeçar o banco do zero**: no Kudu (`https://<nome-do-app>.scm.azurewebsites.net`), apague
  `/home/data/db.sqlite3` e reinicie o app.

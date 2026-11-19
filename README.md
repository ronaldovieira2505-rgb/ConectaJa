# Conecta Já

Marketplace que conecta empresas (Contratantes) a trabalhadores autônomos (Contratados) para
serviços manuais de curta duração. Projeto acadêmico (`MVP_Ecommerce`).

- `backend/`: Django + Django REST Framework + PostgreSQL
- `frontend/`: React + TypeScript (Vite), estilos em `src/styles/app.css` + utilitários Tailwind
- `docs/`: documentação de domínio
- `docs/deploy-azure.md`: publicação em produção
- `scripts/`: utilitários de build e publicação
- `docs/guia-do-repositorio.md`: regras do projeto

## Pré-requisitos (Windows)

- Python 3.12
- Node.js LTS
- PostgreSQL 16 instalado, **ou** Docker Desktop (para usar o `docker-compose.yml`)

Os comandos abaixo são para o **PowerShell**, a partir da raiz do repositório.

## Banco de dados

Opção 1 — Docker (recomendado):

```powershell
docker compose up -d
```

Opção 2 — PostgreSQL instalado: crie o usuário e o banco `conectaja` (senha `conectaja`) ou
ajuste `DATABASE_URL`.

## Backend

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r backend\requirements-dev.txt

$env:SECRET_KEY = "dev-secret"
$env:DEBUG = "true"
$env:ALLOWED_HOSTS = "localhost,127.0.0.1"
$env:DATABASE_URL = "postgres://conectaja:conectaja@localhost:5432/conectaja"

python backend\manage.py migrate
python backend\manage.py runserver
```

O backend não carrega o arquivo `.env` sozinho; as variáveis precisam estar no ambiente
(veja `.env.example` para a lista). Teste em <http://localhost:8000/api/health/>: deve
responder `200` com `{"status": "ok"}`.

## Dados de exemplo

Com o backend configurado (variáveis acima), rode uma vez:

```powershell
python backend\manage.py seed_demo
```

Simula a plataforma em uso há algumas semanas: 4 empresas aprovadas (com logo e apresentação),
6 prestadores aprovados (com foto, documentos e PIX), 13 turnos já realizados e pagos nas
últimas 6 semanas (com avaliações nos dois sentidos, uma falta e uma contestação resolvida),
1 turno aguardando a empresa confirmar as horas, 14 vagas futuras (uma "Urgente") e
candidaturas em aberto, incluindo uma lista de espera. A carteira, as avaliações e os
indicadores do admin já aparecem preenchidos. Senha de todas as contas: `Demo@12345`; a lista
de e-mails aparece no final do comando e em `docs/roteiro-demo.md`. Rodar de novo não duplica
nada; para recomeçar do zero com SQLite, apague o `db.sqlite3` e rode `migrate` e o comando.

## Frontend

Em outro terminal:

```powershell
npm --prefix frontend install
npm --prefix frontend run dev
```

Abra <http://localhost:5173>. O Vite encaminha `/api` para `http://localhost:8000`
(mude com `VITE_API_PROXY_TARGET`). Sem login, a raiz mostra a página inicial pública com as
vagas abertas; depois do login, cada perfil cai na sua área.

## Processamento de prazos

As transições por prazo (encerrar candidaturas, falta, check-out automático, aprovação
automática etc.) são aplicadas pelo `processar_prazos`. Em um terceiro terminal do PowerShell,
com o ambiente virtual ativo e as variáveis do backend definidas:

```powershell
python backend\manage.py processar_prazos --loop 15
```

Ele repete a cada 15 segundos até você apertar `Ctrl+C`. Sem `--loop`, roda uma vez.

## Dados de demonstração

```powershell
python backend\manage.py seed_demo
python backend\manage.py seed_demo --prazos-curtos
```

Cria os dados descritos em "Dados de exemplo" acima. É seguro rodar de novo: não duplica dados.
Com `--prazos-curtos`, os prazos ficam em minutos para a demonstração ao vivo.
As credenciais aparecem no terminal ao final:

| Perfil | E-mail | Senha |
|---|---|---|
| Admin (`/admin`) | `admin@exemplo.com` | `Demo@12345` |
| Empresas aprovadas | `empresa1@exemplo.com` a `empresa4@exemplo.com` | `Demo@12345` |
| Empresa pendente | `empresa.pendente@exemplo.com` | `Demo@12345` |
| Prestadores aprovados | `prestador1@exemplo.com` a `prestador6@exemplo.com` | `Demo@12345` |
| Prestador pendente | `prestador.pendente@exemplo.com` | `Demo@12345` |

O passo a passo da apresentação está em `docs/roteiro-demo.md`.

## Testes e qualidade

Backend (com o ambiente virtual ativo e as variáveis acima definidas):

```powershell
ruff check backend
pytest backend
python backend\manage.py makemigrations --check --dry-run
```

Frontend:

```powershell
npm --prefix frontend run lint
npm --prefix frontend test
npm --prefix frontend run build
```

`npm test` roda os testes uma vez e termina (sem modo watch). O CI executa todos esses comandos.

## Produção

Em produção o Django serve a API e o build do React na mesma origem (gunicorn + WhiteNoise).
Com `DEBUG=false` valem HTTPS obrigatório, HSTS, cookies seguros e limite de tentativas de
login; as variáveis estão em `.env.example`. Para conferir a configuração:

```powershell
python backend\manage.py check --deploy
```

O passo a passo da publicação está em `docs/deploy-azure.md`.

## Integrações externas

Ficam em `backend/integrations/`, atrás de uma interface com implementação fake. Veja o
`README.md` da pasta.

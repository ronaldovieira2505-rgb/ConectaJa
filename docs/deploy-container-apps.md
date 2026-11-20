# Deploy no Azure Container Apps

Guia passo a passo para publicar o Conecta Já em [portal.azure.com](https://portal.azure.com) usando
a imagem Docker gerada pelo CI. Os nomes dos menus estão em português, com o nome em inglês entre
parênteses. O portal muda de vez em quando, então um rótulo pode estar um pouco diferente.

Este é o caminho recomendado. O deploy antigo, por zip no App Service F1 com SQLite, continua
descrito em [deploy-azure.md](deploy-azure.md) e serve só para demonstração.

## Visão geral

| Recurso | Nome sugerido | Para quê |
| --- | --- | --- |
| Grupo de recursos | `rg-conectaja` | Agrupa tudo |
| Banco PostgreSQL (servidor flexível) | `conectaja-pg`, banco `conectaja` | Dados da aplicação |
| Conta de armazenamento + compartilhamento de arquivos | `conectajafiles`, compartilhamento `private-media` | Documentos, selfies, fotos de vagas e logos |
| Imagem do contêiner | `ghcr.io/<dono-do-repositorio>/conecta-ja` | Publicada pelo GitHub Actions |
| Ambiente do Container Apps | `conectaja-env` | Rede e logs compartilhados |
| Container App | `conectaja-web` (entrada externa) | Site e API |
| Container Apps Job | `conectaja-prazos` (agendado) | Processamento de prazos |

```text
Navegador ──HTTPS──> conectaja-web ──> PostgreSQL (conectaja-pg)
                          │
                          └──> Azure Files (/data/private_media)

conectaja-prazos (a cada 5 min) ──> PostgreSQL
```

A mesma imagem roda o site (`web`, padrão) e os prazos (`prazos`). Veja o
[Dockerfile](../Dockerfile) e o [docker-entrypoint.sh](../backend/docker-entrypoint.sh).

Use **a mesma região em todos os recursos**. O exemplo usa Brazil South. Se a assinatura de
estudante recusar a região, escolha outra permitida e use essa em tudo.

**Custos:** o PostgreSQL B1ms tem 12 meses gratuitos para estudantes, e o Container Apps tem uma
cota mensal gratuita no plano de consumo. Confira o aviso de gratuidade na tela de criação e
acompanhe em **Gerenciamento de Custos (Cost Management)**. A imagem fica no GitHub Container
Registry, sem custo.

### Antes de começar

Testes o contêiner na sua máquina, com Docker Desktop aberto:

```powershell
docker compose --profile app up --build
```

Abra <http://localhost:8080>. É a mesma imagem que vai para o Azure, com PostgreSQL, dados de
demonstração e prazos rodando. Para desligar: `docker compose --profile app down`.

---

## Parte 1 — Imagem do contêiner (GitHub Container Registry)

1. A cada push na `main`, o workflow `CI` (`.github/workflows/ci.yml`) roda os testes, monta a
   imagem, sobe o contêiner para testar as sondas e publica:
   - `ghcr.io/<dono>/conecta-ja:latest`
   - `ghcr.io/<dono>/conecta-ja:<commit de 7 caracteres>`

   `<dono>` é o dono do repositório no GitHub, em minúsculas. O endereço exato aparece no resumo
   da execução do workflow.
2. Na primeira vez, deixe o pacote público para o Azure baixar sem senha:
   - No GitHub, abra o perfil do dono do repositório e a aba **Packages**.
   - Abra `conecta-ja` e clique em **Package settings**.
   - Em **Danger Zone**, clique em **Change visibility**, escolha **Public** e confirme.
   - A imagem não carrega segredos: banco, chaves e senhas ficam no Azure.

   Se preferir manter o pacote privado, crie um token do GitHub com permissão `read:packages` e
   informe usuário e token na etapa 5.4 (**Tipo de imagem: Privado**).

---

## Parte 2 — Grupo de recursos e banco de dados

### 2.1 Criar o grupo de recursos

1. Busque **Grupos de recursos (Resource groups)** e clique em **+ Criar (Create)**.
2. **Assinatura:** Azure for Students. **Grupo de recursos:** `rg-conectaja`. **Região:** Brazil South.
3. Clique em **Revisar + criar (Review + create)** e depois em **Criar (Create)**.

### 2.2 Criar o servidor PostgreSQL

1. Busque **Servidores flexíveis do Banco de Dados do Azure para PostgreSQL**
   (**Azure Database for PostgreSQL flexible servers**) e clique em **+ Criar (Create)**.
2. Aba **Básico (Basics)**:
   - **Grupo de recursos:** `rg-conectaja`.
   - **Nome do servidor:** `conectaja-pg`. Se o nome já existir, use um sufixo.
   - **Região:** Brazil South. **Versão do PostgreSQL:** 16.
   - **Tipo de carga de trabalho:** Desenvolvimento (Development).
   - **Computação + armazenamento:** **Com intermitência (Burstable)**, **Standard_B1ms**, 32 GiB.
     Alta disponibilidade desativada.
   - **Método de autenticação:** Somente autenticação do PostgreSQL.
   - **Nome de usuário do administrador:** `conectaja`.
   - **Senha:** crie uma senha forte e guarde num gerenciador de senhas. Ela não vai para o
     repositório nem para grupos de mensagem.
3. Aba **Rede (Networking)**:
   - **Método de conectividade:** Acesso público (endereços IP permitidos).
   - Marque **Permitir acesso público de qualquer serviço do Azure dentro do Azure a este servidor**.
   - Não adicione a faixa `0.0.0.0–255.255.255.255`.
4. Clique em **Revisar + criar** e depois em **Criar**. Leva alguns minutos.

### 2.3 Criar o banco

1. Abra o servidor `conectaja-pg`.
2. Em **Configurações**, abra **Bancos de dados (Databases)**, clique em **+ Adicionar**, digite
   `conectaja` e salve.

### 2.4 Montar a cadeia de conexão

Troque `<SENHA>` pela senha do administrador (e `conectaja-pg`, se usou sufixo):

```text
postgres://conectaja:<SENHA>@conectaja-pg.postgres.database.azure.com:5432/conectaja?sslmode=require
```

Se a senha tiver `@`, `:`, `/` ou `#`, codifique esses caracteres (`@` vira `%40`).

---

## Parte 3 — Armazenamento dos arquivos enviados

Documentos, selfies, fotos de vagas e logos não podem ficar dentro do contêiner: o disco dele é
apagado a cada versão nova. Eles ficam num compartilhamento do Azure Files montado em `/data`.

1. Busque **Contas de armazenamento (Storage accounts)** e clique em **+ Criar**.
   - **Grupo de recursos:** `rg-conectaja`. **Nome:** `conectajafiles` (só letras minúsculas e
     números; se existir, use um sufixo). **Região:** Brazil South.
   - **Desempenho:** Standard. **Redundância:** LRS (armazenamento com redundância local).
   - Clique em **Revisar + criar** e depois em **Criar**.
2. Abra a conta criada. Em **Armazenamento de dados (Data storage)**, abra
   **Compartilhamentos de arquivos (File shares)** e clique em **+ Compartilhamento de arquivos**.
   **Nome:** `private-media`. Camada: **Otimizado para transações (Transaction optimized)**. Crie.
3. Em **Segurança + rede**, abra **Chaves de acesso (Access keys)** e copie a **key1**. Ela é
   usada na etapa 4.2 e não vai para o repositório.

---

## Parte 4 — Ambiente do Container Apps

### 4.1 Criar o app e o ambiente

1. Busque **Aplicativos de Contêiner (Container Apps)** e clique em **+ Criar (Create)**.
2. Aba **Básico (Basics)**:
   - **Grupo de recursos:** `rg-conectaja`.
   - **Nome do aplicativo de contêiner:** `conectaja-web`.
   - **Origem da implantação:** Imagem de contêiner (Container image).
   - **Região:** Brazil South.
   - **Ambiente de Aplicativos de Contêiner:** **Criar novo (Create new)**:
     - **Nome do ambiente:** `conectaja-env`.
     - **Perfis de carga de trabalho:** mantenha só o **Consumption**. Perfis *Dedicated* cobram
       por hora mesmo sem uso.
     - Aba **Monitoramento**: em **Destino dos logs**, escolha **Don't save logs** (sem custo; o
       **Fluxo de log** continua mostrando os logs ao vivo) ou **Azure Monitor** se quiser
       histórico, cobrado por GB.
     - Clique em **Criar**.
3. Aba **Contêiner**: marque **Usar imagem de início rápido (Use quickstart image)**. A imagem
   real entra na etapa 5.4.
4. Aba **Entrada (Ingress)**: **Habilitada**, **Aceitando tráfego de qualquer lugar**, tipo
   **HTTP**, **Porta de destino** 80 por enquanto (a imagem de início rápido usa a 80).
5. Clique em **Revisar + criar** e depois em **Criar**.

### 4.2 Ligar o Azure Files ao ambiente

1. Abra o ambiente `conectaja-env`. Em **Configurações**, abra **Arquivos do Azure (Azure Files)**
   e clique em **+ Adicionar**.
2. Preencha:
   - **Nome:** `private-media`.
   - **Nome da conta de armazenamento:** `conectajafiles`.
   - **Chave da conta de armazenamento:** a key1 da etapa 3.3.
   - **Compartilhamento de arquivos:** `private-media`.
   - **Modo de acesso:** Leitura/gravação (Read/Write).
3. Salve.

---

## Parte 5 — Container App `conectaja-web`

### 5.1 Segredos

Abra o app `conectaja-web`. Em **Configurações**, abra **Segredos (Secrets)** e adicione um por vez
(**Tipo:** Segredo do Aplicativo de Contêiner):

| Chave | Valor |
| --- | --- |
| `database-url` | a cadeia de conexão da etapa 2.4 |
| `secret-key` | uma chave aleatória longa (gere com `python -c "import secrets; print(secrets.token_urlsafe(50))"`) |
| `admin-password` | a senha que o `admin@exemplo.com` vai usar no `/admin` |

### 5.2 Escala

Em **Aplicativo**, abra **Escala (Scale)**:

- **Mínimo de réplicas:** 0 (dorme sem acesso e não cobra). No dia da apresentação, coloque 1
  para não demorar a acordar e volte para 0 depois.
- **Máximo de réplicas:** 1 por enquanto. As migrações rodam na subida do contêiner, e duas
  réplicas subindo ao mesmo tempo poderiam tentar migrar juntas.

### 5.3 Endereço do app

Na **Visão geral (Overview)**, copie a **URL do Aplicativo**, algo como
`https://conectaja-web.<algo>.brazilsouth.azurecontainerapps.io`. Ela é usada na próxima etapa.

### 5.4 Apontar para a imagem, variáveis, volume e sondas

Faça esta etapa depois que a Parte 1 publicar a imagem.

1. Em **Aplicativo**, abra **Contêineres (Containers)** e clique em **Editar e implantar
   (Edit and deploy)**. Selecione o contêiner e clique em **Editar**.
2. **Imagem:**
   - **Origem da imagem:** Docker Hub ou outros registros.
   - **Tipo de imagem:** Público.
   - **Servidor de logon do registro:** `ghcr.io`.
   - **Imagem e marca:** `<dono>/conecta-ja:latest`.
3. **Recursos:** CPU 0,5 e memória 1 Gi.
4. **Variáveis de ambiente:**

   | Nome | Origem | Valor |
   | --- | --- | --- |
   | `DATABASE_URL` | Referenciar um segredo | `database-url` |
   | `SECRET_KEY` | Referenciar um segredo | `secret-key` |
   | `ADMIN_PASSWORD` | Referenciar um segredo | `admin-password` |
   | `DEBUG` | Manual | `false` |
   | `ALLOWED_HOSTS` | Manual | o host da URL da etapa 5.3, sem `https://` |
   | `CSRF_TRUSTED_ORIGINS` | Manual | a URL da etapa 5.3, com `https://` |
   | `SEED_DEMO` | Manual | `true` só na primeira subida (veja o aviso abaixo) |
   | `LOG_LEVEL` | Manual | `INFO` |

5. Aba **Sondas de integridade (Health probes)**:
   - **Atividade (Liveness):** HTTP, caminho `/api/health/live/`, porta 8000.
   - **Preparação (Readiness):** HTTP, caminho `/api/health/`, porta 8000 (este confere o banco).
   - **Inicialização (Startup):** HTTP, caminho `/api/health/live/`, porta 8000, atraso inicial
     de 10 s e limite de falhas 30 (as migrações rodam antes do gunicorn subir).
6. Aba **Montagens de volume (Volume mounts)**:
   - **Tipo de volume:** Arquivos do Azure. **Nome:** `private-media` (o da etapa 4.2).
   - **Caminho de montagem:** `/data/private_media`.
   - **Opções de montagem**, se o campo existir: `uid=10001,gid=10001` (o usuário da imagem).
7. Clique em **Salvar** e depois em **Criar**. Isso gera uma revisão nova.
8. Em **Configurações**, abra **Entrada (Ingress)**, mude a **Porta de destino** para `8000` e salve.

> **Aviso sobre `SEED_DEMO`:** os dados de demonstração criam contas de empresa e de prestador com
> a senha pública do README. Num ambiente aberto ao público, depois da primeira subida troque
> `SEED_DEMO` para `false`, ou não use o seed. Nunca rode `seed_demo --prazos-curtos` aqui: ele
> troca os parâmetros da plataforma no banco.

### 5.5 Testar

1. Abra `<URL>/api/health/`. A resposta deve ser `{"status": "ok"}`.
2. Abra `<URL>/`. A página inicial aparece com as vagas de demonstração.
3. Entre em `<URL>/admin/` com `admin@exemplo.com` e a senha do segredo `admin-password`.
4. Entre como empresa e envie uma foto de vaga. Depois crie uma revisão nova (etapa 6.1) e
   confira se a foto continua lá: isso confirma que o volume do Azure Files está montado.

Se algo não subir, abra **Monitoramento → Fluxo de log (Log stream)**. Cada linha de log traz o
identificador da requisição entre colchetes, o mesmo do cabeçalho `X-Request-ID` da resposta.

---

## Parte 6 — Processamento de prazos (Container Apps Job)

Os prazos (encerrar candidaturas, falta, check-out e aprovação automáticos, fila de espera) rodam
num Job agendado, separado do site. Assim o site pode dormir ou ter várias réplicas sem os prazos
rodarem em dobro.

1. Busque **Trabalhos do Aplicativo de Contêiner (Container App Jobs)** e clique em **+ Criar**.
2. Aba **Básico**:
   - **Grupo de recursos:** `rg-conectaja`. **Nome:** `conectaja-prazos`.
   - **Ambiente:** `conectaja-env` (o existente).
   - **Tipo de gatilho (Trigger type):** Agendado (Schedule).
   - **Expressão cron:** `*/5 * * * *` (a cada 5 minutos). No dia da apresentação, use
     `* * * * *` para os prazos reagirem em até 1 minuto.
   - **Tempo limite da réplica:** 300 s. **Novas tentativas:** 0. **Paralelismo:** 1.
3. Aba **Contêiner**:
   - Mesma imagem da etapa 5.4 (`ghcr.io`, `<dono>/conecta-ja:latest`).
   - **Argumentos (Arguments):** `prazos`.
   - **Recursos:** CPU 0,25 e memória 0,5 Gi.
   - **Variáveis de ambiente:** crie os segredos `database-url` e `secret-key` no Job (como na
     etapa 5.1) e as variáveis `DATABASE_URL`, `SECRET_KEY` e `DEBUG=false`.
4. Clique em **Revisar + criar** e depois em **Criar**.
5. Para testar na hora: abra o Job e clique em **Executar agora (Run now)**. Em
   **Histórico de execução (Execution history)**, a execução deve terminar como **Bem-sucedida**.

---

## Parte 7 — Dia a dia

### 7.1 Publicar uma versão nova

1. Faça o merge do PR na `main` e espere o workflow `CI` terminar (ele publica a imagem).
2. No `conectaja-web`, abra **Contêineres → Editar e implantar** e clique em **Criar**. A revisão
   nova baixa a `latest` atual e roda as migrações na subida.
3. O Job usa a `latest` na próxima execução, sem ação manual.

### 7.2 Voltar para a versão anterior

Cada imagem tem a tag do commit. Em **Editar e implantar**, troque `latest` pela tag do commit
anterior (veja em **Packages** no GitHub) e crie a revisão. Atenção: uma versão antiga não desfaz
migrações já aplicadas no banco.

### 7.3 Backup

O PostgreSQL flexível faz backup automático diário com 7 dias de retenção (em **Backup e
restauração** no servidor). Os arquivos do Azure Files podem ganhar instantâneos em
**Compartilhamentos de arquivos → private-media → Instantâneos (Snapshots)**.

## Problemas comuns

| Sintoma | Causa provável |
| --- | --- |
| Revisão não fica pronta; log mostra erro de conexão | `DATABASE_URL` errada, sem `?sslmode=require`, ou a Rede do banco sem o acesso dos serviços do Azure (etapa 2.2) |
| `Bad Request (400)` ao abrir o site | `ALLOWED_HOSTS` diferente do host da URL |
| `CSRF verification failed` no login | `CSRF_TRUSTED_ORIGINS` sem `https://` ou com outra URL |
| Erro ao enviar foto ou documento (`Permission denied`) | Volume sem as opções `uid=10001,gid=10001` ou montado em outro caminho |
| Fotos somem depois de uma versão nova | Volume não montado em `/data/private_media` |
| Prazos não andam | Job sem as variáveis do banco; veja o **Histórico de execução** |

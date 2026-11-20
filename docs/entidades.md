# Modelo de entidades — Conecta Já

> Fonte oficial do modelo de dados. Nomes de classe em inglês (código) e termos de negócio em português (interface).
> Valores monetários sempre em **centavos (inteiro)**. Datas em UTC no banco, exibidas em `America/Sao_Paulo`.
> Itens marcados **[pós-MVP]** podem existir como campo/modelo vazio, mas não precisam de tela nem regra agora.

## Visão geral

```
User ─┬─ 1:1 ─ Worker (Prestador) ── 1:N ─ WorkerDocument
      │                         └── 1:N ─ Application ── 0..1 ─ Assignment
      └─ N:1 ─ CompanyMember ── N:1 ─ Company (Contratante)
                                         └── 1:N ─ Vacancy (Vaga/turno) ── 1:1 ─ Custody ── 1:N ─ LedgerEntry
                                                        ├── 1:N ─ Application
                                                        └── 1:N ─ Assignment (Alocação)
StateTransition (auditoria de qualquer entidade com estado) · PlatformParameters (singleton) · Notification · VerificationReview
```

## Identidade e acesso

### User (`accounts.User`, já existe)
Login por **e-mail + senha** (e-mail único, case-insensitive). Campo `role`: `COMPANY`, `WORKER` ou `ADMIN`. Admin = `is_staff`.

### Company — Contratante
| Campo | Observação |
|---|---|
| `cnpj` | único, só dígitos, dígitos verificadores validados |
| `legal_name` (razão social), `trade_name` (nome fantasia) | preenchidos pela BrasilAPI, editáveis |
| `state_registration` (inscrição estadual) | texto; aceita "ISENTO" |
| `tax_regime` | `SIMPLES` ou `NORMAL` |
| `registration_status` | situação cadastral retornada pela BrasilAPI (ex.: ATIVA) |
| endereço (`street`, `number`, `complement`, `district`, `city`, `state`, `zip_code`), `phone` | dados cadastrais gerais |
| `preferred_payment_method` | `PIX`, `BOLETO` ou `CARTAO` — **só a preferência**; nunca armazenar dados de cartão ou conta (no futuro o PSP tokeniza) |
| `verification_status` | `PENDENTE`, `APROVADA`, `REJEITADA` (ver `VerificationReview`) |
| `description` | descrição da empresa exibida ao prestador [pós-MVP: US15] |
| `suspended_until` | fim da suspensão manual do admin (US76); vazio = sem suspensão com data |
| `suspension_indefinite` | `true` = suspensa por tempo indeterminado (sem data de fim); só a reativação encerra |

### CompanyMember
Vínculo `User` ↔ `Company` com `role`: `OWNER` (MVP) ou `MANAGER` [pós-MVP: US03]. Nunca compartilhar login.

### Worker — Prestador
| Campo | Observação |
|---|---|
| `full_name`, `cpf` (único, dígitos verificadores validados), `phone`, `birth_date` | idade mínima 18 anos |
| `verification_status` | `PENDENTE_DOCUMENTOS`, `EM_ANALISE`, `APROVADO`, `REJEITADO` |
| `pix_key_type` (`CPF`, `EMAIL`, `TELEFONE`, `ALEATORIA`), `pix_key` | sempre mascarada em respostas e logs |
| `home_latitude`, `home_longitude` | opcional; para ordenar vagas por proximidade |
| `alerts_enabled`, `alert_radius_km`, `alert_only_my_schedule` | alertas de vaga próxima (US19): ligados, raio (5, 10, 20 ou 50 km) e só nos horários da disponibilidade; usam a localização de casa |
| `suspended_until` | preenchido por suspensão automática ou manual |
| `suspension_indefinite` | `true` = suspensão manual por tempo indeterminado (US76); `suspended_until` fica vazio e só a reativação encerra |
| `level` | `NOVO` (MVP); níveis [pós-MVP: US65] |
| `skills` | lista de até 7 categorias de vaga em que o prestador tem experiência (US08), sem repetição |
| `bio` | resumo da experiência, até 500 caracteres, sem e-mail nem telefone (US08) |
| `availability_days`, `availability_periods` | dias (`SEG` a `DOM`) e faixas (`MANHA` 6h–12h, `TARDE` 12h–18h, `NOITE` 18h–6h) em que o prestador costuma trabalhar (US10); só informativo |

### WorkerDocument
`worker`, `kind` (`DOC_FRENTE`, `DOC_VERSO`, `SELFIE`), `file` (**armazenamento privado**, nunca URL pública; acesso só pelo dono e pelo admin), `uploaded_at`.

### PortfolioPhoto — foto de trabalho anterior (US09)
`worker`, `file` (**armazenamento privado**, servido só pela API ao próprio prestador, ao admin e às empresas em que ele tem candidatura ou alocação), `caption` (até 120 caracteres), `created_at`. Até 8 por prestador; JPG, PNG ou WebP de até 5 MB.

### VerificationReview
Decisão do admin na fila de verificação (US73): `subject_type` (`COMPANY`/`WORKER`), `subject_id`, `reviewer`, `decision` (`APROVADO`/`REJEITADO`), `reason` (obrigatório na rejeição), `created_at`.

## Vagas e execução

### Vacancy — Vaga (um turno com N posições)
| Campo | Observação |
|---|---|
| `company`, `title`, `category`, `description` (escopo do serviço) | categoria de uma lista fixa (ex.: Ajudante de obra, Carga e descarga, Varejo, Eventos, Fotografia, Limpeza, Outros) |
| endereço + `latitude`, `longitude` | ponto escolhido no mapa (OpenStreetMap/Leaflet) ou "usar minha localização" |
| `starts_at`, `ends_at` | horas do turno definidas no anúncio |
| `pay_per_person_cents` | valor bruto por pessoa (o que a empresa paga) |
| `positions` | número de pessoas (≥ 1) |
| `equipment`, `equipment_notes` | itens da lista fixa de EPIs, uniforme e ferramentas com quem providencia (`PRESTADOR` ou `EMPRESA`) e observações de até 300 caracteres (US22) |
| `requires_meeting` | [pós-MVP: US23] |
| `status` | ver `docs/maquina-de-estados.md` |

Calculados: `filled_positions` (alocações ativas), `worker_net_cents` = valor − taxa do prestador (ex.: R$ 100 → R$ 97).

### Application — Candidatura
`vacancy`, `worker`, `status`, `created_at`, `decided_at`, `decided_by`. Único por (`vacancy`, `worker`).

### Assignment — Alocação (o turno de um prestador)
Criada quando a candidatura é aprovada. Campos: `vacancy`, `worker`, `application`, `status`,
`check_in_at`, `check_in_lat`, `check_in_lng`, `check_in_distance_m`, `check_out_at`, `check_out_auto` (bool),
`check_in_confirmed_by_company` (bool, check-in confirmado pela empresa ou pelo admin a partir de uma justificativa, US51), `extended_until` (novo fim do turno deste prestador depois de aceitar a hora extra, US53; vazio = fim da vaga), `validated_at`, `validated_by` (usuário ou `SISTEMA`), `contest_response` (texto de 10 a 1.000 caracteres, resposta única do prestador à contestação, US58) e `contest_response_at` (data e hora do envio; vazio = ainda não respondeu). A resposta não é um estado novo nem uma transição.

### ArrivalJustification — justificativa de chegada (US51)
Uma por alocação (`assignment`, 1:1). Campos: `reason` (`GPS`, `BATERIA`, `ENDERECO`, `OUTRO`), `text` (até
300 caracteres, obrigatório em `OUTRO`), `status` (`PENDENTE`, `COM_ADMIN`, `CONFIRMADA`, `RECUSADA`),
`created_at` (vira o horário do check-in se confirmada), `decided_at`, `decided_by` e `decision_reason`.
Enquanto `PENDENTE` ou `COM_ADMIN`, a falta automática não se aplica à alocação.

### OvertimeRequest — pedido de hora extra (US52/US53)
Campos: `assignment`, `minutes` (30 a 240, de 30 em 30), `amount_cents` (valor bruto da extensão, ≥ mínimo
proporcional ao valor por hora do turno), `status` (`AGUARDANDO_PRESTADOR`, `ACEITO`, `RECUSADO`, `EXPIRADO`),
`requested_by`, `created_at`, `expires_at` e `responded_at`. Restrições: um pendente e no máximo um aceito por
alocação. As transições ficam em `StateTransition` (`entity_type = "OvertimeRequest"`).

## Dinheiro (simulado no MVP, mesmo desenho do PSP real)

### Custody — Custódia da vaga
`vacancy` (1:1), `amount_cents` (= valor por pessoa × posições), `status`, `psp_reference` (id do PSP fake), `idempotency_key` (único).
A plataforma **não** guarda dinheiro: a custódia representa o valor retido no PSP.

### LedgerEntry — Livro-razão (imutável, só inserção)
`custody`, `assignment` (opcional), `kind`, `amount_cents` (> 0), `idempotency_key` (único), `created_at`.
`kind`: `RETENCAO` (empresa pagou), `REPASSE_PRESTADOR` (97%), `TAXA_PLATAFORMA` (3%), `ESTORNO_CONTRATANTE` (posições não usadas ou cancelamento).
A hora extra aceita (US53) tem lançamentos próprios: `RETENCAO` ligada à alocação (chave `overtime:<id>:retencao`) e, na liquidação, `REPASSE_PRESTADOR`/`TAXA_PLATAFORMA` separados dos do turno (chaves `...:repasse-extensao` e `...:taxa-extensao`).
Invariante: `RETENCAO = REPASSE + TAXA + ESTORNO` quando a custódia é encerrada.

### Carteira do prestador (não é tabela — é visão calculada)
- **A receber:** alocações confirmadas/em validação × valor líquido, com data prevista de liberação.
- **Liberado:** soma dos `REPASSE_PRESTADOR` do prestador, com data de cada lançamento.

## Transversais

### StateTransition — trilha de auditoria
`entity_type`, `entity_id`, `from_state`, `to_state`, `actor` (usuário ou nulo = `SISTEMA`), `reason`, `created_at`. Gravada **na mesma transação** de toda mudança de estado.

### PlatformParameters — parâmetros editáveis (singleton)
Todos os prazos, limites e taxas de `docs/regras-de-negocio.md`. Editável pelo admin (US79). O código **sempre** lê daqui.

### Notification — notificações dentro do app
`user`, `kind`, `title`, `message`, `link`, `dedup_key` (opcional e único: aviso que só pode sair uma vez, como o lembrete de um turno, US49), `read_at`, `created_at`. Sem e-mail ou push no MVP.

### VacancyInvite — convite para vaga (US44)
`vacancy`, `worker`, `invited_by`, `created_at`. Único por (`vacancy`, `worker`); até 20 por vaga. Só para prestador com turno pago na empresa. Não cria candidatura.

### FavoriteVacancy — vaga favorita (US18)
`worker`, `vacancy`, `created_at`. Única por (`worker`, `vacancy`): favoritar de novo não duplica. Só vagas que já apareceram na busca (`PUBLICADA`, `CANDIDATURAS_ENCERRADAS`, `EM_ANDAMENTO`) podem ser favoritadas; depois de encerrada, cancelada ou lotada, a vaga continua na lista com o selo "Encerrada" ou "Lotada". Cada prestador só vê as próprias favoritas.

### Review — avaliação bilateral [pós-MVP: US63/US64]
`assignment`, `direction` (`EMPRESA_PARA_PRESTADOR` (US63) e `PRESTADOR_PARA_EMPRESA` (US64)), `author` (usuário), `rating` (1 a 5), `comment` (opcional, até 500 caracteres), `created_at`. Única por (`assignment`, `direction`). Definitiva: não há edição nem exclusão. Não obrigatória; conta para o status [pós-MVP].

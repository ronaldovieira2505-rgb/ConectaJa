# Regras de negócio — Conecta Já

> Fonte oficial das regras e dos valores padrão. Tudo que tiver **chave** é parâmetro de `PlatformParameters`, editável pelo admin (US79) e **nunca fixo no código**.
> Para a demonstração, o admin pode reduzir os prazos para minutos (ex.: janela de contestação de 2 min), sem mudar código.

## 1. Modelo de receita

Conforme o relatório N1, a **única receita** é uma taxa percentual sobre o valor bruto de cada turno, **descontada no repasse ao prestador**. Não há mensalidade, plano nem cobrança de entrada.

**Empresa (contratante):** paga exatamente o valor anunciado do turno, **sem acréscimo**.

**Prestador:** a plataforma retém **3%** do valor recebido (`worker_fee_percent` = 3).
Exemplo: vaga de R$ 100,00 → empresa paga R$ 100,00 → prestador recebe R$ 97,00 → plataforma fica com R$ 3,00.
Arredondamento: taxa = 3% do valor em centavos, arredondada para o centavo mais próximo (meio para cima); prestador = valor − taxa.

## 2. Parâmetros (valores padrão)

| Chave | Padrão | Regra |
|---|---|---|
| `min_publish_lead_minutes` | 720 (12 h) | Antecedência mínima entre a publicação e o início do turno |
| `payment_deadline_minutes` | 1440 (24 h) | Prazo para pagar uma vaga criada; depois ela é cancelada |
| `applications_close_minutes_before` | 120 (2 h) | Candidaturas encerram X min antes do início |
| `shift_reminder_minutes_before` | 1440 (24 h) | O prestador com alocação confirmada recebe um lembrete (uma única vez) a partir de X min antes do início (US49) |
| `checkin_open_minutes_before` | 30 | Check-in liberado a partir de X min antes do início |
| `no_show_tolerance_minutes` | 30 | Sem check-in até X min após o início = falta |
| `geofence_radius_m` | 150 | Distância máxima para aceitar o check-in |
| `auto_checkout_minutes_after_end` | 120 (2 h) | Sem check-out até X min após o fim = check-out automático no horário previsto |
| `contest_window_minutes` | 1440 (24 h) | Janela para a empresa aprovar ou contestar; silêncio = aprovação |
| `no_show_limit` / `no_show_window_days` | 2 / 30 | Faltas que geram suspensão automática, e a janela considerada |
| `suspension_days` | 15 | Duração da suspensão automática |
| `free_cancel_minutes_before` | 1440 (24 h) | Prazo mínimo (X min antes do início) para a empresa cancelar pelo app (US71); também é o limite sem penalidade do prestador [pós-MVP: US72] |
| `late_cancel_block_days` | 7 | Bloqueio por cancelamento tardio [pós-MVP] |
| `review_window_days` | 7 | Prazo, em dias após a aprovação das horas, para a empresa avaliar o prestador (US63) e o prestador avaliar a empresa (US64); deve ser maior que zero |
| `worker_fee_percent` | 3 | Taxa retida do prestador |

**Unidades e validação (US79):** todo prazo que era em horas passou a ser em **minutos** (os prazos em dias continuam em dias), o que permite demonstrar janelas curtas (ex.: contestação de 2 min). O admin edita os valores em "Parâmetros da plataforma"; a alteração vale de imediato e fica auditada (quem, quando, valor anterior e novo). Valores negativos são rejeitados. Exigem valor maior que zero: `payment_deadline_minutes`, `shift_reminder_minutes_before`, `geofence_radius_m`, `contest_window_minutes`, `no_show_limit`, `no_show_window_days` e `suspension_days`, `review_window_days`. Os demais prazos aceitam 0. `worker_fee_percent` é inteiro entre 0 e 100.

**Suspensão manual de conta (US76):** só o admin suspende ou reativa, sempre com motivo. A suspensão tem de 1 a 365 dias ou é por tempo indeterminado. Empresa suspensa não cria nem paga vagas novas (vê "Conta suspensa até ..."), mas as vagas já publicadas continuam valendo. Prestador suspenso não se candidata nem é aprovado, e mantém as alocações já confirmadas. Banimento definitivo e recurso do usuário ficam fora do escopo.

## 3. Cadastro e triagem

- **Login:** e-mail + senha para empresa e prestador. O admin usa o painel administrativo.
- **Empresa:** cadastro em 3 etapas: (1) CNPJ, validado e consultado na **BrasilAPI**, que preenche razão social, nome fantasia, endereço e situação; (2) razão social e regime tributário (Simples ou Normal); (3) nome, e-mail e senha. Inscrição estadual (aceita "ISENTO"), telefone e meio de pagamento preferido são opcionais e ficam fora do cadastro inicial. Uma conta por CNPJ. Se a BrasilAPI estiver fora do ar, o cadastro continua com preenchimento manual e a empresa fica marcada para conferência do admin.
- **Prestador:** nome completo, CPF (dígitos verificadores validados; um CPF por conta), telefone, data de nascimento (mínimo 18 anos), documento com foto (frente e verso) e selfie, e chave PIX.
- **Habilidades e experiência (US08, opcional):** até 7 categorias das vagas e um resumo de até 500 caracteres. O resumo não aceita e-mail nem telefone (validação simples), porque o contato só é liberado depois da alocação (§5). A empresa vê as categorias e o resumo na lista de candidatos, com destaque para a categoria da vaga. É uma etapa opcional de "Complete seu perfil" e não bloqueia a candidatura.
- **Verificação de identidade (triagem):** **manual**, feita pela equipe administrativa na fila de verificação (US73). O admin compara a selfie com a foto do documento e confere os dados. Empresas são conferidas pelos dados da BrasilAPI. Biometria automática por serviço pago (ex.: idwall, unico) fica para o pós-MVP.
- **Trabalhos anteriores (US09, opcional):** o prestador adiciona até 8 fotos (JPG, PNG ou WebP, até 5 MB) com legenda opcional de até 120 caracteres e remove quando quiser (o arquivo é apagado). As fotos ficam em armazenamento privado, sem URL pública, e só são servidas ao próprio prestador, às empresas em que ele tem candidatura ou alocação e ao admin.
- **Exclusão da conta do prestador (US11):** o prestador confirma com a senha atual. A conta é desativada, a sessão termina e não é mais possível entrar. Nome vira "Prestador removido"; CPF, telefone, data de nascimento, chave PIX, e-mail, habilidades e resumo (US08) são apagados ou trocados por valores sem identificação, e documentos, selfie e fotos de trabalhos anteriores (US09) são apagados do armazenamento. Alocações pagas, livro-razão, transições e avaliações são mantidos sem identificação direta e continuam contando nas médias, com o autor "Prestador removido". Candidaturas pendentes viram `DESISTENCIA`. Com alocação `CONFIRMADA`, `EM_EXECUCAO`, `AGUARDANDO_VALIDACAO`, `CONTESTADA` ou `APROVADA`, a exclusão é recusada ("Você tem turnos em andamento. Conclua ou cancele antes de excluir a conta."). A exclusão fica em `StateTransition` (`WorkerAccount`, `ATIVA → EXCLUIDA`, motivo "Solicitação do titular"), sem guardar os dados apagados. Exclusão de conta de empresa fica fora.
- **Dados de pagamento:** a empresa informa só a preferência (PIX, boleto ou cartão). **Nunca** armazenar número de cartão ou dados bancários: no produto real, o PSP faz isso.
- **Troca de chave PIX:** no MVP, a confirmação por código é **simulada** (o código aparece na tela em modo demonstração) [US07, pós-MVP].

## 4. Vagas (catálogo da empresa)

- Campos obrigatórios: título, categoria, descrição do escopo, endereço com ponto no mapa, início, fim, valor por pessoa (≥ R$ 1,00) e número de pessoas (≥ 1).
- **EPIs, uniforme e ferramentas (US22, opcional):** a empresa marca itens de uma lista fixa (capacete, luvas, botina, óculos de proteção, protetor auricular, colete refletivo, uniforme, calça preta, camisa branca, sapato social, ferramentas próprias) e, para cada um, se o prestador leva ou a empresa fornece, com observações de até 300 caracteres. O prestador vê, no detalhe da vaga, "Você precisa levar" e "Fornecido pela empresa"; sem itens nem observações, o bloco não aparece. Itens fora da lista são recusados. Os itens seguem as regras de edição da vaga e a alteração fica em `VacancyChange`. Controle de entrega de EPI e termo assinado ficam fora.
- As horas do turno são as do anúncio; o pagamento é o **valor fixo do turno**, não por hora trabalhada.
- A vaga só é publicada **depois** do pagamento (custódia).
- **Editar ou remover** só enquanto nenhuma candidatura tiver sido aprovada. A remoção gera estorno total e expira as candidaturas pendentes, avisando os candidatos. Só vagas `PUBLICADA` podem ser editadas ou removidas (não em `CANDIDATURAS_ENCERRADAS`).
- **Campos editáveis:** título, descrição, categoria, endereço/ponto e início/fim (a antecedência mínima `min_publish_lead_minutes` vale também na edição). Cada alteração é auditada (`VacancyChange`: usuário, data, campo, valor anterior e novo).
- **Duplicar vaga (US25):** a empresa duplica qualquer vaga sua, em qualquer estado. O formulário "Nova vaga" abre preenchido (título, categoria, descrição, endereço e ponto, valor por pessoa e número de pessoas), com data e horário vazios e obrigatórios; nada é criado até a confirmação. A vaga nova nasce `AGUARDANDO_PAGAMENTO`, com custódia própria, sem candidatos, avaliações nem histórico da original, e recebe uma cópia própria da foto. A antecedência mínima vale normalmente.
- **Valor por pessoa e número de pessoas não são editáveis após o pagamento** (decisão do PO). Para alterar, a empresa remove o anúncio (estorno total) e publica um novo. Não há pagamento complementar nem estorno parcial; a custódia não muda.

- **Cancelamento pela empresa (US71):** com prestador aprovado, a empresa cancela **um prestador** (`CONFIRMADA → CANCELADA_EMPRESA`) ou a **vaga inteira** (`PUBLICADA`/`CANDIDATURAS_ENCERRADAS → CANCELADA`) pelo app **somente até `free_cancel_minutes_before` (padrão 1440 min = 24 h) antes do início**. Dentro desse prazo a empresa não cancela pelo app e vê "Cancelamentos só podem ser feitos até 24 h antes do início. Fale com o suporte." (decisão do PO, para proteger o prestador que já reservou o dia). O **motivo é obrigatório** e fica registrado na transição. O valor da posição é estornado à empresa (`ESTORNO_CONTRATANTE`), sem multa; o prestador é notificado. No cancelamento da vaga inteira, todas as alocações viram `CANCELADA_EMPRESA`, as candidaturas pendentes expiram, a custódia é encerrada com estorno total e candidatos e prestadores são avisados. A posição liberada por cancelamento da empresa **não volta para a busca** nem aceita novas aprovações. Vaga sem aprovados continua usando "Remover anúncio" (US24). Cancelamento pelo admin está fora do escopo.

## 5. Candidatura e seleção

- Candidatura voluntária com aprovação da empresa. Não há despacho automático.
- O prestador vê, antes de se candidatar, o **valor líquido** (com os 3% descontados) e o selo "Pagamento garantido" (custódia retida).
- Não é permitido ter duas alocações com horários sobrepostos.
- **Convidar de novo (US44):** na vaga publicada, a empresa vê quem já concluiu turno pago com ela (foto, nome no padrão "Ana R.", turnos com a empresa e a nota que ela deu), da maior para a menor nota, e pode convidar. O convite notifica o prestador com link para a vaga, mas **não** pula a candidatura: ele se candidata e a empresa aprova como sempre (decisão do PO). Cada prestador recebe um convite por vaga; no máximo 20 convites por vaga (decisão do PO). Prestador suspenso, já candidato ou com conflito de horário aparece sem o botão e com o motivo; vaga lotada, encerrada ou cancelada não recebe convites.

## 6. Execução, validação e pagamento

- **Check-in:** geolocalização do navegador, até 150 m do ponto da vaga. Fora do raio, a mensagem mostra a distância.
- **Check-out:** botão do prestador, com check-out automático como rede de segurança.
- **Validação:** a empresa confere entrada e saída e aprova. Se não se manifestar em 24 h, a aprovação é automática.
- **Contestação [extra]:** a empresa contesta com motivo; a equipe administrativa contata as partes e decide.
- **Resposta do prestador à contestação (US58, decisões do PO):** com a alocação `CONTESTADA`, o prestador vê o motivo da empresa e envia a sua versão em texto de 10 a 1.000 caracteres (`POST /api/assignments/<id>/contest-response/`, campo "Sua versão" em "Meus trabalhos"). A resposta é **única e definitiva** (sem nova resposta nem edição), **só texto, sem anexos**, e é gravada com data e hora. O admin e os membros da empresa são notificados no app. A resposta **não muda o estado**: a alocação segue `CONTESTADA` até o admin decidir (US57), com ou sem resposta, e **não há prazo** para responder. Depois da decisão (`APROVADA` ou `ESTORNADA`) a API recusa nova resposta, mas a enviada antes continua visível. O admin vê a resposta ao lado do motivo da empresa (lista e tela de decisão), a empresa dona da vaga a vê no detalhe da contestação e a linha do tempo do turno (US75) registra "Prestador respondeu à contestação". Só o prestador da própria alocação responde (outro usuário recebe 404/403).
- **Liberação:** prestador recebe 97% e a plataforma retém 3% (lançamentos no livro-razão).

**Avaliação do prestador (US63, decisões do PO):** com a alocação `APROVADA` ou `PAGA`, a empresa dona da vaga envia nota de 1 a 5 e comentário opcional de até 500 caracteres (`POST /api/assignments/<id>/review/`). A avaliação fica ligada à alocação, é **definitiva** (sem nova avaliação nem edição) e o prestador é notificado, vendo a nota assim que ela é enviada. O prazo é `review_window_days` (padrão 7 dias) contados da aprovação das horas (`validated_at`); depois disso a API recusa. Alocações em `FALTA`, `CANCELADA_*` ou `ESTORNADA` não são avaliáveis. Avaliar é opcional e nunca bloqueia pagamento nem o fluxo. Média e exibição para outras empresas (US40), níveis e selos (US65/US66) e moderação de comentários ficam fora.

**Avaliação da empresa (US64):** com a alocação `APROVADA` ou `PAGA`, o prestador envia nota de 1 a 5 e comentário opcional de até 500 caracteres (`POST /api/assignments/<id>/review-company/`, botão "Avaliar empresa" em "Meus trabalhos"). Valem as **mesmas regras da US63**: uma avaliação por alocação e por sentido (a da empresa e a do prestador são independentes), sem edição, prazo `review_window_days` (padrão 7 dias) contados da aprovação das horas, não vale para falta, cancelamento ou estorno, e é opcional (nunca bloqueia pagamento). A empresa é notificada (todos os membros). A **nota média da empresa** (média de todas as avaliações recebidas dos prestadores, com 1 casa decimal, e a quantidade) aparece no card da busca e no detalhe da vaga, por exemplo "★ 4,6 · 12 avaliações"; sem avaliações, "Sem avaliações ainda". A empresa vê as avaliações recebidas em "Avaliações" (`GET /api/company/reviews/`), com o prestador no padrão **"Ana S."** (primeiro nome e inicial do último sobrenome): o CPF e o sobrenome completo nunca são expostos. Selo de contratante premium (US66) e filtro premium (US67) ficam fora.

## 7. Hora extra: decisão

**MVP:** não há hora extra. O turno tem as horas do anúncio, e o check-out registra a saída real só para conferência.

**Pós-MVP (US52/US53), recomendado:** a empresa solicita a extensão **antes** de o turno terminar, informando as horas e o valor. O prestador aceita ou recusa no app, sem penalidade se recusar. A empresa **paga a extensão em custódia** antes de ela começar. Assim a garantia de pagamento continua valendo. Descartamos a cobrança automática por tempo excedido: ela cobraria a empresa sem consentimento e o valor não estaria garantido ao prestador.

## 8. Notificações

Somente dentro do app (sino com contador): aprovação ou recusa de candidatura, falta (para a empresa), vaga reaberta, aprovação de horas, pagamento liberado e resultado da verificação.

**Lembrete do turno (US49):** o `processar_prazos` avisa o prestador de cada alocação `CONFIRMADA` cujo início está a até `shift_reminder_minutes_before`, com vaga, empresa, data e horário, endereço completo, link "Ver no mapa" e o horário em que o check-in abre. O título diz "amanhã" (ou "hoje", se a aprovação veio em cima da hora). Cada alocação recebe no máximo um lembrete, garantido pela chave de idempotência da notificação; alocação cancelada, em falta ou já iniciada não recebe.

## 9. Fora do produto (decisões do PO)

- **Cupom de desconto (US28):** removido por decisão do PO.
- **Impulsionamento (US33–US36):** créditos comprados, como nos marketplaces tradicionais. A duração e o posicionamento ficam a cargo de um algoritmo interno [pós-MVP].
- **Níveis e selo (US65/US66):** métricas a definir. Avaliações não são obrigatórias, mas contam para o status [pós-MVP].
- **Lista de espera (US43):** chamada automática do próximo candidato [pós-MVP]. Com a equipe completa, as candidaturas `PENDENTE` continuam válidas e formam a lista de espera, numerada por ordem de candidatura (empresa: "Lista de espera"; prestador: "Na lista de espera (posição N)"). Ao liberar uma posição por falta ou cancelamento do prestador, o primeiro elegível é aprovado pelo SISTEMA, sem prazo de aceite (como na aprovação manual); a empresa pode desligar a chamada por vaga (`auto_call_waitlist`, ligada por padrão).

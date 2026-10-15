# Regras de negócio — V2: decisões, premissas e pendências

Cada item do e-mail de feedback foi investigado **antes** de ser implementado. Esta página registra *onde a regra
mora*, *como funcionava*, *o que foi feito* e *o que ficou como decisão do negócio*. Onde o enunciado era ambíguo,
a escolha está explícita (e é uma constante de uma linha, quando possível).

## 5.1 Colaboradores desligados (HMB)

| Colaborador | Desligamento | Cargo (escala de set/2026) |
|---|---|---|
| Ronaldo Manoel dos Santos | 08/09/2026 | Aux. Manutenção Elétrica |
| Caio Cezar Santos Pereira | 18/09/2026 | Eletricista |
| Lesle Venini Izidoro dos Santos | 26/09/2026 | Técnico de Climatização (noturno) |

- **Onde mora a regra:** `core/regras/elegibilidade.py` (única implementação). É chamada pelo motor
  (`core/motor_base.indicar_responsavel` — *gate duro*), por `esta_disponivel()` das duas unidades e pelos relatórios.
  Antes só a camada de rota filtrava `status == "Ativo"`.
- **Convenção de data:** o **próprio dia do desligamento já é indisponível** (“a partir de 16/09 — a data do
  desligamento — não pode ser recomendado”, convenção que a supervisão já tinha dado para a HETRIN). Se o último dia
  trabalhado deve ser o do desligamento, basta registrar a data seguinte.
- **Dados:** `data_desligamento` por dia (não `status` do mês inteiro, que apagaria os dias já trabalhados). Os três
  estão na semente `data/hmb/colaboradores_overlay.json` → copiada **uma vez** para o banco (`colaborador_overlay`).
- **Histórico preservado:** quem saiu e não consta na escala do mês seguinte vira uma linha *“Desligado — fora da
  escala vigente”* na lista de colaboradores (nada é apagado). Isso também permite identificar OS ainda em nome deles.
- **OS atribuídas a desligados:** tela **Revisão** (somente leitura, `GET /revisao`) lista toda OS aberta/em
  andamento cujo responsável é desligado, gestão, genérico, bloqueado ou vazio. **Nada é reatribuído automaticamente.**
- **Bug paralelo corrigido:** alterar um colaborador não invalidava o cache de preventivas (5 min) — a recomendação
  antiga continuava saindo. Agora toda alteração invalida o cache e a chave de cache inclui a versão do overlay (vale
  entre os workers do gunicorn).

## 5.2 OS “em nome do gestor” — causa-raiz

Evidência com a API real do Neovero (somente leitura):

1. O Neovero **cria cada OS com o responsável padrão do plano** (`planoManutencao.responsavelId`). Na HMB, 57 de 120
   planos ativos têm o gestor (*William de Souza Lobo*, Supervisor de Manutenção) como padrão: **227 de 847** preventivas
   de 01–13/10/2026 nasceram em nome dele. Na HETRIN a gerente/engenheira (*Jaqueliny Araujo da Silva*) aparece do mesmo modo.
   Os planos de ronda usam usuários **genéricos** (“ELÉTRICA - DIURNO”, “CLIMATIZAÇÃO - NOTURNO”).
2. Dentro do app, havia um segundo defeito: o cargo “Supervisor de Manutenção” casava com a palavra `supervisor` da
   lista de cargos técnicos e a categoria “Geral” aceitava **qualquer** cargo. Simulação com a escala real: o supervisor
   recebia 45 de 45 recomendações de categoria *Inspeção* (e aparecia como “Bate com atual”, validando o erro).

**Correção:** `cargo_executa_os()` — gerente, engenheiro, **supervisor**, coordenador, gestor, diretor, administrativo,
analista **nunca** são executantes (nem como último recurso: sem executante apto o resultado é *“sem candidato”*
sinalizado para revisão). O app nunca usa o usuário autenticado como executante (o motor não recebe identidade de
sessão). O teste antigo que *exigia* recomendar a gestora quando era a única opção foi invertido de propósito.

## 5.3 Limites diários

- **Elétrica 14 / Climatização 10** por colaborador por dia (`core/regras/limites.py`), aplicados **dentro do motor**
  (não só na tela). **O limite é um AVISO, não um bloqueio** (ver “Esgotado”).
- **Especialidade** = do **colaborador** (pelo cargo): eletricista/aux. elétrica → Elétrica; técnico/aux. de
  climatização/refrigeração → Climatização; demais cargos não têm teto.
- **O que conta:** OS Aberta, Em andamento e Fechada do dia (não Cancelada) + ocorrências projetadas já atribuídas.
  Cada item tem chave única (`OS:<n>` / `PREV:<plano>:<item>:<dia>`), então **nunca conta duas vezes**. O dia é o da
  execução, não o do processamento.
- **Esgotado:** o motor procura outro profissional **compatível com vaga**. Se **todos** os compatíveis já estão no limite, a OS
  **continua sendo escalada** (para o menos carregado do dia, ou para o responsável da regra nominal / do cargo exigido) e fica
  marcada `requer_intervencao`: a tela mostra só o aviso **“Requer intervenção”** e o motivo aparece quando o usuário **clica**.
  Nunca vai para cargo incompatível. “Sem candidato” passa a significar apenas **ninguém elegível** (desligados, bloqueados,
  fora de escala, regra pendente…). Indicador e filtro “Requer intervenção” = sem candidato + acima do limite.
- **Decisão pendente (impacto grande):** com a regra 5.4 há **~27 rondas diurnas e ~19 noturnas por dia** (HMB) e um
  único responsável por turno/paridade; o teto de 14 deixa ~13 rondas/dia por pessoa como “requer intervenção”. Se a
  supervisão entender que rondas **não** consomem o limite, incluir `8` (tipo RONDA no Neovero) em
  `TIPO_IDS_ISENTOS_LIMITE` — há teste cobrindo as duas situações.

## 5.4 Rondas diárias (HMB) — AUTOMÁTICAS no Neovero

**Retorno dos gestores (15/10/2026):** as rondas diárias são automáticas — o Neovero já cria cada uma com um dos 4 responsáveis de
equipe (**ELÉTRICA-DIURNO, ELÉTRICA-NOTURNO, CLIMATIZAÇÃO-DIURNO, CLIMATIZAÇÃO-NOTURNO**) e “os responsáveis já puxam
diretamente do Neovero”. Dados reais (set–out): 1 698 OS de ronda diária; 1 238 delas com essas equipes (35 ainda abertas).
Decisão adotada (“seguir o Neovero”), **só na HMB**:

- as 4 equipes valem como **responsável correto** das rondas diárias: etiqueta **“Equipe do Neovero”**, fora da Revisão e fora
  de “Genérico”; o plano que as tem como responsável padrão também deixa de aparecer em “Planos com responsável inválido”;
- o sistema **não recomenda executante** para rondas diárias (OS nem projeções);
- a tabela nominal abaixo está **desativada** (`REGRAS_DESATIVADAS` em `units/brasilandia/regras.py`) — some a pendência de “Michael” e
  “Diego H”; o código e os testes continuam, caso seja pedido reativar;
- uma ronda diária em nome de **gestor** (ou desligado/bloqueado/vazio) continua sendo sinalizada e recebe recomendação;
- **Quem aparece na tela:** no lugar do nome da equipe, a coluna Recomendado mostra **as pessoas de plantão naquela equipe, naquele dia** (escala vigente:
  Elétrica = eletricista/aux. elétrica; Climatização = técnico/aux. de climatização; turno da equipe; sem gestão, desligados ou bloqueados), com “Plantão · <equipe>”
  logo abaixo. Vale para OS abertas e previsões (a equipe padrão do plano). Sem ninguém de plantão, ou em mês diferente do da escala carregada, mostra só o nome
  da equipe — nunca inventa pessoa. OS concluídas continuam com o rótulo “Concluída”;
- nomes de equipe só valem em plano automático: em outro plano (ex.: mensal) “ELÉTRICA - DIURNO” segue como Genérico.

Efeito medido nos dados reais da HMB: OS abertas em Revisão **294 → 259** (−35); Genérico entre as abertas 38 → 3; “sem candidato”
635 → 64 (restam só os de ar comprimido/vácuo); “requer intervenção” 788 → 98.

**Tabela antiga (desativada)**

| Turno | Dia | Responsável informado | Situação na escala de out/2026 |
|---|---|---|---|
| Diurno | Ímpar | Iranildo | ✅ único (Iranildo Silva dos Santos) |
| Noturno | Ímpar | Diego H | ❌ nenhum “Diego H” (existem Diego Reimberg e Diego Ferreira da Cunha) |
| Diurno | Par | Michael | ❌ ambíguo (Michael de Campos Eguez / Michael Kelvin de Abreu Moraes, ambos diurno par) |
| Noturno | Par | Diego H | ❌ idem |

- Identifica a ronda diária por `tipoManutencao.id = 8` (RONDA) ou “RONDA” no nome, com periodicidade 1 dia.
  Turno vem do nome do plano (NOTURNO/NOITE e o truncado “NOTURN” que o Neovero produz); sem marcação = diurno.
  A **paridade é a do dia de execução** (`date.day % 2`) — vale na virada de mês (31→1, ambos ímpares).
- **Nomes ambíguos não são escolhidos.** A linha fica *pendente*, as ordens ficam *sem candidato* com o motivo, e a tela
  **Regras** deixa o supervisor confirmar quem é “Michael”/“Diego H” (gravado em `regra_resolucoes`, com auditoria).
  A confirmação só aceita colaborador **ativo**, que **execute OS** e cujo primeiro nome combine com o apelido.
- Combinação sem regra especificada → comportamento anterior preservado.

## 5.5 Oficina de ar comprimido e vácuo (HMB)

- Plano da oficina “AR COMPRIMIDO E VÁCUO” (qualquer periodicidade), turno **diurno**: **par → Douglas Rodrigues + Gustavo
  Rafael; ímpar → Israel**. Noturno **não foi especificado** → sem regra (comportamento anterior).
- Vários responsáveis: o motor devolve principal + apoio e a tela mostra os dois (“A + B”); um não sobrescreve o outro.
  O Neovero guarda **um** responsável principal por OS — o segundo precisa de preenchimento manual (a fila avisa).
- ⚠️ **Divergência detectada:** Douglas Rodrigues consta para dias **pares**, mas sua escala é **ímpar** → em dia par só
  Gustavo estará disponível; a tela mostra o alerta. Precisa de confirmação do negócio.

## 5.6 Preventivas: filtros por dia e atraso

**Causas:** (a) a lista era só *projeção* a partir de `dataProximaPreventiva` (sempre para frente) → não havia como ver
o que foi **concluído** ou está **pendente** em dias passados; (b) “atrasada” era `data < hoje` para *qualquer*
ocorrência, concluída ou não; (c) `todayISO()` usava UTC (virava o dia às 21h em Brasília); (d) “Limpar filtros”
descartava os dados carregados; (e) não havia seleção de dias.

**Modelo novo** (`core/preventivas.py`): ocorrências = **OS reais do Neovero** + projeções dos planos (a projeção é
descartada se já existe OS real para o mesmo plano/equipamento/dia — nunca duplica).

| Status | Significado |
|---|---|
| Concluída / Em andamento / Pendente / Cancelada | situação real da OS (Fechada / Em andamento / Aberta / Cancelada) |
| **Parada** | OS em andamento (situação 2) com `dataHoraParada` e **sem** `dataHoraFuncionamento`. Só exibição: a situação real no Neovero não é alterada. Para OS em andamento a tela mostra também a descrição do Neovero (ex.: “OS em Pendência - Interna”) e a observação da OS |
| **Aguardando geração** | projeção sem OS, de hoje em diante (futuro: a OS ainda será gerada) |
| **Sem OS – verificar** | projeção com data passada e sem OS — pede conferência humana; **não é atraso** (não há informação suficiente). Antes: “Sem OS gerada” |

`atrasada = OS real não concluída (Pendente, Em andamento ou Parada) com data anterior a hoje` (fuso do Brasil).
**Sem duplicidade:** uma projeção que carrega a OS aberta vinculada ao item é a mesma manutenção dessa OS (ainda que as
datas difiram) e não é contada de novo — correção validada com dados reais da HMB (113 OS apareciam duas vezes; atrasadas
382 → 302). Filtros (no
**servidor**, iguais para tela e exportação): dias não contíguos, intervalo, status (múltiplo), atraso, turno, par/ímpar,
responsável, busca, revisão, sem candidato, origem. Totais, tabela, paginação e Excel saem do mesmo cálculo; a exportação
**não aceita linhas do cliente**. “Incluir atrasadas de dias anteriores” (ligado por padrão) traz as OS ainda abertas
mesmo fora do período.

## 5.8 Cargo exigido por plano (HETRIN)

Mecanismo genérico (`core/regras/cargos.py`) com tabela **por unidade** (`units/grand_massif/regras_cargo.py`); a HMB não
tem tabela e **não herda nada**. Gate estrito no motor: só concorre quem é de uma família de cargo permitida, disponível
e com vaga no dia; sem ninguém → *sem candidato* com o motivo (o sistema **nunca escolhe outro cargo por conta própria**).
Cargo **alternativo** só existe quando declarado na tabela e só entra se nenhum principal puder — e o resultado traz o aviso.

| Plano (padrão no nome) | Cargo principal | Alternativa explícita |
|---|---|---|
| Rondas diárias de chiller / ar comprimido | Técnico de Climatização | — |
| Limpeza de fancoils e fancoletes | Técnico de Climatização | — |
| Inspeção do sistema de combate a incêndio | Eletricista | — |
| Grupos geradores (teste de partida e demais planos) | **Exclusivamente** Eletricista | — |
| Painéis termossolares (limpeza/inspeção) | Eletricista | — |
| Coleta de medidor noturna (N1) | Aux. Eletricista | — |
| Réguas de gases medicinais; exaustores/difusores | Aux. Manutenção/Climatização | Aux. Eletricista |
| Ronda de iluminação/tomadas | Eletricista | Aux. Eletricista |
| Motobombas | Eletricista (nomes por turno/dia na tabela abaixo) | — |

### Regras nominais da HETRIN (`units/grand_massif/regras.py`) — correção de out/2026

| Plano | Turno × dia | Responsável |
|---|---|---|
| Fancoletes | ímpar | Wagner Alves Cardozo (técnico diurno) |
| Fancoletes | par | Eduardo Oliveira da Cunha (técnico noturno) |
| Motobombas | diurno ímpar | Luís Alberto |
| Motobombas | diurno par | Salem Abreu |
| Motobombas | noturno ímpar | Lúcio Jorge **e** Valdene Ferreira |
| Motobombas | noturno par | Maikon Douglas |

Combinação não listada → a regra não se aplica e vale o gate de cargo. Os nomes são validados contra o quadro ativo (apelido
ambíguo/ausente deixa a linha pendente, só administradores resolvem). Wellington (bloqueado por aptidão) não recebe
recomendação enquanto o bloqueio existir.

### Novos colaboradores (HETRIN)
Eduardo Oliveira da Cunha (Técnico de Climatização, admitido em **02/10/2026**) e Alceu Rodrigues Junior (Eletricista, admitido em
**13/10/2026**) já constam na escala de outubro; a data de admissão foi registrada (semente `colaboradores_overlay.json` +
migração 007, que só preenche onde ainda não há data) — antes dela nenhum dos dois é elegível.

### Regras e Atribuição são exclusivas do administrador
A tela e **todas** as rotas `/regras*` e `/atribuicoes*` (das duas unidades) respondem 403 a usuário comum; o menu e o aviso de
“nomes pendentes” também ficam ocultos para ele.

OS **já atribuídas** a cargo fora da regra são apenas sinalizadas (campo `cargo_fora_da_regra`, aba “Cargo fora da regra” em
Revisão) — nada é reatribuído. A regra nominal (`nomes_obrigatorios`) tem precedência sobre o cargo.

## 5.9 Histórico de responsável e planos com responsável padrão inválido

- O Neovero só informa o responsável **atual**. A aplicação registra (append-only, por unidade) a 1ª leitura de cada OS e
  cada mudança de responsável entre leituras (`os_responsavel_historico`; `GET /transferencias`). Mudanças anteriores ao
  monitoramento não são conhecidas; o **motivo** é anotado por uma pessoa (`PUT /transferencias/{id}/motivo`, auditado).
- Revisão lista os **planos ativos cujo responsável padrão** (o Neovero cria cada OS com ele) é gestão, genérico, desligado,
  bloqueado ou sem identificação, com o nº de OS abertas afetadas. “Não identificado” = nenhuma OS aberta permite descobrir o
  nome do responsável daquele id.

## 5.7 Preenchimento automático do responsável no Neovero

**Viabilidade (investigada, somente leitura):** não há Swagger/documentação (`/swagger`, `/docs` → 404). `OPTIONS
/api/ordensservico/{id}` responde `Allow: DELETE, GET, PATCH, PUT`, ou seja, atualização existe tecnicamente, mas é a
**API interna do cliente web**, não uma integração oficial; formato do corpo, permissões da conta e efeitos colaterais
**não foram validados** e **nenhuma escrita foi feita**. Por isso a automação é entregue em camadas seguras:

1. **Fila** (sempre): OS abertas com responsável gestão/genérico/desligado/vazio + executante proposto pelo motor
   (regras, escala, limites).
2. **Propostas + aprovação** persistidas, **idempotentes** (chave = unidade+OS+executante+data).
3. **Aplicação desligada por padrão** (`NEOVERO_WRITE_ENABLED=false`). Ligada, ainda roda em **simulação**
   (`NEOVERO_WRITE_DRY_RUN=true`): valida contra o Neovero (OS existe, é da unidade, está aberta, responsável não mudou —
   *compare-and-set* —, vaga no dia) e registra o que seria enviado. O `PATCH {"responsavelId": id}` só sai com as duas
   chaves alteradas, lê de volta e audita antes/depois. **Antes de ligar: testar com UMA OS em ambiente seguro.**
4. Itens **não automatizáveis** (id Neovero desconhecido/ambíguo, regra com 2 responsáveis, sem candidato) aparecem com o
   motivo.

## Premissas gerais

- A escala (Excel) usada é a do **mês corrente** (comportamento original): consultar datas de outro mês usa a escala vigente.
- Hora de execução das OS projetadas: 8h (diurno) ou 20h (plano noturno) — igual ao motor original.
- **Administradores (perfil `dev`):** o primeiro vem de `DEV_ADMIN_*`; **só um administrador cria outro administrador** (`POST /api/admin/users` com `role: "dev"`, sempre sem unidade). Usuário comum recebe 403. O perfil **só se define na criação** (PATCH de `role` → 400). Proteções: o administrador não desativa a própria conta (`admin_proprio`), nunca fica sem administrador ativo, e a senha de um administrador só é alterada por ele mesmo; `DEV_ADMIN_RESET_PASSWORD` redefine apenas o administrador mais antigo. Tudo é auditado (`perfil: dev` nos detalhes, sem senha).

# Auditoria V2 — Refinamento (HETRIN × HMB)

Data da coleta: **14/10/2026**. Fonte: Neovero **somente leitura** (consultas `POST …/query`; nenhuma escrita), OS de
**01/09 a 31/10/2026** das duas unidades (HETRIN: 4 184 OS no período + 181 abertas, 74 planos; HMB: 4 305 + 432, 120
planos), cruzadas com o cadastro/escala do mês e o overlay do banco. As rotinas usadas ficaram fora do repositório
(coleta em pasta temporária); os números abaixo saem do **mesmo código** que roda na aplicação (`gerar_ocorrencias`).

Legenda — **Corrigido e validado**: corrigido no código, com teste automatizado **e** conferido com dado real ·
**Parcial** · **Não corrigido** · **Não validado**: sem como comprovar com o que há acessível (diz o que falta).

## Parte B.1 — HETRIN

| # | Item | Estado | Evidência | Ação / pendência |
|---|---|---|---|---|
| 1 | Desligados: Carlos Aurélio (11/09), Maikon Jonathas (16/09), William Miranda (22/09) | **Corrigido e validado** | Cadastro: `status=Desligado` com as 3 datas. Motor: **0** recomendações a desligados (antes ou depois da data). Nome-grafia **Willian/William** e **Morais/Moraes** casam (`WILLIAN  MIRANDA DE MORAIS` → `William Miranda de Moraes`) | — |
| 2 | Não confundir **Maikon Douglas Batista** (eletricista noturno, ativo) com **Maikon Jonathas** | **Corrigido e validado** | `encontrar_no_cadastro`: nomes completos casam cada um com o seu; só “MAIKON” é recusado (ambíguo → `None`) | — |
| 3 | OS ainda em nome de desligado | **Parcial** (sinalizado; não reatribuído de propósito) | OS abertas: William **2** (202615167 de 23/09 e 202615430 de 26/09 — abertas **depois** do desligamento), Carlos Aurélio **2**. Aparecem em *Revisão* com substituto sugerido | Reatribuir é decisão humana (fila **Atribuição**); escrita no Neovero segue desligada |
| 4 | “4 registros novos do William em 01/10” | **Não validado** | Na coleta **não há OS com William aberta em 01/10** (49 OS dele, última em 26/09; plano-padrão dessas OS é o id 102, não o dele). Não reproduzido | Precisa dos 4 números de OS/registros para investigar a causa-raiz |
| 5 | Carlos Aurélio como responsável **padrão** de plano | **Corrigido e validado** (detecção) | 2 planos (“Réguas de gases medicinais” e “… TÉRREO”) têm o id dele como padrão ⇒ toda OS nova já nasce em nome de desligado. Nova aba *Revisão → Planos com responsável inválido* lista isso, com nº de OS afetadas | Trocar o responsável padrão **no Neovero** (a aplicação não escreve) |
| 6 | Cargos por plano (combate a incêndio, teste de partida, painéis, medidor N1, fancoils BL1, réguas/exaustores, rondas) | **Corrigido e validado** | Gate estrito em `indicar_responsavel` + tabela `units/grand_massif/regras_cargo.py` (nomes de plano **reais**, testados). Dados reais: **0** recomendações fora da regra; por regra, ex.: rondas de climatização → só Técnico (154); medidor N1 → só Aux. Eletricista (9); teste de partida → só Eletricista (6) | — |
| 7 | Cargos **alternativos** configuráveis (não indiscriminados) | **Corrigido e validado** | Só 2 regras declaram alternativa (réguas/exaustores e rondas de iluminação/motobombas); só entra se nenhum principal pode e **gera aviso** “Cargo alternativo usado” (136 principais × 39 alternativos nas réguas) | Confirmar com a supervisão se as duas alternativas estão certas |
| 8 | OS **já** atribuídas a cargo fora da regra | **Corrigido e validado** (sinalização) | **30** OS abertas sinalizadas: 4 rondas de ar comprimido com Eduonete (não é Técnico) e 2 réguas com Carlos Aurélio (desligado) = *fora da regra*; 24 de rondas de iluminação/exaustores com Aux. Eletricista = *cargo alternativo* Aba *Cargo fora da regra* | Nada é reatribuído automaticamente |
| 9 | Wellington (registro) | **Corrigido e validado** | Cadastro: `Wellington de Souza Brito`, Aux. Eletricista noturno, **bloqueado** (aptidão pendente). No Neovero o nome é **“WELINGTON DE SOUSA BRITO”** (grafia diferente) e casa. **30** OS abertas em nome dele → status *Bloqueado*; 0 recomendações a ele | Liberar/atualizar o bloqueio quando a aptidão for regularizada (tela Colaboradores) |
| 10 | Falta de Técnico de Climatização à noite (Chiller 02, compressores 03/05/07) | **Parcial** | Há **2** técnicos (Wagner diurno e Eduardo noturno), em dias **alternados**. Rondas diárias de climatização (14–31/10): 171 ocorrências, 83 → Wagner, 74 → Eduardo, **14 sem candidato** por limite diário (10/dia/técnico) a partir de 22/10. O motor **não** completa com outro cargo: fica *sem candidato* com o motivo | Decisão de negócio: reforçar/contratar ou relaxar o limite (10). Alerta específico de “concentração de carga” **não** foi criado (a cobertura é o limite diário + *sem candidato*) |
| 11 | Compressores 02/05/07: rondas “Sem OS” desde 16/09 | **Validado como causa** | Os 3 itens têm a **OS de 14/09 ainda aberta** (202614049/053/047) e o item do plano não avançou ⇒ o Neovero não gerou as rondas seguintes. Aparecem como *Sem OS – verificar* (3 por dia par) | Encerrar/tratar as 3 OS antigas no Neovero |
| 12 | OS paradas/“aguardando garantia” | **Parcial** | 202614049: situação 2 **com** `dataHoraParada` e sem retorno → status **Parada**. 202614053/047: com `dataHoraFuncionamento` (voltaram) → continuam *Em andamento*. 202615533–536: todas “**OS em Pendência**” com observação “AGUARDANDO/EM MANUTENÇÃO”, **sem** parada registrada → *Em andamento* + a descrição e a observação do Neovero exibidas. Nenhuma situação foi alterada | O Neovero não traz “garantia” em campo estruturado; se 533–536 devem ser *Parada*, é decisão de regra |
| 13 | Futuro × passado: “Aguardando geração” × “Sem OS – verificar” | **Corrigido e validado** | Renomeados e testados. Real (set–out): 1 534 *Aguardando geração*; **163** *Sem OS – verificar* (na 1ª medição, antes de eliminar as duplicidades — 171 —, 98 não tinham nenhuma OS do plano+equipamento na coleta e 73 tinham OS do mesmo plano+equipamento em outra data). Causas: itens com `dataProximaPreventiva` parada no passado (ex.: fancolete desde 16/07; splits em 23/08), rondas bloqueadas por OS antiga aberta (item 11) | Os 11 registros de 25–27/09 citados: na coleta são **14** (Emergencial QAI/climatização ×3, Split ×2+1, Compressores 02/05/07 ×3, Fancolete Trox ×5) — mesma causa |
| 14 | Transferências / histórico de responsável (OS 202614226, 202615137/150, 202615392, 202615448/449) | **Parcial** | O Neovero só dá o responsável **atual** (hoje: Manoel, Jussara ×3, Salem, Luís Alberto — todos válidos). Passou a existir histórico **auditável a partir de agora** (1ª leitura + cada mudança; motivo anotado por pessoa) | Transferências **anteriores** a hoje não são recuperáveis pela API |
| 15 | Possíveis equipamentos duplicados (QUADRO-QAC-BOILLER, QUADRO-QAC-FC-B4-08, RÉGUA HOSPITALAR 01/02/SEM MODELO) | **Não corrigido** (só diagnóstico) | Mesmo nome com **2 ids** (3184/3186; 3193/3194); “RÉGUA HOSPITALAR 01” tem 27 ids e “02” 25 — são itens de plano distintos com o mesmo nome | Nada foi apagado/unificado. Conferir no cadastro do Neovero |
| 16 | Erros conhecidos do relatório **não** viram regra | **Corrigido e validado** | Luís Alberto **ativo** (nome com acento casava errado antes — bug real de `nomes_batem`, corrigido e testado); Wagner é Técnico de Climatização; compressores 02/05/07 = itens do plano; “01/10” não codificado | — |

## Parte B.2 — HMB

| # | Item | Estado | Evidência | Ação / pendência |
|---|---|---|---|---|
| 1 | Desligados: Ronaldo (08/09), Caio (18/09), Lesle (26/09) | **Corrigido e validado** | Cadastro com as 3 datas; **0** recomendações a desligados; nenhuma OS aberta em nome deles | — |
| 2 | Executantes incorretos | **Parcial** | OS abertas por situação do responsável: **Gestão 235** (William de Souza Lobo), Genérico 38 (“ELÉTRICA – DIURNO/NOITE”, “CLIMATIZAÇÃO – NOITE”, “AR CONDICIONADO”), Bloqueado 16 (Uelton), Sem responsável 5, Atribuída 79. Todas em *Revisão* com executante sugerido | Aplicar no Neovero depende de liberar a escrita (item 8) e aprovar |
| 3 | Limites 14 (elétrica) / 10 (climatização) | **Corrigido e validado** | Recomendações respeitam o teto: **0** estouros (set–out); máx. observado 14/dia (Diego Reimberg, Iranildo) | — |
| 4 | Tabela das rondas diárias | **Parcial** | Iranildo (diurno ímpar) resolvido. **Pendentes de confirmação humana**: “Michael” (ambíguo: 2 pessoas) e “Diego H” (nenhum com essa inicial). 599 ocorrências de ronda estão sob regra pendente — as que precisam de executante ficam *sem candidato* por desenho, em vez de escolher ao acaso | Confirmar os dois nomes na tela *Regras* |
| 5 | Tabela de AC/vácuo | **Parcial** | Dia Ímpar → Israel; dia Par → Douglas **e** Gustavo. Pela escala real de outubro **Douglas trabalha dias ímpares** e Israel está “FR” de 17/10 em diante ⇒ nos dias pares só Gustavo está presente e nos ímpares Israel quase nunca: 69 ocorrências recomendadas (1 pessoa) e 71 *sem candidato* | A regra e a escala se contradizem — decisão de negócio. O Neovero guarda **um** `responsavelId` por OS: dois responsáveis não são aplicáveis por API |
| 6 | Filtros de preventivas, atrasos, totais | **Corrigido e validado** | **Bug real encontrado e corrigido**: 113 OS contadas em dobro (projeção do item + OS real de outra data). Depois: 0 duplicadas; atrasadas **382 → 302** e Pendentes **509 → 373**, e atrasadas = OS abertas com data < hoje (302 = 302). 126 combinações status×atraso×turno×paridade: totais, listagem e soma por status **idênticos** | — |
| 7 | Isolamento HETRIN × HMB | **Corrigido e validado** | Testes de acesso por unidade (rotas, query, headers), cache e histórico de responsável por unidade; regras de cargo só na HETRIN | — |
| 8 | Automação da atribuição no Neovero | **Não validado** | Escrita **desligada** (`NEOVERO_WRITE_ENABLED=false`) e em simulação; o contrato do `PATCH /api/ordensservico/{id}` não é documentado e **nenhuma escrita foi feita** | Testar com **uma** OS em ambiente seguro antes de ligar |

## Parte A — O que mudou nesta rodada

1. **Usabilidade:** menu por prioridade (Preventivas · Colaboradores · Revisão; *Configuração*: Atribuição/Planos/Regras;
   admin: Usuários · Utilização; rodapé: Sugestões e Suporte); filtros ativos como chips removíveis; “Mais filtros”
   recolhido; Revisão com abas (ordens, planos com responsável inválido, cargo fora da regra, transferências).
2. **Utilização (Dev):** KPIs (ativos agora, tempo de sessão × ativo × ocioso, encerradas por inatividade, sem utilização
   registrada), lista “conectados agora”, tabela por usuário, sessões (início/fim/motivo), eventos, critérios explícitos,
   ficha do usuário, exportação. Ausência de registro nunca vira “não utiliza”.
3. **Logout em 25 min:** decidido no servidor, auditado, 401 com motivo, multi-aba, aviso 2 min antes, “não foi salva”.
4. **Gestão de usuários:** ficha, desbloqueio, perfil imutável por API, Dev protegido, tudo auditado.
5. **Logo** na tela de login (desktop e mobile), sem mexer no resto.
6. **Sugestões e Suporte:** formulário + `/api/suporte` com SMTP real (**sem credenciais ⇒ “não configurado”, nada simulado**).
7. **Regras:** cargo por plano (HETRIN), histórico de transferências, planos com responsável inválido, status Parada /
   Aguardando geração / Sem OS – verificar, correção de acentos em nomes, correção de OS duplicadas.

## Parte C — Verificação, riscos e dependências

- Testes: backend **596 passed, 2 skipped** · `ruff` limpo · frontend `tsc` limpo, **Vitest 93**, build ok.
- **Não validado com dado real:** envio de e-mail (sem `SMTP_USER/SMTP_PASSWORD`; testado com SMTP simulado em teste),
  escrita no Neovero, causa-raiz dos “4 registros do William em 01/10”, banco Cloud SQL (usuário/nome do banco ainda a obter).
- **Decisões de negócio abertas:** capacidade das rondas × limite diário (HETRIN: 321 rondas de iluminação noturnas (set–out)
  sem candidato por limite diário; Técnico de Climatização 10/dia), Michael/Diego H (HMB), AC/vácuo × escala, alternativas de cargo, 533–536 = Parada?
- **Dependências externas:** conta Gmail com senha de app para o suporte; credenciais do Cloud SQL; liberar escrita do Neovero.

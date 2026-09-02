"""
Motor de Decisão — lógica de scoring compartilhada entre todas as unidades.
Cada unidade implementa sua própria função `esta_disponivel` e `carregar_colaboradores`.
"""
import re

# ── Pesos e constantes ────────────────────────────────────────────────────────
SCORE_FUNCAO_COMPATIVEL = 100
SCORE_FUNCAO_SECUNDARIA = 50
SCORE_TURNO_CORRETO = 50
SCORE_EXP_ATIVO = 20
SCORE_EXP_TIPO = 10
SCORE_CRITICIDADE = 30
PENALIDADE_CARGA = 25
SCORE_HABILIDADE_MAX = 80  # teto da contribuição de habilidades, para não dominar o cargo
# Complexidade/andar pesam mais que os bônus "soft" acima (exp/criticidade) porque o
# pedido da supervisão (ajustes de distribuição de OS, set/2026) explicitamente quer
# esses dois critérios decidindo a recomendação ANTES do score genérico — sem virar
# gate booleano duro (ver docstring de indicar_responsavel para o motivo).
SCORE_COMPLEXIDADE_ADEQUADA = 40
SCORE_ANDAR_REPETIDO = 35
PENALIDADE_CARGA_ALTA = 15  # extra, além de PENALIDADE_CARGA, só quando a tarefa atual é Alta complexidade — evita empilhar toda tarefa complexa sempre na mesma pessoa

# ── Catálogo de habilidades ───────────────────────────────────────────────────
# Extensível: uma habilidade nova é uma linha aqui, não um novo if/else no motor.
# categoria deve bater com uma das categorias que classificar_categoria() retorna.
HABILIDADES = [
    {"id": "aux_eletrica",      "nome": "Auxiliar de Manutenção Elétrica",        "categoria": "Elétrica",      "peso": 50},
    {"id": "aux_hidraulica",    "nome": "Auxiliar de Manutenção Hidráulica",      "categoria": "Hidráulico",    "peso": 50},
    {"id": "aux_refrigeracao",  "nome": "Auxiliar de Manutenção em Refrigeração", "categoria": "Refrigeração",  "peso": 50},
    {"id": "aux_inspecao",      "nome": "Auxiliar de Inspeção/Rondas",            "categoria": "Inspeção",      "peso": 30},
    {"id": "tec_eletrica",      "nome": "Técnico em Elétrica",                    "categoria": "Elétrica",      "peso": 80},
    {"id": "tec_hidraulica",    "nome": "Técnico em Hidráulica",                  "categoria": "Hidráulico",    "peso": 80},
    {"id": "tec_refrigeracao",  "nome": "Técnico em Refrigeração",                "categoria": "Refrigeração",  "peso": 80},
]
HABILIDADES_POR_ID = {h["id"]: h for h in HABILIDADES}

# ── Keywords por categoria ────────────────────────────────────────────────────
# "ar comprimido" e "sistema termossolar" foram adicionados a pedido da supervisão da
# HETRIN (ajustes de distribuição de OS, set/2026) — confirmado rodando o código real
# contra os planos ativos: sem essas keywords, "PM - RONDA DIÁRIA - SISTEMA DE AR
# COMPRIMIDO" e "PM MENSAL - SISTEMA TERMOSSOLAR" caíam no fallback genérico
# 'Inspeção' e tratavam Técnico de Climatização e Eletricista como igualmente aptos,
# quando o pedido é que climatização seja o cargo preferencial pra essas duas linhas.
# "sistema termossolar" (não só "termossolar") é proposital: existe também o plano
# "LIMPEZA E INSPEÇÃO VISUAL DOS PAINÉIS TERMOSSOLARES", que o pedido NÃO menciona e
# onde eletricistas já atuam hoje (achado da investigação: 19 ocorrências/mês,
# considerado uso plausível/misto) — usar a frase completa evita reclassificar esse
# outro plano e mudar um comportamento que não foi reportado como problema.
_KW_REFRIG = [
    "ar condicionado", "ar-condicionado", "fancoil", "fan coil", "chiller",
    "split", "refrigeração", "climatização", "exaustor", "ar comprimido",
    "sistema termossolar",
]
# "quadro(s) de distribuição" e "quadro(s) hvac" foram adicionados a pedido da
# supervisão da HETRIN — confirmado rodando o código real: "PM - RONDA SEMANAL -
# QUADROS DE DISTRIBUIÇÃO" e "PM - RONDA SEMANAL - QUADROS HVAC" caíam no fallback
# 'Inspeção' (nenhuma keyword antiga batia — "quadro elétric" não cobre nenhuma das
# duas frases) e por isso aceitavam Técnico de Climatização como apto, quando ambos os
# planos são "EXCLUSIVAMENTE Eletricistas" pelo pedido. Note: NÃO adicionamos "hvac"
# sozinho a _KW_REFRIG — isso classificaria "QUADROS HVAC" como Refrigeração e
# reabriria exatamente esse mesmo bug (Técnico de Climatização apto num plano
# elétrico), só que pelo caminho contrário.
# "medidor"/"coleta" foram adicionados a pedido da mesma supervisão: sem eles, "COLETA
# DIÁRIA MEDIDOR..." caía em 'Geral', categoria cujo fallback aceita QUALQUER cargo
# sem exceção (inclusive Gerente de Equipe/Engenheira, Auxiliar Administrativo) — não
# incluímos "medidor"/"coleta" aqui em _KW_ELETRICA porque o cargo esperado pra coleta
# é "Auxiliar" em geral (inclusive Aux. Manutenção/Climatização, que não é elétrica) —
# ver _KW_INSPECAO abaixo.
#
# "cco" e "comando" foram REMOVIDOS daqui (existiam antes) — confirmado rodando contra
# os 195 planos ativos reais das duas unidades (HETRIN+HMB): as duas únicas
# ocorrências de "cco"/"comando" em toda a base vêm da oficina "CENTRO DE COMANDO DA
# OPERAÇÃO - CCO", usada nos 6 planos de coleta diária (medidor/hidrômetro) da HETRIN
# — um departamento de operações, sem relação com elétrica. Como
# `tipo_classif = f"{tipo} {descricao} {oficina}"` (routes.py) inclui a oficina no
# mesmo texto avaliado por classificar_categoria(), essas duas keywords forçavam
# "Elétrica" pra TODAS as coletas, cujo _cargo_compativel só aceita a família
# eletricista — excluindo por engano os auxiliares de climatização/manutenção geral
# (ex: Isabel Alves Dias) que a própria escala nomeada da supervisão exige pra essas
# coletas (ver units/grand_massif/escala_nomeada.py). Nenhum outro plano ativo, nas
# duas unidades, dependia dessas duas keywords pra classificar corretamente.
_KW_ELETRICA = [
    "energia elétrica", "régua elétrica", "régua de energia", "quadro elétric",
    "elétrico", "tomada", "disjuntor", "iluminação", "subestação", "média tensão",
    "ccm", "qgbt", "eletroduto", "cabo elétrico", "nobreak", "ups",
    "baixa tensão", "instalação elétric", "painel elétric",
    "quadro de distribuição", "quadros de distribuição", "quadro hvac", "quadros hvac",
]
_KW_HIDRO = [
    "hidrômetro", "hidráulico", "reservatório", "esgoto", "bomba de água",
    "vaso sanitário", "caixa d'água", "caixa dagua", "encanamento",
    "calefação", "hidrante",
]
_KW_INSPECAO = ["rotina", "inspeção", "ronda", "pm ", "preventiva"]
# "coleta"/"medidor" têm prioridade MAIOR que as 4 listas acima (checados antes, em
# _classificar_texto) — descrevem o TIPO de tarefa (uma leitura/anotação simples), não
# o equipamento sendo lido, e valem pra "Coleta Diária Medidor de Energia" e "Coleta
# Diária Hidrômetro" igualmente. Sem essa prioridade, "COLETA DIÁRIA HIDRÔMETRO..."
# batia em "hidrômetro" (_KW_HIDRO) ANTES de "coleta" ser considerado e virava
# 'Hidráulico' — cuja lista de cargo compatível exclui "Aux. Eletricista" (cargo real
# de Jussara/Eduonete, exatamente quem a escala nomeada da supervisão escala pra essa
# coleta — ver units/grand_massif/escala_nomeada.py). Confirmado com dado real: 28 de
# 28 ocorrências de Hidrômetro em setembro/2026 (100%) foram pra outra pessoa por
# causa disso, porque o filtro de cargo já excluía Jussara/Eduonete do pool ANTES do
# filtro de escala nomeada sequer rodar. Tirar "coleta"/"medidor" do fallback 'Geral'
# (que aceita QUALQUER cargo, sem exceção) pra 'Inspeção' (_CARGO_TECNICO +
# _CARGO_AUXILIAR) já resolvia a maior parte do problema pro Medidor; faltava só essa
# prioridade sobre 'Hidráulico' pro Hidrômetro. 'Inspeção' continua aceitando os
# auxiliares reais nomeados e qualquer técnico, mas já exclui cargos puramente
# administrativos/gerenciais (Gerente de Equipe, Auxiliar Administrativo, Profissional
# Multidisciplinar). Verificado contra as duas unidades: "coleta" só aparece em 8
# planos ativos, todos na HETRIN, todos leituras simples (medidor de energia,
# hidrômetro, termo-higrômetro) — nenhum plano da HMB usa essa palavra.
_KW_COLETA = ["coleta", "medidor"]

SETORES_CRITICOS = [
    "centro cirúrgico", "sala cirurg", "bloco cirurg", "bloco 4",
    "uti", "uco", "cti", "ccu", "neonatal", "unidade de terapia intensiva",
]

# ── Mapa cargo → categoria compatível ────────────────────────────────────────
_CARGO_ELETRICA = ["eletricista", "elétric", "técnico elétric"]
_CARGO_REFRIG = ["refrigeração", "técnico em refrig", "climatização"]
_CARGO_HIDRO = ["hidráulico", "encanador"]
# "Auxiliar de Manutenção" (grafia antiga) e "Aux. Manutenção" (abreviação usada na
# planilha nova da HMB) são o mesmo cargo — confirmado com dado real: "Aux. Manutenção
# / Climatização" não batia com a lista antiga e ficava incompatível com Hidráulico
# por engano.
_CARGO_AUXILIAR = ["auxiliar de manutenção", "aux. manutenção", "aux manutenção"]
_CARGO_TECNICO = ["técnico", "eletricista", "mecânico", "oficial", "supervisor"]
# Cargos administrativos/gerenciais — nunca entram na hierarquia de complexidade
# (nem como "técnico" nem como "auxiliar"), mesmo quando o texto do cargo começa com
# "aux" (ex: "Auxiliar Administrativo" não é um auxiliar de manutenção). Usado só por
# _tier_cargo(), não por _cargo_compativel() — a elegibilidade por cargo continua
# governada só pelas listas acima, como já era.
_CARGO_ADMINISTRATIVO = ["administrativ", "gerente", "engenheir", "supervisor de equipe"]


def _e_auxiliar_especializado(cargo_l: str) -> bool:
    if not any(k in cargo_l for k in _CARGO_AUXILIAR):
        return False
    return any(e in cargo_l for e in ["elétric", "hidráulic", "refriger", "mecân"])


def _classificar_texto(texto: str) -> str:
    t = texto.lower()
    if any(k in t for k in _KW_COLETA):
        return "Inspeção"
    if any(k in t for k in _KW_REFRIG):
        return "Refrigeração"
    if any(k in t for k in _KW_ELETRICA):
        return "Elétrica"
    if any(k in t for k in _KW_HIDRO):
        return "Hidráulico"
    if any(k in t for k in _KW_INSPECAO):
        return "Inspeção"
    return "Geral"


def classificar_categoria(tipo_os: str, setor: str, ativo: str) -> str:
    """Classifica a categoria da tarefa. Prioriza o texto do PLANO/tipo de manutenção
    (`tipo_os`) — é o sinal mais confiável, porque descreve a tarefa em si (ex: "RONDA
    ILUMINAÇÃO/TOMADAS"). Só cai pro setor/ativo como sinal secundário quando o
    próprio `tipo_os` não bate nenhuma keyword (retornaria 'Geral' sozinho) — do
    contrário, um SETOR cujo nome cita outro ofício (ex: sala "CASA DE MÁQUINAS
    CLIMATIZAÇÃO" abrigando uma ronda ELÉTRICA de iluminação/tomadas) classificava a
    tarefa errado só pelo nome da sala, não pela tarefa em si.

    Confirmado com dado real (investigação HETRIN, set/2026): William Miranda de
    Moraes (Técnico de Climatização) foi recomendado numa ronda de Iluminação/Tomadas
    porque o setor da ocorrência ("BLOCO 4 1º ANDAR - CASA DE MÁQUINAS CLIMATIZAÇÃO")
    continha a palavra "climatização", batendo em _KW_REFRIG ANTES de "iluminação"/
    "tomada" (_KW_ELETRICA) serem sequer considerados — porque a versão antiga
    concatenava tipo_os + setor + ativo num único texto e checava as categorias nessa
    ordem fixa, sem dar prioridade nenhuma pra de onde veio a keyword."""
    categoria = _classificar_texto(tipo_os or "")
    if categoria != "Geral":
        return categoria
    return _classificar_texto(f"{setor or ''} {ativo or ''}")


# ── Complexidade da tarefa ────────────────────────────────────────────────────
# Pedido da supervisão (ajustes de distribuição de OS, set/2026): auxiliares devem
# receber tarefas de baixa complexidade primeiro (coletas, limpezas, inspeções
# simples, rondas, conferências, apoio); técnicos/eletricistas devem receber as de
# alta complexidade (equipamentos especializados). Implementado como PREFERÊNCIA de
# score (ver SCORE_COMPLEXIDADE_ADEQUADA/_score_complexidade), não como gate de
# elegibilidade — ver docstring de indicar_responsavel() pro motivo (empilhar gates
# booleanos novos multiplica o risco de "sem candidato", já documentado nos gates de
# cargo/turno existentes).
COMPLEXIDADE_BAIXA = "Baixa"
COMPLEXIDADE_MEDIA = "Média"
COMPLEXIDADE_ALTA = "Alta"

# Verbos/tarefas que são baixa complexidade por definição, independente do
# equipamento envolvido — é a própria supervisão que define assim ("limpeza, apoio,
# inspeções básicas" são baixa complexidade mesmo perto de equipamento sofisticado).
# Por isso são checados ANTES das keywords de equipamento especializado abaixo: sem
# essa prioridade, "PM - LIMPEZA GERAL - SALA DOS NOBREAKS" (uma tarefa de limpeza,
# que o próprio pedido atribui a Auxiliares de Eletricista) seria classificada Alta só
# por citar "nobreak", contradizendo a regra que a supervisão pediu pra esse mesmo
# plano.
_KW_COMPLEXIDADE_BAIXA = [
    "limpeza", "coleta", "medidor", "hidrômetro", "conferência", "conferencia",
    "apoio", "leitura", "gases medicinais",
]
# Equipamentos/sistemas citados explicitamente pelo pedido da supervisão como exemplo
# de alta complexidade (Técnicos de Climatização) ou de tarefa reservada a eletricista
# pleno (quadros/nobreaks) — só considerado se nenhuma keyword de baixa complexidade
# acima já bateu.
_KW_COMPLEXIDADE_ALTA = [
    "chiller", "fancoil", "fan coil", "split", "ar comprimido", "termossolar",
    "nobreak", "ups", "quadro de distribuição", "quadros de distribuição",
    "quadro hvac", "quadros hvac", "subestação", "média tensão", "qgbt",
]


def classificar_complexidade(tipo_os: str, setor: str, ativo: str) -> str:
    """Classifica a tarefa em Baixa/Média/Alta complexidade. Sem keyword nenhuma
    batendo (nem baixa nem alta), o default é Média — não é omissão de dado, é o
    nível intermediário mesmo (ex: rondas de iluminação/tomadas, reparo pontual sem
    especialização)."""
    texto = f"{tipo_os or ''} {setor or ''} {ativo or ''}".lower()
    if any(k in texto for k in _KW_COMPLEXIDADE_BAIXA):
        return COMPLEXIDADE_BAIXA
    if any(k in texto for k in _KW_COMPLEXIDADE_ALTA):
        return COMPLEXIDADE_ALTA
    return COMPLEXIDADE_MEDIA


def _tier_cargo(cargo_l: str) -> str:
    """Reduz o cargo a 3 níveis pra casar com classificar_complexidade(): 'tecnico'
    (eletricista/técnico pleno), 'auxiliar' (aux. eletricista, aux. manutenção — pega
    qualquer cargo que comece com "aux", inclusive as grafias abreviadas da HMB) ou
    'outro' (cargos administrativos/gerenciais, que não entram na hierarquia de
    complexidade nem como técnico nem como auxiliar — checado ANTES do prefixo "aux"
    pra não confundir "Auxiliar Administrativo" com auxiliar de manutenção)."""
    if any(k in cargo_l for k in _CARGO_ADMINISTRATIVO):
        return "outro"
    if cargo_l.strip().startswith("aux"):
        return "auxiliar"
    if any(k in cargo_l for k in _CARGO_TECNICO):
        return "tecnico"
    return "outro"


def _score_complexidade(cargo_l: str, complexidade: str) -> int:
    tier = _tier_cargo(cargo_l)
    if complexidade == COMPLEXIDADE_ALTA and tier == "tecnico":
        return SCORE_COMPLEXIDADE_ADEQUADA
    if complexidade == COMPLEXIDADE_BAIXA and tier == "auxiliar":
        return SCORE_COMPLEXIDADE_ADEQUADA
    return 0


def _tier_adequado(complexidade: str) -> str | None:
    """Tier de cargo preferencial pra essa complexidade — None pra Média (não há
    preferência de tier definida pro nível intermediário, fica só ao sabor do score).
    Usado por indicar_responsavel() como um gate soft (ver comentário lá): sem ele,
    validação com dado real (HMB, setembro/2026 inteiro) confirmou que a penalidade de
    carga acumulada (sem teto) podia superar o bônus pontual de complexidade ao longo
    do mês — 311 ocorrências de Alta complexidade acabaram indo pra um auxiliar (o
    oposto do pedido) só porque o técnico "certo" já tinha acumulado muita carga_alta.
    Mesmo bug de fundo que o gate de cargo já resolve pra função/ofício (ver
    'Balanceamento nunca pode fazer alguém tecnicamente inadequado ganhar de alguém
    qualificado' logo abaixo) — aqui é o equivalente pra hierarquia técnico/auxiliar."""
    if complexidade == COMPLEXIDADE_ALTA:
        return "tecnico"
    if complexidade == COMPLEXIDADE_BAIXA:
        return "auxiliar"
    return None


# ── Andar/localização ─────────────────────────────────────────────────────────
# Não existe campo estruturado de andar na API Neovero (setor/setorAtual só tem
# nome/descrição em texto livre) — extração via parsing de string. Padrão validado
# contra dado real (971 setores únicos das duas unidades, HETRIN+HMB): ~95% de
# cobertura. Prioridade: andar/subsolo numerado > térreo > laje técnica > cobertura.
_RE_ANDAR_NUM = re.compile(r"(\d+)\s*[ºª°]?\s*(ANDAR?|SS|SUBSOLO|PAVIMENTO)\b")
_RE_TERREO = re.compile(r"T[ÉE]RREO")
_RE_LAJE_TECNICA = re.compile(r"LAJE\s*T[ÉE]CNICA")
_RE_COBERTURA = re.compile(r"\bCOBERTURA\b")


def extrair_andar(setor: str) -> str | None:
    """Extrai o andar/pavimento do texto livre do setor. Usado só como preferência de
    agrupamento (bônus de score — ver SCORE_ANDAR_REPETIDO), nunca como filtro de
    elegibilidade: um setor sem andar reconhecível (ex: "ÁREA EXTERNA...", que responde
    por ~69% dos ~5% sem cobertura) simplesmente não participa do agrupamento — não
    vira exclusão de ninguém. "ANDAR?" (R opcional) cobre o erro de digitação real
    "4º ANDA" achado na HMB; "SS"/"SUBSOLO" cobre "1SS"/"2SS"."""
    if not setor:
        return None
    s = setor.upper()
    m = _RE_ANDAR_NUM.search(s)
    if m:
        num, unidade = m.group(1), m.group(2)
        return f"{num}º SUBSOLO" if unidade in ("SS", "SUBSOLO") else f"{num}º ANDAR"
    if _RE_TERREO.search(s):
        return "TÉRREO"
    if _RE_LAJE_TECNICA.search(s):
        return "LAJE TÉCNICA"
    if _RE_COBERTURA.search(s):
        return "COBERTURA"
    return None


def is_critico(setor: str) -> bool:
    s = setor.lower()
    return any(k in s for k in SETORES_CRITICOS)


def _turno_compativel(turno_collab: str, hora_os: int) -> bool:
    """Mesma janela horária usada pra dar o bônus de turno em calcular_score() —
    extraída pra função própria pra poder ser reusada como filtro de elegibilidade em
    indicar_responsavel(), não só como bônus de score (ver comentário lá)."""
    turno_l = turno_collab.strip().lower()
    if turno_l == "diurno":
        return 7 <= hora_os < 19
    if turno_l == "noturno":
        return hora_os >= 19 or hora_os < 7
    return False


def _cargo_compativel(cargo_l: str, categoria: str) -> bool:
    if categoria == "Elétrica":
        return any(k in cargo_l for k in _CARGO_ELETRICA)
    if categoria == "Refrigeração":
        return any(k in cargo_l for k in _CARGO_REFRIG)
    if categoria == "Hidráulico":
        return any(k in cargo_l for k in _CARGO_HIDRO) or (
            any(k in cargo_l for k in _CARGO_AUXILIAR) and "elétric" not in cargo_l
        )
    if categoria == "Inspeção":
        return any(k in cargo_l for k in _CARGO_TECNICO + _CARGO_AUXILIAR)
    return True


def _score_funcao(cargo_l: str, categoria: str) -> int:
    if not _cargo_compativel(cargo_l, categoria):
        return 0
    if categoria == "Inspeção":
        if any(k in cargo_l for k in _CARGO_AUXILIAR):
            return SCORE_FUNCAO_SECUNDARIA if _e_auxiliar_especializado(cargo_l) else SCORE_FUNCAO_COMPATIVEL
        return SCORE_FUNCAO_SECUNDARIA
    if categoria == "Geral":
        return SCORE_FUNCAO_COMPATIVEL if any(k in cargo_l for k in _CARGO_AUXILIAR) else SCORE_FUNCAO_SECUNDARIA
    return SCORE_FUNCAO_COMPATIVEL


def _score_habilidades(habilidades: list, categoria: str) -> int:
    """Soma o peso das habilidades do colaborador compatíveis com a categoria da preventiva.
    Extensível: uma habilidade nova em HABILIDADES entra aqui automaticamente, sem
    precisar tocar nesta função."""
    if not habilidades:
        return 0
    total = sum(
        HABILIDADES_POR_ID[h]["peso"]
        for h in habilidades
        if h in HABILIDADES_POR_ID and HABILIDADES_POR_ID[h]["categoria"] == categoria
    )
    return min(total, SCORE_HABILIDADE_MAX)


def calcular_score(
    cargo: str,
    categoria: str,
    turno_collab: str,
    hora_os: int,
    setor: str,
    exp_tipo: int,
    exp_ativo: int,
    carga_at: int,
    disponivel: bool,
    habilidades: list | None = None,
    complexidade: str | None = None,
    mesmo_andar: bool = False,
    carga_alta_at: int = 0,
) -> int:
    if not disponivel:
        return -999

    cargo_l = cargo.lower()
    score = _score_funcao(cargo_l, categoria)
    score += _score_habilidades(habilidades or [], categoria)

    # complexidade/andar são opcionais (None/False por padrão) pra não afetar quem
    # chama calcular_score() diretamente sem essa informação — só indicar_responsavel()
    # as calcula e passa adiante hoje.
    if complexidade:
        score += _score_complexidade(cargo_l, complexidade)

    if mesmo_andar:
        score += SCORE_ANDAR_REPETIDO

    if _turno_compativel(turno_collab, hora_os):
        score += SCORE_TURNO_CORRETO

    score += min(exp_ativo * SCORE_EXP_ATIVO, 60)
    score += min(exp_tipo * SCORE_EXP_TIPO, 30)

    if is_critico(setor):
        score += SCORE_CRITICIDADE

    score -= carga_at * PENALIDADE_CARGA
    if complexidade == COMPLEXIDADE_ALTA:
        score -= carga_alta_at * PENALIDADE_CARGA_ALTA
    return score


def indicar_responsavel(
    colaboradores,
    hist_tipo: dict,
    hist_ativo: dict,
    carga: dict,
    tipo: str,
    setor: str,
    ativo: str,
    data_ref,
    hora_ref: int = 8,
    esta_disponivel_fn=None,
    exigir_turno: bool = False,
    andares_colaborador: dict | None = None,
    carga_alta: dict | None = None,
    nomes_permitidos=None,
):
    """
    Calcula o responsável recomendado para uma tarefa.

    `esta_disponivel_fn` deve ser uma função(row, data_ref) -> bool.
    Se None, usa disponibilidade sempre True (fallback).

    Ordem de decisão (do gate mais restritivo pro mais "soft"; ver justificativa de
    cada um abaixo): disponibilidade (hard) → cargo/função (soft) → turno, se
    `exigir_turno` (soft) → complexidade adequada ao cargo (soft) → escala nomeada,
    se houver (soft) → desempate por (score, -carga). Segue a ordem pedida (cargo →
    turno → especialidade/complexidade → escala → carga → score), com duas adaptações
    deliberadas: (1) turno vem ANTES da escala nomeada — ver comentário no bloco de
    nomes_permitidos mais abaixo (evita que um nome certo mas de turno errado "trave"
    o pool antes do gate de turno ter chance de agir); (2) par/ímpar não é um gate
    novo aqui — já é garantido por outro caminho (ver próximo parágrafo). Andar entra
    DENTRO do score (não como gate) — pesa mais que os critérios "soft" pré-existentes
    (experiência, criticidade) via SCORE_ANDAR_REPETIDO, mas nunca exclui ninguém: só
    decide quem GANHA dentro do pool que os gates acima já filtraram. Complexidade TEM
    gate (ver `tier_ok` abaixo) além do bônus de score — motivo documentado ali.

    Por que a maioria continua gate booleano "soft" (só restringe se não esvaziar) em
    vez de duro: cada gate soft hoje já é condicionado a só restringir quando o
    subconjunto resultante NÃO fica vazio — é assim que o motor consegue sempre
    preferir indicar alguém a "sem candidato". Empilhar gates booleanos duros
    (excluindo de vez, sem essa válvula de escape) multiplicaria o risco de esvaziar
    o pool em combinações raras (ex: noturno + especialidade rara + andar específico +
    alta complexidade ao mesmo tempo) — e escala Par/Ímpar já é garantida por outro
    caminho: junto com
    `esta_disponivel_fn` (que checa o calendário dia a dia) e com
    `expandir_ocorrencias()`/`_corrigir_paridade()` (que só gera a ocorrência num dia
    de paridade compatível com o que o plano exige), então adicionar um gate
    "paridade" aqui seria duplicar uma regra que já existe e já funciona, não uma
    regra nova.

    `exigir_turno` transforma o bônus de turno (SCORE_TURNO_CORRETO) num filtro
    obrigatório: só usa quando `hora_ref` reflete um turno que a origem da tarefa
    já declara explicitamente (ex: nome do plano diz "NOTURNO") — nunca pro
    `hora_ref=8` padrão usado quando o turno é apenas um palpite. Sem essa
    distinção, todo plano sem turno no nome passaria a excluir automaticamente
    qualquer colaborador noturno assim que um diurno estivesse disponível (quase
    sempre o caso), mudando a recomendação da maioria das preventivas do sistema
    por causa de um `hora_ref` que nunca foi uma informação real pra começo de
    conversa — o oposto do que se pretende corrigir aqui.

    `andares_colaborador` (opcional): dict nome -> set de andares já atribuídos a
    esse colaborador NESTA geração (mesmo padrão de `carga` — mutado por quem chama,
    normalmente incrementado em routes.py após cada atribuição). Usado só pra dar o
    bônus de "mesmo andar" (agrupamento logístico); None/{} desliga o bônus sem
    afetar mais nada.

    `carga_alta` (opcional): dict nome -> quantidade de tarefas de Alta complexidade
    já atribuídas nesta geração (mesmo padrão de `carga`). Penaliza levemente quem já
    acumulou várias tarefas complexas, pra não empilhar todas sempre na mesma pessoa
    — só entra em jogo pra tarefas que a própria ocorrência classifica como Alta.

    `nomes_permitidos` (opcional): set de nomes autorizados pra essa ocorrência
    específica (ou None = sem restrição). Usado pra escalas nominais obrigatórias
    (ex: coleta diária de medidor/hidrômetro na HETRIN — ver
    units/grand_massif/escala_nomeada.py); segue a mesma filosofia soft dos outros
    gates (só restringe se o resultado não ficar vazio).
    """
    if colaboradores is None or colaboradores.empty:
        return None, None, {}

    if esta_disponivel_fn is None:
        esta_disponivel_fn = lambda row, data: True

    categoria = classificar_categoria(tipo, setor, ativo)
    complexidade = classificar_complexidade(tipo, setor, ativo)
    andar = extrair_andar(setor)
    andares_colaborador = andares_colaborador if andares_colaborador is not None else {}
    carga_alta = carga_alta if carga_alta is not None else {}
    scores = {}

    for _, row in colaboradores.iterrows():
        nome = row["funcionario"]
        cargo = str(row.get("cargo", ""))
        turno_col = str(row.get("turno", ""))
        regime = str(row.get("regime", ""))
        habilidades = row.get("habilidades", []) or []
        disp = esta_disponivel_fn(row, data_ref)
        mesmo_andar = bool(andar) and andar in andares_colaborador.get(nome, set())
        s = calcular_score(
            cargo,
            categoria,
            turno_col,
            hora_ref,
            setor,
            hist_tipo.get((nome, tipo), 0),
            hist_ativo.get((nome, ativo), 0) if ativo else 0,
            carga.get(nome, 0),
            disp,
            habilidades,
            complexidade=complexidade,
            mesmo_andar=mesmo_andar,
            carga_alta_at=carga_alta.get(nome, 0),
        )
        scores[nome] = {
            "score": s,
            "cargo": cargo,
            "turno": turno_col,
            "regime": regime,
            "escala": f"{turno_col} | {regime}",
            "disponivel": disp,
            "carga": carga.get(nome, 0),
            "categoria": categoria,
            "complexidade": complexidade,
            "andar": andar,
            "mesmo_andar": mesmo_andar,
            "funcao_compativel": _cargo_compativel(cargo.lower(), categoria),
            "turno_compativel": _turno_compativel(turno_col, hora_ref),
            "tier_adequado": _tier_adequado(complexidade) in (None, _tier_cargo(cargo.lower())),
        }

    # -999 é o sentinel exclusivo de "indisponível" (retornado por calcular_score quando
    # disponivel=False). Não usar o valor do score aqui: com carga acumulada sem teto ao
    # longo de um mês inteiro de preventivas, o score de alguém disponível também pode
    # cair abaixo de -999 — usar isso como filtro excluía gente apta por engano.
    disponiveis = {n: s for n, s in scores.items() if s["disponivel"]}
    if not disponiveis:
        return None, None, scores

    # Balanceamento nunca pode fazer alguém tecnicamente inadequado ganhar de alguém
    # qualificado. Sem isso, penalidade de carga sem teto podia empatar (ou até
    # inverter) o score de um técnico já muito utilizado com o de alguém sem cargo
    # compatível nenhum mas que nunca foi escalado (carga sempre 0) — confirmado com
    # dado real: um gestor administrativo virou "empatado" com eletricistas/técnicos
    # disponíveis numa ronda, e o desempate por menor carga escolheu o gestor.
    # Restringe ao subconjunto compatível quando ele existir; só usa o resto se
    # ninguém tecnicamente apto estiver disponível (prefere indicar alguém a nada).
    compativeis = {n: s for n, s in disponiveis.items() if s["funcao_compativel"]}
    if compativeis:
        disponiveis = compativeis

    # Mesmo raciocínio, agora pro turno: sem isso, a penalidade de carga acumulada
    # (sem teto) podia fazer alguém do turno errado "ganhar" de alguém do turno certo
    # que ainda estava disponível naquele dia — confirmado com dado real na HETRIN:
    # plano "COLETA DIÁRIA MEDIDOR - NOTURNO - N1", um eletricista noturno realmente
    # escalado pra aquele dia perdia pra um diurno assim que sua própria carga
    # acumulada (de ser repetidamente o único noturno apto) alcançava o score de um
    # diurno "fresco". Restringe ao subconjunto de turno certo quando ele existir;
    # só usa o resto se ninguém do turno certo estiver disponível (mesma filosofia
    # de preferir indicar alguém a nada).
    if exigir_turno:
        turno_compat = {n: s for n, s in disponiveis.items() if s["turno_compativel"]}
        if turno_compat:
            disponiveis = turno_compat

    # Complexidade adequada ao cargo (auxiliares em Baixa, técnicos em Alta — pedido
    # da supervisão). Mesmo raciocínio de novo: SEM esse gate, era só bônus de score
    # (SCORE_COMPLEXIDADE_ADEQUADA), e a penalidade de carga/carga_alta acumulada (sem
    # teto) podia superar esse bônus ao longo do mês — confirmado com dado real (HMB,
    # setembro/2026 inteiro): 311 ocorrências de Alta complexidade acabaram indo pra
    # um auxiliar, o oposto do pedido, só porque o técnico "certo" já tinha acumulado
    # muita carga_alta. Restringe ao subconjunto de tier adequado quando ele existir
    # (Média não tem tier preferencial — nunca restringe); só usa o resto se ninguém
    # do tier certo estiver disponível (mesma filosofia de preferir indicar alguém a
    # nada). O bônus de score (SCORE_COMPLEXIDADE_ADEQUADA) continua existindo além
    # deste gate — ele só deixa de ser a única linha de defesa.
    tier_ok = {n: s for n, s in disponiveis.items() if s["tier_adequado"]}
    if tier_ok:
        disponiveis = tier_ok

    # Escala nomeada (ex: coleta diária de medidor/hidrômetro na HETRIN — nomes
    # específicos definidos pela supervisão, não um cargo genérico). Vem DEPOIS do
    # turno de propósito: o gate de turno já garante que só sobra gente do turno
    # certo naquele momento; a escala nomeada então só escolhe entre esses. Se viesse
    # ANTES do turno, um nome certo mas turno errado (ex: a pessoa nomeada pro turno
    # noturno está bloqueada, e a única alternativa nomeada pra aquela paridade é
    # diurna) reduziria o pool a essa única pessoa ANTES do turno rodar — e como o
    # gate de turno também é soft (nunca esvazia sozinho), ele ficaria impotente:
    # veria um pool de 1 pessoa de turno errado, tentaria restringir, o resultado
    # ficaria vazio, e recuaria mantendo a pessoa errada. Confirmado com dado real:
    # Wellington de Souza Brito (Noturno, Ímpar) está bloqueado (NR-10 pendente); nos
    # dias em que ele seria o nomeado, a ordem antiga (nomes antes de turno) forçava
    # Jussara da Conceição Cruz (Diurno, também Ímpar) pra dentro de ocorrências
    # noturnas. Turno primeiro corrige isso: sem Wellington disponível, o pool já
    # filtrado por turno simplesmente não tem ninguém nomeado dentro dele, e o gate de
    # nomes recua (mesma filosofia soft), deixando o motor recomendar o melhor
    # candidato noturno genérico — nunca um nome certo no turno errado.
    if nomes_permitidos is not None:
        nomeados = {n: s for n, s in disponiveis.items() if n in nomes_permitidos}
        if nomeados:
            disponiveis = nomeados

    ordenados = sorted(
        disponiveis,
        key=lambda n: (disponiveis[n]["score"], -disponiveis[n]["carga"]),
        reverse=True,
    )
    principal = {"nome": ordenados[0], **disponiveis[ordenados[0]]}
    apoio = {"nome": ordenados[1], **disponiveis[ordenados[1]]} if len(ordenados) > 1 else None
    return principal, apoio, scores


def extrair_ativo(detalhe) -> str:
    if not detalhe:
        return ""
    equip = detalhe.get("equipamento") or {}
    nome = (equip.get("nome") or "").strip()
    if nome:
        return nome
    itens = detalhe.get("itens") or {}
    lista = itens.get("itens", []) or itens.get("equipamentos", [])
    if lista:
        e = (lista[0] if isinstance(lista[0], dict) else {}).get("equipamento") or {}
        return (e.get("nome") or "").strip()
    return ""

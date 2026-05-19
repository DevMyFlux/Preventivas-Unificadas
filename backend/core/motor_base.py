"""
Motor de Decisão — lógica de scoring compartilhada entre todas as unidades.
Cada unidade implementa sua própria função `esta_disponivel` e `carregar_colaboradores`.
"""

# ── Pesos e constantes ────────────────────────────────────────────────────────
SCORE_FUNCAO_COMPATIVEL = 100
SCORE_FUNCAO_SECUNDARIA = 50
SCORE_TURNO_CORRETO = 50
SCORE_EXP_ATIVO = 20
SCORE_EXP_TIPO = 10
SCORE_CRITICIDADE = 30
PENALIDADE_CARGA = 10

# ── Keywords por categoria ────────────────────────────────────────────────────
_KW_REFRIG = [
    "ar condicionado", "ar-condicionado", "fancoil", "fan coil", "chiller",
    "split", "refrigeração", "climatização", "exaustor",
]
_KW_ELETRICA = [
    "energia elétrica", "régua elétrica", "régua de energia", "quadro elétric",
    "elétrico", "tomada", "disjuntor", "iluminação", "subestação", "média tensão",
    "ccm", "cco", "qgbt", "eletroduto", "cabo elétrico", "nobreak", "ups",
    "baixa tensão", "instalação elétric", "comando", "painel elétric",
]
_KW_HIDRO = [
    "hidrômetro", "hidráulico", "reservatório", "esgoto", "bomba de água",
    "vaso sanitário", "caixa d'água", "caixa dagua", "encanamento",
    "calefação", "hidrante",
]
_KW_INSPECAO = ["rotina", "inspeção", "ronda", "pm ", "preventiva"]

SETORES_CRITICOS = [
    "centro cirúrgico", "sala cirurg", "bloco cirurg", "bloco 4",
    "uti", "uco", "cti", "ccu", "neonatal", "unidade de terapia intensiva",
]

# ── Mapa cargo → categoria compatível ────────────────────────────────────────
_CARGO_ELETRICA = ["eletricista", "elétric", "técnico elétric"]
_CARGO_REFRIG = ["refrigeração", "técnico em refrig", "climatização"]
_CARGO_HIDRO = ["hidráulico", "encanador"]
_CARGO_AUXILIAR = ["auxiliar de manutenção"]
_CARGO_TECNICO = ["técnico", "eletricista", "mecânico", "oficial", "supervisor"]


def _e_auxiliar_especializado(cargo_l: str) -> bool:
    if not any(k in cargo_l for k in _CARGO_AUXILIAR):
        return False
    return any(e in cargo_l for e in ["elétric", "hidráulic", "refriger", "mecân"])


def classificar_categoria(tipo_os: str, setor: str, ativo: str) -> str:
    texto = (tipo_os + " " + setor + " " + ativo).lower()
    if any(k in texto for k in _KW_REFRIG):
        return "Refrigeração"
    if any(k in texto for k in _KW_ELETRICA):
        return "Elétrica"
    if any(k in texto for k in _KW_HIDRO):
        return "Hidráulico"
    if any(k in texto for k in _KW_INSPECAO):
        return "Inspeção"
    return "Geral"


def is_critico(setor: str) -> bool:
    s = setor.lower()
    return any(k in s for k in SETORES_CRITICOS)


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
) -> int:
    if not disponivel:
        return -999

    cargo_l = cargo.lower()
    score = _score_funcao(cargo_l, categoria)

    turno_l = turno_collab.strip().lower()
    if turno_l == "diurno" and 7 <= hora_os < 19:
        score += SCORE_TURNO_CORRETO
    elif turno_l == "noturno" and (hora_os >= 19 or hora_os < 7):
        score += SCORE_TURNO_CORRETO

    score += min(exp_ativo * SCORE_EXP_ATIVO, 60)
    score += min(exp_tipo * SCORE_EXP_TIPO, 30)

    if is_critico(setor):
        score += SCORE_CRITICIDADE

    score -= carga_at * PENALIDADE_CARGA
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
):
    """
    Calcula o responsável recomendado para uma tarefa.

    `esta_disponivel_fn` deve ser uma função(row, data_ref) -> bool.
    Se None, usa disponibilidade sempre True (fallback).
    """
    if colaboradores is None or colaboradores.empty:
        return None, None, {}

    if esta_disponivel_fn is None:
        esta_disponivel_fn = lambda row, data: True

    categoria = classificar_categoria(tipo, setor, ativo)
    scores = {}

    for _, row in colaboradores.iterrows():
        nome = row["funcionario"]
        cargo = str(row.get("cargo", ""))
        turno_col = str(row.get("turno", ""))
        regime = str(row.get("regime", ""))
        disp = esta_disponivel_fn(row, data_ref)
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
        }

    disponiveis = {n: s for n, s in scores.items() if s["disponivel"] and s["score"] > -999}
    if not disponiveis:
        return None, None, scores

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

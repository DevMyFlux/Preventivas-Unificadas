"""
Planejamento de ocorrências de preventivas — compartilhado entre todas as unidades.

Antes duplicado (com pequenas divergências de risco) em cada `units/*/routes.py`.
Unificado aqui porque a correção de paridade PAR/ÍMPAR precisa valer igual nas duas
unidades, e manter a mesma lógica em dois lugares é como esse tipo de regra se perde.
"""
import re
import unicodedata
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

_RE_IMPAR = re.compile(r"\bIMPAR\b")
_RE_PAR = re.compile(r"\bPAR\b")

_SITUACOES_EM_ABERTO = frozenset({1, 2})  # Aberta, Em Andamento


def _remover_acentos(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def detectar_paridade(nome_plano: str) -> str | None:
    """Detecta se um plano é explicitamente PAR ou ÍMPAR pelo nome/descrição.

    Usa word-boundary para não confundir "PAR" dentro de "PARTIDA" (ex: "TESTE DE
    PARTIDA DOS GRUPOS GERADORES" não é um plano de paridade) nem dentro de "ÍMPAR"
    (que contém "PAR" como substring — por isso ÍMPAR é checado primeiro, embora o
    word-boundary já evite essa confusão sozinho). Acento/caixa são normalizados.
    """
    if not nome_plano:
        return None
    normalizado = _remover_acentos(nome_plano).upper()
    if _RE_IMPAR.search(normalizado):
        return "IMPAR"
    if _RE_PAR.search(normalizado):
        return "PAR"
    return None


def _paridade_ok(d: date, paridade: str | None) -> bool:
    if paridade is None:
        return True
    return (d.day % 2 == 0) if paridade == "PAR" else (d.day % 2 == 1)


def _corrigir_paridade(d: date, paridade: str | None) -> date:
    """Se a data não bate com a paridade exigida pelo plano, avança até bater — nunca
    recua, para não reagendar uma preventiva para o passado. Cobre tanto uma data de
    origem já desalinhada (dataProximaPreventiva vindo torta do Neovero) quanto o
    desalinhamento que a própria expansão pode introduzir ao cruzar um mês de duração
    ímpar (31 dias): virar de 31 (ímpar) para 1 (ímpar) não muda a paridade do dia, então
    uma única correção de +1 dia não é suficiente nesse caso — precisa repetir."""
    passos = 0
    while not _paridade_ok(d, paridade) and passos < 3:
        d = d + timedelta(days=1)
        passos += 1
    return d


def expandir_ocorrencias(
    dt_base: date,
    periodicidade: int,
    unidade: str,
    d_ini: date,
    d_fim: date,
    paridade: str | None = None,
) -> list:
    """Gera todas as ocorrências em [d_ini, d_fim] a partir de dt_base com a periodicidade
    do plano. Segue somente para frente (como o Neovero): avança de dt_base até entrar no
    período, então coleta todas as ocorrências até d_fim.

    Planos sem periodicidade definida (periodicidade=0) não recorrem — geram no máximo uma
    ocorrência, na própria dataProximaPreventiva.

    Se `paridade` for "PAR" ou "IMPAR", toda ocorrência gerada (a de origem e cada passo
    seguinte) é validada e corrigida como pós-condição — nunca uma data de paridade errada
    sai desta função, mesmo que a origem já estivesse errada ou a expansão desalinhe no
    meio do caminho.
    """
    if not periodicidade:
        dt_corrigida = _corrigir_paridade(dt_base, paridade)
        return [dt_corrigida] if d_ini <= dt_corrigida <= d_fim else []

    _MAP = {
        "D": lambda n: relativedelta(days=n),
        "S": lambda n: relativedelta(weeks=n),
        "M": lambda n: relativedelta(months=n),
        "A": lambda n: relativedelta(years=n),
    }
    try:
        delta = _MAP.get(unidade, lambda n: relativedelta(days=n))(periodicidade)
    except Exception:
        delta = timedelta(days=periodicidade)

    dt = _corrigir_paridade(dt_base, paridade)

    if dt > d_fim:
        return []

    passos = 0
    while dt < d_ini and passos < 500:
        dt = _corrigir_paridade(dt + delta, paridade)
        passos += 1

    datas = []
    passos = 0
    while dt <= d_fim and passos < 500:
        datas.append(dt)
        dt = _corrigir_paridade(dt + delta, paridade)
        passos += 1

    return datas


def descartar_ocorrencia_em_aberto(datas: list, os_vinculada: dict | None) -> list:
    """Remove a primeira ocorrência da lista quando o item já tem uma OS Aberta ou
    Em Andamento vinculada.

    Essa primeira ocorrência é justamente a que já virou a OS em aberto — ela já
    existe como ordem de serviço real, não é mais "planejada". Contá-la de novo na
    lista de preventivas previstas duplica a mesma manutenção (uma vez como OS
    aberta, outra como ocorrência futura). Confirmado com dados reais da Neovero:
    plano PM RONDA PERIÓDICA - FANCOILS HIDRÔNICOS, 14 itens todos com OS aberta —
    sem este descarte a expansão matemática gerava 28 ocorrências (2 por item);
    com o descarte, bate exatamente com as 14 que a Neovero reporta.
    """
    situacao = (os_vinculada or {}).get("situacao")
    if situacao in _SITUACOES_EM_ABERTO and datas:
        return datas[1:]
    return datas

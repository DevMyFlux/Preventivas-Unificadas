"""
Regras nominais de atribuição da HMB (pedido da supervisão — feedback de out/2026).

  5.4  Rondas diárias — responsável por TURNO × TIPO DE DIA (dia de execução):

        Turno    Tipo de dia   Responsável
        Diurno   Ímpar         Iranildo
        Noturno  Ímpar         Diego H
        Diurno   Par           Michael
        Noturno  Par           Diego H

  5.5  Oficina de ar comprimido e vácuo (só turno diurno foi especificado):

        Diurno   Par           Douglas Rodrigues e Gustavo Rafael
        Diurno   Ímpar         Israel

Os nomes são APELIDOS e são validados contra o cadastro ativo da unidade (ver
core/regras/atribuicao.py). Na escala de out/2026 isso produz: "Iranildo", "Israel",
"Douglas Rodrigues" e "Gustavo Rafael" → inequívocos; "Michael" → 2 colaboradores
(Michael de Campos Eguez e Michael Kelvin de Abreu Moraes, ambos diurno par) e "Diego H" →
nenhum com essa inicial (existem Diego Reimberg e Diego Ferreira da Cunha). Esses dois
ficam PENDENTES até alguém confirmar o nome na tela de regras — não há escolha arbitrária.
"""
import re

from core.regras.atribuicao import (
    IMPAR, PAR, TURNO_DIURNO, TURNO_NOTURNO, ContextoOcorrencia, LinhaRegra, RegraNominal,
)
from core.regras.nomes import sem_acento

# tipoManutencao.id = 8 é "RONDA" na HMB (confirmado nas OS reais de out/2026).
TIPO_RONDA_IDS = frozenset({8})

_RE_RONDA = re.compile(r"\bRONDA\b")



def _eh_ronda_diaria(ctx: ContextoOcorrencia) -> bool:
    diaria = ctx.periodicidade == 1 and ctx.unidade_tempo == "D"
    if not diaria:
        return False
    return ctx.tipo_id in TIPO_RONDA_IDS or bool(_RE_RONDA.search(sem_acento(ctx.descricao).upper()))


def _eh_oficina_ar_comprimido_vacuo(ctx: ContextoOcorrencia) -> bool:
    oficina = sem_acento(ctx.oficina).upper()
    return "AR COMPRIMIDO" in oficina and "VACUO" in oficina


RONDA_DIARIA = RegraNominal(
    id="ronda_diaria",
    titulo="Rondas diárias",
    descricao="Responsável pela ronda diária conforme turno e tipo de dia (par/ímpar) da data de execução.",
    linhas=(
        LinhaRegra(TURNO_DIURNO, IMPAR, ("Iranildo",)),
        LinhaRegra(TURNO_NOTURNO, IMPAR, ("Diego H",)),
        LinhaRegra(TURNO_DIURNO, PAR, ("Michael",)),
        LinhaRegra(TURNO_NOTURNO, PAR, ("Diego H",)),
    ),
    aplica=_eh_ronda_diaria,
    turno_padrao=TURNO_DIURNO,
)

OFICINA_AR_COMPRIMIDO_VACUO = RegraNominal(
    id="oficina_ar_comprimido_vacuo",
    titulo="Oficina de ar comprimido e vácuo",
    descricao="Responsáveis pelos planos da oficina 'Ar Comprimido e Vácuo' (turno diurno) conforme tipo de dia.",
    linhas=(
        LinhaRegra(TURNO_DIURNO, PAR, ("Douglas Rodrigues", "Gustavo Rafael")),
        LinhaRegra(TURNO_DIURNO, IMPAR, ("Israel",)),
    ),
    aplica=_eh_oficina_ar_comprimido_vacuo,
    turno_padrao=TURNO_DIURNO,
)

# A ordem importa: a ronda diária é avaliada antes (um plano de ronda nunca é da oficina AC/V).
REGRAS = [RONDA_DIARIA, OFICINA_AR_COMPRIMIDO_VACUO]

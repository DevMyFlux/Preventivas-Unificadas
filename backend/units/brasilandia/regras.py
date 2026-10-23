"""
Regras de atribuição da HMB (pedido da supervisão — feedback de out/2026).

  5.4  Rondas diárias — **AUTOMÁTICAS no Neovero** (retorno dos gestores, 15/10/2026): cada ronda diária já nasce com um dos
       4 responsáveis de equipe — ELÉTRICA-DIURNO, ELÉTRICA-NOTURNO, CLIMATIZAÇÃO-DIURNO, CLIMATIZAÇÃO-NOTURNO — e "os
       responsáveis já puxam diretamente do Neovero". Por isso:
         * essas 4 equipes valem como responsável correto das rondas diárias (não são "Genérico" nem vão para a Revisão);
         * o sistema NÃO recomenda executante para rondas diárias;
         * a antiga tabela nominal (abaixo, `RONDA_DIARIA`) está DESATIVADA — fora de `REGRAS` — e some a pendência de
           "Michael" e "Diego H". Fica no código só como referência/histórico e para reativação, se um dia for pedido.

     Tabela antiga (desativada): responsável por TURNO × TIPO DE DIA (dia de execução):

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
(Só valeria se a tabela das rondas fosse reativada.)
"""
import re

from core.regras.atribuicao import (
    IMPAR, PAR, TURNO_DIURNO, TURNO_NOTURNO, ContextoOcorrencia, LinhaRegra, RegraNominal,
)
from core.regras.nomes import sem_acento

# tipoManutencao.id = 8 é "RONDA" na HMB (confirmado nas OS reais de out/2026).
TIPO_RONDA_IDS = frozenset({8})

_RE_RONDA = re.compile(r"\bRONDA\b")



def _ronda_diaria(descricao: str, tipo_id, periodicidade, unidade_tempo) -> bool:
    if not (periodicidade == 1 and unidade_tempo == "D"):
        return False
    return tipo_id in TIPO_RONDA_IDS or bool(_RE_RONDA.search(sem_acento(descricao or "").upper()))


def _eh_ronda_diaria(ctx: ContextoOcorrencia) -> bool:
    return _ronda_diaria(ctx.descricao, ctx.tipo_id, ctx.periodicidade, ctx.unidade_tempo)


# Responsáveis de EQUIPE que o Neovero atribui sozinho às rondas diárias (nomes normalizados: minúsculas, sem acento/pontuação).
RESPONSAVEIS_EQUIPE = frozenset({"eletrica diurno", "eletrica noturno", "climatizacao diurno", "climatizacao noturno"})


def plano_automatico(descricao: str, oficina: str, tipo_id, periodicidade, unidade_tempo) -> bool:
    """Plano cujo responsável o Neovero define sozinho (rondas diárias): o sistema não recomenda executante."""
    return _ronda_diaria(descricao, tipo_id, periodicidade, unidade_tempo)


# Distribuição das rondas diárias entre as equipes (tabela enviada pelos usuários, out/2026): TODAS as rondas de CLIMATIZAÇÃO
# ficam com a equipe CLIMATIZAÇÃO-NOTURNO (alivia o diurno, que tem um técnico só) e as rondas de ELÉTRICA/QGBT seguem o turno do
# nome do plano (DIURNO por padrão; "NOTURNO"/"NOTUR" no nome → noturno). Só vale para rondas diárias; as demais oficinas ficam
# como o Neovero definiu.
_RE_NOTURNO = re.compile(r"\bNOTUR")

EQUIPES_ROTULO = {
    "eletrica diurno": "ELÉTRICA - DIURNO", "eletrica noturno": "ELÉTRICA - NOTURNO",
    "climatizacao diurno": "CLIMATIZAÇÃO - DIURNO", "climatizacao noturno": "CLIMATIZAÇÃO - NOTURNO",
}


def equipe_da_ronda(descricao: str, oficina: str, tipo_id, periodicidade, unidade_tempo) -> str | None:
    """Equipe (nome normalizado) que deve responder pela ronda diária segundo a distribuição definida; None = sem regra."""
    if not _ronda_diaria(descricao, tipo_id, periodicidade, unidade_tempo):
        return None
    of = sem_acento(oficina or "").upper()
    desc = sem_acento(descricao or "").upper()
    if "CLIMATIZACAO" in of:
        return "climatizacao noturno"
    if "ELETRICA" in of:
        return "eletrica noturno" if _RE_NOTURNO.search(desc) else "eletrica diurno"
    return None


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

# Rondas diárias: AUTOMÁTICAS no Neovero (ver topo do arquivo) — `RONDA_DIARIA` fica fora da lista de regras ativas.
REGRAS = [OFICINA_AR_COMPRIMIDO_VACUO]
REGRAS_DESATIVADAS = [RONDA_DIARIA]

"""
Regras nominais de atribuição da HETRIN (pedido da supervisão — correção da distribuição, out/2026).

  Fancoletes — direcionadas aos técnicos de climatização, por tipo de dia (o plano não declara turno):

        Dia ímpar   Wagner Alves Cardozo        (técnico diurno)
        Dia par     Eduardo Oliveira da Cunha   (técnico noturno)

  Rondas/planos de motobombas — direcionados a eletricistas, por TURNO × TIPO DE DIA:

        Turno    Tipo de dia   Responsável
        Diurno   Ímpar         Luís Alberto
        Diurno   Par           Salem Abreu
        Noturno  Ímpar         Lúcio Jorge e Valdene Ferreira
        Noturno  Par           Maikon Douglas

Os nomes são validados contra o cadastro ATIVO da unidade (ver core/regras/atribuicao.py): apelido ambíguo ou
ausente deixa a linha pendente (confirmação humana na tela de Regras, só administradores) — nunca se escolhe
um homônimo ao acaso. Combinação não especificada → a regra não se aplica e vale o comportamento geral
(inclusive a regra de CARGO de `regras_cargo.py`).

Estas regras valem SOMENTE para a HETRIN; a HMB tem as suas (units/brasilandia/regras.py).
"""
import re

from core.regras.atribuicao import (
    IMPAR, PAR, TURNO_DIURNO, TURNO_NOTURNO, ContextoOcorrencia, LinhaRegra, RegraNominal,
)
from core.regras.nomes import sem_acento

_RE_FANCOLETE = re.compile(r"\bFANCOLETES?\b")
_RE_MOTOBOMBAS = re.compile(r"\bMOTOBOMBAS?\b")


def _eh_fancolete(ctx: ContextoOcorrencia) -> bool:
    return bool(_RE_FANCOLETE.search(sem_acento(ctx.descricao).upper()))


def _eh_motobomba(ctx: ContextoOcorrencia) -> bool:
    return bool(_RE_MOTOBOMBAS.search(sem_acento(ctx.descricao).upper()))


FANCOLETES = RegraNominal(
    id="fancoletes",
    titulo="Fancoletes",
    descricao="Técnicos de climatização por tipo de dia: ímpar → Wagner (diurno); par → Eduardo (noturno).",
    linhas=(
        LinhaRegra(TURNO_DIURNO, IMPAR, ("Wagner Alves Cardozo",)),
        LinhaRegra(TURNO_DIURNO, PAR, ("Eduardo Oliveira da Cunha",)),
    ),
    aplica=_eh_fancolete,
    turno_padrao=TURNO_DIURNO,
)

MOTOBOMBAS = RegraNominal(
    id="motobombas",
    titulo="Motobombas",
    descricao="Eletricistas por turno e tipo de dia (par/ímpar do dia de execução).",
    linhas=(
        LinhaRegra(TURNO_DIURNO, IMPAR, ("Luís Alberto",)),
        LinhaRegra(TURNO_DIURNO, PAR, ("Salem Abreu",)),
        LinhaRegra(TURNO_NOTURNO, IMPAR, ("Lúcio Jorge", "Valdene Ferreira")),
        LinhaRegra(TURNO_NOTURNO, PAR, ("Maikon Douglas",)),
    ),
    aplica=_eh_motobomba,
    turno_padrao=TURNO_DIURNO,
)

REGRAS = [FANCOLETES, MOTOBOMBAS]

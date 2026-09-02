"""
Testes de detectar_turno() (core/planejamento.py) e do bug real que ela corrige.

Bug reportado pelos responsáveis da HETRIN: em 02/09/2026, o plano "COLETA DIÁRIA
MEDIDOR - NOTURNO - N2" recomendou Salem Abreu da Silva Junior, um eletricista só
diurno. Causa raiz: preventivas futuras (sem OS real ainda, sem dataHoraAbertura pra
ler a hora de verdade) sempre eram avaliadas com a hora-padrão (8h) — dentro da
janela diurna (7h-19h) e fora da janela noturna (19h-7h) de calcular_score(). Isso
dava o bônus de turno (+50) pra qualquer colaborador diurno disponível e nunca pra
um noturno, não importa o que o nome do próprio plano dissesse.
"""
import pytest

from core.motor_base import calcular_score, SCORE_TURNO_CORRETO
from core.planejamento import detectar_turno


# ── detectar_turno ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("nome, esperado", [
    ("COLETA DIÁRIA MEDIDOR - NOTURNO - N2", "Noturno"),
    ("COLETA DIÁRIA MEDIDOR - DIURNO - D1", "Diurno"),
    ("COLETA DIÁRIA HIDRÔMETRO -DIURNO - D2", "Diurno"),
    ("PM MENSAL - FANCOIL - HETRIN - NOTURNO", "Noturno"),
    ("PM MENSAL – SPLIT - NOTURNO", "Noturno"),
    ("PM - RONDA SEMANAL - MOTOBOMBAS - HETRIN - DIURNO", "Diurno"),
    ("pm mensal - split - diurno", "Diurno"),  # minúsculo
])
def test_detectar_turno_casos_reais(nome, esperado):
    assert detectar_turno(nome) == esperado


@pytest.mark.parametrize("nome", [
    "PM MENSAL - INSPEÇÃO NOBREAKS",
    "PM - LIMPEZA GERAL - SALA DE BOMBAS DOS CHILLERS",
    "PM RONDA PERIÓDICA - RÉGUAS DE GASES MEDICINAIS",
])
def test_detectar_turno_sem_falso_positivo(nome):
    assert detectar_turno(nome) is None


def test_detectar_turno_nome_vazio():
    assert detectar_turno("") is None
    assert detectar_turno(None) is None


# ── NOITE/DIA — bug real confirmado por investigação (set/2026) ─────────────────
# detectar_turno() só reconhecia NOTURNO/DIURNO — mas ~15% das ocorrências de um mês
# inteiro (352 de 2403, Hetrin/Set-2026) vêm de planos nomeados com NOITE/DIA, não
# NOTURNO/DIURNO (ex: "PM - RONDA ILUMINAÇÃO/TOMADAS - NOITE - N1"), e por isso nunca
# recebiam o filtro/bônus de turno correto — casos reais confirmados: Jussara da
# Conceição Cruz (Aux. Eletricista, Diurno) recomendada 8x pra ronda NOTURNA de
# Iluminação/Tomadas no lugar do eletricista noturno de plantão real.

@pytest.mark.parametrize("nome, esperado", [
    ("PM - RONDA ILUMINAÇÃO/TOMADAS - NOITE - N1", "Noturno"),
    ("PM - RONDA ILUMINAÇÃO/TOMADAS - DIA - D1", "Diurno"),
    ("LIMPEZA QUINZENAL - EXAUSTORES/DIFUSORES - NOITE - N2", "Noturno"),
    ("PM - MENSAL MOTOBOMBAS NOITE - N1", "Noturno"),
    ("PM - LIMPEZA FANCOILS BL1 - DIA 01/02", "Diurno"),
    ("pm - ronda - noite", "Noturno"),  # minúsculo
])
def test_detectar_turno_reconhece_noite_dia(nome, esperado):
    assert detectar_turno(nome) == esperado


@pytest.mark.parametrize("nome", [
    "COLETA DIÁRIA HIDRÔMETRO",  # sem sufixo de turno — "DIÁRIA" não pode virar "DIA"
    "PM RONDA DIÁRIO - SISTEMA DE AR COMPRIMIDO",
])
def test_detectar_turno_dia_nao_confunde_com_diaria(nome):
    """\\bDIA\\b não deve casar dentro de 'DIÁRIA'/'DIÁRIO' (word-boundary não bate no
    meio de outra palavra, mesmo depois de normalizar acento: 'DIÁRIA' -> 'DIARIA',
    onde 'DIA' aparece seguido de 'RIA', sem boundary)."""
    assert detectar_turno(nome) is None


# ── Regressão: hora de referência derivada do turno do plano ────────────────────

def _score_diurno_vs_noturno(hora_ref: int) -> tuple[int, int]:
    """Mesmo colaborador hipotético em dois turnos, único cargo compatível (Eletricista),
    tudo mais igual (sem experiência, sem carga, setor não crítico) — a única diferença
    possível de score é o bônus de turno."""
    score_diurno = calcular_score(
        cargo="Eletricista", categoria="Elétrica", turno_collab="Diurno", hora_os=hora_ref,
        setor="ÁREA EXTERNA", exp_tipo=0, exp_ativo=0, carga_at=0, disponivel=True,
    )
    score_noturno = calcular_score(
        cargo="Eletricista", categoria="Elétrica", turno_collab="Noturno", hora_os=hora_ref,
        setor="ÁREA EXTERNA", exp_tipo=0, exp_ativo=0, carga_at=0, disponivel=True,
    )
    return score_diurno, score_noturno


def test_hora_padrao_favorecia_diurno_mesmo_em_plano_noturno():
    """Documenta o bug: com a hora-padrão antiga (8h) usada pra QUALQUER preventiva,
    um colaborador diurno sempre levava o bônus de turno, mesmo pra um plano noturno."""
    score_diurno, score_noturno = _score_diurno_vs_noturno(hora_ref=8)
    assert score_diurno == score_noturno + SCORE_TURNO_CORRETO


def test_hora_derivada_do_plano_noturno_favorece_colaborador_noturno():
    """Com a hora de referência derivada de detectar_turno() (20h pra plano
    "...NOTURNO..."), o bônus de turno passa a ir pra quem realmente é noturno."""
    hora_ref = 20 if detectar_turno("COLETA DIÁRIA MEDIDOR - NOTURNO - N2") == "Noturno" else 8
    assert hora_ref == 20
    score_diurno, score_noturno = _score_diurno_vs_noturno(hora_ref=hora_ref)
    assert score_noturno == score_diurno + SCORE_TURNO_CORRETO


def test_hora_derivada_do_plano_diurno_continua_favorecendo_diurno():
    hora_ref = 20 if detectar_turno("COLETA DIÁRIA MEDIDOR - DIURNO - D1") == "Noturno" else 8
    assert hora_ref == 8
    score_diurno, score_noturno = _score_diurno_vs_noturno(hora_ref=hora_ref)
    assert score_diurno == score_noturno + SCORE_TURNO_CORRETO


def test_plano_sem_turno_no_nome_mantem_comportamento_padrao():
    """Plano sem "DIURNO"/"NOTURNO" no nome não tem como saber o turno certo — mantém
    a hora-padrão de 8h (comportamento pré-existente, não regride pra esses planos)."""
    hora_ref = 20 if detectar_turno("PM MENSAL - INSPEÇÃO NOBREAKS") == "Noturno" else 8
    assert hora_ref == 8

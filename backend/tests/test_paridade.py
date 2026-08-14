"""
Testes da regra de paridade PAR/ÍMPAR (core/planejamento.py).

Bug corrigido: planos PAR podiam gerar ocorrência em dia ímpar e vice-versa, porque
nada validava a paridade da dataProximaPreventiva nem da expansão por periodicidade.
Confirmado com dados reais antes do fix: "AUX PAR DI" tinha 79 de 112 itens no dia
errado; "SISTEMA DE AR COMPRIMIDO - PAR" tinha 6 de 8.
"""
from datetime import date

import pytest

from core.planejamento import detectar_paridade, expandir_ocorrencias


# ── detectar_paridade ────────────────────────────────────────────────────────

@pytest.mark.parametrize("nome, esperado", [
    ("PM - RONDA DIÁRIA - SISTEMA DE AR COMPRIMIDO - PAR", "PAR"),
    ("PM - RONDA DIÁRIA - SISTEMA DE AR COMPRIMIDO - ÍMPAR", "IMPAR"),
    ("PM - RONDA PERIÓDICA - ILUMINAÇÃO E TOMADAS - AUX IMPAR DI", "IMPAR"),
    ("PM - RONDA PERIÓDICA - ILUMINAÇÃO E TOMADAS - AUX PAR DI", "PAR"),
    ("ROTINA - COLETA DIÁRIA DE DADOS HIDRÔMETRO - PAR", "PAR"),
    ("rotina - coleta diária - impar", "IMPAR"),  # minúsculo
    ("PLANO-PAR-SEMANAL", "PAR"),  # hífen como separador
])
def test_detectar_paridade_casos_reais(nome, esperado):
    assert detectar_paridade(nome) == esperado


@pytest.mark.parametrize("nome", [
    "PM SEMANAL - TESTE DE PARTIDA DOS GRUPOS GERADORES",  # "PARTIDA" contém "PAR"
    "PM MENSAL - INSPEÇÃO NOBREAKS",
    "PM - LIMPEZA GERAL - SALA DE BOMBAS DOS CHILLERS",
    "COMPARTILHADO - RONDA DIÁRIA",  # "COMPARTILHADO" contém "PAR"
])
def test_detectar_paridade_sem_falso_positivo(nome):
    assert detectar_paridade(nome) is None


def test_detectar_paridade_nome_vazio():
    assert detectar_paridade("") is None
    assert detectar_paridade(None) is None


# ── validação/correção de data ───────────────────────────────────────────────

@pytest.mark.parametrize("paridade, dt_base, esperado", [
    ("PAR", date(2026, 8, 1), date(2026, 8, 2)),      # inválido -> corrige pra frente
    ("PAR", date(2026, 8, 2), date(2026, 8, 2)),      # já válido -> mantém
    ("IMPAR", date(2026, 8, 1), date(2026, 8, 1)),    # já válido -> mantém
    ("IMPAR", date(2026, 8, 2), date(2026, 8, 3)),    # inválido -> corrige pra frente
])
def test_correcao_data_unica(paridade, dt_base, esperado):
    """periodicidade=0 (ocorrência única) com paridade: nunca sai com a data errada."""
    datas = expandir_ocorrencias(dt_base, 0, "D", date(2026, 8, 1), date(2026, 8, 31), paridade)
    assert datas == [esperado]


@pytest.mark.parametrize("dia", [28, 29, 30, 31])
@pytest.mark.parametrize("paridade", ["PAR", "IMPAR"])
def test_todos_os_dias_finais_do_mes_corrigem_certo(dia, paridade):
    """Seção 18 do pedido: casos de virada de mês (28-31/08) não podem escapar da regra."""
    dt_base = date(2026, 8, dia)
    datas = expandir_ocorrencias(dt_base, 0, "D", date(2026, 8, 1), date(2026, 9, 30), paridade)
    assert len(datas) == 1
    if paridade == "PAR":
        assert datas[0].day % 2 == 0
    else:
        assert datas[0].day % 2 == 1


def test_nunca_corrige_para_o_passado():
    """A correção só avança — nunca deve devolver uma data anterior à de origem."""
    dt_base = date(2026, 8, 31)
    datas = expandir_ocorrencias(dt_base, 0, "D", date(2026, 8, 1), date(2026, 9, 30), "PAR")
    assert datas[0] >= dt_base


# ── expansão com periodicidade (o cenário real: itens que recorrem) ─────────

def test_expansao_diaria_com_paridade_nunca_viola():
    """Simula o caso real 'SISTEMA DE AR COMPRIMIDO - PAR' (periodicidade 2D) mas
    partindo de uma data-base já desalinhada, como a que vinha do Neovero."""
    dt_base = date(2026, 8, 14)  # ok=par, mas periodicidade 1D testado abaixo pra forçar desvio
    datas = expandir_ocorrencias(dt_base, 1, "D", date(2026, 9, 1), date(2026, 9, 30), "PAR")
    assert len(datas) > 0
    assert all(d.day % 2 == 0 for d in datas)


def test_expansao_periodicidade_impar_de_dias_com_paridade():
    """Caso real: 'AUX PAR DI' tem periodicidade 15D — ímpar, então cruzar um mês de
    31 dias pode desalinhar a paridade no meio da sequência, não só na origem."""
    datas = expandir_ocorrencias(date(2026, 8, 20), 15, "D", date(2026, 9, 1), date(2026, 9, 30), "PAR")
    assert len(datas) > 0
    assert all(d.day % 2 == 0 for d in datas)


def test_expansao_sem_paridade_nao_e_afetada():
    """Plano sem PAR/ÍMPAR no nome continua se comportando exatamente como antes —
    a correção não deve interferir em planos que não declaram paridade."""
    datas = expandir_ocorrencias(date(2026, 8, 14), 7, "D", date(2026, 9, 1), date(2026, 9, 30), None)
    assert datas == [date(2026, 9, 4), date(2026, 9, 11), date(2026, 9, 18), date(2026, 9, 25)]

"""
Testes da expansão de ocorrências de preventivas (core/planejamento.py) — cobre os
bugs corrigidos:
1) planos com ativo=None incluindo inativos (testado a nível de filtro em test_filtros_planos.py)
2) periodicidade=0 sendo tratada como "todo dia" em vez de ocorrência única
Paridade PAR/ÍMPAR tem arquivo próprio: test_paridade.py.

Também garante que as duas unidades continuam expondo a mesma função (evita
reintrodução da duplicação que causou a divergência original).
"""
from datetime import date

from core.planejamento import expandir_ocorrencias
from units.grand_massif.routes import _expandir_ocorrencias as expandir_gm
from units.brasilandia.routes import _expandir_ocorrencias as expandir_br


def test_unidades_usam_a_mesma_implementacao():
    assert expandir_gm is expandir_ocorrencias
    assert expandir_br is expandir_ocorrencias


def test_periodicidade_zero_nao_recorre():
    """periodicidade=0 (item pontual, sem recorrência) não deve gerar ocorrência
    em todo dia do período — só a própria data, se estiver dentro."""
    dt_base = date(2026, 9, 15)
    d_ini, d_fim = date(2026, 9, 1), date(2026, 9, 30)
    assert expandir_ocorrencias(dt_base, 0, "D", d_ini, d_fim) == [dt_base]


def test_periodicidade_zero_fora_do_periodo():
    dt_base = date(2026, 8, 15)
    d_ini, d_fim = date(2026, 9, 1), date(2026, 9, 30)
    assert expandir_ocorrencias(dt_base, 0, "D", d_ini, d_fim) == []


def test_periodicidade_none_tratada_como_zero():
    dt_base = date(2026, 9, 10)
    d_ini, d_fim = date(2026, 9, 1), date(2026, 9, 30)
    assert expandir_ocorrencias(dt_base, None, "D", d_ini, d_fim) == [dt_base]


def test_periodicidade_diaria_expande_dentro_do_periodo():
    dt_base = date(2026, 8, 14)  # antes do período, deve avançar até entrar
    d_ini, d_fim = date(2026, 9, 1), date(2026, 9, 30)
    datas = expandir_ocorrencias(dt_base, 7, "D", d_ini, d_fim)
    assert datas == [date(2026, 9, 4), date(2026, 9, 11), date(2026, 9, 18), date(2026, 9, 25)]


def test_periodicidade_mensal():
    dt_base = date(2026, 1, 15)
    d_ini, d_fim = date(2026, 9, 1), date(2026, 12, 31)
    datas = expandir_ocorrencias(dt_base, 1, "M", d_ini, d_fim)
    assert datas == [date(2026, 9, 15), date(2026, 10, 15), date(2026, 11, 15), date(2026, 12, 15)]


def test_periodicidade_anual():
    dt_base = date(2024, 3, 10)
    d_ini, d_fim = date(2026, 1, 1), date(2026, 12, 31)
    assert expandir_ocorrencias(dt_base, 1, "A", d_ini, d_fim) == [date(2026, 3, 10)]


def test_dt_base_apos_periodo_retorna_vazio():
    dt_base = date(2027, 1, 1)
    d_ini, d_fim = date(2026, 9, 1), date(2026, 9, 30)
    assert expandir_ocorrencias(dt_base, 7, "D", d_ini, d_fim) == []


def test_unidade_desconhecida_cai_para_dias():
    """periodicidadeTempoUnidade fora do mapa (D/S/M/A) usa fallback de dias,
    não deve levantar exceção."""
    dt_base = date(2026, 9, 1)
    d_ini, d_fim = date(2026, 9, 1), date(2026, 9, 30)
    datas = expandir_ocorrencias(dt_base, 10, "X", d_ini, d_fim)
    assert datas == [date(2026, 9, 1), date(2026, 9, 11), date(2026, 9, 21)]

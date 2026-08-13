"""
Testes da expansão de ocorrências de preventivas — cobre os dois bugs corrigidos:
1) planos com ativo=None incluindo inativos (testado a nível de filtro em test_filtros_planos.py)
2) periodicidade=0 sendo tratada como "todo dia" em vez de ocorrência única
"""
from datetime import date

import pytest

from units.grand_massif.routes import _expandir_ocorrencias as expandir_gm
from units.brasilandia.routes import _expandir_ocorrencias as expandir_br

# As duas unidades usam a mesma lógica — testa contra as duas para garantir que
# não divergiram (motivo original da duplicação: cada arquivo tem sua cópia).
IMPLEMENTACOES = [expandir_gm, expandir_br]


@pytest.mark.parametrize("expandir", IMPLEMENTACOES)
def test_periodicidade_zero_nao_recorre(expandir):
    """Bug corrigido: periodicidade=0 (item pontual, sem recorrência) não deve
    gerar ocorrência em todo dia do período — só a própria data, se estiver dentro."""
    dt_base = date(2026, 9, 15)
    d_ini, d_fim = date(2026, 9, 1), date(2026, 9, 30)
    assert expandir(dt_base, 0, "D", d_ini, d_fim) == [dt_base]


@pytest.mark.parametrize("expandir", IMPLEMENTACOES)
def test_periodicidade_zero_fora_do_periodo(expandir):
    dt_base = date(2026, 8, 15)
    d_ini, d_fim = date(2026, 9, 1), date(2026, 9, 30)
    assert expandir(dt_base, 0, "D", d_ini, d_fim) == []


@pytest.mark.parametrize("expandir", IMPLEMENTACOES)
def test_periodicidade_none_tratada_como_zero(expandir):
    dt_base = date(2026, 9, 10)
    d_ini, d_fim = date(2026, 9, 1), date(2026, 9, 30)
    assert expandir(dt_base, None, "D", d_ini, d_fim) == [dt_base]


@pytest.mark.parametrize("expandir", IMPLEMENTACOES)
def test_periodicidade_diaria_expande_dentro_do_periodo(expandir):
    dt_base = date(2026, 8, 14)  # antes do período, deve avançar até entrar
    d_ini, d_fim = date(2026, 9, 1), date(2026, 9, 30)
    datas = expandir(dt_base, 7, "D", d_ini, d_fim)
    assert datas == [date(2026, 9, 4), date(2026, 9, 11), date(2026, 9, 18), date(2026, 9, 25)]


@pytest.mark.parametrize("expandir", IMPLEMENTACOES)
def test_periodicidade_mensal(expandir):
    dt_base = date(2026, 1, 15)
    d_ini, d_fim = date(2026, 9, 1), date(2026, 12, 31)
    datas = expandir(dt_base, 1, "M", d_ini, d_fim)
    assert datas == [date(2026, 9, 15), date(2026, 10, 15), date(2026, 11, 15), date(2026, 12, 15)]


@pytest.mark.parametrize("expandir", IMPLEMENTACOES)
def test_periodicidade_anual(expandir):
    dt_base = date(2024, 3, 10)
    d_ini, d_fim = date(2026, 1, 1), date(2026, 12, 31)
    assert expandir(dt_base, 1, "A", d_ini, d_fim) == [date(2026, 3, 10)]


@pytest.mark.parametrize("expandir", IMPLEMENTACOES)
def test_dt_base_apos_periodo_retorna_vazio(expandir):
    dt_base = date(2027, 1, 1)
    d_ini, d_fim = date(2026, 9, 1), date(2026, 9, 30)
    assert expandir(dt_base, 7, "D", d_ini, d_fim) == []


@pytest.mark.parametrize("expandir", IMPLEMENTACOES)
def test_unidade_desconhecida_cai_para_dias(expandir):
    """periodicidadeTempoUnidade fora do mapa (D/S/M/A) usa fallback de dias,
    não deve levantar exceção."""
    dt_base = date(2026, 9, 1)
    d_ini, d_fim = date(2026, 9, 1), date(2026, 9, 30)
    datas = expandir(dt_base, 10, "X", d_ini, d_fim)
    assert datas == [date(2026, 9, 1), date(2026, 9, 11), date(2026, 9, 21)]

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

from core.planejamento import marcar_ocorrencia_ja_aberta, expandir_ocorrencias
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


class TestMarcarOcorrenciaJaAberta:
    """Cobre o bug encontrado com dados reais da Neovero: plano PM RONDA PERIÓDICA -
    FANCOILS HIDRÔNICOS mostrava 28 no MyFlux contra 14 na Neovero. Os 14 itens já
    tinham uma OS Aberta vinculada — a primeira ocorrência da expansão é justamente
    essa OS que já existe.

    Também cobre a regressão encontrada depois: a primeira versão desta função
    DESCARTAVA a ocorrência da lista, o que fazia itens de "hoje" sumirem por
    completo de consultas de um único dia (a única ocorrência da janela era
    justamente a que tinha OS aberta). Agora só marca, nunca remove — e só marca
    quando há uma ocorrência seguinte para "assumir" a vaga.

    E cobre a terceira rodada de ajuste: comparando com o relatório da Neovero
    mês a mês, marcar a ocorrência usando o estado de OS de HOJE piorava a
    projeção de meses futuros (a OS aberta hoje não vai continuar aberta em
    outubro) — por isso `janela_inclui_hoje=False` desliga a marcação inteira."""

    def test_situacao_aberta_marca_primeira_ocorrencia(self):
        datas = [date(2026, 8, 21), date(2026, 8, 28)]
        assert marcar_ocorrencia_ja_aberta(datas, {"situacao": 1}) == [True, False]

    def test_situacao_em_andamento_marca_primeira_ocorrencia(self):
        datas = [date(2026, 8, 21), date(2026, 8, 28)]
        assert marcar_ocorrencia_ja_aberta(datas, {"situacao": 2}) == [True, False]

    def test_situacao_fechada_nao_marca_nada(self):
        datas = [date(2026, 8, 21), date(2026, 8, 28)]
        assert marcar_ocorrencia_ja_aberta(datas, {"situacao": 3}) == [False, False]

    def test_sem_os_vinculada_nao_marca_nada(self):
        datas = [date(2026, 8, 21), date(2026, 8, 28)]
        assert marcar_ocorrencia_ja_aberta(datas, None) == [False, False]
        assert marcar_ocorrencia_ja_aberta(datas, {}) == [False, False]

    def test_janela_futura_nunca_marca_mesmo_com_os_aberta(self):
        """Consulta de um mês inteiramente futuro (ex: setembro, consultado em
        agosto) não deve usar o estado de OS de hoje para marcar nada."""
        datas = [date(2026, 9, 4), date(2026, 9, 11)]
        assert marcar_ocorrencia_ja_aberta(datas, {"situacao": 1}, janela_inclui_hoje=False) == [False, False]

    def test_lista_vazia_nao_quebra(self):
        assert marcar_ocorrencia_ja_aberta([], {"situacao": 1}) == []

    def test_unica_ocorrencia_nunca_e_marcada_mesmo_com_os_aberta(self):
        """O caso que causou a regressão: consulta de um único dia ("hoje"), o item
        tem só essa ocorrência na janela e já tem OS aberta — precisa continuar
        visível e contando, senão o item some da visão do dia."""
        datas = [date(2026, 8, 21)]
        assert marcar_ocorrencia_ja_aberta(datas, {"situacao": 1}) == [False]
        assert marcar_ocorrencia_ja_aberta(datas, {"situacao": 2}) == [False]

    def test_tres_ocorrencias_so_marca_a_primeira(self):
        datas = [date(2026, 8, 21), date(2026, 8, 28), date(2026, 9, 4)]
        assert marcar_ocorrencia_ja_aberta(datas, {"situacao": 1}) == [True, False, False]

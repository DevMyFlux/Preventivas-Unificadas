"""HMB: nas rondas automáticas a tela mostra QUEM está de plantão na equipe do Neovero (escala), não o nome da equipe."""
from datetime import date

import pytest

from core import preventivas as prev
from core.motor_base import indicar_responsavel
from tests.fakes import colaboradores_df, item_plano, os_neovero, plano_neovero
from tests.test_api_unidade import P, _get, ana, neovero  # noqa: F401  (fixtures reutilizadas)
from units.brasilandia.equipes import plantonistas
from units.brasilandia.regras import RESPONSAVEIS_EQUIPE, plano_automatico

HOJE = date(2026, 10, 14)
D15, D16 = date(2026, 10, 15), date(2026, 10, 16)


def _quadro():
    # dias_plantao por dia do mês: D/N = trabalha; F = folga
    return colaboradores_df([
        {"funcionario": "Rui Diurno Impar", "cargo": "Eletricista", "turno": "Diurno", "dias_plantao": {15: "D", 16: "F"}},
        {"funcionario": "Beto Auxiliar Diurno Impar", "cargo": "Aux. Manutenção Elétrica", "turno": "Diurno", "dias_plantao": {15: "D", 16: "F"}},
        {"funcionario": "Sara Diurno Par", "cargo": "Eletricista", "turno": "Diurno", "dias_plantao": {15: "F", 16: "D"}},
        {"funcionario": "Bruno Noturno Impar", "cargo": "Eletricista", "turno": "Noturno", "dias_plantao": {15: "N", 16: "F"}},
        {"funcionario": "Carla Diurno Impar", "cargo": "Técnico de Climatização", "turno": "Diurno", "dias_plantao": {15: "D", 16: "F"}},
        {"funcionario": "Tiago Auxiliar Noturno Par", "cargo": "Aux. Manutenção / Climatização", "turno": "Noturno", "dias_plantao": {15: "F", 16: "N"}},
        {"funcionario": "Gestor", "cargo": "Supervisor de Manutenção", "turno": "Diurno", "dias_plantao": {15: "D", 16: "D"}},
        {"funcionario": "Paulo Bloqueado", "cargo": "Eletricista", "turno": "Diurno", "bloqueado": True, "dias_plantao": {15: "D", 16: "D"}},
        {"funcionario": "Vera Desligada", "cargo": "Eletricista", "turno": "Diurno", "status": "Desligado", "data_desligamento": "2026-09-01",
         "dias_plantao": {15: "D", 16: "D"}},
    ])


def _ativos():
    q = _quadro()
    return q[q.status == "Ativo"]


def test_plantonistas_por_equipe_dia_e_turno_sem_gestao_bloqueado_ou_desligado():
    a = _ativos()
    assert plantonistas(a, "eletrica diurno", D15) == ["Beto Auxiliar Diurno Impar", "Rui Diurno Impar"]
    assert plantonistas(a, "eletrica diurno", D16) == ["Sara Diurno Par"]
    assert plantonistas(a, "eletrica noturno", D15) == ["Bruno Noturno Impar"]
    assert plantonistas(a, "climatizacao diurno", D15) == ["Carla Diurno Impar"]
    assert plantonistas(a, "climatizacao noturno", D16) == ["Tiago Auxiliar Noturno Par"]
    assert plantonistas(a, "climatizacao noturno", D15) == []             # ninguém de plantão
    assert plantonistas(a.iloc[0:0], "eletrica diurno", D15) == []


def _ctx():
    q = _quadro()
    return prev.ContextoGeracao(colab_ativos=q[q.status == "Ativo"], colab_todos=q, indicar=indicar_responsavel, hoje=HOJE,
                                plano_automatico_fn=plano_automatico, nomes_equipe=RESPONSAVEIS_EQUIPE, plantonistas_fn=plantonistas)


def _ronda(numero, dia, responsavel, situacao=1):
    return os_neovero(numero, dia, situacao=situacao, responsavel=responsavel, responsavel_id=67, plano="PM - DIÁRIO - RONDA – CHILLERS",
                      tipo="RONDA", tipo_id=8, periodicidade=1, unidade_tempo="D", oficina="ELÉTRICA", equip_id=int(numero))


def _gerar(ctx, reais, planos=(), itens=None):
    return prev.gerar_ocorrencias(ctx, list(planos), itens or {}, reais, [], date(2026, 10, 1), date(2026, 10, 31), True)


@pytest.mark.parametrize("dia,equipe,esperado", [
    ("2026-10-15", "ELÉTRICA - DIURNO", ["Beto Auxiliar Diurno Impar", "Rui Diurno Impar"]),
    ("2026-10-16", "ELÉTRICA - DIURNO", ["Sara Diurno Par"]),
    ("2026-10-15", "ELÉTRICA - NOTURNO", ["Bruno Noturno Impar"]),
    ("2026-10-15", "CLIMATIZAÇÃO - DIURNO", ["Carla Diurno Impar"]),
    ("2026-10-16", "CLIMATIZAÇÃO - NOTURNO", ["Tiago Auxiliar Noturno Par"]),
])
def test_os_em_nome_da_equipe_traz_as_pessoas_de_plantao_do_dia(dia, equipe, esperado):
    oc = _gerar(_ctx(), [_ronda(1, dia, equipe)])[0]
    assert oc["responsaveis_plantao"] == esperado and oc["responsavel_nome"] == equipe and oc["recomendado"] is None


def test_sem_ninguem_de_plantao_a_lista_fica_vazia_e_a_tela_cai_para_o_nome_da_equipe():
    oc = _gerar(_ctx(), [_ronda(2, "2026-10-15", "CLIMATIZAÇÃO - NOTURNO")])[0]
    assert oc["responsaveis_plantao"] == [] and oc["responsavel_nome"] == "CLIMATIZAÇÃO - NOTURNO"


def test_previsao_de_ronda_usa_a_equipe_padrao_do_plano_no_dia_da_ocorrencia():
    plano = plano_neovero(1, "PM - DIÁRIO - RONDA – CHILLERS", oficina="ELÉTRICA", periodicidade=1, unidade="D", tipo_id=8)
    plano["responsavelId"] = 67
    ocs = _gerar(_ctx(), [_ronda(3, "2026-10-14", "ELÉTRICA - DIURNO", situacao=3)], [plano], {1: [item_plano(10, "2026-10-15", equip_id=77)]})
    por_dia = {o["data_iso"]: o["responsaveis_plantao"] for o in ocs if o["origem"] == "Plano"}
    assert por_dia["2026-10-15"] == ["Beto Auxiliar Diurno Impar", "Rui Diurno Impar"] and por_dia["2026-10-16"] == ["Sara Diurno Par"]


def test_so_equipes_reconhecidas_em_plano_automatico_e_so_na_unidade_configurada():
    assert _gerar(_ctx(), [_ronda(4, "2026-10-15", "ELÉTRICA - TARDE")])[0]["responsaveis_plantao"] == []
    gerente = _gerar(_ctx(), [_ronda(5, "2026-10-15", "GESTOR")])[0]
    assert gerente["responsaveis_plantao"] == []
    q = _quadro()
    sem_config = prev.ContextoGeracao(colab_ativos=q[q.status == "Ativo"], colab_todos=q, indicar=indicar_responsavel, hoje=HOJE)   # ex.: HETRIN
    assert _gerar(sem_config, [_ronda(6, "2026-10-15", "ELÉTRICA - DIURNO")])[0]["responsaveis_plantao"] == []


def test_ronda_concluida_continua_com_o_rotulo_e_a_pessoa_de_plantao_nao_substitui_o_historico():
    oc = _gerar(_ctx(), [_ronda(7, "2026-10-15", "ELÉTRICA - DIURNO", situacao=3)])[0]
    assert oc["sem_recomendacao_motivo"] == "Concluída" and oc["responsavel_nome"] == "ELÉTRICA - DIURNO"


def test_api_traz_responsaveis_plantao_na_listagem(ana, neovero):
    neovero.os_periodo = [_ronda(11, "2026-10-14", "ELÉTRICA - NOTURNO")]
    neovero.os_abertas = list(neovero.os_periodo)
    item = _get(ana, data_ini="2026-10-14", data_fim="2026-10-14").get_json()["itens"][0]
    assert item["responsavel_nome"] == "ELÉTRICA - NOTURNO" and isinstance(item["responsaveis_plantao"], list)


def test_fora_do_mes_da_escala_carregada_nao_mostra_pessoas_so_a_equipe():
    ctx = _ctx()
    setembro = prev.gerar_ocorrencias(ctx, [], {}, [_ronda(8, "2026-09-15", "ELÉTRICA - DIURNO")], [], date(2026, 9, 1), date(2026, 9, 30), True)[0]
    novembro_plano = plano_neovero(1, "PM - DIÁRIO - RONDA – CHILLERS", oficina="ELÉTRICA", periodicidade=1, unidade="D", tipo_id=8)
    novembro_plano["responsavelId"] = 67
    assert setembro["responsaveis_plantao"] == [] and setembro["responsavel_nome"] == "ELÉTRICA - DIURNO"
    ocs = prev.gerar_ocorrencias(ctx, [novembro_plano], {1: [item_plano(10, "2026-11-02", equip_id=77)]}, [_ronda(9, "2026-10-14", "ELÉTRICA - DIURNO", situacao=3)],
                                 [], date(2026, 11, 1), date(2026, 11, 3), True)
    assert ocs and all(o["responsaveis_plantao"] == [] for o in ocs if o["origem"] == "Plano")

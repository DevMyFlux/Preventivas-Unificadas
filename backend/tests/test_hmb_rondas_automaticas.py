"""
HMB: as rondas diárias são AUTOMÁTICAS no Neovero (responsáveis de equipe: Elétrica/Climatização × Diurno/Noturno).
O sistema as reconhece como corretas, não as manda para a Revisão e não recomenda executante. Só vale para a HMB.
"""
from datetime import date

import pytest

from core import preventivas as prev
from core.motor_base import indicar_responsavel
from tests.fakes import colaboradores_df, item_plano, os_neovero, plano_neovero
from tests.test_api_unidade import P, _get, ana, neovero  # noqa: F401  (fixtures reutilizadas)
from units.brasilandia.regras import REGRAS, RESPONSAVEIS_EQUIPE, plano_automatico

HOJE = date(2026, 10, 14)
EQUIPES = ["ELÉTRICA - DIURNO", "ELÉTRICA - NOTURNO", "CLIMATIZAÇÃO - DIURNO", "CLIMATIZAÇÃO - NOTURNO"]


def _ctx(com_regra_automatica=True):
    colab = colaboradores_df([
        {"funcionario": "Eletricista A", "cargo": "Eletricista"},
        {"funcionario": "William de Souza Lobo", "cargo": "Supervisor de Manutenção", "turno": "Administrativo"},
    ])
    extra = {"plano_automatico_fn": plano_automatico, "nomes_equipe": RESPONSAVEIS_EQUIPE} if com_regra_automatica else {}
    return prev.ContextoGeracao(colab_ativos=colab[colab.status == "Ativo"], colab_todos=colab, indicar=indicar_responsavel,
                                hoje=HOJE, **extra)


def _ronda(numero, responsavel, situacao=1, plano="PM - DIÁRIO - RONDA – CHILLERS", **kw):
    kw.setdefault("equip_id", int(numero))
    return os_neovero(numero, "2026-10-14", situacao=situacao, responsavel=responsavel, responsavel_id=67, plano=plano,
                      tipo="RONDA", tipo_id=8, periodicidade=1, unidade_tempo="D", oficina="ELÉTRICA", **kw)


def _gerar(ctx, reais, planos=(), itens=None):
    return prev.gerar_ocorrencias(ctx, list(planos), itens or {}, reais, [], date(2026, 10, 1), date(2026, 10, 31), True)


@pytest.mark.parametrize("equipe", EQUIPES)
def test_as_quatro_equipes_sao_o_responsavel_correto_da_ronda_diaria(equipe):
    oc = _gerar(_ctx(), [_ronda(1, equipe)])[0]
    assert oc["responsavel_status"] == prev.RESP_EQUIPE == "Equipe do Neovero"
    assert oc["revisao"] is False                      # não vai para a Revisão
    assert oc["recomendado"] is None and oc["sem_candidato"] is False and oc["requer_intervencao"] is False


def test_equipe_so_vale_em_plano_automatico_nas_demais_continua_generico():
    mensal = os_neovero(2, "2026-10-14", situacao=1, responsavel="ELÉTRICA - DIURNO", responsavel_id=67, plano="PM - MENSAL - QUADROS ELÉTRICOS",
                        oficina="ELÉTRICA", periodicidade=1, unidade_tempo="M")
    oc = _gerar(_ctx(), [mensal])[0]
    assert oc["responsavel_status"] == prev.RESP_GENERICO and oc["revisao"] is True and oc["recomendado"] == "Eletricista A"


def test_ronda_em_nome_do_gestor_continua_sendo_gestao_e_recebe_recomendacao():
    oc = _gerar(_ctx(), [_ronda(3, "WILLIAN DE SOUZA LOBO")])[0]
    assert oc["responsavel_status"] == prev.RESP_GESTAO and oc["revisao"] is True and oc["recomendado"] == "Eletricista A"


def test_outros_nomes_de_equipe_nao_sao_aceitos_e_outra_unidade_sem_a_configuracao_nao_muda():
    assert _gerar(_ctx(), [_ronda(4, "ELÉTRICA - TARDE")])[0]["responsavel_status"] == prev.RESP_GENERICO
    sem_config = _gerar(_ctx(com_regra_automatica=False), [_ronda(5, "ELÉTRICA - DIURNO")])[0]     # ex.: HETRIN
    assert sem_config["responsavel_status"] == prev.RESP_GENERICO and sem_config["revisao"] is True


def test_projecao_de_ronda_diaria_nao_recebe_recomendacao():
    plano = plano_neovero(1, "PM - DIÁRIO - RONDA – CHILLERS", oficina="ELÉTRICA", periodicidade=1, unidade="D", tipo_id=8)
    itens = {1: [item_plano(10, "2026-10-15", equip_id=77)]}
    ocs = [o for o in _gerar(_ctx(), [], [plano], itens) if o["origem"] == "Plano"]
    assert ocs and all(o["recomendado"] is None and not o["sem_candidato"] and not o["requer_intervencao"] for o in ocs)


def test_plano_automatico_e_so_ronda_diaria_tipo_8_ou_com_ronda_no_nome():
    assert plano_automatico("PM - DIÁRIO - MEDIÇÃO HIDROMETRO", "", 8, 1, "D") is True        # tipo RONDA no Neovero
    assert plano_automatico("PM - DIÁRIO - RONDA – CHILLERS", "", 2, 1, "D") is True
    assert plano_automatico("PM - MENSAL – RONDA – ILUMINAÇÃO", "", 8, 1, "M") is False        # não é diária
    assert plano_automatico("PM - MENSAL - SPLIT", "", 2, 1, "M") is False


def test_ronda_automatica_nao_entra_na_regra_ativa_nem_gera_pendencia_de_nomes():
    assert [r.id for r in REGRAS] == ["oficina_ar_comprimido_vacuo"]


# ── via API (HMB) ────────────────────────────────────────────────────────────

def test_api_listagem_e_revisao_nao_tratam_a_equipe_como_problema(ana, neovero):
    neovero.os_periodo = [_ronda(11, "ELÉTRICA - NOTURNO"), _ronda(12, "CLIMATIZAÇÃO - DIURNO", equip_id=12),
                          _ronda(13, "WILLIAN DE SOUZA LOBO", equip_id=13)]
    neovero.os_abertas = list(neovero.os_periodo)
    itens = {o["os_vinculada"]: o for o in _get(ana, data_ini="2026-10-14", data_fim="2026-10-14").get_json()["itens"]}
    assert itens["11"]["responsavel_status"] == "Equipe do Neovero" and itens["11"]["revisao"] is False
    assert itens["12"]["recomendado"] is None
    assert itens["13"]["responsavel_status"] == "Gestão" and itens["13"]["revisao"] is True
    rev = ana.get(f"{P}/revisao").get_json()
    assert [i["os_numero"] for i in rev["itens"]] == ["13"]                    # só a do gestor precisa de revisão


def test_planos_de_ronda_com_equipe_como_padrao_nao_aparecem_como_responsavel_invalido(ana, neovero):
    plano = plano_neovero(1, "PM - DIÁRIO - RONDA – CHILLERS", oficina="ELÉTRICA", periodicidade=1, unidade="D", tipo_id=8)
    plano["responsavelId"] = 67
    outro = plano_neovero(2, "PM - MENSAL - NOBREAK", oficina="ELÉTRICA")
    outro["responsavelId"] = 67
    neovero.planos = [plano, outro]
    neovero.os_abertas = [_ronda(21, "ELÉTRICA - DIURNO")]
    neovero.os_abertas[0]["planoManutencaoId"] = 1
    neovero.os_periodo = list(neovero.os_abertas)
    invalidos = {p["plano_id"] for p in ana.get(f"{P}/revisao").get_json()["planos_responsavel_invalido"]}
    assert 1 not in invalidos          # ronda diária: a equipe é o esperado


def test_equipe_e_projecao_de_ronda_dizem_que_e_automatico():
    assert _gerar(_ctx(), [_ronda(31, "ELÉTRICA - DIURNO")])[0]["sem_recomendacao_motivo"] == "Equipe do Neovero (automático)"
    plano = plano_neovero(1, "PM - DIÁRIO - RONDA – CHILLERS", oficina="ELÉTRICA", periodicidade=1, unidade="D", tipo_id=8)
    proj = [o for o in _gerar(_ctx(), [], [plano], {1: [item_plano(10, "2026-10-15", equip_id=77)]}) if o["origem"] == "Plano"]
    assert proj and all(o["sem_recomendacao_motivo"] == "Automático (Neovero)" for o in proj)

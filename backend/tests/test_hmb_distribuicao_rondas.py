"""
HMB — distribuição de rondas e executantes por cargo (pedido dos usuários, out/2026). Só vale para a HMB.

  * rondas diárias: TODAS as de CLIMATIZAÇÃO na equipe CLIMATIZAÇÃO-NOTURNO; as de ELÉTRICA/QGBT seguem o turno do nome do plano;
  * planos mensais de motobomba e ronda de iluminação → Auxiliar de Manutenção Elétrica; fancoil mensal → Técnico de
    Climatização; quadros elétricos → Eletricista.
Os nomes dos planos abaixo são os REAIS do Neovero da HMB (travessão "–", espaços duplos, "NOTUR" truncado).
"""
from datetime import date

import pytest

from core import preventivas as prev
from core.motor_base import indicar_responsavel
from tests.fakes import colaboradores_df, os_neovero
from units.brasilandia.regras import EQUIPES_ROTULO, RESPONSAVEIS_EQUIPE, equipe_da_ronda, plano_automatico
from units.brasilandia.regras_cargo import regra_cargo_do_plano
from units.grand_massif.regras_cargo import regra_cargo_do_plano as regra_hetrin

HOJE = date(2026, 10, 14)


# ── cargo por plano ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("plano, familia", [
    ("PM - MENSAL -  MOTOBOMBA", "aux_eletricista"),
    ("PM - MENSAL – RONDA – ILUMINAÇÃO", "aux_eletricista"),
    ("PM - MENSAL - FANCOIL", "tecnico_climatizacao"),
    ("PM - MENSAL - QUADROS ELÉTRICOS", "eletricista"),
    ("PM - TRIMESTRAL - QUADROS ELÉTRICOS", "eletricista"),
    ("PM - SEMESTRAL - QUADROS ELÉTRICOS", "eletricista"),
    ("PREDITIVA ANUAL - QUADROS ELÉTRICOS (TERMOGRAFIA)", "eletricista"),
])
def test_executante_por_cargo_dos_planos_pedidos(plano, familia):
    regra = regra_cargo_do_plano(plano)
    assert regra is not None and regra.principais == (familia,) and regra.alternativas == ()


@pytest.mark.parametrize("plano", [
    "PM - SEMANAL- MOTOBOMBA", "PM - TRIMESTRAL -  MOTOBOMBA", "PM - ANUAL -  MOTOBOMBA",     # só a MENSAL foi pedida
    "PM - TRIMESTRAL - FANCOIL", "PM - SEMESTRAL -  FANCOIL",
    "PM - MENSAL - SPLIT", "PM - MENSAL - NOBREAK",
    "PM – DIÁRIO - RONDA - ÁGUA POTÁVEL",
])
def test_planos_fora_do_pedido_ficam_sem_regra_de_cargo(plano):
    assert regra_cargo_do_plano(plano) is None


def test_a_tabela_da_hmb_nao_vaza_para_a_hetrin():
    assert regra_hetrin("PM - MENSAL - QUADROS ELÉTRICOS") is None
    assert regra_hetrin("PM - MENSAL - FANCOIL") is None


def _ctx():
    colab = colaboradores_df([
        {"funcionario": "Aux Eletrica", "cargo": "Aux. Manutenção Elétrica"},
        {"funcionario": "Eletricista A", "cargo": "Eletricista"},
        {"funcionario": "Tecnico Clima", "cargo": "Técnico de Climatização"},
        {"funcionario": "Aux Clima", "cargo": "Aux. Manutenção / Climatização"},
        {"funcionario": "William de Souza Lobo", "cargo": "Supervisor de Manutenção", "turno": "Administrativo"},
    ])
    return prev.ContextoGeracao(colab_ativos=colab[colab.status == "Ativo"], colab_todos=colab, indicar=indicar_responsavel,
                                regra_cargo_fn=regra_cargo_do_plano, plano_automatico_fn=plano_automatico,
                                nomes_equipe=RESPONSAVEIS_EQUIPE, equipe_esperada_fn=equipe_da_ronda,
                                equipes_rotulo=EQUIPES_ROTULO, hoje=HOJE)


def _mensal(numero, plano, oficina):
    # o Neovero deixa os mensais no nome do supervisor (responsável padrão do plano)
    return os_neovero(numero, "2026-10-14", situacao=1, responsavel="WILLIAN DE SOUZA LOBO", responsavel_id=31, plano=plano,
                      oficina=oficina, periodicidade=1, unidade_tempo="M", equip_id=int(numero))


def _gerar(reais):
    return prev.gerar_ocorrencias(_ctx(), [], {}, reais, [], date(2026, 10, 1), date(2026, 10, 31), True)


@pytest.mark.parametrize("plano, oficina, esperado", [
    ("PM - MENSAL -  MOTOBOMBA", "MOTO BOMBAS", "Aux Eletrica"),
    ("PM - MENSAL – RONDA – ILUMINAÇÃO", "ELÉTRICA/QGBT", "Aux Eletrica"),
    ("PM - MENSAL - FANCOIL", "CLIMATIZAÇÃO", "Tecnico Clima"),
    ("PM - MENSAL - QUADROS ELÉTRICOS", "ELÉTRICA/QGBT", "Eletricista A"),
])
def test_recomendacao_respeita_o_cargo_pedido(plano, oficina, esperado):
    oc = _gerar([_mensal(1, plano, oficina)])[0]
    assert oc["recomendado"] == esperado
    assert oc["regra_cargo"]["id"]


def test_sem_ninguem_do_cargo_pedido_fica_sem_candidato_e_nunca_outro_cargo():
    ctx = _ctx()
    sem_aux = ctx.colab_ativos[ctx.colab_ativos.funcionario != "Aux Eletrica"]
    ctx.colab_ativos = sem_aux
    oc = prev.gerar_ocorrencias(ctx, [], {}, [_mensal(2, "PM - MENSAL -  MOTOBOMBA", "MOTO BOMBAS")], [],
                                date(2026, 10, 1), date(2026, 10, 31), True)[0]
    assert oc["recomendado"] is None and oc["sem_candidato"] is True and oc["requer_intervencao"] is True


# ── equipe da ronda diária ────────────────────────────────────────────────────

@pytest.mark.parametrize("plano", [
    "PM - DIÁRIO - RONDA – CASA DOS FANCOIS", "PM - DIÁRIO - RONDA – CASA DOS FANCOIS – NOTURNO",
    "PM - DIÁRIO - RONDA – CHILLERS", "PM - DIÁRIO - RONDA – SALA DE ISOLAMENTO", "PM - DIÁRIO - RONDA – SALA DE PRESSURIZAÇÃO",
    "PM - DIÁRIO - RONDA – LIGAR AR COND. E ILUMINAÇÃO 05H NOTURN",
])
def test_toda_ronda_de_climatizacao_vai_para_a_equipe_noturna(plano):
    assert equipe_da_ronda(plano, "CLIMATIZAÇÃO", 8, 1, "D") == "climatizacao noturno"


@pytest.mark.parametrize("plano, equipe", [
    ("PM – DIÁRIO - RONDA - ÁGUA POTÁVEL", "eletrica diurno"),
    ("PM – DIÁRIO - RONDA - ÁGUA POTÁVEL – NOTURNO", "eletrica noturno"),
    ("PM – DIÁRIO - RONDA - SIST. AQUE. VIA PLACAS SOLARES – NOTUR", "eletrica noturno"),   # nome truncado no Neovero
    ("PM – DIÁRIO - RONDA – SECUNDARIA", "eletrica diurno"),
    ("PM – DIÁRIO - RONDA – NOBREAK – NOTURNO", "eletrica noturno"),
])
def test_ronda_eletrica_segue_o_turno_do_nome(plano, equipe):
    assert equipe_da_ronda(plano, "ELÉTRICA/QGBT", 8, 1, "D") == equipe


def test_so_ronda_diaria_tem_equipe_definida():
    assert equipe_da_ronda("PM - MENSAL – RONDA – ILUMINAÇÃO", "ELÉTRICA/QGBT", 8, 1, "M") is None
    assert equipe_da_ronda("PM - MENSAL - FANCOIL", "CLIMATIZAÇÃO", 2, 1, "M") is None
    assert equipe_da_ronda("PM – DIÁRIO - RONDA - X", "MOTO BOMBAS", 8, 1, "D") is None     # oficina fora da tabela


def _ronda(numero, plano, oficina, responsavel):
    return os_neovero(numero, "2026-10-14", situacao=1, responsavel=responsavel, responsavel_id=68, plano=plano, tipo="RONDA",
                      tipo_id=8, periodicidade=1, unidade_tempo="D", oficina=oficina, equip_id=int(numero))


def test_ronda_de_climatizacao_do_dia_passa_a_responder_a_equipe_noturna_e_avisa_a_divergencia():
    oc = _gerar([_ronda(5, "PM - DIÁRIO - RONDA – CHILLERS", "CLIMATIZAÇÃO", "CLIMATIZAÇÃO - DIURNO")])[0]
    assert oc["responsavel_status"] == prev.RESP_EQUIPE and oc["revisao"] is False and oc["recomendado"] is None
    assert oc["responsavel_nome"] == "CLIMATIZAÇÃO - NOTURNO"
    assert oc["equipe_neovero"] == "CLIMATIZAÇÃO - DIURNO"
    assert any("Equipe no Neovero: CLIMATIZAÇÃO - DIURNO" in a for a in oc["alertas"])


def test_ronda_que_ja_esta_na_equipe_certa_nao_muda_nem_alerta():
    oc = _gerar([_ronda(6, "PM – DIÁRIO - RONDA - ÁGUA POTÁVEL – NOTURNO", "ELÉTRICA/QGBT", "ELÉTRICA - NOTURNO")])[0]
    assert oc["responsavel_nome"] == "ELÉTRICA - NOTURNO" and not oc.get("equipe_neovero") and oc["alertas"] == []


def test_ronda_em_nome_de_pessoa_ou_gestor_nao_e_redistribuida():
    oc = _gerar([_ronda(7, "PM - DIÁRIO - RONDA – CHILLERS", "CLIMATIZAÇÃO", "WILLIAN DE SOUZA LOBO")])[0]
    assert oc["responsavel_status"] == prev.RESP_GESTAO and oc["revisao"] is True and not oc.get("equipe_neovero")

"""
Regras de cargo por plano (HETRIN): quem pode executar o quê, cargo alternativo explícito, escassez de
Técnico de Climatização sinalizada (sem escolha silenciosa), desvio em OS já atribuídas, status "Parada" e
isolamento entre unidades (a HMB não herda nada).
"""
from datetime import date

import pytest

from core import preventivas as prev
from core.motor_base import indicar_responsavel
from core.regras import cargos
from tests.fakes import colaboradores_df, os_neovero
from units.grand_massif.regras_cargo import REGRAS_CARGO, regra_cargo_do_plano

HOJE = date(2026, 10, 14)
SUPERVISAO = "WILLIAN DE SOUZA LOBO"        # OS criada no nome do gestor → precisa de executante

ELETRICISTA = {"funcionario": "Eletricista A", "cargo": "Eletricista"}
AUX_ELETRICISTA = {"funcionario": "Aux Eletrico A", "cargo": "Aux. Eletricista"}
AUX_MANUT = {"funcionario": "Aux Manut A", "cargo": "Aux. Manutenção / Climatização"}
TEC_CLIMA = {"funcionario": "Tecnico Clima A", "cargo": "Técnico de Climatização"}
GESTOR = {"funcionario": "William de Souza Lobo", "cargo": "Gerente de Equipe / Engenheira", "turno": "Administrativo"}


def _ctx(linhas, com_regra=True):
    colab = colaboradores_df(linhas + [GESTOR])
    return prev.ContextoGeracao(
        colab_ativos=colab[colab["status"] == "Ativo"], colab_todos=colab, indicar=indicar_responsavel,
        regra_cargo_fn=regra_cargo_do_plano if com_regra else None, hoje=HOJE)


def _os(numero, plano, responsavel=SUPERVISAO, **kw):
    kw.setdefault("equip_id", int(numero))
    kw.setdefault("oficina", "ELÉTRICA")
    return os_neovero(numero, "2026-10-14", situacao=1, responsavel=responsavel, responsavel_id=31, plano=plano, **kw)


def _gerar(ctx, reais):
    return prev.gerar_ocorrencias(ctx, [], {}, reais, [], date(2026, 10, 1), date(2026, 10, 31), True)


# ── famílias de cargo ────────────────────────────────────────────────────────

@pytest.mark.parametrize("cargo,familia", [
    ("Eletricista", cargos.FAM_ELETRICISTA),
    ("Aux. Eletricista", cargos.FAM_AUX_ELETRICISTA),
    ("Auxiliar de Eletricista", cargos.FAM_AUX_ELETRICISTA),
    ("Aux. Manutenção / Climatização", cargos.FAM_AUX_MANUTENCAO),
    ("Técnico de Climatização", cargos.FAM_TEC_CLIMATIZACAO),
    ("Tecnico de Climatizacao", cargos.FAM_TEC_CLIMATIZACAO),
    ("Gerente de Equipe / Engenheira", None), ("Auxiliar Administrativo", None), ("", None), (None, None),
])
def test_familia_do_cargo(cargo, familia):
    assert cargos.familia_do_cargo(cargo) == familia


# ── tabela da HETRIN contra nomes REAIS de planos ────────────────────────────

@pytest.mark.parametrize("plano,regra", [
    ("PM – MENSAL – INSPEÇÃO SISTEMA DE COMBATE A INCÊNDIO", "inspecao_combate_incendio"),
    ("PM SEMANAL - TESTE DE PARTIDA DOS GRUPOS GERADORES", "grupos_geradores"),
    ("PM - LIMPEZA E INSPEÇÃO VISUAL DOS PAINÉIS TERMOSSOLARES", "paineis_termossolares"),
    ("COLETA DIÁRIA MEDIDOR - NOTURNO - N1", "coleta_medidor_noturno_n1"),
    ("PM - LIMPEZA FANCOILS BL1 - DIA 01", "fancoils_e_fancoletes"),
    ("PM - LIMPEZA FANCOILS BL1 - DIA 02", "fancoils_e_fancoletes"),
    ("PM RONDA PERIÓDICA - RÉGUAS DE GASES MEDICINAIS - 1º ANDAR", "reguas_gases_e_exaustores"),
    ("LIMPEZA QUINZENAL - EXAUSTORES/DIFUSORES - NOITE - N1", "reguas_gases_e_exaustores"),
    ("PM - RONDA ILUMINAÇÃO/TOMADAS - NOITE - N1", "ronda_iluminacao_tomadas"),
    ("PM - RONDA SEMANAL - MOTOBOMBAS - HETRIN - DIURNO", "motobombas"),
    ("PM - MENSAL MOTOBOMBAS NOITE - N1", "motobombas"),
    ("PM MENSAL - FANCOLETE - HETRIN", "fancoils_e_fancoletes"),
    ("PM SEMANAL - INSPEÇÃO GRUPOS GERADORES", "grupos_geradores"),
    ("RONDA DIÁRIA – CHILLER CONDENSAÇÃO A AR – COMPRESSOR SCROLL", "rondas_climatizacao_diarias"),
    ("PM - RONDA DIÁRIA - SISTEMA DE AR COMPRIMIDO - PAR", "rondas_climatizacao_diarias"),
])
def test_planos_reais_da_hetrin_casam_com_a_regra_certa(plano, regra):
    assert regra_cargo_do_plano(plano).id == regra


@pytest.mark.parametrize("plano", [
    "PM - MENSAL - SPLIT", "PM SEMANAL - SISTEMA DE ALARME DE COMBATE A INCÊNDIO",     # alarme semanal: sem regra pedida
    "COLETA DIÁRIA MEDIDOR - NOTURNO - N2", "COLETA DIÁRIA MEDIDOR - DIURNO - D1",       # só o N1 foi regulado
    "PM RONDA PERIÓDICA - FANCOILS HIDRÔNICOS", "",
])
def test_planos_sem_regra_de_cargo_continuam_livres(plano):
    assert regra_cargo_do_plano(plano) is None


def test_alternativas_sao_explicitas_so_onde_declaradas():
    com_alt = {r.id for r in REGRAS_CARGO if r.alternativas}
    assert com_alt == {"reguas_gases_e_exaustores", "ronda_iluminacao_tomadas"}
    assert cargos.violacao(regra_cargo_do_plano("PM - LIMPEZA FANCOILS BL1 - DIA 01"), "Aux. Eletricista").startswith("Cargo fora")
    assert cargos.violacao(regra_cargo_do_plano("PM - LIMPEZA FANCOILS BL1 - DIA 01"), "Técnico de Climatização") is None
    assert cargos.violacao(regra_cargo_do_plano("PM - RONDA ILUMINAÇÃO/TOMADAS - DIA - D1"), "Aux. Eletricista").startswith("Cargo alternativo")


# ── motor: gate estrito ──────────────────────────────────────────────────────

INSPECAO = "PM – MENSAL – INSPEÇÃO SISTEMA DE COMBATE A INCÊNDIO"


def test_inspecao_de_combate_a_incendio_vai_para_eletricista_e_nunca_para_auxiliar():
    oc = _gerar(_ctx([ELETRICISTA, AUX_ELETRICISTA, AUX_MANUT]), [_os(1, INSPECAO)])[0]
    assert oc["recomendado"] == "Eletricista A"
    assert oc["regra_cargo"]["id"] == "inspecao_combate_incendio"


def test_sem_eletricista_a_inspecao_fica_sem_candidato_e_nao_cai_em_auxiliar():
    oc = _gerar(_ctx([AUX_ELETRICISTA, AUX_MANUT, TEC_CLIMA]), [_os(1, INSPECAO)])[0]
    assert oc["recomendado"] is None and oc["sem_candidato"] is True
    assert "Eletricista" in oc["motivo_sem_candidato"] and "não escolhe outro cargo" in oc["motivo_sem_candidato"]


def test_teste_de_partida_dos_geradores_so_eletricista():
    ctx = _ctx([AUX_ELETRICISTA, ELETRICISTA])
    oc = _gerar(ctx, [_os(1, "PM SEMANAL - TESTE DE PARTIDA DOS GRUPOS GERADORES")])[0]
    assert oc["recomendado"] == "Eletricista A"


def test_limpeza_de_fancoils_bl1_so_tecnico_de_climatizacao_nao_o_auxiliar():
    ctx = _ctx([AUX_MANUT, TEC_CLIMA])
    oc = _gerar(ctx, [_os(1, "PM - LIMPEZA FANCOILS BL1 - DIA 01", oficina="CLIMATIZAÇÃO")])[0]
    assert oc["recomendado"] == "Tecnico Clima A"
    assert _gerar(_ctx([AUX_MANUT]), [_os(2, "PM - LIMPEZA FANCOILS BL1 - DIA 01")])[0]["recomendado"] is None


def test_coleta_noturna_de_medidor_n1_e_do_auxiliar_de_eletricista_nao_do_eletricista():
    ctx = _ctx([{**ELETRICISTA, "turno": "Noturno"}, {**AUX_ELETRICISTA, "turno": "Noturno"}])
    oc = _gerar(ctx, [_os(1, "COLETA DIÁRIA MEDIDOR - NOTURNO - N1")])[0]
    assert oc["recomendado"] == "Aux Eletrico A"


def test_alternativa_so_entra_quando_nenhum_principal_pode_e_vem_com_aviso():
    plano = "PM - RONDA ILUMINAÇÃO/TOMADAS - DIA - D1"
    com_principal = _gerar(_ctx([ELETRICISTA, AUX_ELETRICISTA]), [_os(1, plano)])[0]
    assert com_principal["recomendado"] == "Eletricista A" and com_principal["alertas"] == []
    so_alternativo = _gerar(_ctx([AUX_ELETRICISTA, AUX_MANUT]), [_os(2, plano)])[0]
    assert so_alternativo["recomendado"] == "Aux Eletrico A"
    assert any("Cargo alternativo usado" in a for a in so_alternativo["alertas"])
    nenhum = _gerar(_ctx([AUX_MANUT, TEC_CLIMA]), [_os(3, plano)])[0]      # nem principal nem alternativo
    assert nenhum["recomendado"] is None and nenhum["sem_candidato"]


def test_reguas_de_gases_preferem_aux_manutencao_e_aceitam_aux_eletricista_como_alternativa():
    plano = "PM RONDA PERIÓDICA - RÉGUAS DE GASES MEDICINAIS - TÉRREO"
    assert _gerar(_ctx([AUX_ELETRICISTA, AUX_MANUT, ELETRICISTA]), [_os(1, plano)])[0]["recomendado"] == "Aux Manut A"
    alt = _gerar(_ctx([AUX_ELETRICISTA, ELETRICISTA]), [_os(2, plano)])[0]
    assert alt["recomendado"] == "Aux Eletrico A" and any("alternativo" in a for a in alt["alertas"])


def test_escassez_de_tecnico_de_climatizacao_na_ronda_diaria_e_sinalizada_e_nunca_substituida():
    """Ronda diária de chiller/ar comprimido é exclusiva do Técnico de Climatização: sem ele no dia → alerta humano."""
    plano = "RONDA DIÁRIA – CHILLER CONDENSAÇÃO A AR – COMPRESSOR SCROLL"
    ctx = _ctx([ELETRICISTA, AUX_ELETRICISTA, AUX_MANUT, {**TEC_CLIMA, "bloqueado": True}])
    oc = _gerar(ctx, [_os(1, plano, oficina="CLIMATIZAÇÃO")])[0]
    assert oc["recomendado"] is None and oc["sem_candidato"] is True
    assert "Técnico de Climatização" in oc["motivo_sem_candidato"]


def test_limite_diario_dentro_da_familia_avisa_mas_nao_recua_para_outro_cargo():
    ctx = _ctx([ELETRICISTA, AUX_ELETRICISTA])
    ocs = _gerar(ctx, [_os(100 + i, INSPECAO) for i in range(16)])
    assert all(o["recomendado"] == "Eletricista A" for o in ocs)                  # nunca vai para o auxiliar
    assert sum(1 for o in ocs if o["requer_intervencao"]) == 2 and not any(o["sem_candidato"] for o in ocs)


def test_hmb_e_qualquer_unidade_sem_tabela_nao_herdam_regra_de_cargo():
    """Sem `regra_cargo_fn` (HMB) a mesma inspeção pode ir a qualquer cargo apto: nada foi copiado."""
    ctx = _ctx([AUX_ELETRICISTA], com_regra=False)
    oc = _gerar(ctx, [_os(1, INSPECAO)])[0]
    assert oc["recomendado"] == "Aux Eletrico A" and "regra_cargo" not in oc
    import units.brasilandia.routes as hmb
    assert "regra_cargo" not in open(hmb.__file__, encoding="utf-8").read()


# ── OS já atribuída com cargo fora da regra: só sinaliza ─────────────────────

def test_os_atribuida_a_cargo_fora_da_regra_e_sinalizada_sem_reatribuir():
    ctx = _ctx([ELETRICISTA, AUX_ELETRICISTA])
    oc = _gerar(ctx, [_os(1, "PM SEMANAL - TESTE DE PARTIDA DOS GRUPOS GERADORES", responsavel="AUX ELETRICO A")])[0]
    assert oc["responsavel_status"] == prev.RESP_ATRIBUIDA
    assert oc["recomendado"] is None                       # não reatribui
    assert oc["cargo_fora_da_regra"].startswith("Cargo fora da regra")
    ok = _gerar(ctx, [_os(2, "PM SEMANAL - TESTE DE PARTIDA DOS GRUPOS GERADORES", responsavel="ELETRICISTA A")])[0]
    assert ok["cargo_fora_da_regra"] is None


def test_os_concluida_nao_gera_alerta_de_cargo():
    real = os_neovero(1, "2026-10-14", situacao=3, responsavel="AUX ELETRICO A", responsavel_id=2,
                      plano="PM SEMANAL - TESTE DE PARTIDA DOS GRUPOS GERADORES")
    assert _gerar(_ctx([ELETRICISTA, AUX_ELETRICISTA]), [real])[0]["cargo_fora_da_regra"] is None


# ── status "Parada" × "Em andamento" (exibição; situação real intacta) ───────

def _andamento(numero, responsavel="ELETRICISTA A", **extra):
    o = os_neovero(numero, "2026-10-10", situacao=2, responsavel=responsavel, responsavel_id=2, equip_id=numero)
    o.update(extra)
    return o


def test_os_em_andamento_com_parada_sem_funcionamento_vira_parada_sem_mudar_a_situacao():
    parada = _andamento(1, dataHoraParada="2026-10-10T08:00:00", dataHoraFuncionamento=None)
    ocs = {o["os_vinculada"]: o for o in _gerar(_ctx([ELETRICISTA]), [parada, _andamento(2)])}
    assert ocs["1"]["status"] == "Parada" and ocs["1"]["os_situacao"] == "Em Andamento" and ocs["1"]["atrasada"] is True
    assert ocs["1"]["parada_desde"] == "2026-10-10T08:00:00"
    assert ocs["2"]["status"] == "Em andamento"


def test_os_em_pendencia_sem_parada_registrada_mostra_a_situacao_e_a_observacao_do_neovero_mas_nao_vira_parada():
    """Real (HETRIN): 202615533–536 estão 'OS em Pendência' com observação 'AGUARDANDO MANUTENÇÃO' e SEM parada registrada."""
    o = _andamento(7, situacaoDescricaoCompleta="OS em Pendência - Interna", observacao="AGUARDANDO MANUTENÇÃO")
    oc = _gerar(_ctx([ELETRICISTA]), [o])[0]
    assert oc["status"] == "Em andamento" and oc["parada_desde"] is None
    assert oc["situacao_neovero"] == "OS em Pendência - Interna" and oc["observacao_os"] == "AGUARDANDO MANUTENÇÃO"
    fechada = os_neovero(8, "2026-10-10", situacao=3, responsavel="ELETRICISTA A", responsavel_id=2, equip_id=8)
    fechada["observacao"] = "texto qualquer"
    assert _gerar(_ctx([ELETRICISTA]), [fechada])[0]["observacao_os"] is None      # só OS em andamento expõe observação


def test_parada_que_voltou_a_funcionar_continua_em_andamento():
    voltou = _andamento(3, dataHoraParada="2026-10-10T08:00:00", dataHoraFuncionamento="2026-10-11T08:00:00")
    assert _gerar(_ctx([ELETRICISTA]), [voltou])[0]["status"] == "Em andamento"


def test_parada_so_se_aplica_a_situacao_em_andamento():
    aberta = os_neovero(4, "2026-10-10", situacao=1, responsavel="ELETRICISTA A", responsavel_id=2)
    aberta["dataHoraParada"] = "2026-10-10T08:00:00"
    assert _gerar(_ctx([ELETRICISTA]), [aberta])[0]["status"] == "Pendente"


def test_parada_conta_nos_totais_e_continua_exigindo_executante_valido():
    parada = _andamento(5, responsavel=SUPERVISAO, dataHoraParada="2026-10-10T08:00:00")
    oc = _gerar(_ctx([ELETRICISTA]), [parada])[0]
    assert oc["status"] == "Parada" and oc["revisao"] is True and oc["recomendado"] == "Eletricista A"
    assert "Parada" in prev.STATUS_ORDEM


def test_nomes_novos_dos_status_futuro_e_passado():
    assert prev.ST_PREVISTA == "Aguardando geração" and prev.ST_SEM_OS == "Sem OS – verificar"
    assert prev.classificar_status(None, date(2026, 10, 20), HOJE)[0] == "Aguardando geração"
    assert prev.classificar_status(None, date(2026, 10, 10), HOJE) == ("Sem OS – verificar", False)


def test_linhas_sem_recomendacao_mantem_rotulos_curtos_e_trazem_o_nome_do_responsavel():
    ctx = _ctx([ELETRICISTA])
    reais = [
        os_neovero(1, "2026-10-10", situacao=3, responsavel="ELETRICISTA A", responsavel_id=2, equip_id=1),     # concluída
        os_neovero(2, "2026-10-10", situacao=4, responsavel="ELETRICISTA A", responsavel_id=2, equip_id=2),     # cancelada
        os_neovero(3, "2026-10-14", situacao=1, responsavel="ELETRICISTA A", responsavel_id=2, equip_id=3),     # já atribuída
        _os(4, "PM - MENSAL - SPLIT"),                                                                              # gestor: recebe recomendação
    ]
    por = {o["os_vinculada"]: o for o in _gerar(ctx, reais)}
    assert [por[n]["sem_recomendacao_motivo"] for n in "123"] == ["Concluída", "Cancelada", "Já atribuída"]   # rótulos que ajudam a ler
    assert [por[n]["responsavel_nome"] for n in "123"] == ["ELETRICISTA A"] * 3                          # e o nome continua disponível
    assert all(por[n]["recomendado"] is None for n in "123")
    assert por["4"]["recomendado"] == "Eletricista A" and por["4"]["responsavel_nome"] == SUPERVISAO

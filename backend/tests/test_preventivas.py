"""
Modelo de preventivas (5.6): status de execução, atraso, casamento OS×projeção, filtros por
dia/período/status/turno, paginação e consistência de totais — mais a integração das regras
(gestão, limite diário, ronda) no gerador.
"""
from datetime import date, datetime, timezone

import pytest

from core import preventivas as prev
from core.motor_base import indicar_responsavel
from core.regras.atribuicao import resolver_regras
from tests.fakes import colaboradores_df, item_plano, os_neovero, plano_neovero
from units.brasilandia.regras import OFICINA_AR_COMPRIMIDO_VACUO, RONDA_DIARIA

REGRAS = [RONDA_DIARIA, OFICINA_AR_COMPRIMIDO_VACUO]    # a tabela das rondas está desativada no produto; aqui testa-se o mecanismo

HOJE = date(2026, 10, 14)


def _ctx(colab=None, regras=(), **kw):
    colab = colab if colab is not None else colaboradores_df([
        {"funcionario": "Eletricista A", "cargo": "Eletricista"},
        {"funcionario": "Clima A", "cargo": "Técnico de Climatização"},
        {"funcionario": "William de Souza Lobo", "cargo": "Supervisor de Manutenção", "turno": "Administrativo"},
    ])
    ativos = colab[colab["status"] == "Ativo"]
    return prev.ContextoGeracao(
        colab_ativos=ativos, colab_todos=colab, indicar=indicar_responsavel,
        regras_resolvidas=resolver_regras(list(regras), ativos) if regras else {}, hoje=HOJE, **kw)


def _gerar(ctx, os_periodo=(), planos=(), itens=None, ini=date(2026, 10, 1), fim=date(2026, 10, 31),
           abertas=(), atrasadas=True):
    return prev.gerar_ocorrencias(ctx, list(planos), itens or {}, list(os_periodo), list(abertas), ini, fim, atrasadas)


# ── status e atraso ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("situacao,dia,status,atrasada", [
    (3, date(2026, 10, 10), prev.ST_CONCLUIDA, False),     # fechada nunca atrasa
    (4, date(2026, 10, 10), prev.ST_CANCELADA, False),
    (1, date(2026, 10, 10), prev.ST_PENDENTE, True),       # aberta e data passada = atrasada
    (1, date(2026, 10, 14), prev.ST_PENDENTE, False),      # aberta hoje = ainda no prazo
    (1, date(2026, 10, 20), prev.ST_PENDENTE, False),
    (2, date(2026, 10, 10), prev.ST_EM_ANDAMENTO, True),
    (2, date(2026, 10, 14), prev.ST_EM_ANDAMENTO, False),
    (None, date(2026, 10, 20), prev.ST_PREVISTA, False),   # projeção futura
    (None, date(2026, 10, 14), prev.ST_PREVISTA, False),
    (None, date(2026, 10, 10), prev.ST_SEM_OS, False),     # projeção passada sem OS: NÃO é atraso
])
def test_classificar_status(situacao, dia, status, atrasada):
    assert prev.classificar_status(situacao, dia, HOJE) == (status, atrasada)


def test_hoje_local_usa_fuso_do_brasil_nao_utc():
    """Às 22h de 13/10 em Brasília já é 14/10 em UTC; 'hoje' deve continuar 13/10."""
    class Falso(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 14, 1, 0, tzinfo=timezone.utc)
    import core.preventivas as m
    original = m.datetime
    m.datetime = Falso
    try:
        assert m.hoje_local() == date(2026, 10, 13)
    finally:
        m.datetime = original


def test_os_sem_informacao_suficiente_nao_e_classificada_como_atrasada():
    """Item de plano com data base passada e OS ainda NÃO gerada/sincronizada: 'Sem OS gerada'."""
    plano = plano_neovero(1, "PM - MENSAL - SPLIT", periodicidade=1, unidade="M")
    itens = {1: [item_plano(100, "2026-10-05")]}
    ocs = _gerar(_ctx(), planos=[plano], itens=itens, ini=date(2026, 10, 1), fim=date(2026, 10, 10))
    assert len(ocs) == 1
    assert ocs[0]["status"] == prev.ST_SEM_OS and ocs[0]["atrasada"] is False


def test_os_aberta_com_data_passada_e_atrasada_e_concluida_nao():
    reais = [
        os_neovero(1001, "2026-10-05", situacao=1, responsavel="Eletricista A", responsavel_id=1),
        os_neovero(1002, "2026-10-05", situacao=3, responsavel="Eletricista A", responsavel_id=1, equip_id=11),
        os_neovero(1003, "2026-10-14", situacao=1, responsavel="Eletricista A", responsavel_id=1, equip_id=12),
    ]
    ocs = {o["os_vinculada"]: o for o in _gerar(_ctx(), os_periodo=reais)}
    assert ocs["1001"]["status"] == "Pendente" and ocs["1001"]["atrasada"] is True
    assert ocs["1002"]["status"] == "Concluída" and ocs["1002"]["atrasada"] is False
    assert ocs["1003"]["status"] == "Pendente" and ocs["1003"]["atrasada"] is False


# ── casamento OS real × projeção (sem duplicidade) ───────────────────────────

def test_projecao_com_os_real_no_mesmo_dia_nao_duplica():
    plano = plano_neovero(1, "PM - MENSAL - SPLIT")
    itens = {1: [item_plano(100, "2026-10-14", equip_id=10)]}
    real = os_neovero(2001, "2026-10-14", plano_id=1, equip_id=10, situacao=1, responsavel="Eletricista A", responsavel_id=1)
    ocs = _gerar(_ctx(), os_periodo=[real], planos=[plano], itens=itens)
    assert len(ocs) == 1 and ocs[0]["origem"] == "OS"


def test_cada_os_real_absorve_no_maximo_uma_projecao():
    plano = plano_neovero(1, "PM - DIÁRIO - X", periodicidade=1, unidade="D")
    itens = {1: [item_plano(100, "2026-10-14", equip_id=10)]}
    real = os_neovero(2002, "2026-10-14", plano_id=1, equip_id=10, periodicidade=1, unidade_tempo="D")
    ocs = _gerar(_ctx(), os_periodo=[real], planos=[plano], itens=itens, ini=date(2026, 10, 14), fim=date(2026, 10, 16))
    origens = sorted((o["data_iso"], o["origem"]) for o in ocs)
    assert origens == [("2026-10-14", "OS"), ("2026-10-15", "Plano"), ("2026-10-16", "Plano")]


def test_os_fora_do_periodo_selecionado_nao_aparece():
    reais = [os_neovero(3001, "2026-09-10", situacao=3)]
    assert _gerar(_ctx(), os_periodo=reais, ini=date(2026, 10, 1), fim=date(2026, 10, 31)) == []


def test_atrasadas_de_dias_anteriores_entram_so_quando_pedido():
    antiga = os_neovero(4001, "2026-09-20", situacao=1, responsavel="Eletricista A", responsavel_id=1)
    com = _gerar(_ctx(), abertas=[antiga], ini=date(2026, 10, 14), fim=date(2026, 10, 14), atrasadas=True)
    sem = _gerar(_ctx(), abertas=[antiga], ini=date(2026, 10, 14), fim=date(2026, 10, 14), atrasadas=False)
    assert [o["os_vinculada"] for o in com] == ["4001"] and com[0]["atrasada"] is True
    assert sem == []


# ── responsável: gestão / genérico / desligado (5.1 e 5.2) ───────────────────

def test_os_em_nome_do_gestor_e_sinalizada_e_recebe_executante_recomendado():
    real = os_neovero(5001, "2026-10-14", situacao=1, responsavel="WILLIAN DE SOUZA LOBO", responsavel_id=31,
                      plano="PM - MENSAL - QUADROS ELÉTRICOS", oficina="ELÉTRICA/QGBT")
    oc = _gerar(_ctx(), os_periodo=[real])[0]
    assert oc["responsavel_status"] == prev.RESP_GESTAO
    assert oc["revisao"] is True
    assert oc["recomendado"] == "Eletricista A"          # nunca o gestor
    assert oc["recomendado"] != "William de Souza Lobo"


def test_responsavel_generico_do_neovero_e_sinalizado():
    real = os_neovero(5002, "2026-10-14", situacao=1, responsavel="ELÉTRICA - DIURNO", responsavel_id=67,
                      plano="PM - DIÁRIO - RONDA - NOBREAK", oficina="ELÉTRICA/QGBT")
    oc = _gerar(_ctx(), os_periodo=[real])[0]
    assert oc["responsavel_status"] == prev.RESP_GENERICO and oc["revisao"] is True


def test_os_aberta_em_nome_de_desligado_e_sinalizada_sem_reatribuir_historico():
    colab = colaboradores_df([
        {"funcionario": "Caio Cezar Santos Pereira", "cargo": "Eletricista", "data_desligamento": "2026-09-18"},
        {"funcionario": "Eletricista A", "cargo": "Eletricista"},
    ])
    aberta = os_neovero(5003, "2026-10-14", situacao=1, responsavel="CAIO CEZAR SANTOS PEREIRA", responsavel_id=9)
    fechada = os_neovero(5004, "2026-09-10", situacao=3, responsavel="CAIO CEZAR SANTOS PEREIRA", responsavel_id=9,
                         equip_id=11)
    ocs = {o["os_vinculada"]: o for o in _gerar(_ctx(colab), os_periodo=[aberta, fechada],
                                                ini=date(2026, 9, 1), fim=date(2026, 10, 31))}
    assert ocs["5003"]["responsavel_status"] == prev.RESP_DESLIGADO and ocs["5003"]["revisao"] is True
    # histórico concluído: intocado — sem recomendação, sem revisão
    assert ocs["5004"]["status"] == "Concluída" and ocs["5004"]["revisao"] is False
    assert ocs["5004"]["recomendado"] is None and ocs["5004"]["responsavel_atual"] == "CAIO CEZAR SANTOS PEREIRA"


def test_os_com_executante_valido_nao_e_reatribuida_nem_recomendada():
    real = os_neovero(5005, "2026-10-14", situacao=1, responsavel="ELETRICISTA A", responsavel_id=2)
    oc = _gerar(_ctx(), os_periodo=[real])[0]
    assert oc["responsavel_status"] == prev.RESP_ATRIBUIDA
    assert oc["recomendado"] is None and oc["revisao"] is False


def test_sem_executante_apto_vira_sem_candidato_e_nunca_o_gestor():
    colab = colaboradores_df([{"funcionario": "William de Souza Lobo", "cargo": "Supervisor de Manutenção"}])
    real = os_neovero(5006, "2026-10-14", situacao=1, responsavel="WILLIAN DE SOUZA LOBO", responsavel_id=31)
    oc = _gerar(_ctx(colab), os_periodo=[real])[0]
    assert oc["recomendado"] is None and oc["sem_candidato"] is True
    assert oc["motivo_sem_candidato"]


# ── limite diário dentro do gerador (sem dupla contagem) ─────────────────────

def test_gerador_escala_todas_mas_sinaliza_intervencao_alem_das_14_por_dia():
    colab = colaboradores_df([{"funcionario": "Unico Eletricista", "cargo": "Eletricista"}])
    reais = [os_neovero(6000 + i, "2026-10-14", situacao=1, responsavel="WILLIAN DE SOUZA LOBO", responsavel_id=31,
                        equip_id=100 + i, plano="PM - MENSAL - QUADROS ELÉTRICOS", oficina="ELÉTRICA/QGBT")
             for i in range(20)]
    ctx = _ctx(colab)
    ocs = _gerar(ctx, os_periodo=reais)
    com = [o for o in ocs if o["recomendado"]]
    assert len(com) == 20 and not [o for o in ocs if o["sem_candidato"]]        # nenhuma fica sem escalar
    acima = [o for o in ocs if o["requer_intervencao"]]
    assert len(acima) == 6 and all(o["recomendado"] == "Unico Eletricista" for o in acima)
    assert all("Limite diário" in o["motivo_intervencao"] and "(limite 14)" in o["motivo_intervencao"] for o in acima)
    assert not any(o["requer_intervencao"] for o in com if o not in acima)       # as 14 primeiras sem aviso
    assert prev.totais(ocs)["requer_intervencao"] == 6


def test_os_reais_ja_atribuidas_consomem_o_limite_do_dia_e_nao_sao_contadas_duas_vezes():
    colab = colaboradores_df([{"funcionario": "Unico Eletricista", "cargo": "Eletricista"}])
    ja_dele = [os_neovero(7000 + i, "2026-10-14", situacao=1, responsavel="UNICO ELETRICISTA", responsavel_id=2,
                          equip_id=200 + i) for i in range(13)]
    para_atribuir = [os_neovero(7100 + i, "2026-10-14", situacao=1, responsavel="WILLIAN DE SOUZA LOBO",
                                responsavel_id=31, equip_id=300 + i, plano="PM - QUADRO ELÉTRICO",
                                oficina="ELÉTRICA/QGBT") for i in range(3)]
    ctx = _ctx(colab)
    ocs = _gerar(ctx, os_periodo=ja_dele + para_atribuir)
    novas = [o for o in ocs if o["recomendado"]]
    assert len(novas) == 3                                                       # as 3 são escaladas
    assert sum(1 for o in novas if o["requer_intervencao"]) == 2                 # 13 + 1 = 14; a 2ª e a 3ª passam do limite
    assert not any(o["sem_candidato"] for o in ocs)
    assert ctx.ocupacao.total("Unico Eletricista", date(2026, 10, 14)) == 16


def test_ocupacao_e_independente_por_dia():
    colab = colaboradores_df([{"funcionario": "Unico Eletricista", "cargo": "Eletricista"}])
    reais = [os_neovero(8000 + i, f"2026-10-{14 + (i % 2):02d}", situacao=1, responsavel="WILLIAN DE SOUZA LOBO",
                        responsavel_id=31, equip_id=400 + i, plano="PM - QUADRO ELÉTRICO", oficina="ELÉTRICA/QGBT")
             for i in range(20)]   # 10 em cada dia
    ocs = _gerar(_ctx(colab), os_periodo=reais)
    assert all(o["recomendado"] == "Unico Eletricista" for o in ocs)


# ── regra de ronda integrada ao gerador ──────────────────────────────────────

def test_ronda_diurna_impar_e_atribuida_ao_responsavel_da_regra():
    colab = colaboradores_df([
        {"funcionario": "Iranildo Silva dos Santos", "cargo": "Eletricista", "regime": "Ímpar"},
        {"funcionario": "Outro Eletricista", "cargo": "Eletricista"},
    ])
    real = os_neovero(9001, "2026-10-13", situacao=1, responsavel="ELÉTRICA - DIURNO", responsavel_id=67,
                      plano="PM - DIÁRIO - RONDA – NOBREAK", oficina="ELÉTRICA/QGBT", tipo="RONDA", tipo_id=8,
                      periodicidade=1, unidade_tempo="D")
    oc = _gerar(_ctx(colab, regras=REGRAS), os_periodo=[real], ini=date(2026, 10, 13), fim=date(2026, 10, 13))[0]
    assert oc["recomendado"] == "Iranildo Silva dos Santos"
    assert oc["regra"]["status"] == "aplicada"


def test_ronda_com_regra_pendente_fica_sem_candidato_com_motivo():
    colab = colaboradores_df([
        {"funcionario": "Michael de Campos Eguez", "cargo": "Eletricista", "regime": "Par"},
        {"funcionario": "Michael Kelvin de Abreu Moraes", "cargo": "Aux. Manutenção Elétrica", "regime": "Par"},
    ])
    real = os_neovero(9002, "2026-10-14", situacao=1, responsavel="ELÉTRICA - DIURNO", responsavel_id=67,
                      plano="PM - DIÁRIO - RONDA – NOBREAK", oficina="ELÉTRICA/QGBT", tipo="RONDA", tipo_id=8,
                      periodicidade=1, unidade_tempo="D")
    oc = _gerar(_ctx(colab, regras=REGRAS), os_periodo=[real], ini=date(2026, 10, 14), fim=date(2026, 10, 14))[0]
    assert oc["recomendado"] is None and oc["sem_candidato"] is True
    assert "Michael" in oc["motivo_sem_candidato"] and oc["regra"]["status"] == "pendente"


def test_oficina_ac_vacuo_dia_par_recomenda_os_dois_responsaveis():
    colab = colaboradores_df([
        {"funcionario": "Douglas Rodrigues", "cargo": "Técnico de Climatização", "regime": "Par"},
        {"funcionario": "Gustavo Rafael Pereira Vargas", "cargo": "Aux. Manutenção / Climatização", "regime": "Par"},
        {"funcionario": "Israel Pereira Bomfim", "cargo": "Técnico de Climatização", "regime": "Ímpar"},
    ])
    real = os_neovero(9003, "2026-10-14", situacao=1, responsavel="ISRAEL PEREIRA BOMFIM", responsavel_id=15,
                      plano="PM - DIÁRIA - AR COMPRIMIDO", oficina="AR COMPRIMIDO E VÁCUO", periodicidade=1,
                      unidade_tempo="D")
    ctx = _ctx(colab, regras=REGRAS)
    # Israel (ímpar) consta como responsável atual, mas é dia PAR: a OS não é 'reatribuída' por isso;
    # aqui testamos a regra sobre uma OS ainda sem executante válido
    real["responsavel"], real["responsavelId"] = None, None
    oc = _gerar(ctx, os_periodo=[real], ini=date(2026, 10, 14), fim=date(2026, 10, 14))[0]
    assert set(oc["recomendados"]) == {"Douglas Rodrigues", "Gustavo Rafael Pereira Vargas"}
    assert oc["recomendado"] in oc["recomendados"]


# ── filtros / totais / paginação ─────────────────────────────────────────────

def _massa():
    reais = [
        os_neovero(10001, "2026-10-10", situacao=3, responsavel="ELETRICISTA A", responsavel_id=2, equip_id=1,
                   plano="PM - NOTURNO - A"),
        os_neovero(10002, "2026-10-10", situacao=1, responsavel="ELETRICISTA A", responsavel_id=2, equip_id=2),
        os_neovero(10003, "2026-10-12", situacao=2, responsavel="ELETRICISTA A", responsavel_id=2, equip_id=3),
        os_neovero(10004, "2026-10-14", situacao=1, responsavel="ELETRICISTA A", responsavel_id=2, equip_id=4),
        os_neovero(10005, "2026-10-14", situacao=3, responsavel="CLIMA A", responsavel_id=3, equip_id=5),
        os_neovero(10006, "2026-10-20", situacao=1, responsavel="WILLIAN DE SOUZA LOBO", responsavel_id=31, equip_id=6),
    ]
    return _gerar(_ctx(), os_periodo=reais, ini=date(2026, 10, 1), fim=date(2026, 10, 31))


def test_filtro_por_dias_selecionados_nao_contiguos():
    massa = _massa()
    r = prev.filtrar(massa, {"dias": "2026-10-10,2026-10-14"})
    assert sorted(o["os_vinculada"] for o in r) == ["10001", "10002", "10004", "10005"]


def test_filtro_por_intervalo_inclusivo_nas_duas_pontas():
    massa = _massa()
    r = prev.filtrar(massa, {"data_ini": "2026-10-12", "data_fim": "2026-10-14"})
    assert sorted(o["os_vinculada"] for o in r) == ["10003", "10004", "10005"]


def test_filtro_por_status_e_atraso():
    massa = _massa()
    assert {o["os_vinculada"] for o in prev.filtrar(massa, {"status": "Concluída"})} == {"10001", "10005"}
    assert {o["os_vinculada"] for o in prev.filtrar(massa, {"atrasada": True})} == {"10002", "10003"}
    assert {o["os_vinculada"] for o in prev.filtrar(massa, {"status": ["Pendente", "Em andamento"], "atrasada": True})} \
        == {"10002", "10003"}


def test_filtros_combinados_dia_status_e_responsavel():
    massa = _massa()
    r = prev.filtrar(massa, {"dias": ["2026-10-14"], "status": "Concluída", "responsavel": "clima"})
    assert [o["os_vinculada"] for o in r] == ["10005"]


def test_filtro_de_revisao_acha_a_os_em_nome_do_gestor():
    massa = _massa()
    assert [o["os_vinculada"] for o in prev.filtrar(massa, {"revisao": True})] == ["10006"]


def test_filtro_de_turno_usa_o_turno_declarado_no_plano():
    massa = _massa()
    assert [o["os_vinculada"] for o in prev.filtrar(massa, {"turno": "Noturno"})] == ["10001"]
    assert len(prev.filtrar(massa, {"turno": "—"})) == len(massa) - 1


def test_totais_batem_com_a_lista_e_com_a_soma_por_status():
    massa = _massa()
    t = prev.totais(massa)
    assert t["total"] == len(massa) == sum(t["por_status"].values())
    assert t["atrasadas"] == sum(1 for o in massa if o["atrasada"]) == 2
    assert prev.totais(prev.filtrar(massa, {"status": "Concluída"}))["total"] == 2


def test_paginacao_cobre_todos_os_itens_sem_repetir():
    massa = _massa()
    paginas = [prev.paginar_lista(massa, p, 4) for p in (1, 2, 3)]
    ids = [o["id"] for pg in paginas for o in pg]
    assert len(ids) == len(massa) == len(set(ids))
    assert prev.paginar_lista(massa, 99, 4) == []


def test_ordenacao_por_data():
    datas = [o["data_iso"] for o in _massa()]
    assert datas == sorted(datas)


def test_campos_privados_nao_vazam_para_a_api():
    for o in _massa():
        assert not [k for k in o if k.startswith("_")]


def test_tipo_isento_nao_consome_nem_consulta_o_limite_diario(monkeypatch):
    """Ponto de decisão da supervisão: se as rondas (tipo 8) forem isentas, passam do teto de 14."""
    from core.regras import limites
    colab = colaboradores_df([{"funcionario": "Unico Eletricista", "cargo": "Eletricista"}])
    reais = [os_neovero(9100 + i, "2026-10-14", situacao=1, responsavel="WILLIAN DE SOUZA LOBO", responsavel_id=31,
                        equip_id=500 + i, plano="PM - DIÁRIO - RONDA - NOBREAK", oficina="ELÉTRICA/QGBT", tipo="RONDA",
                        tipo_id=8, periodicidade=1, unidade_tempo="D") for i in range(20)]
    padrao = _gerar(_ctx(colab), os_periodo=reais)
    assert sum(1 for o in padrao if o["recomendado"] and not o["requer_intervencao"]) == 14          # padrão: tudo conta (as demais, com aviso)
    monkeypatch.setattr(limites, "TIPO_IDS_ISENTOS_LIMITE", frozenset({8}))
    isento = _gerar(_ctx(colab), os_periodo=reais)
    assert sum(1 for o in isento if o["recomendado"] and not o["requer_intervencao"]) == 20       # isento: nenhum aviso


def test_projecao_com_a_os_aberta_vinculada_nao_duplica_a_os_real_de_outra_data():
    """Achado com dados reais (HMB): item com data base antiga (07/09) cuja OS aberta (nº 9001) foi aberta em 06/10.
    A OS real e a projeção são a MESMA manutenção — contar as duas inflava pendentes e atrasadas."""
    plano = plano_neovero(1, "PM - MENSAL - SPLIT")
    item = item_plano(100, "2026-09-07", equip_id=10, os_ligada={"id": 9001, "numero": "9001", "situacao": 1})
    real = os_neovero(9001, "2026-10-06", plano_id=1, equip_id=10, situacao=1, responsavel="Eletricista A", responsavel_id=1)
    ocs = _gerar(_ctx(), os_periodo=[real], planos=[plano], itens={1: [item]}, ini=date(2026, 9, 1), fim=date(2026, 10, 31))
    com_a_os = [o for o in ocs if o["os_vinculada"] == "9001"]
    assert len(com_a_os) == 1 and com_a_os[0]["origem"] == "OS"
    assert sum(1 for o in ocs if o["atrasada"]) == 1          # só a OS real (06/10 < hoje 14/10)


def test_projecao_com_os_vinculada_fora_da_lista_real_continua_aparecendo():
    """Se a OS vinculada não está entre as OS reais carregadas, a projeção é a única representação dela."""
    plano = plano_neovero(1, "PM - MENSAL - SPLIT")
    item = item_plano(100, "2026-10-10", equip_id=10, os_ligada={"id": 9002, "numero": "9002", "situacao": 1})
    ocs = _gerar(_ctx(), planos=[plano], itens={1: [item]}, ini=date(2026, 10, 1), fim=date(2026, 10, 31))
    ligada = [o for o in ocs if o["os_vinculada"] == "9002"]
    assert len(ligada) == 1 and ligada[0]["origem"] == "Plano" and ligada[0]["status"] == "Pendente"

"""
Histórico de responsável das OS (transferências observadas), planos com responsável padrão inválido e
isolamento entre unidades.
"""
from datetime import date

from sqlalchemy import select

from core import os_historico, preventivas as prev
from core.db import sessao
from core.models import OsResponsavelHistorico
from core.motor_base import indicar_responsavel
from tests.conftest import fazer_login
from tests.fakes import colaboradores_df, os_neovero, plano_neovero
from tests.test_api_unidade import P, _get, _massa, ana, neovero  # noqa: F401  (fixtures reaproveitadas)


def _vista(numero, responsavel, plano="PM - X"):
    return {"os_numero": numero, "os_id": int(numero), "plano": plano, "responsavel": responsavel}


# ── núcleo ───────────────────────────────────────────────────────────────────

def test_primeira_leitura_vira_registro_inicial_e_nao_transferencia(app):
    assert os_historico.registrar_observacoes("HMB", [_vista("100", "Fulano A")]) == 1
    assert os_historico.listar("HMB") == []                                     # só transferências por padrão
    (r,) = os_historico.listar("HMB", so_transferencias=False)
    assert r["tipo"] == "inicial" and r["para"] == "Fulano A" and r["de"] is None


def test_mudar_de_responsavel_gera_transferencia_e_repetir_a_leitura_nao_duplica(app):
    os_historico.registrar_observacoes("HMB", [_vista("200", "Fulano A")])
    assert os_historico.registrar_observacoes("HMB", [_vista("200", "Fulano A")]) == 0     # sem mudança: nada novo
    assert os_historico.registrar_observacoes("HMB", [_vista("200", "Beltrano B")]) == 1
    (t,) = os_historico.listar("HMB")
    assert (t["de"], t["para"], t["tipo"]) == ("Fulano A", "Beltrano B", "transferencia")
    assert os_historico.registrar_observacoes("HMB", [_vista("200", "Beltrano B")]) == 0


def test_volta_ao_responsavel_anterior_tambem_e_registrada_e_historico_completo_e_ordenado(app):
    for nome in ("A", "B", "A"):
        os_historico.registrar_observacoes("HMB", [_vista("300", nome)])
    trocas = os_historico.listar("HMB", os_numero="300")
    assert [(t["de"], t["para"]) for t in trocas] == [("B", "A"), ("A", "B")]      # mais recente primeiro
    assert len(os_historico.listar("HMB", os_numero="300", so_transferencias=False)) == 3


def test_ficar_sem_responsavel_e_registrado_como_transferencia_para_vazio(app):
    os_historico.registrar_observacoes("HMB", [_vista("400", "A")])
    os_historico.registrar_observacoes("HMB", [_vista("400", None)])
    (t,) = os_historico.listar("HMB")
    assert t["de"] == "A" and t["para"] is None


def test_o_historico_nao_cruza_unidades_mesmo_com_o_mesmo_numero_de_os(app):
    os_historico.registrar_observacoes("HMB", [_vista("500", "A")])
    os_historico.registrar_observacoes("HETRIN", [_vista("500", "Z")])
    os_historico.registrar_observacoes("HMB", [_vista("500", "B")])
    assert [(t["de"], t["para"]) for t in os_historico.listar("HMB")] == [("A", "B")]
    assert os_historico.listar("HETRIN") == []


def test_motivo_e_anotado_por_pessoa_dentro_da_unidade_e_limitado(app):
    os_historico.registrar_observacoes("HMB", [_vista("600", "A")])
    os_historico.registrar_observacoes("HMB", [_vista("600", "B")])
    (t,) = os_historico.listar("HMB")
    assert os_historico.anotar_motivo("HETRIN", t["id"], "tentativa de outra unidade", "x") is None
    r = os_historico.anotar_motivo("HMB", t["id"], "  Troca de   turno  " + "z" * 400, "ana.hmb")
    assert r["motivo"].startswith("Troca de turno") and len(r["motivo"]) == os_historico.MOTIVO_MAX and r["motivo_por"] == "ana.hmb"
    assert os_historico.anotar_motivo("HMB", t["id"], "", "ana.hmb")["motivo"] is None


def test_o_registro_e_append_only_a_leitura_nao_apaga_linhas(app):
    os_historico.registrar_observacoes("HMB", [_vista("700", "A")])
    os_historico.registrar_observacoes("HMB", [_vista("700", "B")])
    os_historico.registrar_observacoes("HMB", [])
    with sessao() as s:
        assert len(s.scalars(select(OsResponsavelHistorico)).all()) == 2


# ── via API: gerar preventivas observa; /transferencias lista; motivo é auditado ─

def test_gerar_preventivas_registra_responsavel_e_detecta_transferencia(ana, neovero):
    _massa(neovero)
    assert _get(ana).status_code == 200
    assert os_historico.listar("HMB") == []                                   # 1ª leitura: baseline
    neovero.os_periodo[1]["responsavel"] = {"id": 3, "nome": "MICHAEL DE CAMPOS EGUEZ"}    # OS 2 mudou de dono no Neovero
    neovero.os_periodo[1]["responsavelId"] = 3
    assert _get(ana, refresh="1").status_code == 200
    d = ana.get(f"{P}/transferencias").get_json()
    assert d["total"] == 1 and d["itens"][0]["os_numero"] == "2"
    assert (d["itens"][0]["de"], d["itens"][0]["para"]) == ("CLIMA UM", "MICHAEL DE CAMPOS EGUEZ")
    assert "não são conhecidas" in d["nota"]
    assert ana.get(f"{P}/transferencias", query_string={"os": "3"}).get_json()["total"] == 0


def test_transferencias_da_hmb_nao_aparecem_para_a_hetrin_e_exigem_login(app, ana, neovero, criar_usuarios):
    os_historico.registrar_observacoes("HMB", [_vista("800", "A")])
    os_historico.registrar_observacoes("HMB", [_vista("800", "B")])
    assert app.test_client().get(f"{P}/transferencias").status_code == 401
    beto = app.test_client()
    fazer_login(beto, "beto.hetrin", criar_usuarios)
    assert beto.get(f"{P}/transferencias").status_code == 403                    # unidade errada: recusado pela guarda
    assert beto.get("/api/grandmassif/transferencias").status_code in (200, 502, 503)   # a sua própria, sem dados da HMB


def test_anotar_motivo_via_api_e_registrado_na_auditoria(ana, neovero):
    os_historico.registrar_observacoes("HMB", [_vista("900", "A")])
    os_historico.registrar_observacoes("HMB", [_vista("900", "B")])
    (t,) = os_historico.listar("HMB")
    r = ana.put(f"{P}/transferencias/{t['id']}/motivo", json={"motivo": "Equipe reorganizada"})
    assert r.status_code == 200 and r.get_json()["motivo"] == "Equipe reorganizada"
    assert ana.put(f"{P}/transferencias/99999/motivo", json={"motivo": "x"}).status_code == 404
    from core.models import AuditLog
    with sessao() as s:
        ev = s.scalars(select(AuditLog).where(AuditLog.path == f"{P}/transferencias/{t['id']}/motivo")).all()
    assert ev and ev[-1].username == "ana.hmb" and ev[-1].action == "update"


# ── planos cujo responsável padrão não é executante válido ───────────────────

def _ctx():
    colab = colaboradores_df([
        {"funcionario": "Eletricista A", "cargo": "Eletricista"},
        {"funcionario": "Carlos Aurélio de Carvalho", "cargo": "Aux. Manutenção / Climatização", "status": "Desligado",
         "data_desligamento": "2026-09-11"},
        {"funcionario": "William de Souza Lobo", "cargo": "Gerente de Equipe / Engenheira", "turno": "Administrativo"},
    ])
    return prev.ContextoGeracao(colab_ativos=colab[colab["status"] == "Ativo"], colab_todos=colab, indicar=indicar_responsavel,
                                hoje=date(2026, 10, 14))


def _plano(pid, rid, ativo=True):
    p = plano_neovero(pid, f"PLANO {pid}")
    p["responsavelId"], p["ativo"] = rid, ativo
    return p


def test_planos_com_responsavel_padrao_invalido_sao_listados_com_o_motivo_e_as_os_afetadas():
    abertas = [
        os_neovero(1, "2026-10-14", plano_id=1, responsavel="ELETRICISTA A", responsavel_id=10),
        os_neovero(2, "2026-10-14", plano_id=2, responsavel="CARLOS AURELIO DE CARVALHO", responsavel_id=20, equip_id=2),
        os_neovero(3, "2026-10-14", plano_id=2, responsavel="CARLOS AURELIO DE CARVALHO", responsavel_id=20, equip_id=3),
        os_neovero(4, "2026-10-14", plano_id=3, responsavel="WILLIAN DE SOUZA LOBO", responsavel_id=30, equip_id=4),
    ]
    planos = [_plano(1, 10), _plano(2, 20), _plano(3, 30), _plano(4, 99), _plano(5, None), _plano(6, 20, ativo=False)]
    por_plano = {x["plano_id"]: x for x in prev.planos_com_responsavel_invalido(planos, abertas, _ctx())}
    assert 1 not in por_plano                                                    # executante válido: não aparece
    assert por_plano[2]["status"] == "Desligado" and por_plano[2]["os_abertas"] == 2
    assert por_plano[3]["status"] == "Gestão"
    assert por_plano[4]["status"] == "Não identificado" and por_plano[4]["responsavel_nome"] is None   # sem OS para resolver o nome
    assert por_plano[5]["status"] == "Sem responsável"
    assert 6 not in por_plano                                                    # plano inativo ignorado


def test_revisao_via_api_traz_os_planos_com_responsavel_invalido(ana, neovero):
    _massa(neovero)
    neovero.planos[0]["responsavelId"] = 31          # o mesmo id do gestor das OS de _massa
    d = ana.get(f"{P}/revisao").get_json()
    assert d["planos_responsavel_invalido"][0]["status"] == "Gestão"
    assert "cargo_fora_da_regra" in d and d["cargo_fora_da_regra"] == []         # HMB: sem regra de cargo

"""
Fila de conferência e aplicação de executantes no Neovero (5.7): idempotência, compare-and-set,
conferência da unidade, limite diário, escrita desligada por padrão, simulação, auditoria e
tolerância a falhas. NENHUM teste faz requisição real ao Neovero.
"""
import pytest
from sqlalchemy import select

from core import atribuicoes
from core.db import sessao
from core.models import AtribuicaoProposta, AuditLog
from tests.conftest import fazer_login
from tests.fakes import os_neovero
from tests.test_api_unidade import P, NeoveroFalso, ana, neovero  # noqa: F401  (fixtures reutilizadas)


@pytest.fixture()
def cenario(neovero):
    """OS 51 aberta em nome do gestor (a corrigir); histórico traz o id do Neovero de 'Iranildo'."""
    neovero.os_periodo = [
        os_neovero(51, "2026-10-13", situacao=1, responsavel="WILLIAN DE SOUZA LOBO", responsavel_id=31,
                   plano="PM - MENSAL - QUADROS ELÉTRICOS", oficina="ELÉTRICA/QGBT", os_id=5100, equip_id=51),
        os_neovero(52, "2026-10-12", situacao=3, responsavel="IRANILDO SILVA DOS SANTOS", responsavel_id=5,
                   os_id=5200, equip_id=52),
    ]
    neovero.os_abertas = [neovero.os_periodo[0]]
    return neovero


def _fila(c):
    return c.get(f"{P}/atribuicoes", query_string={"data_ini": "2026-10-13", "data_fim": "2026-10-13"}).get_json()


def test_fila_lista_os_em_nome_de_gestao_com_executante_proposto_e_id_neovero(ana, cenario):
    d = _fila(ana)
    assert len(d["fila"]) == 1
    f = d["fila"][0]
    assert f["os_numero"] == "51" and f["responsavel_status"] == "Gestão" and f["responsavel_atual"] == "WILLIAN DE SOUZA LOBO"
    assert f["proposto"] == "Iranildo Silva dos Santos" and f["neovero_funcionario_id"] == 5 and f["automatizavel"] is True


def test_integracao_vem_desabilitada_e_em_simulacao_por_padrao(ana, cenario):
    integ = _fila(ana)["integracao"]
    assert integ["escrita_habilitada"] is False and integ["simulacao"] is True
    assert "não foi validada" in integ["aviso"]


def test_sem_id_neovero_conhecido_a_os_nao_e_automatizavel(ana, cenario):
    cenario.os_periodo = cenario.os_periodo[:1]       # some o histórico que revelava o id de Iranildo
    cenario.os_abertas = cenario.os_periodo[:1]
    f = _fila(ana)["fila"][0]
    assert f["automatizavel"] is False and "sem correspondência" in f["motivo"].lower()


def _propor(c):
    return c.post(f"{P}/atribuicoes/propostas", json={"data_ini": "2026-10-13", "data_fim": "2026-10-13", "os_ids": [5100]})


def test_proposta_e_idempotente_nao_duplica(ana, cenario):
    r1 = _propor(ana).get_json()["resultado"][0]
    r2 = _propor(ana).get_json()["resultado"][0]
    assert r1["criada"] is True and r2["criada"] is False and r1["id"] == r2["id"]
    with sessao() as s:
        assert len(s.scalars(select(AtribuicaoProposta)).all()) == 1
        p = s.scalars(select(AtribuicaoProposta)).one()
        assert p.status == "proposta" and p.responsavel_original_id == 31 and p.neovero_funcionario_id == 5
        assert p.unit == "HMB" and p.criado_por == "ana.hmb"


def test_so_proposta_aprovada_e_processada(ana, cenario):
    pid = _propor(ana).get_json()["resultado"][0]["id"]
    r = ana.post(f"{P}/atribuicoes/processar", json={"ids": [pid], "modo": "simular"}).get_json()["resultado"][0]
    assert r["status"] == "proposta" and "aprovadas" in r["mensagem"]


@pytest.fixture()
def aprovada(ana, cenario, monkeypatch):
    pid = _propor(ana).get_json()["resultado"][0]["id"]
    assert ana.post(f"{P}/atribuicoes/decisao", json={"ids": [pid], "acao": "aprovar"}).get_json()["atualizadas"] == 1
    return pid


def _os_fresca(**ov):
    base = {"id": 5100, "numero": "51", "situacao": 1, "responsavelId": 31, "empresa": {"id": 2}}
    return {**base, **ov}


def test_aplicar_com_escrita_desabilitada_responde_409(ana, aprovada):
    r = ana.post(f"{P}/atribuicoes/processar", json={"ids": [aprovada], "modo": "aplicar"})
    assert r.status_code == 409 and r.get_json()["codigo"] == "escrita_desabilitada"


def test_simulacao_valida_contra_o_neovero_mas_nao_escreve(ana, aprovada, monkeypatch):
    escritas = []
    monkeypatch.setattr(atribuicoes, "buscar_os", lambda h, i: _os_fresca())
    monkeypatch.setattr(atribuicoes, "_contar_os_do_dia", lambda *a: 3)
    monkeypatch.setattr(atribuicoes, "_requisitar", lambda *a, **k: escritas.append(a) or None)
    r = ana.post(f"{P}/atribuicoes/processar", json={"ids": [aprovada], "modo": "simular"}).get_json()["resultado"][0]
    assert r["status"] == "simulada" and escritas == []
    with sessao() as s:
        ev = s.scalars(select(AuditLog).where(AuditLog.event == "assignment_apply")).one()
        assert ev.result == "success" and '"escreveu": false' in ev.details and ev.resource == "51"


def test_aplicar_habilitado_mas_em_dry_run_nao_escreve(ana, aprovada, monkeypatch):
    monkeypatch.setenv("NEOVERO_WRITE_ENABLED", "true")           # DRY_RUN continua true (padrão)
    escritas = []
    monkeypatch.setattr(atribuicoes, "buscar_os", lambda h, i: _os_fresca())
    monkeypatch.setattr(atribuicoes, "_contar_os_do_dia", lambda *a: 0)
    monkeypatch.setattr(atribuicoes, "_requisitar", lambda *a, **k: escritas.append(a))
    r = ana.post(f"{P}/atribuicoes/processar", json={"ids": [aprovada], "modo": "aplicar"}).get_json()["resultado"][0]
    assert r["status"] == "simulada" and escritas == []


def test_aplicar_de_verdade_confirma_por_leitura_e_registra(ana, aprovada, monkeypatch):
    monkeypatch.setenv("NEOVERO_WRITE_ENABLED", "true")
    monkeypatch.setenv("NEOVERO_WRITE_DRY_RUN", "false")
    estado = {"resp": 31}
    enviados = []

    class Resp:
        status_code = 200

    def fake_req(metodo, caminho, headers, json_body=None, tentativas=2):
        enviados.append((metodo, caminho, json_body))
        estado["resp"] = json_body["responsavelId"]
        return Resp()

    monkeypatch.setattr(atribuicoes, "buscar_os", lambda h, i: _os_fresca(responsavelId=estado["resp"]))
    monkeypatch.setattr(atribuicoes, "_contar_os_do_dia", lambda *a: 0)
    monkeypatch.setattr(atribuicoes, "_requisitar", fake_req)
    r = ana.post(f"{P}/atribuicoes/processar", json={"ids": [aprovada], "modo": "aplicar"}).get_json()["resultado"][0]
    assert r["status"] == "aplicada"
    assert enviados == [("PATCH", "/api/ordensservico/5100", {"responsavelId": 5})]
    # reaplicar a mesma proposta não escreve de novo (idempotência: status final)
    r2 = ana.post(f"{P}/atribuicoes/processar", json={"ids": [aprovada], "modo": "aplicar"}).get_json()["resultado"][0]
    assert r2["status"] == "aplicada" and len(enviados) == 1


def test_conflito_se_o_responsavel_mudou_desde_a_proposta_nao_sobrescreve(ana, aprovada, monkeypatch):
    monkeypatch.setenv("NEOVERO_WRITE_ENABLED", "true")
    monkeypatch.setenv("NEOVERO_WRITE_DRY_RUN", "false")
    monkeypatch.setattr(atribuicoes, "buscar_os", lambda h, i: _os_fresca(responsavelId=77))   # alguém já mexeu
    monkeypatch.setattr(atribuicoes, "_requisitar", lambda *a, **k: pytest.fail("não podia escrever"))
    r = ana.post(f"{P}/atribuicoes/processar", json={"ids": [aprovada], "modo": "aplicar"}).get_json()["resultado"][0]
    assert r["status"] == "conflito" and "mudou" in r["mensagem"]


@pytest.mark.parametrize("fresca,esperado", [
    (_os_fresca(empresa={"id": 3}), "outra unidade"),
    (_os_fresca(numero="999"), "divergente"),
    (_os_fresca(situacao=3), "não está mais"),
])
def test_validacoes_de_seguranca_antes_de_escrever(ana, aprovada, monkeypatch, fresca, esperado):
    monkeypatch.setenv("NEOVERO_WRITE_ENABLED", "true")
    monkeypatch.setenv("NEOVERO_WRITE_DRY_RUN", "false")
    monkeypatch.setattr(atribuicoes, "buscar_os", lambda h, i: fresca)
    monkeypatch.setattr(atribuicoes, "_requisitar", lambda *a, **k: pytest.fail("não podia escrever"))
    r = ana.post(f"{P}/atribuicoes/processar", json={"ids": [aprovada], "modo": "aplicar"}).get_json()["resultado"][0]
    assert r["status"] in ("falha", "conflito") and esperado in r["mensagem"]


def test_limite_diario_e_rechecado_no_neovero_antes_de_aplicar(ana, aprovada, monkeypatch):
    monkeypatch.setattr(atribuicoes, "buscar_os", lambda h, i: _os_fresca())
    monkeypatch.setattr(atribuicoes, "_contar_os_do_dia", lambda *a: 14)    # Iranildo (eletricista) já tem 14
    r = ana.post(f"{P}/atribuicoes/processar", json={"ids": [aprovada], "modo": "simular"}).get_json()["resultado"][0]
    assert r["status"] == "falha" and "Limite diário" in r["mensagem"]


def test_neovero_indisponivel_marca_falha_sem_perder_a_proposta(ana, aprovada, monkeypatch):
    from core.neovero_client import NeoveroIndisponivelError
    def cai(h, i):
        raise NeoveroIndisponivelError("timeout")
    monkeypatch.setattr(atribuicoes, "buscar_os", cai)
    r = ana.post(f"{P}/atribuicoes/processar", json={"ids": [aprovada], "modo": "simular"}).get_json()["resultado"][0]
    assert r["status"] == "falha" and "indispon" in r["mensagem"].lower()
    with sessao() as s:
        assert s.scalars(select(AtribuicaoProposta)).one().status == "falha"
    # falha pode ser reaberta como nova proposta (idempotência por chave reaproveita o registro)
    assert _propor(ana).get_json()["resultado"][0].get("reaberta") is True


def test_rejeitada_nao_e_processada(ana, cenario):
    pid = _propor(ana).get_json()["resultado"][0]["id"]
    assert ana.post(f"{P}/atribuicoes/decisao", json={"ids": [pid], "acao": "rejeitar"}).get_json()["atualizadas"] == 1
    r = ana.post(f"{P}/atribuicoes/processar", json={"ids": [pid], "modo": "simular"}).get_json()["resultado"][0]
    assert r["status"] == "rejeitada"


def test_propostas_de_uma_unidade_nao_aparecem_nem_sao_decididas_por_outra(app, ana, cenario, criar_usuarios):
    pid = _propor(ana).get_json()["resultado"][0]["id"]
    beto = app.test_client()
    fazer_login(beto, "beto.hetrin", criar_usuarios)
    assert beto.post("/api/grandmassif/atribuicoes/decisao", json={"ids": [pid], "acao": "aprovar"}).get_json()["atualizadas"] == 0
    assert beto.post(f"{P}/atribuicoes/decisao", json={"ids": [pid], "acao": "aprovar"}).status_code == 403


def test_chave_de_idempotencia_e_estavel_e_sensivel_aos_campos():
    a = atribuicoes.chave_idempotencia("HMB", 1, "Fulano", "2026-10-13")
    assert a == atribuicoes.chave_idempotencia("HMB", 1, " fulano ", "2026-10-13")
    assert a != atribuicoes.chave_idempotencia("HETRIN", 1, "Fulano", "2026-10-13")
    assert a != atribuicoes.chave_idempotencia("HMB", 2, "Fulano", "2026-10-13")
    assert a != atribuicoes.chave_idempotencia("HMB", 1, "Fulano", "2026-10-14")


def test_regra_com_dois_responsaveis_avisa_que_o_neovero_guarda_um_so():
    oc = {"origem": "OS", "status": "Pendente", "responsavel_status": "Gestão", "os_id": 1, "os_vinculada": "1",
          "data_iso": "2026-10-14", "plano": "PM - DIÁRIA - VÁCUO", "responsavel_atual": "GESTOR",
          "recomendado": "Douglas Rodrigues", "recomendados": ["Douglas Rodrigues", "Gustavo Rafael Pereira Vargas"],
          "cargo": "Técnico", "alertas": []}
    fila = atribuicoes.montar_fila([oc], {7: "DOUGLAS RODRIGUES"})
    assert fila[0]["neovero_funcionario_id"] == 7
    assert "mais de um responsável" in fila[0]["motivo"] and "manualmente" in fila[0]["motivo"]


def test_mapa_de_ids_exige_correspondencia_unica():
    ids = {1: "MICHAEL DE CAMPOS EGUEZ", 2: "MICHAEL KELVIN DE ABREU MORAES PUPO"}
    assert atribuicoes.resolver_id_neovero("Michael de Campos Eguez", ids) == (1, None)
    assert atribuicoes.resolver_id_neovero("Fulano de Tal", ids)[0] is None
    assert atribuicoes.resolver_id_neovero("Michael", ids)[0] is None   # ambíguo -> não automatiza

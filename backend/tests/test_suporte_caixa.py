"""Caixa de mensagens interna (entrega padrão do suporte): usuários enviam, só o Dev lê e trata."""
import json

import pytest
from sqlalchemy import select

from core import suporte
from core.db import sessao
from core.models import AuditLog, SuporteSolicitacao
from tests.conftest import fazer_login

MSG = {"nome": "Ana Souza", "email": "ana@hospital.com", "tipo": "problema",
       "mensagem": "A tela de preventivas demora para carregar no período da manhã."}


@pytest.fixture()
def ana(app, criar_usuarios):
    c = app.test_client()
    fazer_login(c, "ana.hmb", criar_usuarios)
    return c


@pytest.fixture()
def dev(app, criar_usuarios):
    c = app.test_client()
    fazer_login(c, "dev", criar_usuarios)
    return c


@pytest.fixture(autouse=True)
def _sem_smtp_e_sem_envio(monkeypatch):
    """Padrão = caixa. Se algo tentar usar SMTP, o teste falha."""
    monkeypatch.delenv("SUPORTE_ENTREGA", raising=False)
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)

    def proibido(msg):
        raise AssertionError("a caixa interna não pode enviar e-mail")
    monkeypatch.setattr(suporte, "enviar_smtp", proibido)


def test_sem_nenhuma_configuracao_a_mensagem_e_registrada_na_caixa_sem_email(ana):
    st = ana.get("/api/suporte/status").get_json()
    assert st["entrega"] == "caixa" and st["configurado"] is True
    r = ana.post("/api/suporte", json=MSG)
    assert r.status_code == 201 and r.get_json()["entrega"] == "caixa" and "plataforma" in r.get_json()["mensagem"]
    with sessao() as s:
        (m,) = s.scalars(select(SuporteSolicitacao)).all()
    assert m.status == "recebida" and m.situacao == "nova" and m.unit == "HMB" and m.username == "ana.hmb"


def test_o_dev_ve_a_mensagem_com_remetente_unidade_tipo_e_texto(ana, dev):
    ana.post("/api/suporte", json=MSG)
    d = dev.get("/api/admin/suporte").get_json()
    assert d["total"] == 1 and d["nao_lidas"] == 1
    m = d["itens"][0]
    assert (m["username"], m["unit"], m["tipo"], m["nome"], m["email"]) == ("ana.hmb", "HMB", "problema", "Ana Souza", "ana@hospital.com")
    assert m["mensagem"] == MSG["mensagem"] and m["situacao"] == "nova"
    assert dev.get("/api/admin/suporte/contagem").get_json() == {"nao_lidas": 1}


@pytest.mark.parametrize("rota,metodo", [("/api/admin/suporte", "get"), ("/api/admin/suporte/contagem", "get"),
                                          ("/api/admin/suporte/1", "patch")])
def test_usuario_comum_nao_ve_nem_trata_mensagens_e_anonimo_e_barrado(app, ana, rota, metodo):
    ana.post("/api/suporte", json=MSG)
    kw = {"json": {"situacao": "lida"}} if metodo == "patch" else {}
    assert getattr(ana, metodo)(rota, **kw).status_code == 403
    assert getattr(app.test_client(), metodo)(rota, **kw).status_code == 401


def test_a_resposta_do_usuario_nao_expoe_mensagens_de_outras_pessoas(app, ana, criar_usuarios):
    ana.post("/api/suporte", json=MSG)
    beto = app.test_client()
    fazer_login(beto, "beto.hetrin", criar_usuarios)
    r = beto.post("/api/suporte", json={**MSG, "mensagem": "Mensagem do Beto para a administração."})
    assert r.status_code == 201 and "itens" not in r.get_json() and MSG["mensagem"] not in r.get_data(as_text=True)
    assert beto.get("/api/suporte/status").status_code == 200


def test_marcar_como_lida_e_resolvida_registra_quem_e_quando_e_audita(ana, dev):
    ana.post("/api/suporte", json=MSG)
    mid = dev.get("/api/admin/suporte").get_json()["itens"][0]["id"]
    r = dev.patch(f"/api/admin/suporte/{mid}", json={"situacao": "lida"})
    assert r.status_code == 200 and r.get_json()["situacao"] == "lida" and r.get_json()["tratada_por"] == "dev" and r.get_json()["tratada_em"]
    assert dev.get("/api/admin/suporte/contagem").get_json()["nao_lidas"] == 0
    assert dev.patch(f"/api/admin/suporte/{mid}", json={"situacao": "resolvida"}).get_json()["situacao"] == "resolvida"
    assert dev.patch(f"/api/admin/suporte/{mid}", json={"situacao": "nova"}).get_json()["tratada_por"] is None
    assert dev.patch(f"/api/admin/suporte/{mid}", json={"situacao": "lixo"}).status_code == 400
    assert dev.patch("/api/admin/suporte/9999", json={"situacao": "lida"}).status_code == 404
    with sessao() as s:
        ev = s.scalars(select(AuditLog).where(AuditLog.path == f"/api/admin/suporte/{mid}", AuditLog.method == "PATCH")).all()
    assert ev and ev[0].username == "dev" and json.loads(ev[0].details)["situacao"] == "lida"


def test_filtros_por_situacao_tipo_e_unidade_e_paginacao(app, ana, dev, criar_usuarios):
    beto = app.test_client()
    fazer_login(beto, "beto.hetrin", criar_usuarios)
    ana.post("/api/suporte", json=MSG)
    ana.post("/api/suporte", json={**MSG, "tipo": "melhoria", "mensagem": "Uma melhoria bem detalhada para o sistema."})
    beto.post("/api/suporte", json={**MSG, "tipo": "sugestao", "mensagem": "Uma sugestão do Beto sobre os relatórios."})
    ids = {m["tipo"]: m["id"] for m in dev.get("/api/admin/suporte").get_json()["itens"]}
    dev.patch(f"/api/admin/suporte/{ids['melhoria']}", json={"situacao": "resolvida"})
    q = lambda **k: dev.get("/api/admin/suporte", query_string=k).get_json()  # noqa: E731
    assert q()["total"] == 3 and q(unit="HETRIN")["total"] == 1 and q(tipo="melhoria")["total"] == 1
    assert q(situacao="nova")["total"] == 2 and q(situacao="resolvida")["total"] == 1
    pg = q(page_size=2)
    assert len(pg["itens"]) == 2 and pg["total"] == 3 and pg["itens"][0]["id"] > pg["itens"][1]["id"]    # mais recente primeiro
    assert len(q(page=2, page_size=2)["itens"]) == 1


def test_antiabuso_continua_valendo_na_caixa(ana, monkeypatch):
    assert ana.post("/api/suporte", json=MSG).status_code == 201
    assert ana.post("/api/suporte", json=MSG).status_code == 409                   # duplicata
    monkeypatch.setenv("SUPORTE_LIMITE_POR_HORA", "2")
    assert ana.post("/api/suporte", json={**MSG, "mensagem": "Segunda mensagem totalmente diferente da primeira."}).status_code == 201
    assert ana.post("/api/suporte", json={**MSG, "mensagem": "Terceira mensagem que deve passar do limite."}).status_code == 429
    assert ana.post("/api/suporte", json={**MSG, "email": "invalido"}).status_code == 400


def test_a_leitura_da_caixa_nao_polui_a_auditoria_mas_o_envio_sim_sem_o_texto(ana, dev):
    ana.post("/api/suporte", json=MSG)
    dev.get("/api/admin/suporte")
    dev.get("/api/admin/suporte/contagem")
    with sessao() as s:
        leituras = s.scalars(select(AuditLog).where(AuditLog.path.like("/api/admin/suporte%"), AuditLog.method == "GET")).all()
        envio = s.scalars(select(AuditLog).where(AuditLog.path == "/api/suporte")).all()
    assert leituras == []
    assert envio and json.loads(envio[-1].details)["entrega"] == "caixa" and MSG["mensagem"] not in envio[-1].details


def test_modo_email_continua_disponivel_e_exige_smtp(ana, monkeypatch):
    monkeypatch.setenv("SUPORTE_ENTREGA", "email")
    assert ana.get("/api/suporte/status").get_json() == {**ana.get("/api/suporte/status").get_json(), "entrega": "email", "configurado": False}
    assert ana.post("/api/suporte", json=MSG).status_code == 503

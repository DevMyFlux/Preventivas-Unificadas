"""Sugestões e Suporte: validação, sem simulação de envio, antiabuso, segredos fora das respostas."""
import json

import pytest
from sqlalchemy import select

from core import suporte
from core.db import sessao
from core.models import AuditLog, SuporteSolicitacao
from tests.conftest import fazer_login

VALIDO = {"nome": "Ana Souza", "email": "ana@hospital.com", "tipo": "problema",
          "mensagem": "A tela de preventivas demora para carregar no período da manhã."}
SEGREDO = "senha-de-app-super-secreta"


@pytest.fixture(autouse=True)
def _entrega_por_email(monkeypatch):
    """Estes testes cobrem o modo `email` (SMTP); a caixa interna (padrão) tem arquivo próprio."""
    monkeypatch.setenv("SUPORTE_ENTREGA", "email")


@pytest.fixture()
def ana(app, criar_usuarios):
    c = app.test_client()
    fazer_login(c, "ana.hmb", criar_usuarios)
    return c


@pytest.fixture()
def smtp(monkeypatch):
    """SMTP configurado, mas o envio é capturado (nenhuma conexão real)."""
    monkeypatch.setenv("SMTP_USER", "suporte.app@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", SEGREDO)
    enviados = []
    monkeypatch.setattr(suporte, "enviar_smtp", lambda msg: enviados.append(msg))
    return enviados


def _registros():
    with sessao() as s:
        return s.scalars(select(SuporteSolicitacao).order_by(SuporteSolicitacao.id)).all()


def test_exige_autenticacao_e_csrf(app, ana):
    assert app.test_client().post("/api/suporte", json=VALIDO).status_code == 401
    ana.environ_base["HTTP_X_CSRF_TOKEN"] = "errado"
    assert ana.post("/api/suporte", json=VALIDO).status_code == 403


def test_sem_credenciais_smtp_responde_nao_configurado_e_nao_simula_envio(ana, monkeypatch):
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    chamado = []
    monkeypatch.setattr(suporte, "enviar_smtp", lambda m: chamado.append(m))
    r = ana.post("/api/suporte", json=VALIDO)
    assert r.status_code == 503 and r.get_json()["codigo"] == "suporte_nao_configurado"
    assert "NÃO foi enviada" in r.get_json()["erro"] and chamado == []
    assert all(x.status != "enviada" for x in _registros())
    assert ana.get("/api/suporte/status").get_json()["configurado"] is False


def test_envio_valido_monta_email_para_o_suporte_com_reply_to_do_usuario(ana, smtp):
    r = ana.post("/api/suporte", json=VALIDO)
    assert r.status_code == 201 and r.get_json()["ok"] is True
    (msg,) = smtp
    assert msg["To"] == "dev.tech@myflux.ai" and msg["From"] == "suporte.app@gmail.com"
    assert msg["Reply-To"] == "ana@hospital.com" and "Problema" in msg["Subject"]
    corpo = msg.get_content()
    assert "ana.hmb" in corpo and "HMB" in corpo and VALIDO["mensagem"] in corpo
    (reg,) = _registros()
    assert reg.status == "enviada" and reg.unit == "HMB" and reg.username == "ana.hmb"
    assert ana.get("/api/suporte/status").get_json()["configurado"] is True


@pytest.mark.parametrize("campo,valor", [
    ("nome", ""), ("nome", "A"), ("nome", "x" * 121),
    ("email", ""), ("email", "sem-arroba"), ("email", "a@b"), ("email", "a@b.com\r\nBcc: x@y.com"),
    ("tipo", "outro"), ("tipo", ""),
    ("mensagem", "curta"), ("mensagem", "x" * 5001),
])
def test_validacao_rejeita_entradas_invalidas_sem_enviar(ana, smtp, campo, valor):
    r = ana.post("/api/suporte", json={**VALIDO, campo: valor})
    assert r.status_code == 400 and r.get_json()["campo"] == campo
    assert smtp == [] and _registros() == []


def test_corpo_nao_json_ou_grande_demais(ana, smtp):
    assert ana.post("/api/suporte", data="texto", content_type="text/plain").status_code == 400
    assert ana.post("/api/suporte", json={**VALIDO, "mensagem": "x" * 40000}).status_code == 413
    assert smtp == []


def test_nome_com_quebra_de_linha_nao_injeta_cabecalho(ana, smtp):
    r = ana.post("/api/suporte", json={**VALIDO, "nome": "Ana\r\nBcc: alvo@x.com"})
    assert r.status_code == 201
    (msg,) = smtp
    assert msg["Bcc"] is None and "\n" not in msg["Subject"] and "\r" not in msg["Subject"]


def test_caracteres_de_controle_sao_removidos_da_mensagem(ana, smtp):
    ana.post("/api/suporte", json={**VALIDO, "mensagem": "Texto\x00 com\x07 controles e várias palavras\nsegunda linha"})
    (reg,) = _registros()
    assert "\x00" not in reg.mensagem and "\x07" not in reg.mensagem and "segunda linha" in reg.mensagem


def test_clique_duplo_nao_gera_dois_emails(ana, smtp):
    assert ana.post("/api/suporte", json=VALIDO).status_code == 201
    r = ana.post("/api/suporte", json=VALIDO)
    assert r.status_code == 409 and r.get_json()["codigo"] == "duplicada"
    assert len(smtp) == 1 and len(_registros()) == 1


def test_limite_por_hora(ana, smtp, monkeypatch):
    monkeypatch.setenv("SUPORTE_LIMITE_POR_HORA", "2")
    for i in range(2):
        assert ana.post("/api/suporte", json={**VALIDO, "mensagem": f"Mensagem número {i} para o suporte técnico"}).status_code == 201
    r = ana.post("/api/suporte", json={**VALIDO, "mensagem": "Outra mensagem diferente para o suporte"})
    assert r.status_code == 429 and r.get_json()["codigo"] == "limite_excedido"
    assert len(smtp) == 2


def test_limite_e_por_usuario(app, criar_usuarios, smtp, monkeypatch):
    monkeypatch.setenv("SUPORTE_LIMITE_POR_HORA", "1")
    a, b = app.test_client(), app.test_client()
    fazer_login(a, "ana.hmb", criar_usuarios)
    fazer_login(b, "beto.hetrin", criar_usuarios)
    assert a.post("/api/suporte", json=VALIDO).status_code == 201
    assert b.post("/api/suporte", json=VALIDO).status_code == 201     # outro usuário, mesma mensagem: permitido


def test_falha_no_smtp_retorna_erro_generico_sem_vazar_detalhes_e_permite_nova_tentativa(ana, smtp, monkeypatch):
    def quebra(msg):
        raise RuntimeError(f"auth falhou para suporte.app@gmail.com com {SEGREDO}")
    monkeypatch.setattr(suporte, "enviar_smtp", quebra)
    r = ana.post("/api/suporte", json=VALIDO)
    assert r.status_code == 502 and r.get_json()["codigo"] == "suporte_falha_envio"
    assert SEGREDO not in r.get_data(as_text=True) and "gmail" not in r.get_data(as_text=True)
    (reg,) = _registros()
    assert reg.status == "falha" and reg.erro == "RuntimeError" and SEGREDO not in (reg.erro or "")
    monkeypatch.setattr(suporte, "enviar_smtp", lambda m: smtp.append(m))
    assert ana.post("/api/suporte", json=VALIDO).status_code == 201        # falha não bloqueia a repetição


def test_segredo_smtp_nunca_aparece_em_respostas_nem_na_auditoria(ana, smtp):
    textos = [ana.post("/api/suporte", json=VALIDO).get_data(as_text=True),
              ana.get("/api/suporte/status").get_data(as_text=True)]
    with sessao() as s:
        textos += [json.dumps([e.details, e.path, e.resource]) for e in s.scalars(select(AuditLog)).all()]
    assert not any(SEGREDO in t for t in textos)


def test_auditoria_registra_o_envio_sem_o_texto_da_mensagem(ana, smtp):
    ana.post("/api/suporte", json=VALIDO)
    with sessao() as s:
        ev = s.scalars(select(AuditLog).where(AuditLog.path == "/api/suporte")).all()
    assert ev and ev[-1].username == "ana.hmb" and ev[-1].module == "suporte"
    detalhes = json.loads(ev[-1].details)
    assert detalhes["enviado"] is True and detalhes["tipo"] == "problema"
    assert VALIDO["mensagem"] not in ev[-1].details


def test_dev_tambem_pode_enviar(app, criar_usuarios, smtp):
    d = app.test_client()
    fazer_login(d, "dev", criar_usuarios)
    assert d.post("/api/suporte", json=VALIDO).status_code == 201
    assert "todas (Dev)" in smtp[0].get_content()


def test_usa_smtp_com_starttls_e_login_no_servidor_configurado(monkeypatch):
    """O transporte real usa STARTTLS+login (sem abrir conexão: smtplib é substituído)."""
    monkeypatch.setenv("SMTP_USER", "u@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", SEGREDO)
    chamadas = []

    class Falso:
        def __init__(self, host, porta, timeout=None, context=None):
            chamadas.append(("conectar", host, porta))
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self, context=None): chamadas.append(("starttls",))
        def login(self, u, p): chamadas.append(("login", u))
        def send_message(self, m): chamadas.append(("enviar", m["To"]))

    monkeypatch.setattr(suporte.smtplib, "SMTP", Falso)
    suporte.enviar_smtp(suporte.montar_email({**VALIDO}, type("U", (), {"username": "x"})(), "HMB", suporte.agora_utc()))
    assert chamadas == [("conectar", "smtp.gmail.com", 587), ("starttls",), ("login", "u@gmail.com"), ("enviar", "dev.tech@myflux.ai")]

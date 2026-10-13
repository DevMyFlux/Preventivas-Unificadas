"""Autenticação: login válido/inválido, bloqueio, sessão, CSRF, cookie, política de senha, bootstrap do Dev."""
import re
from datetime import timedelta

import pytest
from sqlalchemy import select

from core import audit
from core.auth import servico
from core.db import agora_utc, sessao
from core.models import AuditLog, AuthSession, User
from tests.conftest import fazer_login


def _eventos(*nomes):
    with sessao() as s:
        return s.scalars(select(AuditLog).where(AuditLog.event.in_(nomes)).order_by(AuditLog.id)).all()


def test_login_valido_cria_sessao_com_cookie_httponly_e_samesite(client, criar_usuarios):
    r = client.post("/api/auth/login", json={"username": "ana.hmb", "password": criar_usuarios})
    assert r.status_code == 200
    corpo = r.get_json()
    assert corpo["user"]["username"] == "ana.hmb" and corpo["user"]["unit"] == "HMB"
    assert corpo["user"]["is_dev"] is False
    chaves = set(corpo["user"]) | set(corpo)
    assert not {"password", "password_hash", "hash", "token"} & chaves
    cookie = r.headers["Set-Cookie"]
    assert "myflux_session=" in cookie and "HttpOnly" in cookie and "SameSite=Lax" in cookie
    assert "csrf_token" in corpo


def test_login_com_senha_errada_ou_usuario_inexistente_tem_resposta_identica(client, criar_usuarios):
    a = client.post("/api/auth/login", json={"username": "ana.hmb", "password": "errada-errada1"})
    b = client.post("/api/auth/login", json={"username": "ninguem", "password": "errada-errada1"})
    assert a.status_code == b.status_code == 401
    assert a.get_json() == b.get_json()          # não revela se o usuário existe
    assert "Set-Cookie" not in a.headers


def test_login_vazio_ou_malformado_e_rejeitado(client, criar_usuarios):
    for corpo in ({}, {"username": "", "password": ""}, {"username": "ana.hmb"}, {"password": "x"}):
        assert client.post("/api/auth/login", json=corpo).status_code == 401
    assert client.post("/api/auth/login", data="nao-e-json", content_type="text/plain").status_code == 401


def test_usuario_desativado_nao_entra_e_resposta_e_generica(client, criar_usuarios):
    from core.auth.servico import obter_usuario_por_username
    uid = obter_usuario_por_username("ana.hmb").id
    with sessao() as s:
        s.get(User, uid).is_active = False
    r = client.post("/api/auth/login", json={"username": "ana.hmb", "password": criar_usuarios})
    assert r.status_code == 401
    assert r.get_json()["codigo"] == "credenciais_invalidas"
    falhas = _eventos("login_failed")
    assert falhas and falhas[-1].details and "usuario_desativado" in falhas[-1].details


def test_bloqueio_temporario_apos_falhas_repetidas_mesmo_com_senha_certa(client, criar_usuarios, monkeypatch):
    monkeypatch.setenv("LOGIN_MAX_FAILURES", "3")
    for _ in range(3):
        assert client.post("/api/auth/login", json={"username": "ana.hmb", "password": "errada-errada1"}).status_code == 401
    r = client.post("/api/auth/login", json={"username": "ana.hmb", "password": criar_usuarios})
    assert r.status_code == 423 and r.get_json()["codigo"] == "conta_bloqueada"
    # depois do prazo, volta a funcionar
    with sessao() as s:
        s.get(User, servico.obter_usuario_por_username("ana.hmb").id).locked_until = agora_utc() - timedelta(seconds=1)
    assert client.post("/api/auth/login", json={"username": "ana.hmb", "password": criar_usuarios}).status_code == 200


def test_limite_de_tentativas_por_ip(client, criar_usuarios, monkeypatch):
    monkeypatch.setattr(servico, "_LIMITE_FALHAS_POR_IP", 5)
    for i in range(5):
        client.post("/api/auth/login", json={"username": f"x{i}abc", "password": "zzzzzzzz1"})
    r = client.post("/api/auth/login", json={"username": "ana.hmb", "password": criar_usuarios})
    assert r.status_code == 429


def test_rotas_exigem_login_e_me_devolve_o_usuario(client, criar_usuarios):
    assert client.get("/api/auth/me").status_code == 401
    fazer_login(client, "ana.hmb", criar_usuarios)
    me = client.get("/api/auth/me").get_json()
    assert me["user"]["username"] == "ana.hmb" and me["csrf_token"]


def test_logout_encerra_a_sessao_e_o_cookie_para_de_valer(client, criar_usuarios):
    fazer_login(client, "ana.hmb", criar_usuarios)
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    with sessao() as s:
        sess = s.scalars(select(AuthSession)).all()[-1]
        assert sess.end_reason == "logout" and sess.ended_at is not None


def test_csrf_obrigatorio_em_requisicoes_que_alteram_estado(client, criar_usuarios):
    fazer_login(client, "ana.hmb", criar_usuarios)
    client.environ_base.pop("HTTP_X_CSRF_TOKEN")
    r = client.post("/api/auth/ping")
    assert r.status_code == 403 and r.get_json()["codigo"] == "csrf_invalido"
    client.environ_base["HTTP_X_CSRF_TOKEN"] = "token-errado"
    assert client.post("/api/auth/ping").status_code == 403


def test_sessao_expira_por_inatividade_e_registra_fim_na_ultima_atividade(client, criar_usuarios, monkeypatch):
    monkeypatch.setenv("SESSION_IDLE_MINUTES", "30")
    fazer_login(client, "ana.hmb", criar_usuarios)
    ultima = agora_utc() - timedelta(minutes=45)
    with sessao() as s:
        sess = s.scalars(select(AuthSession)).all()[-1]
        sess.last_activity_at = ultima
    assert client.get("/api/auth/me").status_code == 401
    with sessao() as s:
        sess = s.scalars(select(AuthSession)).all()[-1]
        assert sess.end_reason == "idle_timeout" and sess.ended_at == ultima


def test_sessao_expira_pelo_tempo_maximo_absoluto(client, criar_usuarios):
    fazer_login(client, "ana.hmb", criar_usuarios)
    with sessao() as s:
        sess = s.scalars(select(AuthSession)).all()[-1]
        sess.expires_at = agora_utc() - timedelta(minutes=1)
        sess.last_activity_at = agora_utc()
    assert client.get("/api/auth/me").status_code == 401
    with sessao() as s:
        assert s.scalars(select(AuthSession)).all()[-1].end_reason == "max_lifetime"


def test_atividade_renova_last_activity_e_estende_a_ociosidade(client, criar_usuarios, monkeypatch):
    fazer_login(client, "ana.hmb", criar_usuarios)
    with sessao() as s:
        s.scalars(select(AuthSession)).all()[-1].last_activity_at = agora_utc() - timedelta(minutes=20)
    assert client.get("/api/auth/me").status_code == 200   # ainda dentro dos 30 min -> renova
    with sessao() as s:
        sess = s.scalars(select(AuthSession)).all()[-1]
        assert agora_utc() - sess.last_activity_at < timedelta(seconds=30)


def test_sessoes_vencidas_sem_logout_sao_finalizadas_pelo_varredor(client, criar_usuarios):
    """Desconexão inesperada (aba fechada, rede caiu): ninguém chama logout."""
    fazer_login(client, "ana.hmb", criar_usuarios)
    with sessao() as s:
        s.scalars(select(AuthSession)).all()[-1].last_activity_at = agora_utc() - timedelta(hours=3)
    assert servico.finalizar_sessoes_vencidas() == 1
    with sessao() as s:
        sess = s.scalars(select(AuthSession)).all()[-1]
        assert sess.end_reason == "idle_timeout"
    assert servico.finalizar_sessoes_vencidas() == 0   # idempotente


def test_trocar_senha_exige_a_atual_valida_a_politica_e_derruba_as_sessoes(client, criar_usuarios):
    fazer_login(client, "ana.hmb", criar_usuarios)
    assert client.post("/api/auth/password", json={"current_password": "errada", "new_password": "NovaSenha123"}).status_code == 400
    assert client.post("/api/auth/password", json={"current_password": criar_usuarios, "new_password": "curta1"}).status_code == 400
    r = client.post("/api/auth/password", json={"current_password": criar_usuarios, "new_password": "NovaSenha123"})
    assert r.status_code == 200 and r.get_json()["relogin"] is True
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"username": "ana.hmb", "password": criar_usuarios}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "ana.hmb", "password": "NovaSenha123"}).status_code == 200


@pytest.mark.parametrize("senha", ["curta1", "somenteletrasaqui", "1234567890123", ""])
def test_politica_de_senha(app, senha):
    with pytest.raises(servico.ValidacaoError):
        servico.validar_senha(senha, "fulano")


def test_senha_nao_pode_ser_igual_ao_usuario():
    with pytest.raises(servico.ValidacaoError):
        servico.validar_senha("fulano12345", "fulano12345")


def test_senha_armazenada_com_hash_scrypt_e_token_so_como_sha256(client, criar_usuarios):
    fazer_login(client, "ana.hmb", criar_usuarios)
    with sessao() as s:
        user = s.scalar(select(User).where(User.username == "ana.hmb"))
        assert user.password_hash.startswith("scrypt:") and criar_usuarios not in user.password_hash
        sess = s.scalars(select(AuthSession)).all()[-1]
        assert re.fullmatch(r"[0-9a-f]{64}", sess.token_hash)
        cookie = client.get_cookie("myflux_session").value
        assert cookie != sess.token_hash and servico.hash_token(cookie) == sess.token_hash


def test_nenhuma_senha_ou_token_aparece_nos_logs_de_auditoria(client, criar_usuarios):
    client.post("/api/auth/login", json={"username": "ana.hmb", "password": "errada-errada1"})
    fazer_login(client, "ana.hmb", criar_usuarios)
    token = client.get_cookie("myflux_session").value
    csrf = client.environ_base["HTTP_X_CSRF_TOKEN"]
    with sessao() as s:
        tudo = " ".join(str(c) for linha in s.scalars(select(AuditLog)).all() for c in
                        (linha.details, linha.path, linha.resource, linha.user_agent))
    for segredo in (criar_usuarios, "errada-errada1", token, csrf):
        assert segredo not in tudo


def test_login_gera_eventos_de_auditoria_de_sucesso_e_falha(client, criar_usuarios):
    client.post("/api/auth/login", json={"username": "ana.hmb", "password": "errada-errada1"})
    fazer_login(client, "ana.hmb", criar_usuarios)
    client.post("/api/auth/logout")
    ev = _eventos("login_failed", "login_success", "logout")
    assert [e.event for e in ev] == ["login_failed", "login_success", "logout"]
    assert ev[0].result == "failure" and ev[1].result == "success"
    assert ev[1].username == "ana.hmb" and ev[1].unit == "HMB" and ev[1].ip


def test_sanitizar_remove_chaves_sensiveis_em_qualquer_nivel():
    d = audit.sanitizar({"senha": "x", "ok": 1, "a": {"Authorization": "Bearer y", "n": [{"token": "t", "v": 2}]}})
    assert d["senha"] == "[REDACTED]" and d["ok"] == 1
    assert d["a"]["Authorization"] == "[REDACTED]" and d["a"]["n"][0] == {"token": "[REDACTED]", "v": 2}


def test_bootstrap_cria_o_dev_a_partir_do_ambiente_sem_credencial_no_codigo(app, monkeypatch):
    assert servico.existe_dev() is False
    monkeypatch.setenv("DEV_ADMIN_USERNAME", "Felipe")
    monkeypatch.setenv("DEV_ADMIN_PASSWORD", "SenhaDoDev123")
    assert "Dev criado" in servico.bootstrap_admin()
    u = servico.obter_usuario_por_username("felipe")
    assert u.is_dev and u.unit is None and u.password_hash != "SenhaDoDev123"
    # segunda execução não duplica nem altera
    assert servico.bootstrap_admin() == "existente"


def test_bootstrap_sem_variaveis_avisa_e_nao_cria_ninguem(app, monkeypatch):
    monkeypatch.delenv("DEV_ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("DEV_ADMIN_PASSWORD", raising=False)
    assert "AVISO" in servico.bootstrap_admin() and servico.existe_dev() is False


def test_bootstrap_nao_sobrescreve_senha_do_dev_sem_o_reset_explicito(app, monkeypatch):
    monkeypatch.setenv("DEV_ADMIN_USERNAME", "felipe")
    monkeypatch.setenv("DEV_ADMIN_PASSWORD", "SenhaDoDev123")
    servico.bootstrap_admin()
    monkeypatch.setenv("DEV_ADMIN_PASSWORD", "OutraSenha456")
    servico.bootstrap_admin()
    from werkzeug.security import check_password_hash
    assert check_password_hash(servico.obter_usuario_por_username("felipe").password_hash, "SenhaDoDev123")
    monkeypatch.setenv("DEV_ADMIN_RESET_PASSWORD", "true")
    assert "redefinida" in servico.bootstrap_admin()
    assert check_password_hash(servico.obter_usuario_por_username("felipe").password_hash, "OutraSenha456")


def test_codigo_fonte_nao_contem_credenciais_do_neovero():
    import pathlib
    raiz = pathlib.Path(__file__).resolve().parent.parent
    proibidos = ("admin@myflux.ai", "admin@2026")
    for arq in list(raiz.rglob("*.py")) + list(raiz.rglob("*.json")):
        if "tests" in arq.parts or ".venv" in arq.parts:
            continue
        texto = arq.read_text(encoding="utf-8", errors="ignore")
        for p in proibidos:
            assert p not in texto, f"credencial hardcoded em {arq}"


# ── proxy / IP do cliente / cabeçalhos de segurança ───────────────────────────

def test_ip_do_cliente_so_confia_em_x_forwarded_for_com_proxy_configurado(monkeypatch):
    from app_factory import create_app
    cabecalho = {"X-Forwarded-For": "6.6.6.6, 203.0.113.9"}   # o 1º item é forjado pelo cliente; o último, o proxy anexou

    monkeypatch.setenv("TRUST_PROXY_HOPS", "0")
    sem_proxy = create_app("sqlite:///:memory:", bootstrap=False)
    servico.criar_usuario("fulano.teste", "Senha12345", unit="HMB")
    sem_proxy.test_client().post("/api/auth/login", json={"username": "fulano.teste", "password": "x"}, headers=cabecalho)
    with sessao() as s:
        assert s.scalars(select(AuditLog).where(AuditLog.event == "login_failed")).all()[-1].ip == "127.0.0.1"

    monkeypatch.setenv("TRUST_PROXY_HOPS", "1")
    com_proxy = create_app("sqlite:///:memory:", bootstrap=False)
    servico.criar_usuario("fulano.teste", "Senha12345", unit="HMB")
    com_proxy.test_client().post("/api/auth/login", json={"username": "fulano.teste", "password": "x"}, headers=cabecalho)
    with sessao() as s:
        assert s.scalars(select(AuditLog).where(AuditLog.event == "login_failed")).all()[-1].ip == "203.0.113.9"


def test_cabecalhos_de_seguranca_em_todas_as_respostas_e_hsts_em_producao(client, monkeypatch):
    r = client.get("/api/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff" and r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Cache-Control"] == "no-store" and "Strict-Transport-Security" not in r.headers
    monkeypatch.setenv("APP_ENV", "production")
    assert "max-age=" in client.get("/api/health").headers["Strict-Transport-Security"]


def test_cors_nao_e_aberto_para_qualquer_origem(client, monkeypatch):
    r = client.get("/api/health", headers={"Origin": "https://site-malicioso.example"})
    assert "Access-Control-Allow-Origin" not in r.headers
    monkeypatch.setenv("CORS_ORIGINS", "https://app.exemplo.com")
    ok = client.get("/api/health", headers={"Origin": "https://app.exemplo.com"})
    assert ok.headers["Access-Control-Allow-Origin"] == "https://app.exemplo.com"
    assert ok.headers["Access-Control-Allow-Credentials"] == "true"
    assert "Access-Control-Allow-Origin" not in client.get("/api/health", headers={"Origin": "https://outro.example"}).headers


def test_resposta_de_erro_interno_nao_vaza_detalhes(app):
    @app.route("/api/_teste_erro")
    def _erro():
        raise RuntimeError("segredo-interno-xyz")
    app.config["TESTING"] = False
    app.config["PROPAGATE_EXCEPTIONS"] = False
    c = app.test_client()
    # precisa estar autenticado para chegar na rota
    servico.criar_usuario("erro.user", "Senha12345", unit="HMB")
    fazer_login(c, "erro.user", "Senha12345")
    r = c.get("/api/_teste_erro")
    assert r.status_code == 500 and "segredo-interno-xyz" not in r.get_data(as_text=True)


def test_login_aceita_email_como_usuario(app, monkeypatch):
    monkeypatch.setenv("DEV_ADMIN_USERNAME", "Dev@Exemplo.com")
    monkeypatch.setenv("DEV_ADMIN_PASSWORD", "SenhaDoDev123")
    assert "Dev criado" in servico.bootstrap_admin()
    c = app.test_client()
    r = c.post("/api/auth/login", json={"username": "dev@exemplo.com", "password": "SenhaDoDev123"})
    assert r.status_code == 200 and r.get_json()["user"]["is_dev"] is True
    for invalido in ("a b@x.com", "x@@", "<script>"):
        with pytest.raises(servico.ValidacaoError):
            servico.validar_username(invalido + "zz")

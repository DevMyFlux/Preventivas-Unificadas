"""
Logout automático após 25 minutos de inatividade — decidido e imposto no BACKEND.

Cobre: limite de 25 min, definição de atividade (o que conta e o que não conta), invalidação
efetiva, impossibilidade de reaproveitar sessão encerrada (inclusive reabrindo a página),
múltiplas abas, tempo ativo estimado e registro de auditoria específico.
"""
import json
from datetime import timedelta

import pytest
from sqlalchemy import select

from core.auth import servico
from core.db import agora_utc, sessao
from core.models import AuditLog, AuthSession
from core.settings import settings
from tests.conftest import fazer_login


def _sessao_atual() -> AuthSession:
    with sessao() as s:
        return s.scalars(select(AuthSession).order_by(AuthSession.id)).all()[-1]


def _inativo_ha(minutos: float, **extra) -> None:
    """Recua a última atividade da sessão mais recente (simula `minutos` de inatividade)."""
    with sessao() as s:
        sess = s.scalars(select(AuthSession).order_by(AuthSession.id)).all()[-1]
        sess.last_activity_at = agora_utc() - timedelta(minutes=minutos)
        for k, v in extra.items():
            setattr(sess, k, v)


def _eventos(*nomes):
    with sessao() as s:
        return s.scalars(select(AuditLog).where(AuditLog.event.in_(nomes)).order_by(AuditLog.id)).all()


@pytest.fixture()
def ana(app, criar_usuarios):
    c = app.test_client()
    fazer_login(c, "ana.hmb", criar_usuarios)
    return c


# ── o limite é 25 minutos ─────────────────────────────────────────────────────

def test_limite_padrao_de_inatividade_e_25_minutos():
    assert settings.sessao_ociosa_minutos == 25


def test_sessao_continua_valida_aos_24_minutos_de_inatividade(ana):
    _inativo_ha(24)
    assert ana.get("/api/auth/me").status_code == 200


def test_sessao_cai_aos_26_minutos_de_inatividade_com_motivo_e_mensagem(ana):
    _inativo_ha(26)
    r = ana.get("/api/auth/me")
    assert r.status_code == 401
    corpo = r.get_json()
    assert corpo["motivo"] == "inatividade" and corpo["codigo"] == "nao_autenticado"
    assert "desconectado por inatividade" in corpo["erro"]


def test_o_limite_e_contado_desde_a_ultima_atividade_valida_nao_desde_o_login(ana):
    with sessao() as s:   # login há 2 horas, mas atividade há 10 minutos: continua logado
        sess = s.scalars(select(AuthSession)).all()[-1]
        sess.created_at = agora_utc() - timedelta(hours=2)
        sess.last_activity_at = agora_utc() - timedelta(minutes=10)
    assert ana.get("/api/auth/me").status_code == 200


def test_limite_configuravel_por_ambiente_mas_o_padrao_do_produto_e_25(ana, monkeypatch):
    monkeypatch.setenv("SESSION_IDLE_MINUTES", "10")
    _inativo_ha(11)
    assert ana.get("/api/auth/me").status_code == 401


# ── o que conta (e o que não conta) como atividade ────────────────────────────

def test_requisicao_do_usuario_atualiza_a_ultima_atividade(ana):
    _inativo_ha(20)
    assert ana.get("/api/brasilandia/habilidades").status_code == 200
    assert agora_utc() - _sessao_atual().last_activity_at < timedelta(seconds=30)


def test_consulta_periodica_de_sessao_NAO_conta_como_atividade(ana):
    """O polling do frontend (para exibir o aviso de expiração) nunca mantém a sessão viva."""
    _inativo_ha(20)
    antes = _sessao_atual().last_activity_at
    for _ in range(5):
        r = ana.get("/api/auth/session")
        assert r.status_code == 200
    assert _sessao_atual().last_activity_at == antes
    # e o tempo restante diminui conforme o tempo passa (≈ 5 min restantes)
    assert 280 <= r.get_json()["expira_em_s"] <= 305


def test_ping_sem_interacao_NAO_renova_mas_com_interacao_renova(ana):
    _inativo_ha(20)
    antes = _sessao_atual().last_activity_at
    assert ana.post("/api/auth/ping", json={"interagiu": False}).status_code == 200
    assert ana.post("/api/auth/ping", json={}).status_code == 200
    assert _sessao_atual().last_activity_at == antes
    assert ana.post("/api/auth/ping", json={"interagiu": True}).status_code == 200
    assert _sessao_atual().last_activity_at > antes
    assert ana.get("/api/auth/session").get_json()["expira_em_s"] > 24 * 60


def test_so_chamadas_automaticas_deixam_a_sessao_expirar(ana):
    """Simula uma aba esquecida aberta: só polling + pings sem interação. Passados 25 min, cai."""
    _inativo_ha(20)
    ana.get("/api/auth/session")
    ana.post("/api/auth/ping", json={"interagiu": False})
    _inativo_ha(26)
    assert ana.get("/api/auth/session").status_code == 401


def test_navegacao_entre_modulos_conta_como_atividade(ana):
    _inativo_ha(20)
    assert ana.post("/api/auth/activity", json={"module": "planos", "unit": "HMB"}).status_code == 200
    assert agora_utc() - _sessao_atual().last_activity_at < timedelta(seconds=30)


# ── tempo ativo estimado ──────────────────────────────────────────────────────

def test_tempo_ativo_soma_os_intervalos_limitados_pela_janela_de_atividade(ana):
    base = agora_utc()
    _inativo_ha(0, active_seconds=0, activity_count=0)
    with sessao() as s:     # atividade há 2 min → conta 2 min
        s.scalars(select(AuthSession)).all()[-1].last_activity_at = base - timedelta(minutes=2)
    ana.get("/api/brasilandia/habilidades")
    sess = _sessao_atual()
    assert 115 <= sess.active_seconds <= 125 and sess.activity_count == 1
    with sessao() as s:     # atividade há 20 min → conta no máx. a janela (5 min); o resto é ocioso
        s.scalars(select(AuthSession)).all()[-1].last_activity_at = agora_utc() - timedelta(minutes=20)
    ana.get("/api/brasilandia/habilidades")
    sess = _sessao_atual()
    assert 115 + 295 <= sess.active_seconds <= 125 + 305 and sess.activity_count == 2


def test_requisicoes_em_rajada_nao_geram_uma_gravacao_por_chamada(ana):
    antes = _sessao_atual().activity_count
    for _ in range(15):
        ana.get("/api/brasilandia/habilidades")
    assert _sessao_atual().activity_count - antes <= 1     # throttle de 30 s


# ── invalidação efetiva no backend ────────────────────────────────────────────

def test_apos_expirar_nenhuma_rota_protegida_funciona_mais(app, ana):
    _inativo_ha(26)
    ana.get("/api/auth/me")   # primeira detecção encerra a sessão
    for rota in ("/api/auth/me", "/api/brasilandia/colaboradores", "/api/brasilandia/preventivas?data_ini=2026-10-14&data_fim=2026-10-14",
                 "/api/auth/session"):
        r = ana.get(rota)
        assert r.status_code == 401, rota
        assert r.get_json()["motivo"] == "inatividade"
    assert ana.post("/api/auth/ping", json={"interagiu": True}).status_code == 401
    assert ana.post("/api/auth/activity", json={"module": "planos"}).status_code == 401


def test_recarregar_a_pagina_nao_recupera_a_sessao_encerrada(ana):
    """Reabrir/atualizar a página reenvia o MESMO cookie: continua inválido, mesmo que a última
    atividade fosse 'consertada' depois (o encerramento é definitivo e fica gravado)."""
    _inativo_ha(30)
    assert ana.get("/api/auth/me").status_code == 401
    with sessao() as s:                    # tentativa de "ressuscitar" mexendo no relógio da sessão
        sess = s.scalars(select(AuthSession)).all()[-1]
        sess.last_activity_at = agora_utc()
    assert ana.get("/api/auth/me").status_code == 401
    r = ana.get("/api/auth/me")
    assert r.get_json()["motivo"] == "inatividade"      # a tela de login sabe explicar o motivo
    assert _sessao_atual().end_reason == "idle_timeout" and _sessao_atual().ended_at is not None


def test_nova_autenticacao_cria_outra_sessao_independente(app, ana, criar_usuarios):
    _inativo_ha(30)
    assert ana.get("/api/auth/me").status_code == 401
    fazer_login(ana, "ana.hmb", criar_usuarios)
    assert ana.get("/api/auth/me").status_code == 200
    with sessao() as s:
        assert len(s.scalars(select(AuthSession)).all()) == 2


def test_operacao_de_escrita_apos_expirar_e_recusada_e_nada_e_gravado(app, ana, monkeypatch):
    from core import colaboradores_overlay as ov
    from units.brasilandia import config as cfg
    antes = ov.carregar(cfg.OVERLAY)
    _inativo_ha(26)
    r = ana.patch("/api/brasilandia/colaborador/Fulano/bloqueio", json={"bloqueado": True, "aviso": "x"})
    assert r.status_code == 401 and r.get_json()["mutacao"] is True      # o cliente sabe que NÃO foi salvo
    assert ov.carregar(cfg.OVERLAY) == antes


def test_batimento_e_navegacao_automaticos_nao_sao_operacoes_perdidas(ana):
    _inativo_ha(26)
    r = ana.post("/api/auth/ping", json={"interagiu": True})
    assert r.status_code == 401 and r.get_json()["mutacao"] is False and r.get_json()["motivo"] == "inatividade"
    assert ana.post("/api/auth/activity", json={"module": "planos"}).get_json()["mutacao"] is False


# ── múltiplas abas ────────────────────────────────────────────────────────────

def test_duas_abas_compartilham_a_sessao_atividade_numa_mantem_a_outra_viva(app, ana):
    aba_b = app.test_client()
    aba_b.set_cookie(settings.cookie_name, ana.get_cookie(settings.cookie_name).value)
    aba_b.environ_base["HTTP_X_CSRF_TOKEN"] = ana.environ_base["HTTP_X_CSRF_TOKEN"]
    _inativo_ha(24)
    assert aba_b.get("/api/brasilandia/habilidades").status_code == 200      # uso na aba B renova
    assert ana.get("/api/auth/session").get_json()["expira_em_s"] > 24 * 60   # aba A enxerga a renovação


def test_expiracao_aparece_nas_duas_abas_ao_mesmo_tempo(app, ana):
    aba_b = app.test_client()
    aba_b.set_cookie(settings.cookie_name, ana.get_cookie(settings.cookie_name).value)
    _inativo_ha(27)
    assert ana.get("/api/auth/session").status_code == 401
    r = aba_b.get("/api/auth/session")
    assert r.status_code == 401 and r.get_json()["motivo"] == "inatividade"


def test_encerramento_por_logout_em_uma_aba_vale_para_a_outra(app, ana):
    aba_b = app.test_client()
    aba_b.set_cookie(settings.cookie_name, ana.get_cookie(settings.cookie_name).value)
    assert ana.post("/api/auth/logout").status_code == 200
    r = aba_b.get("/api/auth/me")
    assert r.status_code == 401 and r.get_json()["motivo"] == "logout"


# ── auditoria do encerramento ─────────────────────────────────────────────────

def test_encerramento_por_inatividade_gera_registro_especifico_com_usuario_unidade_e_horario(ana):
    ultima = agora_utc() - timedelta(minutes=40)
    with sessao() as s:
        s.scalars(select(AuthSession)).all()[-1].last_activity_at = ultima
    ana.get("/api/auth/me")
    ev = _eventos("session_idle_timeout")
    assert len(ev) == 1
    e = ev[0]
    assert e.username == "ana.hmb" and e.unit == "HMB" and e.session_id == _sessao_atual().id
    assert e.ts == ultima                                    # o horário é o da ÚLTIMA ATIVIDADE (início da ociosidade)
    d = json.loads(e.details)
    assert d["motivo"] == "idle_timeout" and d["duracao_s"] >= 0 and "ativo_s" in d


def test_o_registro_de_encerramento_nao_duplica_em_requisicoes_repetidas(ana):
    _inativo_ha(30)
    for _ in range(6):
        ana.get("/api/auth/me")
        ana.get("/api/brasilandia/habilidades")
    assert len(_eventos("session_idle_timeout")) == 1


def test_varredura_fecha_sessoes_esquecidas_e_registra_cada_uma_uma_vez(app, criar_usuarios):
    for _ in range(3):
        fazer_login(app.test_client(), "ana.hmb", criar_usuarios)
    with sessao() as s:
        for sess in s.scalars(select(AuthSession)).all():
            sess.last_activity_at = agora_utc() - timedelta(minutes=50)
    assert servico.finalizar_sessoes_vencidas() == 3
    assert servico.finalizar_sessoes_vencidas() == 0
    assert len(_eventos("session_idle_timeout")) == 3


def test_expiracao_pelo_limite_absoluto_tem_evento_proprio(ana):
    with sessao() as s:
        sess = s.scalars(select(AuthSession)).all()[-1]
        sess.expires_at = agora_utc() - timedelta(minutes=1)
        sess.last_activity_at = agora_utc()
    assert ana.get("/api/auth/me").get_json()["motivo"] == "tempo_maximo"
    assert len(_eventos("session_max_lifetime")) == 1


def test_desativar_usuario_registra_encerramento_das_sessoes_abertas(app, ana, criar_usuarios):
    dev = app.test_client()
    fazer_login(dev, "dev", criar_usuarios)
    uid = servico.obter_usuario_por_username("ana.hmb").id
    dev.post(f"/api/admin/users/{uid}/active", json={"active": False})
    ev = _eventos("session_revoked")
    assert len(ev) == 1 and ev[0].username == "ana.hmb"
    assert json.loads(ev[0].details)["motivo"] == "user_deactivated"
    r = ana.get("/api/auth/me")
    assert r.status_code == 401 and r.get_json()["motivo"] == "conta_desativada"


def test_login_ainda_funciona_apos_uma_sessao_expirar_e_historico_e_preservado(app, ana, criar_usuarios):
    _inativo_ha(30)
    ana.get("/api/auth/me")
    nova = app.test_client()
    fazer_login(nova, "ana.hmb", criar_usuarios)
    with sessao() as s:
        sessoes = s.scalars(select(AuthSession).order_by(AuthSession.id)).all()
    assert [x.end_reason for x in sessoes] == ["idle_timeout", None]
    assert len(_eventos("login_success")) == 2 and len(_eventos("session_idle_timeout")) == 1

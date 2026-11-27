"""Criação de ADMINISTRADOR (perfil dev): só administrador cria administrador; proteções das contas administrativas."""
import pytest
from sqlalchemy import select

from core.auth import servico
from core.db import sessao
from core.models import AuditLog
from tests.conftest import fazer_login

NOVO = {"username": "novo.admin", "password": "SenhaForte123", "display_name": "Novo Admin", "role": "dev"}


@pytest.fixture()
def dev(app, criar_usuarios):
    c = app.test_client()
    fazer_login(c, "dev", criar_usuarios)
    return c


def test_administrador_cria_administrador_sem_unidade_com_acesso_a_tudo(app, dev):
    r = dev.post("/api/admin/users", json={**NOVO, "unit": "HMB"})           # unidade é ignorada: administrador acessa todas
    assert r.status_code == 201
    u = r.get_json()
    assert u["is_dev"] is True and u["role"] == "dev" and u["unit"] is None and u["created_by"] == "dev"
    novo = app.test_client()
    fazer_login(novo, "novo.admin", "SenhaForte123")
    assert novo.get("/api/admin/users").status_code == 200                   # área administrativa
    assert novo.get("/api/brasilandia/colaboradores").status_code == 200     # as duas unidades
    assert novo.get("/api/grandmassif/regras").status_code == 200            # Regras/Atribuição liberadas
    assert {x["codigo"] for x in novo.get("/api/auth/me").get_json()["user"]["units"]} == {"HMB", "HETRIN"}


def test_o_novo_administrador_tambem_pode_criar_administradores_e_usuarios(app, dev):
    dev.post("/api/admin/users", json=NOVO)
    novo = app.test_client()
    fazer_login(novo, "novo.admin", "SenhaForte123")
    assert novo.post("/api/admin/users", json={**NOVO, "username": "terceiro.admin"}).status_code == 201
    assert novo.post("/api/admin/users", json={"username": "comum.hmb", "password": "SenhaForte123", "unit": "HMB"}).status_code == 201


@pytest.mark.parametrize("login,unidade", [("ana.hmb", "HMB"), ("beto.hetrin", "HETRIN")])
def test_usuario_comum_nao_cria_administrador_nem_ninguem(app, criar_usuarios, login, unidade):
    c = app.test_client()
    fazer_login(c, login, criar_usuarios)
    assert c.post("/api/admin/users", json=NOVO).status_code == 403
    assert c.post("/api/admin/users", json={"username": "x.comum", "password": "SenhaForte123", "unit": unidade}).status_code == 403
    assert servico.obter_usuario_por_username("novo.admin") is None
    assert servico.obter_usuario_por_username("x.comum") is None
    assert app.test_client().post("/api/admin/users", json=NOVO).status_code == 401      # anônimo


def test_comum_nao_se_promove_nem_e_promovido_por_patch(app, dev, criar_usuarios):
    ana = app.test_client()
    fazer_login(ana, "ana.hmb", criar_usuarios)
    uid = servico.obter_usuario_por_username("ana.hmb").id
    assert ana.patch(f"/api/admin/users/{uid}", json={"role": "dev"}).status_code == 403
    assert dev.patch(f"/api/admin/users/{uid}", json={"role": "dev"}).status_code == 400        # perfil só se define na criação
    assert servico.obter_usuario_por_username("ana.hmb").role == "user"


def test_criacao_de_administrador_e_auditada_e_a_senha_nao_aparece(dev):
    dev.post("/api/admin/users", json=NOVO)
    with sessao() as s:
        ev = s.scalars(select(AuditLog).where(AuditLog.path == "/api/admin/users", AuditLog.method == "POST")).all()
    assert ev and ev[-1].username == "dev" and '"perfil": "dev"' in ev[-1].details and "SenhaForte123" not in ev[-1].details


def test_validacoes_continuam_valendo_para_administrador(dev):
    assert dev.post("/api/admin/users", json={**NOVO, "password": "curta"}).status_code == 400
    assert dev.post("/api/admin/users", json={**NOVO, "username": "dev"}).get_json()["campo"] == "username"      # login duplicado
    assert dev.post("/api/admin/users", json={**NOVO, "role": "root"}).get_json()["codigo"] == "perfil_invalido"


def test_administrador_desativa_outro_administrador_mas_nunca_a_si_mesmo(app, dev):
    dev.post("/api/admin/users", json=NOVO)
    outro = servico.obter_usuario_por_username("novo.admin").id
    eu = servico.obter_usuario_por_username("dev").id
    assert dev.post(f"/api/admin/users/{eu}/active", json={"active": False}).get_json()["codigo"] == "admin_proprio"
    r = dev.post(f"/api/admin/users/{outro}/active", json={"active": False})
    assert r.status_code == 200 and r.get_json()["is_active"] is False
    novo = app.test_client()
    assert novo.post("/api/auth/login", json={"username": "novo.admin", "password": "SenhaForte123"}).status_code == 401
    assert servico.obter_usuario(outro) is not None                                # histórico preservado
    assert dev.post(f"/api/admin/users/{outro}/active", json={"active": True}).status_code == 200


def test_senha_de_outro_administrador_nao_e_redefinida_por_aqui(dev):
    dev.post("/api/admin/users", json=NOVO)
    outro = servico.obter_usuario_por_username("novo.admin").id
    assert dev.post(f"/api/admin/users/{outro}/password", json={"password": "OutraSenha12345"}).status_code == 403
    eu = servico.obter_usuario_por_username("dev").id
    assert dev.post(f"/api/admin/users/{eu}/password", json={"password": "OutraSenha12345"}).status_code == 200


def test_bootstrap_com_varios_administradores_so_redefine_o_inicial(dev, monkeypatch):
    dev.post("/api/admin/users", json=NOVO)
    monkeypatch.setenv("DEV_ADMIN_USERNAME", "inicial.novo")
    monkeypatch.setenv("DEV_ADMIN_PASSWORD", "SenhaInicial123")
    monkeypatch.setenv("DEV_ADMIN_RESET_PASSWORD", "true")
    servico.bootstrap_admin()
    assert servico.obter_usuario_por_username("inicial.novo") is not None          # o mais antigo foi renomeado
    assert servico.obter_usuario_por_username("dev") is None
    assert servico.obter_usuario_por_username("novo.admin") is not None            # o criado depois não foi tocado

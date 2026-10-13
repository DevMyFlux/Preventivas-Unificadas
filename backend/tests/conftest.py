"""Fixtures compartilhadas: aplicação Flask isolada (SQLite em memória) e helpers de login."""
import os

import pytest

# Nenhum teste fala com o Neovero real nem usa credenciais reais.
os.environ.pop("NEOVERO_USERNAME", None)
os.environ.pop("NEOVERO_PASSWORD", None)
os.environ["APP_ENV"] = "test"
os.environ["COOKIE_SECURE"] = "false"
os.environ["PASSWORD_MIN_LENGTH"] = "8"
os.environ.pop("DATABASE_URL", None)
os.environ.pop("CLOUD_SQL_CONNECTION_NAME", None)


@pytest.fixture(autouse=True)
def _scrypt_barato(monkeypatch):
    """scrypt com custo mínimo só nos testes (o código de produção usa o padrão forte do werkzeug)."""
    from werkzeug.security import generate_password_hash
    from core.auth import servico
    monkeypatch.setattr(servico, "hash_senha", lambda s: generate_password_hash(s, method="scrypt:1024:8:1"))


@pytest.fixture()
def app():
    from app_factory import create_app
    from core import cache
    cache.clear_all()
    flask_app = create_app("sqlite:///:memory:", bootstrap=False)
    flask_app.config["TESTING"] = True
    yield flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


def fazer_login(client, username, senha):
    r = client.post("/api/auth/login", json={"username": username, "password": senha})
    assert r.status_code == 200, r.get_json()
    client.environ_base["HTTP_X_CSRF_TOKEN"] = r.get_json()["csrf_token"]
    return r.get_json()


@pytest.fixture()
def criar_usuarios(app):
    """Cria o Dev e um usuário por unidade; devolve as senhas usadas nos testes."""
    from core.auth import servico
    from core.models import ROLE_DEV
    senha = "Senha12345"
    servico.criar_usuario("dev", senha, display_name="Dev", role=ROLE_DEV)
    servico.criar_usuario("ana.hmb", senha, display_name="Ana", unit="HMB")
    servico.criar_usuario("beto.hetrin", senha, display_name="Beto", unit="HETRIN")
    return senha

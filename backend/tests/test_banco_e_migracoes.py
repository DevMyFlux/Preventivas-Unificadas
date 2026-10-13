"""Banco de dados: migrações idempotentes/aditivas, resolução da conexão e histórico preservado."""
import pytest
from sqlalchemy import select, text

from core import db, migrations, models
from core.db import sessao
from core.settings import settings


def test_migracao_cria_as_tabelas_e_e_idempotente(app):
    assert {"users", "auth_sessions", "audit_log", "regra_resolucoes", "atribuicao_propostas",
            "colaborador_overlay", "schema_migrations"} <= migrations.tabelas_existentes()
    assert migrations.migrar() == []          # segunda execução: nada a aplicar
    with sessao() as s:
        assert [m.version for m in s.scalars(select(models.SchemaMigration)).all()] == [1, 2]


def test_migracao_nao_apaga_dados_existentes(app, criar_usuarios):
    antes = db.get_engine().connect().execute(text("SELECT COUNT(*) FROM users")).scalar()
    migrations.migrar()
    migrations.migrar()
    assert db.get_engine().connect().execute(text("SELECT COUNT(*) FROM users")).scalar() == antes == 3


def test_url_postgres_e_normalizada_para_driver_puro_python():
    assert db._normalizar_url("postgres://u:p@h/db") == "postgresql+pg8000://u:p@h/db"
    assert db._normalizar_url("postgresql://u:p@h/db") == "postgresql+pg8000://u:p@h/db"
    assert db._normalizar_url("sqlite:///x.db") == "sqlite:///x.db"


def test_cloud_sql_exige_variaveis_de_conexao(monkeypatch):
    pytest.importorskip("google.cloud.sql.connector")
    monkeypatch.setenv("CLOUD_SQL_CONNECTION_NAME", "projeto:regiao:instancia")
    monkeypatch.delenv("DB_USER", raising=False)
    monkeypatch.delenv("DB_PASSWORD", raising=False)
    monkeypatch.delenv("DB_NAME", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError) as e:
        db._criar_engine_cloud_sql()
    assert "DB_USER" in str(e.value) and "DB_PASSWORD" in str(e.value)


def test_identificador_da_instancia_sozinho_nao_e_credencial(monkeypatch):
    """O identificador projeto:regiao:instancia só localiza a instância — sem usuário/senha/banco
    a aplicação se recusa a conectar em vez de tentar adivinhar."""
    monkeypatch.setenv("CLOUD_SQL_CONNECTION_NAME", "gestao-rh-escalas:southamerica-east1:rh-monitoramento-db")
    assert settings.cloud_sql_connection_name.endswith("rh-monitoramento-db")
    assert settings.db_user is None and settings.db_password is None


def test_audit_log_nao_tem_rotas_de_delecao(app):
    regras = {(r.rule, m) for r in app.url_map.iter_rules() for m in r.methods}
    assert not [x for x in regras if x[0].startswith("/api/admin/audit") and x[1] in ("DELETE", "PUT", "PATCH", "POST")]

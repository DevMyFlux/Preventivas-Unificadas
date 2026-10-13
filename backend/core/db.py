"""
Acesso ao banco de dados (SQLAlchemy).

Ordem de resolução da conexão:
  1. `DATABASE_URL` (qualquer URL SQLAlchemy; `postgres://` e `postgresql://` são
     convertidas para o driver puro-Python pg8000).
  2. Cloud SQL via `CLOUD_SQL_CONNECTION_NAME` + `DB_USER` + `DB_PASSWORD` + `DB_NAME`
     (Cloud SQL Python Connector — exige credenciais GCP no ambiente, ex.
     GOOGLE_APPLICATION_CREDENTIALS; o identificador da instância sozinho NÃO dá acesso).
  3. SQLite local (`SQLITE_PATH`) — só para desenvolvimento/testes; em produção os
     dados ficariam num disco efêmero (a aplicação avisa no log).
"""
import logging
import os
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from core.settings import settings

log = logging.getLogger("myflux.db")

_engine: Engine | None = None
_SessionFactory: sessionmaker | None = None
_connector = None  # google.cloud.sql.connector.Connector, criado sob demanda


def agora_utc() -> datetime:
    """UTC *naive* — convenção única da aplicação para colunas DateTime (SQLite não
    preserva tz; usar naive-UTC em todos os motores evita comparações inconsistentes)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _normalizar_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+pg8000://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+pg8000://" + url[len("postgresql://"):]
    return url


def _criar_engine_cloud_sql() -> Engine:
    global _connector
    try:
        from google.cloud.sql.connector import Connector, IPTypes
    except ImportError as exc:  # pragma: no cover - depende do pacote opcional
        raise RuntimeError(
            "CLOUD_SQL_CONNECTION_NAME definido, mas 'cloud-sql-python-connector' não está "
            "instalado. Instale-o (consta em requirements.txt) ou use DATABASE_URL."
        ) from exc
    faltando = [n for n, v in (("DB_USER", settings.db_user), ("DB_PASSWORD", settings.db_password),
                               ("DB_NAME", settings.db_name)) if not v]
    if faltando:
        raise RuntimeError(f"Cloud SQL configurado, mas faltam variáveis: {', '.join(faltando)}")

    ip_type = IPTypes.PRIVATE if settings.cloud_sql_ip_type == "private" else IPTypes.PUBLIC
    _connector = Connector()

    def _conn():
        return _connector.connect(
            settings.cloud_sql_connection_name, "pg8000",
            user=settings.db_user, password=settings.db_password, db=settings.db_name,
            ip_type=ip_type,
        )

    return create_engine("postgresql+pg8000://", creator=_conn, pool_pre_ping=True, pool_recycle=1800)


def _criar_engine_sqlite(caminho: str) -> Engine:
    if caminho == ":memory:":
        eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    else:
        os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
        eng = create_engine(f"sqlite:///{caminho}", connect_args={"check_same_thread": False})

    @event.listens_for(eng, "connect")
    def _pragmas(dbapi_conn, _):  # pragma: no cover - trivial
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    return eng


def init_engine(url: str | None = None) -> Engine:
    """Cria (ou recria) o engine global. `url` explícita tem prioridade — usada em testes."""
    global _engine, _SessionFactory
    if url:
        if url == "sqlite://:memory:" or url == "sqlite:///:memory:":
            eng = _criar_engine_sqlite(":memory:")
        elif url.startswith("sqlite:///"):
            eng = _criar_engine_sqlite(url[len("sqlite:///"):])
        else:
            eng = create_engine(_normalizar_url(url), pool_pre_ping=True)
    elif settings.database_url:
        u = _normalizar_url(settings.database_url)
        eng = _criar_engine_sqlite(u[len("sqlite:///"):]) if u.startswith("sqlite:///") else create_engine(u, pool_pre_ping=True)
    elif settings.cloud_sql_connection_name:
        eng = _criar_engine_cloud_sql()
    else:
        if settings.producao:
            log.warning(
                "Nenhum banco configurado (DATABASE_URL / CLOUD_SQL_*): usando SQLite local em "
                "'%s'. Em ambientes com disco efêmero (ex.: Railway sem volume) usuários e logs "
                "SE PERDEM a cada deploy.", settings.sqlite_path)
        eng = _criar_engine_sqlite(settings.sqlite_path)

    if _engine is not None:
        _engine.dispose()
    _engine = eng
    _SessionFactory = sessionmaker(bind=eng, expire_on_commit=False, future=True)
    return eng


def get_engine() -> Engine:
    if _engine is None:
        init_engine()
    assert _engine is not None
    return _engine


def dialeto() -> str:
    return get_engine().dialect.name


@contextmanager
def sessao() -> Session:
    """Sessão transacional: commit ao sair sem erro, rollback em exceção."""
    if _SessionFactory is None:
        init_engine()
    assert _SessionFactory is not None
    s = _SessionFactory()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()

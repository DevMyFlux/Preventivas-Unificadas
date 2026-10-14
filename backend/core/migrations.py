"""
Migrações de esquema — leves, ordenadas e *aditivas*.

Regras:
  * Cada migração tem um número de versão único e crescente e roda uma única vez
    (registrada em `schema_migrations`).
  * Só criam tabelas/colunas/índices novos — nada de DROP/ALTER destrutivo. Dados
    existentes nunca são tocados.
  * Reexecutar `migrar()` é seguro (idempotente).

Para adicionar uma migração: acrescente uma função `_mNNN_descricao(conn)` e registre-a
em MIGRACOES com o próximo número.
"""
import logging
import time

from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError

from core import models
from core.db import get_engine

log = logging.getLogger("myflux.migrations")


def _m001_esquema_inicial(conn) -> None:
    """Cria users, auth_sessions, audit_log, regra_resolucoes e atribuicao_propostas.
    `create_all` só cria o que ainda não existe."""
    models.Base.metadata.create_all(conn)


def _m002_overlay_de_colaboradores(conn) -> None:
    """Cria `colaborador_overlay` (substitui o JSON em disco como armazenamento durável).
    Aditiva: o JSON versionado continua existindo e é a semente da 1ª leitura de cada unidade."""
    models.ColaboradorOverlay.__table__.create(conn, checkfirst=True)


def _m003_atividade_das_sessoes(conn) -> None:
    """Acrescenta a `auth_sessions` os contadores de atividade (tempo ativo e nº de atividades).
    Aditiva: ALTER TABLE ... ADD COLUMN com DEFAULT 0; sessões antigas ficam com 0 (desconhecido)."""
    existentes = {c["name"] for c in inspect(conn).get_columns("auth_sessions")}
    for coluna in ("active_seconds", "activity_count"):
        if coluna not in existentes:
            conn.execute(text(f"ALTER TABLE auth_sessions ADD COLUMN {coluna} INTEGER NOT NULL DEFAULT 0"))


def _m004_suporte(conn) -> None:
    """Cria `suporte_solicitacoes` (Sugestões e Suporte). Aditiva."""
    models.SuporteSolicitacao.__table__.create(conn, checkfirst=True)


def _m005_historico_de_responsavel(conn) -> None:
    """Cria `os_responsavel_historico` (transferências observadas). Aditiva."""
    models.OsResponsavelHistorico.__table__.create(conn, checkfirst=True)


def _m006_caixa_de_mensagens(conn) -> None:
    """Acrescenta a `suporte_solicitacoes` a situação de tratamento (nova/lida/resolvida). Aditiva."""
    existentes = {c["name"] for c in inspect(conn).get_columns("suporte_solicitacoes")}
    if "situacao" not in existentes:
        conn.execute(text("ALTER TABLE suporte_solicitacoes ADD COLUMN situacao VARCHAR(12) NOT NULL DEFAULT 'nova'"))
    if "tratada_em" not in existentes:
        conn.execute(text("ALTER TABLE suporte_solicitacoes ADD COLUMN tratada_em TIMESTAMP"))
    if "tratada_por" not in existentes:
        conn.execute(text("ALTER TABLE suporte_solicitacoes ADD COLUMN tratada_por VARCHAR(64)"))


MIGRACOES = [
    (1, "esquema_inicial", _m001_esquema_inicial),
    (2, "overlay_de_colaboradores", _m002_overlay_de_colaboradores),
    (3, "atividade_das_sessoes", _m003_atividade_das_sessoes),
    (4, "suporte", _m004_suporte),
    (5, "historico_de_responsavel", _m005_historico_de_responsavel),
    (6, "caixa_de_mensagens", _m006_caixa_de_mensagens),
]


def _migrar_uma_vez() -> list[int]:
    """Aplica as migrações pendentes. Retorna as versões aplicadas nesta chamada."""
    engine = get_engine()
    aplicadas: list[int] = []
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            # vários workers do gunicorn importam o app ao mesmo tempo: serializa a migração
            conn.execute(text("SELECT pg_advisory_xact_lock(746600101)"))
        models.SchemaMigration.__table__.create(conn, checkfirst=True)
        ja = {r[0] for r in conn.execute(text("SELECT version FROM schema_migrations"))}
        for versao, nome, fn in MIGRACOES:
            if versao in ja:
                continue
            log.info("Aplicando migração %03d_%s", versao, nome)
            fn(conn)
            conn.execute(models.SchemaMigration.__table__.insert().values(
                version=versao, name=nome, applied_at=models.agora_utc()))
            aplicadas.append(versao)
    return aplicadas


def migrar() -> list[int]:
    """Aplica as migrações pendentes. Vários workers do gunicorn importam o app ao mesmo tempo: no
    PostgreSQL uma trava consultiva os serializa; no SQLite (sem trava) o perdedor da corrida recebe
    "table already exists"/"UNIQUE constraint" — então refazemos: na nova tentativa a migração já
    está registrada e nada mais é aplicado."""
    ultimo = None
    for tentativa in range(5):
        try:
            return _migrar_uma_vez()
        except (OperationalError, ProgrammingError, IntegrityError) as exc:
            ultimo = exc
            log.warning("Migração concorrente (tentativa %d): %s", tentativa + 1, type(exc).__name__)
            time.sleep(0.3 * (tentativa + 1))
    raise ultimo


def tabelas_existentes() -> set[str]:
    return set(inspect(get_engine()).get_table_names())

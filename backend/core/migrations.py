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

from sqlalchemy import inspect, text

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


MIGRACOES = [
    (1, "esquema_inicial", _m001_esquema_inicial),
    (2, "overlay_de_colaboradores", _m002_overlay_de_colaboradores),
]


def migrar() -> list[int]:
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


def tabelas_existentes() -> set[str]:
    return set(inspect(get_engine()).get_table_names())

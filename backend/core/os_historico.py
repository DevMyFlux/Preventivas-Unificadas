"""
Histórico de responsável das OS — transferências OBSERVADAS.

O Neovero só devolve o responsável ATUAL da OS. Para tornar auditável quem estava com a OS e quando
passou para outra pessoa, a aplicação registra uma observação (append-only) na primeira vez que vê uma OS
e a cada vez que o responsável muda entre duas leituras. Isto é um registro do que a aplicação VIU:
mudanças feitas no Neovero antes da primeira leitura (ou entre duas leituras, em sequência) não são
reconstruídas. O motivo da transferência é anotado por uma pessoa (nunca inventado pelo sistema).

Isolamento: toda consulta e toda gravação carrega a unidade; nada cruza HETRIN × HMB.
"""
import logging

from sqlalchemy import func, select

from core.db import agora_utc, sessao
from core.models import OsResponsavelHistorico

log = logging.getLogger("myflux.os_historico")

TIPO_INICIAL = "inicial"
TIPO_TRANSFERENCIA = "transferencia"
MOTIVO_MAX = 300


def _nome(v) -> str | None:
    v = (v or "").strip()
    return v or None


def registrar_observacoes(unit: str, os_vistas: list[dict]) -> int:
    """Registra primeira observação / mudança de responsável. `os_vistas`: dicts com `os_numero`, `os_id`,
    `plano`, `responsavel` (nome no Neovero ou None). Devolve quantas linhas foram gravadas."""
    atuais = {str(o["os_numero"]): o for o in os_vistas if o.get("os_numero") not in (None, "", "—")}
    if not atuais:
        return 0
    gravadas = 0
    agora = agora_utc()
    with sessao() as s:
        ultimo_id = (select(func.max(OsResponsavelHistorico.id)).where(
            OsResponsavelHistorico.unit == unit, OsResponsavelHistorico.os_numero.in_(list(atuais)))
            .group_by(OsResponsavelHistorico.os_numero))
        anteriores = {r.os_numero: r for r in s.scalars(select(OsResponsavelHistorico).where(
            OsResponsavelHistorico.id.in_(ultimo_id))).all()}
        for numero, o in atuais.items():
            atual = _nome(o.get("responsavel"))
            ant = anteriores.get(numero)
            if ant is None:
                tipo, anterior = TIPO_INICIAL, None
            elif _nome(ant.responsavel) != atual:
                tipo, anterior = TIPO_TRANSFERENCIA, _nome(ant.responsavel)
            else:
                continue
            s.add(OsResponsavelHistorico(unit=unit, os_numero=numero, os_id=o.get("os_id"), plano=(o.get("plano") or "")[:200],
                                         responsavel=atual, anterior=anterior, tipo=tipo, observado_em=agora))
            gravadas += 1
    return gravadas


def listar(unit: str, *, os_numero: str | None = None, so_transferencias: bool = True, limite: int = 500) -> list[dict]:
    with sessao() as s:
        stmt = select(OsResponsavelHistorico).where(OsResponsavelHistorico.unit == unit)
        if os_numero:
            stmt = stmt.where(OsResponsavelHistorico.os_numero == str(os_numero))
        if so_transferencias:
            stmt = stmt.where(OsResponsavelHistorico.tipo == TIPO_TRANSFERENCIA)
        linhas = s.scalars(stmt.order_by(OsResponsavelHistorico.id.desc()).limit(limite)).all()
        return [serializar(r) for r in linhas]


def serializar(r: OsResponsavelHistorico) -> dict:
    return {
        "id": r.id, "os_numero": r.os_numero, "os_id": r.os_id, "plano": r.plano, "de": r.anterior, "para": r.responsavel,
        "tipo": r.tipo, "observado_em": r.observado_em.isoformat() + "Z", "motivo": r.motivo, "motivo_por": r.motivo_por,
    }


def anotar_motivo(unit: str, registro_id: int, motivo: str, usuario: str) -> dict | None:
    """Anota (ou corrige) o motivo de uma transferência. Só dentro da unidade do registro."""
    motivo = " ".join((motivo or "").split())[:MOTIVO_MAX]
    with sessao() as s:
        r = s.get(OsResponsavelHistorico, registro_id)
        if r is None or r.unit != unit:
            return None
        r.motivo, r.motivo_por = (motivo or None), (usuario if motivo else None)
        s.flush()
        return serializar(r)

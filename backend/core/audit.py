"""
Auditoria: trilha append-only de quem fez o quê, quando, em qual unidade e com qual
resultado. Nunca grava senhas, tokens, cookies ou segredos — `sanitizar()` remove/mascara
qualquer chave com nome sensível antes de persistir.

Falhar ao gravar um evento de auditoria NUNCA derruba a requisição do usuário (o erro vai
para o log da aplicação); a perda de um evento é preferível a indisponibilidade, mas é
sempre registrada em log para investigação.
"""
import json
import logging
import re
from datetime import datetime

from core.db import agora_utc, sessao
from core.models import AuditLog

log = logging.getLogger("myflux.audit")

_CHAVE_SENSIVEL = re.compile(
    r"pass|senha|secret|token|authorization|cookie|csrf|api[_-]?key|credential|hash", re.I
)
_MAX_STR = 500
_MAX_ITENS = 50
_MAX_PROFUNDIDADE = 4


def sanitizar(valor, _nivel: int = 0):
    """Devolve uma cópia do valor segura para persistir: chaves sensíveis viram
    "[REDACTED]", strings são truncadas e a estrutura tem tamanho/profundidade limitados."""
    if _nivel > _MAX_PROFUNDIDADE:
        return "[...]"
    if isinstance(valor, dict):
        saida = {}
        for i, (k, v) in enumerate(valor.items()):
            if i >= _MAX_ITENS:
                saida["..."] = "[truncado]"
                break
            saida[str(k)] = "[REDACTED]" if _CHAVE_SENSIVEL.search(str(k)) else sanitizar(v, _nivel + 1)
        return saida
    if isinstance(valor, (list, tuple, set)):
        itens = [sanitizar(v, _nivel + 1) for v in list(valor)[:_MAX_ITENS]]
        if len(valor) > _MAX_ITENS:
            itens.append("[truncado]")
        return itens
    if isinstance(valor, str):
        return valor if len(valor) <= _MAX_STR else valor[:_MAX_STR] + "…"
    if isinstance(valor, (int, float, bool)) or valor is None:
        return valor
    if isinstance(valor, datetime):
        return valor.isoformat()
    return str(valor)[:_MAX_STR]


def registrar(
    event: str,
    *,
    user=None,
    username: str | None = None,
    unit: str | None = None,
    session_id: int | None = None,
    module: str | None = None,
    action: str | None = None,
    resource: str | None = None,
    result: str = "success",
    status_code: int | None = None,
    method: str | None = None,
    path: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    details: dict | None = None,
) -> None:
    """Grava um evento. `user` (objeto User) preenche user_id/username/unit se não
    informados explicitamente."""
    try:
        with sessao() as s:
            s.add(AuditLog(
                ts=agora_utc(),
                user_id=getattr(user, "id", None),
                username=username or getattr(user, "username", None),
                unit=unit if unit is not None else getattr(user, "unit", None),
                session_id=session_id,
                event=event[:48],
                module=(module or None) and module[:32],
                action=(action or None) and action[:16],
                resource=(resource or None) and resource[:160],
                result=result,
                status_code=status_code,
                method=method,
                path=(path or None) and path[:255],
                ip=(ip or None) and ip[:64],
                user_agent=(user_agent or None) and user_agent[:255],
                details=json.dumps(sanitizar(details), ensure_ascii=False) if details else None,
            ))
    except Exception:  # pragma: no cover - defesa: auditoria não derruba a requisição
        log.exception("Falha ao gravar evento de auditoria %s", event)

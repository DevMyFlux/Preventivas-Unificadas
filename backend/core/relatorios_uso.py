"""
Consultas e relatórios de utilização (somente leitura sobre `audit_log` e `auth_sessions`).

Como diferenciamos *inatividade* de *ausência de registros*:
  * Cada login abre uma sessão com `last_activity_at` (atualizado por qualquer chamada
    autenticada e por heartbeat do frontend enquanto o usuário interage).
  * Uma sessão sem logout é encerrada, de forma explícita, como `idle_timeout`
    (passou do limite sem atividade — o fim registrado é a ÚLTIMA ATIVIDADE conhecida)
    ou `max_lifetime`. Isso cobre fechamento de aba, queda de rede e outras
    desconexões inesperadas.
  * Dentro de uma sessão, só podemos afirmar tempo "ocioso" quando há uma lacuna entre
    atividades maior que o limite de inatividade. Fora de qualquer sessão NÃO há como
    saber se a pessoa usou outro canal — por isso o relatório diz "sem registros no
    período" e nunca "não utilizou o sistema".
  * Registros começaram a ser coletados na data do primeiro evento da tabela; períodos
    anteriores a ela são "sem cobertura", não inatividade (`inicio_cobertura`).
"""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import func, select

from core.db import agora_utc, sessao
from core.models import AuditLog, AuthSession, User
from core.settings import settings

# Brasil não tem horário de verão desde 2019: UTC-3 fixo para agrupar por dia local.
_OFFSET_BR = timedelta(hours=-3)
MAX_LINHAS_RELATORIO = 200_000

NOTA_METODOLOGICA = (
    "Ausência de registros não significa inatividade: um usuário só é considerado ocioso quando "
    "há uma sessão aberta sem atividade além do limite configurado. Períodos sem sessão aparecem "
    "como 'sem registros'. A coleta de eventos começou em {inicio}."
)


def dia_local(ts: datetime) -> date:
    return (ts + _OFFSET_BR).date()


def intervalo_utc(d_ini: date | None, d_fim: date | None) -> tuple[datetime | None, datetime | None]:
    """Converte dias locais (BRT) [d_ini, d_fim] para um intervalo UTC [ini, fim)."""
    ini = datetime(d_ini.year, d_ini.month, d_ini.day) - _OFFSET_BR if d_ini else None
    fim = (datetime(d_fim.year, d_fim.month, d_fim.day) + timedelta(days=1)) - _OFFSET_BR if d_fim else None
    return ini, fim


def parse_data(valor: str | None) -> date | None:
    if not valor:
        return None
    try:
        return datetime.strptime(valor[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _aplicar_filtros(stmt, f: dict):
    ini, fim = intervalo_utc(f.get("data_ini"), f.get("data_fim"))
    if ini:
        stmt = stmt.where(AuditLog.ts >= ini)
    if fim:
        stmt = stmt.where(AuditLog.ts < fim)
    if f.get("user_id"):
        stmt = stmt.where(AuditLog.user_id == f["user_id"])
    if f.get("username"):
        stmt = stmt.where(AuditLog.username.like(f"%{f['username'].strip().lower()}%"))
    if f.get("unit"):
        stmt = stmt.where(AuditLog.unit == f["unit"])
    if f.get("module"):
        stmt = stmt.where(AuditLog.module == f["module"])
    if f.get("event"):
        stmt = stmt.where(AuditLog.event == f["event"])
    if f.get("action"):
        stmt = stmt.where(AuditLog.action == f["action"])
    if f.get("result"):
        stmt = stmt.where(AuditLog.result == f["result"])
    return stmt


def serializar_evento(e: AuditLog) -> dict:
    import json
    try:
        detalhes = json.loads(e.details) if e.details else None
    except ValueError:
        detalhes = None
    return {
        "id": e.id, "ts": e.ts.isoformat() + "Z", "user_id": e.user_id, "username": e.username, "unit": e.unit,
        "session_id": e.session_id, "event": e.event, "module": e.module, "action": e.action,
        "resource": e.resource, "result": e.result, "status_code": e.status_code, "method": e.method,
        "path": e.path, "ip": e.ip, "user_agent": e.user_agent, "details": detalhes,
    }


def listar_auditoria(filtros: dict, pagina: int = 1, por_pagina: int = 50) -> dict:
    por_pagina = max(1, min(int(por_pagina), 200))
    pagina = max(1, int(pagina))
    with sessao() as s:
        base = _aplicar_filtros(select(AuditLog), filtros)
        total = s.scalar(select(func.count()).select_from(base.subquery())) or 0
        linhas = s.scalars(
            base.order_by(AuditLog.ts.desc(), AuditLog.id.desc()).limit(por_pagina).offset((pagina - 1) * por_pagina)
        ).all()
        return {
            "total": total, "pagina": pagina, "por_pagina": por_pagina,
            "itens": [serializar_evento(e) for e in linhas],
        }


def todas_linhas_auditoria(filtros: dict) -> list[AuditLog]:
    with sessao() as s:
        return list(s.scalars(
            _aplicar_filtros(select(AuditLog), filtros).order_by(AuditLog.ts.desc()).limit(MAX_LINHAS_RELATORIO)
        ).all())


def inicio_cobertura() -> datetime | None:
    with sessao() as s:
        return s.scalar(select(func.min(AuditLog.ts)))


def _duracao_sessao(sess: AuthSession, agora: datetime) -> timedelta:
    fim = sess.ended_at or min(sess.last_activity_at, agora)
    return max(fim - sess.created_at, timedelta(0))


def listar_sessoes(filtros: dict, limite: int = 200) -> list[dict]:
    from core.auth import servico
    servico.finalizar_sessoes_vencidas()
    ini, fim = intervalo_utc(filtros.get("data_ini"), filtros.get("data_fim"))
    agora = agora_utc()
    with sessao() as s:
        stmt = select(AuthSession, User).join(User, User.id == AuthSession.user_id)
        if ini:
            stmt = stmt.where(AuthSession.created_at >= ini)
        if fim:
            stmt = stmt.where(AuthSession.created_at < fim)
        if filtros.get("user_id"):
            stmt = stmt.where(AuthSession.user_id == filtros["user_id"])
        if filtros.get("unit"):
            stmt = stmt.where(User.unit == filtros["unit"])
        linhas = s.execute(stmt.order_by(AuthSession.created_at.desc()).limit(limite)).all()
        saida = []
        for sess, user in linhas:
            saida.append({
                "id": sess.id, "user_id": user.id, "username": user.username, "unit": user.unit,
                "inicio": sess.created_at.isoformat() + "Z",
                "ultima_atividade": sess.last_activity_at.isoformat() + "Z",
                "fim": (sess.ended_at.isoformat() + "Z") if sess.ended_at else None,
                "encerramento": sess.end_reason or "em_andamento",
                "duracao_min": round(_duracao_sessao(sess, agora).total_seconds() / 60, 1),
                "ip": sess.ip,
            })
        return saida


def resumo(filtros: dict) -> dict:
    """Indicadores de atividade do período."""
    from core.auth import servico
    servico.finalizar_sessoes_vencidas()
    linhas = todas_linhas_auditoria(filtros)
    por_dia: dict[date, dict] = defaultdict(lambda: {"eventos": 0, "logins": 0, "usuarios": set()})
    por_modulo: Counter = Counter()
    por_usuario: dict[str, dict] = {}
    falhas: Counter = Counter()
    contadores = Counter()
    for e in linhas:
        dia = dia_local(e.ts)
        d = por_dia[dia]
        d["eventos"] += 1
        if e.event == "login_success":
            d["logins"] += 1
            contadores["logins"] += 1
        if e.event in ("login_failed", "login_blocked"):
            contadores["logins_falhos"] += 1
        if e.user_id:
            d["usuarios"].add(e.user_id)
        if e.module and e.event not in ("login_success", "login_failed", "login_blocked", "logout"):
            por_modulo[e.module] += 1
        if e.username:
            u = por_usuario.setdefault(e.username, {
                "username": e.username, "unit": e.unit, "eventos": 0, "escritas": 0, "exportacoes": 0,
                "falhas": 0, "ultimo_evento": e.ts})
            u["eventos"] += 1
            if e.action in ("create", "update", "delete"):
                u["escritas"] += 1
            if e.action == "export":
                u["exportacoes"] += 1
            if e.result != "success":
                u["falhas"] += 1
            if e.ts > u["ultimo_evento"]:
                u["ultimo_evento"] = e.ts
        if e.result == "denied":
            contadores["negados"] += 1
        if e.result == "failure" and e.event not in ("login_failed",):
            contadores["falhas"] += 1
        if e.result != "success" and e.event not in ("login_failed", "login_blocked"):
            falhas[(e.event, e.module, e.status_code)] += 1

    sessoes = listar_sessoes(filtros, limite=5000)
    enc = Counter(s["encerramento"] for s in sessoes)
    cobertura = inicio_cobertura()

    return {
        "periodo": {
            "data_ini": filtros["data_ini"].isoformat() if filtros.get("data_ini") else None,
            "data_fim": filtros["data_fim"].isoformat() if filtros.get("data_fim") else None,
        },
        "totais": {
            "eventos": len(linhas),
            "usuarios_ativos": len({e.user_id for e in linhas if e.user_id}),
            "logins": contadores["logins"],
            "logins_falhos": contadores["logins_falhos"],
            "acessos_negados": contadores["negados"],
            "falhas": contadores["falhas"],
            "sessoes": len(sessoes),
            "sessoes_em_andamento": enc.get("em_andamento", 0),
            "sessoes_por_encerramento": dict(enc),
            "tempo_medio_sessao_min": round(sum(s["duracao_min"] for s in sessoes) / len(sessoes), 1) if sessoes else 0,
        },
        "por_dia": [
            {"data": dia.isoformat(), "eventos": v["eventos"], "logins": v["logins"], "usuarios_ativos": len(v["usuarios"])}
            for dia, v in sorted(por_dia.items())
        ],
        "por_modulo": [{"modulo": m, "eventos": n} for m, n in por_modulo.most_common()],
        "por_usuario": sorted(
            ({**u, "ultimo_evento": u["ultimo_evento"].isoformat() + "Z"} for u in por_usuario.values()),
            key=lambda x: -x["eventos"]),
        "falhas_relevantes": [
            {"evento": ev, "modulo": mod, "status": st, "ocorrencias": n}
            for (ev, mod, st), n in falhas.most_common(15)
        ],
        "cobertura_desde": (cobertura.isoformat() + "Z") if cobertura else None,
        "nota": NOTA_METODOLOGICA.format(inicio=cobertura.strftime("%d/%m/%Y") if cobertura else "—"),
        "limite_inatividade_min": settings.sessao_ociosa_minutos,
    }


def relatorio_por_usuario(filtros: dict) -> list[dict]:
    """Uma linha por usuário cadastrado (inclusive quem não tem nenhum registro no período —
    marcado como 'Sem registros no período', não como 'inativo')."""
    from core.auth import servico
    servico.finalizar_sessoes_vencidas()
    linhas = todas_linhas_auditoria({**filtros, "user_id": None, "username": None})
    sessoes = listar_sessoes({**filtros, "user_id": None}, limite=20000)
    eventos_por_user: dict[int, list[AuditLog]] = defaultdict(list)
    for e in linhas:
        if e.user_id:
            eventos_por_user[e.user_id].append(e)
    sessoes_por_user: dict[int, list[dict]] = defaultdict(list)
    for sx in sessoes:
        sessoes_por_user[sx["user_id"]].append(sx)

    with sessao() as s:
        usuarios = s.scalars(select(User).order_by(User.username)).all()

    saida = []
    for u in usuarios:
        if filtros.get("unit") and u.unit != filtros["unit"]:
            continue
        if filtros.get("user_id") and u.id != filtros["user_id"]:
            continue
        evs = eventos_por_user.get(u.id, [])
        sess = sessoes_por_user.get(u.id, [])
        uteis = [e for e in evs if e.event not in ("login_failed", "login_blocked")]
        dias = {dia_local(e.ts) for e in uteis}
        saida.append({
            "username": u.username, "nome": u.display_name, "perfil": u.role, "unidade": u.unit or "Todas",
            "conta_ativa": u.is_active,
            "sessoes": len(sess),
            "tempo_em_sessao_min": round(sum(x["duracao_min"] for x in sess), 1),
            "eventos": len(uteis),
            "escritas": sum(1 for e in uteis if e.action in ("create", "update", "delete")),
            "exportacoes": sum(1 for e in uteis if e.action == "export"),
            "falhas": sum(1 for e in evs if e.result != "success"),
            "dias_com_registro": len(dias),
            "primeiro_evento": (min(e.ts for e in uteis).isoformat() + "Z") if uteis else None,
            "ultimo_evento": (max(e.ts for e in uteis).isoformat() + "Z") if uteis else None,
            "ultimo_login": (u.last_login_at.isoformat() + "Z") if u.last_login_at else None,
            "situacao": "Com atividade registrada" if uteis else "Sem registros no período",
        })
    return saida

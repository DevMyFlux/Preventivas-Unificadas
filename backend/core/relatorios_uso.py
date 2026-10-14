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


def _fim_efetivo(sess: AuthSession, agora: datetime) -> datetime:
    """Fim usado no tempo de sessão: o encerramento real; se ainda aberta, agora (ou a última atividade,
    se a sessão já passou do limite de inatividade e ainda não foi fechada pela varredura)."""
    if sess.ended_at:
        return sess.ended_at
    limite = timedelta(minutes=settings.sessao_ociosa_minutos)
    return agora if agora - sess.last_activity_at <= limite else sess.last_activity_at


def _duracao_sessao(sess: AuthSession, agora: datetime) -> timedelta:
    return max(_fim_efetivo(sess, agora) - sess.created_at, timedelta(0))


def estado_da_sessao(sess: AuthSession, agora: datetime) -> str:
    """'ativo' (atividade nos últimos minutos da janela), 'ocioso' (aberta, sem atividade recente, ainda
    dentro do limite) ou 'encerrada'. É a única forma confiável de dizer "usando agora"."""
    if sess.ended_at is not None:
        return "encerrada"
    ocioso_desde = agora - sess.last_activity_at
    if ocioso_desde > timedelta(minutes=settings.sessao_ociosa_minutos):
        return "encerrada"
    return "ativo" if ocioso_desde <= timedelta(minutes=settings.atividade_janela_minutos) else "ocioso"


ROTULO_ENCERRAMENTO = {
    "logout": "Saiu (logout)",
    "idle_timeout": "Expirou por inatividade",
    "max_lifetime": "Expirou (tempo máximo da sessão)",
    "user_deactivated": "Conta desativada",
    "revoked": "Encerrada pelo administrador",
    "password_changed": "Senha alterada",
}


def _minutos(seg: float) -> float:
    return round(seg / 60, 1)


def _serializar_sessao(sess: AuthSession, user: User, agora: datetime) -> dict:
    total_s = _duracao_sessao(sess, agora).total_seconds()
    ativo_s = min(sess.active_seconds or 0, total_s) if total_s else 0
    estado = estado_da_sessao(sess, agora)
    return {
        "id": sess.id, "user_id": user.id, "username": user.username, "nome": user.display_name, "unit": user.unit,
        "inicio": sess.created_at.isoformat() + "Z",
        "ultima_atividade": sess.last_activity_at.isoformat() + "Z",
        "fim": (sess.ended_at.isoformat() + "Z") if sess.ended_at else None,
        "estado": estado,
        "encerramento": sess.end_reason or ("em_andamento" if estado != "encerrada" else "expirada_nao_registrada"),
        "motivo_texto": (ROTULO_ENCERRAMENTO.get(sess.end_reason, sess.end_reason) if sess.end_reason
                         else ("Em andamento" if estado != "encerrada" else "Expirada (aguardando registro)")),
        "duracao_min": _minutos(total_s),
        "tempo_ativo_min": _minutos(ativo_s),
        "tempo_ocioso_min": _minutos(max(total_s - ativo_s, 0)),
        "atividades": sess.activity_count or 0,
        "por_inatividade": sess.end_reason == "idle_timeout",
        "ip": sess.ip,
    }


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
        return [_serializar_sessao(sess, user, agora) for sess, user in linhas]


def ativos_agora(filtros: dict | None = None) -> list[dict]:
    """Sessões abertas neste momento, classificadas em ativo/ocioso (somente o que o backend consegue
    afirmar com confiança: última atividade válida dentro da janela)."""
    from core.auth import servico
    servico.finalizar_sessoes_vencidas()
    filtros = filtros or {}
    agora = agora_utc()
    with sessao() as s:
        stmt = select(AuthSession, User).join(User, User.id == AuthSession.user_id).where(AuthSession.ended_at.is_(None))
        if filtros.get("unit"):
            stmt = stmt.where(User.unit == filtros["unit"])
        if filtros.get("user_id"):
            stmt = stmt.where(AuthSession.user_id == filtros["user_id"])
        itens = [_serializar_sessao(sess, user, agora) for sess, user in s.execute(stmt).all()]
    return sorted((i for i in itens if i["estado"] != "encerrada"), key=lambda x: x["ultima_atividade"], reverse=True)


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
    enc = Counter(x["encerramento"] for x in sessoes)
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
            "sessoes_em_andamento": sum(1 for x in sessoes if x["estado"] != "encerrada"),
            "sessoes_por_encerramento": dict(enc),
            "sessoes_por_inatividade": sum(1 for x in sessoes if x["por_inatividade"]),
            "tempo_medio_sessao_min": round(sum(x["duracao_min"] for x in sessoes) / len(sessoes), 1) if sessoes else 0,
            "tempo_total_sessao_min": round(sum(x["duracao_min"] for x in sessoes), 1),
            "tempo_total_ativo_min": round(sum(x["tempo_ativo_min"] for x in sessoes), 1),
            "tempo_total_ocioso_min": round(sum(x["tempo_ocioso_min"] for x in sessoes), 1),
            "usuarios_ativos_agora": len({x["user_id"] for x in ativos_agora(filtros) if x["estado"] == "ativo"}),
            "usuarios_online_agora": len({x["user_id"] for x in ativos_agora(filtros)}),
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
    """Uma linha por usuário cadastrado, com os indicadores de utilização do período.

    CRITÉRIOS EXPLÍCITOS (nunca se afirma "não utiliza"):
      * "Utilizou no período": há ao menos uma sessão iniciada ou um evento (exceto falhas de login).
      * "Sem registros no período": nenhuma sessão/evento. O campo `parecer` diz se o período está
        inteiramente dentro da coleta (ausência de registro) ou só em parte (a coleta começou depois
        do início do período — nesse caso NADA pode ser concluído sobre o trecho anterior).
      * Tempo de sessão != tempo ativo: o ativo soma os intervalos entre atividades válidas (cada um
        limitado a ACTIVITY_WINDOW_MINUTES); o ocioso é a diferença."""
    from core.auth import servico
    servico.finalizar_sessoes_vencidas()
    linhas = todas_linhas_auditoria({**filtros, "user_id": None, "username": None})
    sessoes = listar_sessoes({**filtros, "user_id": None}, limite=20000)
    cobertura = inicio_cobertura()
    ini_local = filtros.get("data_ini")
    cobertura_dia = dia_local(cobertura) if cobertura else None

    eventos_por_user: dict[int, list[AuditLog]] = defaultdict(list)
    for e in linhas:
        if e.user_id:
            eventos_por_user[e.user_id].append(e)
    sessoes_por_user: dict[int, list[dict]] = defaultdict(list)
    for sx in sessoes:
        sessoes_por_user[sx["user_id"]].append(sx)

    with sessao() as s:
        usuarios = s.scalars(select(User).order_by(User.username)).all()
        ultima_sessao = dict(s.execute(
            select(AuthSession.user_id, func.max(AuthSession.created_at)).group_by(AuthSession.user_id)).all())

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
        utilizou = bool(sess or uteis)
        abertas = [x for x in sess if x["estado"] != "encerrada"]
        estado_agora = ("ativo" if any(x["estado"] == "ativo" for x in abertas)
                        else "ocioso" if abertas else "offline")
        if utilizou:
            parecer = "Utilizou no período"
        elif cobertura_dia is None or (ini_local and ini_local < cobertura_dia):
            inicio = cobertura_dia.strftime("%d/%m/%Y") if cobertura_dia else "—"
            parecer = f"Sem registros — a coleta de utilização começou em {inicio}; o período anterior não é coberto"
        else:
            parecer = "Sem registros no período (período coberto pela coleta)"
        ultimo_ev = max((e.ts for e in uteis), default=None)
        ult_sess = ultima_sessao.get(u.id)
        saida.append({
            "id": u.id, "username": u.username, "nome": u.display_name, "perfil": u.role, "unidade": u.unit or "Todas",
            "conta_ativa": u.is_active,
            "ultimo_acesso": (ult_sess.isoformat() + "Z") if ult_sess else None,
            "acessos": len(sess),
            "sessoes": len(sess),
            "tempo_sessao_min": round(sum(x["duracao_min"] for x in sess), 1),
            "tempo_ativo_min": round(sum(x["tempo_ativo_min"] for x in sess), 1),
            "tempo_ocioso_min": round(sum(x["tempo_ocioso_min"] for x in sess), 1),
            "sessoes_por_inatividade": sum(1 for x in sess if x["por_inatividade"]),
            "estado_agora": estado_agora,
            "eventos": len(uteis),
            "escritas": sum(1 for e in uteis if e.action in ("create", "update", "delete")),
            "exportacoes": sum(1 for e in uteis if e.action == "export"),
            "falhas": sum(1 for e in evs if e.result != "success"),
            "dias_com_registro": len(dias),
            "primeiro_evento": (min(e.ts for e in uteis).isoformat() + "Z") if uteis else None,
            "ultimo_evento": (ultimo_ev.isoformat() + "Z") if ultimo_ev else None,
            "ultimo_login": (u.last_login_at.isoformat() + "Z") if u.last_login_at else None,
            "utilizou": utilizou,
            "situacao": "Com utilização registrada" if utilizou else "Sem utilização registrada",
            "parecer": parecer,
        })
    return saida


def indicadores_gerais(itens: list[dict]) -> dict:
    """Totais coerentes com a tabela por usuário (mesma fonte) — sem recalcular de outra forma."""
    return {
        "usuarios_cadastrados": len(itens),
        "usuarios_que_utilizaram": sum(1 for i in itens if i["utilizou"]),
        "usuarios_sem_utilizacao_registrada": sum(1 for i in itens if i["conta_ativa"] and not i["utilizou"]),
        "usuarios_ativos_agora": sum(1 for i in itens if i["estado_agora"] == "ativo"),
        "usuarios_ociosos_agora": sum(1 for i in itens if i["estado_agora"] == "ocioso"),
        "acessos": sum(i["acessos"] for i in itens),
        "tempo_sessao_min": round(sum(i["tempo_sessao_min"] for i in itens), 1),
        "tempo_ativo_min": round(sum(i["tempo_ativo_min"] for i in itens), 1),
        "tempo_ocioso_min": round(sum(i["tempo_ocioso_min"] for i in itens), 1),
        "sessoes_por_inatividade": sum(i["sessoes_por_inatividade"] for i in itens),
    }


_CRITERIOS = [
    "Tempo de sessão = do login ao encerramento (ou até agora, se aberta). NÃO significa que a pessoa estava usando.",
    "Tempo ativo = soma dos intervalos entre atividades válidas (cliques, navegação e consultas feitas pelo usuário), cada intervalo limitado a {janela} min.",
    "Tempo ocioso = tempo de sessão − tempo ativo. Chamadas automáticas em segundo plano NÃO contam como atividade.",
    "A sessão é encerrada no servidor após {limite} min sem atividade válida; o fim registrado é a última atividade.",
    "'Ativo agora' = sessão aberta com atividade nos últimos {janela} min; 'ocioso' = aberta, sem atividade recente, ainda dentro do limite.",
    "'Sem utilização registrada' indica ausência de registros no período — não comprova que a pessoa não usou o sistema.",
]


def criterios() -> list[str]:
    return [c.format(janela=settings.atividade_janela_minutos, limite=settings.sessao_ociosa_minutos) for c in _CRITERIOS]

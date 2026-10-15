"""
Área administrativa (somente Dev): usuários, auditoria, sessões e relatórios de uso.

A restrição ao perfil Dev é imposta pela guarda global (`core.auth.http`: qualquer
`/api/admin/*` exige `role == dev`) e RE-verificada aqui por decorator — defesa em
profundidade: mesmo que a guarda seja alterada, as rotas continuam protegidas.
"""
from functools import wraps

from flask import Blueprint, g, jsonify, request, send_file
from sqlalchemy import func, select

from core import audit, relatorios_uso
from core.auth import servico
from core.auth.http import ip_cliente
from core.auth.rotas import serializar_usuario
from core.db import agora_utc, sessao
from core.exporters import gerar_csv_tabela, gerar_excel_tabela
from core.models import ROLE_DEV, ROLE_USER, AuthSession, SuporteSolicitacao, User
from core.settings import settings
from core.unidades import UNIDADES, codigo_valido

bp = Blueprint("admin", __name__, url_prefix="/api/admin")

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def dev_required(fn):
    @wraps(fn)
    def _wrapper(*args, **kwargs):
        user = g.get("user")
        if user is None or not user.is_dev:
            return jsonify({"erro": "Acesso restrito ao administrador.", "codigo": "proibido"}), 403
        return fn(*args, **kwargs)
    return _wrapper


bp.before_request(lambda: None)  # a guarda global já autentica; dev_required valida o perfil


def _serializar(u: User, sessoes_abertas: int = 0) -> dict:
    return {
        **serializar_usuario(u),
        "is_active": u.is_active,
        "created_at": u.created_at.isoformat() + "Z",
        "created_by": u.created_by,
        "last_login_at": (u.last_login_at.isoformat() + "Z") if u.last_login_at else None,
        "deactivated_at": (u.deactivated_at.isoformat() + "Z") if u.deactivated_at else None,
        "locked_until": (u.locked_until.isoformat() + "Z") if u.locked_until and u.locked_until > agora_utc() else None,
        "sessoes_abertas": sessoes_abertas,
    }


def _filtros_periodo() -> dict:
    a = request.args
    uid = a.get("user_id", type=int)
    return {
        "data_ini": relatorios_uso.parse_data(a.get("data_ini")),
        "data_fim": relatorios_uso.parse_data(a.get("data_fim")),
        "user_id": uid,
        "username": a.get("username") or None,
        "unit": a.get("unit") if a.get("unit") in UNIDADES else None,
        "module": a.get("module") or None,
        "event": a.get("event") or None,
        "action": a.get("action") or None,
        "result": a.get("result") if a.get("result") in ("success", "failure", "denied") else None,
    }


def _auditar_admin(evento: str, alvo: User | None, detalhes: dict | None = None) -> None:
    audit.registrar(evento, user=g.user, session_id=g.auth_session.id, module="admin",
                    action="update", resource=alvo.username if alvo else None,
                    method=request.method, path=request.path, ip=ip_cliente(),
                    user_agent=request.headers.get("User-Agent"), details=detalhes)


# ── Usuários ──────────────────────────────────────────────────────────────────

@bp.route("/users", methods=["GET"])
@dev_required
def listar_usuarios():
    with sessao() as s:
        usuarios = s.scalars(select(User).order_by(User.role.desc(), User.username)).all()
        abertas = dict(s.execute(
            select(AuthSession.user_id, func.count()).where(AuthSession.ended_at.is_(None)).group_by(AuthSession.user_id)
        ).all())
    return jsonify({"itens": [_serializar(u, abertas.get(u.id, 0)) for u in usuarios],
                    "unidades": [{"codigo": u.codigo, "nome": u.nome} for u in UNIDADES.values()]})


@bp.route("/users", methods=["POST"])
@dev_required
def criar_usuario():
    """Cria usuário comum (vinculado a uma unidade) ou ADMINISTRADOR (`role: "dev"`, acessa todas as unidades).
    Só administradores chegam aqui (guarda global + `dev_required`): portanto só administrador cria administrador."""
    c = request.get_json(silent=True) or {}
    role = c.get("role", ROLE_USER)
    if role not in (ROLE_USER, ROLE_DEV):
        return jsonify({"erro": "Perfil inválido.", "codigo": "perfil_invalido", "campo": "role"}), 400
    try:
        user = servico.criar_usuario(
            str(c.get("username", "")), str(c.get("password", "")),
            display_name=str(c.get("display_name", "")), role=role, unit=c.get("unit"),
            criado_por=g.user.username, must_change_password=bool(c.get("must_change_password", False)),
        )
    except servico.ValidacaoError as e:
        return jsonify({"erro": e.mensagem, "campo": e.campo}), 400
    g.audit_details = {"perfil": user.role, "unidade": user.unit}
    return jsonify(_serializar(user)), 201


@bp.route("/users/<int:user_id>", methods=["PATCH"])
@dev_required
def editar_usuario(user_id: int):
    c = request.get_json(silent=True) or {}
    if "role" in c or "is_dev" in c:
        # perfil/permissão NÃO é editável por API: só existe o Dev (bootstrap) e usuários comuns
        return jsonify({"erro": "O perfil não pode ser alterado por esta operação.", "codigo": "perfil_imutavel"}), 400
    with sessao() as s:
        user = s.get(User, user_id)
        if not user:
            return jsonify({"erro": "Usuário não encontrado."}), 404
        mudancas = {}
        if "display_name" in c:
            user.display_name = str(c["display_name"]).strip()[:120]
            mudancas["display_name"] = user.display_name
        if "unit" in c:
            if user.is_dev:
                return jsonify({"erro": "O perfil Dev acessa todas as unidades; não tem vínculo."}), 400
            if not codigo_valido(c["unit"]):
                return jsonify({"erro": "Unidade inválida.", "campo": "unit"}), 400
            if c["unit"] != user.unit:
                mudancas["unit"] = {"de": user.unit, "para": c["unit"]}
                user.unit = c["unit"]
        s.flush()
        s.expunge(user)
    if "unit" in mudancas:
        # a unidade vem do cadastro a cada requisição, mas derrubamos as sessões abertas
        # para que a mudança de vínculo tenha efeito imediato e rastreável
        servico.encerrar_sessoes_do_usuario(user_id, "revoked")
    g.audit_details = mudancas
    return jsonify(_serializar(user))


@bp.route("/users/<int:user_id>", methods=["GET"])
@dev_required
def detalhe_usuario(user_id: int):
    """Ficha da conta: dados cadastrais, indicadores de utilização do período, sessões e últimos eventos."""
    with sessao() as s:
        user = s.get(User, user_id)
        if not user:
            return jsonify({"erro": "Usuário não encontrado."}), 404
        abertas = s.scalar(select(func.count()).select_from(AuthSession)
                           .where(AuthSession.user_id == user_id, AuthSession.ended_at.is_(None))) or 0
        s.expunge(user)
    f = {**_filtros_periodo(), "user_id": user_id, "unit": None, "username": None}
    uso = relatorios_uso.relatorio_por_usuario(f)
    eventos = relatorios_uso.listar_auditoria({"user_id": user_id, **{k: f[k] for k in ("data_ini", "data_fim")}}, 1, 25)
    return jsonify({
        "usuario": _serializar(user, abertas),
        "utilizacao": uso[0] if uso else None,
        "sessoes": relatorios_uso.listar_sessoes(f, limite=30),
        "eventos": eventos["itens"],
        "total_eventos": eventos["total"],
    })


@bp.route("/users/<int:user_id>/unlock", methods=["POST"])
@dev_required
def desbloquear_usuario(user_id: int):
    """Remove o bloqueio temporário por tentativas inválidas (não altera senha nem ativação)."""
    with sessao() as s:
        user = s.get(User, user_id)
        if not user:
            return jsonify({"erro": "Usuário não encontrado."}), 404
        user.failed_logins, user.locked_until = 0, None
        s.flush()
        s.expunge(user)
    g.audit_details = {"acao": "desbloqueio"}
    return jsonify(_serializar(user))


@bp.route("/users/<int:user_id>/active", methods=["POST"])
@dev_required
def alterar_ativo(user_id: int):
    c = request.get_json(silent=True) or {}
    ativo = c.get("active")
    if not isinstance(ativo, bool):
        return jsonify({"erro": "Informe active true/false."}), 400
    with sessao() as s:
        user = s.get(User, user_id)
        if not user:
            return jsonify({"erro": "Usuário não encontrado."}), 404
        if user.is_dev and not ativo:
            if user.id == g.user.id:
                return jsonify({"erro": "Você não pode desativar a sua própria conta de administrador.",
                                "codigo": "admin_proprio"}), 400
            outros = s.scalar(select(func.count()).select_from(User).where(
                User.role == ROLE_DEV, User.is_active.is_(True), User.id != user.id)) or 0
            if outros == 0:    # nunca fica sem administrador ativo
                return jsonify({"erro": "Não é possível desativar o último administrador ativo.", "codigo": "dev_protegido"}), 400
        user.is_active = ativo
        user.deactivated_at = None if ativo else agora_utc()
        if ativo:
            user.failed_logins = 0
            user.locked_until = None
        s.flush()
        s.expunge(user)
    encerradas = 0 if ativo else servico.encerrar_sessoes_do_usuario(user_id, "user_deactivated")
    g.audit_details = {"ativo": ativo, "sessoes_encerradas": encerradas}
    return jsonify(_serializar(user))


@bp.route("/users/<int:user_id>/password", methods=["POST"])
@dev_required
def redefinir_senha(user_id: int):
    c = request.get_json(silent=True) or {}
    alvo = servico.obter_usuario(user_id)
    if not alvo:
        return jsonify({"erro": "Usuário não encontrado."}), 404
    if alvo.is_dev and alvo.id != g.user.id:
        return jsonify({"erro": "Cada administrador altera a própria senha; a senha de outro administrador não pode ser redefinida aqui."}), 403
    try:
        servico.alterar_senha(user_id, str(c.get("password", "")), forcar_troca=bool(c.get("must_change_password", True)))
    except servico.ValidacaoError as e:
        return jsonify({"erro": e.mensagem, "campo": e.campo}), 400
    g.audit_details = {"forcar_troca": bool(c.get("must_change_password", True))}  # nunca a senha
    return jsonify({"ok": True})


# ── Auditoria / sessões / relatórios ──────────────────────────────────────────

# ── caixa de mensagens (Sugestões e Suporte) ─────────────────────────────────

_SITUACOES_MENSAGEM = ("nova", "lida", "resolvida")


def _serializar_mensagem(m: SuporteSolicitacao) -> dict:
    return {
        "id": m.id, "ts": m.ts.isoformat() + "Z", "username": m.username, "unit": m.unit, "nome": m.nome, "email": m.email,
        "tipo": m.tipo, "mensagem": m.mensagem, "entrega": m.status, "situacao": m.situacao,
        "tratada_em": (m.tratada_em.isoformat() + "Z") if m.tratada_em else None, "tratada_por": m.tratada_por,
    }


@bp.route("/suporte", methods=["GET"])
@dev_required
def listar_mensagens():
    """Caixa de mensagens enviadas pelos usuários (somente Dev). Filtros: situacao, tipo, unit; paginada."""
    a = request.args
    pagina = max(1, a.get("page", 1, type=int))
    por_pagina = min(100, max(1, a.get("page_size", 25, type=int)))
    with sessao() as s:
        base = select(SuporteSolicitacao).where(SuporteSolicitacao.status != "enviando")
        if a.get("situacao") in _SITUACOES_MENSAGEM:
            base = base.where(SuporteSolicitacao.situacao == a["situacao"])
        if a.get("tipo") in ("sugestao", "problema", "melhoria"):
            base = base.where(SuporteSolicitacao.tipo == a["tipo"])
        if a.get("unit") in UNIDADES:
            base = base.where(SuporteSolicitacao.unit == a["unit"])
        total = s.scalar(select(func.count()).select_from(base.subquery())) or 0
        linhas = s.scalars(base.order_by(SuporteSolicitacao.id.desc()).offset((pagina - 1) * por_pagina).limit(por_pagina)).all()
        itens = [_serializar_mensagem(m) for m in linhas]
        nao_lidas = s.scalar(select(func.count()).select_from(SuporteSolicitacao).where(
            SuporteSolicitacao.situacao == "nova", SuporteSolicitacao.status != "enviando")) or 0
    return jsonify({"total": total, "pagina": pagina, "por_pagina": por_pagina, "itens": itens, "nao_lidas": nao_lidas})


@bp.route("/suporte/contagem", methods=["GET"])
@dev_required
def contagem_mensagens():
    with sessao() as s:
        n = s.scalar(select(func.count()).select_from(SuporteSolicitacao).where(
            SuporteSolicitacao.situacao == "nova", SuporteSolicitacao.status != "enviando")) or 0
    return jsonify({"nao_lidas": n})


@bp.route("/suporte/<int:mensagem_id>", methods=["PATCH"])
@dev_required
def tratar_mensagem(mensagem_id: int):
    """Marca a mensagem como nova/lida/resolvida (registra quem e quando)."""
    situacao = (request.get_json(silent=True) or {}).get("situacao")
    if situacao not in _SITUACOES_MENSAGEM:
        return jsonify({"erro": "Situação inválida.", "codigo": "validacao", "campo": "situacao"}), 400
    with sessao() as s:
        m = s.get(SuporteSolicitacao, mensagem_id)
        if m is None or m.status == "enviando":
            return jsonify({"erro": "Mensagem não encontrada."}), 404
        m.situacao = situacao
        m.tratada_em, m.tratada_por = (None, None) if situacao == "nova" else (agora_utc(), g.user.username)
        s.flush()
        saida = _serializar_mensagem(m)
    g.audit_details = {"mensagem": mensagem_id, "situacao": situacao}
    return jsonify(saida)


@bp.route("/audit", methods=["GET"])
@dev_required
def auditoria():
    r = relatorios_uso.listar_auditoria(
        _filtros_periodo(), request.args.get("page", 1, type=int), request.args.get("page_size", 50, type=int))
    return jsonify(r)


@bp.route("/audit/summary", methods=["GET"])
@dev_required
def auditoria_resumo():
    return jsonify(relatorios_uso.resumo(_filtros_periodo()))


@bp.route("/sessions", methods=["GET"])
@dev_required
def sessoes():
    return jsonify({"itens": relatorios_uso.listar_sessoes(_filtros_periodo())})


@bp.route("/usage", methods=["GET"])
@dev_required
def uso_por_usuario():
    f = _filtros_periodo()
    itens = relatorios_uso.relatorio_por_usuario(f)
    return jsonify({
        "itens": itens,
        "indicadores": relatorios_uso.indicadores_gerais(itens),
        "ativos_agora": relatorios_uso.ativos_agora(f),
        "criterios": relatorios_uso.criterios(),
        "limite_inatividade_min": settings.sessao_ociosa_minutos,
        "janela_atividade_min": settings.atividade_janela_minutos,
        "cobertura_desde": (lambda c: (c.isoformat() + "Z") if c else None)(relatorios_uso.inicio_cobertura()),
        "nota": relatorios_uso.resumo(f)["nota"],
    })


def _enviar(buf, nome: str, mimetype: str):
    return send_file(buf, as_attachment=True, download_name=nome, mimetype=mimetype)


@bp.route("/audit/export", methods=["GET"])
@dev_required
def exportar_auditoria():
    f = _filtros_periodo()
    linhas = relatorios_uso.todas_linhas_auditoria(f)
    cabecalho = ["Data/Hora (UTC)", "Usuário", "Unidade", "Evento", "Módulo", "Ação", "Recurso", "Resultado",
                 "HTTP", "IP", "Detalhes"]
    dados = [[e.ts.strftime("%Y-%m-%d %H:%M:%S"), e.username or "", e.unit or "", e.event, e.module or "",
              e.action or "", e.resource or "", e.result, e.status_code or "", e.ip or "", e.details or ""]
             for e in linhas]
    g.audit_details = {"linhas": len(dados), "formato": request.args.get("format", "xlsx")}
    sufixo = agora_utc().strftime("%Y%m%d_%H%M%S")
    if request.args.get("format") == "csv":
        return _enviar(gerar_csv_tabela(cabecalho, dados), f"auditoria_{sufixo}.csv", "text/csv")
    larguras = [20, 18, 10, 26, 16, 10, 28, 11, 7, 16, 60]
    buf = gerar_excel_tabela("Auditoria de utilização", list(zip(cabecalho, larguras)), dados, "Auditoria")
    return _enviar(buf, f"auditoria_{sufixo}.xlsx", _XLSX)


@bp.route("/usage/export", methods=["GET"])
@dev_required
def exportar_uso():
    f = _filtros_periodo()
    itens = relatorios_uso.relatorio_por_usuario(f)
    cabecalho = ["Usuário", "Nome", "Unidade", "Conta ativa", "Último acesso (UTC)", "Acessos no período",
                 "Tempo de sessão (min)", "Tempo ativo (min)", "Tempo ocioso (min)", "Sessões encerradas por inatividade",
                 "Estado agora", "Eventos", "Alterações", "Exportações", "Falhas", "Dias com registro",
                 "Último evento (UTC)", "Situação", "Parecer"]
    dados = [[i["username"], i["nome"], i["unidade"], "Sim" if i["conta_ativa"] else "Não", i["ultimo_acesso"] or "",
              i["acessos"], i["tempo_sessao_min"], i["tempo_ativo_min"], i["tempo_ocioso_min"],
              i["sessoes_por_inatividade"], i["estado_agora"], i["eventos"], i["escritas"], i["exportacoes"],
              i["falhas"], i["dias_com_registro"], i["ultimo_evento"] or "", i["situacao"], i["parecer"]] for i in itens]
    g.audit_details = {"linhas": len(dados), "formato": request.args.get("format", "xlsx")}
    sufixo = agora_utc().strftime("%Y%m%d_%H%M%S")
    if request.args.get("format") == "csv":
        return _enviar(gerar_csv_tabela(cabecalho, dados), f"uso_{sufixo}.csv", "text/csv")
    larguras = [24, 22, 10, 10, 20, 10, 12, 12, 12, 14, 11, 9, 10, 11, 8, 11, 20, 24, 50]
    buf = gerar_excel_tabela("Relatório de utilização por usuário", list(zip(cabecalho, larguras)), dados, "Uso",
                             subtitulo=" | ".join(relatorios_uso.criterios()))
    return _enviar(buf, f"uso_{sufixo}.xlsx", _XLSX)

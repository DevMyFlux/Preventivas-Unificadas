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
from core.models import ROLE_USER, AuthSession, User
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
    c = request.get_json(silent=True) or {}
    if c.get("role", ROLE_USER) != ROLE_USER:
        return jsonify({"erro": "Somente o administrador inicial (Dev) tem perfil Dev; não é possível criar outro.",
                        "codigo": "perfil_invalido"}), 400
    try:
        user = servico.criar_usuario(
            str(c.get("username", "")), str(c.get("password", "")),
            display_name=str(c.get("display_name", "")), role=ROLE_USER, unit=c.get("unit"),
            criado_por=g.user.username, must_change_password=bool(c.get("must_change_password", False)),
        )
    except servico.ValidacaoError as e:
        return jsonify({"erro": e.mensagem, "campo": e.campo}), 400
    g.audit_details = {"unidade": user.unit}
    return jsonify(_serializar(user)), 201


@bp.route("/users/<int:user_id>", methods=["PATCH"])
@dev_required
def editar_usuario(user_id: int):
    c = request.get_json(silent=True) or {}
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
            return jsonify({"erro": "A conta Dev não pode ser desativada.", "codigo": "dev_protegido"}), 400
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
        return jsonify({"erro": "Somente o próprio Dev pode alterar a senha da conta Dev."}), 403
    try:
        servico.alterar_senha(user_id, str(c.get("password", "")), forcar_troca=bool(c.get("must_change_password", True)))
    except servico.ValidacaoError as e:
        return jsonify({"erro": e.mensagem, "campo": e.campo}), 400
    g.audit_details = {"forcar_troca": bool(c.get("must_change_password", True))}  # nunca a senha
    return jsonify({"ok": True})


# ── Auditoria / sessões / relatórios ──────────────────────────────────────────

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
    return jsonify({"itens": relatorios_uso.relatorio_por_usuario(f),
                    "nota": relatorios_uso.resumo(f)["nota"]})


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
    resumo = relatorios_uso.resumo(f)
    cabecalho = ["Usuário", "Nome", "Perfil", "Unidade", "Conta ativa", "Sessões", "Tempo em sessão (min)",
                 "Eventos", "Escritas", "Exportações", "Falhas", "Dias com registro", "Primeiro evento (UTC)",
                 "Último evento (UTC)", "Último login (UTC)", "Situação no período"]
    dados = [[i["username"], i["nome"], i["perfil"], i["unidade"], "Sim" if i["conta_ativa"] else "Não",
              i["sessoes"], i["tempo_em_sessao_min"], i["eventos"], i["escritas"], i["exportacoes"], i["falhas"],
              i["dias_com_registro"], i["primeiro_evento"] or "", i["ultimo_evento"] or "",
              i["ultimo_login"] or "", i["situacao"]] for i in itens]
    g.audit_details = {"linhas": len(dados), "formato": request.args.get("format", "xlsx")}
    sufixo = agora_utc().strftime("%Y%m%d_%H%M%S")
    if request.args.get("format") == "csv":
        return _enviar(gerar_csv_tabela(cabecalho, dados), f"uso_{sufixo}.csv", "text/csv")
    larguras = [18, 24, 8, 10, 10, 9, 14, 9, 9, 11, 8, 12, 20, 20, 20, 28]
    buf = gerar_excel_tabela("Relatório de utilização por usuário", list(zip(cabecalho, larguras)), dados,
                             "Uso", subtitulo=resumo["nota"])
    return _enviar(buf, f"uso_{sufixo}.xlsx", _XLSX)

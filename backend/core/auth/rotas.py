"""Rotas de autenticação: /api/auth/* e /api/health."""
from flask import Blueprint, g, jsonify, make_response, request

from core import audit
from core.auth import servico
from core.auth.http import ip_cliente
from core.settings import settings
from core.unidades import UNIDADES

bp = Blueprint("auth", __name__, url_prefix="/api")

_MODULOS_VALIDOS = {"planos", "preventivas", "colaboradores", "distribuicao", "regras", "admin", "login"}


def serializar_usuario(user) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "is_dev": user.is_dev,
        "unit": user.unit,
        "unit_name": UNIDADES[user.unit].nome if user.unit in UNIDADES else None,
        "must_change_password": user.must_change_password,
        "units": [
            {"codigo": u.codigo, "nome": u.nome, "prefixo": u.prefixo_api}
            for u in UNIDADES.values()
            if user.is_dev or u.codigo == user.unit
        ],
    }


def _definir_cookie(resp, token: str):
    resp.set_cookie(
        settings.cookie_name, token,
        max_age=settings.sessao_max_horas * 3600,
        httponly=True, secure=settings.cookie_secure, samesite="Lax", path="/",
    )
    return resp


@bp.route("/health")
def health():
    return jsonify({"status": "ok"})


@bp.route("/auth/login", methods=["POST"])
def login():
    corpo = request.get_json(silent=True) or {}
    try:
        user, token, csrf = servico.autenticar(
            str(corpo.get("username", ""))[:128], str(corpo.get("password", ""))[:256],
            ip=ip_cliente(), user_agent=request.headers.get("User-Agent"),
        )
    except servico.AuthError as e:
        return jsonify({"erro": e.mensagem, "codigo": e.codigo}), e.status
    resp = make_response(jsonify({"user": serializar_usuario(user), "csrf_token": csrf}))
    return _definir_cookie(resp, token)


@bp.route("/auth/logout", methods=["POST"])
def logout():
    servico.encerrar_sessao(g.auth_session.id, "logout")
    audit.registrar("logout", user=g.user, session_id=g.auth_session.id, module="auth", action="logout",
                    ip=ip_cliente(), user_agent=request.headers.get("User-Agent"))
    resp = make_response(jsonify({"ok": True}))
    resp.delete_cookie(settings.cookie_name, path="/")
    return resp


@bp.route("/auth/me")
def me():
    return jsonify({"user": serializar_usuario(g.user), "csrf_token": g.auth_session.csrf_token})


@bp.route("/auth/ping", methods=["POST"])
def ping():
    """Heartbeat do frontend: confirma que a aba está em uso (usuário interagiu
    recentemente). Atualiza `last_activity_at`; não gera evento de auditoria."""
    servico.registrar_atividade(g.auth_session.id)
    return jsonify({"ok": True})


@bp.route("/auth/activity", methods=["POST"])
def activity():
    """Registra navegação entre módulos/abas (que não geram chamada de API própria)."""
    corpo = request.get_json(silent=True) or {}
    modulo = str(corpo.get("module", ""))[:32]
    if modulo not in _MODULOS_VALIDOS:
        return jsonify({"erro": "módulo inválido"}), 400
    unidade = str(corpo.get("unit", ""))[:16]
    servico.registrar_atividade(g.auth_session.id)
    audit.registrar("module_view", user=g.user, session_id=g.auth_session.id, module=modulo, action="read",
                    unit=unidade if unidade in UNIDADES and (g.user.is_dev or unidade == g.user.unit) else None,
                    method="POST", path="/api/auth/activity", ip=ip_cliente(),
                    user_agent=request.headers.get("User-Agent"))
    return jsonify({"ok": True})


@bp.route("/auth/password", methods=["POST"])
def trocar_senha():
    corpo = request.get_json(silent=True) or {}
    atual, nova = str(corpo.get("current_password", "")), str(corpo.get("new_password", ""))
    from werkzeug.security import check_password_hash
    usuario = servico.obter_usuario(g.user.id)
    if not usuario or not check_password_hash(usuario.password_hash, atual):
        audit.registrar("password_change_failed", user=g.user, session_id=g.auth_session.id, module="auth",
                        action="update", result="failure", ip=ip_cliente())
        return jsonify({"erro": "Senha atual incorreta.", "codigo": "senha_atual_incorreta"}), 400
    try:
        servico.alterar_senha(g.user.id, nova)
    except servico.ValidacaoError as e:
        return jsonify({"erro": e.mensagem, "campo": e.campo}), 400
    audit.registrar("password_changed", user=g.user, module="auth", action="update", ip=ip_cliente())
    # alterar_senha derruba todas as sessões, inclusive esta: o cliente precisa logar de novo
    resp = make_response(jsonify({"ok": True, "relogin": True}))
    resp.delete_cookie(settings.cookie_name, path="/")
    return resp

"""
Integração Flask da autenticação/autorização: guarda global *deny-by-default*, CSRF,
isolamento por unidade e auditoria de requisições.

A guarda roda em `before_request` para TODA rota `/api/*`: uma rota nova é protegida
automaticamente (precisa autenticação) sem que alguém lembre de decorá-la. O escopo de
unidade é decidido pelo prefixo da URL (`/api/grandmassif` ↔ HETRIN, `/api/brasilandia`
↔ HMB) comparado com a unidade gravada no cadastro do usuário — nada vindo do cliente
(query string, corpo, header) escolhe a unidade.
"""
import re
from urllib.parse import unquote

from flask import g, jsonify, request

from core import audit
from core.auth import servico
from core.settings import settings
from core.unidades import unidade_por_prefixo

_PUBLICAS = {("POST", "/api/auth/login"), ("GET", "/api/health")}
_METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}
# POSTs automáticos do frontend (batimento/navegação): se a sessão caiu neles, nenhum dado do usuário se perdeu
_NAO_E_OPERACAO = {"/api/auth/ping", "/api/auth/activity"}

# Endpoints que não geram evento de auditoria (ruído / já auditados pela própria rota).
_SEM_AUDITORIA = {
    "/api/auth/login", "/api/auth/logout", "/api/auth/me", "/api/auth/ping", "/api/auth/activity", "/api/auth/session",
    "/api/health",
}
# Leituras do painel administrativo não são auditadas (o Dev consultando logs não deve
# poluir o próprio histórico de uso); mutações e exportações administrativas são.
_RE_ADMIN_LEITURA = re.compile(r"^/api/admin/(audit(/summary)?|sessions|usage|users|assignments)?/?$")


def ip_cliente() -> str | None:
    """IP do cliente. Atrás do proxy do Railway, ProxyFix (app_factory) já substitui `remote_addr`
    pelo valor que o PROXY CONFIÁVEL anexou a X-Forwarded-For — nunca lemos o cabeçalho cru
    (o primeiro item é controlado pelo cliente e permitiria forjar o IP)."""
    return request.remote_addr


def _json_erro(codigo: str, mensagem: str, status: int, **extra):
    return jsonify({"erro": mensagem, "codigo": codigo, **extra}), status


_MENSAGEM_401 = {
    "inatividade": "Você foi desconectado por inatividade. Entre novamente para continuar.",
    "tempo_maximo": "Sua sessão atingiu o tempo máximo. Entre novamente.",
    "conta_desativada": "Sua conta foi desativada.",
    "encerrada_pelo_admin": "Sua sessão foi encerrada pelo administrador. Entre novamente.",
    "senha_alterada": "Sua senha foi alterada. Entre novamente.",
    "logout": "Você saiu do sistema. Entre novamente.",
}


def _deve_tocar(caminho: str) -> bool:
    """O que CONTA como atividade do usuário: qualquer requisição autenticada disparada por ele —
    EXCETO a consulta periódica de sessão (`GET /api/auth/session`) e o batimento (`POST
    /api/auth/ping`) quando não informa interação real. Assim nenhuma chamada automática em segundo
    plano mantém a sessão viva sem alguém usando a aplicação."""
    if caminho == "/api/auth/session":
        return False
    if caminho == "/api/auth/ping":
        corpo = request.get_json(silent=True) or {}
        return bool(corpo.get("interagiu"))
    return True


def classificar(metodo: str, caminho: str) -> tuple[str, str, str | None]:
    """(módulo, ação, recurso) de uma requisição, para a trilha de auditoria."""
    partes = [unquote(p) for p in caminho.split("/") if p]  # ['api', 'brasilandia', 'colaborador', 'Fulano', 'status']
    if len(partes) >= 2 and partes[1] == "admin":
        modulo = "admin"
        recurso = "/".join(partes[2:]) or None
        acao = {"GET": "read", "POST": "create", "PUT": "update", "PATCH": "update", "DELETE": "delete"}.get(metodo, "read")
        if "export" in caminho:
            acao = "export"
        return modulo, acao, recurso
    if len(partes) >= 3 and unidade_por_prefixo(caminho):
        seg = partes[2]
        resto = partes[3:]
        mapa_modulo = {
            "preventivas": "preventivas", "exportar_preventivas": "exportacao",
            "planos": "planos", "exportar_planos": "exportacao",
            "colaboradores": "colaboradores", "colaborador": "colaboradores", "habilidades": "colaboradores",
            "exportar": "exportacao", "limpar_cache": "sistema",
            "atribuicoes": "distribuicao", "regras": "regras", "revisao": "distribuicao",
            "os": "distribuicao", "recomendacoes": "distribuicao", "tasks_por_funcionario": "distribuicao",
        }
        modulo = mapa_modulo.get(seg, seg)
        if seg.startswith("exportar"):
            acao = "export"
        else:
            acao = {"GET": "read", "POST": "create", "PUT": "update", "PATCH": "update", "DELETE": "delete"}.get(metodo, "read")
        recurso = None
        if seg == "colaborador" and resto:
            recurso = resto[0]
        elif seg in ("atribuicoes", "regras") and resto:
            recurso = "/".join(resto)
        return modulo, acao, recurso
    if len(partes) >= 2 and partes[1] == "auth":
        return "auth", {"GET": "read"}.get(metodo, "update"), "/".join(partes[2:]) or None
    acao_padrao = {"GET": "read", "POST": "create", "PUT": "update", "PATCH": "update", "DELETE": "delete"}.get(metodo, "read")
    return (partes[1] if len(partes) > 1 else "api"), acao_padrao, None


def instalar(app) -> None:
    """Registra a guarda, os headers de segurança e a auditoria de requisições."""

    @app.before_request
    def _guarda():
        caminho = request.path
        g.audit_details = None
        if not caminho.startswith("/api/"):
            return None
        if request.method == "OPTIONS":
            return "", 204
        if (request.method, caminho) in _PUBLICAS:
            return None

        token = request.cookies.get(settings.cookie_name)
        user, sess_ou_motivo = servico.validar_sessao(token, tocar=_deve_tocar(caminho))
        if user is None:
            g.nao_autenticado = True
            motivo = sess_ou_motivo
            return _json_erro("nao_autenticado", _MENSAGEM_401.get(motivo, "Autenticação necessária."), 401,
                              motivo=motivo, mutacao=request.method not in _METODOS_SEGUROS and caminho not in _NAO_E_OPERACAO)
        g.user, g.auth_session = user, sess_ou_motivo

        if request.method not in _METODOS_SEGUROS:
            enviado = request.headers.get("X-CSRF-Token", "")
            if not enviado or enviado != g.auth_session.csrf_token:
                g.negado_motivo = "csrf_invalido"
                return _json_erro("csrf_invalido", "Requisição rejeitada (token CSRF ausente ou inválido).", 403)

        if caminho.startswith("/api/admin") and not user.is_dev:
            g.negado_motivo = "area_administrativa"
            return _json_erro("proibido", "Acesso restrito ao administrador.", 403)

        unidade = unidade_por_prefixo(caminho)
        if unidade and not user.is_dev and user.unit != unidade.codigo:
            g.negado_motivo = f"unidade_diferente:{unidade.codigo}"
            return _json_erro("proibido", "Você não tem acesso a esta unidade.", 403)

        g.unidade_rota = unidade
        return None

    @app.after_request
    def _auditar_e_proteger(resp):
        # Headers de segurança em todas as respostas
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if settings.producao:
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        else:
            resp.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")

        # CORS: só origens explicitamente configuradas (padrão: mesma origem, sem CORS)
        origem = request.headers.get("Origin")
        if origem and origem in settings.cors_origins:
            resp.headers["Access-Control-Allow-Origin"] = origem
            resp.headers["Vary"] = "Origin"
            resp.headers["Access-Control-Allow-Credentials"] = "true"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, PUT, DELETE, OPTIONS"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-CSRF-Token"

        try:
            _auditar_requisicao(resp)
        except Exception:  # pragma: no cover - auditoria nunca derruba a resposta
            pass
        return resp


def _auditar_requisicao(resp) -> None:
    caminho, metodo = request.path, request.method
    if not caminho.startswith("/api/") or metodo == "OPTIONS" or caminho in _SEM_AUDITORIA:
        return
    status = resp.status_code
    if g.get("nao_autenticado") and metodo == "GET":
        return  # sondagem anônima de GET: nada foi exposto e evitaria inflar a tabela
    user = g.get("user")
    modulo, acao, recurso = classificar(metodo, caminho)

    negado = status in (401, 403)
    falha = status >= 400
    # Leituras bem-sucedidas do painel admin não entram na trilha
    if modulo == "admin" and acao == "read" and not falha and _RE_ADMIN_LEITURA.match(caminho):
        return
    # Leituras de exportação/planos etc. entram; HEAD não
    if metodo == "HEAD":
        return

    resultado = "denied" if negado else ("failure" if falha else "success")
    detalhes = dict(g.get("audit_details") or {})
    if g.get("negado_motivo"):
        detalhes["motivo"] = g.negado_motivo
    if g.get("nao_autenticado"):
        detalhes["motivo"] = "nao_autenticado"
    if falha and request.args:
        detalhes.setdefault("query", {k: v for k, v in request.args.items()})
    elif acao in ("read", "export") and request.args:
        detalhes.setdefault("query", {k: v for k, v in request.args.items()})

    unidade_acessada = unidade_por_prefixo(caminho)   # unidade ALVO da requisição (o Dev não tem unidade própria)
    if user is not None and unidade_acessada and user.unit != unidade_acessada.codigo:
        detalhes.setdefault("unidade_do_usuario", user.unit)   # p/ investigar tentativas entre unidades
    audit.registrar(
        f"{modulo}.{acao}" if resultado == "success" else f"{modulo}.{acao}_{resultado}",
        user=user, unit=unidade_acessada.codigo if unidade_acessada else None, session_id=getattr(g.get("auth_session"), "id", None),
        module=modulo, action=acao, resource=recurso, result=resultado, status_code=status,
        method=metodo, path=caminho, ip=ip_cliente(), user_agent=request.headers.get("User-Agent"),
        details=detalhes or None,
    )

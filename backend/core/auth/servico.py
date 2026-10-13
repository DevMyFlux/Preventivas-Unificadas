"""
Serviço de autenticação e sessões (sem dependência de Flask — testável isoladamente).

Decisões de segurança:
  * Senhas: hash scrypt com salt individual (werkzeug). Nunca texto puro, nunca em log.
  * Sessão: token aleatório de 256 bits no cookie HttpOnly; no banco fica só o SHA-256
    do token (um vazamento do banco não permite sequestrar sessões).
  * Login: resposta genérica para usuário inexistente / senha errada / conta desativada
    (não revela quais usuários existem) e custo de verificação equalizado com um hash
    fictício. Bloqueio temporário por falhas repetidas + limite por IP.
  * Sessão expira por inatividade e por tempo máximo absoluto; desativar o usuário
    derruba imediatamente as sessões abertas.
"""
import hashlib
import re
import secrets
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from core import audit
from core.db import agora_utc, sessao
from core.models import ROLE_DEV, ROLE_USER, AuditLog, AuthSession, User
from core.settings import settings
from core.unidades import codigo_valido

_RE_USERNAME = re.compile(r"^(?:[a-z0-9][a-z0-9._-]{2,63}|[a-z0-9._+-]{1,40}@[a-z0-9-]+(?:\.[a-z0-9-]+)+)$")   # login simples ou e-mail
_TOUCH_MIN_SEGUNDOS = 30       # grava last_activity no máx. a cada 30 s por sessão
_LIMITE_FALHAS_POR_IP = 20     # tentativas falhas por IP na janela abaixo
_JANELA_IP_MINUTOS = 15

# Hash fictício para igualar o tempo de resposta quando o usuário não existe.
_HASH_FICTICIO = generate_password_hash("senha-ficticia-para-equalizar-tempo")


class AuthError(Exception):
    def __init__(self, codigo: str, mensagem: str, status: int = 401):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.status = status


class ValidacaoError(Exception):
    def __init__(self, mensagem: str, campo: str | None = None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.campo = campo


# ── helpers ───────────────────────────────────────────────────────────────────

def normalizar_username(username: str | None) -> str:
    return (username or "").strip().lower()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def validar_username(username: str) -> str:
    u = normalizar_username(username)
    if len(u) > 64 or not _RE_USERNAME.match(u):
        raise ValidacaoError(
            "Usuário deve ter 3–64 caracteres (letras minúsculas, números, '.', '_', '-' ou e-mail).", "username")
    return u


def validar_senha(senha: str | None, username: str | None = None) -> str:
    senha = senha or ""
    minimo = settings.senha_min_tamanho
    if len(senha) < minimo:
        raise ValidacaoError(f"A senha deve ter pelo menos {minimo} caracteres.", "password")
    if not re.search(r"[A-Za-z]", senha) or not re.search(r"\d", senha):
        raise ValidacaoError("A senha deve conter letras e números.", "password")
    if username and senha.lower() == username.lower():
        raise ValidacaoError("A senha não pode ser igual ao usuário.", "password")
    return senha


def hash_senha(senha: str) -> str:
    return generate_password_hash(senha, method="scrypt")


# ── usuários ──────────────────────────────────────────────────────────────────

def criar_usuario(
    username: str, senha: str, *, display_name: str = "", role: str = ROLE_USER,
    unit: str | None = None, criado_por: str | None = None, must_change_password: bool = False,
) -> User:
    u = validar_username(username)
    validar_senha(senha, u)
    if role not in (ROLE_DEV, ROLE_USER):
        raise ValidacaoError("Perfil inválido.", "role")
    if role == ROLE_USER and not codigo_valido(unit):
        raise ValidacaoError("Usuário comum deve estar vinculado a uma unidade válida.", "unit")
    if role == ROLE_DEV:
        unit = None
    with sessao() as s:
        if s.scalar(select(User).where(User.username == u)):
            raise ValidacaoError("Já existe um usuário com esse nome.", "username")
        user = User(
            username=u, display_name=(display_name or u).strip()[:120],
            password_hash=hash_senha(senha), role=role, unit=unit,
            is_active=True, must_change_password=must_change_password, created_by=criado_por,
        )
        s.add(user)
        s.flush()
        return user


def obter_usuario(user_id: int) -> User | None:
    with sessao() as s:
        return s.get(User, user_id)


def obter_usuario_por_username(username: str) -> User | None:
    with sessao() as s:
        return s.scalar(select(User).where(User.username == normalizar_username(username)))


def existe_dev() -> bool:
    with sessao() as s:
        return s.scalar(select(func.count()).select_from(User).where(User.role == ROLE_DEV)) > 0


def alterar_senha(user_id: int, nova_senha: str, *, forcar_troca: bool = False) -> None:
    with sessao() as s:
        user = s.get(User, user_id)
        if not user:
            raise ValidacaoError("Usuário não encontrado.")
        validar_senha(nova_senha, user.username)
        user.password_hash = hash_senha(nova_senha)
        user.must_change_password = forcar_troca
        user.failed_logins = 0
        user.locked_until = None
    # trocar a senha invalida as sessões abertas
    encerrar_sessoes_do_usuario(user_id, "password_changed")


def bootstrap_admin() -> str:
    """Cria o administrador (Dev) inicial a partir de DEV_ADMIN_USERNAME/DEV_ADMIN_PASSWORD.
    Nada fica no código-fonte. Retorna um texto curto para o log (nunca a senha).

    Com DEV_ADMIN_RESET_PASSWORD=true (recuperação): o Dev existente passa a ter o usuário e a senha
    das variáveis — mesmo que o usuário atual dele seja outro."""
    usuario, senha = settings.dev_admin_username, settings.dev_admin_password
    if not usuario or not senha:
        return ("existente" if existe_dev() else
                "AVISO: nenhum Dev cadastrado e DEV_ADMIN_USERNAME/DEV_ADMIN_PASSWORD não definidos — "
                "ninguém poderá entrar até que o administrador seja configurado.")
    u = validar_username(usuario)
    reset = settings.dev_admin_reset
    dev_id = None
    mensagem = None
    with sessao() as s:
        alvo = s.scalar(select(User).where(User.username == u))
        dev_atual = s.scalar(select(User).where(User.role == ROLE_DEV))
        if alvo is not None and alvo.role != ROLE_DEV:
            return "AVISO: DEV_ADMIN_USERNAME coincide com um usuário comum; nada foi alterado."
        if alvo is None and dev_atual is not None and not reset:
            return ("existente (variáveis DEV_ADMIN_* ignoradas: já há um Dev cadastrado com outro usuário; "
                    "use DEV_ADMIN_RESET_PASSWORD=true para substituí-lo)")
        if alvo is not None and not reset:
            return "existente"
        if alvo is not None or dev_atual is not None:
            dev = alvo or dev_atual
            antigo = dev.username
            validar_senha(senha, u)
            dev.username = u
            dev.password_hash = hash_senha(senha)
            dev.failed_logins, dev.locked_until, dev.is_active = 0, None, True
            dev_id = dev.id
            mensagem = (f"Dev redefinido (DEV_ADMIN_RESET_PASSWORD=true): usuário '{antigo}' -> '{u}'"
                        if antigo != u else "senha do Dev redefinida (DEV_ADMIN_RESET_PASSWORD=true)")
    if dev_id is not None:
        encerrar_sessoes_do_usuario(dev_id, "password_changed")
        return mensagem
    try:
        criar_usuario(u, senha, display_name="Dev", role=ROLE_DEV, criado_por="bootstrap")
    except (IntegrityError, ValidacaoError):
        return "existente (criado por outro worker na mesma subida)"
    return "Dev criado a partir das variáveis de ambiente"


# ── login / sessão ────────────────────────────────────────────────────────────

def _falhas_recentes_do_ip(s, ip: str | None) -> int:
    if not ip:
        return 0
    desde = agora_utc() - timedelta(minutes=_JANELA_IP_MINUTOS)
    return s.scalar(
        select(func.count()).select_from(AuditLog).where(
            AuditLog.event == "login_failed", AuditLog.ip == ip, AuditLog.ts >= desde)
    ) or 0


def autenticar(username: str, senha: str, *, ip: str | None = None, user_agent: str | None = None):
    """Valida credenciais e abre uma sessão. Retorna (user, token, csrf). Levanta AuthError.

    A transação do banco é confirmada ANTES de levantar o erro (para persistir o contador
    de falhas/bloqueio) e os eventos de auditoria são gravados DEPOIS do commit — gravar
    em outra conexão com uma transação aberta travaria o SQLite."""
    u = normalizar_username(username)
    erro_generico = AuthError("credenciais_invalidas", "Usuário ou senha inválidos.", 401)
    erro: AuthError | None = None
    evento: tuple | None = None   # (nome, kwargs) a registrar depois do commit
    user = token = csrf = None
    sess_id = None

    with sessao() as s:
        agora = agora_utc()
        if _falhas_recentes_do_ip(s, ip) >= _LIMITE_FALHAS_POR_IP:
            erro = AuthError("muitas_tentativas", "Muitas tentativas. Aguarde alguns minutos.", 429)
            evento = ("login_blocked", {"username": u, "result": "denied", "details": {"motivo": "limite_por_ip"}})
        else:
            user = s.scalar(select(User).where(User.username == u)) if u else None
            if user is None or not senha:
                check_password_hash(_HASH_FICTICIO, senha or "")
                erro = erro_generico
                evento = ("login_failed", {"username": u or None, "result": "failure",
                                           "details": {"motivo": "usuario_inexistente"}})
                user = None
            elif user.locked_until and user.locked_until > agora:
                erro = AuthError(
                    "conta_bloqueada",
                    "Conta bloqueada temporariamente por tentativas inválidas. Tente novamente mais tarde.", 423)
                evento = ("login_blocked", {"user": user, "result": "denied",
                                            "details": {"motivo": "conta_bloqueada_temporariamente"}})
            else:
                senha_ok = check_password_hash(user.password_hash, senha)
                motivo = None
                if not senha_ok:
                    user.failed_logins = (user.failed_logins or 0) + 1
                    if user.failed_logins >= settings.login_max_falhas:
                        user.locked_until = agora + timedelta(minutes=settings.login_bloqueio_minutos)
                        user.failed_logins = 0
                    motivo = "senha_incorreta"
                elif not user.is_active:
                    motivo = "usuario_desativado"
                if motivo:
                    # resposta idêntica nos casos: não revela se a conta existe/está ativa
                    erro = erro_generico
                    evento = ("login_failed", {"user": user, "result": "failure", "details": {"motivo": motivo}})
                else:
                    user.failed_logins = 0
                    user.locked_until = None
                    user.last_login_at = agora
                    token = secrets.token_urlsafe(32)
                    csrf = secrets.token_urlsafe(24)
                    sess = AuthSession(
                        token_hash=hash_token(token), csrf_token=csrf, user_id=user.id,
                        created_at=agora, last_activity_at=agora,
                        expires_at=agora + timedelta(hours=settings.sessao_max_horas),
                        ip=ip, user_agent=(user_agent or "")[:255] or None,
                    )
                    s.add(sess)
                    evento = ("login_success", {"user": user})
        s.flush()
        if sess_id is None and token is not None:
            sess_id = sess.id
        if user is not None:
            s.expunge(user)

    nome_evento, kwargs = evento
    audit.registrar(nome_evento, session_id=sess_id, module="auth", action="login",
                    ip=ip, user_agent=user_agent, **{k: v for k, v in kwargs.items()})
    if erro:
        raise erro
    return user, token, csrf


def _encerrar(s, sess: AuthSession, motivo: str, quando=None) -> None:
    if sess.ended_at is None:
        sess.ended_at = quando or agora_utc()
        sess.end_reason = motivo


def validar_sessao(token: str | None):
    """Retorna (user, sessao) se o token corresponde a uma sessão válida; senão (None, motivo).
    Também faz a limpeza preguiçosa de sessões vencidas e atualiza `last_activity_at`
    (no máx. 1 gravação a cada 30 s)."""
    if not token:
        return None, "sem_cookie"
    agora = agora_utc()
    with sessao() as s:
        sess = s.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(token)))
        if sess is None:
            return None, "token_desconhecido"
        if sess.ended_at is not None:
            return None, "sessao_encerrada"
        user = s.get(User, sess.user_id)
        if sess.expires_at <= agora:
            _encerrar(s, sess, "max_lifetime", sess.expires_at)
            return None, "sessao_expirada"
        if agora - sess.last_activity_at > timedelta(minutes=settings.sessao_ociosa_minutos):
            # encerrada na última atividade real conhecida — ausência de eventos depois
            # disso é inatividade, não "uso desconhecido"
            _encerrar(s, sess, "idle_timeout", sess.last_activity_at)
            return None, "sessao_ociosa"
        if user is None or not user.is_active:
            _encerrar(s, sess, "user_deactivated", agora)
            return None, "usuario_desativado"
        if (agora - sess.last_activity_at).total_seconds() >= _TOUCH_MIN_SEGUNDOS:
            sess.last_activity_at = agora
        s.flush()
        s.expunge(user)
        s.expunge(sess)
        return user, sess


def registrar_atividade(sessao_id: int) -> None:
    """Marca atividade explícita (heartbeat do frontend), respeitando o limite de gravação."""
    agora = agora_utc()
    with sessao() as s:
        sess = s.get(AuthSession, sessao_id)
        if sess and sess.ended_at is None and (agora - sess.last_activity_at).total_seconds() >= 5:
            sess.last_activity_at = agora


def encerrar_sessao(sessao_id: int, motivo: str = "logout") -> None:
    with sessao() as s:
        sess = s.get(AuthSession, sessao_id)
        if sess:
            _encerrar(s, sess, motivo)


def encerrar_sessoes_do_usuario(user_id: int, motivo: str) -> int:
    agora = agora_utc()
    with sessao() as s:
        res = s.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.ended_at.is_(None))
            .values(ended_at=agora, end_reason=motivo)
        )
        return res.rowcount or 0


def finalizar_sessoes_vencidas() -> int:
    """Fecha sessões abertas que já passaram do limite de inatividade ou de vida — cobre
    desconexões inesperadas (aba fechada, rede caiu, sem logout). O fim registrado é a
    última atividade conhecida (ociosidade) ou o limite absoluto."""
    agora = agora_utc()
    limite_ocioso = agora - timedelta(minutes=settings.sessao_ociosa_minutos)
    n = 0
    with sessao() as s:
        abertas = s.scalars(select(AuthSession).where(AuthSession.ended_at.is_(None))).all()
        for sess in abertas:
            if sess.expires_at <= agora:
                _encerrar(s, sess, "max_lifetime", sess.expires_at)
                n += 1
            elif sess.last_activity_at < limite_ocioso:
                _encerrar(s, sess, "idle_timeout", sess.last_activity_at)
                n += 1
    return n

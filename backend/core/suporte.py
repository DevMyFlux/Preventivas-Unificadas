"""
Sugestões e Suporte: qualquer usuário autenticado envia sugestão/problema/melhoria; a mensagem
segue por e-mail (SMTP) para o time de suporte.

Garantias:
  * Credenciais SMTP só existem no ambiente do servidor (`SMTP_USER`/`SMTP_PASSWORD`); nunca em
    resposta de API, auditoria, log ou frontend. Sem elas o endpoint responde 503
    `suporte_nao_configurado` — NENHUM envio é simulado.
  * Entrada validada e higienizada (sem caracteres de controle; e-mail sem CR/LF — anti header
    injection); corpo limitado; limite por usuário/hora; duplicata idêntica bloqueada.
  * A mensagem é gravada antes do envio (status `enviando`): clique duplo/concorrência não gera dois
    e-mails e uma falha de SMTP não perde o texto do usuário.
  * O texto da mensagem NÃO vai para a trilha de auditoria (só tipo, tamanho e resultado).
"""
import hashlib
import logging
import re
import smtplib
import ssl
from datetime import timedelta
from email.message import EmailMessage

from flask import Blueprint, g, jsonify, request
from sqlalchemy import func, select

from core.auth.http import ip_cliente
from core.db import agora_utc, sessao
from core.models import SuporteSolicitacao
from core.settings import settings

log = logging.getLogger("myflux.suporte")

bp = Blueprint("suporte", __name__, url_prefix="/api/suporte")

TIPOS = {"sugestao": "Sugestão", "problema": "Problema", "melhoria": "Melhoria"}
NOME_MIN, NOME_MAX = 2, 120
MSG_MIN, MSG_MAX = 10, 5000
CORPO_MAX_BYTES = 32 * 1024
JANELA_DUPLICATA = timedelta(minutes=10)

_RE_EMAIL = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$")
_RE_CONTROLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")   # preserva \t e \n; remove o resto


class ErroValidacao(ValueError):
    def __init__(self, campo: str, mensagem: str):
        super().__init__(mensagem)
        self.campo, self.mensagem = campo, mensagem


def _linha(valor) -> str:
    """Texto de uma linha só: sem controles/quebras, espaços normalizados."""
    return " ".join(_RE_CONTROLE.sub("", str(valor or "")).replace("\r", " ").replace("\n", " ").split())


def validar(corpo: dict) -> dict:
    nome = _linha(corpo.get("nome"))
    if not (NOME_MIN <= len(nome) <= NOME_MAX):
        raise ErroValidacao("nome", f"Informe o nome ({NOME_MIN} a {NOME_MAX} caracteres).")
    email = str(corpo.get("email") or "").strip()
    if len(email) > 254 or not _RE_EMAIL.match(email):
        raise ErroValidacao("email", "Informe um e-mail de retorno válido.")
    tipo = str(corpo.get("tipo") or "").strip().lower()
    if tipo not in TIPOS:
        raise ErroValidacao("tipo", "Escolha o tipo: sugestão, problema ou melhoria.")
    mensagem = _RE_CONTROLE.sub("", str(corpo.get("mensagem") or "")).replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(mensagem) < MSG_MIN:
        raise ErroValidacao("mensagem", f"Descreva com pelo menos {MSG_MIN} caracteres.")
    if len(mensagem) > MSG_MAX:
        raise ErroValidacao("mensagem", f"A mensagem pode ter no máximo {MSG_MAX} caracteres.")
    return {"nome": nome, "email": email, "tipo": tipo, "mensagem": mensagem}


def _hash(user_id: int, dados: dict) -> str:
    base = "\x1f".join((str(user_id), dados["tipo"], " ".join(dados["mensagem"].lower().split())))
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def montar_email(dados: dict, user, unidade: str | None, quando) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = _linha(f"[MyFlux Preventivas] {TIPOS[dados['tipo']]} — {dados['nome']}")[:200]
    msg["From"] = settings.smtp_remetente
    msg["To"] = settings.suporte_destino
    msg["Reply-To"] = dados["email"]     # já validado (sem CR/LF)
    msg.set_content(
        f"Tipo: {TIPOS[dados['tipo']]}\n"
        f"Nome: {dados['nome']}\n"
        f"E-mail de retorno: {dados['email']}\n"
        f"Usuário: {user.username}\n"
        f"Unidade: {unidade or 'todas (Dev)'}\n"
        f"Data (UTC): {quando.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"{'-' * 40}\n{dados['mensagem']}\n")
    return msg


def enviar_smtp(msg: EmailMessage) -> None:
    """Único ponto que fala com o servidor SMTP (os testes o substituem — nunca há envio real em teste)."""
    host, porta = settings.smtp_host, settings.smtp_port
    contexto = ssl.create_default_context()
    if porta == 465:
        with smtplib.SMTP_SSL(host, porta, timeout=15, context=contexto) as srv:
            srv.login(settings.smtp_user, settings.smtp_password)
            srv.send_message(msg)
        return
    with smtplib.SMTP(host, porta, timeout=15) as srv:
        srv.starttls(context=contexto)
        srv.login(settings.smtp_user, settings.smtp_password)
        srv.send_message(msg)


def _erro(codigo: str, mensagem: str, status: int, **extra):
    return jsonify({"erro": mensagem, "codigo": codigo, **extra}), status


@bp.route("/status", methods=["GET"])
def status():
    """Só diz SE está pronto e COMO a mensagem é entregue (nunca expõe host, usuário ou senha)."""
    return jsonify({"configurado": settings.suporte_configurado, "entrega": settings.suporte_entrega, "tipos": TIPOS,
                    "limites": {"mensagem_max": MSG_MAX, "mensagem_min": MSG_MIN, "nome_max": NOME_MAX}})


@bp.route("", methods=["POST"])
def enviar():
    user = g.user
    if (request.content_length or 0) > CORPO_MAX_BYTES:
        return _erro("corpo_grande", "Mensagem grande demais.", 413)
    corpo = request.get_json(silent=True)
    if not isinstance(corpo, dict):
        return _erro("corpo_invalido", "Requisição inválida.", 400)
    try:
        dados = validar(corpo)
    except ErroValidacao as e:
        return _erro("validacao", e.mensagem, 400, campo=e.campo)
    g.audit_details = {"tipo": dados["tipo"], "tamanho": len(dados["mensagem"])}

    caixa = settings.suporte_entrega == "caixa"
    if not caixa and not settings.suporte_configurado:
        # Não simula: informa que o envio de e-mail não está configurado neste ambiente. Nada é gravado
        # como "enviado"; o texto fica com o usuário na tela.
        log.warning("Suporte: SMTP não configurado (defina SMTP_USER/SMTP_PASSWORD no ambiente)")
        return _erro("suporte_nao_configurado",
                     "O envio de e-mail do suporte ainda não está configurado neste ambiente. "
                     "Sua mensagem NÃO foi enviada.", 503)

    agora = agora_utc()
    h = _hash(user.id, dados)
    with sessao() as s:
        recentes = s.scalar(select(func.count()).select_from(SuporteSolicitacao).where(
            SuporteSolicitacao.user_id == user.id, SuporteSolicitacao.ts >= agora - timedelta(hours=1),
            SuporteSolicitacao.status.in_(("enviando", "recebida", "enviada", "falha")))) or 0
        if recentes >= settings.suporte_limite_por_hora:
            return _erro("limite_excedido", "Muitas mensagens em pouco tempo. Tente novamente mais tarde.", 429)
        duplicada = s.scalar(select(func.count()).select_from(SuporteSolicitacao).where(
            SuporteSolicitacao.user_id == user.id, SuporteSolicitacao.msg_hash == h,
            SuporteSolicitacao.ts >= agora - JANELA_DUPLICATA, SuporteSolicitacao.status.in_(("enviando", "recebida", "enviada"))))
        if duplicada:
            return _erro("duplicada", "Esta mensagem já foi enviada. Aguarde o retorno do suporte.", 409)
        reg = SuporteSolicitacao(user_id=user.id, username=user.username, unit=user.unit, nome=dados["nome"],
                                 email=dados["email"], tipo=dados["tipo"], mensagem=dados["mensagem"], msg_hash=h,
                                 status="enviando", ip=ip_cliente(), ts=agora)
        s.add(reg)
        s.flush()
        reg_id = reg.id

    if caixa:
        # Caixa interna: a mensagem já está gravada e fica visível só para o Dev. Nenhum e-mail é enviado.
        with sessao() as s:
            s.get(SuporteSolicitacao, reg_id).status = "recebida"
        g.audit_details = {**g.audit_details, "entrega": "caixa", "id": reg_id}
        return jsonify({"ok": True, "id": reg_id, "entrega": "caixa",
                        "mensagem": "Mensagem registrada. A administração vai ler na própria plataforma."}), 201

    try:
        enviar_smtp(montar_email(dados, user, user.unit, agora))
    except Exception as exc:   # SMTP indisponível, autenticação recusada, timeout...
        categoria = type(exc).__name__[:60]       # nunca a mensagem (pode ecoar o usuário/host)
        log.error("Suporte: falha no envio SMTP (%s)", categoria)
        with sessao() as s:
            r = s.get(SuporteSolicitacao, reg_id)
            r.status, r.erro = "falha", categoria
        g.audit_details = {**g.audit_details, "enviado": False, "erro": categoria}
        return _erro("suporte_falha_envio",
                     "Não foi possível enviar sua mensagem agora. Tente novamente em alguns minutos.", 502)

    with sessao() as s:
        s.get(SuporteSolicitacao, reg_id).status = "enviada"
    g.audit_details = {**g.audit_details, "enviado": True, "id": reg_id}
    return jsonify({"ok": True, "id": reg_id, "entrega": "email", "mensagem": "Mensagem enviada ao suporte. Responderemos no e-mail informado."}), 201

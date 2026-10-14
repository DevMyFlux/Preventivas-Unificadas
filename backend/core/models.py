"""
Modelos do banco (SQLAlchemy 2.0, declarativo).

Convenções:
  * Datas/horas em UTC *naive* (ver core.db.agora_utc).
  * Nada é apagado fisicamente: usuários são desativados (`is_active=False`), sessões
    são encerradas (`ended_at`) e o `audit_log` é append-only — assim a desativação de
    uma conta nunca apaga o histórico de atividades do usuário.
  * `audit_log.username`/`unit` guardam um *snapshot* do momento do evento, para que
    o histórico continue legível mesmo se o usuário for renomeado ou mudar de unidade.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from core.db import agora_utc


class Base(DeclarativeBase):
    pass


ROLE_DEV = "dev"
ROLE_USER = "user"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default=ROLE_USER)
    # NULL só para o perfil Dev (acesso a todas as unidades); usuário comum sempre tem unidade.
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failed_logins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=agora_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=agora_utc, onupdate=agora_utc)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    sessions: Mapped[list["AuthSession"]] = relationship(back_populates="user")

    @property
    def is_dev(self) -> bool:
        return self.role == ROLE_DEV


class AuthSession(Base):
    """Uma sessão = um login. Guarda início, última atividade e como terminou, que é o
    insumo dos relatórios de atividade/inatividade."""
    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # sha256 do token do cookie
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=agora_utc)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=agora_utc)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)  # limite absoluto
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # logout | idle_timeout | max_lifetime | revoked | user_deactivated | password_changed
    end_reason: Mapped[str | None] = mapped_column(String(24), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Tempo EFETIVAMENTE ativo (soma dos intervalos entre atividades, cada um limitado a
    # ACTIVITY_WINDOW_MINUTES) e quantas atividades válidas foram registradas. Sessão aberta != uso.
    active_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    activity_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    user: Mapped[User] = relationship(back_populates="sessions")

    __table_args__ = (
        Index("ix_auth_sessions_user_created", "user_id", "created_at"),
        Index("ix_auth_sessions_open", "ended_at", "last_activity_at"),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=agora_utc)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    session_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event: Mapped[str] = mapped_column(String(48), nullable=False)       # ex.: login_success, request, assignment_apply
    module: Mapped[str | None] = mapped_column(String(32), nullable=True)  # auth | preventivas | planos | colaboradores | admin ...
    action: Mapped[str | None] = mapped_column(String(16), nullable=True)  # read | create | update | delete | export | login | logout
    resource: Mapped[str | None] = mapped_column(String(160), nullable=True)
    result: Mapped[str] = mapped_column(String(10), nullable=False, default="success")  # success | failure | denied
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    method: Mapped[str | None] = mapped_column(String(8), nullable=True)
    path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON sanitizado (nunca segredos)

    __table_args__ = (
        Index("ix_audit_ts", "ts"),
        Index("ix_audit_user_ts", "user_id", "ts"),
        Index("ix_audit_unit_ts", "unit", "ts"),
        Index("ix_audit_event_ts", "event", "ts"),
    )


class RegraResolucao(Base):
    """Confirmação humana de um nome citado numa regra de atribuição (ex.: "Michael") —
    usada quando o apelido bate com mais de um colaborador ou com nenhum. Nada é
    escolhido automaticamente em caso de ambiguidade."""
    __tablename__ = "regra_resolucoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    alias: Mapped[str] = mapped_column(String(120), nullable=False)       # normalizado (minúsculo, sem acento)
    funcionario: Mapped[str] = mapped_column(String(160), nullable=False)  # nome completo no cadastro
    resolved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolved_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=agora_utc)

    __table_args__ = (UniqueConstraint("unit", "alias", name="uq_regra_resolucao_unit_alias"),)


class AtribuicaoProposta(Base):
    """Proposta de preenchimento de executante de uma OS no Neovero (fila de conferência).
    `chave_idempotencia` impede propostas/aplicações duplicadas para o mesmo (OS, executante)."""
    __tablename__ = "atribuicao_propostas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    chave_idempotencia: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    os_id: Mapped[int] = mapped_column(Integer, nullable=False)
    os_numero: Mapped[str] = mapped_column(String(32), nullable=False)
    data_prevista: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    plano: Mapped[str | None] = mapped_column(String(255), nullable=True)
    responsavel_original_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    responsavel_original: Mapped[str | None] = mapped_column(String(160), nullable=True)
    funcionario_proposto: Mapped[str] = mapped_column(String(160), nullable=False)
    neovero_funcionario_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # proposta | aprovada | rejeitada | simulada | aplicada | conflito | falha
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="proposta")
    mensagem: Mapped[str | None] = mapped_column(Text, nullable=True)
    criado_por: Mapped[str | None] = mapped_column(String(64), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=agora_utc)
    aprovado_por: Mapped[str | None] = mapped_column(String(64), nullable=True)
    aprovado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    processado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (Index("ix_atribuicao_unit_status", "unit", "status"),)


class ColaboradorOverlay(Base):
    """Atributos de colaborador editados pela aplicação (status do mês, datas de admissão/
    desligamento, bloqueio, habilidades). Uma linha por (unidade, colaborador); `dados` é JSON."""
    __tablename__ = "colaborador_overlay"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    chave: Mapped[str] = mapped_column(String(160), nullable=False)   # nome em maiúsculas (ou __seed__)
    dados: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=agora_utc)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (UniqueConstraint("unit", "chave", name="uq_overlay_unit_chave"),)


class SuporteSolicitacao(Base):
    """Sugestão/problema/melhoria enviada por um usuário autenticado. O registro existe ANTES do envio
    do e-mail (status `enviando`) para que um clique duplo não gere dois e-mails e para que a mensagem
    não se perca se o envio falhar. `status`: enviando | enviada | falha | nao_configurado."""
    __tablename__ = "suporte_solicitacoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=agora_utc)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    tipo: Mapped[str] = mapped_column(String(16), nullable=False)
    mensagem: Mapped[str] = mapped_column(Text, nullable=False)
    msg_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="enviando")
    erro: Mapped[str | None] = mapped_column(String(200), nullable=True)     # categoria do erro, nunca credenciais
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (Index("ix_suporte_user_ts", "user_id", "ts"),)


class OsResponsavelHistorico(Base):
    """Observações (append-only) do responsável de cada OS: primeira leitura e transferências. Ver core/os_historico.py."""
    __tablename__ = "os_responsavel_historico"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    os_numero: Mapped[str] = mapped_column(String(32), nullable=False)
    os_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    plano: Mapped[str | None] = mapped_column(String(200), nullable=True)
    responsavel: Mapped[str | None] = mapped_column(String(160), nullable=True)   # nome no Neovero (None = sem responsável)
    anterior: Mapped[str | None] = mapped_column(String(160), nullable=True)
    tipo: Mapped[str] = mapped_column(String(16), nullable=False)                  # inicial | transferencia
    observado_em: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=agora_utc)
    motivo: Mapped[str | None] = mapped_column(String(300), nullable=True)          # anotado por uma pessoa
    motivo_por: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (Index("ix_os_hist_unit_os", "unit", "os_numero", "id"),)


class SchemaMigration(Base):
    __tablename__ = "schema_migrations"

    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=agora_utc)

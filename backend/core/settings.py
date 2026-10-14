"""
Configuração central da aplicação — tudo vem de variáveis de ambiente.

Nenhum segredo (senha, token, chave) vive no código-fonte: os valores abaixo são
lidos do ambiente em tempo de importação. Para desenvolvimento local, um arquivo
`backend/.env` (ignorado pelo git — ver `.gitignore`) é carregado automaticamente se
existir; variáveis já definidas no ambiente têm prioridade sobre o arquivo.
"""
import os
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent.parent


def _carregar_dotenv(caminho: Path) -> None:
    if not caminho.is_file():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, _, valor = linha.partition("=")
        chave = chave.strip()
        valor = valor.strip().strip('"').strip("'")
        if chave and chave not in os.environ:
            os.environ[chave] = valor


# Testes são herméticos: nunca herdam credenciais/variáveis do .env local do desenvolvedor.
if os.environ.get("APP_ENV") != "test":
    _carregar_dotenv(_BASE_DIR / ".env")


def _bool(nome: str, padrao: bool) -> bool:
    bruto = os.environ.get(nome)
    if bruto is None or bruto == "":
        return padrao
    return bruto.strip().lower() in ("1", "true", "yes", "sim", "on")


def _int(nome: str, padrao: int) -> int:
    try:
        return int(os.environ.get(nome, "") or padrao)
    except ValueError:
        return padrao


def _lista(nome: str) -> list[str]:
    return [p.strip() for p in os.environ.get(nome, "").split(",") if p.strip()]


class Settings:
    """Leitura preguiçosa: cada atributo consulta o ambiente na hora, para que testes
    possam alterar `os.environ` sem recarregar o módulo."""

    # ── Ambiente ──────────────────────────────────────────────────────────────
    @property
    def ambiente(self) -> str:
        return os.environ.get("APP_ENV", "development").strip().lower()

    @property
    def producao(self) -> bool:
        return self.ambiente == "production"

    # ── Banco de dados ────────────────────────────────────────────────────────
    @property
    def database_url(self) -> str | None:
        return os.environ.get("DATABASE_URL") or None

    @property
    def cloud_sql_connection_name(self) -> str | None:
        """Ex.: projeto:regiao:instancia — o identificador da instância Cloud SQL NÃO é
        uma credencial; usuário/senha/nome do banco vêm das variáveis DB_*."""
        return os.environ.get("CLOUD_SQL_CONNECTION_NAME") or None

    @property
    def db_user(self) -> str | None:
        return os.environ.get("DB_USER") or None

    @property
    def db_password(self) -> str | None:
        return os.environ.get("DB_PASSWORD") or None

    @property
    def db_name(self) -> str | None:
        return os.environ.get("DB_NAME") or None

    @property
    def cloud_sql_ip_type(self) -> str:
        return os.environ.get("CLOUD_SQL_IP_TYPE", "public").strip().lower()

    @property
    def sqlite_path(self) -> str:
        return os.environ.get("SQLITE_PATH") or str(_BASE_DIR / "data" / "app.db")

    # ── Sessão / autenticação ─────────────────────────────────────────────────
    @property
    def cookie_name(self) -> str:
        # O Firebase Hosting (rewrite para o Cloud Run) descarta todos os cookies exceto "__session".
        return "__session"

    @property
    def cookie_secure(self) -> bool:
        # Secure por padrão em produção; local (http) precisa poder desligar.
        return _bool("COOKIE_SECURE", self.producao)

    @property
    def sessao_ociosa_minutos(self) -> int:
        return _int("SESSION_IDLE_MINUTES", 25)

    @property
    def atividade_janela_minutos(self) -> int:
        """Maior intervalo entre duas atividades que ainda conta como tempo ATIVO (o resto é ocioso)."""
        return _int("ACTIVITY_WINDOW_MINUTES", 5)

    @property
    def sessao_max_horas(self) -> int:
        return _int("SESSION_MAX_HOURS", 12)

    @property
    def login_max_falhas(self) -> int:
        return _int("LOGIN_MAX_FAILURES", 5)

    @property
    def login_bloqueio_minutos(self) -> int:
        return _int("LOGIN_LOCKOUT_MINUTES", 15)

    @property
    def senha_min_tamanho(self) -> int:
        return _int("PASSWORD_MIN_LENGTH", 10)

    @property
    def proxy_hops(self) -> int:
        """Quantos proxies reversos confiáveis ficam na frente (Railway = 1). Só então o IP do
        cliente e o esquema (https) são lidos de X-Forwarded-*; com 0, esses cabeçalhos são ignorados
        (um cliente poderia forjá-los para burlar o limite de tentativas por IP)."""
        return _int("TRUST_PROXY_HOPS", 1 if self.producao else 0)

    @property
    def cors_origins(self) -> list[str]:
        return _lista("CORS_ORIGINS")

    # ── Administrador inicial (Dev) ───────────────────────────────────────────
    @property
    def dev_admin_username(self) -> str | None:
        return os.environ.get("DEV_ADMIN_USERNAME") or None

    @property
    def dev_admin_password(self) -> str | None:
        return os.environ.get("DEV_ADMIN_PASSWORD") or None

    @property
    def dev_admin_reset(self) -> bool:
        return _bool("DEV_ADMIN_RESET_PASSWORD", False)

    # ── Neovero ───────────────────────────────────────────────────────────────
    @property
    def neovero_url_base(self) -> str:
        return os.environ.get("NEOVERO_URL_BASE", "https://grandmassif.api.neovero.com").rstrip("/")

    @property
    def neovero_origin(self) -> str:
        return os.environ.get("NEOVERO_ORIGIN", "https://grandmassif.neovero.com")

    @property
    def neovero_usuario(self) -> str | None:
        return os.environ.get("NEOVERO_USERNAME") or None

    @property
    def neovero_senha(self) -> str | None:
        return os.environ.get("NEOVERO_PASSWORD") or None

    @property
    def neovero_escrita_habilitada(self) -> bool:
        """Chave geral para qualquer ESCRITA no Neovero. Desligada por padrão: o
        contrato de escrita da API não foi validado contra um ambiente seguro."""
        return _bool("NEOVERO_WRITE_ENABLED", False)

    @property
    def neovero_escrita_simulada(self) -> bool:
        """Mesmo com a escrita habilitada, `true` (padrão) só valida e registra o que
        SERIA enviado — nenhuma requisição de escrita sai da aplicação."""
        return _bool("NEOVERO_WRITE_DRY_RUN", True)

    # ── Sugestões e Suporte (e-mail via SMTP) ─────────────────────────────────
    # A senha de app do Gmail vive SOMENTE no ambiente/secret manager do servidor. Sem SMTP_USER e
    # SMTP_PASSWORD o recurso responde "não configurado" — nenhum envio é simulado.
    @property
    def smtp_host(self) -> str:
        return os.environ.get("SMTP_HOST", "smtp.gmail.com").strip()

    @property
    def smtp_port(self) -> int:
        return _int("SMTP_PORT", 587)

    @property
    def smtp_user(self) -> str | None:
        return os.environ.get("SMTP_USER") or None

    @property
    def smtp_password(self) -> str | None:
        return os.environ.get("SMTP_PASSWORD") or None

    @property
    def smtp_remetente(self) -> str | None:
        return os.environ.get("SMTP_FROM") or self.smtp_user

    @property
    def suporte_destino(self) -> str:
        return os.environ.get("SUPORTE_DESTINO", "dev.tech@myflux.ai").strip()

    @property
    def suporte_limite_por_hora(self) -> int:
        return _int("SUPORTE_LIMITE_POR_HORA", 5)

    @property
    def suporte_configurado(self) -> bool:
        return bool(self.smtp_user and self.smtp_password and self.smtp_remetente)


settings = Settings()

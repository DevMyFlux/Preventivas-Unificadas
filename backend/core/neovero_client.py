"""
Cliente HTTP compartilhado para a API Neovero.
Gerencia autenticação e paginação — independente de unidade.
"""
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from core.settings import settings

MAX_WORKERS_PADRAO = 6  # concorrência controlada para não sobrecarregar a API do Neovero

_token_cache: dict = {"token": None, "expires": 0.0}

class NeoveroConfigError(RuntimeError):
    """Credenciais/URL do Neovero ausentes no ambiente."""


class NeoveroIndisponivelError(RuntimeError):
    """Neovero fora do ar, lento ou respondendo com erro de rede/servidor."""


def _url_base() -> str:
    return settings.neovero_url_base


def _headers_base() -> dict:
    origem = settings.neovero_origin
    return {
        "client_name": "NeoveroWeb",
        "accept": "application/json, text/plain, */*",
        "origin": origem,
        "referer": origem + "/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }


# Compatibilidade: código/testes antigos importam URL_BASE e HEADERS_BASE.
URL_BASE = settings.neovero_url_base
HEADERS_BASE = _headers_base()

SIT_MAP = {1: "Aberta", 2: "Em Andamento", 3: "Fechada", 4: "Cancelada"}

# Situações que representam uma OS realmente em curso — o Neovero não cria a ordem de
# serviço com antecedência pra uma preventiva projetada no futuro, então o que vem
# "vinculado" a um item costuma ser a última OS já fechada de um ciclo anterior. Exibir
# isso pra qualquer ocorrência futura confundia o usuário (parecia ser a OS daquela
# data específica). Só mostra a OS vinculada quando ela está de fato aberta/em
# andamento; caso contrário, o campo fica vazio.
_SITUACOES_ATIVAS = frozenset({1, 2})


def os_vinculada_visivel(os_v: dict) -> tuple[str, str]:
    """Retorna (número, situação) da OS vinculada a um item, só quando ela está
    realmente aberta ou em andamento. Sem OS ativa, retorna ("—", "—")."""
    situacao = (os_v or {}).get("situacao")
    if situacao not in _SITUACOES_ATIVAS:
        return "—", "—"
    return os_v.get("numero", "") or "—", SIT_MAP.get(situacao, "—")


def obter_token() -> str:
    if _token_cache["token"] and time.time() < _token_cache["expires"]:
        return _token_cache["token"]
    usuario, senha = settings.neovero_usuario, settings.neovero_senha
    if not usuario or not senha:
        raise NeoveroConfigError(
            "Integração Neovero não configurada: defina NEOVERO_USERNAME e NEOVERO_PASSWORD no ambiente.")
    try:
        r = requests.post(
            _url_base() + "/api/token",
            data={"username": usuario, "password": senha},  # form-urlencoded; escapa caracteres especiais
            headers={**_headers_base(), "content-type": "application/x-www-form-urlencoded"},
            timeout=60,
        )
        r.raise_for_status()
    except requests.RequestException as exc:
        raise NeoveroIndisponivelError(f"Falha ao autenticar no Neovero: {type(exc).__name__}") from exc
    token = r.json().get("access_token", "")
    _token_cache["token"] = token
    _token_cache["expires"] = time.time() + 3000  # 50 minutos
    return token


def get_headers() -> dict:
    return {**_headers_base(), "authorization": f"Bearer {obter_token()}"}


def _requisitar(metodo: str, caminho: str, headers: dict, *, json_body=None, tentativas: int = 2):
    """Uma requisição ao Neovero com tratamento uniforme de falhas.

    * Erro de rede/timeout/5xx → `NeoveroIndisponivelError` (nunca devolve dado parcial
      como se fosse completo).
    * 401 → descarta o token em cache e tenta mais uma vez com um token novo.
    A resposta (qualquer status < 500) é devolvida para o chamador decidir sobre 4xx."""
    ultimo_erro = None
    for tentativa in range(tentativas):
        try:
            r = requests.request(metodo, f"{_url_base()}{caminho}", headers=headers, json=json_body, timeout=60)
        except requests.RequestException as exc:
            ultimo_erro = exc
            continue
        if r.status_code == 401 and tentativa + 1 < tentativas:
            _token_cache["token"] = None
            headers = {**headers, "authorization": f"Bearer {obter_token()}"}
            continue
        if r.status_code >= 500:
            ultimo_erro = RuntimeError(f"HTTP {r.status_code}")
            continue
        return r
    raise NeoveroIndisponivelError(
        f"Neovero indisponível ({type(ultimo_erro).__name__ if ultimo_erro else 'erro'}) em {caminho}")


def _pagina(headers: dict, payload_base: dict, endpoint: str, offset: int) -> dict:
    r = _requisitar("POST", endpoint, {**headers, "content-type": "application/json"},
                    json_body={**payload_base, "offset": offset})
    r.raise_for_status()
    return r.json()


def paginar(headers: dict, payload_base: dict, endpoint: str, max_workers: int = MAX_WORKERS_PADRAO) -> list:
    """Percorre todas as páginas do endpoint POST Neovero e retorna os registros acumulados.

    A 1ª página traz `totalCount`; com ele as demais são buscadas em paralelo (concorrência
    limitada) em vez de uma depois da outra — a consulta de OS de um mês levava ~30 s em série.
    Sem `totalCount` (ou com resposta inesperada) cai no modo sequencial. Qualquer página que
    falhe levanta NeoveroIndisponivelError: nunca se devolve um resultado parcial como completo."""
    limite = payload_base.get("limit", 100)
    primeira = _pagina(headers, payload_base, endpoint, 0)
    regs = list(primeira.get("records", []))
    total = primeira.get("totalCount")
    if len(regs) < limite:
        return regs

    if isinstance(total, int) and total > limite:
        offsets = list(range(limite, total, limite))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            paginas = list(executor.map(lambda off: _pagina(headers, payload_base, endpoint, off), offsets))
        vistos = {r.get("id") for r in regs if isinstance(r, dict) and r.get("id") is not None}
        for pg in paginas:
            for rec in pg.get("records", []):
                rid = rec.get("id") if isinstance(rec, dict) else None
                if rid is not None:
                    if rid in vistos:
                        continue   # registro deslocado entre páginas por inclusão concorrente
                    vistos.add(rid)
                regs.append(rec)
        return regs

    offset = limite   # modo sequencial (sem totalCount)
    while True:
        pg = _pagina(headers, payload_base, endpoint, offset)
        lote = pg.get("records", [])
        regs.extend(lote)
        offset += limite
        if not lote or len(lote) < limite:
            break
    return regs


def buscar_itens_plano(headers: dict, plano_id, limit: int = 200) -> list:
    """Busca itens (preventivas) de um plano com paginação. Plano inexistente (404) devolve
    lista vazia; falha de rede/servidor levanta NeoveroIndisponivelError (não esconde o erro)."""
    itens, offset_i = [], 0
    while True:
        r = _requisitar("GET", f"/api/planosmanutencao/{plano_id}/itens?limit={limit}&offset={offset_i}", headers)
        if r.status_code != 200:
            break
        dados = r.json()
        lote = dados.get("itens", dados.get("records", []))
        itens.extend(lote)
        offset_i += limit
        if not lote or len(lote) < limit:
            break
    return itens


def buscar_os(headers: dict, os_id) -> dict | None:
    """Detalhe de uma OS (GET /api/ordensservico/{id}); None se não existir."""
    r = _requisitar("GET", f"/api/ordensservico/{os_id}", headers)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def buscar_itens_varios_planos(headers: dict, planos: list, max_workers: int = 10) -> dict:
    """Busca itens de vários planos em paralelo (concorrência controlada).
    Retorna {plano_id: itens}. Uma requisição HTTP por plano continua sendo feita —
    só deixam de ser sequenciais, evitando N round-trips um atrás do outro."""
    resultado = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(buscar_itens_plano, headers, p["id"]): p["id"] for p in planos}
        for future in futures:
            plano_id = futures[future]
            resultado[plano_id] = future.result()
    return resultado


def filtros_planos(empresa_id: int, oficina_id: int = 0, ativo: bool | None = True) -> list:
    """Monta filtros Neovero para planos de manutenção. oficina_id=0 = sem filtro. ativo=None omite o filtro."""
    filtros = [{"property": "empresaId", "value": empresa_id}]
    if ativo is not None:
        filtros.append({"property": "ativo", "value": ativo})
    if oficina_id:
        filtros.append({"property": "oficina.id", "value": [oficina_id]})
    return filtros

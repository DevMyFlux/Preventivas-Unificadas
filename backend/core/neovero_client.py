"""
Cliente HTTP compartilhado para a API Neovero.
Gerencia autenticação e paginação — independente de unidade.
"""
import time
from concurrent.futures import ThreadPoolExecutor

import requests

MAX_WORKERS_PADRAO = 6  # concorrência controlada para não sobrecarregar a API do Neovero

_token_cache: dict = {"token": None, "expires": 0.0}

URL_BASE = "https://grandmassif.api.neovero.com"
USUARIO = "admin@myflux.ai"
SENHA = "admin@2026"

HEADERS_BASE = {
    "client_name": "NeoveroWeb",
    "accept": "application/json, text/plain, */*",
    "origin": "https://grandmassif.neovero.com",
    "referer": "https://grandmassif.neovero.com/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

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
    r = requests.post(
        URL_BASE + "/api/token",
        data=f"username={USUARIO}&password={SENHA.replace('@', '%40')}",
        headers={**HEADERS_BASE, "content-type": "application/x-www-form-urlencoded"},
        timeout=60,
    )
    r.raise_for_status()
    token = r.json().get("access_token", "")
    _token_cache["token"] = token
    _token_cache["expires"] = time.time() + 3000  # 50 minutos
    return token


def get_headers() -> dict:
    return {**HEADERS_BASE, "authorization": f"Bearer {obter_token()}"}


def paginar(headers: dict, payload_base: dict, endpoint: str) -> list:
    """Percorre todas as páginas do endpoint POST Neovero e retorna registros acumulados."""
    todas, offset = [], 0
    while True:
        r = requests.post(
            f"{URL_BASE}{endpoint}",
            headers={**headers, "content-type": "application/json"},
            json={**payload_base, "offset": offset},
            timeout=60,
        )
        r.raise_for_status()
        regs = r.json().get("records", [])
        todas.extend(regs)
        offset += payload_base.get("limit", 100)
        if not regs or len(regs) < payload_base.get("limit", 100):
            break
    return todas


def buscar_itens_plano(headers: dict, plano_id, limit: int = 200) -> list:
    """Busca itens (preventivas) de um plano com paginação."""
    itens, offset_i = [], 0
    while True:
        r = requests.get(
            f"{URL_BASE}/api/planosmanutencao/{plano_id}/itens?limit={limit}&offset={offset_i}",
            headers=headers,
            timeout=60,
        )
        if r.status_code != 200:
            break
        dados = r.json()
        lote = dados.get("itens", dados.get("records", []))
        itens.extend(lote)
        offset_i += limit
        if not lote or len(lote) < limit:
            break
    return itens


def buscar_itens_varios_planos(headers: dict, planos: list, max_workers: int = MAX_WORKERS_PADRAO) -> dict:
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

"""
Registro único das unidades atendidas pela aplicação.

É a fonte de verdade para o vínculo usuário↔unidade: o escopo de acesso (backend) é
decidido a partir do prefixo da rota ↔ unidade do usuário, nunca de um parâmetro
enviado pelo frontend.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Unidade:
    codigo: str          # chave persistida em users.unit
    nome: str            # rótulo de exibição
    prefixo_api: str     # prefixo de URL do blueprint da unidade
    empresa_id: int      # empresa.id no Neovero


UNIDADES: dict[str, Unidade] = {
    "HETRIN": Unidade("HETRIN", "Hetrin", "/api/grandmassif", 3),
    "HMB": Unidade("HMB", "HMB", "/api/brasilandia", 2),
}


def unidade_por_prefixo(caminho: str) -> Unidade | None:
    """Devolve a unidade dona de um caminho de URL (`/api/grandmassif/...`), ou None."""
    for u in UNIDADES.values():
        if caminho == u.prefixo_api or caminho.startswith(u.prefixo_api + "/"):
            return u
    return None


def codigo_valido(codigo: str | None) -> bool:
    return codigo in UNIDADES

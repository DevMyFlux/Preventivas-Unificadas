"""
Regras de CARGO por plano de manutenção (quem pode executar o quê).

Mecanismo genérico e declarativo: cada unidade declara sua própria tabela de `RegraCargo`
(ver `units/grand_massif/regras_cargo.py`); nada é copiado entre unidades — uma unidade sem
tabela não sofre nenhuma restrição extra.

Uma regra tem cargos PRINCIPAIS e, opcionalmente, ALTERNATIVOS declarados de forma explícita:
  * o motor escolhe entre os principais disponíveis (com vaga no dia);
  * só recorre a um cargo alternativo se NENHUM principal puder assumir — e o resultado
    carrega o aviso de que foi usado cargo alternativo (nunca é silencioso);
  * se nem principais nem alternativos puderem, a ocorrência fica SEM CANDIDATO com o motivo
    `cargo_sem_habilitado` — o sistema não escolhe outro cargo por conta própria.
"""
import re
from dataclasses import dataclass

from core.regras.nomes import sem_acento

FAM_ELETRICISTA = "eletricista"
FAM_AUX_ELETRICISTA = "aux_eletricista"
FAM_TEC_CLIMATIZACAO = "tecnico_climatizacao"
FAM_AUX_MANUTENCAO = "aux_manutencao"

NOMES_FAMILIAS = {
    FAM_ELETRICISTA: "Eletricista",
    FAM_AUX_ELETRICISTA: "Auxiliar de Eletricista",
    FAM_TEC_CLIMATIZACAO: "Técnico de Climatização",
    FAM_AUX_MANUTENCAO: "Auxiliar de Manutenção/Climatização",
}


def familia_do_cargo(cargo: str | None) -> str | None:
    """Família do cargo (None = cargo fora das famílias de execução: gestão, administrativo, vazio…)."""
    c = sem_acento(cargo or "").lower().strip()
    if not c:
        return None
    if c.startswith("aux") and "eletric" in c:
        return FAM_AUX_ELETRICISTA
    if c.startswith("aux") and ("manut" in c or "climat" in c):
        return FAM_AUX_MANUTENCAO
    if "tecnico" in c and "climat" in c:
        return FAM_TEC_CLIMATIZACAO
    if "eletricista" in c:
        return FAM_ELETRICISTA
    return None


@dataclass(frozen=True)
class RegraCargo:
    id: str
    descricao: str                      # texto de negócio (aparece em alertas e relatórios)
    padrao: str                         # regex aplicada ao nome do plano normalizado (maiúsculo, sem acento)
    principais: tuple[str, ...]
    alternativas: tuple[str, ...] = ()

    def casa(self, descricao_plano: str) -> bool:
        return re.search(self.padrao, normalizar_plano(descricao_plano)) is not None

    @property
    def permitidas(self) -> tuple[str, ...]:
        return self.principais + self.alternativas

    def texto_cargos(self) -> str:
        p = " ou ".join(NOMES_FAMILIAS[f] for f in self.principais)
        if not self.alternativas:
            return p
        return f"{p} (alternativa: {' ou '.join(NOMES_FAMILIAS[f] for f in self.alternativas)})"


def normalizar_plano(texto: str | None) -> str:
    return " ".join(sem_acento(texto or "").upper().split())


def regra_do_plano(regras: tuple[RegraCargo, ...] | list[RegraCargo], descricao_plano: str | None) -> RegraCargo | None:
    """Primeira regra cujo padrão casa com o plano (a ordem da tabela é a prioridade)."""
    if not descricao_plano:
        return None
    for r in regras:
        if r.casa(descricao_plano):
            return r
    return None


def violacao(regra: RegraCargo | None, cargo: str | None) -> str | None:
    """Texto do desvio se o `cargo` não é permitido pela regra; None se está de acordo (ou sem regra)."""
    if regra is None:
        return None
    fam = familia_do_cargo(cargo)
    if fam in regra.principais:
        return None
    if fam in regra.alternativas:
        return f"Cargo alternativo ({NOMES_FAMILIAS[fam]}): a regra pede {regra.texto_cargos()}"
    return f"Cargo fora da regra: o plano pede {regra.texto_cargos()}"

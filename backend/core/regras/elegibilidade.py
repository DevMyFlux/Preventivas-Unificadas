"""
Elegibilidade de colaboradores para receber ordens de serviço — regra ÚNICA e central.

Um colaborador só é elegível numa data se TODAS as condições abaixo valerem:

  1. Executa OS: o cargo não é de gestão/administração/análise (gerente, engenheiro,
     supervisor, coordenador, administrativo, analista…). Quem opera/gerencia o sistema
     NUNCA é executante por padrão. (Causa-raiz do relato "ordens aparecendo em nome do
     gestor": o cargo "Supervisor de Manutenção" casava com "supervisor" em
     _CARGO_TECNICO e a categoria "Geral" aceitava qualquer cargo.)
  2. Status não é "Desligado" (exclusão do mês inteiro, definida pela escala/overlay).
  3. A data está dentro do vínculo: >= data_admissao (se houver) e < data_desligamento
     (se houver) — o próprio dia do desligamento já é indisponível, convenção adotada
     pela supervisão desde a primeira regra de desligamento (ver colaboradores_overlay).
  4. Não está bloqueado (aptidão pendente, ex.: NR-10).

A função devolve também o MOTIVO da inelegibilidade, para diagnóstico e relatórios.
Ela é usada pelo motor de recomendação (hard gate), por `esta_disponivel` de cada
unidade e pelos relatórios de revisão — não existe segunda implementação.
"""
from datetime import date

from core import colaboradores_overlay

# Palavras que identificam cargos que NÃO executam ordens de serviço de campo.
CARGOS_NAO_EXECUTANTES = (
    "gerente", "engenheir", "supervisor", "coordenador", "gestor", "gestora", "diretor",
    "administrativ", "analista", "assistente administrativo", "secretári",
)

MOTIVO_NAO_EXECUTA = "cargo_nao_executante"
MOTIVO_DESLIGADO_STATUS = "status_desligado"
MOTIVO_FORA_DO_VINCULO = "fora_do_vinculo"
MOTIVO_BLOQUEADO = "bloqueado"


def cargo_executa_os(cargo: str | None) -> bool:
    c = (cargo or "").strip().lower()
    return not any(k in c for k in CARGOS_NAO_EXECUTANTES)


def cargo_e_gestao(cargo: str | None) -> bool:
    return not cargo_executa_os(cargo)


def motivo_inelegibilidade(row, data_ref: date) -> str | None:
    """None se elegível em `data_ref`; senão o código do primeiro impedimento."""
    if not cargo_executa_os(str(row.get("cargo", ""))):
        return MOTIVO_NAO_EXECUTA
    if row.get("status") == "Desligado":
        return MOTIVO_DESLIGADO_STATUS
    if not colaboradores_overlay.dentro_do_vinculo(row, data_ref):
        return MOTIVO_FORA_DO_VINCULO
    if row.get("bloqueado"):
        return MOTIVO_BLOQUEADO
    return None


def elegivel(row, data_ref: date) -> bool:
    return motivo_inelegibilidade(row, data_ref) is None


def ficou_desligado_ate(row, data_ref: date) -> bool:
    """True se o colaborador está desligado (por status ou por data) em `data_ref`.
    Usado para sinalizar OS ainda atribuídas a quem já saiu — nunca reatribui sozinho."""
    return row.get("status") == "Desligado" or not colaboradores_overlay.dentro_do_vinculo(row, data_ref)

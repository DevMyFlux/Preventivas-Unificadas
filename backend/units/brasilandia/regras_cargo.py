"""
Regras de CARGO da HMB por plano de manutenção (pedido dos usuários do sistema, out/2026).

Aplica-se SOMENTE à HMB — a HETRIN tem a sua tabela (units/grand_massif/regras_cargo.py) e não herda nada daqui.
Executantes dos planos mensais que o Neovero deixa no nome do supervisor (responsável padrão do plano):

  PM - MENSAL - MOTOBOMBA               Auxiliar de Manutenção Elétrica
  PM - MENSAL - RONDA - ILUMINAÇÃO      Auxiliar de Manutenção Elétrica
  PM - MENSAL - FANCOIL                 Técnico de Climatização
  QUADROS ELÉTRICOS (todos)             Eletricista

Não há cargo alternativo: se ninguém do cargo pedido estiver disponível, a ocorrência fica SEM CANDIDATO com o motivo
explícito (requer intervenção) — o sistema não escolhe outro cargo por conta própria.
Os padrões usam \\W+ entre as palavras porque o Neovero grafa os planos da HMB com travessão (–) e espaços duplos.
"""
from core.regras.cargos import (
    FAM_AUX_ELETRICISTA, FAM_ELETRICISTA, FAM_TEC_CLIMATIZACAO, RegraCargo, regra_do_plano,
)

REGRAS_CARGO = (
    RegraCargo("mensal_motobomba",
               "Motobomba mensal: Auxiliar de Manutenção Elétrica",
               r"PM\W+MENSAL\W+MOTO\s?BOMBAS?\b", (FAM_AUX_ELETRICISTA,)),
    RegraCargo("mensal_ronda_iluminacao",
               "Ronda mensal de iluminação: Auxiliar de Manutenção Elétrica",
               r"PM\W+MENSAL\W+RONDA\W+ILUMINACAO", (FAM_AUX_ELETRICISTA,)),
    RegraCargo("mensal_fancoil",
               "Fancoil mensal: Técnico de Climatização",
               r"PM\W+MENSAL\W+FANCOILS?\b", (FAM_TEC_CLIMATIZACAO,)),
    RegraCargo("quadros_eletricos",
               "Quadros elétricos: Eletricista",
               r"\bQUADROS?\s+ELETRICOS?\b", (FAM_ELETRICISTA,)),
)


def regra_cargo_do_plano(descricao_plano: str | None) -> RegraCargo | None:
    return regra_do_plano(REGRAS_CARGO, descricao_plano)

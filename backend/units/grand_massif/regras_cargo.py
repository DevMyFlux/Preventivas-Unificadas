"""
Regras de CARGO da HETRIN por plano de manutenção (pedido da supervisão, set/2026).

Aplica-se SOMENTE à HETRIN. A HMB tem regras próprias (nominais) e não herda nada daqui.
Os cargos "alternativos" são EXPLÍCITOS e configuráveis neste arquivo — não há alternativa implícita.
A ordem é a prioridade: a primeira regra que casa com o plano vale.
"""
from core.regras.cargos import (
    FAM_AUX_ELETRICISTA, FAM_AUX_MANUTENCAO, FAM_ELETRICISTA, FAM_TEC_CLIMATIZACAO, RegraCargo, regra_do_plano,
)

REGRAS_CARGO = (
    RegraCargo("rondas_climatizacao_diarias",
               "Rondas diárias de chiller / ar comprimido: exclusivas do Técnico de Climatização",
               r"RONDA DIARIA.*(CHILLER|AR COMPRIMIDO)", (FAM_TEC_CLIMATIZACAO,)),
    RegraCargo("fancoils_e_fancoletes",
               "Limpeza de fancoils e fancoletes: Técnico de Climatização",
               r"(LIMPEZA.*FANCOILS?|\bFANCOLETES?\b)", (FAM_TEC_CLIMATIZACAO,)),
    RegraCargo("inspecao_combate_incendio",
               "Inspeção do sistema de combate a incêndio: Eletricista",
               r"INSPECAO.*COMBATE A INCENDIO", (FAM_ELETRICISTA,)),
    RegraCargo("grupos_geradores",
               "Grupos geradores (teste de partida e demais planos): exclusivamente Eletricista",
               r"(GERADOR|TESTE DE PARTIDA)", (FAM_ELETRICISTA,)),
    RegraCargo("paineis_termossolares",
               "Limpeza/inspeção dos painéis termossolares: Eletricista",
               r"PAINE(L|IS) TERMOSSOLARE?S?", (FAM_ELETRICISTA,)),
    RegraCargo("coleta_medidor_noturno_n1",
               "Coleta de medidor noturna (N1): Auxiliar de Eletricista",
               r"COLETA DIARIA MEDIDOR.*NOTURNO.*\bN1\b", (FAM_AUX_ELETRICISTA,)),
    RegraCargo("reguas_gases_e_exaustores",
               "Réguas de gases medicinais e exaustores/difusores: Auxiliar de Manutenção "
               "(alternativa explícita: Auxiliar de Eletricista)",
               r"(REGUAS? DE GASES|EXAUSTORES/DIFUSORES)", (FAM_AUX_MANUTENCAO,), (FAM_AUX_ELETRICISTA,)),
    RegraCargo("motobombas",
               "Motobombas: Eletricista (os nomes por turno e dia estão em regras.py)",
               r"MOTOBOMBAS?", (FAM_ELETRICISTA,)),
    RegraCargo("ronda_iluminacao_tomadas",
               "Ronda de iluminação/tomadas: Eletricista (alternativa explícita: Auxiliar de Eletricista)",
               r"RONDA.*ILUMINACAO/TOMADAS", (FAM_ELETRICISTA,), (FAM_AUX_ELETRICISTA,)),
)


def regra_cargo_do_plano(descricao_plano: str | None) -> RegraCargo | None:
    return regra_do_plano(REGRAS_CARGO, descricao_plano)

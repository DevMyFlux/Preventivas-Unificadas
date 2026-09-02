"""
Escala nominal obrigatória para as coletas diárias da HETRIN (Medidor de Energia e
Hidrômetro) — pedido explícito da supervisão da unidade (email "Ajustes na Lógica de
Distribuição de OS", set/2026):

    Coleta Diária – Medidor de Energia:
        Jussara da Conceição  -> Auxiliar, Diurno Ímpar
        Wellington             -> Auxiliar, Noturno Ímpar
        Eduonete               -> Auxiliar, Diurno Par
        Isabel                  -> Auxiliar, Noturno Par
    Coleta Diária – Hidrômetro:
        Jussara da Conceição  -> Turno Ímpar
        Eduonete               -> Turno Par

Fica AQUI (não em core/motor_base.py) porque é dado específico da HETRIN — nomes reais
de colaboradores desta unidade, não uma regra genérica reaproveitável pela HMB. O
motor compartilhado só ganhou um gate genérico e parametrizável (`nomes_permitidos`
em core.motor_base.indicar_responsavel); quem preenche esse parâmetro com dado real é
cada unidade, do mesmo jeito que `exigir_turno`/`hora_ref` já são calculados em
routes.py e só passados adiante pro motor.

Confirmado contra a planilha real (Escala_HETRIN_Setembro_2026.xlsx) e contra a API
Neovero real (investigação set/2026): as 4 pessoas existem, os cargos/turnos batem, e
o padrão par/ímpar real (inspecionado dia a dia em `dias_plantao`, já que o campo
`regime` sozinho não é confiável no formato de planilha atual — sempre "Fixo") bate
exatamente com o que a supervisão pediu. Wellington segue com o padrão de escala
correto, mas seu cadastro está com `bloqueado=True` (pendência de qualificação/
autorização NR-10) — isso já é resolvido pelo gate de disponibilidade existente
(colaboradores bloqueados nunca aparecem como disponíveis), não precisa de tratamento
especial aqui.

A cobertura de itens foi conferida contra os planos reais ativos na Neovero: a família
"Medidor de Energia" tem exatamente 4 planos ativos (D1/D2/N1/N2, todos o mesmo
equipamento físico lido em 4 turnos) e a família "Hidrômetro" tem exatamente 2 (D1/D2,
sem variante noturna) — a escala nomeada de 4 e 2 pessoas, respectivamente, cobre as
duas famílias sem sobra nem lacuna.
"""
import re
import unicodedata


def _sem_acento(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


_RE_MEDIDOR = re.compile(r"\bMEDIDOR\b")
_RE_HIDROMETRO = re.compile(r"\bHIDROMETRO\b")

# paridade: "Par"/"Ímpar" — mesmo valor já calculado em routes.py como `dia_par`
# (paridade real do dia da ocorrência, não do nome do plano) e reaproveitado aqui.
ESCALA_COLETA_MEDIDOR = [
    {"nome": "Jussara da Conceição Cruz", "turno": "Diurno", "paridade": "Ímpar"},
    {"nome": "Wellington de Souza Brito", "turno": "Noturno", "paridade": "Ímpar"},
    {"nome": "Eduonete Lopes dos Santos", "turno": "Diurno", "paridade": "Par"},
    {"nome": "Isabel Alves Dias", "turno": "Noturno", "paridade": "Par"},
]
# Não existe variante noturna de hidrômetro nos planos ativos da HETRIN — só 2 pessoas,
# diferenciadas só pela paridade do dia (o turno já é implicitamente Diurno pros dois
# planos ativos, e o gate de turno genérico de indicar_responsavel já cobre isso).
ESCALA_COLETA_HIDROMETRO = [
    {"nome": "Jussara da Conceição Cruz", "paridade": "Ímpar"},
    {"nome": "Eduonete Lopes dos Santos", "paridade": "Par"},
]


def nomes_permitidos_coleta(nome_plano: str, dia_par: str) -> set | None:
    """Retorna o conjunto de nomes autorizados pra essa ocorrência, se o plano for uma
    das coletas diárias nomeadas (Medidor de Energia / Hidrômetro); None se o plano
    não for uma dessas duas famílias — nesse caso o chamador não deve restringir nada
    (equivalente a não passar `nomes_permitidos` pro motor).

    `dia_par` já vem calculado em routes.py como "Par"/"Ímpar" (paridade real do dia
    da ocorrência, dt_prev.day % 2) — mesmo campo usado no card final da preventiva.
    Turno não é filtrado aqui: o plano já é explícito sobre turno no próprio nome
    ("...- DIURNO - D1", "...- NOTURNO - N1") e o gate de turno genérico de
    indicar_responsavel (via detectar_turno + exigir_turno) já cobre essa parte —
    filtrar de novo aqui seria duplicar uma regra que já funciona."""
    if not nome_plano:
        return None
    normalizado = _sem_acento(nome_plano).upper()
    if _RE_MEDIDOR.search(normalizado):
        tabela = ESCALA_COLETA_MEDIDOR
    elif _RE_HIDROMETRO.search(normalizado):
        tabela = ESCALA_COLETA_HIDROMETRO
    else:
        return None
    return {e["nome"] for e in tabela if e["paridade"] == dia_par}

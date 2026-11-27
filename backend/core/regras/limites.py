"""
Limite diário de ordens por colaborador, por especialidade.

  * Elétrica:     no máximo 14 ordens por colaborador por dia.
  * Climatização: no máximo 10 ordens por colaborador por dia.

Decisões documentadas (o enunciado deixou em aberto):

  * ESPECIALIDADE é a do COLABORADOR (derivada do cargo), não a da OS: um eletricista
    nunca passa de 14/dia, qualquer que seja a categoria das tarefas dele. Cargos sem
    especialidade de limite (ex.: "Aux. Manutenção Hidráulica") não têm teto.
  * O DIA é a data de execução da ocorrência (data prevista da preventiva / data de
    abertura da OS real), no calendário local — nunca a data em que o cálculo rodou.
  * O QUE CONTA: toda OS atribuída ao colaborador no dia que não esteja Cancelada
    (Aberta, Em Andamento e Fechada contam — o trabalho do dia foi demanda dele) mais
    as ocorrências *projetadas* que o motor já atribuiu a ele nesta geração.
  * SEM CONTAR DUAS VEZES: cada item é identificado por uma chave única (`OS:<número>`
    para OS reais; `PREV:<plano>:<item>:<data>` para ocorrências projetadas) guardada
    num conjunto por (colaborador, dia) — registrar a mesma chave de novo não aumenta
    a contagem.
  * TIPOS ISENTOS: nenhum por padrão (`TIPO_IDS_ISENTOS_LIMITE` vazio — o enunciado não abre exceção).
    DECISÃO PENDENTE da supervisão: na HMB há ~27 rondas diurnas e ~19 noturnas por dia e a regra de
    rondas aponta UM responsável por turno/paridade; com o teto de 14 para eletricista, o excedente
    aparece como "requer intervenção". Se as rondas (tipo RONDA, id 8 no Neovero) não devem consumir
    o limite, basta incluir 8 em TIPO_IDS_ISENTOS_LIMITE — é a única linha a mudar.
"""
from collections import defaultdict
from datetime import date

ESPECIALIDADE_ELETRICA = "Elétrica"
ESPECIALIDADE_CLIMATIZACAO = "Climatização"

LIMITES_DIARIOS: dict[str, int] = {
    ESPECIALIDADE_ELETRICA: 14,
    ESPECIALIDADE_CLIMATIZACAO: 10,
}

# ids de tipoManutencao do Neovero (ex.: {8} = RONDA na HMB) que NÃO consomem o limite diário.
# Vazio = tudo conta (comportamento pedido no enunciado).
TIPO_IDS_ISENTOS_LIMITE: frozenset[int] = frozenset()


def tipo_isento(tipo_id) -> bool:
    return tipo_id in TIPO_IDS_ISENTOS_LIMITE

_KW_ELETRICA = ("eletricista", "elétric", "eletric")
_KW_CLIMATIZACAO = ("climatiza", "refriger")


def especialidade_do_cargo(cargo: str | None) -> str | None:
    """'Elétrica' / 'Climatização' / None (sem especialidade sujeita a limite)."""
    c = (cargo or "").lower()
    if any(k in c for k in _KW_ELETRICA):
        return ESPECIALIDADE_ELETRICA
    if any(k in c for k in _KW_CLIMATIZACAO):
        return ESPECIALIDADE_CLIMATIZACAO
    return None


def limite_do_cargo(cargo: str | None) -> int | None:
    esp = especialidade_do_cargo(cargo)
    return LIMITES_DIARIOS.get(esp) if esp else None


class OcupacaoDiaria:
    """Controle de ocupação diária: quantas ordens (únicas) cada colaborador já tem em cada dia."""

    def __init__(self):
        self._itens: dict[tuple[str, date], set[str]] = defaultdict(set)

    def registrar(self, nome: str, dia: date, chave: str) -> bool:
        """Registra o item; devolve False se a mesma chave já estava registrada (sem dupla contagem)."""
        conj = self._itens[(nome, dia)]
        if chave in conj:
            return False
        conj.add(chave)
        return True

    def total(self, nome: str, dia: date) -> int:
        return len(self._itens.get((nome, dia), ()))

    def contem(self, nome: str, dia: date, chave: str) -> bool:
        return chave in self._itens.get((nome, dia), ())

    def tem_vaga(self, nome: str, cargo: str | None, dia: date) -> bool:
        limite = limite_do_cargo(cargo)
        return limite is None or self.total(nome, dia) < limite

    def resumo_dia(self, dia: date) -> dict[str, int]:
        return {n: len(v) for (n, d), v in self._itens.items() if d == dia}


def chave_os(numero) -> str:
    return f"OS:{numero}"


def chave_prevista(plano_id, item_id, dia: date) -> str:
    return f"PREV:{plano_id}:{item_id}:{dia.isoformat()}"

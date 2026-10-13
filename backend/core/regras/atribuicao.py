"""
Regras nominais de atribuição de executantes (tabelas "turno × tipo de dia → responsável").

Uma `RegraNominal` diz: para ocorrências de certos planos (ronda diária, oficina de ar
comprimido…), o executante é fixado pela combinação TURNO × PARIDADE DO DIA DE EXECUÇÃO.

Princípios:
  * A paridade é a do DIA DE EXECUÇÃO da ocorrência (data prevista / data da OS), nunca a
    do dia em que a ordem foi criada ou processada. A conta usa `date.day % 2`, portanto
    vale igual na virada de mês (31 → 1 mantém a regra por dia-calendário; 30 é par, 31
    ímpar, 1 ímpar…).
  * Combinação turno×paridade que a regra NÃO especifica → a regra não se aplica
    (`sem_regra`): o comportamento anterior é preservado, nada é inventado.
  * Os nomes da regra são apelidos ("Michael", "Diego H"). Eles são validados contra o
    cadastro ATIVO da unidade; se algum bater com mais de uma pessoa, com ninguém, ou
    divergir da escala (par/ímpar), a linha vira `pendente` e a ocorrência fica SEM
    candidato com o motivo explícito — nunca se escolhe um homônimo ao acaso.
  * Mais de um responsável na mesma linha → todos concorrem como executantes; a
    aplicação NÃO sobrescreve um pelo outro (o motor devolve principal + apoio e a tela
    mostra os dois).
"""
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from core.regras.nomes import ResolucaoAlias, normalizar_nome, resolver_alias

TURNO_DIURNO = "Diurno"
TURNO_NOTURNO = "Noturno"
PAR = "Par"
IMPAR = "Ímpar"


def paridade_do_dia(d: date) -> str:
    return PAR if d.day % 2 == 0 else IMPAR


@dataclass(frozen=True)
class ContextoOcorrencia:
    """Dados mínimos de uma ocorrência para decidir se uma regra se aplica."""
    descricao: str          # nome do plano de manutenção
    oficina: str
    tipo_id: int | None     # tipoManutencao.id no Neovero (ex.: 8 = RONDA na HMB)
    periodicidade: int
    unidade_tempo: str      # D, S, M, A
    data: date              # dia de EXECUÇÃO
    turno: str | None       # Diurno/Noturno declarado pelo plano; None = não declarado


@dataclass(frozen=True)
class LinhaRegra:
    turno: str
    paridade: str
    responsaveis: tuple[str, ...]


@dataclass(frozen=True)
class RegraNominal:
    id: str
    titulo: str
    descricao: str
    linhas: tuple[LinhaRegra, ...]
    aplica: Callable[[ContextoOcorrencia], bool]
    # turno efetivo da ocorrência quando o plano não o declara (ex.: ronda diurna não diz "diurno")
    turno_padrao: str | None = TURNO_DIURNO

    def aliases(self) -> set[str]:
        return {normalizar_nome(a) for linha in self.linhas for a in linha.responsaveis}


@dataclass
class LinhaResolvida:
    turno: str
    paridade: str
    resolucoes: list[ResolucaoAlias]
    alertas: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "ok" if all(r.status == "ok" for r in self.resolucoes) else "pendente"

    @property
    def nomes(self) -> list[str]:
        return [r.escolhido for r in self.resolucoes if r.escolhido]

    @property
    def pendencias(self) -> list[ResolucaoAlias]:
        return [r for r in self.resolucoes if r.status != "ok"]


@dataclass
class RegraResolvida:
    regra: RegraNominal
    linhas: dict[tuple[str, str], LinhaResolvida]


@dataclass
class AplicacaoRegra:
    regra_id: str | None
    status: str                      # "sem_regra" | "aplicada" | "pendente"
    nomes: frozenset = frozenset()
    pendencias: tuple = ()
    alertas: tuple = ()
    mensagem: str = ""


SEM_REGRA = AplicacaoRegra(None, "sem_regra")


def _linhas_do_roster(roster) -> list[dict]:
    if roster is None:
        return []
    if hasattr(roster, "iterrows"):
        return [r.to_dict() for _, r in roster.iterrows()]
    return list(roster)


def resolver_regras(regras: list[RegraNominal], roster, confirmacoes: dict[str, str] | None = None
                    ) -> dict[str, RegraResolvida]:
    """Resolve todas as regras da unidade. Só colaboradores com status Ativo entram no
    cadastro de resolução (desligado não pode ser responsável de regra)."""
    linhas_roster = [r for r in _linhas_do_roster(roster) if r.get("status", "Ativo") == "Ativo"]
    por_nome = {r["funcionario"]: r for r in linhas_roster}
    nomes = list(por_nome)
    saida: dict[str, RegraResolvida] = {}
    for regra in regras:
        linhas: dict[tuple[str, str], LinhaResolvida] = {}
        for linha_regra in regra.linhas:
            res = [resolver_alias(a, nomes, confirmacoes) for a in linha_regra.responsaveis]
            alertas = []
            for r in res:
                if r.status != "ok":
                    continue
                reg = str(por_nome[r.escolhido].get("regime", "")).strip()
                if reg in (PAR, IMPAR) and reg != linha_regra.paridade:
                    alertas.append(
                        f"{r.escolhido} consta na regra para dias {linha_regra.paridade}, mas a escala dele(a) é {reg} — "
                        f"nesses dias só estará disponível quem a escala permitir.")
            linhas[(linha_regra.turno, linha_regra.paridade)] = LinhaResolvida(
                linha_regra.turno, linha_regra.paridade, res, alertas)
        saida[regra.id] = RegraResolvida(regra, linhas)
    return saida


def aplicar_regras(resolvidas: dict[str, RegraResolvida], ctx: ContextoOcorrencia) -> AplicacaoRegra:
    """Decide se alguma regra se aplica à ocorrência e, se sim, quem deve executá-la."""
    for rr in resolvidas.values():
        regra = rr.regra
        if not regra.aplica(ctx):
            continue
        turno = ctx.turno or regra.turno_padrao
        par = paridade_do_dia(ctx.data)
        linha = rr.linhas.get((turno, par))
        if linha is None:
            return SEM_REGRA  # combinação não especificada: preserva o comportamento existente
        if linha.status != "ok":
            msgs = "; ".join(p.motivo for p in linha.pendencias)
            return AplicacaoRegra(
                regra.id, "pendente", frozenset(), tuple(linha.pendencias), tuple(linha.alertas),
                f"Regra '{regra.titulo}' ({turno} {par}) aguardando confirmação de nome: {msgs}")
        return AplicacaoRegra(regra.id, "aplicada", frozenset(linha.nomes), (), tuple(linha.alertas),
                              f"Regra '{regra.titulo}' ({turno} {par}): {' + '.join(linha.nomes)}")
    return SEM_REGRA


def descrever(resolvidas: dict[str, RegraResolvida]) -> list[dict]:
    """Estrutura serializável para a tela de regras (e para o relatório de validação)."""
    saida = []
    for rr in resolvidas.values():
        linhas = []
        for (turno, par), lin in rr.linhas.items():
            linhas.append({
                "turno": turno, "paridade": par, "status": lin.status, "alertas": lin.alertas,
                "responsaveis": [{
                    "alias": r.alias, "status": r.status, "escolhido": r.escolhido, "origem": r.origem,
                    "candidatos": r.candidatos, "motivo": r.motivo,
                } for r in lin.resolucoes],
            })
        saida.append({"id": rr.regra.id, "titulo": rr.regra.titulo, "descricao": rr.regra.descricao, "linhas": linhas})
    return saida

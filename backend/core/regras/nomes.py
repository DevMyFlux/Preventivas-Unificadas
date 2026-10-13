"""
Nomes de pessoas: normalização, comparação tolerante (Neovero × cadastro interno) e
resolução de apelidos citados em regras de negócio ("Michael", "Diego H"…).

Princípio: um apelido só vira uma pessoa quando é *inequívoco* (bate com exatamente um
colaborador) ou quando um humano confirmou explicitamente (tabela `regra_resolucoes`).
Ambiguidade e ausência são devolvidas como tal — nunca resolvidas por palpite.
"""
import re
import unicodedata
from dataclasses import dataclass, field


def sem_acento(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalizar_nome(nome: str) -> str:
    """minúsculas, sem acento, sem pontuação, espaços colapsados."""
    t = sem_acento(nome).lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _bate_prefixo(p: str, q: str) -> bool:
    return p == q or p.startswith(q[:3]) or q.startswith(p[:3])


def nomes_batem(nome_api: str, nome_planilha: str) -> bool:
    """Compara o nome vindo do Neovero com o do cadastro interno, tolerando variações
    de grafia comuns (Willian/William, Morais/Moraes, abreviações com ponto). O 1º nome
    usa a mesma regra de prefixo (3 letras) dos demais; a defesa contra falso-positivo é
    exigir que a maioria das palavras bata (>= max(2, 60%)).

    Confirmado com dado real (HETRIN, set/2026): o Neovero tem "WILLIAN MIRANDA DE
    MORAIS" e o cadastro interno "William Miranda de Moraes" — a mesma pessoa."""
    def normalizar(n):
        return [p.replace(".", "").lower() for p in (n or "").strip().split() if len(p) > 1]
    partes_api = normalizar(nome_api)
    partes_planilha = normalizar(nome_planilha)
    if not partes_api or not partes_planilha:
        return False
    if not _bate_prefixo(partes_api[0], partes_planilha[0]):
        return False
    matches = sum(1 for p in partes_planilha if any(_bate_prefixo(p, q) for q in partes_api))
    return matches >= max(2, len(partes_planilha) * 0.6)


def encontrar_no_cadastro(nome_neovero: str, nomes_cadastro: list[str]) -> str | None:
    """Nome do cadastro interno que corresponde a `nome_neovero`, ou None. Se houver mais
    de um candidato plausível devolve o de maior sobreposição de palavras *apenas se
    único no topo*; empate = None (ambíguo), para quem chama sinalizar revisão."""
    if not nome_neovero:
        return None
    exato = [n for n in nomes_cadastro if normalizar_nome(n) == normalizar_nome(nome_neovero)]
    if len(exato) == 1:
        return exato[0]
    candidatos = [n for n in nomes_cadastro if nomes_batem(nome_neovero, n)]
    if len(candidatos) == 1:
        return candidatos[0]
    if not candidatos:
        return None
    palavras_api = set(normalizar_nome(nome_neovero).split())
    pontos = sorted(((len(palavras_api & set(normalizar_nome(n).split())), n) for n in candidatos), reverse=True)
    if pontos[0][0] > pontos[1][0]:
        return pontos[0][1]
    return None


@dataclass
class ResolucaoAlias:
    alias: str
    status: str                     # "ok" | "ambiguo" | "nao_encontrado"
    escolhido: str | None = None    # nome completo quando status == "ok"
    origem: str | None = None       # "unico" | "confirmado"
    candidatos: list[str] = field(default_factory=list)   # ambíguo: quem bate; não encontrado: sugestões
    motivo: str = ""


def candidatos_alias(alias: str, nomes: list[str]) -> list[str]:
    """Colaboradores cujo nome contém o apelido: o 1º token do apelido prefixa o 1º nome e
    cada token seguinte prefixa alguma outra palavra do nome."""
    tokens = normalizar_nome(alias).split()
    if not tokens:
        return []
    saida = []
    for nome in nomes:
        palavras = normalizar_nome(nome).split()
        if not palavras or not palavras[0].startswith(tokens[0]):
            continue
        resto = palavras[1:]
        if all(any(p.startswith(t) for p in resto) for t in tokens[1:]):
            saida.append(nome)
    return saida


def resolver_alias(alias: str, nomes: list[str], confirmacoes: dict[str, str] | None = None) -> ResolucaoAlias:
    chave = normalizar_nome(alias)
    confirmado = (confirmacoes or {}).get(chave)
    if confirmado:
        if confirmado in nomes:
            return ResolucaoAlias(alias, "ok", confirmado, "confirmado")
        return ResolucaoAlias(alias, "nao_encontrado", None, None, [],
                              f"A confirmação anterior ({confirmado}) não está mais no quadro ativo da unidade.")
    cand = candidatos_alias(alias, nomes)
    if len(cand) == 1:
        return ResolucaoAlias(alias, "ok", cand[0], "unico")
    if len(cand) > 1:
        return ResolucaoAlias(alias, "ambiguo", None, None, cand,
                              f"'{alias}' corresponde a {len(cand)} colaboradores — confirme qual deles.")
    primeiro = normalizar_nome(alias).split()[0] if normalizar_nome(alias) else ""
    sugestoes = [n for n in nomes if primeiro and normalizar_nome(n).startswith(primeiro)]
    return ResolucaoAlias(alias, "nao_encontrado", None, None, sugestoes,
                          f"Nenhum colaborador ativo corresponde a '{alias}'.")

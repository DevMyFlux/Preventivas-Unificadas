"""Persistência (banco) das confirmações humanas de nomes citados em regras de atribuição."""
from sqlalchemy import delete, select

from core.db import agora_utc, sessao
from core.models import RegraResolucao
from core.regras.nomes import normalizar_nome


def carregar_confirmacoes(unidade: str) -> dict[str, str]:
    """{alias normalizado: nome completo confirmado} da unidade."""
    try:
        with sessao() as s:
            linhas = s.scalars(select(RegraResolucao).where(RegraResolucao.unit == unidade)).all()
            return {r.alias: r.funcionario for r in linhas}
    except Exception:  # banco indisponível não pode derrubar a geração de preventivas
        return {}


def confirmar(unidade: str, alias: str, funcionario: str, por: str | None) -> None:
    chave = normalizar_nome(alias)
    with sessao() as s:
        atual = s.scalar(select(RegraResolucao).where(RegraResolucao.unit == unidade, RegraResolucao.alias == chave))
        if atual:
            atual.funcionario, atual.resolved_by, atual.resolved_at = funcionario, por, agora_utc()
        else:
            s.add(RegraResolucao(unit=unidade, alias=chave, funcionario=funcionario, resolved_by=por))


def remover(unidade: str, alias: str) -> int:
    chave = normalizar_nome(alias)
    with sessao() as s:
        return s.execute(delete(RegraResolucao).where(RegraResolucao.unit == unidade,
                                                      RegraResolucao.alias == chave)).rowcount or 0


def versao(unidade: str) -> str:
    """Valor que muda quando uma confirmação é criada/alterada/removida — entra na chave de cache."""
    from sqlalchemy import func
    try:
        with sessao() as s:
            n = s.scalar(select(func.count()).select_from(RegraResolucao).where(RegraResolucao.unit == unidade))
            ultimo = s.scalar(select(func.max(RegraResolucao.resolved_at)).where(RegraResolucao.unit == unidade))
            return f"{n}:{ultimo}"
    except Exception:
        return "indisponivel"

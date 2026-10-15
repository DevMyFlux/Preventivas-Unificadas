"""
HMB — pessoas de plantão por EQUIPE do Neovero.

As rondas diárias nascem no Neovero em nome de uma equipe (ELÉTRICA-DIURNO, ELÉTRICA-NOTURNO, CLIMATIZAÇÃO-DIURNO,
CLIMATIZAÇÃO-NOTURNO). A tela mostra, no lugar do nome da equipe, QUEM está de plantão naquele dia e turno nessa equipe,
segundo a escala vigente (a mesma disponibilidade usada nas recomendações: plantão do dia, sem desligados/bloqueados).
Elétrica = cargos de especialidade Elétrica (eletricista, aux. eletricista/manutenção elétrica);
Climatização = técnico e aux. de climatização/refrigeração. Cargos de gestão/administrativos nunca entram.
"""
from core.regras.limites import especialidade_do_cargo
from units.brasilandia.colaboradores import esta_disponivel


def plantonistas(colab_ativos, equipe_norm: str, dia) -> list[str]:
    """Nomes (ordem alfabética) de quem está de plantão em `dia` na equipe `equipe_norm` (ex.: "eletrica diurno")."""
    especialidade = "Elétrica" if equipe_norm.startswith("eletrica") else "Climatização"
    turno = "Noturno" if "noturno" in equipe_norm else "Diurno"
    if colab_ativos is None or colab_ativos.empty:
        return []
    nomes = [r["funcionario"] for _, r in colab_ativos.iterrows()
             if especialidade_do_cargo(str(r.get("cargo", ""))) == especialidade and str(r.get("turno", "")) == turno
             and esta_disponivel(r, dia)]
    return sorted(nomes)

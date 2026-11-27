"""Motor Brasilândia — delega para motor_base usando disponibilidade por código diário."""
from core.motor_base import indicar_responsavel as _indicar, extrair_ativo, classificar_categoria
from units.brasilandia.colaboradores import esta_disponivel


def indicar_responsavel(
    colaboradores, hist_tipo, hist_ativo, carga, tipo, setor, ativo, data_ref, hora_ref=8, **kwargs,
):
    """Delegação para o motor compartilhado com a disponibilidade da unidade. `kwargs`
    repassa os parâmetros opcionais (exigir_turno, andares_colaborador, carga_alta,
    nomes_permitidos, ocupacao, nomes_obrigatorios, diagnostico)."""
    return _indicar(
        colaboradores, hist_tipo, hist_ativo, carga,
        tipo, setor, ativo, data_ref, hora_ref,
        esta_disponivel_fn=esta_disponivel,
        **kwargs,
    )


__all__ = ["indicar_responsavel", "extrair_ativo", "classificar_categoria"]

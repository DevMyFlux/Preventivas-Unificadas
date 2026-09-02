"""Motor Grand Massif — delega para motor_base usando disponibilidade Par/Ímpar."""
from core.motor_base import indicar_responsavel as _indicar, extrair_ativo, classificar_categoria
from units.grand_massif.colaboradores import esta_disponivel


def indicar_responsavel(
    colaboradores, hist_tipo, hist_ativo, carga, tipo, setor, ativo, data_ref, hora_ref=8,
    exigir_turno=False, andares_colaborador=None, carga_alta=None, nomes_permitidos=None,
):
    return _indicar(
        colaboradores, hist_tipo, hist_ativo, carga,
        tipo, setor, ativo, data_ref, hora_ref,
        esta_disponivel_fn=esta_disponivel,
        exigir_turno=exigir_turno,
        andares_colaborador=andares_colaborador,
        carga_alta=carga_alta,
        nomes_permitidos=nomes_permitidos,
    )


__all__ = ["indicar_responsavel", "extrair_ativo", "classificar_categoria"]

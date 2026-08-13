"""Testes do motor de recomendação compartilhado (core/motor_base.py)."""
from datetime import date

import pandas as pd
import pytest

from core.motor_base import (
    calcular_score,
    classificar_categoria,
    indicar_responsavel,
    is_critico,
)


def test_classificar_categoria_eletrica():
    assert classificar_categoria("Manutenção quadro elétrico", "Bloco A", "") == "Elétrica"


def test_classificar_categoria_refrigeracao():
    assert classificar_categoria("Limpeza do chiller", "", "Ar condicionado split") == "Refrigeração"


def test_classificar_categoria_hidraulico():
    assert classificar_categoria("Troca de hidrômetro", "", "") == "Hidráulico"


def test_classificar_categoria_geral_default():
    assert classificar_categoria("Serviço qualquer sem palavra-chave", "Almoxarifado", "") == "Geral"


def test_is_critico_uti():
    assert is_critico("UTI Adulto") is True
    assert is_critico("Recepção") is False


def test_score_indisponivel_e_sempre_minimo():
    score = calcular_score(
        cargo="Eletricista", categoria="Elétrica", turno_collab="Diurno", hora_os=10,
        setor="Recepção", exp_tipo=5, exp_ativo=5, carga_at=0, disponivel=False,
    )
    assert score == -999


def test_score_cargo_compativel_maior_que_incompativel():
    score_compativel = calcular_score(
        cargo="Eletricista", categoria="Elétrica", turno_collab="Diurno", hora_os=10,
        setor="Recepção", exp_tipo=0, exp_ativo=0, carga_at=0, disponivel=True,
    )
    score_incompativel = calcular_score(
        cargo="Encanador", categoria="Elétrica", turno_collab="Diurno", hora_os=10,
        setor="Recepção", exp_tipo=0, exp_ativo=0, carga_at=0, disponivel=True,
    )
    assert score_compativel > score_incompativel


def test_score_habilidade_compativel_aumenta_score():
    base = calcular_score(
        cargo="Auxiliar de Manutenção", categoria="Elétrica", turno_collab="Diurno", hora_os=10,
        setor="Recepção", exp_tipo=0, exp_ativo=0, carga_at=0, disponivel=True,
    )
    com_habilidade = calcular_score(
        cargo="Auxiliar de Manutenção", categoria="Elétrica", turno_collab="Diurno", hora_os=10,
        setor="Recepção", exp_tipo=0, exp_ativo=0, carga_at=0, disponivel=True,
        habilidades=["aux_eletrica"],
    )
    assert com_habilidade > base


def test_score_habilidade_categoria_diferente_nao_conta():
    base = calcular_score(
        cargo="Auxiliar de Manutenção", categoria="Elétrica", turno_collab="Diurno", hora_os=10,
        setor="Recepção", exp_tipo=0, exp_ativo=0, carga_at=0, disponivel=True,
    )
    com_habilidade_errada = calcular_score(
        cargo="Auxiliar de Manutenção", categoria="Elétrica", turno_collab="Diurno", hora_os=10,
        setor="Recepção", exp_tipo=0, exp_ativo=0, carga_at=0, disponivel=True,
        habilidades=["aux_hidraulica"],
    )
    assert com_habilidade_errada == base


def test_score_turno_correto_soma_pontos():
    diurno_no_turno = calcular_score(
        cargo="Auxiliar de Manutenção", categoria="Geral", turno_collab="Diurno", hora_os=10,
        setor="", exp_tipo=0, exp_ativo=0, carga_at=0, disponivel=True,
    )
    diurno_fora_do_turno = calcular_score(
        cargo="Auxiliar de Manutenção", categoria="Geral", turno_collab="Noturno", hora_os=10,
        setor="", exp_tipo=0, exp_ativo=0, carga_at=0, disponivel=True,
    )
    assert diurno_no_turno > diurno_fora_do_turno


def test_score_carga_penaliza():
    sem_carga = calcular_score(
        cargo="Auxiliar de Manutenção", categoria="Geral", turno_collab="Diurno", hora_os=10,
        setor="", exp_tipo=0, exp_ativo=0, carga_at=0, disponivel=True,
    )
    com_carga = calcular_score(
        cargo="Auxiliar de Manutenção", categoria="Geral", turno_collab="Diurno", hora_os=10,
        setor="", exp_tipo=0, exp_ativo=0, carga_at=3, disponivel=True,
    )
    assert com_carga < sem_carga


def _colaboradores_df():
    return pd.DataFrame([
        {"funcionario": "Ana Eletricista", "cargo": "Eletricista", "turno": "Diurno", "regime": "Fixo"},
        {"funcionario": "Bruno Encanador", "cargo": "Encanador", "turno": "Diurno", "regime": "Fixo"},
    ])


def test_indicar_responsavel_escolhe_cargo_compativel():
    principal, apoio, scores = indicar_responsavel(
        colaboradores=_colaboradores_df(),
        hist_tipo={}, hist_ativo={}, carga={},
        tipo="Manutenção elétrica", setor="Recepção", ativo="Quadro elétrico",
        data_ref=date(2026, 9, 10), hora_ref=10,
    )
    assert principal is not None
    assert principal["nome"] == "Ana Eletricista"


def test_indicar_responsavel_sem_colaboradores_retorna_none():
    principal, apoio, scores = indicar_responsavel(
        colaboradores=pd.DataFrame(), hist_tipo={}, hist_ativo={}, carga={},
        tipo="X", setor="Y", ativo="Z", data_ref=date(2026, 9, 10),
    )
    assert principal is None and apoio is None and scores == {}


def test_indicar_responsavel_respeita_disponibilidade():
    def indisponivel(row, data):
        return False

    principal, apoio, scores = indicar_responsavel(
        colaboradores=_colaboradores_df(),
        hist_tipo={}, hist_ativo={}, carga={},
        tipo="Manutenção elétrica", setor="Recepção", ativo="Quadro elétrico",
        data_ref=date(2026, 9, 10), esta_disponivel_fn=indisponivel,
    )
    assert principal is None

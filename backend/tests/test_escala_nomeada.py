"""Testes da escala nominal obrigatória de coleta (units/grand_massif/escala_nomeada.py).

Escala pedida pela supervisão da HETRIN (email "Ajustes na Lógica de Distribuição de
OS", set/2026):
    Coleta Diária – Medidor de Energia:
        Jussara da Conceição -> Auxiliar, Diurno Ímpar
        Wellington            -> Auxiliar, Noturno Ímpar
        Eduonete              -> Auxiliar, Diurno Par
        Isabel                 -> Auxiliar, Noturno Par
    Coleta Diária – Hidrômetro:
        Jussara da Conceição -> Turno Ímpar
        Eduonete              -> Turno Par
"""
from datetime import date

import pandas as pd
import pytest

from core.motor_base import indicar_responsavel
from units.grand_massif.escala_nomeada import nomes_permitidos_coleta


# nomes_permitidos_coleta() filtra só por PARIDADE — turno já é responsabilidade do
# gate genérico de turno (exigir_turno em indicar_responsavel, via detectar_turno do
# próprio nome do plano), então pra uma paridade "Ímpar" o conjunto retornado inclui
# tanto o diurno quanto o noturno daquele dia (Jussara e Wellington); é o gate de
# turno, combinado com esse conjunto, que resolve pra 1 pessoa só (ver
# core/motor_base.py::indicar_responsavel).
@pytest.mark.parametrize("nome_plano, dia_par, esperado", [
    ("COLETA DIÁRIA MEDIDOR - DIURNO - D1", "Ímpar", {"Jussara da Conceição Cruz", "Wellington de Souza Brito"}),
    ("COLETA DIÁRIA MEDIDOR - NOTURNO - N1", "Ímpar", {"Jussara da Conceição Cruz", "Wellington de Souza Brito"}),
    ("COLETA DIÁRIA MEDIDOR - DIURNO - D2", "Par", {"Eduonete Lopes dos Santos", "Isabel Alves Dias"}),
    ("COLETA DIÁRIA MEDIDOR - NOTURNO - N2", "Par", {"Eduonete Lopes dos Santos", "Isabel Alves Dias"}),
])
def test_nomes_permitidos_medidor(nome_plano, dia_par, esperado):
    assert nomes_permitidos_coleta(nome_plano, dia_par) == esperado


@pytest.mark.parametrize("nome_plano, dia_par, esperado", [
    ("COLETA DIÁRIA HIDRÔMETRO -DIURNO - D1", "Ímpar", {"Jussara da Conceição Cruz"}),
    ("COLETA DIÁRIA HIDRÔMETRO -DIURNO - D2", "Par", {"Eduonete Lopes dos Santos"}),
])
def test_nomes_permitidos_hidrometro(nome_plano, dia_par, esperado):
    assert nomes_permitidos_coleta(nome_plano, dia_par) == esperado


@pytest.mark.parametrize("nome_plano", [
    "PM - RONDA ILUMINAÇÃO/TOMADAS - NOITE - N1",
    "PM MENSAL - SPLIT - HETRIN",
    "PM RONDA PERIÓDICA - RÉGUAS DE GASES MEDICINAIS - 1º ANDAR",
    "",
])
def test_nomes_permitidos_none_pra_planos_fora_das_duas_familias(nome_plano):
    """None = sem restrição — o motor não deve filtrar nada por causa desse plano."""
    assert nomes_permitidos_coleta(nome_plano, "Par") is None


def test_nomes_permitidos_case_insensitive_e_sem_acento():
    resultado = nomes_permitidos_coleta("coleta diária medidor - diurno - d1", "Ímpar")
    assert resultado == {"Jussara da Conceição Cruz", "Wellington de Souza Brito"}


def test_medidor_nao_confunde_com_hidrometro():
    """Mesmo os dois compartilhando 'coleta diária', cada família tem sua própria
    tabela — o conjunto de hidrômetro (só 2 pessoas, sem variante noturna) não pode
    vazar pro medidor (4 pessoas, com variante noturna) por engano."""
    medidor = nomes_permitidos_coleta("COLETA DIÁRIA MEDIDOR - NOTURNO - N2", "Par")
    hidrometro = nomes_permitidos_coleta("COLETA DIÁRIA HIDRÔMETRO -DIURNO - D2", "Par")
    assert medidor == {"Eduonete Lopes dos Santos", "Isabel Alves Dias"}
    assert hidrometro == {"Eduonete Lopes dos Santos"}
    assert medidor != hidrometro


# ── Integração com indicar_responsavel — resolve pra 1 pessoa só via cargo+turno ──
# Bug real reportado: "COLETA DIÁRIA MEDIDOR - NOTURNO - N2" (02/09/2026, dia PAR)
# recomendava Salem Abreu da Silva Junior, eletricista só diurno. Simula o pool
# completo das 4 pessoas nomeadas + um auxiliar genérico que não deveria ganhar.

def _colab_coleta():
    return pd.DataFrame([
        {"funcionario": "Jussara da Conceição Cruz", "cargo": "Aux. Eletricista", "turno": "Diurno", "regime": "Fixo"},
        {"funcionario": "Wellington de Souza Brito", "cargo": "Aux. Eletricista", "turno": "Noturno", "regime": "Fixo"},
        {"funcionario": "Eduonete Lopes dos Santos", "cargo": "Aux. Eletricista", "turno": "Diurno", "regime": "Fixo"},
        {"funcionario": "Isabel Alves Dias", "cargo": "Aux. Manutenção / Climatização", "turno": "Noturno", "regime": "Fixo"},
        {"funcionario": "Outro Auxiliar Qualquer", "cargo": "Aux. Manutenção", "turno": "Noturno", "regime": "Fixo"},
    ])


def test_integracao_medidor_noturno_par_recomenda_isabel():
    dia_par = "Par"
    nome_plano = "COLETA DIÁRIA MEDIDOR - NOTURNO - N2"
    tipo_classif = f"Preventiva {nome_plano} CENTRO DE COMANDO DA OPERAÇÃO - CCO"
    nomes = nomes_permitidos_coleta(nome_plano, dia_par)

    principal, _, _ = indicar_responsavel(
        _colab_coleta(), {}, {}, {}, tipo_classif, "", "", date(2026, 9, 2),
        hora_ref=20, exigir_turno=True, nomes_permitidos=nomes,
    )
    assert principal["nome"] == "Isabel Alves Dias"


def test_integracao_medidor_diurno_impar_recomenda_jussara():
    dia_par = "Ímpar"
    nome_plano = "COLETA DIÁRIA MEDIDOR - DIURNO - D1"
    tipo_classif = f"Preventiva {nome_plano} CENTRO DE COMANDO DA OPERAÇÃO - CCO"
    nomes = nomes_permitidos_coleta(nome_plano, dia_par)

    principal, _, _ = indicar_responsavel(
        _colab_coleta(), {}, {}, {}, tipo_classif, "", "", date(2026, 9, 1),
        hora_ref=8, exigir_turno=True, nomes_permitidos=nomes,
    )
    assert principal["nome"] == "Jussara da Conceição Cruz"


def test_integracao_hidrometro_diurno_impar_recomenda_jussara():
    """Bug real confirmado por validação com dado real (setembro/2026 inteiro): ANTES
    do fix de prioridade 'coleta'>'hidrômetro', 28 de 28 ocorrências de Hidrômetro no
    mês foram pra outra pessoa (não Jussara/Eduonete), porque classificar_categoria
    classificava o plano como 'Hidráulico' e excluía o cargo real delas (Aux.
    Eletricista) do cargo compatível ANTES do gate de escala nomeada sequer rodar."""
    dia_par = "Ímpar"
    nome_plano = "COLETA DIÁRIA HIDRÔMETRO -DIURNO - D1"
    tipo_classif = f"Preventiva {nome_plano} CENTRO DE COMANDO DA OPERAÇÃO - CCO"
    nomes = nomes_permitidos_coleta(nome_plano, dia_par)

    principal, _, scores = indicar_responsavel(
        _colab_coleta(), {}, {}, {}, tipo_classif, "", "", date(2026, 9, 1),
        hora_ref=8, exigir_turno=True, nomes_permitidos=nomes,
    )
    assert scores["Jussara da Conceição Cruz"]["funcao_compativel"] is True
    assert principal["nome"] == "Jussara da Conceição Cruz"


# ── Bug real: pessoa nomeada bloqueada não pode "travar" o pool no turno errado ──
# Wellington de Souza Brito (Noturno, Ímpar, Medidor) está bloqueado (NR-10
# pendente). Validação com dado real (set/2026 inteiro) confirmou que, com o gate de
# escala nomeada rodando ANTES do gate de turno, o pool ficava reduzido a {Jussara}
# (a única pessoa nomeada pra Ímpar disponível, já que Wellington nunca aparece em
# `disponiveis`) ANTES do turno ter chance de agir — e como o gate de turno também é
# soft (só restringe se não esvaziar), ele ficava impotente e Jussara (Diurno) era
# recomendada pras 14 ocorrências noturnas de Medidor N1 nos dias ímpares. Corrigido
# invertendo a ordem: turno agora roda ANTES da escala nomeada.

def test_wellington_bloqueado_nao_forca_jussara_em_turno_noturno():
    colab = pd.DataFrame([
        {"funcionario": "Jussara da Conceição Cruz", "cargo": "Aux. Eletricista", "turno": "Diurno", "regime": "Fixo"},
        {"funcionario": "Outro Noturno Disponível", "cargo": "Eletricista", "turno": "Noturno", "regime": "Fixo"},
    ])

    def esta_disponivel(row, data):
        # Wellington nem chega a aparecer no DataFrame — simula o bloqueio real
        # (bloqueado = nunca disponível, já filtrado antes de chegar em indicar_responsavel).
        return True

    dia_par = "Ímpar"
    nome_plano = "COLETA DIÁRIA MEDIDOR - NOTURNO - N1"
    tipo_classif = f"Preventiva {nome_plano} CENTRO DE COMANDO DA OPERAÇÃO - CCO"
    nomes = nomes_permitidos_coleta(nome_plano, dia_par)  # {Jussara, Wellington} — Wellington nunca disponível
    assert "Wellington de Souza Brito" in nomes

    principal, _, scores = indicar_responsavel(
        colab, {}, {}, {}, tipo_classif, "", "", date(2026, 9, 3),
        hora_ref=20, exigir_turno=True, nomes_permitidos=nomes,
        esta_disponivel_fn=esta_disponivel,
    )
    # nunca pode recomendar Jussara (Diurno) pra uma ocorrência noturna só porque ela
    # é a única nomeada disponível — o turno tem que vencer, mesmo sem nome batendo
    assert principal["nome"] == "Outro Noturno Disponível"
    assert scores["Jussara da Conceição Cruz"]["turno_compativel"] is False

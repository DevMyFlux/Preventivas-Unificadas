"""Testes do motor de recomendação compartilhado (core/motor_base.py)."""
from datetime import date

import pandas as pd
import pytest

from core.motor_base import (
    _cargo_compativel,
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


# ── Bug corrigido: carga acumulada não pode excluir gente disponível ────────
# Antes do fix, `disponiveis` filtrava por `score > -999`, o mesmo sentinel que
# calcular_score usa para "indisponível". Como a penalidade de carga não tem teto,
# depois de várias dezenas de atribuições numa geração de preventivas de um mês
# inteiro, o score de alguém DISPONÍVEL também cruzava -999 e era excluído por
# engano — confirmado com dados reais: 1440 de 2232 preventivas de Hetrin/Set-2026
# ficavam sem recomendação por esse motivo, mesmo com os 17 colaboradores aptos.

def test_indicar_responsavel_nao_exclui_disponivel_com_carga_alta():
    carga_alta = {"Ana Eletricista": 100, "Bruno Encanador": 100}  # 100*25=2500 > qualquer score possível
    principal, apoio, scores = indicar_responsavel(
        colaboradores=_colaboradores_df(),
        hist_tipo={}, hist_ativo={}, carga=carga_alta,
        tipo="Manutenção elétrica", setor="Recepção", ativo="Quadro elétrico",
        data_ref=date(2026, 9, 10), hora_ref=10,
    )
    assert principal is not None
    assert scores["Ana Eletricista"]["score"] < -999  # o score real ainda é bem negativo...
    assert principal["nome"] == "Ana Eletricista"      # ...mas ainda é escolhida, por ser a melhor disponível


def test_indicar_responsavel_prefere_menor_carga_em_empate_de_score():
    colab = pd.DataFrame([
        {"funcionario": "Ana", "cargo": "Eletricista", "turno": "Diurno", "regime": "Fixo"},
        {"funcionario": "Bia", "cargo": "Eletricista", "turno": "Diurno", "regime": "Fixo"},
    ])
    principal, apoio, scores = indicar_responsavel(
        colaboradores=colab, hist_tipo={}, hist_ativo={},
        carga={"Ana": 3, "Bia": 1},  # mesmo score técnico, Bia tem menos carga
        tipo="Manutenção elétrica", setor="Recepção", ativo="Quadro elétrico",
        data_ref=date(2026, 9, 10), hora_ref=10,
    )
    assert principal["nome"] == "Bia"


def test_indicar_responsavel_score_maior_vence_mesmo_com_mais_carga_moderada():
    """Uma pequena diferença de carga não deve derrubar quem tem vantagem técnica clara."""
    colab = pd.DataFrame([
        {"funcionario": "Especialista", "cargo": "Eletricista", "turno": "Diurno", "regime": "Fixo"},
        {"funcionario": "Generalista", "cargo": "Auxiliar de Manutenção", "turno": "Diurno", "regime": "Fixo"},
    ])
    principal, _, _ = indicar_responsavel(
        colaboradores=colab, hist_tipo={}, hist_ativo={},
        carga={"Especialista": 1, "Generalista": 0},
        tipo="Manutenção elétrica", setor="Recepção", ativo="Quadro elétrico",
        data_ref=date(2026, 9, 10), hora_ref=10,
    )
    assert principal["nome"] == "Especialista"


def test_carga_dinamica_redistribui_ao_longo_de_varias_os():
    """Simula o efeito cascata da seção 10 do pedido: sem redistribuir carga, a
    mesma pessoa venceria as N atribuições seguidas. Incrementando carga a cada
    escolha (como as rotas fazem), a recomendação deve variar."""
    colab = pd.DataFrame([
        {"funcionario": "Ana", "cargo": "Eletricista", "turno": "Diurno", "regime": "Fixo"},
        {"funcionario": "Bruno", "cargo": "Eletricista", "turno": "Diurno", "regime": "Fixo"},
        {"funcionario": "Carla", "cargo": "Eletricista", "turno": "Diurno", "regime": "Fixo"},
    ])
    carga = {}
    escolhidos = []
    for _ in range(6):
        principal, _, _ = indicar_responsavel(
            colaboradores=colab, hist_tipo={}, hist_ativo={}, carga=carga,
            tipo="Manutenção elétrica", setor="Recepção", ativo="Quadro elétrico",
            data_ref=date(2026, 9, 10), hora_ref=10,
        )
        escolhidos.append(principal["nome"])
        carga[principal["nome"]] = carga.get(principal["nome"], 0) + 1

    # com 3 pessoas tecnicamente empatadas e 6 OS, cada uma deve aparecer pelo
    # menos uma vez — não pode ser sempre a mesma (efeito cascata)
    assert len(set(escolhidos)) == 3


# ── Cargo abreviado (planilha nova da HMB usa "Aux." em vez de "Auxiliar de") ────

@pytest.mark.parametrize("cargo", [
    "Auxiliar de Manutenção",
    "Auxiliar de Manutenção/Climatização",
    "Aux. Manutenção",
    "Aux. Manutenção / Climatização",
    "Aux Manutenção",
])
def test_cargo_auxiliar_reconhece_forma_abreviada(cargo):
    assert _cargo_compativel(cargo.lower(), "Hidráulico") is True


# ── Bug corrigido: balanceamento não pode fazer cargo incompatível ganhar de ────
# ── cargo compatível, mesmo com muita carga acumulada no compatível ─────────────
# Confirmado com dado real (Hetrin, categoria Inspeção): depois de várias dezenas
# de atribuições numa geração de preventivas, técnicos/eletricistas disponíveis
# empatavam em score com uma gestora administrativa (cargo incompatível, mas nunca
# escalada antes = carga sempre 0) — e o desempate por menor carga escolhia a
# gestora. Isso viola a regra: "balanceamento nunca deve fazer um funcionário
# tecnicamente inadequado ganhar de um funcionário tecnicamente qualificado".

def test_balanceamento_nao_supera_incompatibilidade_de_cargo():
    colab = pd.DataFrame([
        {"funcionario": "Eletricista Sobrecarregado", "cargo": "Eletricista", "turno": "Diurno", "regime": "Fixo"},
        {"funcionario": "Gestora Nunca Escalada", "cargo": "Gestora Local / Engenheira", "turno": "Administrativo", "regime": "Fixo"},
    ])
    principal, _, scores = indicar_responsavel(
        colaboradores=colab, hist_tipo={}, hist_ativo={},
        carga={"Eletricista Sobrecarregado": 10, "Gestora Nunca Escalada": 0},  # -250 de penalidade no eletricista
        tipo="Manutenção elétrica", setor="Recepção", ativo="Quadro elétrico",
        data_ref=date(2026, 9, 10), hora_ref=10,
    )
    # mesmo com o eletricista deeply penalizado por carga e a gestora em carga zero,
    # o eletricista (tecnicamente apto) tem que vencer
    assert principal["nome"] == "Eletricista Sobrecarregado"
    assert scores["Gestora Nunca Escalada"]["funcao_compativel"] is False
    assert scores["Eletricista Sobrecarregado"]["funcao_compativel"] is True


def test_ninguem_compativel_ainda_assim_recomenda_alguem():
    """Sem candidato compatível nenhum, o motor deve preferir indicar o melhor
    disponível a devolver 'sem candidato' — só não pode preferir o incompatível
    quando existe opção melhor (coberto pelo teste acima)."""
    colab = pd.DataFrame([
        {"funcionario": "Gestora", "cargo": "Gestora Local / Engenheira", "turno": "Administrativo", "regime": "Fixo"},
    ])
    principal, _, _ = indicar_responsavel(
        colaboradores=colab, hist_tipo={}, hist_ativo={}, carga={},
        tipo="Manutenção elétrica", setor="Recepção", ativo="Quadro elétrico",
        data_ref=date(2026, 9, 10), hora_ref=10,
    )
    assert principal is not None
    assert principal["nome"] == "Gestora"

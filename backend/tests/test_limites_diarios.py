"""
Limites diários de ordens por colaborador (5.3): Elétrica ≤ 14, Climatização ≤ 10.

O limite é aplicado DENTRO do motor de recomendação (não só na tela): estes testes chamam
`indicar_responsavel` diretamente.
"""
from datetime import date

from core.motor_base import indicar_responsavel
from core.regras.limites import (
    LIMITES_DIARIOS, OcupacaoDiaria, chave_os, chave_prevista, especialidade_do_cargo, limite_do_cargo,
)
from tests.fakes import colaboradores_df

DIA = date(2026, 10, 14)


def _elet(*nomes):
    return colaboradores_df([{"funcionario": n, "cargo": "Eletricista"} for n in nomes])


def _recomendar(colab, ocupacao, tipo="Manutenção elétrica quadro", diag=None, dia=DIA, **kw):
    return indicar_responsavel(colab, {}, {}, {}, tipo, "Bloco A", "Quadro elétrico", dia, 10,
                               ocupacao=ocupacao, diagnostico=diag if diag is not None else {}, **kw)


def test_limites_configurados_conforme_pedido():
    assert LIMITES_DIARIOS == {"Elétrica": 14, "Climatização": 10}


def test_especialidade_pelo_cargo():
    assert especialidade_do_cargo("Eletricista") == "Elétrica"
    assert especialidade_do_cargo("Aux. Eletricista") == "Elétrica"
    assert especialidade_do_cargo("Aux. Manutenção Elétrica") == "Elétrica"
    assert especialidade_do_cargo("Técnico de Climatização") == "Climatização"
    assert especialidade_do_cargo("Aux. Manutenção / Climatização") == "Climatização"
    assert especialidade_do_cargo("Encanador") is None
    assert limite_do_cargo("Eletricista") == 14
    assert limite_do_cargo("Técnico de Climatização") == 10
    assert limite_do_cargo("Encanador") is None


def test_eletricista_chega_a_14_e_nao_passa():
    colab = _elet("Eletricista Único")
    oc = OcupacaoDiaria()
    for i in range(14):
        principal, _, _ = _recomendar(colab, oc)
        assert principal and principal["nome"] == "Eletricista Único", f"ordem {i + 1} deveria caber"
        oc.registrar(principal["nome"], DIA, chave_prevista(1, i, DIA))
    assert oc.total("Eletricista Único", DIA) == 14
    diag = {}
    principal, _, _ = _recomendar(colab, oc, diag=diag)
    assert principal is None, "a 15ª ordem não pode ser atribuída em silêncio"
    assert diag["motivo"] == "limite_diario"


def test_climatizacao_chega_a_10_e_nao_passa():
    colab = colaboradores_df([{"funcionario": "Clima 1", "cargo": "Técnico de Climatização"}])
    oc = OcupacaoDiaria()
    for i in range(10):
        p, _, _ = _recomendar(colab, oc, tipo="Limpeza do split")
        assert p is not None
        oc.registrar("Clima 1", DIA, chave_prevista(2, i, DIA))
    diag = {}
    p, _, _ = _recomendar(colab, oc, tipo="Limpeza do split", diag=diag)
    assert p is None and diag["motivo"] == "limite_diario"


def test_quando_um_atinge_o_limite_busca_outro_elegivel_e_compativel():
    colab = _elet("Cheio", "Livre")
    oc = OcupacaoDiaria()
    for i in range(14):
        oc.registrar("Cheio", DIA, chave_os(1000 + i))
    principal, apoio, scores = _recomendar(colab, oc)
    assert principal["nome"] == "Livre"
    assert apoio is None  # "Cheio" saiu do conjunto de candidatos
    assert scores["Cheio"]["com_vaga"] is False and scores["Cheio"]["ocupacao_dia"] == 14


def test_limite_esgotado_nao_empurra_para_cargo_incompativel():
    """Todos os eletricistas cheios + um técnico de climatização livre: a ordem elétrica NÃO
    pode ir para o climatizador — sinaliza intervenção."""
    colab = colaboradores_df([
        {"funcionario": "Eletricista Cheio", "cargo": "Eletricista"},
        {"funcionario": "Clima Livre", "cargo": "Técnico de Climatização"},
    ])
    oc = OcupacaoDiaria()
    for i in range(14):
        oc.registrar("Eletricista Cheio", DIA, chave_os(2000 + i))
    diag = {}
    principal, _, _ = _recomendar(colab, oc, diag=diag)
    assert principal is None
    assert diag["motivo"] == "limite_diario"


def test_mesma_ordem_nao_e_contada_duas_vezes():
    oc = OcupacaoDiaria()
    assert oc.registrar("Fulano", DIA, chave_os(123)) is True
    assert oc.registrar("Fulano", DIA, chave_os(123)) is False
    assert oc.total("Fulano", DIA) == 1


def test_contagem_e_por_dia_nao_acumulada_no_mes():
    colab = _elet("Eletricista Único")
    oc = OcupacaoDiaria()
    for i in range(14):
        oc.registrar("Eletricista Único", DIA, chave_os(3000 + i))
    # no dia seguinte a contagem recomeça
    proximo = date(2026, 10, 15)
    principal, _, _ = _recomendar(colab, oc, dia=proximo)
    assert principal is not None and principal["nome"] == "Eletricista Único"


def test_cargo_sem_especialidade_nao_tem_teto():
    colab = colaboradores_df([{"funcionario": "Encanador", "cargo": "Encanador"}])
    oc = OcupacaoDiaria()
    for i in range(50):
        oc.registrar("Encanador", DIA, chave_os(4000 + i))
    principal, _, _ = indicar_responsavel(colab, {}, {}, {}, "Reparo hidráulico", "Bloco", "Bomba", DIA, 10, ocupacao=oc)
    assert principal is not None


def test_sem_ocupacao_informada_comportamento_antigo_preservado():
    colab = _elet("Eletricista Único")
    principal, _, _ = indicar_responsavel(colab, {}, {}, {"Eletricista Único": 99}, "Manutenção elétrica", "Bloco",
                                          "Quadro", DIA, 10)
    assert principal is not None


def test_regra_nominal_respeita_limite_diario():
    colab = _elet("Iranildo", "Outro")
    oc = OcupacaoDiaria()
    for i in range(14):
        oc.registrar("Iranildo", DIA, chave_os(5000 + i))
    diag = {}
    principal, _, _ = _recomendar(colab, oc, diag=diag, nomes_obrigatorios={"Iranildo"})
    assert principal is None
    assert diag["motivo"] == "regra_nominal_limite_diario"

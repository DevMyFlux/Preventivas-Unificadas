"""
5.1  Colaboradores desligados não recebem OS a partir da data de desligamento (histórico preservado).
5.2  Quem gerencia/administra nunca é tratado como executante (causa-raiz de "OS em nome do gestor").
"""
import json
import os
from datetime import date

import pytest

from core import colaboradores_overlay as overlay
from core.motor_base import indicar_responsavel
from core.regras import elegibilidade as eleg
from tests.fakes import colaboradores_df

HMB_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "hmb")

# Desligamentos informados pela supervisão (HMB) — e-mail de feedback, set/2026
DESLIGADOS_HMB = {
    "Ronaldo Manoel dos Santos": date(2026, 9, 8),
    "Caio Cezar Santos Pereira": date(2026, 9, 18),
    "Lesle Venini Izidoro dos Santos": date(2026, 9, 26),
}


# ── dados reais versionados: as três datas estão no overlay da HMB ───────────

def test_overlay_da_hmb_registra_os_tres_desligamentos_com_as_datas_do_email():
    dados = overlay.carregar(HMB_DIR)
    for nome, data in DESLIGADOS_HMB.items():
        entrada = dados[nome.upper()]
        assert entrada["data_desligamento"] == data.isoformat(), nome
        assert entrada["nome"] == nome


def test_overlay_nao_marca_status_do_mes_inteiro_para_nao_apagar_dias_trabalhados():
    """Só a data: até o dia anterior ao desligamento a pessoa ainda era elegível."""
    dados = overlay.carregar(HMB_DIR)
    for nome in DESLIGADOS_HMB:
        assert "status" not in dados[nome.upper()]


# ── comportamento do motor com a planilha de setembro (onde eles constam) ────

def _sala(nome, cargo, desligamento, **extra):
    return {"funcionario": nome, "cargo": cargo, "data_desligamento": desligamento.isoformat(), **extra}


@pytest.mark.parametrize("nome,cargo,data", [
    ("Ronaldo Manoel dos Santos", "Aux. Manutenção Elétrica", date(2026, 9, 8)),
    ("Caio Cezar Santos Pereira", "Eletricista", date(2026, 9, 18)),
    ("Lesle Venini Izidoro dos Santos", "Técnico de Climatização", date(2026, 9, 26)),
])
def test_elegivel_ate_a_vespera_e_inelegivel_a_partir_da_data_de_desligamento(nome, cargo, data):
    df = colaboradores_df([_sala(nome, cargo, data)])
    row = df.iloc[0]
    from datetime import timedelta
    assert eleg.elegivel(row, data - timedelta(days=1)) is True
    assert eleg.elegivel(row, data) is False
    assert eleg.elegivel(row, data + timedelta(days=1)) is False
    assert eleg.elegivel(row, data + timedelta(days=40)) is False
    assert eleg.motivo_inelegibilidade(row, data) == eleg.MOTIVO_FORA_DO_VINCULO


def test_motor_nao_recomenda_desligado_depois_da_data_e_recomenda_antes():
    df = colaboradores_df([_sala("Caio Cezar Santos Pereira", "Eletricista", date(2026, 9, 18))])
    antes = indicar_responsavel(df, {}, {}, {}, "Manutenção elétrica", "Bloco", "Quadro", date(2026, 9, 17), 10)[0]
    depois = indicar_responsavel(df, {}, {}, {}, "Manutenção elétrica", "Bloco", "Quadro", date(2026, 9, 18), 10)[0]
    assert antes is not None and antes["nome"] == "Caio Cezar Santos Pereira"
    assert depois is None


def test_motor_prefere_outro_eletricista_quando_um_foi_desligado():
    df = colaboradores_df([
        _sala("Caio Cezar Santos Pereira", "Eletricista", date(2026, 9, 18)),
        {"funcionario": "Outro Eletricista", "cargo": "Eletricista"},
    ])
    principal, apoio, scores = indicar_responsavel(df, {}, {}, {}, "Manutenção elétrica", "Bloco", "Quadro",
                                                   date(2026, 9, 25), 10)
    assert principal["nome"] == "Outro Eletricista" and apoio is None
    assert scores["Caio Cezar Santos Pereira"]["disponivel"] is False


def test_status_desligado_e_validado_no_proprio_motor_nao_so_na_rota():
    """Mesmo sem o pré-filtro da camada de rota, quem está Desligado nunca é recomendado."""
    df = colaboradores_df([{"funcionario": "Saiu", "cargo": "Eletricista", "status": "Desligado"}])
    assert indicar_responsavel(df, {}, {}, {}, "Manutenção elétrica", "B", "Q", date(2026, 9, 10), 10)[0] is None


def test_esta_disponivel_das_unidades_aplica_a_elegibilidade_central():
    from units.brasilandia.colaboradores import esta_disponivel as disp_hmb
    from units.grand_massif.colaboradores import esta_disponivel as disp_gm
    df = colaboradores_df([
        {"funcionario": "A", "cargo": "Eletricista", "status": "Desligado"},
        {"funcionario": "B", "cargo": "Supervisor de Manutenção"},
        {"funcionario": "C", "cargo": "Eletricista", "data_desligamento": "2026-09-10"},
    ])
    for fn in (disp_hmb, disp_gm):
        assert fn(df.iloc[0], date(2026, 9, 5)) is False   # status Desligado
        assert fn(df.iloc[1], date(2026, 9, 5)) is False   # gestão não executa OS
        assert fn(df.iloc[2], date(2026, 9, 10)) is False  # no dia do desligamento
        assert fn(df.iloc[2], date(2026, 9, 9)) is True    # na véspera ainda elegível


def test_loader_preserva_historico_com_linha_de_desligado_fora_da_escala(monkeypatch, tmp_path):
    """Quem saiu e não consta mais na escala do mês continua no cadastro (Desligado, com data)."""
    import pandas as pd
    base = colaboradores_df([{"funcionario": "Ativo Presente", "cargo": "Eletricista"}])
    (tmp_path / "colaboradores_overlay.json").write_text(json.dumps({
        "FULANO DESLIGADO": {"nome": "Fulano Desligado", "cargo": "Eletricista", "turno": "Diurno",
                             "data_desligamento": "2026-09-08"},
    }), encoding="utf-8")
    df = overlay.aplicar_overlay(base, str(tmp_path))
    fantasma = df[df["funcionario"] == "Fulano Desligado"].iloc[0]
    assert fantasma["status"] == "Desligado" and fantasma["data_desligamento"] == "2026-09-08"
    assert bool(fantasma["fora_da_escala"]) is True
    assert not df[df["funcionario"] == "Ativo Presente"].iloc[0]["fora_da_escala"]
    assert isinstance(fantasma["dias_plantao"], dict)
    # nada de NaN vazando para o JSON
    assert pd.isna(df["aviso"]).sum() == 0 or df["aviso"].map(lambda v: v is None or isinstance(v, str)).all()


def test_dados_reais_hmb_carregados_trazem_os_tres_desligados_como_historico():
    from units.brasilandia import colaboradores as hmb
    hmb.invalidar_cache()
    df = hmb.carregar_colaboradores()
    for nome, data in DESLIGADOS_HMB.items():
        achados = df[df["funcionario"] == nome]
        assert len(achados) == 1, nome
        linha = achados.iloc[0]
        assert linha["data_desligamento"] == data.isoformat()
        assert eleg.elegivel(linha, date(2026, 10, 14)) is False
    hmb.invalidar_cache()


# ── 5.2: gestão nunca é executante ───────────────────────────────────────────

@pytest.mark.parametrize("cargo", [
    "Supervisor de Manutenção", "Gerente de Equipe / Engenheira", "Gestora Local / Engenheira",
    "Auxiliar Administrativo", "Analista de Dados", "Coordenador de Manutenção",
])
def test_cargos_de_gestao_nao_executam_os(cargo):
    assert eleg.cargo_executa_os(cargo) is False
    assert eleg.cargo_e_gestao(cargo) is True


@pytest.mark.parametrize("cargo", [
    "Eletricista", "Aux. Eletricista", "Técnico de Climatização", "Aux. Manutenção / Climatização",
    "Aux. Manutenção Elétrica", "Encanador",
])
def test_cargos_de_campo_executam_os(cargo):
    assert eleg.cargo_executa_os(cargo) is True


def test_supervisor_de_manutencao_nao_e_recomendado_em_ronda_de_inspecao():
    """Reprodução do bug real da HMB: 'Supervisor de Manutenção' casava com 'supervisor' em
    _CARGO_TECNICO e recebia 100% das tarefas de categoria Inspeção quando nenhum técnico
    estava sobrecarregado (45 de 45 em simulação com a escala real)."""
    df = colaboradores_df([
        {"funcionario": "William de Souza Lobo", "cargo": "Supervisor de Manutenção", "turno": "Administrativo"},
        {"funcionario": "Eletricista A", "cargo": "Eletricista"},
    ])
    carga = {"Eletricista A": 40}   # muito carregado: antes, o supervisor (carga 0) ganhava
    for _ in range(20):
        principal, _, _ = indicar_responsavel(df, {}, {}, carga, "PM - RONDA DIÁRIA", "Sala", "Equip", date(2026, 10, 14), 10)
        assert principal["nome"] == "Eletricista A"


def test_com_so_gestao_disponivel_o_resultado_e_sem_candidato_para_revisao():
    df = colaboradores_df([{"funcionario": "Gerente", "cargo": "Gerente de Equipe / Engenheira"}])
    diag = {}
    principal, _, _ = indicar_responsavel(df, {}, {}, {}, "PM algo", "Sala", "Equip", date(2026, 10, 14), 10, diagnostico=diag)
    assert principal is None and diag["motivo"] == "nenhum_elegivel"


def test_usuario_logado_nunca_e_confundido_com_executante():
    """O módulo de recomendação não conhece o usuário autenticado: a assinatura de
    `indicar_responsavel` não recebe nenhuma identidade de sessão, e o executante só pode sair
    do cadastro de colaboradores."""
    import inspect
    params = set(inspect.signature(indicar_responsavel).parameters)
    assert not params & {"user", "usuario", "g", "session", "sessao", "login"}
    df = colaboradores_df([{"funcionario": "Eletricista A", "cargo": "Eletricista"}])
    principal, _, _ = indicar_responsavel(df, {}, {}, {}, "Manutenção elétrica", "S", "E", date(2026, 10, 14), 10)
    assert principal["nome"] in set(df["funcionario"])

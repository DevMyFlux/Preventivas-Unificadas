"""Testes da persistência de status/habilidades (core/colaboradores_overlay.py).
Usa tmp_path para nunca tocar nos dados reais do projeto."""
import pandas as pd

from core import colaboradores_overlay as overlay


def test_carregar_sem_arquivo_retorna_vazio(tmp_path):
    assert overlay.carregar(str(tmp_path)) == {}


def test_set_status_persiste_e_normaliza_nome(tmp_path):
    d = str(tmp_path)
    overlay.set_status(d, "  joão da silva  ", "Desligado")
    dados = overlay.carregar(d)
    assert dados["JOÃO DA SILVA"]["status"] == "Desligado"


def test_set_status_invalido_levanta_erro(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        overlay.set_status(str(tmp_path), "Fulano", "Aposentado")


def test_adicionar_e_remover_habilidade(tmp_path):
    d = str(tmp_path)
    habilidades = overlay.adicionar_habilidade(d, "Maria", "tec_eletrica")
    assert habilidades == ["tec_eletrica"]

    habilidades = overlay.adicionar_habilidade(d, "Maria", "tec_eletrica")
    assert habilidades == ["tec_eletrica"], "não deve duplicar habilidade já presente"

    habilidades = overlay.adicionar_habilidade(d, "Maria", "aux_hidraulica")
    assert set(habilidades) == {"tec_eletrica", "aux_hidraulica"}

    habilidades = overlay.remover_habilidade(d, "Maria", "tec_eletrica")
    assert habilidades == ["aux_hidraulica"]


def test_aplicar_overlay_default_ativo_sem_habilidades(tmp_path):
    df = pd.DataFrame([{"funcionario": "Pedro", "cargo": "Técnico"}])
    resultado = overlay.aplicar_overlay(df, str(tmp_path))
    assert resultado.iloc[0]["status"] == "Ativo"
    assert resultado.iloc[0]["habilidades"] == []


def test_aplicar_overlay_reflete_status_e_habilidades_salvos(tmp_path):
    d = str(tmp_path)
    overlay.set_status(d, "Pedro", "Desligado")
    overlay.adicionar_habilidade(d, "Pedro", "tec_hidraulica")

    df = pd.DataFrame([
        {"funcionario": "Pedro", "cargo": "Técnico"},
        {"funcionario": "Ana", "cargo": "Auxiliar"},
    ])
    resultado = overlay.aplicar_overlay(df, d)

    pedro = resultado[resultado["funcionario"] == "Pedro"].iloc[0]
    ana = resultado[resultado["funcionario"] == "Ana"].iloc[0]
    assert pedro["status"] == "Desligado"
    assert pedro["habilidades"] == ["tec_hidraulica"]
    assert ana["status"] == "Ativo"
    assert ana["habilidades"] == []


def test_aplicar_overlay_nao_muta_dataframe_original(tmp_path):
    df = pd.DataFrame([{"funcionario": "Pedro", "cargo": "Técnico"}])
    overlay.aplicar_overlay(df, str(tmp_path))
    assert "status" not in df.columns

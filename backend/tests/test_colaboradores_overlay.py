"""Testes da persistência de status/habilidades (core/colaboradores_overlay.py).
Usa tmp_path para nunca tocar nos dados reais do projeto."""
import json

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


# ── set_bloqueado — pensado pra planilhas sem coluna de Status própria (ex: formato
# calendário simples da HETRIN a partir de setembro/2026), onde a única forma de
# registrar uma pendência de aptidão real (ex: autorização elétrica) é fora do Excel.

def test_set_bloqueado_persiste_com_aviso(tmp_path):
    d = str(tmp_path)
    overlay.set_bloqueado(d, "Wellington de Souza Brito", True, "Autorização elétrica pendente.")
    dados = overlay.carregar(d)
    entry = dados["WELLINGTON DE SOUZA BRITO"]
    assert entry["bloqueado"] is True
    assert entry["aviso"] == "Autorização elétrica pendente."


def test_set_bloqueado_false_remove_aviso(tmp_path):
    d = str(tmp_path)
    overlay.set_bloqueado(d, "Fulano", True, "Pendência qualquer.")
    overlay.set_bloqueado(d, "Fulano", False)
    entry = overlay.carregar(d)["FULANO"]
    assert entry["bloqueado"] is False
    assert "aviso" not in entry


def test_aplicar_overlay_sobrescreve_bloqueado_quando_planilha_nao_tem(tmp_path):
    """Formato calendário: o parser não populou 'bloqueado' (não tem coluna Status),
    mas o overlay registra uma pendência real — precisa vencer o default False."""
    d = str(tmp_path)
    overlay.set_bloqueado(d, "Wellington", True, "Condicionado.")

    df = pd.DataFrame([
        {"funcionario": "Wellington", "cargo": "Aux. Eletricista", "bloqueado": False, "aviso": None},
        {"funcionario": "Outro", "cargo": "Eletricista", "bloqueado": False, "aviso": None},
    ])
    resultado = overlay.aplicar_overlay(df, d)

    wellington = resultado[resultado["funcionario"] == "Wellington"].iloc[0]
    outro = resultado[resultado["funcionario"] == "Outro"].iloc[0]
    assert bool(wellington["bloqueado"]) is True
    assert wellington["aviso"] == "Condicionado."
    assert bool(outro["bloqueado"]) is False
    assert outro["aviso"] is None or pd.isna(outro["aviso"])


def test_aplicar_overlay_preserva_bloqueado_do_parser_sem_entrada_no_overlay(tmp_path):
    """Formato rico/12x36: o parser já calculou bloqueado=True (coluna Status própria)
    e não há entrada no overlay pra essa pessoa — o overlay não deve apagar isso."""
    d = str(tmp_path)
    df = pd.DataFrame([
        {"funcionario": "Ederson", "cargo": "Aux. Manutenção", "bloqueado": True, "aviso": "Condicionado."},
    ])
    resultado = overlay.aplicar_overlay(df, d)
    ederson = resultado.iloc[0]
    assert bool(ederson["bloqueado"]) is True


def test_aplicar_overlay_aviso_ausente_serializa_como_null_nao_nan(tmp_path):
    """Regressão: atribuir uma lista Python com None misturado a uma string real
    faz o pandas promover a coluna pra NaN (float) silenciosamente. json.dumps não
    recusa NaN — emite o token literal `NaN`, que não é JSON válido e quebra
    JSON.parse no frontend. Precisa continuar serializando como `null`."""
    d = str(tmp_path)
    overlay.set_bloqueado(d, "Bloqueado", True, "Pendência real.")

    df = pd.DataFrame([
        {"funcionario": "Bloqueado", "cargo": "Eletricista"},
        {"funcionario": "Livre", "cargo": "Eletricista"},
    ])
    resultado = overlay.aplicar_overlay(df, d)

    livre = resultado[resultado["funcionario"] == "Livre"].iloc[0]
    assert livre["aviso"] is None
    serializado = json.dumps(resultado.iloc[1].to_dict())
    assert "NaN" not in serializado
    assert '"aviso": null' in serializado

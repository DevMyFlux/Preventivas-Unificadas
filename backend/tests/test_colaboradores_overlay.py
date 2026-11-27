"""Testes da persistência de status/habilidades (core/colaboradores_overlay.py).
Usa tmp_path para nunca tocar nos dados reais do projeto."""
import json
from datetime import date

import pandas as pd
import pytest

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


# ── dentro_do_vinculo() / data_admissao / data_desligamento — bug real confirmado ──
# Auditoria com dado real (HETRIN, set/2026): 3 colaboradores com contrato de
# experiência encerrado em datas específicas dentro do mês (11, 16 e 22/09) continuaram
# sendo recomendados em preventivas e em OS reais do Neovero até o fim do mês, porque
# o sistema só sabia excluir alguém por MÊS inteiro (arquivo/status), nunca por DIA
# dentro de um mês já em andamento. Essas datas resolvem isso sem inventar uma regra
# fixa pros 3 nomes — funciona pra qualquer colaborador, de qualquer unidade.

def test_dentro_do_vinculo_sem_datas_sempre_true():
    assert overlay.dentro_do_vinculo({}, date(2026, 9, 30)) is True


def test_dentro_do_vinculo_exclui_a_partir_da_data_de_desligamento_inclusive():
    """Exemplo dado pela própria supervisão: desligamento em 16/09 -> elegível até
    15/09, NÃO elegível a partir de (e incluindo) 16/09."""
    row = {"data_desligamento": "2026-09-16"}
    assert overlay.dentro_do_vinculo(row, date(2026, 9, 15)) is True
    assert overlay.dentro_do_vinculo(row, date(2026, 9, 16)) is False
    assert overlay.dentro_do_vinculo(row, date(2026, 9, 17)) is False


def test_dentro_do_vinculo_exclui_antes_da_data_de_admissao():
    row = {"data_admissao": "2026-09-10"}
    assert overlay.dentro_do_vinculo(row, date(2026, 9, 9)) is False
    assert overlay.dentro_do_vinculo(row, date(2026, 9, 10)) is True
    assert overlay.dentro_do_vinculo(row, date(2026, 9, 11)) is True


def test_dentro_do_vinculo_combina_admissao_e_desligamento():
    row = {"data_admissao": "2026-09-05", "data_desligamento": "2026-09-20"}
    assert overlay.dentro_do_vinculo(row, date(2026, 9, 4)) is False
    assert overlay.dentro_do_vinculo(row, date(2026, 9, 10)) is True
    assert overlay.dentro_do_vinculo(row, date(2026, 9, 20)) is False


def test_set_data_desligamento_persiste_e_remove(tmp_path):
    d = str(tmp_path)
    overlay.set_data_desligamento(d, "Carlos Aurélio de Carvalho", "2026-09-11")
    assert overlay.carregar(d)["CARLOS AURÉLIO DE CARVALHO"]["data_desligamento"] == "2026-09-11"
    overlay.set_data_desligamento(d, "Carlos Aurélio de Carvalho", None)
    assert "data_desligamento" not in overlay.carregar(d)["CARLOS AURÉLIO DE CARVALHO"]


def test_set_data_admissao_persiste_e_remove(tmp_path):
    d = str(tmp_path)
    overlay.set_data_admissao(d, "Fulano", "2026-09-10")
    assert overlay.carregar(d)["FULANO"]["data_admissao"] == "2026-09-10"
    overlay.set_data_admissao(d, "Fulano", None)
    assert "data_admissao" not in overlay.carregar(d)["FULANO"]


def test_set_data_desligamento_formato_invalido_levanta_erro(tmp_path):
    with pytest.raises(ValueError):
        overlay.set_data_desligamento(str(tmp_path), "Fulano", "11/09/2026")


def test_aplicar_overlay_expoe_datas_de_vinculo(tmp_path):
    d = str(tmp_path)
    overlay.set_data_desligamento(d, "Maikon Jonathas Gomes Bessa", "2026-09-16")

    df = pd.DataFrame([
        {"funcionario": "Maikon Jonathas Gomes Bessa", "cargo": "Técnico de Climatização"},
        {"funcionario": "Outro", "cargo": "Eletricista"},
    ])
    resultado = overlay.aplicar_overlay(df, d)

    maikon = resultado[resultado["funcionario"] == "Maikon Jonathas Gomes Bessa"].iloc[0]
    outro = resultado[resultado["funcionario"] == "Outro"].iloc[0]
    assert maikon["data_desligamento"] == "2026-09-16"
    assert maikon["data_admissao"] is None
    assert outro["data_desligamento"] is None
    assert outro["data_admissao"] is None
    # mesma regressão de NaN-vs-null já coberta pra "aviso" — confirma que as duas
    # colunas novas também serializam certo
    serializado = json.dumps(resultado.iloc[1].to_dict())
    assert "NaN" not in serializado

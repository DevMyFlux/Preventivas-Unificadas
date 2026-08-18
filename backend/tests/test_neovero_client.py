"""
Testes de core/neovero_client.py.

Contexto do fix: a coluna "OS Vinculada"/"Status OS" da aba Preventivas mostrava a
última OS conhecida de um item mesmo quando a ocorrência é uma projeção futura sem
nenhuma OS real ainda — o Neovero não cria a ordem de serviço com antecedência.
Isso confundia usuários (parecia ser a OS daquela data específica). Decisão: só
expor a OS vinculada quando ela está de fato Aberta ou Em Andamento.
"""
from core.neovero_client import os_vinculada_visivel


def test_os_fechada_fica_oculta():
    assert os_vinculada_visivel({"numero": "202508123", "situacao": 3}) == ("—", "—")


def test_os_cancelada_fica_oculta():
    assert os_vinculada_visivel({"numero": "202508123", "situacao": 4}) == ("—", "—")


def test_os_aberta_e_exibida():
    assert os_vinculada_visivel({"numero": "202508123", "situacao": 1}) == ("202508123", "Aberta")


def test_os_em_andamento_e_exibida():
    assert os_vinculada_visivel({"numero": "202508123", "situacao": 2}) == ("202508123", "Em Andamento")


def test_sem_os_nenhuma_fica_oculta():
    assert os_vinculada_visivel({}) == ("—", "—")
    assert os_vinculada_visivel(None) == ("—", "—")


def test_situacao_desconhecida_fica_oculta():
    assert os_vinculada_visivel({"numero": "202508123", "situacao": 99}) == ("—", "—")

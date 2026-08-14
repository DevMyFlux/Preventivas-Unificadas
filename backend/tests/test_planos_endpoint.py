"""
Regressão: a rota /planos é cadastral (seção 7 do briefing original) e precisa
mostrar planos ativos E inativos — cada item já vem com o campo "ativo" pra tela
exibir o status. Bug encontrado: brasilandia/routes.py chamava filtros_planos()
sem passar ativo=None, caindo no default (ativo=True) e escondendo os inativos —
diferente de grand_massif/routes.py, que sempre passou ativo=None explicitamente.
"""
from unittest.mock import patch

import app as flask_app_module
from units.brasilandia import routes as br_routes
from units.grand_massif import routes as gm_routes


def _rodar_planos_com_paginar_mockado(routes_module):
    """Chama a view /planos com paginar() mockado e devolve os filtros que
    ela realmente montou pra consultar o Neovero."""
    capturado = {}

    def fake_paginar(headers, payload, endpoint):
        capturado["filtros"] = payload["filterGroups"][0]["filters"]
        return []

    with patch.object(routes_module, "paginar", side_effect=fake_paginar), \
         patch.object(routes_module, "get_headers", return_value={}), \
         patch.object(routes_module._cache_module, "get", return_value=None), \
         patch.object(routes_module._cache_module, "set"):
        with flask_app_module.app.test_request_context():
            routes_module.api_planos()

    return capturado["filtros"]


def test_planos_grand_massif_nao_filtra_por_ativo():
    filtros = _rodar_planos_com_paginar_mockado(gm_routes)
    propriedades = [f["property"] for f in filtros]
    assert "ativo" not in propriedades, "planos deve trazer ativos e inativos (tela cadastral)"


def test_planos_brasilandia_nao_filtra_por_ativo():
    filtros = _rodar_planos_com_paginar_mockado(br_routes)
    propriedades = [f["property"] for f in filtros]
    assert "ativo" not in propriedades, "planos deve trazer ativos e inativos (tela cadastral)"


def test_planos_das_duas_unidades_usam_o_mesmo_criterio():
    filtros_gm = {f["property"] for f in _rodar_planos_com_paginar_mockado(gm_routes)}
    filtros_br = {f["property"] for f in _rodar_planos_com_paginar_mockado(br_routes)}
    assert filtros_gm == filtros_br

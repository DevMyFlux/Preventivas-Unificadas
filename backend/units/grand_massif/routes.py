"""
Blueprint Flask — Hetrin (Grand Massif). Rotas: /api/grandmassif/*

Toda a lógica de rotas vive em core/unit_blueprint.py; aqui só se declara o que é
específico desta unidade: configuração, loader de escala, motor e a escala nomeada
(coleta diária de medidor/hidrômetro).
"""
from core.unit_blueprint import criar_blueprint
from units.grand_massif import config as CFG
from units.grand_massif.colaboradores import carregar_colaboradores, invalidar_cache
from units.grand_massif.escala_nomeada import nomes_permitidos_coleta
from units.grand_massif.motor import indicar_responsavel
from units.grand_massif.regras_cargo import regra_cargo_do_plano

bp = criar_blueprint(
    nome="grand_massif", cfg=CFG, codigo_unidade="HETRIN",
    carregar_colaboradores=carregar_colaboradores, invalidar_colaboradores=invalidar_cache,
    indicar_responsavel=indicar_responsavel, regras=(), nomes_permitidos_fn=nomes_permitidos_coleta,
    regra_cargo_fn=regra_cargo_do_plano,
)

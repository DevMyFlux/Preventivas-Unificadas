"""
Blueprint Flask — Hospital Municipal Brasilândia (HMB). Rotas: /api/brasilandia/*

Toda a lógica de rotas vive em core/unit_blueprint.py; aqui só se declara o que é
específico desta unidade: configuração, loader de escala, motor e as regras nominais de
atribuição (rondas diárias e oficina de ar comprimido/vácuo — ver units/brasilandia/regras.py).
"""
from core.unit_blueprint import criar_blueprint
from units.brasilandia import config as CFG
from units.brasilandia.colaboradores import carregar_colaboradores, invalidar_cache
from units.brasilandia.motor import indicar_responsavel
from units.brasilandia.regras import REGRAS

bp = criar_blueprint(
    nome="brasilandia", cfg=CFG, codigo_unidade="HMB",
    carregar_colaboradores=carregar_colaboradores, invalidar_colaboradores=invalidar_cache,
    indicar_responsavel=indicar_responsavel, regras=REGRAS, nomes_permitidos_fn=None,
)

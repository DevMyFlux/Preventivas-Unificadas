"""Configuração da unidade Hospital Municipal Brasilândia."""
import os

EMPRESA_ID = 2
OFICINA_ID = 0  # sem filtro de oficina → retorna todos os planos da empresa
NOME = "Hospital Municipal Brasilândia"
PREFIXO_API = "brasilandia"
COR_UNIDADE = "#1a5276"  # azul escuro diferenciado

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "brasilandia")

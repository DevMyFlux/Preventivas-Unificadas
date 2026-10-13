"""Configuração da unidade Hospital Municipal Brasilândia."""
import os

from core.overlay_store import DbStore

EMPRESA_ID = 2
OFICINA_ID = 0  # sem filtro de oficina → retorna todos os planos da empresa
NOME = "HMB"
PREFIXO_API = "brasilandia"
COR_UNIDADE = "#1a5276"  # azul escuro diferenciado

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "hmb")

# Overlay de colaboradores (status/vínculo/bloqueio/habilidades): durável no banco da aplicação;
# o JSON em DATA_DIR é só a semente da primeira leitura (ver core/overlay_store.py).
OVERLAY = DbStore("HMB", DATA_DIR)

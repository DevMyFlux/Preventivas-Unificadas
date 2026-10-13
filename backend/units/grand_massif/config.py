"""Configuração da unidade Grand Massif."""
import os

from core.overlay_store import DbStore

EMPRESA_ID = 3
OFICINA_ID = 0  # 0 = sem filtro de oficina
NOME = "Hetrin"
PREFIXO_API = "grandmassif"
COR_UNIDADE = "#1F3864"  # azul primário

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "hetrin")

# Overlay de colaboradores (status/vínculo/bloqueio/habilidades): durável no banco da aplicação;
# o JSON em DATA_DIR é só a semente da primeira leitura (ver core/overlay_store.py).
OVERLAY = DbStore("HETRIN", DATA_DIR)

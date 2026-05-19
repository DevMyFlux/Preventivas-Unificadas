"""
MyFlux Preventivas — Aplicação Unificada
Backend Flask com suporte a múltiplas unidades via Blueprints.

Unidades:
  - Grand Massif       → /api/grandmassif/*
  - Hospital Brasilândia → /api/brasilandia/*

Acesse: http://localhost:5000
"""
import os

from flask import Flask, send_from_directory

from units.grand_massif.routes import bp as bp_gm
from units.brasilandia.routes import bp as bp_br

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIST = os.path.join(SCRIPT_DIR, "..", "frontend", "dist")

app = Flask(__name__)

# ── Registra blueprints por unidade ──────────────────────────────────────────
app.register_blueprint(bp_gm)
app.register_blueprint(bp_br)


# ── Serve o frontend React (SPA) ──────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIST, "index.html")


@app.route("/assets/<path:filename>")
def serve_assets(filename):
    return send_from_directory(os.path.join(FRONTEND_DIST, "assets"), filename)


@app.route("/<path:path>")
def catch_all(path):
    full_path = os.path.join(FRONTEND_DIST, path)
    if os.path.isfile(full_path):
        return send_from_directory(FRONTEND_DIST, path)
    return send_from_directory(FRONTEND_DIST, "index.html")


if __name__ == "__main__":
    print("=" * 60)
    print("  MyFlux Preventivas — Servidor Unificado")
    print("  http://localhost:5000")
    print("  Unidades: Grand Massif | Hospital Municipal Brasilândia")
    print("=" * 60)
    app.run(debug=True, port=5000, threaded=True)

import logging
import os

from flask import Flask, jsonify, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix

from core import db, migrations
from core.settings import settings
from core.auth import admin_rotas, http as auth_http, rotas as auth_rotas, servico as auth_servico
from units.brasilandia.routes import bp as bp_br
from units.grand_massif.routes import bp as bp_gm

FRONTEND_DIST = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "dist")
)

log = logging.getLogger("myflux")


def create_app(database_url: str | None = None, *, bootstrap: bool = True) -> Flask:
    """Fábrica da aplicação. `database_url` permite apontar para um banco isolado (testes)."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    flask_app = Flask(__name__)
    flask_app.config["JSON_AS_ASCII"] = False
    flask_app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # corpos de requisição até 8 MB

    if settings.proxy_hops:
        flask_app.wsgi_app = ProxyFix(flask_app.wsgi_app, x_for=settings.proxy_hops, x_proto=settings.proxy_hops)

    db.init_engine(database_url)
    aplicadas = migrations.migrar()
    if aplicadas:
        log.info("Migrações aplicadas: %s", aplicadas)
    if bootstrap:
        log.info("Administrador inicial: %s", auth_servico.bootstrap_admin())

    # Guarda global (login obrigatório, CSRF, escopo por unidade, auditoria, headers, CORS)
    auth_http.instalar(flask_app)

    flask_app.register_blueprint(auth_rotas.bp)
    flask_app.register_blueprint(admin_rotas.bp)
    flask_app.register_blueprint(bp_gm)
    flask_app.register_blueprint(bp_br)

    @flask_app.errorhandler(404)
    def _nao_encontrado(e):
        from flask import request
        if request.path.startswith("/api/"):
            return jsonify({"erro": "Recurso não encontrado."}), 404
        return e

    @flask_app.errorhandler(413)
    def _grande_demais(_e):
        return jsonify({"erro": "Requisição grande demais."}), 413

    @flask_app.errorhandler(500)
    def _erro_interno(_e):
        # nunca devolve stack trace/mensagem interna ao cliente
        return jsonify({"erro": "Erro interno. Tente novamente; se persistir, contate o suporte."}), 500

    # Serve React SPA (presente no container de produção)
    if os.path.isdir(FRONTEND_DIST):
        @flask_app.route("/")
        def _index():
            return send_from_directory(FRONTEND_DIST, "index.html")

        @flask_app.route("/<path:path>")
        def _spa(path):
            if path.startswith("api/"):
                return jsonify({"erro": "Recurso não encontrado."}), 404
            full = os.path.join(FRONTEND_DIST, path)
            if os.path.isfile(full):
                return send_from_directory(FRONTEND_DIST, path)
            return send_from_directory(FRONTEND_DIST, "index.html")

    return flask_app


import os

from flask import Flask, send_from_directory

from units.grand_massif.routes import bp as bp_gm
from units.brasilandia.routes import bp as bp_br

FRONTEND_DIST = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "dist")
)

app = Flask(__name__)


@app.after_request
def _cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.route("/api/<path:path>", methods=["OPTIONS"])
def _options(**_):
    return "", 204


app.register_blueprint(bp_gm)
app.register_blueprint(bp_br)


# Serve React SPA (presente no container de produção)
if os.path.isdir(FRONTEND_DIST):
    @app.route("/")
    def _index():
        return send_from_directory(FRONTEND_DIST, "index.html")

    @app.route("/<path:path>")
    def _spa(path):
        full = os.path.join(FRONTEND_DIST, path)
        if os.path.isfile(full):
            return send_from_directory(FRONTEND_DIST, path)
        return send_from_directory(FRONTEND_DIST, "index.html")


if __name__ == "__main__":
    app.run(debug=True, port=5000, threaded=True)

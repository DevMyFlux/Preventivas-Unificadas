"""Ponto de entrada WSGI (gunicorn app:app). A fábrica fica em app_factory.py para que os
testes possam criar aplicações isoladas sem efeitos colaterais de importação."""
import os

from app_factory import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=int(os.environ.get("PORT", 5000)), threaded=True)

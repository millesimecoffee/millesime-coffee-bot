"""Lance la webapp Flask en local pour vérifier la Mini App dans un navigateur.

Usage : python run_webapp_dev.py  → http://localhost:5000/menu
Ne sert qu'au développement ; en production c'est bot.py qui démarre le serveur.
"""
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

# Charger le .env comme le fait bot.py
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from webapp import app  # noqa: E402

# Sans ça, Jinja garde menu.html en cache et sert la version d'avant l'édition.
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.jinja_env.auto_reload = True

if __name__ == "__main__":
    # PORT est impose par l'outil d'apercu ; DEV_PORT reste pour un
    # lancement a la main.
    port = int(os.getenv("PORT") or os.getenv("DEV_PORT") or "5000")
    print(f"Mini App de dev : http://localhost:{port}/menu")
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True)

"""Lance toutes les suites de tests, chacune dans son propre processus.

    python tests/run_tous.py

Chaque suite modifie des variables d'environnement et remplace des fonctions
du serveur : les isoler dans des processus separes evite qu'une suite en
perturbe une autre.
"""
import os
import subprocess
import sys
from pathlib import Path

ICI = Path(__file__).parent
SUITES = sorted(p for p in ICI.glob("test_*.py"))

# Les suites affichent des drapeaux et des accents. Quand la sortie est
# redirigée, Python retombe sur l'encodage du système — cp1252 sous Windows —
# et une suite parfaitement verte échoue sur un simple print. On impose l'UTF-8
# aux processus fils : un test ne doit jamais dépendre du terminal qui l'appelle.
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}

resultats = []
for suite in SUITES:
    print(f"\n{'#' * 62}\n#  {suite.name}\n{'#' * 62}", flush=True)
    r = subprocess.run([sys.executable, str(suite)], cwd=str(ICI.parent), env=ENV)
    resultats.append((suite.name, r.returncode == 0))

print(f"\n{'=' * 62}\nRECAPITULATIF")
for nom, ok in resultats:
    print(f"   {'PASSE ' if ok else 'ECHEC '} {nom}")

echecs = [n for n, ok in resultats if not ok]
if echecs:
    print(f"\n{len(echecs)} suite(s) en echec.")
    sys.exit(1)
print(f"\n{len(resultats)} suites, tout est vert.")

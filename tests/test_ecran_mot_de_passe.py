"""Écran de mot de passe : chaque échec doit dire sa vraie cause.

Le piège corrigé ici : une session Telegram périmée renvoyait « Mot de passe
incorrect », alors que le mot de passe était bon. On cherche alors une faute
de frappe qui n'existe pas.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import preparer, titre, fin, OWNER, AUTRE

webapp = preparer()
import storage
storage._load = lambda: []

app = webapp.app.test_client()

# Signature valide seulement si initData vaut "bon".
import json as _json
webapp._verify_init_data = lambda init, token: (
    {"user": _json.dumps({"id": AUTRE, "username": "c"})} if init == "bon" else None)


def auth(mdp, init="bon"):
    webapp._rate_reset(f"pwd:uid:{AUTRE}")
    with webapp._pwd_lock:
        webapp._pwd_attempts.clear()
    return app.post("/api/auth", json={"initData": init, "password": mdp})


print("=" * 62)

titre(1, "Session valide + bon mot de passe -> entree")
r = auth("PLATA O PLOMO")
print(f"   HTTP {r.status_code} ok={r.get_json().get('ok')}")
assert r.status_code == 200 and r.get_json()["ok"] is True

titre(2, "Session valide + mauvais mot de passe -> wrong_password")
r = auth("PAS LE BON")
d = r.get_json()
print(f"   HTTP {r.status_code} error={d.get('error')}")
assert d.get("error") == "wrong_password"

titre(3, "Session invalide + BON mot de passe -> auth_failed, PAS wrong_password")
print("    (c'est le cas qui faisait croire a un mot de passe faux)")
for mdp in ["PLATA O PLOMO", "RICH PORTER"]:
    r = auth(mdp, init="perime")
    d = r.get_json()
    print(f"   {mdp:<14s} HTTP {r.status_code} error={d.get('error')}")
    assert r.status_code == 401 and d.get("error") == "auth_failed"
    assert d.get("error") != "wrong_password"

titre(4, "Session absente -> auth_failed aussi")
r = auth("PLATA O PLOMO", init="")
print(f"   HTTP {r.status_code} error={r.get_json().get('error')}")
assert r.status_code == 401 and r.get_json().get("error") == "auth_failed"

titre(5, "Trop d'essais -> blocked, distinct du mot de passe faux")
webapp._rate_reset(f"pwd:uid:{AUTRE}")
with webapp._pwd_lock:
    webapp._pwd_attempts.clear()
codes = []
for _ in range(7):
    codes.append(app.post("/api/auth",
                          json={"initData": "bon", "password": "faux"}).get_json())
bloques = [c for c in codes if c.get("blocked")]
print(f"   {len(bloques)} reponse(s) « blocked » sur 7 essais")
assert bloques, "aucun blocage apres 7 essais"
print(f"   forme de la reponse : {bloques[0]}")

titre(6, "Mot de passe non configure -> message dedie")
os.environ["BOT_PASSWORD"] = ""
r = app.post("/api/auth", json={"initData": "bon", "password": "peu importe"})
print(f"   HTTP {r.status_code} error={r.get_json().get('error')}")
assert r.get_json().get("error") == "no_password_configured"
os.environ["BOT_PASSWORD"] = "PLATA O PLOMO"

titre(7, "Les raisons de refus sont tracees cote serveur")
import logging
traces = []


class Collecteur(logging.Handler):
    def emit(self, record):
        traces.append(record.getMessage())


logging.getLogger("webapp").addHandler(Collecteur())
logging.getLogger("webapp").setLevel(logging.INFO)
# On remet la vraie fonction : les tests ci-dessus l'avaient remplacée.
import importlib
importlib.reload(webapp)
webapp._verify_init_data("", "jeton")
webapp._verify_init_data("user=x&hash=zzz", "jeton")
webapp._verify_init_data("auth_date=1&user=x&hash=zzz", "")
for t in traces:
    print(f"   {t}")
assert any("absent" in t for t in traces)
assert any("signature" in t for t in traces)

fin()

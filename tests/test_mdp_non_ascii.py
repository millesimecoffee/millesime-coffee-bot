"""Un mot de passe avec des accents ou du cyrillique ne doit pas faire tomber
le serveur.

`hmac.compare_digest` refuse les chaînes contenant du non-ASCII : il lève une
TypeError, que Flask transforme en 500. Constaté en production le 15 août 2026
sur /api/auth. Concrètement, un client qui tapait un accent — ou n'importe quel
caractère cyrillique depuis l'ajout du russe — voyait la boutique en panne au
lieu de « mot de passe incorrect ».
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import preparer, simuler_telegram, titre, fin, OWNER, AUTRE

webapp = preparer(BOT_PASSWORD="PLATA O PLOMO",
                  ADMIN_PANEL_PASSWORD="RICH PORTER",
                  LIVREUR_PASSWORD="LIVREUR BRUXELLES",
                  DATA_DIR=tempfile.mkdtemp(prefix="millesime_mdp_"))
import github_backup
github_backup.backup_file_async = lambda *a, **k: None

uid = {"v": AUTRE}
simuler_telegram(webapp, uid)
app = webapp.app.test_client()

# Des mots de passe faux, mais qu'un vrai client peut taper.
PIEGES = [
    ("accent francais",     "café au lait"),
    ("cedille",             "Garçon"),
    ("cyrillique",          "Привет"),
    ("cyrillique + espace", "мой пароль"),
    ("emoji",               "mot☕passe"),
    ("chinois",             "密码"),
    ("accent seul",         "é"),
    ("melange",             "PLATA O PLOMÓ"),
]

print("=" * 62)

titre(1, "Aucun de ces mots de passe ne doit provoquer d'erreur 500")
plantages = []
for nom, mdp in PIEGES:
    r = app.post("/api/auth", json={"initData": "x", "password": mdp})
    etat = "OK" if r.status_code < 500 else "PLANTAGE"
    print(f"   {nom:22s} -> HTTP {r.status_code}  {etat}")
    if r.status_code >= 500:
        plantages.append(nom)
assert not plantages, f"{len(plantages)} plantage(s) : {plantages}"

titre(2, "Ils sont refuses, pas acceptes par erreur")
for nom, mdp in PIEGES:
    d = app.post("/api/auth", json={"initData": "x", "password": mdp}).get_json()
    assert not d.get("ok"), f"{nom} ne doit pas ouvrir la boutique"
print(f"   {len(PIEGES)} mots de passe refuses proprement")

titre(3, "Le bon mot de passe marche toujours")
# Les essais precedents ont declenche le blocage anti-force-brute : on repart
# d'un compteur vierge, sinon on testerait le blocage et pas la comparaison.
webapp._pwd_attempts.clear()
d = app.post("/api/auth", json={"initData": "x", "password": "PLATA O PLOMO"}).get_json()
print(f"   « PLATA O PLOMO » -> ok={d.get('ok')}")
assert d.get("ok") is True
d = app.post("/api/auth", json={"initData": "x", "password": "  plata o plomo  "}).get_json()
print(f"   casse et espaces ignores -> ok={d.get('ok')}")
assert d.get("ok") is True

titre(4, "Le panneau admin resiste aux memes caracteres")
uid["v"] = OWNER
webapp._pwd_attempts.clear()
webapp._rate_store.clear()
plantages = []
for nom, mdp in PIEGES:
    r = app.post("/api/admin/unlock", json={"initData": "x", "password": mdp})
    if r.status_code >= 500:
        plantages.append(f"{nom} -> {r.status_code}")
print(f"   {len(PIEGES)} tentatives, plantages : {plantages or 'aucun'}")
assert not plantages
webapp._rate_store.clear()
r = app.post("/api/admin/unlock", json={"initData": "x", "password": "RICH PORTER"})
print(f"   le vrai mot de passe -> HTTP {r.status_code}")
assert r.status_code == 200

titre(5, "L'acces livreur aussi")
webapp._admin_unlocked.clear()
uid["v"] = AUTRE
plantages = []
for nom, mdp in PIEGES:
    r = app.post("/api/auth", json={"initData": "x", "password": mdp})
    if r.status_code >= 500:
        plantages.append(nom)
assert not plantages
webapp._pwd_attempts.clear()
d = app.post("/api/auth", json={"initData": "x", "password": "livreur bruxelles"}).get_json()
print(f"   « livreur bruxelles » -> ok={d.get('ok')} role={d.get('role')}")
assert d.get("ok") is True

titre(6, "Une reference de chat exotique ne fait pas tomber le serveur")
for nom, valeur in PIEGES + [("tres long", "é" * 300)]:
    r = app.post("/api/chat/thread", json={"initData": "x", "chat_ref": valeur})
    if r.status_code >= 500:
        plantages.append(f"chat_ref {nom}")
print(f"   {len(PIEGES) + 1} references aberrantes -> plantages : {plantages or 'aucun'}")
assert not plantages

fin()

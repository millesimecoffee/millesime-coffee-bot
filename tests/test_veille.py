"""L'accès de veille : voir qui consulte le catalogue, et rien d'autre.

Ce mot de passe n'ouvre qu'un écran : les passages sur le catalogue, avec le
pays et la ville regardés. Il ne doit donner accès à AUCUN autre écran — ni
commandes, ni conversations, ni panneau, ni catalogue.
"""
import os
import sys
import tempfile
import time as _time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import preparer, simuler_telegram, titre, fin, OWNER, AUTRE

DOSSIER = tempfile.mkdtemp(prefix="millesime_veille_")
webapp = preparer(ADMIN_PANEL_PASSWORD="RICH PORTER",
                  LIVREUR_PASSWORD="LIVREUR BRUXELLES",
                  LIVREUR_ZONES="Belgique:Bruxelles",
                  VEILLE_PASSWORD="The White Page",
                  NOTIF_IGNORER_OWNER="0",
                  DATA_DIR=DOSSIER)
import github_backup
github_backup.backup_file_async = lambda *a, **k: None
github_backup.backup_binaire_async = lambda *a, **k: None

import parcours
parcours._FICHIER = Path(DOSSIER) / "parcours.json"

import pushover
pushover.pays_choisi = lambda *a, **k: True
pushover.ville_choisie = lambda *a, **k: True


class Reponse:
    status_code = 200
    text = "{}"

    def json(self):
        return {"ok": True, "result": {}}


import httpx
httpx.post = lambda *a, **k: Reponse()
httpx.get = lambda *a, **k: Reponse()

VEILLEUR = 610000777
qui = {"v": AUTRE}
simuler_telegram(webapp, qui)
app = webapp.app.test_client()


def entrer(uid, mdp):
    qui["v"] = uid
    webapp._pwd_attempts.clear()
    webapp._rate_store.clear()
    return app.post("/api/auth", json={"initData": "x", "password": mdp}).get_json()


def consulter(uid, pays, ville=""):
    qui["v"] = uid
    webapp._rate_store.clear()
    return app.post("/api/notify/city",
                    json={"initData": "x", "country": pays, "city": ville})


print("=" * 66)

titre(1, "Un passage sur le catalogue est enregistre")
consulter(111, "🇫🇷 France", "Paris")
consulter(222, "🇪🇸 Espagne", "Barcelone")
consulter(333, "🇧🇪 Belgique", "Bruxelles")
p = parcours.passages()
print(f"   {len(p)} passage(s) enregistre(s)")
for x in p:
    print(f"   {x['prenom'] or '?':10s} {x['pays']:16s} {x['ville']}")
assert len(p) == 3, p

titre(2, "Le pays seul compte aussi (la ville suivra)")
consulter(444, "🇬🇧 Angleterre")
p = parcours.passages()
print(f"   {len(p)} passage(s), dernier : {p[0]['pays']} ville={p[0]['ville'] or '(aucune)'}")
assert p[0]["pays"] == "🇬🇧 Angleterre" and p[0]["ville"] == ""

titre(3, "Les allers-retours ne creent pas dix lignes")
avant = len(parcours.passages())
for _ in range(6):
    consulter(111, "🇫🇷 France", "Paris")
apres = len(parcours.passages())
print(f"   6 consultations identiques : {avant} -> {apres} ligne(s)")
assert apres == avant, "un meme visiteur sur la meme ville doit etre regroupe"

titre(4, "Mais un changement de ville, si")
consulter(111, "🇫🇷 France", "Marseille") if "Marseille" in str(parcours) else None
consulter(111, "🇪🇸 Espagne", "Malaga")
p = parcours.passages()
print(f"   nouvelle destination -> {p[0]['pays']} · {p[0]['ville']}")
assert p[0]["ville"] == "Malaga"

titre(5, "Le mot de passe « The White Page » ouvre l'acces")
d = entrer(VEILLEUR, "The White Page")
print(f"   ok={d.get('ok')} veille={d.get('veille')} admin={d.get('admin')} "
      f"livreur={d.get('livreur')}")
assert d.get("ok") and d.get("veille")
assert not d.get("admin") and not d.get("livreur")

titre(6, "Casse et espaces sans importance")
for variante in ["the white page", "  THE WHITE PAGE  ", "The   White   Page"]:
    d = entrer(VEILLEUR, variante)
    print(f"   « {variante:22s} » -> veille={d.get('veille')}")
    assert d.get("veille"), variante

titre(7, "Il voit la liste des passages")
qui["v"] = VEILLEUR
entrer(VEILLEUR, "The White Page")
r = app.post("/api/veille/passages", json={"initData": "x"})
d = r.get_json()
print(f"   HTTP {r.status_code} — {len(d.get('passages', []))} passage(s)")
print(f"   resume : {d.get('resume')}")
assert r.status_code == 200 and d.get("ok")
assert len(d["passages"]) >= 4
champs = set(d["passages"][0])
print(f"   champs par ligne : {sorted(champs)}")
assert champs <= {"uid", "prenom", "pays", "ville", "at"}, champs

titre("7b", "Sa reponse d'authentification ne porte ni catalogue ni prix")
d = entrer(VEILLEUR, "The White Page")
print(f"   champs recus : {sorted(d)}")
assert set(d) == {"ok", "admin", "livreur", "veille"}, sorted(d)
for interdit in ("catalog", "min_orders", "currencies", "payment_config",
                 "city_payment", "support"):
    assert interdit not in d, interdit
print("   ni catalogue, ni minimums, ni coordonnees de paiement")

titre("7c", "Le veilleur n'apparait pas dans sa propre liste")
entrer(VEILLEUR, "The White Page")
consulter(VEILLEUR, "🇫🇷 France", "Paris")
qui["v"] = VEILLEUR
p2 = app.post("/api/veille/passages", json={"initData": "x"}).get_json()["passages"]
print(f"   son identifiant dans la liste : {any(x['uid'] == str(VEILLEUR) for x in p2)}")
assert not any(x["uid"] == str(VEILLEUR) for x in p2)

titre(8, "Et RIEN d'autre")
FERMES = [
    ("commandes admin", "/api/admin/orders", {}),
    ("clients admin", "/api/admin/clients", {}),
    ("courses livreur", "/api/livreur/courses", {}),
    ("conversations", "/api/chat/threads", {}),
    ("diffusion", "/api/admin/broadcast", {"texte": "test"}),
    ("envoi de message", "/api/admin/send_message", {"client_id": 111, "texte": "x"}),
    ("note client", "/api/admin/client_note", {"client_id": 111, "note": "x"}),
    ("detail commande", "/api/admin/order/150801", {}),
]
ouverts = []
for nom, route, extra in FERMES:
    r = app.post(route, json={"initData": "x", **extra})
    ferme = r.status_code in (401, 403)
    print(f"   {nom:18s} -> HTTP {r.status_code} {'ferme' if ferme else '*** OUVERT ***'}")
    if not ferme:
        ouverts.append(nom)
assert not ouverts, f"acces ouverts a tort : {ouverts}"

titre(9, "Un simple client ne voit pas les passages")
qui["v"] = 999000222
r = app.post("/api/veille/passages", json={"initData": "x"})
print(f"   client ordinaire -> HTTP {r.status_code}")
assert r.status_code == 403

titre(10, "L'owner y a droit aussi, c'est sa boutique")
qui["v"] = OWNER
app.post("/api/admin/unlock", json={"initData": "x", "password": "RICH PORTER"})
r = app.post("/api/veille/passages", json={"initData": "x"})
print(f"   owner -> HTTP {r.status_code}")
assert r.status_code == 200

titre(11, "Le journal ne grossit pas indefiniment")
parcours.MAX_PASSAGES = 20
for i in range(60):
    parcours.noter(500000 + i, f"P{i}", "🇫🇷 France", "Paris")
n = len(parcours.passages(800))
print(f"   60 passages, plafond {parcours.MAX_PASSAGES} -> {n} garde(s)")
assert n == parcours.MAX_PASSAGES
parcours.MAX_PASSAGES = 800

titre(12, "Aucune coordonnee dans le journal")
brut = parcours._FICHIER.read_text(encoding="utf-8")
for interdit in ("selfie", "adresse", "address", "phone", "lat", "lon", "total", "cart"):
    assert interdit not in brut.lower(), interdit
print("   ni adresse, ni photo, ni panier, ni telephone")

fin()

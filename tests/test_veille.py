"""L'accès de veille : voir qui consulte le catalogue, et rien d'autre.

Ce mot de passe n'ouvre qu'un écran : les passages sur le catalogue, avec le
pays et la ville regardés. Il ne doit donner accès à AUCUN autre écran — ni
commandes, ni conversations, ni panneau, ni catalogue.
"""
import json
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

titre("4b", "Choisir un pays PUIS sa ville ne fait qu'une seule ligne")
# C'est le parcours reel : on clique sur le pays, l'ecran des villes s'ouvre,
# on clique sur la ville. Constate en production le 15 aout 2026 : deux lignes
# apparaissaient pour un seul visiteur qui affinait son choix.
avant = len(parcours.passages(400))
consulter(555111, "🇩🇪 Allemagne")
consulter(555111, "🇩🇪 Allemagne", "Berlin")
apres = parcours.passages(400)
nouvelles = len(apres) - avant
ligne = [x for x in apres if x.get("uid") == "555111"][0]
print(f"   pays puis ville -> {nouvelles} ligne(s) : {ligne['pays']} · {ligne['ville']}")
assert nouvelles == 1, f"{nouvelles} lignes au lieu d'une"
assert ligne["ville"] == "Berlin", "la ligne doit porter la ville finale"

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
# « type » distingue une vue d'une etape de commande. Rien de plus ne doit
# figurer sur une ligne de vue.
assert champs <= {"uid", "prenom", "pays", "ville", "at", "type"}, champs

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

titre(10, "L'owner voit exactement le meme tableau de bord")
qui["v"] = OWNER
app.post("/api/admin/unlock", json={"initData": "x", "password": "RICH PORTER"})
r = app.post("/api/veille/passages", json={"initData": "x", "jours": 30})
d_owner = r.get_json()
print(f"   owner -> HTTP {r.status_code}")
assert r.status_code == 200 and d_owner.get("ok")
# Il doit recevoir les memes blocs que l'acces White Page, pas un sous-ensemble.
assert set(d_owner) == {"ok", "passages", "resume", "classements", "entonnoir", "jours"},     sorted(d_owner)
print(f"   blocs recus : {sorted(d_owner)}")
qui["v"] = VEILLEUR
entrer(VEILLEUR, "The White Page")
d_veille = app.post("/api/veille/passages", json={"initData": "x", "jours": 30}).get_json()
print(f"   identiques a ceux de la veille : {set(d_owner) == set(d_veille)}")
assert set(d_owner) == set(d_veille)
assert d_owner["entonnoir"] == d_veille["entonnoir"]

titre(11, "Le journal ne grossit pas indefiniment")
parcours.MAX_PASSAGES = 20
for i in range(60):
    parcours.noter(500000 + i, f"P{i}", "🇫🇷 France", "Paris")
n = len(parcours.passages(800))
print(f"   60 passages, plafond {parcours.MAX_PASSAGES} -> {n} garde(s)")
assert n == parcours.MAX_PASSAGES
parcours.MAX_PASSAGES = 800

titre("11b", "Les commandes et leurs etapes sont suivies")
parcours.noter_commande("150801", 777, "Ines", "🇪🇸 Espagne", "Malaga", "pending")
parcours.noter_commande("150801", 777, "Ines", "🇪🇸 Espagne", "Malaga", "confirmed")
parcours.noter_commande("150801", 777, "Ines", "🇪🇸 Espagne", "Malaga", "delivered")
parcours.noter_commande("150802", 888, "Theo", "🇫🇷 France", "Paris", "pending")
e = parcours.entonnoir(90)
print(f"   entonnoir : {e}")
assert e["lancees"] == 2 and e["confirmees"] == 1 and e["livrees"] == 1

titre("11c", "Les classements repondent")
c = parcours.classements(90)
print(f"   villes regardees  : {[(x['ville'], x['n']) for x in c['villes_vues'][:3]]}")
print(f"   villes commandees : {[(x['ville'], x['n']) for x in c['villes_commandes']]}")
assert {x["ville"] for x in c["villes_commandes"]} == {"Malaga", "Paris"}
assert all(0 <= x["part"] <= 100 for x in c["villes_vues"])

titre("11d", "Une etape de commande ne porte NI montant NI panier")
lignes = [x for x in parcours.passages(400) if x.get("type") == "commande"]
champs = set().union(*(set(x) for x in lignes))
print(f"   champs : {sorted(champs)}")
assert champs == {"type", "uid", "prenom", "pays", "ville", "etape", "ref", "at"}, champs
for interdit in ("total", "cart", "panier", "prix", "montant", "payment"):
    assert interdit not in champs

titre("11e", "L'ecran de veille ne renvoie jamais de montant")
qui["v"] = VEILLEUR
entrer(VEILLEUR, "The White Page")
rep = app.post("/api/veille/passages", json={"initData": "x", "jours": 90}).get_json()
brut_reponse = json.dumps(rep, ensure_ascii=False)
# « total » existe dans le resume, mais c'est un NOMBRE DE LIGNES, pas un
# montant : on verifie donc les cles, pas une simple presence de mot.
for interdit in ("cart", "€", "price", "montant", "panier", "selfie", "address", "phone"):
    assert interdit not in brut_reponse.lower(), interdit
cles_resume = set(rep.get("resume") or {})
cles_entonnoir = set(rep.get("entonnoir") or {})
print(f"   resume    : {sorted(cles_resume)}")
print(f"   entonnoir : {sorted(cles_entonnoir)}")
assert cles_resume == {"total", "aujourd_hui", "personnes", "personnes_aujourd_hui",
                       "commandes_aujourd_hui"}, cles_resume
assert cles_entonnoir == {"vues", "lancees", "confirmees", "en_route", "livrees",
                          "annulees"}, cles_entonnoir
# Chaque valeur est un compteur entier, jamais une somme d'argent.
assert all(isinstance(v, int) for v in (rep["resume"] | rep["entonnoir"]).values())
for r in rep.get("classements", {}).get("villes_commandes", []):
    assert set(r) == {"pays", "ville", "n", "part"}, r
print("   que des compteurs : aucun montant ne sort de cet acces")

titre("11f", "Le compte de veille recoit les notifications Telegram")
# On capture ce que le bot envoie, sans rien expedier.
envois = []


class RepTg:
    status_code = 200

    def json(self):
        return {"ok": True}


import httpx as _httpx
_httpx.post = lambda url, **kw: (envois.append(kw.get("json") or {}), RepTg())[1]
os.environ["BOT_TOKEN"] = "123:FAKE"
os.environ["VEILLE_CHAT_ID"] = str(VEILLEUR)

webapp._rate_store.clear()
consulter(123456, "🇫🇷 France", "Paris")
vus = [e for e in envois if str(e.get("chat_id")) == str(VEILLEUR)]
print(f"   consultation -> {len(vus)} notification(s)")
for e in vus:
    print(f"   « {e.get('text','').replace(chr(10), ' | ')} »")
assert vus, "le compte de veille doit etre prevenu"

envois.clear()
webapp._prevenir_veille("\U0001F6D2 <b>Nouvelle commande</b>\n"
                        "\U0001F1EA\U0001F1F8 Espagne \u00b7 <b>Malaga</b>\n"
                        "n\u00b0\u20260801")
print(f"   commande     -> {len(envois)} notification(s)")
print(f"   « {envois[0].get('text','').replace(chr(10), ' | ')} »")
assert envois

titre("11g", "Les notifications ne portent NI montant NI panier")
envois.clear()
webapp._rate_store.clear()
consulter(123457, "🇪🇸 Espagne", "Barcelone")
webapp._prevenir_veille("✅ Commande <b>confirmée</b>")
textes = " ".join(e.get("text", "") for e in envois).lower()
for interdit in ("€", "eur", "total", "prix", "montant", "coca", "weed",
                 "panier", "£", "$"):
    assert interdit not in textes, f"« {interdit} » dans une notification"
print(f"   {len(envois)} message(s) verifies : aucun prix, aucun produit")

titre("11h", "Sans destinataire, rien n'est envoye et rien ne casse")
os.environ["VEILLE_CHAT_ID"] = ""
webapp._veilleurs_connus.clear()
envois.clear()
n = webapp._prevenir_veille("test")
print(f"   aucun destinataire -> {n} envoi(s)")
assert n == 0 and not envois

titre("11i", "Ouvrir l'acces inscrit le compte aux notifications")
webapp._veilleurs_connus.clear()
entrer(VEILLEUR, "The White Page")
print(f"   comptes retenus : {list(webapp._veilleurs_connus)}")
assert str(VEILLEUR) in webapp._veilleurs_connus
os.environ["VEILLE_CHAT_ID"] = ""

titre(12, "Aucune coordonnee dans le journal")
brut = json.loads(parcours._FICHIER.read_text(encoding="utf-8"))
# On verifie les CLES, pas des sous-chaines : chercher « lon » dans le texte
# brut attrapait « Londres », et « total » un simple compteur.
cles = set().union(*(set(x) for x in brut)) if brut else set()
print(f"   cles presentes : {sorted(cles)}")
AUTORISEES = {"type", "uid", "prenom", "pays", "ville", "at", "etape", "ref"}
assert cles <= AUTORISEES, cles - AUTORISEES
for interdit in ("selfie", "adresse", "address", "phone", "lat", "lon",
                 "total", "cart", "prix", "montant", "payment"):
    assert interdit not in cles, interdit
print("   ni adresse, ni photo, ni panier, ni telephone, ni montant")

fin()

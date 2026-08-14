"""Accès livreur : ses courses, aucune identité de client.

Le livreur doit pouvoir travailler seul — voir les commandes de sa zone, les
faire avancer, parler au client — sans jamais apprendre qui est ce client.
"""
import base64
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import preparer, titre, fin, OWNER, AUTRE

DOSSIER = tempfile.mkdtemp(prefix="millesime_livreur_")
webapp = preparer(LIVREUR_PASSWORD="BRUXELLES 2026",
                  LIVREUR_ZONES="Belgique:Bruxelles",
                  ADMIN_PANEL_PASSWORD="RICH PORTER",
                  DATA_DIR=DOSSIER)

import chat
import storage

LIVREUR = 555000777
CLIENT_BXL = 111222333
CLIENT_PARIS = 444555666

CMD_BXL = {"order_id": "BXL01", "user_id": CLIENT_BXL, "status": "pending",
           "city": "Bruxelles", "country": "🇧🇪 Belgique",
           "address": "12 rue Neuve, 1000 Bruxelles",
           "address_lat": 50.8466, "address_lon": 4.3528,
           "cart": {"❄️ COCA 1G": 2}, "total": 200, "display_currency": "€",
           "payment": "💵 Cash — EUR", "created_at": webapp._now_iso(),
           # Tout ce qui suit ne doit JAMAIS ressortir côté livreur.
           "user_name": "Jean Dupont", "username": "jean_dupont",
           "selfie_b64": base64.b64encode(b"\xff\xd8\xff-photo-du-client").decode(),
           "phone": "+32470112233", "lang": "fr"}
CMD_PARIS = dict(CMD_BXL, order_id="PAR01", user_id=CLIENT_PARIS, city="Paris",
                 country="🇫🇷 France", user_name="Marie Martin",
                 username="marie", address="3 rue de Rivoli, Paris")

BASE = [dict(CMD_BXL), dict(CMD_PARIS)]
storage._load = lambda: [dict(o) for o in BASE]
storage.get_order = lambda oid: next((dict(o) for o in BASE if o["order_id"] == oid), None)


def maj(oid, upd):
    for o in BASE:
        if o["order_id"] == oid:
            o.update(upd)
            return True
    return False


storage.update_order = webapp.update_order = maj

import github_backup
github_backup.backup_file_async = lambda *a, **k: None
github_backup.backup_binaire_async = lambda *a, **k: None

envois = []


class Rep:
    status_code = 200
    text = "{}"

    def json(self):
        return {"ok": True, "result": {}}


import httpx
httpx.post = lambda url, **kw: (envois.append((url, kw.get("json"))) or Rep())

qui = {"v": LIVREUR}
webapp._verify_init_data = lambda i, t: (
    {"user": json.dumps({"id": qui["v"], "first_name": "X"})} if i else None)

app = webapp.app.test_client()
# Ce qui ne doit JAMAIS sortir : tout ce qui permettrait de recontacter le
# client ailleurs que dans l'application. Le prénom et la photo de remise
# sont autorisés — ils servent à livrer, pas à démarcher.
PII = ["jean_dupont", "+32470112233", str(CLIENT_BXL), "marie"]


def sans_identite(charge, ou=""):
    """Vérifie qu'aucune donnée personnelle ne traîne dans la réponse."""
    brut = json.dumps(charge, ensure_ascii=False)
    fuites = [p for p in PII if p in brut]
    assert not fuites, f"fuite dans {ou} : {fuites}"
    return True


print("=" * 62)

titre(1, "Le mot de passe livreur ouvre un panel distinct")
r = app.post("/api/auth", json={"initData": "x", "password": "BRUXELLES 2026"})
d = r.json
print(f"   ok={d.get('ok')} admin={d.get('admin')} livreur={d.get('livreur')}")
assert d["ok"] and d["livreur"] is True and d["admin"] is False

titre(2, "Il ne voit que les courses de sa zone")
d = app.post("/api/livreur/courses", json={"initData": "x"}).json
ids = [c["order_id"] for c in d["courses"]]
print(f"   zones : {d['zones']}")
print(f"   courses visibles : {ids}  (à traiter : {d['a_traiter']})")
assert ids == ["BXL01"], "Paris ne doit pas apparaître"

titre(3, "Le prénom passe, aucun moyen de recontact ne passe")
c = d["courses"][0]
print(f"   champs reçus : {sorted(c)}")
print(f"   client affiché : {c['client']!r}")
sans_identite(d, "la liste des courses")
assert c["client"] == "Jean Dupont", "le prénom doit être visible"
for interdit in ("user_id", "user_name", "username", "selfie_b64", "phone"):
    assert interdit not in c, f"{interdit} ne doit pas être exposé"
print("   ni pseudo @, ni user_id, ni selfie, ni téléphone")

titre("3b", "Un compte sans prénom ne révèle pas son pseudo à la place")
print("    (user_name retombe sur le pseudo Telegram : piège à éviter)")
for cas, attendu in [
    ({"user_name": "jean_dupont", "username": "jean_dupont"}, ""),
    ({"user_name": "@contactme", "username": ""}, ""),
    ({"user_name": "+32470112233", "username": ""}, ""),
    ({"user_name": "?", "username": "x"}, ""),
    ({"user_name": "Jean", "username": "jean_dupont"}, "Jean"),
]:
    obtenu = webapp._prenom_seul(cas)
    print(f"   {str(cas)[:46]:48s} -> {obtenu!r}")
    assert obtenu == attendu

titre("3c", "Le selfie : il doit voir à qui il remet la commande")
print(f"   has_selfie : {c['has_selfie']}")
assert c["has_selfie"] is True
brut = json.dumps(d, ensure_ascii=False)
assert CMD_BXL["selfie_b64"] not in brut, "le base64 n'a rien à faire dans la liste"
print("   (la photo est servie par sa route, pas glissée dans la liste)")
r = app.get(f"/api/livreur/course/BXL01/selfie?initData=x")
print(f"   photo servie : HTTP {r.status_code} {r.headers.get('Content-Type')} "
      f"{len(r.data)} octets")
assert r.status_code == 200 and r.data == b"\xff\xd8\xff-photo-du-client"

titre("3d", "Mais pas celle d'une commande hors de sa zone")
r = app.get("/api/livreur/course/PAR01/selfie?initData=x")
print(f"   Paris : HTTP {r.status_code}")
assert r.status_code == 404

titre(4, "Mais il a bien ce qu'il faut pour livrer")
print(f"   adresse : {c['address']}")
print(f"   panier  : {c['cart']}  —  {c['total']} {c['display_currency']}  ({c['payment']})")
assert c["address"] and c["cart"] and c["total"]

titre(5, "Il fait avancer la course, étape par étape")
for etape, attendu in [("confirmed", 200), ("delivering", 200), ("delivered", 200)]:
    r = app.post(f"/api/livreur/course/BXL01/status",
                 json={"initData": "x", "status": etape})
    print(f"   {etape:<11s} HTTP {r.status_code}  statut réel : {storage.get_order('BXL01')['status']}")
    assert r.status_code == attendu

titre(6, "Il ne peut pas faire reculer une course")
r = app.post("/api/livreur/course/BXL01/status",
             json={"initData": "x", "status": "confirmed"})
print(f"   livrée -> confirmée : HTTP {r.status_code} ({r.json.get('error')})")
assert r.status_code == 400

titre(7, "Il ne peut pas toucher à une course hors de sa zone")
r = app.post("/api/livreur/course/PAR01/status",
             json={"initData": "x", "status": "confirmed"})
print(f"   Paris : HTTP {r.status_code} ({r.json.get('error')})")
assert r.status_code == 404
assert storage.get_order("PAR01")["status"] == "pending"

titre(8, "Le client est prévenu comme si l'admin avait agi")
statuts = [j.get("chat_id") for _, j in envois if j and "text" in (j or {})]
print(f"   {len(envois)} notification(s) envoyée(s) au client {statuts[:3]}")
assert any(str(CLIENT_BXL) == str(x) for x in statuts)

titre(9, "Il discute avec le client par une référence opaque")
ref = c["chat_ref"]
print(f"   référence : {ref[:16]}…  (ni le user_id, ni un pseudo)")
assert str(CLIENT_BXL) not in ref
r = app.post("/api/chat/send", json={"initData": "x", "chat_ref": ref,
                                     "texte": "Je suis en bas de l'immeuble."})
print(f"   envoi : HTTP {r.status_code} — de « {r.json['message']['de']} »")
assert r.status_code == 200 and r.json["message"]["de"] == "vendeur"

titre(10, "Dans la conversation : le prénom, et rien de plus")
d = app.post("/api/chat/thread", json={"initData": "x", "chat_ref": ref}).json
print(f"   en-tête : « {d.get('titre')} » — {d.get('sous_titre')}")
print(f"   client_id renvoyé : {d.get('client_id')!r}  profil : {d.get('profil')}")
sans_identite(d, "le fil de conversation")
assert d.get("titre") == "Jean Dupont", "le prénom doit s'afficher"
assert d.get("client_id") == "" and not d.get("profil")
print("   il peut lui parler, il ne peut pas le recontacter ailleurs")

titre(11, "Le client répond, le livreur le voit")
qui["v"] = CLIENT_BXL
app.post("/api/chat/send", json={"initData": "x", "texte": "J'arrive !"})
qui["v"] = LIVREUR
d = app.post("/api/chat/thread", json={"initData": "x", "chat_ref": ref}).json
print(f"   {len(d['messages'])} messages : {[m['de'] for m in d['messages']]}")
assert [m["de"] for m in d["messages"]] == ["vendeur", "client"]

titre("11b", "Aucune coordonnée ne circule dans ce fil")
print("    (c'est par là que passerait un détournement de client)")
BLOQUES = [
    ("0470 11 22 33",                 "telephone"),
    ("+32470112233",                  "telephone"),
    ("appelle moi au 04.70.11.22.33", "telephone"),
    ("0 4 7 0 1 1 2 2 3 3",           "telephone"),
    ("écris-moi @jean_livreur",       "pseudo"),
    ("t.me/jeanlivreur",              "lien"),
    ("passe sur whatsapp",            "lien"),
    ("mon insta : instagram.com/x",   "lien"),
]
for texte, motif in BLOQUES:
    r = app.post("/api/chat/send", json={"initData": "x", "chat_ref": ref, "texte": texte})
    d2 = r.json
    print(f"   REFUSÉ  {texte[:30]:32s} {d2.get('motif') or d2.get('error')}")
    assert r.status_code == 400 and d2.get("error") == "contact_interdit"
    assert d2.get("motif") == motif, f"{texte} : motif {d2.get('motif')} au lieu de {motif}"

titre("11c", "Mais la conversation normale n'est pas gênée")
PASSENT = [
    "Je suis en bas, code 1234",
    "Bâtiment B, 3e étage, porte 12",
    "12 rue Neuve, 1000 Bruxelles",
    "J'arrive dans 10 minutes",
    "Commande 140801 bien reçue",
    "Ça fait 340 € au total",
    "Sonnez 2 fois s'il vous plaît",
]
for texte in PASSENT:
    r = app.post("/api/chat/send", json={"initData": "x", "chat_ref": ref, "texte": texte})
    print(f"   passe   {texte[:34]:36s} HTTP {r.status_code}")
    assert r.status_code == 200, f"faux positif sur : {texte}"

titre("11d", "Le client non plus, tant qu'une course est en cours")
BASE.append(dict(CMD_BXL, order_id="BXL99", status="delivering"))
qui["v"] = CLIENT_BXL
r = app.post("/api/chat/send", json={"initData": "x", "texte": "mon num : 0470112233"})
print(f"   course en cours  : HTTP {r.status_code} ({r.json.get('motif')})")
assert r.status_code == 400
# Une fois tout livré, il redialogue normalement avec la boutique.
BASE[-1]["status"] = "delivered"
r = app.post("/api/chat/send", json={"initData": "x", "texte": "mon num : 0470112233"})
print(f"   plus rien en cours : HTTP {r.status_code}")
assert r.status_code == 200
BASE.pop()

titre("11e", "… mais l'owner reste libre d'échanger ce qu'il veut")
qui["v"] = OWNER
app.post("/api/admin/unlock", json={"initData": "x", "password": "RICH PORTER"})
r = app.post("/api/chat/send",
             json={"initData": "x", "client_id": CLIENT_BXL,
                   "texte": "Voici mon numéro direct : 0470 11 22 33"})
print(f"   owner -> client : HTTP {r.status_code}")
assert r.status_code == 200, "l'owner ne doit pas être filtré"
qui["v"] = LIVREUR

titre("11f", "Sa connexion suffit à l'inscrire pour les notifications")
print("    (pas besoin de relever son identifiant Telegram à la main)")
print(f"   destinataires connus : {webapp._destinataires_livreur()}")
assert str(LIVREUR) in webapp._destinataires_livreur()

titre("11g", "Une commande dans sa zone lui arrive directement")
envois.clear()
r = webapp._prevenir_livreur("🛵 test de course", cle_anti_repetition="")
recus = [j for u, j in envois if "sendMessage" in u]
print(f"   {r} envoi(s) — destinataire {recus[0]['chat_id'] if recus else '—'}")
assert r == 1 and str(recus[0]["chat_id"]) == str(LIVREUR)

titre("11h", "Le message de course ne contient aucune identité")
envois.clear()
webapp._prevenir_livreur(
    f"🛵 NOUVELLE COURSE N° BXL01\n📍 12 rue Neuve\n👤 Pour "
    f"{webapp._prenom_seul(CMD_BXL)}\n💰 200 €")
texte = envois[-1][1]["text"]
for ligne in texte.splitlines():
    print(f"   | {ligne}")
sans_identite({"t": texte}, "la notification de course")
assert "Jean Dupont" in texte, "le prénom, lui, est utile au livreur"

titre("11h2", "Reconnaissance au pseudo Telegram")
print("    (un bot ne peut ni ecrire a un inconnu, ni traduire un @pseudo :")
print("     on le reconnait au premier message qu'il envoie)")
os.environ["LIVREUR_USERNAME"] = "yofast17"
webapp._livreurs_connus.clear()
for uid_test, pseudo, attendu in [
    (321321, "quelqu_un_dautre", False),
    (321321, None,               False),
    (777111, "@yofast17",        True),
    (777111, "YoFast17",         True),
]:
    ok = webapp.enregistrer_livreur_par_pseudo(uid_test, pseudo)
    print(f"   uid={uid_test} pseudo={str(pseudo):18s} -> inscrit : {ok}")
    assert ok is attendu
print(f"   destinataires : {webapp._destinataires_livreur()}")
assert webapp._destinataires_livreur() == ["777111"]
os.environ["LIVREUR_USERNAME"] = ""
webapp._livreurs_connus.clear()
webapp._retenir_livreur(LIVREUR)

titre("11i", "LIVREUR_CHAT_ID a le dernier mot s'il est défini")
os.environ["LIVREUR_CHAT_ID"] = "424242, 434343"
print(f"   destinataires : {webapp._destinataires_livreur()}")
assert webapp._destinataires_livreur() == ["424242", "434343"]
os.environ["LIVREUR_CHAT_ID"] = ""

titre(12, "Une référence inventée ne donne accès à rien")
for faux in ["0" * 24, "", webapp._ref_chat("PAR01")]:
    r = app.post("/api/chat/thread", json={"initData": "x", "chat_ref": faux})
    print(f"   {faux[:14]!r:18s} HTTP {r.status_code} ({r.json.get('error')})")
    assert r.status_code == 400, "hors zone ou inconnue : refus attendu"

titre(13, "Sans le mot de passe livreur, aucun accès")
qui["v"] = 999888777
for route in ["/api/livreur/courses", "/api/livreur/course/BXL01/status"]:
    r = app.post(route, json={"initData": "x", "status": "confirmed"})
    print(f"   {route:<38s} HTTP {r.status_code} ({r.json.get('error')})")
    assert r.status_code == 403
r = app.get("/api/livreur/course/BXL01/selfie?initData=x")
print(f"   {'photo du client':<38s} HTTP {r.status_code}")
assert r.status_code == 403

titre(14, "Le livreur n'entre pas dans le panel admin")
qui["v"] = LIVREUR
for route in ["/api/admin/orders", "/api/admin/clients", "/api/chat/threads"]:
    r = app.post(route, json={"initData": "x", "limit": 5})
    print(f"   {route:<24s} HTTP {r.status_code} ({r.json.get('error')})")
    assert r.status_code == 403

titre(15, "L'admin, lui, garde tout")
qui["v"] = OWNER
app.post("/api/admin/unlock", json={"initData": "x", "password": "RICH PORTER"})
d = app.post("/api/admin/orders", json={"initData": "x", "limit": 10}).json
noms = [o.get("user_name") for o in d["orders"]]
print(f"   {len(d['orders'])} commandes, clients : {noms}")
assert "Jean Dupont" in noms and len(d["orders"]) == 2

titre(16, "Verrouiller referme la session du livreur")
qui["v"] = LIVREUR
app.post("/api/livreur/lock", json={"initData": "x"})
r = app.post("/api/livreur/courses", json={"initData": "x"})
print(f"   HTTP {r.status_code} ({r.json.get('error')})")
assert r.status_code == 403

titre(17, "Zone configurable : un pays entier")
os.environ["LIVREUR_ZONES"] = "France"
app.post("/api/auth", json={"initData": "x", "password": "BRUXELLES 2026"})
d = app.post("/api/livreur/courses", json={"initData": "x"}).json
print(f"   zones {d['zones']} -> courses {[c['order_id'] for c in d['courses']]}")
assert [c["order_id"] for c in d["courses"]] == ["PAR01"]
os.environ["LIVREUR_ZONES"] = "Belgique:Bruxelles"

titre(18, "Sans LIVREUR_PASSWORD, le rôle n'existe pas")
os.environ["LIVREUR_PASSWORD"] = ""
r = app.post("/api/livreur/courses", json={"initData": "x"})
print(f"   HTTP {r.status_code} ({r.json.get('error')})")
assert r.status_code == 403
os.environ["LIVREUR_PASSWORD"] = "BRUXELLES 2026"

shutil.rmtree(DOSSIER, ignore_errors=True)
fin()

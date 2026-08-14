"""Accès livreur : ses courses, aucune identité de client.

Le livreur doit pouvoir travailler seul — voir les commandes de sa zone, les
faire avancer, parler au client — sans jamais apprendre qui est ce client.
"""
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
           "selfie_b64": "AAAAPHOTO", "phone": "+32470112233",
           "lang": "fr"}
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
# client ailleurs que dans l'application. Le prénom, lui, est autorisé.
PII = ["jean_dupont", "AAAAPHOTO", "+32470112233", str(CLIENT_BXL), "marie"]


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

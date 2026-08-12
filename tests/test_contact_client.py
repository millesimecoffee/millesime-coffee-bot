"""Bouton « contacter le client » : raccourci vers la conversation."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import preparer, simuler_telegram, titre, fin, OWNER, AUTRE

webapp = preparer(ADMIN_PANEL_PASSWORD="")     # owner direct
uid = {"v": OWNER}
simuler_telegram(webapp, uid)

import storage

AVEC_PSEUDO = {"order_id": "A1", "user_id": 777, "username": "jean_client",
               "user_name": "Jean", "city": "Paris", "country": "🇫🇷 France",
               "status": "pending", "total": 100, "cart": {}}
SANS_PSEUDO = {"order_id": "B2", "user_id": 888, "username": "",
               "user_name": "Marc", "city": "Miami", "country": "🇺🇸 États-Unis",
               "status": "pending", "total": 200, "cart": {},
               "created_at": "2026-08-10T10:00:00+02:00"}
VIEILLE_B2 = dict(SANS_PSEUDO, order_id="B1", created_at="2026-01-01T10:00:00+01:00")

TOUTES = [AVEC_PSEUDO, VIEILLE_B2, SANS_PSEUDO]
storage.get_order = lambda oid: next((dict(o) for o in TOUTES if o["order_id"] == oid), None)
storage._load = lambda: [dict(o) for o in TOUTES]

envois = []


class Reponse:
    status_code = 200
    text = "{}"

    def json(self):
        return {"ok": True, "result": {"username": "MillesimeCoffeeBot"}}


import httpx
httpx.post = lambda url, json=None, timeout=None, **kw: (
    envois.append((url.rsplit("/", 1)[-1], json)) or Reponse())
httpx.get = lambda url, timeout=None, **kw: Reponse()

app = webapp.app.test_client()


def contacter(**corps):
    return app.post("/api/admin/contact", json={"initData": "x", **corps})


print("=" * 62)

titre(1, "Client AVEC pseudo -> lien t.me ouvrable directement")
d = contacter(order_id="A1").get_json()
print(f"   {d}")
assert d["ok"] and d["mode"] == "username" and d["link"] == "https://t.me/jean_client"
assert envois == [], "aucun message inutile ne doit partir"

titre(2, "Client SANS pseudo -> le bot prepare le raccourci")
print("    (tg://user?id= ne peut pas etre ouvert par la Mini App,")
print("     mais fonctionne dans un message envoye par le bot)")
d = contacter(order_id="B2").get_json()
print(f"   reponse : {d}")
assert d["ok"] and d["mode"] == "bot"
methode, payload = envois[-1]
print(f"   methode Telegram : {methode}")
print(f"   destinataire     : {payload['chat_id']} (l'admin connecte)")
assert methode == "sendMessage" and payload["chat_id"] == OWNER

titre(3, "Le message contient le lien direct et un bouton")
lignes = payload["text"].replace("\n\n", "\n").splitlines()
for l in lignes:
    print(f"   | {l}")
bouton = payload["reply_markup"]["inline_keyboard"][0][0]
print(f"   bouton : {bouton['text']!r} -> {bouton['url']}")
assert bouton["url"] == "tg://user?id=888"
assert 'href="tg://user?id=888"' in payload["text"]
assert "Marc" in payload["text"] and "B2" in payload["text"]
assert payload["parse_mode"] == "HTML"

titre(4, "Retour vers le chat du bot pour appuyer sur le bouton")
print(f"   lien renvoye a la Mini App : {d['link']}")
assert d["link"] == "https://t.me/MillesimeCoffeeBot"

titre(5, "Depuis le repertoire clients (sans numero de commande)")
envois.clear()
d = contacter(user_id=888).get_json()
print(f"   {d}")
assert d["ok"] and d["mode"] == "bot"
print(f"   commande citee : {[l for l in envois[-1][1]['text'].splitlines() if 'Commande' in l]}")
assert "B2" in envois[-1][1]["text"], "la commande la plus recente doit etre citee"

titre(6, "Le nom du client est echappe (pas d'injection HTML)")
TOUTES.append({"order_id": "C3", "user_id": 999, "username": "",
               "user_name": "<b>pirate</b>", "status": "pending", "total": 0, "cart": {}})
contacter(order_id="C3")
texte = envois[-1][1]["text"]
print(f"   {[l for l in texte.splitlines() if 'pirate' in l][0]}")
assert "<b>pirate</b>" not in texte and "&lt;b&gt;pirate" in texte

titre(7, "Commande inconnue -> 404 propre")
r = contacter(order_id="INEXISTANT")
print(f"   HTTP {r.status_code} ({r.get_json().get('error')})")
assert r.status_code == 404

titre(8, "Sans droits admin -> refuse")
uid["v"] = AUTRE
r = contacter(order_id="B2")
print(f"   HTTP {r.status_code} ({r.get_json().get('error')})")
assert r.status_code in (401, 403)
uid["v"] = OWNER

titre(9, "Panne d'envoi Telegram -> erreur remontee, pas de faux succes")
class Echec:
    status_code = 403
    text = '{"description":"bot was blocked by the user"}'

    def json(self):
        return {"description": "bot was blocked by the user"}


httpx.post = lambda url, json=None, timeout=None, **kw: Echec()
r = contacter(order_id="B2")
print(f"   HTTP {r.status_code} — {r.get_json().get('detail')}")
assert r.status_code == 502 and r.get_json()["ok"] is False

fin()

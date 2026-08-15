"""Le client annule sa commande lui-même.

Ce qui doit tenir : on n'annule que sa propre commande, on ne peut plus
annuler une commande déjà livrée, la boutique est prévenue à chaque fois, et
le chiffre d'affaires ne compte pas la commande retirée.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import preparer, simuler_telegram, titre, fin, OWNER, AUTRE

webapp = preparer(ADMIN_PANEL_PASSWORD="", OWNER_CHAT_ID="999000",
                  DATA_DIR=tempfile.mkdtemp(prefix="millesime_annul_"))
import github_backup
github_backup.backup_file_async = lambda *a, **k: None

CLIENT = AUTRE
uid = {"v": CLIENT}
simuler_telegram(webapp, uid)

import storage

BASE = {"order_id": "C1", "user_id": CLIENT, "status": "pending", "total": 120,
        "cart": {"❄️ COCA 1G": 2}, "city": "Bruxelles", "country": "🇧🇪 Belgique",
        "created_at": webapp._now_iso(), "user_name": "Alex", "username": "alex",
        "display_currency": "€"}

BASE_DONNEES = {}
ecritures = []


def poser(**champs):
    BASE_DONNEES.clear()
    o = dict(BASE, **champs)
    BASE_DONNEES[o["order_id"]] = o
    ecritures.clear()
    return o


def _update(oid, upd):
    if oid not in BASE_DONNEES:
        return False
    BASE_DONNEES[oid].update(upd)
    ecritures.append((oid, dict(upd)))
    return True


storage.get_order = lambda oid: dict(BASE_DONNEES[oid]) if oid in BASE_DONNEES else None
storage.update_order = _update
storage._load = lambda: [dict(o) for o in BASE_DONNEES.values()]

# Telegram : on enregistre ce qui part au lieu de l'envoyer.
envois = []


class Reponse:
    status_code = 200

    def json(self):
        return {"ok": True}


import httpx
httpx.post = lambda url, **kw: (envois.append(kw.get("json") or {}), Reponse())[1]

app = webapp.app.test_client()


def annuler(oid="C1", init="x"):
    return app.post(f"/api/client/order/{oid}/cancel", json={"initData": init})


print("=" * 62)

titre(1, "Annulation possible a chaque etape tant que rien n'est remis")
for etape in ["pending", "confirmed", "delivering"]:
    poser(status=etape)
    r = annuler()
    d = r.get_json()
    print(f"   {etape:11s} -> HTTP {r.status_code}, statut « {d.get('status')} », "
          f"etait « {d.get('avant')} »")
    assert r.status_code == 200 and d["ok"]
    assert BASE_DONNEES["C1"]["status"] == "cancelled_by_client"
    assert BASE_DONNEES["C1"].get("_cancelled_at"), "l'heure d'annulation est notee"

titre(2, "Une commande livree ne s'annule plus")
poser(status="delivered")
r = annuler()
print(f"   HTTP {r.status_code} ({r.get_json().get('error')})")
assert r.status_code == 409 and r.get_json()["error"] == "trop_tard"
assert BASE_DONNEES["C1"]["status"] == "delivered", "rien n'a bouge"

titre(3, "On n'annule pas la commande d'un autre")
poser(status="pending", user_id=OWNER)
r = annuler()
print(f"   HTTP {r.status_code} ({r.get_json().get('error')})")
assert r.status_code == 403
assert BASE_DONNEES["C1"]["status"] == "pending", "intacte"
assert ecritures == [], "aucune ecriture ne doit passer"

titre(4, "Commande inconnue, sans session, identifiant absurde")
poser(status="pending")
r = annuler("INEXISTANTE")
print(f"   inconnue      -> HTTP {r.status_code}")
assert r.status_code == 404
uid["v"] = None
r = annuler(init="")
print(f"   sans session  -> HTTP {r.status_code}")
assert r.status_code == 401
uid["v"] = CLIENT
for absurde in ["../../etc/passwd", "A" * 300, "%00"]:
    r = annuler(absurde)
    print(f"   {absurde[:18]:20s} -> HTTP {r.status_code}")
    assert r.status_code < 500

titre(5, "Annuler deux fois ne renvoie pas d'erreur et ne renotifie pas")
poser(status="confirmed")
annuler()
envois.clear()
r = annuler()
d = r.get_json()
print(f"   deuxieme passage -> HTTP {r.status_code}, unchanged={d.get('unchanged')}")
print(f"   messages Telegram envoyes : {len(envois)}")
assert r.status_code == 200 and d.get("unchanged") is True
assert envois == [], "la boutique ne doit pas etre prevenue deux fois"

titre(6, "La boutique est prevenue, avec l'etape a laquelle on en etait")
poser(status="delivering")
envois.clear()
annuler()
textes = [e.get("text", "") for e in envois]
print(f"   {len(envois)} message(s) ; destinataires : {[e.get('chat_id') for e in envois]}")
for t in textes:
    print("   " + t.replace("\n", " / ")[:96])
assert envois, "au moins un message doit partir"
assert any("999000" == str(e.get("chat_id")) for e in envois), "l'owner est prevenu"
assert any("ANNUL" in t.upper() for t in textes)
assert any("C1" in t for t in textes), "le numero de commande est dedans"
assert any("livraison" in t for t in textes), "l'etape precedente est rappelee"

titre(7, "Le nom du client est echappe, pas injecte tel quel dans le HTML")
poser(status="pending", user_name="<b>pirate</b>")
envois.clear()
annuler()
t = envois[0].get("text", "")
print(f"   nom rendu : {[l for l in t.split(chr(10)) if 'pirate' in l]}")
assert "&lt;b&gt;pirate&lt;/b&gt;" in t
assert "<b>pirate</b>" not in t

titre(8, "Une commande annulee par le client ne compte pas dans le chiffre")
poser(status="pending", total=500)
annuler()
stats = storage.get_stats()
print(f"   statut final : {BASE_DONNEES['C1']['status']}")
print(f"   chiffre d'affaires : {stats.get('revenue', stats.get('ca', 0))}")
assert BASE_DONNEES["C1"]["status"] in storage._ANNULEES
assert not stats.get("revenue"), "une commande annulee ne rapporte rien"

titre(9, "Une panne de Telegram n'empeche pas l'annulation")
poser(status="confirmed")


def _casse(*a, **k):
    raise RuntimeError("Telegram injoignable")


httpx.post = _casse
r = annuler()
print(f"   HTTP {r.status_code} malgre l'echec de notification")
assert r.status_code == 200
assert BASE_DONNEES["C1"]["status"] == "cancelled_by_client"
httpx.post = lambda url, **kw: (envois.append(kw.get("json") or {}), Reponse())[1]

fin()

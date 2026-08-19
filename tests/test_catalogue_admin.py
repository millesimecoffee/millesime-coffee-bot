"""L'owner édite le catalogue complet depuis l'espace admin.

On vérifie que l'API admin renvoie le catalogue, l'enregistre après validation,
le persiste (survivant à un rechargement du module), le refuse s'il est mal
formé, et n'est accessible qu'à l'owner. Enfin, une ville ajoutée par l'éditeur
doit être immédiatement commandable côté client.
"""
import importlib
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import preparer, simuler_telegram, titre, fin, OWNER, AUTRE

webapp = preparer(ADMIN_PANEL_PASSWORD="",           # admin = owner uniquement
                  PAYMENT_LINK="https://exemple.test/pay",
                  CRYPTO_ETH="0xabc", CRYPTO_USDT="0xdef",
                  DATA_DIR=tempfile.mkdtemp(prefix="millesime_cat_"))
import github_backup
github_backup.backup_file_async = lambda *a, **k: None
github_backup.backup_binaire_async = lambda *a, **k: None

import catalog
import storage
storage.save_order = lambda o: None

import httpx


class Reponse:
    status_code = 200
    text = "{}"

    def json(self):
        return {"ok": True, "result": {}}


httpx.post = lambda *a, **k: Reponse()
httpx.get = lambda *a, **k: Reponse()

uid = {"v": OWNER}
simuler_telegram(webapp, uid)
app = webapp.app.test_client()

print("=" * 62)

titre(1, "L'owner récupère le catalogue complet")
r = app.post("/api/admin/catalog", json={"initData": "x"})
d = r.get_json()
assert r.status_code == 200 and d["ok"], d
snap = d["catalogue"]
nb_pays = len(snap["pays"])
print(f"   {nb_pays} pays reçus ; 1er = {snap['pays'][0]['nom']}")
assert nb_pays >= 10, snap
assert snap["pays"][0]["villes"][0]["produits"], "Paris devrait avoir des produits"

titre(2, "Un non-admin est refusé")
uid["v"] = AUTRE
r = app.post("/api/admin/catalog", json={"initData": "x"})
print(f"   AUTRE -> HTTP {r.status_code} ({r.get_json().get('error')})")
assert r.status_code == 403, r.status_code
r = app.post("/api/admin/catalog/save", json={"initData": "x", "catalogue": snap})
assert r.status_code == 403, "un non-admin ne doit pas pouvoir enregistrer"
uid["v"] = OWNER

titre(3, "L'owner modifie prix + ajoute produit, ville et pays")
snap["pays"][0]["villes"][0]["produits"][0]["prix"] = 111
snap["pays"][0]["villes"][0]["produits"].append({"nom": "🧪 NEW 1G", "prix": 55})
snap["pays"][0]["villes"].append({
    "nom": "Lyon",
    "produits": [{"nom": "❄️ COCA 1G", "prix": 90}],
    "min": {"type": "amount", "value": 50},
    "methodes": ["cash", "crypto"],
    "devises": None,
})
snap["pays"].append({
    "nom": "🇨🇭 Suisse",
    "devises": ["€", "$"],
    "villes": [{"nom": "Genève",
                "produits": [{"nom": "❄️ COCA 1G", "prix": 200}],
                "min": None, "methodes": None, "devises": None}],
})
r = app.post("/api/admin/catalog/save", json={"initData": "x", "catalogue": snap})
d = r.get_json()
assert r.status_code == 200 and d["ok"], d
print(f"   enregistré : {len(d['catalogue']['pays'])} pays")

titre(4, "Les modifications survivent à un rechargement du module")
importlib.reload(catalog)
assert catalog.CATALOG["🇫🇷 France"]["Paris"]["❄️ COCA 1G"] == 111
assert "🧪 NEW 1G" in catalog.CATALOG["🇫🇷 France"]["Paris"]
assert "Lyon" in catalog.CATALOG["🇫🇷 France"]
assert catalog.MIN_ORDER["Lyon"] == {"type": "amount", "value": 50}
assert "🇨🇭 Suisse" in catalog.CATALOG
print("   prix=111, produit ajouté, Lyon + Suisse persistés")

titre(5, "La ville ajoutée est commandable côté client")
def commander(pays, ville, produit, methode="cash"):
    return app.post("/api/finalize_order", json={
        "initData": "x", "country": pays, "city": ville,
        "cart": {produit: 3}, "display_currency": "€",
        "payment": {"method": methode, "currency": "EUR", "label": methode},
        "address": {"text": "12 rue Test", "short": "12 rue Test"},
        "selfie_b64": "",
    })
r = commander("🇫🇷 France", "Lyon", "❄️ COCA 1G")
d = r.get_json()
print(f"   commande Lyon -> HTTP {r.status_code} ok={d.get('ok')}")
assert d.get("ok"), d
# Lyon n'accepte pas « link » (méthodes cash+crypto) → doit être refusé
r = commander("🇫🇷 France", "Lyon", "❄️ COCA 1G", methode="link")
assert r.status_code == 400, "Lyon ne doit pas accepter link"
print("   Lyon accepte cash, refuse link (règle respectée)")

titre(6, "Un catalogue mal formé est refusé avec un message clair")
mauvais = catalog.snapshot()
mauvais["pays"][0]["villes"][0]["produits"][0]["prix"] = -10
r = app.post("/api/admin/catalog/save", json={"initData": "x", "catalogue": mauvais})
d = r.get_json()
print(f"   prix -10 -> HTTP {r.status_code} : {d.get('message')}")
assert r.status_code == 400 and d.get("error") == "invalide", d
assert d.get("message"), "un message d'explication est attendu"
# Le refus ne doit RIEN avoir changé : le prix reste 111
importlib.reload(catalog)
assert catalog.CATALOG["🇫🇷 France"]["Paris"]["❄️ COCA 1G"] == 111, "un refus ne doit rien appliquer"
print("   refus propre : le catalogue n'a pas bougé")

titre(7, "Suppression : retirer une ville et un produit")
snap2 = catalog.snapshot()
fr = next(p for p in snap2["pays"] if p["nom"] == "🇫🇷 France")
fr["villes"] = [v for v in fr["villes"] if v["nom"] != "Lyon"]     # supprime Lyon
paris = next(v for v in fr["villes"] if v["nom"] == "Paris")
paris["produits"] = [p for p in paris["produits"] if p["nom"] != "🧪 NEW 1G"]
r = app.post("/api/admin/catalog/save", json={"initData": "x", "catalogue": snap2})
assert r.get_json()["ok"], r.get_json()
importlib.reload(catalog)
assert "Lyon" not in catalog.CATALOG["🇫🇷 France"]
assert "Lyon" not in catalog.MIN_ORDER, "le minimum de Lyon doit partir avec la ville"
assert "🧪 NEW 1G" not in catalog.CATALOG["🇫🇷 France"]["Paris"]
print("   Lyon et 🧪 NEW 1G supprimés, minimum nettoyé")

fin()

"""Certaines villes n'acceptent qu'une partie des moyens de paiement.

Barcelone, Marbella et Malaga ne prennent que du liquide, en euros. Le panneau
client masque déjà le reste, mais rien n'empêche d'envoyer la requête à la
main : c'est le serveur qui doit refuser, et c'est ce qu'on vérifie ici.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import preparer, simuler_telegram, titre, fin, OWNER, AUTRE

webapp = preparer(ADMIN_PANEL_PASSWORD="", PAYMENT_LINK="https://exemple.test/pay",
                  CRYPTO_ETH="0xabc", CRYPTO_USDT="0xdef",
                  DATA_DIR=tempfile.mkdtemp(prefix="millesime_pay_"))
import github_backup
github_backup.backup_file_async = lambda *a, **k: None
github_backup.backup_binaire_async = lambda *a, **k: None

import catalog
import storage
storage.save_order = lambda o: None

uid = {"v": AUTRE}
simuler_telegram(webapp, uid)


class Reponse:
    status_code = 200
    text = "{}"

    def json(self):
        return {"ok": True, "result": {}}


import httpx
httpx.post = lambda *a, **k: Reponse()
httpx.get = lambda *a, **k: Reponse()

app = webapp.app.test_client()

CASH_SEUL = [("🇪🇸 Espagne", "Barcelone"), ("🇪🇸 Espagne", "Marbella"),
             ("🇪🇸 Espagne", "Malaga")]

print("=" * 66)

titre(1, "Le catalogue connait la regle")
for pays, ville in CASH_SEUL:
    m = catalog.get_payment_methods(pays, ville)
    d = catalog.get_currencies(pays, ville)
    print(f"   {ville:12s} -> moyens {m}  devises {d}")
    assert m == ["cash"], m
    assert d == ["€"], d

titre(2, "Les autres villes gardent tous les moyens actifs")
# « link » peut etre suspendu (stand-by) : l'attendu se derive du meme filtre
# que le catalogue, donc le test reste juste qu'il soit actif ou non.
attendu = [m for m in catalog.METHODES_PAIEMENT if m not in catalog._moyens_standby()]
for pays, villes in catalog.CATALOG.items():
    for ville in villes:
        if (pays, ville) in CASH_SEUL:
            continue
        m = catalog.get_payment_methods(pays, ville)
        assert m == attendu, f"{ville} : {m}"
print(f"   {sum(len(v) for v in catalog.CATALOG.values()) - 3} autres villes : "
      f"{attendu}")

titre(3, "Une commande en carte ou en crypto est REFUSEE sur ces villes")


def commander(pays, ville, methode, devise="EUR", affichage="€"):
    produit = list(catalog.CATALOG[pays][ville])[0]
    return app.post("/api/finalize_order", json={
        "initData": "x", "country": pays, "city": ville,
        "cart": {produit: 3}, "display_currency": affichage,
        "payment": {"method": methode, "currency": devise, "label": methode},
        "address": {"text": "12 rue Test", "short": "12 rue Test"},
        "selfie_b64": "",
    })


passes = []
for pays, ville in CASH_SEUL:
    for methode in ("link", "crypto"):
        r = commander(pays, ville, methode)
        d = r.get_json()
        etat = "refuse" if r.status_code == 400 else "*** PASSE ***"
        print(f"   {ville:12s} {methode:7s} -> HTTP {r.status_code} {etat} "
              f"{d.get('error') or ''}")
        if r.status_code != 400:
            passes.append(f"{ville}/{methode}")
assert not passes, f"passes : {passes}"

titre(4, "Le liquide en euros passe")
for pays, ville in CASH_SEUL:
    r = commander(pays, ville, "cash", "EUR", "€")
    d = r.get_json()
    print(f"   {ville:12s} cash EUR -> HTTP {r.status_code} ok={d.get('ok')}")
    assert d.get("ok"), d

titre(5, "Le liquide dans une autre devise est refuse")
for pays, ville in CASH_SEUL:
    r = commander(pays, ville, "cash", "GBP", "€")
    print(f"   {ville:12s} cash GBP -> HTTP {r.status_code} "
          f"{r.get_json().get('error') or ''}")
    assert r.status_code == 400

titre(6, "La devise d'affichage retombe sur l'euro")
produit = list(catalog.CATALOG["🇪🇸 Espagne"]["Barcelone"])[0]
r = app.post("/api/finalize_order", json={
    "initData": "x", "country": "🇪🇸 Espagne", "city": "Barcelone",
    "cart": {produit: 3}, "display_currency": "$",
    "payment": {"method": "cash", "currency": "EUR"},
    "address": {"text": "12 rue Test"}, "selfie_b64": ""})
d = r.get_json()
print(f"   affichage demande « $ » -> commande {'acceptee' if d.get('ok') else 'refusee'}")
assert d.get("ok")

titre(7, "Une ville sans regle particuliere accepte toujours tout")
r = commander("🇫🇷 France", "Paris", "crypto")
print(f"   Paris crypto -> HTTP {r.status_code} ok={r.get_json().get('ok')}")
assert r.get_json().get("ok"), "les autres villes ne doivent pas etre touchees"

titre(8, "La configuration envoyee au client porte la regle")
d = app.post("/api/auth", json={"initData": "x", "password": "PLATA O PLOMO"}).get_json()
regles = d.get("city_payment") or {}
print(f"   {len(regles)} ville(s) decrite(s) (seulement les particulieres)")
for pays, ville in CASH_SEUL:
    r = regles.get(f"{pays}|{ville}") or {}
    print(f"   {ville:12s} -> {r}")
    assert r.get("methodes") == ["cash"] and r.get("devises") == ["€"]
# Paris n'a pas de regle particuliere : il ne doit PAS figurer dans la liste,
# sinon le panneau croirait sa liste de devises restreinte.
print(f"   Paris present : {'🇫🇷 France|Paris' in regles}")
assert "🇫🇷 France|Paris" not in regles
assert len(regles) == len(CASH_SEUL)

fin()

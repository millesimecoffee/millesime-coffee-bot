"""On n'encaisse que la monnaie du pays.

Euro dans la zone euro, livre en Angleterre, dollar aux États-Unis, baht en
Thaïlande, dirham au Maroc. Le panneau ne propose que ça, et surtout le
serveur refuse le reste — une requête forgée à la main ne doit pas faire
entrer des livres sterling à Paris.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import preparer, simuler_telegram, titre, fin, AUTRE

webapp = preparer(ADMIN_PANEL_PASSWORD="", PAYMENT_LINK="https://exemple.test/pay",
                  DATA_DIR=tempfile.mkdtemp(prefix="millesime_dev_"))
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

# Ce que le client a demandé, pays par pays.
ATTENDU = {
    "🇫🇷 France": "€", "🇧🇪 Belgique": "€", "🇳🇱 Pays-Bas": "€",
    "🇪🇸 Espagne": "€", "🇮🇹 Italie": "€", "🇬🇷 Grèce": "€",
    "🇵🇹 Portugal": "€", "🇩🇪 Allemagne": "€", "🇭🇷 Croatie": "€",
    "🇺🇸 États-Unis": "$", "🇬🇧 Angleterre": "£",
    "🇹🇭 Thaïlande": "฿", "🇲🇦 Maroc": "dh",
}
CODE = {"€": "EUR", "$": "USD", "£": "GBP", "dh": "MAD", "฿": "THB"}

print("=" * 66)

titre(1, "Chaque pays n'a plus qu'une seule devise")
for pays, devise in ATTENDU.items():
    obtenu = catalog.get_currencies(pays)
    print(f"   {pays:22s} -> {obtenu}")
    assert obtenu == [devise], (pays, obtenu)

titre(2, "Hongrie et Albanie restent ouvertes (non decidees)")
for pays in ("🇭🇺 Hongrie", "🇦🇱 Albanie"):
    obtenu = catalog.get_currencies(pays)
    print(f"   {pays:22s} -> {obtenu}")
    assert len(obtenu) > 1, "elles attendent une decision, pas une devise inventee"


def commander(pays, ville, devise_cash):
    produit = list(catalog.CATALOG[pays][ville])[0]
    mini = catalog.MIN_ORDER.get(ville) or {}
    q = 5 if (mini.get("type") == "amount") else 3
    return app.post("/api/finalize_order", json={
        "initData": "x", "country": pays, "city": ville,
        "cart": {produit: q}, "display_currency": catalog.get_currencies(pays)[0],
        "payment": {"method": "cash", "currency": devise_cash},
        "address": {"text": "12 rue Test"}, "selfie_b64": ""})


titre(3, "La bonne devise passe partout")
for pays, devise in ATTENDU.items():
    ville = list(catalog.CATALOG[pays])[0]
    r = commander(pays, ville, CODE[devise])
    d = r.get_json()
    etat = "accepte" if d.get("ok") else f"REFUSE ({d.get('error')})"
    print(f"   {ville:18s} {CODE[devise]:4s} -> {etat}")
    assert d.get("ok"), (pays, ville, d)

titre(4, "Toute autre devise est REFUSEE par le serveur")
AUTRES = ["EUR", "USD", "GBP", "THB", "MAD", "CHF", "AED"]
passes = []
for pays, devise in ATTENDU.items():
    ville = list(catalog.CATALOG[pays])[0]
    bonne = CODE[devise]
    for code in AUTRES:
        if code == bonne:
            continue
        r = commander(pays, ville, code)
        if r.get_json().get("ok"):
            passes.append(f"{ville}/{code}")
print(f"   {len(ATTENDU) * (len(AUTRES) - 1)} combinaisons interdites testees")
print(f"   passees a tort : {passes or 'aucune'}")
assert not passes, passes

titre(5, "Le message d'erreur dit ce qui est accepte")
r = commander("🇫🇷 France", "Paris", "GBP")
d = r.get_json()
print(f"   Paris en GBP -> HTTP {r.status_code} {d.get('error')} {d.get('acceptees')}")
assert r.status_code == 400 and d.get("acceptees") == ["EUR"]

titre(6, "La devise d'affichage suit aussi")
d = app.post("/api/auth", json={"initData": "x", "password": "PLATA O PLOMO"}).get_json()
cc = d.get("country_currencies") or {}
for pays, devise in ATTENDU.items():
    assert cc.get(pays) == [devise], (pays, cc.get(pays))
print(f"   {len(ATTENDU)} pays : une seule devise proposee a l'affichage")

titre(7, "Une devise d'affichage aberrante retombe sur celle du pays")
produit = list(catalog.CATALOG["🇹🇭 Thaïlande"]["Bangkok"])[0] \
    if "Bangkok" in catalog.CATALOG["🇹🇭 Thaïlande"] \
    else list(catalog.CATALOG["🇹🇭 Thaïlande"][list(catalog.CATALOG["🇹🇭 Thaïlande"])[0]])[0]
ville_th = list(catalog.CATALOG["🇹🇭 Thaïlande"])[0]
r = app.post("/api/finalize_order", json={
    "initData": "x", "country": "🇹🇭 Thaïlande", "city": ville_th,
    "cart": {produit: 5}, "display_currency": "£",     # jamais accepte la-bas
    "payment": {"method": "cash", "currency": "THB"},
    "address": {"text": "12 rue Test"}, "selfie_b64": ""})
print(f"   affichage « £ » en Thailande -> {'accepte' if r.get_json().get('ok') else 'refuse'}")
assert r.get_json().get("ok"), "l'affichage retombe sur le baht, la commande passe"

titre(8, "Les villes a regle particuliere gardent la leur")
for pays, ville in catalog.PAIEMENT_PAR_VILLE:
    regle = catalog.PAIEMENT_PAR_VILLE[(pays, ville)]
    obtenu = catalog.get_currencies(pays, ville)
    print(f"   {ville:12s} -> {obtenu} (regle ville)")
    assert obtenu == regle["devises"]

fin()

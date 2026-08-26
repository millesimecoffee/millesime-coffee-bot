"""Paiement carte via lien SumUp hébergé.

L'app demande un lien de paiement ; le serveur recalcule le montant depuis le
catalogue (jamais celui du client), crée un checkout SumUp et renvoie l'URL
hébergée. L'API SumUp est simulée ici — le test tourne sans réseau ni clé.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import preparer, simuler_telegram, titre, fin, AUTRE

webapp = preparer(ADMIN_PANEL_PASSWORD="", SUMUP_API_KEY="sup_sk_test",
                  SUMUP_MERCHANT_CODE="MTEST",
                  DATA_DIR=tempfile.mkdtemp(prefix="millesime_sumup_"))
import github_backup
github_backup.backup_file_async = lambda *a, **k: None
import storage
storage.save_order = lambda o: None
import catalog

# Faux SumUp : capture le corps envoyé, renvoie une URL hébergée.
envois = []
import httpx


class R:
    def __init__(self, code, data):
        self.status_code = code
        self._d = data
        self.text = str(data)

    def json(self):
        return self._d


httpx.post = lambda url, **kw: (envois.append((url, kw.get("json"))) or
                                R(201, {"id": "chk_1", "status": "PENDING",
                                        "hosted_checkout_url": "https://checkout.sumup.com/pay/c-TEST"}))

uid = {"v": AUTRE}
simuler_telegram(webapp, uid)
app = webapp.app.test_client()

print("=" * 62)

titre(1, "Un panier valide renvoie un lien SumUp au bon montant")
prods = list(catalog.CATALOG["🇫🇷 France"]["Paris"].items())
cart = {prods[0][0]: 1, prods[1][0]: 2}
attendu = round(prods[0][1] + prods[1][1] * 2, 2)
r = app.post("/api/pay/sumup_link",
             json={"initData": "x", "country": "🇫🇷 France", "city": "Paris", "cart": cart})
d = r.get_json()
print(f"   HTTP {r.status_code} · montant {d.get('amount')} (attendu {attendu}) · url {d.get('url')}")
assert r.status_code == 200 and d["ok"] and abs(d["amount"] - attendu) < 0.01, d
assert d["url"] == "https://checkout.sumup.com/pay/c-TEST"
# Le montant transmis à SumUp est celui recalculé côté serveur, en EUR, hébergé.
_, corps = envois[-1]
assert abs(corps["amount"] - attendu) < 0.01, corps
assert corps["currency"] == "EUR" and corps["hosted_checkout"]["enabled"] is True
assert corps["merchant_code"] == "MTEST"
print("   transmis à SumUp :", corps["amount"], corps["currency"], "· merchant", corps["merchant_code"])

titre(2, "Le montant envoyé par le client est ignoré")
# On glisse un faux « amount » énorme : il ne doit rien changer.
r = app.post("/api/pay/sumup_link",
             json={"initData": "x", "country": "🇫🇷 France", "city": "Paris",
                   "cart": cart, "amount": 9999})
assert abs(envois[-1][1]["amount"] - attendu) < 0.01, "le montant client ne doit jamais être utilisé"
print("   montant client 9999 ignoré → SumUp reçoit", envois[-1][1]["amount"])

titre(3, "Une ville cash-only refuse la carte")
b = list(catalog.CATALOG["🇪🇸 Espagne"]["Barcelone"])[0]
r = app.post("/api/pay/sumup_link",
             json={"initData": "x", "country": "🇪🇸 Espagne", "city": "Barcelone", "cart": {b: 1}})
print(f"   Barcelone -> HTTP {r.status_code} ({r.get_json().get('error')})")
assert r.status_code == 400 and r.get_json().get("error") == "paiement_non_accepte"

titre(4, "Panier vide refusé")
r = app.post("/api/pay/sumup_link",
             json={"initData": "x", "country": "🇫🇷 France", "city": "Paris", "cart": {}})
print(f"   panier vide -> HTTP {r.status_code} ({r.get_json().get('error')})")
assert r.status_code == 400 and r.get_json().get("error") == "empty_cart"

titre(5, "Sans clé SumUp configurée : paiement carte indisponible")
os.environ.pop("SUMUP_API_KEY", None)
r = app.post("/api/pay/sumup_link",
             json={"initData": "x", "country": "🇫🇷 France", "city": "Paris", "cart": cart})
print(f"   sans clé -> HTTP {r.status_code} ({r.get_json().get('error')})")
assert r.status_code == 503 and r.get_json().get("error") == "indisponible"

fin()

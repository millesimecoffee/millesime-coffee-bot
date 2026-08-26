"""Paiement carte via lien SumUp hébergé + vérification automatique.

Le serveur recalcule le montant depuis le catalogue (jamais celui du client),
crée un checkout SumUp, et — surtout — ne crée la commande que si SumUp confirme
que le checkout est PAID pour le BON montant. L'API SumUp est simulée ici.
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
github_backup.backup_binaire_async = lambda *a, **k: None
import storage
storage.save_order = lambda o: None
import catalog


class R:
    def __init__(self, code, data):
        self.status_code = code
        self._d = data
        self.text = str(data)

    def json(self):
        return self._d


# État SumUp simulé, piloté par chaque test.
etat = {"status": "PENDING", "amount": 0.0}
envois = []

import httpx


def faux_post(url, **kw):
    if "checkouts" in url:
        envois.append(kw.get("json"))
        return R(201, {"id": "chk_1", "status": "PENDING",
                       "hosted_checkout_url": "https://checkout.sumup.com/pay/c-TEST"})
    return R(200, {"ok": True, "result": {}})          # Telegram & co.


def faux_get(url, **kw):
    return R(200, {"status": etat["status"], "amount": etat["amount"],
                   "currency": "EUR", "transactions": []})


httpx.post = faux_post
httpx.get = faux_get

uid = {"v": AUTRE}
simuler_telegram(webapp, uid)
app = webapp.app.test_client()

PROD = list(catalog.CATALOG["🇫🇷 France"]["Paris"])[0]
PRIX = catalog.CATALOG["🇫🇷 France"]["Paris"][PROD]

print("=" * 62)

titre(1, "Le lien SumUp est créé au bon montant et renvoie un checkout_id")
cart = {PROD: 2}
attendu = round(PRIX * 2, 2)
r = app.post("/api/pay/sumup_link",
             json={"initData": "x", "country": "🇫🇷 France", "city": "Paris", "cart": cart})
d = r.get_json()
print(f"   montant {d.get('amount')} (attendu {attendu}) · id {d.get('checkout_id')}")
assert d["ok"] and abs(d["amount"] - attendu) < 0.01 and d["checkout_id"] == "chk_1"
assert abs(envois[-1]["amount"] - attendu) < 0.01 and envois[-1]["currency"] == "EUR"


def finalize_link(qte, sumup_id="chk_1"):
    return app.post("/api/finalize_order", json={
        "initData": "x", "country": "🇫🇷 France", "city": "Paris",
        "cart": {PROD: qte}, "display_currency": "€",
        "payment": {"method": "link", "sumup_id": sumup_id, "label": "Carte"},
        "address": {"text": "12 rue Test", "short": "12 rue Test"}, "selfie_b64": "",
    })


total = round(PRIX * 2, 2)

titre(2, "Commande carte REFUSÉE tant que SumUp n'a pas confirmé (PENDING)")
etat.update(status="PENDING", amount=total)
r = finalize_link(2)
print(f"   PENDING -> HTTP {r.status_code} ({r.get_json().get('error')} / {r.get_json().get('statut')})")
assert r.status_code == 402 and r.get_json().get("error") == "paiement_non_confirme"

titre(3, "Commande carte ACCEPTÉE quand SumUp confirme PAID au bon montant")
etat.update(status="PAID", amount=total)
r = finalize_link(2)
print(f"   PAID -> HTTP {r.status_code} ok={r.get_json().get('ok')} num={r.get_json().get('order_id')}")
assert r.get_json().get("ok") is True

titre(4, "PAID mais MAUVAIS montant → refusée")
etat.update(status="PAID", amount=total + 50)
r = finalize_link(2)
print(f"   montant faux -> HTTP {r.status_code} statut={r.get_json().get('statut')}")
assert r.status_code == 402 and r.get_json().get("statut") == "montant"

titre(5, "Sans checkout_id → refusée (aucune preuve de paiement)")
etat.update(status="PAID", amount=total)
r = finalize_link(2, sumup_id="")
print(f"   sans id -> HTTP {r.status_code} statut={r.get_json().get('statut')}")
assert r.status_code == 402 and r.get_json().get("statut") == "absent"

titre(6, "L'endpoint de statut reflète l'état SumUp")
etat.update(status="PAID", amount=total)
r = app.post("/api/pay/sumup_status", json={"initData": "x", "checkout_id": "chk_1"})
assert r.get_json().get("paid") is True
etat.update(status="PENDING")
r = app.post("/api/pay/sumup_status", json={"initData": "x", "checkout_id": "chk_1"})
assert r.get_json().get("paid") is False
print("   PAID -> paid=True ; PENDING -> paid=False")

titre(7, "Le liquide n'est pas soumis à la vérification SumUp")
r = app.post("/api/finalize_order", json={
    "initData": "x", "country": "🇫🇷 France", "city": "Paris",
    "cart": {PROD: 2}, "display_currency": "€",
    "payment": {"method": "cash", "currency": "EUR", "label": "Cash"},
    "address": {"text": "12 rue Test", "short": "12 rue Test"}, "selfie_b64": "",
})
print(f"   cash -> HTTP {r.status_code} ok={r.get_json().get('ok')}")
assert r.get_json().get("ok") is True

titre(8, "Sans clé SumUp : paiement carte indisponible")
os.environ.pop("SUMUP_API_KEY", None)
r = app.post("/api/pay/sumup_link",
             json={"initData": "x", "country": "🇫🇷 France", "city": "Paris", "cart": cart})
print(f"   sans clé -> HTTP {r.status_code} ({r.get_json().get('error')})")
assert r.status_code == 503 and r.get_json().get("error") == "indisponible"

fin()

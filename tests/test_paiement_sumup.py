"""Paiement carte via lien SumUp + vérification NON bloquante (statut attaché).

Le serveur recalcule le montant depuis le catalogue, crée un checkout SumUp,
puis — à la finalisation — vérifie l'encaissement et ATTACHE le statut à la
commande sans jamais la perdre (l'owner reçoit toujours la commande). Un mode
strict (SUMUP_STRICT) permet, si voulu, de refuser une carte non confirmée.
L'API SumUp est simulée ici.
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
saved = []
storage.save_order = lambda o: saved.append(o)
import catalog


class R:
    def __init__(self, code, data):
        self.status_code = code
        self._d = data
        self.text = str(data)

    def json(self):
        return self._d


etat = {"status": "PENDING", "amount": 0.0}
envois = []
import httpx
httpx.post = lambda url, **kw: (envois.append(kw.get("json")) or
                                R(201, {"id": "chk_1", "status": "PENDING",
                                        "hosted_checkout_url": "https://checkout.sumup.com/pay/c-TEST"})) \
    if "checkouts" in url else R(200, {"ok": True, "result": {}})
httpx.get = lambda url, **kw: R(200, {"status": etat["status"], "amount": etat["amount"],
                                      "currency": "EUR", "transactions": []})

uid = {"v": AUTRE}
simuler_telegram(webapp, uid)
app = webapp.app.test_client()

PROD = list(catalog.CATALOG["🇫🇷 France"]["Paris"])[0]
PRIX = catalog.CATALOG["🇫🇷 France"]["Paris"][PROD]
total = round(PRIX * 2, 2)


def finalize_link(sumup_id="chk_1"):
    return app.post("/api/finalize_order", json={
        "initData": "x", "country": "🇫🇷 France", "city": "Paris",
        "cart": {PROD: 2}, "display_currency": "€",
        "payment": {"method": "link", "sumup_id": sumup_id, "label": "Carte"},
        "address": {"text": "12 rue Test", "short": "12 rue Test"}, "selfie_b64": "",
    })


print("=" * 62)

titre(1, "Le lien SumUp est créé au bon montant et renvoie un checkout_id")
r = app.post("/api/pay/sumup_link",
             json={"initData": "x", "country": "🇫🇷 France", "city": "Paris", "cart": {PROD: 2}})
d = r.get_json()
print(f"   montant {d.get('amount')} (attendu {total}) · id {d.get('checkout_id')}")
assert d["ok"] and abs(d["amount"] - total) < 0.01 and d["checkout_id"] == "chk_1"

titre(2, "Par défaut : commande carte NON payée → reçue quand même, marquée « à vérifier »")
etat.update(status="PENDING", amount=total)
saved.clear()
r = finalize_link()
d = r.get_json()
print(f"   PENDING -> HTTP {r.status_code} ok={d.get('ok')} · verified={saved[-1]['payment_verified']} statut={saved[-1]['payment_status']}")
assert r.status_code == 200 and d["ok"] is True
assert saved[-1]["payment_verified"] is False and saved[-1]["payment_status"] == "PENDING"

titre(3, "Par défaut : commande carte PAYÉE → reçue, marquée vérifiée")
etat.update(status="PAID", amount=total)
saved.clear()
r = finalize_link()
print(f"   PAID -> HTTP {r.status_code} · verified={saved[-1]['payment_verified']}")
assert r.get_json()["ok"] and saved[-1]["payment_verified"] is True

titre(4, "Par défaut : PAYÉE mais mauvais montant → reçue, marquée « à vérifier »")
etat.update(status="PAID", amount=total + 50)
saved.clear()
r = finalize_link()
print(f"   montant faux -> HTTP {r.status_code} · verified={saved[-1]['payment_verified']} statut={saved[-1]['payment_status']}")
assert r.get_json()["ok"] and saved[-1]["payment_verified"] is False and saved[-1]["payment_status"] == "montant"

titre(5, "Mode strict (SUMUP_STRICT=1) : carte non confirmée → REFUSÉE")
os.environ["SUMUP_STRICT"] = "1"
etat.update(status="PENDING", amount=total)
r = finalize_link()
print(f"   strict + PENDING -> HTTP {r.status_code} ({r.get_json().get('error')})")
assert r.status_code == 402 and r.get_json().get("error") == "paiement_non_confirme"
etat.update(status="PAID", amount=total)
r = finalize_link()
print(f"   strict + PAID -> HTTP {r.status_code} ok={r.get_json().get('ok')}")
assert r.get_json().get("ok") is True
os.environ.pop("SUMUP_STRICT", None)

titre(6, "Le liquide n'est jamais soumis à la vérification SumUp")
saved.clear()
r = app.post("/api/finalize_order", json={
    "initData": "x", "country": "🇫🇷 France", "city": "Paris",
    "cart": {PROD: 2}, "display_currency": "€",
    "payment": {"method": "cash", "currency": "EUR", "label": "Cash"},
    "address": {"text": "12 rue Test", "short": "12 rue Test"}, "selfie_b64": "",
})
print(f"   cash -> HTTP {r.status_code} · verified={saved[-1]['payment_verified']}")
assert r.get_json().get("ok") and saved[-1]["payment_verified"] is None

titre(7, "Sans clé SumUp : paiement carte indisponible (création du lien)")
os.environ.pop("SUMUP_API_KEY", None)
r = app.post("/api/pay/sumup_link",
             json={"initData": "x", "country": "🇫🇷 France", "city": "Paris", "cart": {PROD: 2}})
print(f"   sans clé -> HTTP {r.status_code} ({r.get_json().get('error')})")
assert r.status_code == 503 and r.get_json().get("error") == "indisponible"

fin()

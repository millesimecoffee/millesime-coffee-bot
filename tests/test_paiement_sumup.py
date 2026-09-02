"""Paiement carte SumUp : vérification non bloquante + anti-rejeu + robustesse.

- Le montant est recalculé serveur, le statut du paiement est attaché à la
  commande (l'owner reçoit toujours la commande).
- Un même checkout payé ne peut valider qu'UNE commande (anti double-dépense).
- Si la sauvegarde échoue, la commande n'est pas créée (500) et le checkout
  n'est pas « brûlé » (le client peut réessayer).
L'API SumUp est simulée.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import preparer, simuler_telegram, titre, fin, AUTRE

webapp = preparer(ADMIN_PANEL_PASSWORD="", SUMUP_API_KEY="sup_sk_test",
                  SUMUP_MERCHANT_CODE="MTEST",
                  DATA_DIR=tempfile.mkdtemp(prefix="millesime_sumup_"))
webapp._rate_limited = lambda *a, **k: False        # anti-flood testé ailleurs
import github_backup
github_backup.backup_file_async = lambda *a, **k: None
github_backup.backup_binaire_async = lambda *a, **k: None
import storage
saved = []
_vrai_save = storage.save_order
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
                                R(201, {"id": "chk", "status": "PENDING",
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
_n = {"i": 0}


def finalize(sumup_id=None):
    if sumup_id is None:
        _n["i"] += 1
        sumup_id = f"chk_{_n['i']}"
    return app.post("/api/finalize_order", json={
        "initData": "x", "country": "🇫🇷 France", "city": "Paris",
        "cart": {PROD: 2}, "display_currency": "€",
        "payment": {"method": "link", "sumup_id": sumup_id, "label": "Carte"},
        "address": {"text": "12 rue Test", "short": "12 rue Test"}, "selfie_b64": "",
    })


print("=" * 62)

titre(1, "Lien SumUp au bon montant + checkout_id renvoyé")
r = app.post("/api/pay/sumup_link",
             json={"initData": "x", "country": "🇫🇷 France", "city": "Paris", "cart": {PROD: 2}})
d = r.get_json()
assert d["ok"] and abs(d["amount"] - total) < 0.01 and d.get("checkout_id") == "chk"
print(f"   montant {d['amount']} · id {d['checkout_id']}")

titre(2, "Carte NON payée → reçue quand même, marquée « à vérifier »")
etat.update(status="PENDING", amount=total)
saved.clear()
r = finalize()
assert r.status_code == 200 and r.get_json()["ok"] is True
assert saved[-1]["payment_verified"] is False and saved[-1]["payment_status"] == "PENDING"
print(f"   verified={saved[-1]['payment_verified']} statut={saved[-1]['payment_status']}")

titre(3, "Carte PAYÉE → reçue, vérifiée, sumup_id tracé")
etat.update(status="PAID", amount=total)
saved.clear()
r = finalize("chk_paye_A")
assert r.get_json()["ok"] and saved[-1]["payment_verified"] is True
assert saved[-1]["sumup_id"] == "chk_paye_A"
print(f"   verified={saved[-1]['payment_verified']} sumup_id={saved[-1]['sumup_id']}")

titre(4, "ANTI DOUBLE-DÉPENSE : rejouer le même checkout payé → refusé (409)")
saved.clear()
r = finalize("chk_paye_A")     # déjà consommé au titre 3
print(f"   rejeu chk_paye_A -> HTTP {r.status_code} ({r.get_json().get('error')})")
assert r.status_code == 409 and r.get_json().get("error") == "paiement_deja_utilise"
assert not saved, "aucune commande ne doit être créée sur un rejeu"

titre(5, "PAYÉE mais mauvais montant → reçue, marquée « à vérifier »")
etat.update(status="PAID", amount=total + 50)
saved.clear()
r = finalize()
assert r.get_json()["ok"] and saved[-1]["payment_verified"] is False and saved[-1]["payment_status"] == "montant"
print(f"   verified={saved[-1]['payment_verified']} statut={saved[-1]['payment_status']}")

titre(6, "Mode strict : carte non confirmée → refusée ; payée → acceptée")
os.environ["SUMUP_STRICT"] = "1"
etat.update(status="PENDING", amount=total)
r = finalize()
assert r.status_code == 402 and r.get_json().get("error") == "paiement_non_confirme"
etat.update(status="PAID", amount=total)
r = finalize("chk_strict_ok")
assert r.get_json().get("ok") is True
os.environ.pop("SUMUP_STRICT", None)
print("   PENDING->402 ; PAID->200")

titre(7, "Sauvegarde en échec → 500, et le checkout n'est PAS brûlé (réessai OK)")
etat.update(status="PAID", amount=total)
def _boom(o):
    raise RuntimeError("insert refusé")
storage.save_order = _boom
r = finalize("chk_retry")
print(f"   save échoue -> HTTP {r.status_code} ({r.get_json().get('error')})")
assert r.status_code == 500 and r.get_json().get("error") == "save_failed"
storage.save_order = lambda o: saved.append(o)   # rétabli
saved.clear()
r = finalize("chk_retry")        # le même id doit repasser (non consommé)
assert r.get_json().get("ok") and saved[-1]["payment_verified"] is True
print("   réessai avec le même id -> 200 (checkout non consommé après un save raté)")

titre(8, "Le liquide n'est jamais soumis à la vérification SumUp")
saved.clear()
r = app.post("/api/finalize_order", json={
    "initData": "x", "country": "🇫🇷 France", "city": "Paris",
    "cart": {PROD: 2}, "display_currency": "€",
    "payment": {"method": "cash", "currency": "EUR", "label": "Cash"},
    "address": {"text": "12 rue Test", "short": "12 rue Test"}, "selfie_b64": "",
})
assert r.get_json().get("ok") and saved[-1]["payment_verified"] is None
print("   cash -> verified=None")

titre(9, "Sans clé SumUp : création du lien indisponible")
os.environ.pop("SUMUP_API_KEY", None)
r = app.post("/api/pay/sumup_link",
             json={"initData": "x", "country": "🇫🇷 France", "city": "Paris", "cart": {PROD: 2}})
assert r.status_code == 503 and r.get_json().get("error") == "indisponible"
print("   sans clé -> 503")

fin()

"""Gardes de sécurité ajoutés après l'audit.

- /api/finalize_order est rate-limité (anti-flood de commandes).
- /api/geocode exige une session (plus de proxy Nominatim ouvert).
- /cityimg ne déclenche un fetch Pexels que pour de vraies villes.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import preparer, simuler_telegram, titre, fin, AUTRE

webapp = preparer(ADMIN_PANEL_PASSWORD="", DATA_DIR=tempfile.mkdtemp(prefix="millesime_sec_"))
import github_backup
github_backup.backup_file_async = lambda *a, **k: None
import storage
storage.save_order = lambda o: None
import catalog

import httpx
httpx.post = lambda *a, **k: type("R", (), {"status_code": 200, "text": "{}",
                                            "json": lambda s: {"ok": True}})()

uid = {"v": AUTRE}
simuler_telegram(webapp, uid)
app = webapp.app.test_client()

PROD = list(catalog.CATALOG["🇫🇷 France"]["Paris"])[0]

print("=" * 62)

titre(1, "/api/finalize_order est rate-limité (le flood est stoppé)")
def commander():
    return app.post("/api/finalize_order", json={
        "initData": "x", "country": "🇫🇷 France", "city": "Paris",
        "cart": {PROD: 2}, "display_currency": "€",
        "payment": {"method": "cash", "currency": "EUR", "label": "Cash"},
        "address": {"text": "12 rue Test", "short": "12 rue Test"}, "selfie_b64": "",
    })
codes = [commander().status_code for _ in range(8)]
n_ok = codes.count(200)
n_429 = codes.count(429)
print(f"   8 commandes rapides -> {n_ok}×200, {n_429}×429 ({codes})")
assert n_429 >= 1, "le rate-limit doit finir par bloquer"
assert n_ok <= 5, "au plus 5 commandes passent dans la fenêtre"

titre(2, "/api/geocode sans session → 401 (plus de proxy Nominatim ouvert)")
r = app.post("/api/geocode", json={"initData": "", "address": "10 rue de Paris"})
print(f"   sans initData -> HTTP {r.status_code} ({r.get_json().get('error')})")
assert r.status_code == 401 and r.get_json().get("error") == "auth_failed"

titre(3, "/cityimg ne cible que de vraies villes")
# _slug_to_city_query renvoie None pour un slug inconnu → aucun fetch Pexels.
assert webapp._slug_to_city_query("villebidonxyz123") is None
assert webapp._slug_to_city_query("paris") is not None
print("   slug inconnu -> None (pas de fetch) ; 'paris' -> reconnu")

fin()

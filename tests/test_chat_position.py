"""Partage de position dans la messagerie de la Mini App.

Une position (lat/lon) part sans texte ni fichier, se range comme message de
type « location », et des coordonnées hors bornes sont refusées.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import preparer, simuler_telegram, titre, fin, AUTRE

webapp = preparer(ADMIN_PANEL_PASSWORD="", DATA_DIR=tempfile.mkdtemp(prefix="millesime_pos_"))
uid = {"v": AUTRE}
simuler_telegram(webapp, uid)

import chat
import storage
storage._load = lambda: []

import httpx
httpx.post = lambda url, **kw: type("R", (), {"status_code": 200, "text": "{}",
                                              "json": lambda s: {"ok": True}})()
import github_backup
github_backup.backup_file_async = lambda *a, **k: None

app = webapp.app.test_client()

print("=" * 62)

titre(1, "Une position part et se range comme message « location »")
r = app.post("/api/chat/send", json={"initData": "x",
                                     "location": {"lat": 41.3874, "lon": 2.1686}})
d = r.get_json()
assert r.status_code == 200 and d["ok"], d
m = d["message"]
print(f"   type={m['type']} · lat={m.get('lat')} · lon={m.get('lon')}")
assert m["type"] == "location"
assert abs(m["lat"] - 41.3874) < 1e-6 and abs(m["lon"] - 2.1686) < 1e-6

titre(2, "Des coordonnées hors bornes sont refusées")
for mauvais in ({"lat": 200, "lon": 2}, {"lat": 41, "lon": 999}, {"lat": "x", "lon": 2}):
    r = app.post("/api/chat/send", json={"initData": "x", "location": mauvais})
    print(f"   {mauvais} -> HTTP {r.status_code} ({r.get_json().get('error')})")
    assert r.status_code == 400 and r.get_json().get("error") == "bad_location"

titre(3, "La position apparaît dans le fil et dans l'aperçu")
r = app.post("/api/chat/thread", json={"initData": "x"})
msgs = r.get_json().get("messages", [])
assert any(x.get("type") == "location" for x in msgs), "la position doit être dans le fil"
assert chat.resume({"type": "location"}) == "📍 Position"
print("   résumé =", chat.resume({"type": "location"}))

titre(4, "La vignette de carte : route protégée, dégradée sans jeton Mapbox")
os.environ.pop("MAPBOX_TOKEN", "")
r = app.get("/api/chat/location_preview?lat=41.3874&lon=2.1686&initData=x")
print(f"   sans jeton -> HTTP {r.status_code} (dégradation propre)")
assert r.status_code == 404       # pas de jeton → pas d'image, mais pas d'erreur 500
r = app.get("/api/chat/location_preview?lat=999&lon=2&initData=x")
assert r.status_code == 400       # coordonnées invalides
print("   coordonnées invalides -> 400")

fin()

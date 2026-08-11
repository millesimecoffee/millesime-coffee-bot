"""Entrée unifiée : un seul écran, deux mots de passe, deux modes."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import preparer, simuler_telegram, titre, fin, OWNER, AUTRE

webapp = preparer()
uid = {"v": AUTRE}
simuler_telegram(webapp, uid)

import storage
storage._load = lambda: []

app = webapp.app.test_client()


def auth(mdp, init="x"):
    webapp._rate_reset(f"pwd:uid:{uid['v']}")
    with webapp._pwd_lock:
        webapp._pwd_attempts.clear()
    return app.post("/api/auth", json={"initData": init, "password": mdp})


def panel_ouvert():
    return app.post("/api/admin/orders", json={"initData": "x", "limit": 1}).status_code


def reverrouiller():
    app.post("/api/admin/lock", json={"initData": "x"})


print("=" * 62)

titre(1, "Compte inconnu + mot de passe CLIENT -> catalogue, pas le panel")
uid["v"] = AUTRE
reverrouiller()
d = auth("PLATA O PLOMO").get_json()
print(f"   ok={d.get('ok')} admin={d.get('admin')} pays={len(d.get('catalog') or {})}")
assert d["ok"] and d["admin"] is False and d["catalog"]
print(f"   acces panel : HTTP {panel_ouvert()} (403 attendu)")
assert panel_ouvert() == 403

titre(2, "Compte inconnu + mot de passe ADMIN -> panel ouvert")
print("    (n'importe quel telephone, n'importe quel compte Telegram)")
reverrouiller()
d = auth("RICH PORTER").get_json()
print(f"   ok={d.get('ok')} admin={d.get('admin')}")
assert d["ok"] and d["admin"] is True
print(f"   acces panel : HTTP {panel_ouvert()} (200 attendu)")
assert panel_ouvert() == 200

titre(3, "Casse et espaces tolerants sur les deux mots de passe")
for variante, admin_attendu in [("rich porter", True), ("Rich Porter", True),
                                ("  RICH   PORTER  ", True),
                                ("plata o plomo", False), ("Plata O Plomo", False)]:
    reverrouiller()
    d = auth(variante).get_json()
    print(f"   {variante!r:22s} ok={d.get('ok')} admin={d.get('admin')}")
    assert d.get("ok") is True and d.get("admin") is admin_attendu

titre(4, "Mot de passe colle ou faux -> refuse")
for faux in ["RICHPORTER", "PLATAOPLOMO", "RICH PORTE", "n'importe quoi", ""]:
    reverrouiller()
    d = auth(faux).get_json()
    print(f"   {faux!r:18s} ok={d.get('ok')}")
    assert d.get("ok") is not True

titre(5, "Sans session Telegram valide -> refuse avant le mot de passe")
r = auth("RICH PORTER", init="")
print(f"   HTTP {r.status_code} ({r.get_json().get('error')})")
assert r.status_code == 401

titre(6, "Le compte owner passe aussi par le mot de passe admin")
uid["v"] = OWNER
reverrouiller()
print(f"   sans saisie : HTTP {panel_ouvert()} (403 attendu)")
assert panel_ouvert() == 403
auth("RICH PORTER")
print(f"   apres saisie : HTTP {panel_ouvert()} (200 attendu)")
assert panel_ouvert() == 200

titre(7, "Verrouiller referme la session")
reverrouiller()
print(f"   HTTP {panel_ouvert()} (403 attendu)")
assert panel_ouvert() == 403

titre(8, "Une entree admin ne declenche pas la notif « client entre »")
appels = []
webapp._notify_owner_client_entry = lambda p: appels.append(1)
uid["v"] = AUTRE
reverrouiller(); auth("RICH PORTER")
print(f"   apres entree admin  : {len(appels)} notification (0 attendu)")
assert len(appels) == 0
reverrouiller(); auth("PLATA O PLOMO")
print(f"   apres entree client : {len(appels)} notification (1 attendu)")
assert len(appels) == 1

titre(9, "Sans ADMIN_PANEL_PASSWORD -> seul le compte owner entre")
os.environ["ADMIN_PANEL_PASSWORD"] = ""
uid["v"] = AUTRE
reverrouiller()
print(f"   compte inconnu : HTTP {panel_ouvert()} (403 attendu)")
assert panel_ouvert() == 403
uid["v"] = OWNER
print(f"   compte owner   : HTTP {panel_ouvert()} (200 attendu)")
assert panel_ouvert() == 200
os.environ["ADMIN_PANEL_PASSWORD"] = "RICH PORTER"

titre(10, "Anti-force-brute : blocage apres 5 essais")
uid["v"] = AUTRE
reverrouiller()
webapp._rate_reset(f"adminpwd:127.0.0.1:{AUTRE}")
codes = [app.post("/api/admin/unlock",
                  json={"initData": "x", "password": "faux"}).status_code
         for _ in range(7)]
print(f"   codes successifs : {codes}")
assert 429 in codes, "aucun blocage apres plusieurs essais"

fin()

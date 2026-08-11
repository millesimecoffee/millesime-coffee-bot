"""Notifications de parcours : entrée, pays, ville, bon de commande."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import preparer, simuler_telegram, titre, fin, OWNER, AUTRE

webapp = preparer()
uid = {"v": AUTRE}
simuler_telegram(webapp, uid)

import catalog
import pushover

app = webapp.app.test_client()
FR = "🇫🇷 France"
ES = "🇪🇸 Espagne"


def signaler(pays, ville="", init="x"):
    return app.post("/api/notify/city",
                    json={"initData": init, "country": pays, "city": ville})


print("=" * 62)

titre(1, "Clic sur une tuile pays -> le pays seul est annonce")
uid["v"] = 1001
r = signaler(ES).get_json()
print(f"   {r}")
assert r["sent"] == ["country"]

titre(2, "Puis une ville de ce pays -> la ville seule")
r = signaler(ES, "Barcelone").get_json()
print(f"   {r}")
assert r["sent"] == ["city"]

titre(3, "Retour sur une ville deja vue -> rien (anti-repetition)")
r = signaler(ES, "Barcelone").get_json()
print(f"   {r}")
assert r["sent"] == []

titre(4, "Recherche directe d'une ville d'un AUTRE pays -> pays PUIS ville")
r = signaler(FR, "Paris").get_json()
print(f"   {r}")
assert r["sent"] == ["country", "city"]

titre(5, "Texte arbitraire -> refuse (pas d'injection dans les notifications)")
for faux in ["Gotham", "<b>pirate</b>", "'; DROP TABLE"]:
    r = signaler(FR, faux)
    print(f"   {faux!r:20s} HTTP {r.status_code} ({r.get_json().get('error')})")
    assert r.status_code == 400

titre(6, "Ville reelle mais du mauvais pays -> refuse")
r = signaler(FR, "Barcelone")
print(f"   HTTP {r.status_code} ({r.get_json().get('error')})")
assert r.status_code == 400

titre(7, "Sans authentification -> refuse")
r = signaler(FR, "Paris", init="")
print(f"   HTTP {r.status_code} ({r.get_json().get('error')})")
assert r.status_code == 401

titre(8, "Par defaut l'owner recoit AUSSI ses propres notifications")
print("    (sinon il ne peut pas tester sa boutique et la croit en panne)")
uid["v"] = OWNER
r = signaler(FR, "Paris").get_json()
print(f"   {r}")
assert r.get("skipped") != "owner" and r["sent"]

titre(9, "NOTIF_IGNORER_OWNER=1 retablit le silence")
os.environ["NOTIF_IGNORER_OWNER"] = "1"
r = signaler(ES, "Tenerife").get_json()
print(f"   {r}")
assert r.get("skipped") == "owner"
os.environ["NOTIF_IGNORER_OWNER"] = ""

titre(10, "Prepositions correctes sur les 15 pays du catalogue")
attendu = {"PORTUGAL": "AU", "MAROC": "AU", "PAYS-BAS": "AUX", "ÉTATS-UNIS": "AUX"}
for pays in catalog.CATALOG:
    _, nom = pushover._separer_drapeau(pays)
    prep = pushover._PREPOSITION_PAYS.get(nom, "EN")
    assert prep == attendu.get(nom, "EN"), f"{nom} -> {prep}"
print(f"   {len(catalog.CATALOG)} pays verifies, dont {len(attendu)} exceptions")

titre(11, "Format des messages Pushover")
captures = []
pushover.envoyer = (lambda message, titre="", priorite=0, url="",
                           url_titre="", image=None: captures.append((message, image)))
pushover.entree_shop()
pushover.pays_choisi("🇺🇸 États-Unis")
pushover.ville_choisie("Las Vegas", "🇺🇸 États-Unis")
pushover.nouvelle_commande(order_id="020802", adresse="10 RUE X, PARIS, 75020",
                           articles={"❄️ COCA 1G": 1, "🌸 TUCI 1G": 2},
                           total=700, devise="€", client="@client",
                           selfie=b"\xff\xd8\xff-photo")
for m, _ in captures:
    assert not m.startswith("—"), "les separateurs devaient etre retires"
    assert len(m) <= 1024
bon, photo = captures[-1]
assert bon.count("🛍") == 1, "un seul marqueur sac attendu"
for ligne in ("❄️ COCA 1G × 1", "🌸 TUCI 1G × 2"):
    assert ligne in bon, f"quantite manquante : {ligne}"
assert photo == b"\xff\xd8\xff-photo", "le selfie n'est pas joint"
print(f"   {len(captures)} messages, quantites sur chaque ligne, selfie joint")
print(f"   pays : {captures[1][0]}")

titre(12, "Une image trop lourde ne fait pas perdre la notification")
os.environ.update(PUSHOVER_USER_KEY="u" * 30, PUSHOVER_APP_TOKEN="a" * 30)
envois = []


class Reponse:
    status_code = 200

    def json(self):
        return {"status": 1}


import httpx
httpx.post = lambda url, data=None, files=None, timeout=None: (
    envois.append(bool(files)) or Reponse())
ok = pushover.envoyer_bloquant("test", "t", image=b"x" * 3_000_000)
print(f"   envoi accepte : {ok}, piece jointe transmise : {envois[-1]}")
assert ok is True and envois[-1] is False
os.environ.update(PUSHOVER_USER_KEY="", PUSHOVER_APP_TOKEN="")

fin()

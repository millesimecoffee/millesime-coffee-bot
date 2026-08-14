"""Suivi de commande : position simulée vs position réelle du livreur."""
import json
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import preparer, titre, fin, OWNER

webapp = preparer()

CLIENT = 424242
COMMANDE = {
    "order_id": "TEST01", "user_id": CLIENT, "status": "delivering",
    "city": "Paris", "total": 120, "address": "10 rue de Rivoli, Paris",
    "address_lat": 48.8566, "address_lon": 2.3522,
    "_delivery_started_at": webapp._now_iso(), "_eta_minutes": 20,
    "created_at": webapp._now_iso(),
}

_qui = {"v": CLIENT}
webapp._verify_init_data = lambda i, t: {"user": json.dumps({"id": _qui["v"]})} if i else None
import storage
storage.get_order = lambda oid: dict(COMMANDE) if oid == "TEST01" else None

app = webapp.app.test_client()


def suivre():
    r = app.post("/api/order/track", json={"initData": "x", "order_id": "TEST01"})
    assert r.status_code == 200, f"HTTP {r.status_code}"
    return r.get_json()


print("=" * 62)

titre(1, "Sans partage de position -> trajectoire simulee")
webapp.clear_driver_position()
d = suivre()
print(f"   live={d['live']}  distance={d['distance_km']} km  ETA={d['eta_seconds']//60} min")
assert d["live"] is False and d["driver_pos"]

titre(2, "Avec position en direct -> vraie position")
webapp.set_driver_position(48.8670, 2.3500)
d2 = suivre()
print(f"   live={d2['live']}  cap={d2['driver_pos']['heading']:.0f}°  "
      f"distance={d2['distance_km']} km  ETA={d2['eta_seconds']//60} min")
assert d2["live"] is True
assert abs(d2["driver_pos"]["lat"] - 48.8670) < 1e-6
assert d2["distance_km"] > 1.0

titre(3, "Le livreur se rapproche -> distance et ETA baissent")
webapp.set_driver_position(48.8600, 2.3515)
d3 = suivre()
print(f"   distance {d2['distance_km']} -> {d3['distance_km']} km, "
      f"progression {d3['progress']:.0%}")
assert d3["distance_km"] < d2["distance_km"] and d3["progress"] > 0

titre(4, "Partage arrete -> retour a la trajectoire simulee")
webapp.clear_driver_position()
print(f"   live={suivre()['live']}")
assert suivre()["live"] is False

titre(5, "Position perimee -> repli estime, pas de position figee")
webapp.set_driver_position(48.8670, 2.3500)
with webapp._driver_pos_lock:
    webapp._driver_pos["at"] = webapp._now_aware() - timedelta(seconds=webapp._DRIVER_POS_TTL + 5)
print(f"   live={suivre()['live']} (position vieille de {webapp._DRIVER_POS_TTL + 5} s)")
assert suivre()["live"] is False

titre(6, "Commande d'un autre client -> acces refuse")
_qui["v"] = 999
r = app.post("/api/order/track", json={"initData": "x", "order_id": "TEST01"})
print(f"   HTTP {r.status_code} — {r.get_json()}")
assert r.status_code == 403
_qui["v"] = CLIENT

titre(7, "L'ecran de suivi recoit de quoi tout afficher")
print("    (heures d'etapes, heure d'arrivee, panier : sinon la timeline et")
print("     le bouton « details » afficheraient des tirets)")
COMMANDE.update({
    "_confirmed_at": "2026-08-12T13:24:00+02:00",
    "_delivery_started_at": "2026-08-12T13:28:00+02:00",
    "created_at": "2026-08-12T13:22:00+02:00",
    "cart": {"❄️ COCA 1G": 2}, "payment": "Espèces",
})
webapp.set_driver_position(48.8600, 2.3515)
d = suivre()
print(f"   heures d'etapes : {d['step_times']}")
assert set(d["step_times"]) == {"received", "preparing", "delivering"}, \
    "l'etape non franchie ne doit pas avoir d'heure"
print(f"   heure d'arrivee : {d['eta_at']}")
assert d["eta_at"], "sans eta_at, l'ecran ne peut pas annoncer une heure"
assert d["eta_at"] > webapp._now_iso(), "l'arrivee doit etre dans le futur"
print(f"   panier : {d['cart']}  total : {d['total']}  paiement : {d['payment']}")
assert d["cart"] == {"❄️ COCA 1G": 2} and d["address"]

titre(8, "Une commande livree : toutes les etapes horodatees, arrivee figee")
COMMANDE.update({"status": "delivered", "_delivered_at": "2026-08-12T13:41:00+02:00"})
d = suivre()
print(f"   etapes : {d['steps']}")
print(f"   heures : {sorted(d['step_times'])}")
assert all(d["steps"].values()), "les 4 etapes doivent etre franchies"
assert "delivered" in d["step_times"]
print(f"   eta_at : {d['eta_at']} (aucune arrivee a annoncer)")
assert d["eta_at"] is None
COMMANDE.update({"status": "delivering"})
COMMANDE.pop("_delivered_at", None)

titre(9, "Cap et vitesse deduits de deux points successifs")
webapp.clear_driver_position()
webapp.set_driver_position(48.8700, 2.3400)
import time
time.sleep(1.1)
webapp.set_driver_position(48.8660, 2.3450)
pos = webapp.get_driver_position()
print(f"   cap {pos['heading']:.0f}°, vitesse {pos['speed_kmh']:.0f} km/h, age {pos['age_seconds']} s")
assert 90 < pos["heading"] < 220, "cap incoherent vers le sud-est"
webapp.clear_driver_position()

fin()

"""Itinéraire routier : tracé rue par rue, mis en cache, sans jamais bloquer.

Le trait droit entre le livreur et l'adresse ne ressemble à rien. On demande
le vrai chemin à Mapbox — mais un service tiers peut être lent, en panne ou
hors quota : la carte doit continuer à fonctionner dans tous les cas.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import preparer, titre, fin

webapp = preparer(MAPBOX_TOKEN="jeton-de-test")

DEPART = (50.8570, 4.3610)
ARRIVEE = (50.8466, 4.3528)

# Faux tracé : un L, qui zigzague au lieu d'aller tout droit.
TRACE = [[50.8570, 4.3610], [50.8570, 4.3528], [50.8520, 4.3528], [50.8466, 4.3528]]

appels = []


class Reponse:
    status_code = 200
    text = ""

    def json(self):
        return {"routes": [{
            "geometry": {"coordinates": [[p[1], p[0]] for p in TRACE]},
            "distance": 2640.0, "duration": 720.0,
        }]}


import httpx


def faux_get(url, timeout=None, params=None, **kw):
    appels.append(url)
    return Reponse()


httpx.get = faux_get
print("=" * 62)

titre(1, "Le tracé revient en [lat, lon], prêt pour la carte")
webapp._route_cache.clear()
points, metres, secondes = webapp._route_pour("C1", DEPART, ARRIVEE)
print(f"   {len(points)} points, {metres/1000:.2f} km, {secondes/60:.0f} min")
print(f"   premier {points[0]}  dernier {points[-1]}")
assert points[0] == [50.857, 4.361] and points[-1] == [50.8466, 4.3528]
assert len(appels) == 1

titre(2, "Le tracé zigzague : ce n'est pas une ligne droite")
vol = webapp._haversine_km(*DEPART, *ARRIVEE)
longueur = sum(webapp._haversine_km(*points[i], *points[i+1])
               for i in range(len(points)-1))
print(f"   vol d'oiseau {vol:.2f} km — par la route {longueur:.2f} km "
      f"(×{longueur/vol:.2f})")
assert longueur > vol * 1.1

titre(3, "Deuxième relevé au même endroit : rien n'est redemandé")
webapp._route_pour("C1", DEPART, ARRIVEE)
webapp._route_pour("C1", (DEPART[0] + 0.0002, DEPART[1]), ARRIVEE)
print(f"   appels à Mapbox : {len(appels)} (1 attendu)")
assert len(appels) == 1

titre(4, "Le livreur s'est éloigné de plus de 250 m : on recalcule")
loin = (DEPART[0] + 0.004, DEPART[1])      # ~450 m
ecart = webapp._haversine_km(*DEPART, *loin) * 1000
webapp._route_pour("C1", loin, ARRIVEE)
print(f"   deplacement {ecart:.0f} m -> appels : {len(appels)} (2 attendus)")
assert len(appels) == 2

titre(5, "Cache périmé : on recalcule aussi")
import time as _t
with webapp._route_lock:
    webapp._route_cache["C1"]["at"] = _t.time() - webapp._ROUTE_TTL - 1
webapp._route_pour("C1", loin, ARRIVEE)
print(f"   appels : {len(appels)} (3 attendus)")
assert len(appels) == 3

titre(6, "Chaque commande a son propre tracé")
webapp._route_pour("C2", DEPART, ARRIVEE)
print(f"   commandes en cache : {sorted(webapp._route_cache)}")
assert sorted(webapp._route_cache) == ["C1", "C2"]

titre(7, "Commande livrée : le tracé est oublié")
webapp._oublier_route("C2")
print(f"   restant : {sorted(webapp._route_cache)}")
assert "C2" not in webapp._route_cache

titre(8, "Mapbox en panne -> pas de tracé, mais aucune exception")
webapp._route_cache.clear()


class Panne:
    status_code = 503
    text = "service indisponible"

    def json(self):
        return {}


httpx.get = lambda *a, **k: Panne()
r = webapp._route_pour("C3", DEPART, ARRIVEE)
print(f"   resultat : {r}  (la carte retombera sur la ligne droite)")
assert r == (None, None, None)

titre(9, "Réponse vide ou illisible -> même repli")
for corps in [{"routes": []}, {}, {"routes": [{"geometry": {"coordinates": [[1, 2]]}}]}]:
    httpx.get = (lambda c: lambda *a, **k: type(
        "R", (), {"status_code": 200, "text": "", "json": lambda s: c})())(corps)
    r = webapp._route_pour("C4", DEPART, ARRIVEE)
    print(f"   {str(corps)[:44]:46s} -> {r[0]}")
    assert r[0] is None

titre(10, "Le réseau lâche -> repli, toujours sans exception")
def explose(*a, **k):
    raise OSError("connexion perdue")


httpx.get = explose
r = webapp._route_pour("C5", DEPART, ARRIVEE)
print(f"   resultat : {r}")
assert r == (None, None, None)

titre(11, "Sans jeton Mapbox, on n'appelle même pas le service")
os.environ["MAPBOX_TOKEN"] = ""
touche = []
httpx.get = lambda *a, **k: touche.append(1)
r = webapp._itineraire_mapbox(DEPART, ARRIVEE)
print(f"   appels reseau : {len(touche)} — resultat {r}")
assert not touche and r == (None, None, None)
os.environ["MAPBOX_TOKEN"] = "jeton-de-test"

fin()

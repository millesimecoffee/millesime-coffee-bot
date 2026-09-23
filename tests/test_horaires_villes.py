"""Horaires d'ouverture par ville : état ouvert/fermé et exposition à l'API.

Six villes (Barcelone, Malaga, Palma De Majorque, Rome, Milan, Berlin) sont
ouvertes tous les jours de 10h00 à minuit, heure LOCALE de la ville. Le client
doit voir « Ouvert » ou « Fermé » selon l'heure de la VILLE, où qu'il soit.
"""
import os
import sys
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import preparer, titre, fin

DOSSIER = tempfile.mkdtemp(prefix="millesime_horaires_")
webapp = preparer(DATA_DIR=DOSSIER)

import catalog

app = webapp.app.test_client()
print("=" * 62)

VILLES = ["Barcelone", "Malaga", "Palma De Majorque", "Rome", "Milan", "Berlin"]


def _utc_pour_heure_locale_cet(h, m=0):
    """UTC correspondant à l'heure murale CET donnée. Europe/Paris = UTC+2 en
    septembre (CEST). On teste toujours à une date estivale fixe."""
    return datetime(2026, 9, 23, (h - 2) % 24, m, tzinfo=timezone.utc)


titre(1, "Les six villes demandées ont des horaires 10h→minuit")
for v in VILLES:
    h = catalog.get_horaires("", v)
    assert h is not None, f"{v} devrait avoir des horaires"
    assert h["ouv"] == "10:00" and h["fer"] == "00:00", f"{v}: {h}"
    print(f"   {v:<20s} {h['txt']}  (tz {h['tz']})")


titre(2, "Ouvert/fermé bascule aux bonnes heures locales")
cas = [(9, 59, False), (10, 0, True), (12, 0, True), (23, 59, True), (0, 0, False), (3, 0, False)]
for h, m, attendu in cas:
    got = catalog.ville_ouverte("", "Barcelone", _utc_pour_heure_locale_cet(h, m))
    etat = "ouvert" if got else "fermé"
    print(f"   {h:02d}h{m:02d} local -> {etat}")
    assert got is attendu, f"{h:02d}h{m:02d}: attendu {attendu}, obtenu {got}"


titre(3, "Une ville sans horaires ne renvoie ni pastille ni état")
assert catalog.get_horaires("", "Paris") is None
assert catalog.ville_ouverte("", "Paris") is None
print("   Paris (sans horaires) -> get_horaires=None, ville_ouverte=None")


titre(4, "Le snapshot est indexé « pays|ville » et couvre les six villes")
snap = catalog.horaires_snapshot(_utc_pour_heure_locale_cet(15, 0))
attendues = {
    "🇪🇸 Espagne|Barcelone", "🇪🇸 Espagne|Malaga", "🇪🇸 Espagne|Palma De Majorque",
    "🇮🇹 Italie|Rome", "🇮🇹 Italie|Milan", "🇩🇪 Allemagne|Berlin",
}
print(f"   clés : {sorted(snap.keys())}")
assert set(snap.keys()) == attendues
# À 15h CET tout est ouvert, et chaque entrée porte de quoi recalculer côté client.
for cle, e in snap.items():
    assert e["ouvert"] is True
    for champ in ("ouv_min", "fer_min", "tz", "txt"):
        assert champ in e, f"{cle}: champ {champ} manquant"
assert snap["🇩🇪 Allemagne|Berlin"]["fer_min"] == 0
assert snap["🇩🇪 Allemagne|Berlin"]["ouv_min"] == 600


titre(5, "L'indépendance vis-à-vis de l'overlay éditable")
# Les horaires vivent hors du catalogue éditable : réappliquer un overlay
# (qui reconstruit CATALOG/MIN_ORDER/…) ne doit pas les effacer.
catalog.rafraichir()
assert catalog.get_horaires("", "Berlin") is not None, \
    "les horaires doivent survivre à rafraichir()"
print("   rafraichir() n'efface pas les horaires (table indépendante)")


titre(6, "/api/catalog expose city_hours pour le client")
d = app.get("/api/catalog").get_json()
ch = d.get("city_hours") or {}
print(f"   city_hours : {len(ch)} villes")
assert set(ch.keys()) == attendues
b = ch["🇪🇸 Espagne|Barcelone"]
assert b["tz"] == "Europe/Paris" and b["ouv_min"] == 600 and b["fer_min"] == 0
assert "ouvert" in b

fin()

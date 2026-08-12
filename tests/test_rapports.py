"""Rapports du bot (/stats, minuit, hebdo) : bonne journée, bons montants."""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import preparer, titre, fin

preparer()
import storage
from storage import get_stats, get_stats_period, _PARIS

AUJ = datetime.now(_PARIS)
HIER = (AUJ - timedelta(days=1)).strftime("%Y-%m-%d")
JOUR = AUJ.strftime("%Y-%m-%d")


def cmd(oid, quand_iso, total, statut="delivered", ville="Paris"):
    return {"order_id": oid, "user_id": 1, "status": statut, "total": total,
            "created_at": quand_iso, "city": ville, "cart": {"❄️ COCA 1G": 1}}


print("=" * 62)

titre(1, "Une commande de 00h30 a Paris compte pour CE jour-la")
print("    (le serveur Render tourne en UTC : 00h30 Paris = 22h30 UTC la veille)")
storage._load = lambda: [cmd("N1", "2026-08-11T22:30:00+00:00", 100)]
s = get_stats(date_str="2026-08-12")
print(f"   journee du 12 aout : {s['orders_today']} commande, {s['ca_today']:.0f} €")
assert s["orders_today"] == 1, "rangee dans la mauvaise journee"
s_veille = get_stats(date_str="2026-08-11")
print(f"   journee du 11 aout : {s_veille['orders_today']} commande")
assert s_veille["orders_today"] == 0

titre(2, "Une commande de 23h30 Paris reste sur sa journee")
storage._load = lambda: [cmd("N2", "2026-08-12T21:30:00+00:00", 100)]
print(f"   12 aout : {get_stats(date_str='2026-08-12')['orders_today']} commande")
assert get_stats(date_str="2026-08-12")["orders_today"] == 1

titre(3, "« Aujourd'hui » se calcule a l'heure de Paris, pas du serveur")
storage._load = lambda: [cmd("N3", AUJ.isoformat(timespec="seconds"), 60)]
s = get_stats()
print(f"   date retenue : {s['date_str']} (attendu {JOUR})")
assert s["date_str"] == JOUR and s["orders_today"] == 1

titre(4, "Les commandes annulees ne comptent dans aucun chiffre d'affaires")
storage._load = lambda: [
    cmd("A", AUJ.isoformat(timespec="seconds"), 100),
    cmd("B", AUJ.isoformat(timespec="seconds"), 900, statut="cancelled"),
    cmd("C", AUJ.isoformat(timespec="seconds"), 500, statut="cancelled_by_client"),
]
s = get_stats()
print(f"   3 commandes dont 2 annulees -> CA {s['ca_today']:.0f} € (100 attendu)")
print(f"   CA total : {s['ca_total']:.0f} €")
assert s["ca_today"] == 100 and s["ca_total"] == 100

titre(5, "Le panier moyen ne se fait pas diluer par les annulations")
print(f"   panier moyen du jour : {s['avg_basket_day']:.0f} € (100 attendu, pas 33)")
assert s["avg_basket_day"] == 100

titre(6, "Le nombre de commandes recues reste affiche en entier")
print(f"   commandes du jour : {s['orders_today']} (3 attendu)")
assert s["orders_today"] == 3

titre(7, "Rapport hebdomadaire : meme decoupage, memes exclusions")
debut = (AUJ - timedelta(days=7)).strftime("%Y-%m-%d")
fin_p = (AUJ - timedelta(days=1)).strftime("%Y-%m-%d")
storage._load = lambda: [
    cmd("H1", (AUJ - timedelta(days=2)).isoformat(timespec="seconds"), 200),
    cmd("H2", (AUJ - timedelta(days=3)).isoformat(timespec="seconds"), 800, statut="cancelled"),
    cmd("H3", (AUJ - timedelta(days=30)).isoformat(timespec="seconds"), 400),
]
p = get_stats_period(debut, fin_p)
print(f"   {debut} -> {fin_p} : {p['orders_period']} commandes, {p['ca_period']:.0f} € (200 attendu)")
assert p["ca_period"] == 200
assert p["orders_period"] == 2, "la commande d'il y a 30 jours doit rester dehors"

titre(8, "Ancien format sans fuseau : toujours lisible")
storage._load = lambda: [cmd("V1", "2026-07-01T14:00:00", 250)]
s = get_stats(date_str="2026-07-01")
print(f"   1er juillet : {s['orders_today']} commande, {s['ca_today']:.0f} €")
assert s["orders_today"] == 1

titre(9, "Horodatage absent ou illisible : ignore, aucun plantage")
storage._load = lambda: [
    {"order_id": "X1", "total": 50, "cart": {}, "status": "delivered"},
    cmd("X2", "pas une date", 70),
    cmd("X3", "", 90),
]
s = get_stats(date_str=JOUR)
p = get_stats_period("2026-01-01", "2030-01-01")
print(f"   get_stats OK ({s['orders_today']} du jour), get_stats_period OK ({p['orders_period']})")

fin()

"""Statistiques du panel : CA, classements, horodatage des étapes."""
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import preparer, simuler_telegram, titre, fin, OWNER

webapp = preparer(ADMIN_PANEL_PASSWORD="")   # owner direct, sans verrou
uid = {"v": OWNER}
simuler_telegram(webapp, uid)

import storage

app = webapp.app.test_client()
AUJ = webapp._dt.now(webapp._PARIS).date() if hasattr(webapp, "_dt") else None
from datetime import datetime as _dt
AUJ = _dt.now(webapp._PARIS).date()


def cmd(jours, total, ville, statut="delivered", panier=None):
    quand = _dt.now(webapp._PARIS) - timedelta(days=jours)
    return {"order_id": f"C{jours}{int(total)}", "user_id": 1, "status": statut,
            "created_at": quand.isoformat(timespec="seconds"),
            "city": ville, "country": "🇫🇷 France", "total": total,
            "cart": panier or {"❄️ COCA 1G": 1}}


JEU = [
    cmd(0, 100, "Paris"),
    cmd(0, 200, "Paris", panier={"🌸 TUCI 1G": 3}),
    cmd(2, 300, "Miami"),
    cmd(6, 400, "Miami"),
    cmd(20, 500, "Berlin"),                      # dans le mois, hors 7 jours
    cmd(1, 999, "Paris", statut="cancelled"),    # annulee : exclue du CA
]
storage._load = lambda: list(JEU)

print("=" * 62)

d = app.post("/api/admin/orders", json={"initData": "x", "limit": 50}).get_json()

titre(1, "Chiffre d'affaires par periode (heure de Paris)")
print(f"   journalier    : {d['today_ca']:.0f} €  ({d['today_count']} cmd)")
print(f"   7 jours       : {d['ca_semaine']:.0f} €  ({d['count_semaine']} cmd)")
print(f"   mois en cours : {d['ca_mois']:.0f} €  ({d['count_mois']} cmd)")
assert d["today_ca"] == 300, "jour = 100 + 200"
assert d["ca_semaine"] == 1000, "7 jours = 100 + 200 + 300 + 400"
assert d["today_ca"] <= d["ca_semaine"], "le jour doit tenir dans les 7 jours"

titre(2, "Une commande annulee n'entre dans aucun CA")
print(f"   commande de 999 € annulee : absente des totaux -> {999 not in (d['today_ca'], d['ca_semaine'])}")
assert d["ca_semaine"] == 1000

titre(3, "Compteurs de statut : les annulations client comptent avec les autres")
print(f"   {d['counts']}")
assert sum(d["counts"].values()) == len(JEU)

titre(4, "Top 5 villes, classe par chiffre d'affaires")
for i, v in enumerate(d["top_villes"], 1):
    print(f"   {i}. {v['ville']:<8s} {v['ca']:>6.0f} €  ({v['commandes']} cmd)")
assert d["top_villes"][0]["ville"] == "Miami", "Miami = 700 €, doit etre premier"
assert len(d["top_villes"]) <= 5

titre(5, "Top 5 produits, classe par quantite")
for i, p in enumerate(d["top_produits"], 1):
    print(f"   {i}. {p['produit']:<14s} × {p['quantite']}")
assert d["top_produits"][0]["produit"] == "❄️ COCA 1G", "5 unites, doit etre premier"

titre(6, "Les journees sont decoupees a l'heure de Paris, pas du serveur")
jour = webapp._jour_paris("2026-08-02T23:30:00+00:00")
print(f"   23h30 UTC le 2 aout -> {jour} a Paris (3 aout attendu, +2h)")
assert jour.day == 3, "le decoupage doit suivre Paris"

titre(7, "Chaque changement de statut est horodate")
etat = {"o": {"order_id": "T1", "user_id": 1, "status": "pending", "total": 10, "cart": {}}}
storage.get_order = lambda oid: dict(etat["o"])
maj = lambda oid, upd: (etat["o"].update(upd), True)[1]
storage.update_order = webapp.update_order = maj
for s in ["confirmed", "delivering", "delivered"]:
    app.post("/api/admin/order/T1/status", json={"initData": "x", "status": s})
champs = sorted(k for k in etat["o"] if k.startswith("_"))
print(f"   {champs}")
for attendu in ["_confirmed_at", "_delivery_started_at", "_delivered_at"]:
    assert attendu in champs, f"{attendu} manquant"

titre(8, "Le panel signale quand le client n'a pas pu etre prevenu")
r = app.post("/api/admin/order/T1/status", json={"initData": "x", "status": "cancelled"})
corps = r.get_json()
print(f"   ok={corps.get('ok')} notified={corps.get('notified')} ({corps.get('notify_error')})")
assert corps["ok"] is True and corps["notified"] is False

fin()

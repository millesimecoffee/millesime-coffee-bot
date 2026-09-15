"""Non-régression des correctifs de l'audit #2.

Chaque test cible un bug confirmé lors du second audit, pour qu'une
régression future le fasse échouer bruyamment :

  #2  storage : fichier absent + restauration du dépôt incomplète -> on refuse
      d'écrire (sinon on repart à vide et on écrase la sauvegarde).
  #3  storage : un update Supabase qui échoue (réponse vide) ne doit pas passer
      pour un succès.
  #9  github_backup : distinguer un 404 franc d'une panne transitoire, et
      refuser d'envoyer un fichier dont la restauration a échoué.
  #11 statut : compare-and-swap — deux transitions concurrentes depuis le même
      point de départ ne s'empilent pas ; l'endpoint répond 409.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import preparer, simuler_telegram, titre, fin, OWNER

DOSSIER = tempfile.mkdtemp(prefix="millesime_audit2_")
webapp = preparer(ADMIN_PANEL_PASSWORD="", DATA_DIR=DOSSIER)
uid = {"v": OWNER}
simuler_telegram(webapp, uid)

import storage
import github_backup as gh

app = webapp.app.test_client()
print("=" * 62)

# On garde les vraies implémentations : certains tests remplacent storage.*
# par des simulacres, il faut pouvoir revenir aux vraies ensuite.
_VRAI_UPDATE = storage.update_order


# ── #11 : compare-and-swap sur le statut ─────────────────────────────────────
titre(11, "Deux transitions concurrentes ne s'empilent pas (CAS)")

# En mode fichier réel : l'écriture n'a lieu que si le statut attendu tient.
storage._ORDERS_FILE = Path(DOSSIER) / "orders.json"
storage._FILE_CACHE = {"cle": None, "data": None}
storage._order_index = {}
gh.backup_file_async = lambda *a, **k: None   # pas de réseau pendant le test

storage.save_order({"order_id": "CAS1", "user_id": 1, "status": "pending",
                    "total": 10, "cart": {}, "created_at": webapp._now_iso()})

ok = storage.update_order("CAS1", {"status": "confirmed"}, attendu="pending")
print(f"   pending -> confirmed (attendu=pending) : {ok}")
assert ok is True and storage.get_order("CAS1")["status"] == "confirmed"

# La commande est déjà « confirmed » : une écriture qui croit partir de
# « pending » doit être refusée, pas écraser la transition d'un autre.
try:
    storage.update_order("CAS1", {"status": "delivering"}, attendu="pending")
    raise AssertionError("StatutInattendu attendu")
except storage.StatutInattendu:
    print("   confirmed + attendu=pending -> StatutInattendu (course perdue)")
assert storage.get_order("CAS1")["status"] == "confirmed", "rien ne doit avoir bougé"


titre("11b", "L'endpoint admin répond 409 quand la course a déjà avancé")
# get_order voit « pending », mais l'écriture lève StatutInattendu : un autre
# opérateur est passé entre-temps.
storage.get_order = lambda oid: {"order_id": "Z1", "user_id": 1,
                                 "status": "pending", "total": 10, "cart": {}}

def _maj_conflit(oid, upd, attendu=None):
    raise storage.StatutInattendu(oid)

storage.update_order = webapp.update_order = _maj_conflit
r = app.post("/api/admin/order/Z1/status", json={"initData": "x", "status": "confirmed"})
print(f"   HTTP {r.status_code}  ({r.get_json().get('error')})")
assert r.status_code == 409 and r.get_json().get("error") == "conflict"


# ── #3 : un update Supabase raté ne passe pas pour un succès ──────────────────
titre(3, "update_order Supabase : réponse vide = échec, pas succès")
storage.update_order = _VRAI_UPDATE      # restaurer la vraie implémentation

class _FauxSB:
    def __init__(self, retour_update):
        self.retour_update = retour_update
    def select(self, *a, **k):
        return [{"data": {"order_id": "S1", "status": "pending"}}]
    def update(self, *a, **k):
        return self.retour_update

storage._use_supabase = lambda: True

storage._sb = _FauxSB(retour_update=[])          # échec simulé
storage._order_index = {}
ok = storage.update_order("S1", {"status": "confirmed"})
print(f"   update renvoie [] -> update_order = {ok} (False attendu)")
assert ok is False

storage._sb = _FauxSB(retour_update=[{"data": {"order_id": "S1", "status": "confirmed"}}])
storage._order_index = {}
ok = storage.update_order("S1", {"status": "confirmed"})
print(f"   update renvoie la ligne -> update_order = {ok} (True attendu)")
assert ok is True

storage._use_supabase = lambda: False            # retour au mode fichier


# ── #9 : github_backup distingue 404 et panne transitoire ────────────────────
titre(9, "download : 404 = « absent », panne = « erreur » (tri-état)")

gh._TOKEN = "jeton-de-test"                       # active le backup
gh._DATA_DIR = Path(DOSSIER)
gh._restore_incomplet = set()

class _Rep:
    def __init__(self, code):
        self.status_code = code
    def json(self):
        return {}
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

# 404 franc -> « absent »
gh.httpx.get = lambda *a, **k: _Rep(404)
print(f"   404 -> {gh._etat_download('orders.json')!r}")
assert gh._etat_download("orders.json") == "absent"

# Panne réseau -> « erreur »
def _boom(*a, **k):
    raise RuntimeError("getaddrinfo failed")
gh.httpx.get = _boom
print(f"   panne réseau -> {gh._etat_download('orders.json')!r}")
assert gh._etat_download("orders.json") == "erreur"


titre("9b", "Une restauration en échec suspend les envois du fichier")
gh._restore_incomplet = set()
gh.httpx.get = _boom
etat = gh._restaurer_un("orders.json", essais=1)
print(f"   _restaurer_un -> {etat!r}, incomplète = {gh.restauration_incomplete('orders.json')}")
assert etat == "erreur" and gh.restauration_incomplete("orders.json") is True

# Le fichier local existe (reconstruit à vide) mais on REFUSE de l'envoyer.
(Path(DOSSIER) / "orders.json").write_text("[]", encoding="utf-8")
envoye = gh.upload_file("orders.json")
print(f"   upload_file pendant restauration incomplète -> {envoye} (False attendu)")
assert envoye is False


titre("9c", "Un 404 confirmé, lui, lève le blocage")
gh._restore_incomplet = {"orders.json"}
gh.httpx.get = lambda *a, **k: _Rep(404)
etat = gh._restaurer_un("orders.json", essais=1)
print(f"   _restaurer_un -> {etat!r}, incomplète = {gh.restauration_incomplete('orders.json')}")
assert etat == "absent" and gh.restauration_incomplete("orders.json") is False


# ── #2 : storage refuse d'écrire à vide quand la restauration a échoué ────────
titre(2, "Fichier absent + restauration incomplète -> refus d'écrire")
# On enlève le fichier et on marque la restauration comme incomplète.
storage._ORDERS_FILE = Path(DOSSIER) / "inexistant.json"
storage._FILE_CACHE = {"cle": None, "data": None}
gh._restore_incomplet = {"orders.json"}
gh.httpx.get = _boom     # au cas où un retry se déclencherait

try:
    storage._load_from_file(pour_ecriture=True)
    raise AssertionError("LectureImpossible attendu")
except storage.LectureImpossible:
    print("   pour_ecriture=True -> LectureImpossible (on n'écrase pas la sauvegarde)")

# En lecture seule, rester tolérant : on renvoie une liste vide, sans lever.
vide = storage._load_from_file(pour_ecriture=False)
print(f"   pour_ecriture=False -> {vide!r} (lecture tolérante)")
assert vide == []

fin()

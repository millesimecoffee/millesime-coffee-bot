"""Reproduit l'incident de production : lectures pendant les écritures.

Avant correctif, orders.json était ouvert en « w » (vidé aussitôt) : une
lecture concurrente voyait du JSON tronqué. Le panel lit toutes les 3 s.
"""
import json, os, pathlib, sys, tempfile, threading, time, logging

logging.disable(logging.ERROR)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
tmp = tempfile.mkdtemp()
os.environ["DATA_DIR"] = tmp
os.chdir(tmp)

import storage
storage._ORDERS_FILE = pathlib.Path(tmp) / "orders.json"
storage._gh.backup_file_async = lambda *a, **k: None   # pas de sync GitHub en test


def commandes(n, poids=30_000):
    """n commandes avec un selfie volumineux, comme en production."""
    return [{"order_id": f"T{i:04d}", "user_id": 1, "total": 100,
             "selfie_b64": "A" * poids} for i in range(n)]


print("=" * 62)

print("\n1) Ecriture atomique : aucun fichier temporaire ne subsiste")
storage._save_to_file(commandes(20))
restes = [f for f in os.listdir(tmp) if f.endswith(".tmp")]
print(f"   fichiers .tmp restants : {restes or 'aucun'}")
assert not restes

print("\n2) Lectures pendant des ecritures, a la cadence du panel (3 s)")
print("   (c'est le scenario de l'incident en production)")
stop = threading.Event()
etat = {"ok": 0, "tronque": 0}


def lecteur():
    while not stop.is_set():
        try:
            with storage._ORDERS_FILE.open(encoding="utf-8") as f:
                json.load(f)
            etat["ok"] += 1
        except json.JSONDecodeError:
            etat["tronque"] += 1
        except OSError:
            pass
        for _ in range(30):                 # 3 s, interruptible
            if stop.is_set():
                break
            time.sleep(0.1)


t = threading.Thread(target=lecteur, daemon=True)
t.start()
perdues = 0
for i in range(25):
    avant = storage._ORDERS_FILE.stat().st_mtime_ns
    storage._save_to_file(commandes(20 + i))
    if storage._ORDERS_FILE.stat().st_mtime_ns == avant:
        perdues += 1
    time.sleep(0.08)
stop.set()
t.join(timeout=2)

final = json.loads(storage._ORDERS_FILE.read_text(encoding="utf-8"))
print(f"   lectures completes : {etat['ok']}")
print(f"   JSON tronque       : {etat['tronque']}")
print(f"   ecritures perdues  : {perdues}/25")
print(f"   etat final         : {len(final)} commandes (44 attendu)")
assert etat["tronque"] == 0, "des lectures ont vu un fichier tronque"
assert perdues == 0, "des ecritures ont ete perdues"
assert len(final) == 44

print("\n3) Fichier corrompu : une ecriture doit REFUSER, pas ecraser")
storage._FILE_CACHE.update(cle=None, data=None)
storage._save_to_file(commandes(5))
sain = storage._ORDERS_FILE.read_text(encoding="utf-8")
storage._ORDERS_FILE.write_text(sain[: len(sain) // 2], encoding="utf-8")
storage._FILE_CACHE.update(cle=None, data=None)

d = storage._load_from_file()
print(f"   lecture d'affichage : {len(d)} commande(s) — degradation acceptee")
assert d == []

storage._FILE_CACHE.update(cle=None, data=None)
try:
    storage.save_order({"order_id": "NEUF", "user_id": 2, "total": 50})
    raise AssertionError("save_order aurait du refuser")
except storage.LectureImpossible:
    print("   enregistrement d'une commande : refuse (LectureImpossible)")

taille = storage._ORDERS_FILE.stat().st_size
print(f"   le fichier casse n'a pas ete remplace par une liste vide : {taille} octets")
assert taille > 100

print("\n4) Retour a la normale une fois le fichier repare")
storage._ORDERS_FILE.write_text(sain, encoding="utf-8")
storage._FILE_CACHE.update(cle=None, data=None)
storage.save_order({"order_id": "NEUF", "user_id": 2, "total": 50})
storage._FILE_CACHE.update(cle=None, data=None)
apres = storage._load_from_file()
print(f"   commandes apres reparation : {len(apres)} (6 attendu)")
assert len(apres) == 6 and any(o["order_id"] == "NEUF" for o in apres)

print("\n5) update_order reste protege lui aussi")
storage._ORDERS_FILE.write_text("{casse", encoding="utf-8")
storage._FILE_CACHE.update(cle=None, data=None)
try:
    storage.update_order("NEUF", {"status": "confirmed"})
    raise AssertionError("update_order aurait du refuser")
except storage.LectureImpossible:
    print("   refuse (LectureImpossible)")

print("\n" + "=" * 62)
print("TOUS LES CONTROLES SONT PASSES")

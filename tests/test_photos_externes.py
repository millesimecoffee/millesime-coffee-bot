"""Les photos vivent à côté des commandes, plus dedans.

Les selfies pesaient 97 % de orders.json — 624 Ko sur 642 Ko pour 19
commandes — alors que le fichier entier est réécrit et renvoyé au dépôt à
chaque changement de statut. Sur un an, il aurait dépassé 17 Mo.

Ce qui doit tenir : une photo enregistrée se relit à l'identique, les anciennes
commandes qui la portent encore dedans continuent de marcher, et la migration
ne perd rien.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import titre, fin

DOSSIER = tempfile.mkdtemp(prefix="millesime_photos_")
os.environ["DATA_DIR"] = DOSSIER
os.environ["GITHUB_TOKEN"] = ""            # pas de réseau dans les tests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pathlib import Path
import github_backup
github_backup.backup_file_async = lambda *a, **k: None
github_backup.backup_binaire_async = lambda *a, **k: None
github_backup.telecharger_binaire = lambda *a, **k: b""

import storage
storage._DATA_DIR = Path(DOSSIER)
storage._ORDERS_FILE = Path(DOSSIER) / "orders.json"
storage._PHOTOS_DIR = Path(DOSSIER) / "photos"

SELFIE = "data:image/jpeg;base64," + ("A" * 40000)
PREUVE = "data:image/jpeg;base64," + ("B" * 9000)


def poids_fichier():
    return storage._ORDERS_FILE.stat().st_size if storage._ORDERS_FILE.exists() else 0


print("=" * 62)

titre(1, "Une commande enregistree ne porte plus sa photo dans le fichier")
cmd = {"order_id": "P1", "user_id": 42, "total": 120, "status": "pending",
       "selfie_b64": SELFIE, "proof_b64": PREUVE}
storage.save_order(cmd)
brut = json.loads(storage._ORDERS_FILE.read_text(encoding="utf-8"))
print(f"   orders.json : {poids_fichier()} octets pour 1 commande")
print(f"   champs photo dans le fichier : "
      f"selfie={len(brut[0].get('selfie_b64') or '')} preuve={len(brut[0].get('proof_b64') or '')}")
print(f"   references : {brut[0].get('selfie_fichier')} / {brut[0].get('proof_fichier')}")
assert not brut[0].get("selfie_b64") and not brut[0].get("proof_b64")
assert brut[0].get("selfie_fichier") and brut[0].get("proof_fichier")
assert poids_fichier() < 1000, "le fichier doit rester leger"

titre(2, "Le dictionnaire de l'appelant garde sa photo")
# La notification Pushover s'en sert JUSTE apres l'enregistrement.
print(f"   selfie encore present chez l'appelant : {len(cmd['selfie_b64'])} caracteres")
assert cmd["selfie_b64"] == SELFIE, "save_order ne doit pas vider le dict recu"

titre(3, "La relecture rend la photo a l'identique")
relu = storage.get_order("P1")
print(f"   selfie relu : {len(relu['selfie_b64'])} caracteres")
print(f"   preuve relue : {len(relu['proof_b64'])} caracteres")
assert relu["selfie_b64"] == SELFIE
assert relu["proof_b64"] == PREUVE

titre(4, "Deux relectures d'affilee (une par l'index memoire)")
r2 = storage.get_order("P1")
assert r2["selfie_b64"] == SELFIE, "l'index memoire doit rehydrater lui aussi"
print("   identique au second appel")

titre(5, "Un changement de statut ne ramene pas la photo dans le fichier")
storage.update_order("P1", {"status": "delivered"})
brut = json.loads(storage._ORDERS_FILE.read_text(encoding="utf-8"))
print(f"   apres mise a jour : {poids_fichier()} octets, statut {brut[0]['status']}")
assert brut[0]["status"] == "delivered"
assert not brut[0].get("selfie_b64")
assert storage.get_order("P1")["selfie_b64"] == SELFIE, "et la photo se relit toujours"

titre(6, "Une ancienne commande, photo dedans, marche encore")
storage._order_index.clear()
anciennes = json.loads(storage._ORDERS_FILE.read_text(encoding="utf-8"))
anciennes.append({"order_id": "VIEUX", "user_id": 7, "total": 50,
                  "status": "pending", "selfie_b64": SELFIE})
storage._ORDERS_FILE.write_text(json.dumps(anciennes), encoding="utf-8")
storage._FILE_CACHE["cle"] = None
v = storage.get_order("VIEUX")
print(f"   selfie de l'ancienne : {len(v['selfie_b64'])} caracteres")
assert v["selfie_b64"] == SELFIE
print(f"   a_une_photo : ancienne={storage.a_une_photo(v)} "
      f"nouvelle={storage.a_une_photo(storage.get_order('P1'))}")
assert storage.a_une_photo(v) and storage.a_une_photo(storage.get_order("P1"))

titre(7, "La migration sort les photos des anciennes commandes")
storage._order_index.clear()
storage._FILE_CACHE["cle"] = None
avant = poids_fichier()
deplacees = storage.migrer_photos()
apres = poids_fichier()
print(f"   {deplacees} commande(s) migree(s) : {avant} -> {apres} octets")
assert deplacees == 1
assert apres < avant
storage._order_index.clear()
storage._FILE_CACHE["cle"] = None
assert storage.get_order("VIEUX")["selfie_b64"] == SELFIE, "rien ne doit etre perdu"
print("   la photo migree se relit a l'identique")

titre(8, "Migration rejouee : elle ne fait rien et ne reecrit pas")
poids = poids_fichier()
n = storage.migrer_photos()
print(f"   deuxieme passage : {n} migration(s), fichier {poids_fichier()} octets")
assert n == 0 and poids_fichier() == poids

titre(9, "Photo disparue du disque : elle est reprise depuis la sauvegarde")
# Render n'a AUCUN disque persistant : apres chaque redemarrage, les fichiers
# photos ont disparu. Il faut donc savoir les retelecharger a la demande,
# sinon tous les selfies deviennent introuvables au premier redeploiement.
chemin = storage._chemin_photo("P1", "selfie_b64")
sauvegarde = chemin.read_text(encoding="utf-8")
chemin.unlink()
github_backup.telecharger_binaire = lambda chemin_repo: (
    sauvegarde.encode("utf-8") if chemin_repo.endswith("P1.selfie_b64.txt") else b"")
storage._order_index.clear()
storage._FILE_CACHE["cle"] = None
o = storage.get_order("P1")
print(f"   selfie repris : {len(o.get('selfie_b64') or '')} caracteres")
print(f"   fichier reecrit sur le disque : {chemin.exists()}")
assert o["selfie_b64"] == SELFIE, "la photo doit revenir de la sauvegarde"
assert chemin.exists(), "et etre remise sur le disque pour les fois suivantes"
github_backup.telecharger_binaire = lambda *a, **k: b""

titre("9b", "Photo introuvable partout : la commande reste lisible")
chemin = storage._chemin_photo("P1", "selfie_b64")
chemin.unlink()
storage._order_index.clear()
storage._FILE_CACHE["cle"] = None
o = storage.get_order("P1")
print(f"   selfie : {len(o.get('selfie_b64') or '')} caracteres, commande : {o['order_id']}")
assert o and o["order_id"] == "P1", "une photo perdue ne doit pas perdre la commande"

titre(10, "Gain de place sur vingt commandes")
storage._ORDERS_FILE.unlink()
storage._FILE_CACHE["cle"] = None
storage._order_index.clear()
for i in range(20):
    storage.save_order({"order_id": f"V{i}", "user_id": i, "total": 100,
                        "status": "pending", "selfie_b64": SELFIE})
final = poids_fichier()
ancien_modele = 20 * (len(SELFIE) + 200)
print(f"   20 commandes : {final:,} octets".replace(",", " "))
print(f"   avec les photos dedans, ce serait ~{ancien_modele:,} octets".replace(",", " "))
print(f"   soit {ancien_modele / max(final, 1):.0f} fois plus")
assert final < ancien_modele / 10


# ── Médias du chat qui sortent du fil ────────────────────────────────────────
titre(11, "Un media qui sort du fil est efface du disque")
import chat
chat._FICHIER = Path(DOSSIER) / "chats.json"
chat._MEDIA_DIR = Path(DOSSIER) / "chat_media"
chat._gh = github_backup
chat.MAX_MESSAGES = 5

media_ids = []
for i in range(8):
    mid = chat.ecrire_media(b"\xff\xd8" + bytes(500), "photo")
    media_ids.append(mid)
    chat.ajouter(999, chat.CLIENT, media_id=mid, kind="photo")

restants = [m for m in media_ids if chat._chemin_media(m).exists()]
dans_le_fil = {m.get("media") for m in chat.messages(999)}
print(f"   8 photos envoyees, plafond du fil : {chat.MAX_MESSAGES}")
print(f"   fichiers encore sur le disque : {len(restants)}")
print(f"   medias encore references      : {len(dans_le_fil)}")
assert len(restants) == chat.MAX_MESSAGES, restants
assert set(restants) == dans_le_fil, "seuls les medias encore cites doivent rester"

fin()

"""Aucune coordonnée ne doit circuler dans le chat.

Un client a réussi à écrire son numéro WhatsApp le 15 août 2026. Le filtre le
détectait pourtant : il ne lui était simplement pas appliqué. Le client n'était
filtré que pendant qu'une course était entre les mains d'un livreur — un
raisonnement faux, parce qu'un fil appartient à un CLIENT, pas à une commande,
et que le livreur qui l'ouvre y lit tout.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import preparer, simuler_telegram, titre, fin, OWNER, AUTRE

DOSSIER = tempfile.mkdtemp(prefix="millesime_fuite_")
webapp = preparer(ADMIN_PANEL_PASSWORD="RICH PORTER",
                  LIVREUR_PASSWORD="LIVREUR BRUXELLES",
                  LIVREUR_ZONES="Belgique:Bruxelles",
                  TRADUCTION_REPLI="0", DATA_DIR=DOSSIER)
import github_backup
github_backup.backup_file_async = lambda *a, **k: None
github_backup.backup_binaire_async = lambda *a, **k: None

import chat
from pathlib import Path
chat._FICHIER = Path(DOSSIER) / "chats.json"
chat._MEDIA_DIR = Path(DOSSIER) / "chat_media"

CLIENT = AUTRE
uid = {"v": CLIENT}
simuler_telegram(webapp, uid)
app = webapp.app.test_client()

import storage
CMD = {"order_id": "F1", "user_id": CLIENT, "status": "delivered", "total": 90,
       "city": "Bruxelles", "country": "🇧🇪 Belgique", "user_name": "Alex",
       "created_at": "2026-08-15T13:00:00+02:00", "cart": {}}
BASE = {"F1": dict(CMD)}
storage._load = lambda: [dict(o) for o in BASE.values()]
storage.get_order = lambda oid: dict(BASE[oid]) if oid in BASE else None

# Le message reel qui est passe en production, et ses variantes.
PIEGES = [
    ("whatsapp",          "My WhatsApp +32 470 123456 is that okay to message there?"),
    ("numero simple",     "appelle moi au 06 12 34 56 78"),
    ("numero colle",      "0612345678"),
    ("numero espace",     "0 6 1 2 3 4 5 6 7 8"),
    ("pseudo telegram",   "ecris moi @alexdealer"),
    ("lien t.me",         "https://t.me/alexdealer"),
    ("signal",            "on continue sur signal.me/#p/+32470"),
    ("instagram",         "insta : instagram.com/alexxx"),
]

print("=" * 64)

titre(1, "Le client ne peut JAMAIS envoyer de coordonnees")
# Commande deja livree, donc aucune course en cours : c'est exactement le cas
# qui passait avant.
passes = []
for nom, texte in PIEGES:
    r = app.post("/api/chat/send", json={"initData": "x", "texte": texte})
    d = r.get_json()
    etat = "refuse" if not d.get("ok") else "*** PASSE ***"
    print(f"   {nom:18s} -> HTTP {r.status_code:3d}  {etat}  {d.get('motif') or ''}")
    if d.get("ok"):
        passes.append(nom)
assert not passes, f"{len(passes)} message(s) passes : {passes}"

titre(2, "Sans aucune commande non plus")
BASE.clear()
r = app.post("/api/chat/send",
             json={"initData": "x", "texte": "My WhatsApp +32 470 123456"})
print(f"   client sans commande -> HTTP {r.status_code} {r.get_json().get('error')}")
assert not r.get_json().get("ok")
BASE["F1"] = dict(CMD)

titre(3, "Un message normal passe toujours")
for texte in ["Bonjour, vous arrivez dans combien de temps ?",
              "Je suis au 3e etage, porte 12",
              "code de l'immeuble : 4477",
              "Merci beaucoup !"]:
    d = app.post("/api/chat/send", json={"initData": "x", "texte": texte}).get_json()
    print(f"   {texte[:44]:46s} -> ok={d.get('ok')}")
    assert d.get("ok"), f"message legitime refuse : {texte}"

titre(4, "L'owner, lui, reste libre")
uid["v"] = OWNER
# Il faut deverrouiller le panneau : c'est ce qui lui donne le statut d'owner.
app.post("/api/admin/unlock", json={"initData": "x", "password": "RICH PORTER"})
d = app.post("/api/chat/send",
             json={"initData": "x", "client_id": CLIENT,
                   "texte": "appelez-moi au 06 12 34 56 78"}).get_json()
print(f"   owner envoie son numero -> ok={d.get('ok')}")
assert d.get("ok"), "c'est sa boutique, il donne son numero a qui il veut"

titre(5, "Le livreur ne peut pas non plus")
webapp._admin_unlocked.clear()
uid["v"] = 555000999
app.post("/api/auth", json={"initData": "x", "password": "livreur bruxelles"})
ref = webapp._ref_chat("F1")
passes = []
for nom, texte in PIEGES:
    d = app.post("/api/chat/send",
                 json={"initData": "x", "chat_ref": ref, "texte": texte}).get_json()
    if d.get("ok"):
        passes.append(nom)
print(f"   {len(PIEGES)} tentatives du livreur -> passees : {passes or 'aucune'}")
assert not passes

titre(6, "Le livreur ne voit que la conversation de SA course")
# Un message ancien, ecrit bien avant la commande.
chat.ajouter(CLIENT, chat.CLIENT, texte="message tres ancien")
fil = chat._lire()
fil[str(CLIENT)]["messages"][-1]["at"] = "2026-08-01T10:00:00+02:00"
chat._ecrire(fil)
chat.ajouter(CLIENT, chat.CLIENT, texte="message de la course")

d = app.post("/api/chat/thread", json={"initData": "x", "chat_ref": ref}).get_json()
vus = [m.get("texte") for m in d.get("messages", [])]
print(f"   commande passee le : {CMD['created_at'][:16]}")
print(f"   messages vus par le livreur : {len(vus)}")
print(f"   « message tres ancien » visible : {'message tres ancien' in vus}")
assert "message tres ancien" not in vus, "le livreur ne doit pas lire l'historique"
assert "message de la course" in vus, "mais bien la conversation de sa course"

titre(7, "L'owner, lui, voit tout le fil")
webapp._livreur_unlocked.clear()
uid["v"] = OWNER
app.post("/api/admin/unlock", json={"initData": "x", "password": "RICH PORTER"})
d = app.post("/api/chat/thread", json={"initData": "x", "client_id": CLIENT}).get_json()
vus = [m.get("texte") for m in d.get("messages", [])]
print(f"   messages vus par l'owner : {len(vus)}")
assert "message tres ancien" in vus


# ── Acces livreur verrouille sur les comptes declares ───────────────────────
titre(8, "Un mot de passe livreur qui fuite ne suffit plus")
import os as _os
_os.environ["LIVREUR_CHAT_ID"] = "8544248639"
webapp._livreur_unlocked.clear()
webapp._admin_unlocked.clear()
webapp._pwd_attempts.clear()

uid["v"] = 7721334621                      # le compte qui avait le mot de passe
d = app.post("/api/auth", json={"initData": "x", "password": "livreur bruxelles"}).get_json()
print(f"   compte non declare -> ok={d.get('ok')}")
assert not d.get("ok"), "un compte non declare ne doit pas ouvrir le panneau"
r = app.post("/api/livreur/courses", json={"initData": "x"})
print(f"   et ses courses      -> HTTP {r.status_code}")
assert r.status_code >= 400

webapp._pwd_attempts.clear()
uid["v"] = 8544248639                      # le vrai livreur
d = app.post("/api/auth", json={"initData": "x", "password": "livreur bruxelles"}).get_json()
print(f"   compte declare     -> ok={d.get('ok')}")
assert d.get("ok"), "le vrai livreur doit toujours entrer"

titre(9, "Sans liste declaree, l'ancien comportement est conserve")
_os.environ["LIVREUR_CHAT_ID"] = ""
webapp._livreur_unlocked.clear()
webapp._pwd_attempts.clear()
uid["v"] = 999888777
d = app.post("/api/auth", json={"initData": "x", "password": "livreur bruxelles"}).get_json()
print(f"   nouveau livreur sans liste -> ok={d.get('ok')}")
assert d.get("ok"), "sinon impossible d'inscrire un livreur sans toucher a la config"

fin()

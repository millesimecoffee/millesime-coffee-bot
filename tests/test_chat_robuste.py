"""Le chat doit tenir sous une utilisation réelle : envois simultanés,
messages hors normes, médias abîmés, et un fil qui ne perd jamais rien.
"""
import base64
import json
import os
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import preparer, simuler_telegram, titre, fin, OWNER, AUTRE

DOSSIER = tempfile.mkdtemp(prefix="millesime_chatr_")
webapp = preparer(ADMIN_PANEL_PASSWORD="", TRADUCTION_REPLI="0", DATA_DIR=DOSSIER)
import github_backup
github_backup.backup_file_async = lambda *a, **k: None
github_backup.backup_binaire_async = lambda *a, **k: None
github_backup.supprimer_binaire_async = lambda *a, **k: None
github_backup.telecharger_binaire = lambda *a, **k: b""

import chat
from pathlib import Path
chat._FICHIER = Path(DOSSIER) / "chats.json"
chat._MEDIA_DIR = Path(DOSSIER) / "chat_media"

CLIENT = AUTRE
uid = {"v": CLIENT}
simuler_telegram(webapp, uid)
app = webapp.app.test_client()

print("=" * 64)

titre(1, "Cinquante envois simultanes : aucun message perdu")
# Le verrou du fichier doit tenir : deux ecritures qui se croisent ne
# doivent pas se recouvrir.
erreurs = []


def envoyer(n):
    try:
        chat.ajouter(CLIENT, chat.CLIENT, texte=f"message {n:03d}")
    except Exception as exc:                       # pragma: no cover
        erreurs.append(f"{n}: {exc}")


fils = [threading.Thread(target=envoyer, args=(i,)) for i in range(50)]
for f in fils:
    f.start()
for f in fils:
    f.join()
recus = chat.messages(CLIENT)
textes = {m["texte"] for m in recus}
manquants = [f"message {i:03d}" for i in range(50) if f"message {i:03d}" not in textes]
print(f"   envoyes : 50 | dans le fil : {len(recus)} | manquants : {len(manquants)}")
print(f"   erreurs : {erreurs or 'aucune'}")
assert not erreurs and not manquants

titre(2, "Les identifiants restent uniques")
ids = [m["id"] for m in recus]
print(f"   {len(ids)} messages, {len(set(ids))} identifiants distincts")
assert len(ids) == len(set(ids))

titre(3, "Le fichier reste du JSON valide")
brut = chat._FICHIER.read_text(encoding="utf-8")
data = json.loads(brut)
print(f"   {len(brut)} octets relus sans erreur, {len(data)} fil(s)")

titre(4, "Le fil ne depasse jamais son plafond")
for i in range(chat.MAX_MESSAGES + 40):
    chat.ajouter(CLIENT, chat.VENDEUR, texte=f"remplissage {i}")
n = len(chat.messages(CLIENT))
print(f"   plafond {chat.MAX_MESSAGES} -> {n} message(s) gardes")
assert n == chat.MAX_MESSAGES

titre(5, "Textes hors normes : rien ne casse")
CAS = [
    ("tres long", "a" * 5000),
    ("emoji seul", "🎉🎉🎉"),
    ("cyrillique", "Привет как дела"),
    ("chinois", "你好世界"),
    ("sauts de ligne", "ligne1\nligne2\n\n\nligne4"),
    ("html", "<script>alert(1)</script>"),
    ("guillemets", 'il a dit "bonjour" et \'salut\''),
    ("caracteres de controle", "abc"),
    ("espaces seuls", "        "),
]
for nom, texte in CAS:
    r = app.post("/api/chat/send", json={"initData": "x", "texte": texte})
    assert r.status_code < 500, f"{nom} -> HTTP {r.status_code}"
    print(f"   {nom:22s} -> HTTP {r.status_code}")

titre(6, "Le texte est tronque, jamais refuse en silence")
long = "b" * 5000
d = app.post("/api/chat/send", json={"initData": "x", "texte": long}).get_json()
if d.get("ok"):
    garde = len(d["message"]["texte"])
    print(f"   5000 caracteres -> {garde} gardes (plafond {chat.MAX_TEXTE})")
    assert garde == chat.MAX_TEXTE

titre(7, "Medias abimes : refuses proprement, jamais de 500")
MEDIAS = [
    ("photo vide", {"photo_b64": ""}),
    ("photo illisible", {"photo_b64": "data:image/jpeg;base64,pas-du-base64!!"}),
    ("photo tronquee", {"photo_b64": "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8").decode()}),
    ("audio illisible", {"audio_b64": "data:audio/ogg;base64,???"}),
    ("photo enorme", {"photo_b64": "data:image/jpeg;base64," + "A" * 9_000_000}),
]
ACCEPTEES = []
for nom, charge in MEDIAS:
    r = app.post("/api/chat/send", json={"initData": "x", **charge})
    print(f"   {nom:20s} -> HTTP {r.status_code}")
    assert r.status_code < 500, nom
    if r.get_json().get("ok"):
        ACCEPTEES.append(nom)
# Une photo qu'on ne sait pas decoder ne doit PAS entrer dans le fil : elle y
# resterait sous forme de bulle cassee, que personne ne peut reparer.
print(f"   acceptees a tort : {ACCEPTEES or 'aucune'}")
assert not ACCEPTEES

titre(8, "Repondre a un message inexistant ou efface")
m = chat.ajouter(CLIENT, chat.CLIENT, texte="original")
chat.supprimer(CLIENT, m["id"], chat.CLIENT)
for cible in [m["id"], "nexistepas", "", "x" * 100]:
    r = app.post("/api/chat/send",
                 json={"initData": "x", "texte": "reponse", "repond_a": cible})
    assert r.status_code < 500
print("   4 cibles aberrantes -> aucune erreur serveur")

titre(9, "Lire un media qui n'appartient pas au fil")
autre = 777000111
mid = chat.ecrire_media(b"\xff\xd8" + bytes(300), "photo")
chat.ajouter(autre, chat.CLIENT, media_id=mid, kind="photo")
uid["v"] = CLIENT                                  # un autre client demande
r = app.get(f"/api/chat/media/{mid}?initData=x")
print(f"   media d'autrui -> HTTP {r.status_code}")
assert r.status_code in (403, 404), r.status_code

titre(10, "Le compteur de non-lus ne part jamais dans le negatif")
uid["v"] = CLIENT
for _ in range(3):
    app.post("/api/chat/thread", json={"initData": "x"})
    d = app.post("/api/chat/resume", json={"initData": "x"}).get_json()
    assert d.get("non_lus", 0) >= 0, d
print(f"   non lus apres lecture : {d.get('non_lus')}")

titre(11, "Un fil vide ne cree pas d'entree fantome")
vide = 888000222
avant = len(chat._lire())
app.post("/api/chat/thread", json={"initData": "x", "client_id": vide})
apres = len(chat._lire())
print(f"   fils avant {avant}, apres consultation d'un fil vide : {apres}")
assert apres == avant, "ouvrir un fil vide ne doit rien ecrire"

fin()

"""Suppression d'un message pour les deux côtés de la conversation.

Ce qui doit tenir : on n'efface que ses propres messages, le contenu part
vraiment (texte, traduction, média sur le disque), et rien de ce qui a été
effacé ne subsiste ailleurs — ni dans les citations figées, ni dans l'aperçu
de la liste des conversations.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import preparer, simuler_telegram, titre, fin, OWNER

webapp = preparer(ADMIN_PANEL_PASSWORD="", TRADUCTION_REPLI="0",
                  DATA_DIR=tempfile.mkdtemp(prefix="millesime_suppr_"))
import github_backup
github_backup.backup_file_async = lambda *a, **k: None
github_backup.backup_binaire_async = lambda *a, **k: None
supprimes = []
github_backup.supprimer_binaire_async = lambda chemin: supprimes.append(chemin)

import chat
chat._gh = github_backup

CLIENT = 555000111
uid = {"v": OWNER}
simuler_telegram(webapp, uid)
app = webapp.app.test_client()

print("=" * 62)

titre(1, "Le vendeur efface son message : la trace reste, le texte part")
chat.ajouter(CLIENT, chat.CLIENT, texte="bonjour")
mien = chat.ajouter(CLIENT, chat.VENDEUR, texte="mon numero est le 06",
                    trad={"en": "my number is 06"})
r = app.post("/api/chat/supprimer",
             json={"initData": "x", "client_id": CLIENT, "message_id": mien["id"]})
d = r.get_json()
print(f"   HTTP {r.status_code} -> ok={d.get('ok')}")
assert r.status_code == 200 and d["ok"]
apres = [m for m in chat.messages(CLIENT) if m["id"] == mien["id"]][0]
print(f"   restant : {apres}")
assert apres["supprime"] is True
assert apres["texte"] == "" and "trad" not in apres and "media" not in apres
assert len(chat.messages(CLIENT)) == 2, "la ligne reste dans le fil"

titre(2, "Personne ne peut effacer le message de l'autre")
sien = chat.ajouter(CLIENT, chat.CLIENT, texte="a moi")
r = app.post("/api/chat/supprimer",
             json={"initData": "x", "client_id": CLIENT, "message_id": sien["id"]})
print(f"   vendeur -> message du client : HTTP {r.status_code} ({r.get_json().get('error')})")
assert r.status_code == 403
assert chat.messages(CLIENT)[-1]["texte"] == "a moi", "intact"

titre(3, "Le client efface le sien, pas celui de la boutique")
uid["v"] = CLIENT
r = app.post("/api/chat/supprimer", json={"initData": "x", "message_id": sien["id"]})
print(f"   client -> son message : HTTP {r.status_code}")
assert r.status_code == 200
boutique = chat.ajouter(CLIENT, chat.VENDEUR, texte="a la boutique")
r = app.post("/api/chat/supprimer", json={"initData": "x", "message_id": boutique["id"]})
print(f"   client -> message boutique : HTTP {r.status_code}")
assert r.status_code == 403
uid["v"] = OWNER

titre(4, "Une photo effacee disparait du disque et de la sauvegarde")
media = chat.ecrire_media(b"\xff\xd8\xff" + b"0" * 400, "photo")
photo = chat.ajouter(CLIENT, chat.VENDEUR, media_id=media, kind="photo")
chemin = chat._chemin_media(media)
assert chemin.exists(), "le fichier doit exister avant"
app.post("/api/chat/supprimer",
         json={"initData": "x", "client_id": CLIENT, "message_id": photo["id"]})
print(f"   fichier present apres suppression : {chemin.exists()}")
print(f"   retire de la sauvegarde : {supprimes}")
assert not chemin.exists()
assert f"chat_media/{media}" in supprimes
print(f"   media encore rattache au fil : {chat.contient(media, CLIENT)}")
assert not chat.contient(media, CLIENT), "l'URL du media ne doit plus repondre"

titre(5, "Le texte efface ne survit pas dans une citation figee")
cible = chat.ajouter(CLIENT, chat.VENDEUR, texte="rendez-vous rue de la Loi")
reponse = chat.ajouter(CLIENT, chat.CLIENT, texte="ok", repond_a=cible["id"])
assert "Loi" in reponse["rep"]["apercu"], "la citation cite bien avant"
app.post("/api/chat/supprimer",
         json={"initData": "x", "client_id": CLIENT, "message_id": cible["id"]})
citation = [m for m in chat.messages(CLIENT) if m["id"] == reponse["id"]][0]["rep"]
print(f"   citation apres suppression : {citation}")
assert citation["apercu"] == "" and citation["supprime"] is True

titre(6, "On ne cite pas un message deja efface")
tardif = chat.ajouter(CLIENT, chat.CLIENT, texte="et donc ?", repond_a=cible["id"])
print(f"   rep = {tardif.get('rep')}")
assert "rep" not in tardif

titre(7, "L'apercu de la liste ne montre pas le contenu efface")
dernier = chat.ajouter(CLIENT, chat.VENDEUR, texte="code de la porte 4477")
app.post("/api/chat/supprimer",
         json={"initData": "x", "client_id": CLIENT, "message_id": dernier["id"]})
fil = [f for f in chat.fils() if f["client_id"] == str(CLIENT)][0]
print(f"   dernier : {fil['dernier']}")
assert fil["dernier"]["supprime"] is True and fil["dernier"]["texte"] == ""

titre(8, "Identifiant inconnu, vide ou aberrant : refus propre, pas de 500")
for mauvais in ["", "zzz", None, 42, ["a"], {"a": 1}, "x" * 500]:
    r = app.post("/api/chat/supprimer",
                 json={"initData": "x", "client_id": CLIENT, "message_id": mauvais})
    print(f"   message_id={str(mauvais)[:14]:16s} -> HTTP {r.status_code}")
    assert r.status_code in (400, 404), r.status_code

titre(9, "Supprimer deux fois ne casse rien")
r = app.post("/api/chat/supprimer",
             json={"initData": "x", "client_id": CLIENT, "message_id": mien["id"]})
print(f"   deuxieme passage : HTTP {r.status_code}")
assert r.status_code == 200

titre(10, "Sans authentification, aucune suppression")
uid["v"] = None
r = app.post("/api/chat/supprimer",
             json={"initData": "", "client_id": CLIENT, "message_id": mien["id"]})
print(f"   HTTP {r.status_code}")
assert r.status_code == 401
uid["v"] = OWNER

fin()

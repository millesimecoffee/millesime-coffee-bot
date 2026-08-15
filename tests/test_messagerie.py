"""Messagerie privée vendeur ↔ client dans la Mini App."""
import base64
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import preparer, simuler_telegram, titre, fin, OWNER, AUTRE

DOSSIER = tempfile.mkdtemp(prefix="millesime_chat_")
webapp = preparer(ADMIN_PANEL_PASSWORD="", DATA_DIR=DOSSIER)
uid = {"v": AUTRE}
simuler_telegram(webapp, uid)

import chat
import storage

CLIENT = AUTRE
AUTRE_CLIENT = 555000111

storage._load = lambda: [{"order_id": "M1", "user_id": CLIENT, "user_name": "Joe",
                          "username": "", "city": "Bruxelles", "country": "🇧🇪 Belgique",
                          "status": "delivered", "total": 100, "cart": {},
                          "created_at": webapp._now_iso()}]

# Aucun appel réseau : ni Telegram, ni Pushover, ni GitHub.
envois = []
import httpx
httpx.post = lambda url, **kw: type("R", (), {"status_code": 200, "text": "{}",
                                              "json": lambda s: {"ok": True}})()
import github_backup
_vrai_envoyer_binaire = github_backup.envoyer_binaire
github_backup.backup_file_async = lambda *a, **k: None
github_backup.backup_binaire_async = lambda *a, **k: envois.append(a[0])
github_backup.telecharger_binaire = lambda *a, **k: b""

app = webapp.app.test_client()

# Vraie image JPEG, encodee par cv2 : l'ancien fixture avait un en-tete
# JPEG mais n'etait pas decodable, et le serveur le stockait quand meme.
PIXEL = base64.b64encode(bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb00430006040506050406060506070706"
    "080a100a0a09090a140e0f0c1017141818171416161a1d251f1a1b231c1616202c2023262729"
    "2a29191f2d302d283025282928ffdb0043010707070a080a130a0a13281a161a282828282828"
    "2828282828282828282828282828282828282828282828282828282828282828282828282828"
    "282828282828ffc00011080002000203012200021101031101ffc4001f000001050101010101"
    "0100000000000000000102030405060708090a0bffc400b51000020103030204030505040400"
    "00017d01020300041105122131410613516107227114328191a1082342b1c11552d1f0243362"
    "7282090a161718191a25262728292a3435363738393a434445464748494a535455565758595a"
    "636465666768696a737475767778797a838485868788898a92939495969798999aa2a3a4a5a6"
    "a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7"
    "e8e9eaf1f2f3f4f5f6f7f8f9faffc4001f010003010101010101010101000000000000010203"
    "0405060708090a0bffc400b51100020102040403040705040400010277000102031104052131"
    "061241510761711322328108144291a1b1c109233352f0156272d10a162434e125f11718191a"
    "262728292a35363738393a434445464748494a535455565758595a636465666768696a737475"
    "767778797a82838485868788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7"
    "b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae2e3e4e5e6e7e8e9eaf2f3f4f5f6f7f8f9"
    "faffda000c03010002110311003f00f962e2796e6e259ee6579a7958bc9248c599d89c9249e4"
    "927bd145159d2f823e88a96ecfffd9"
)).decode()


def envoyer(**corps):
    return app.post("/api/chat/send", json={"initData": "x", **corps})


def fil(**corps):
    return app.post("/api/chat/thread", json={"initData": "x", **corps})


print("=" * 62)

titre(1, "Le client ecrit, le vendeur lit")
uid["v"] = CLIENT
r = envoyer(texte="Bonjour, ma commande arrive quand ?").get_json()
print(f"   envoi client : ok={r['ok']} type={r['message']['type']}")
assert r["ok"] and r["message"]["de"] == "client"
uid["v"] = OWNER
d = fil(client_id=CLIENT).get_json()
print(f"   le vendeur voit {len(d['messages'])} message : {d['messages'][0]['texte']!r}")
print(f"   profil rattache : {d['profil'].get('user_name')} — {d['profil'].get('city')}")
assert d["role"] == "vendeur" and len(d["messages"]) == 1

titre(2, "Le vendeur repond, le client lit")
r = envoyer(client_id=CLIENT, texte="Dans 20 minutes !").get_json()
assert r["message"]["de"] == "vendeur"
uid["v"] = CLIENT
d = fil().get_json()
print(f"   le client voit {len(d['messages'])} messages, dernier de « {d['messages'][-1]['de']} »")
assert len(d["messages"]) == 2 and d["role"] == "client"

titre(3, "Un client ne peut pas ouvrir la conversation d'un autre")
uid["v"] = AUTRE_CLIENT
d = fil(client_id=CLIENT).get_json()
print(f"   client_id force a {CLIENT} -> fil rendu : {d['client_id']} ({len(d['messages'])} messages)")
assert d["client_id"] == str(AUTRE_CLIENT) and d["messages"] == []

titre(4, "Photo : compressee, stockee hors du JSON, servie a qui de droit")
uid["v"] = CLIENT
r = envoyer(photo_b64="data:image/jpeg;base64," + PIXEL).get_json()
media = r["message"]["media"]
print(f"   message type={r['message']['type']} media={media}")
assert r["message"]["type"] == "photo" and media.endswith(".jpg")
taille_json = os.path.getsize(os.path.join(DOSSIER, "chats.json"))
fichiers = os.listdir(os.path.join(DOSSIER, "chat_media"))
print(f"   chats.json : {taille_json} octets — chat_media/ : {len(fichiers)} fichier(s)")
assert media not in open(os.path.join(DOSSIER, "chats.json"), encoding="utf-8").read().replace(media, media)[:0] + "", ""
contenu = open(os.path.join(DOSSIER, "chats.json"), encoding="utf-8").read()
assert PIXEL[:40] not in contenu, "la photo ne doit pas etre dans le JSON"
print(f"   sauvegarde distante demandee : {envois[-1]}")
assert envois[-1].startswith("chat_media/")

titre(5, "La photo est servie au client et au vendeur, a personne d'autre")
r = app.get(f"/api/chat/media/{media}?initData=x")
print(f"   client proprietaire : HTTP {r.status_code} ({r.headers.get('Content-Type')})")
assert r.status_code == 200 and r.headers["Content-Type"].startswith("image/")
uid["v"] = OWNER
r = app.get(f"/api/chat/media/{media}?initData=x&client_id={CLIENT}")
print(f"   vendeur             : HTTP {r.status_code}")
assert r.status_code == 200
uid["v"] = AUTRE_CLIENT
r = app.get(f"/api/chat/media/{media}?initData=x")
print(f"   client tiers        : HTTP {r.status_code} (404 attendu)")
assert r.status_code == 404

titre(6, "Message vocal avec sa duree")
uid["v"] = CLIENT
r = envoyer(audio_b64=base64.b64encode(b"OggS" + b"\x00" * 5000).decode(),
            duree=12).get_json()
print(f"   type={r['message']['type']} duree={r['message']['duree']} s media={r['message']['media']}")
assert r["message"]["type"] == "audio" and r["message"]["duree"] == 12
assert r["message"]["media"].endswith(".ogg")

titre(7, "Compteur de non-lus, des deux cotes")
print("    (photo et audio envoyes dans la meme seconde : l'horodatage a la")
print("     seconde ne suffit pas a les distinguer, on suit l'identifiant)")
uid["v"] = OWNER
n = app.post("/api/chat/resume", json={"initData": "x"}).get_json()
print(f"   vendeur : {n['non_lus']} non lus (2 attendus : photo, audio)")
assert n["non_lus"] == 2
fil(client_id=CLIENT)                      # le vendeur ouvre le fil
n = app.post("/api/chat/resume", json={"initData": "x"}).get_json()
print(f"   apres lecture : {n['non_lus']}")
assert n["non_lus"] == 0

titre(8, "Liste des conversations, la plus recente en tete")
uid["v"] = AUTRE_CLIENT
envoyer(texte="Moi aussi j'ai une question")
uid["v"] = OWNER
d = app.post("/api/chat/threads", json={"initData": "x"}).get_json()
for f in d["threads"]:
    print(f"   {f['client_id']:<12s} {f['total']} msg  non lus={f['non_lus']}  "
          f"dernier: {f['dernier']['texte'][:28] or f['dernier']['type']!r}")
assert d["threads"][0]["client_id"] == str(AUTRE_CLIENT)
assert d["non_lus"] == 1

titre(9, "Un client n'accede pas a la liste des conversations")
uid["v"] = CLIENT
r = app.post("/api/chat/threads", json={"initData": "x"})
print(f"   HTTP {r.status_code} ({r.get_json().get('error')})")
assert r.status_code in (401, 403)

titre(10, "Message vide, trop long, ou mal forme")
r = envoyer(texte="")
print(f"   vide        : HTTP {r.status_code} ({r.get_json().get('error')})")
assert r.status_code == 400
r = envoyer(texte="a" * 5000).get_json()
print(f"   5000 signes : tronque a {len(r['message']['texte'])}")
assert len(r["message"]["texte"]) == chat.MAX_TEXTE
r = envoyer(photo_b64="pas du base64 du tout !!!")
print(f"   photo cassee: HTTP {r.status_code} ({r.get_json().get('error')})")
assert r.status_code == 400
r = envoyer(audio_b64=base64.b64encode(b"x" * (chat.MAX_MEDIA + 10)).decode())
print(f"   audio 3 Mo+ : HTTP {r.status_code} ({r.get_json().get('error')})")
assert r.status_code == 413

titre(11, "Sans session Telegram valide : rien n'est accessible")
for route, corps in [("/api/chat/thread", {}), ("/api/chat/send", {"texte": "hop"}),
                     ("/api/chat/threads", {})]:
    r = app.post(route, json={"initData": "", **corps})
    print(f"   {route:22s} HTTP {r.status_code}")
    assert r.status_code == 401

titre(12, "L'admin en mode client ouvre son propre fil, pas une erreur")
print("    (la carte « Discuter avec le vendeur » n'envoie aucun destinataire)")
uid["v"] = OWNER
d = fil().get_json()
print(f"   role={d['role']} fil={d['client_id']} (le sien)")
assert d["ok"] and d["role"] == "client" and d["client_id"] == str(OWNER)
r = app.post("/api/chat/send", json={"initData": "x", "texte": "essai en mode client"})
print(f"   envoi : HTTP {r.status_code}, de « {r.get_json()['message']['de']} »")
assert r.status_code == 200 and r.get_json()["message"]["de"] == "client"
d = app.post("/api/chat/thread", json={"initData": "x", "client_id": CLIENT}).get_json()
print(f"   avec un destinataire, il redevient vendeur : role={d['role']}")
assert d["role"] == "vendeur"

titre(13, "Un media inconnu ou un chemin piege ne sort pas du dossier")
uid["v"] = CLIENT
for faux in ["inexistant.jpg", "..%2F..%2Fetc%2Fpasswd", "....//chats.json"]:
    r = app.get(f"/api/chat/media/{faux}?initData=x")
    print(f"   {faux[:26]:28s} HTTP {r.status_code}")
    assert r.status_code in (400, 403, 404)

titre(14, "Le fil ne grossit pas sans fin")
print(f"   plafond : {chat.MAX_MESSAGES} messages conserves par conversation")
gros = [{"id": str(i), "de": "client", "type": "texte", "texte": "x", "at": "2026-01-01T00:00:00+01:00"}
        for i in range(chat.MAX_MESSAGES + 50)]
data = chat._lire()
data[str(CLIENT)]["messages"] = gros
chat._ecrire(data)
chat.ajouter(CLIENT, "vendeur", texte="le dernier")
restants = chat.messages(CLIENT)
print(f"   apres {len(gros)} + 1 messages : {len(restants)} conserves, dernier = {restants[-1]['texte']!r}")
assert len(restants) == chat.MAX_MESSAGES and restants[-1]["texte"] == "le dernier"

titre("14b", "Un client SANS commande qui ecrit en francais lit en francais")
print("    (sans ce reglage, il recevait les reponses traduites en anglais,")
print("     la langue par defaut)")
uid["v"] = 424242424          # aucun historique de commande
r = app.post("/api/chat/send",
             json={"initData": "x", "texte": "Bonjour, vous livrez ce soir ?"})
assert r.status_code == 200 and r.get_json()["message"].get("lang") == "fr"
d = app.post("/api/chat/thread", json={"initData": "x"}).get_json()
print(f"   langue detectee sur son message : fr — ma_langue = {d['ma_langue']!r}")
assert d["ma_langue"] == "fr", "sa langue doit venir de ce qu'il ecrit"
uid["v"] = AUTRE

titre(15, "Ouvrir la messagerie sans ecrire ne cree pas de fil vide")
uid["v"] = 777000333
fil()
apres = list(chat._lire())
print(f"   visiteur 777000333 apres ouverture : present = {'777000333' in apres}")
assert "777000333" not in apres
uid["v"] = OWNER
noms = [f["client_id"] for f in app.post("/api/chat/threads",
                                         json={"initData": "x"}).get_json()["threads"]]
print(f"   conversations listees : {noms}")
assert "777000333" not in noms

titre(16, "Sauvegarde distante : jamais deux envois en meme temps")
print("    (chaque envoi cree un commit sur la meme branche ; deux commits")
print("     simultanes se soldent par un 409, meme sur des chemins differents)")
import threading as _th
import time as _t

github_backup._TOKEN = "faux-jeton"
en_cours, chevauchements, faits = [], [], []
verrou_obs = _th.Lock()


class ReponsePut:
    status_code = 201

    def json(self):
        return {"content": {"sha": "abc"}}


def faux_put(url, headers=None, json=None, timeout=None, **kw):
    with verrou_obs:
        if en_cours:
            chevauchements.append(url)
        en_cours.append(url)
    _t.sleep(0.02)                      # le temps d'un aller-retour reseau
    with verrou_obs:
        en_cours.remove(url)
        faits.append(url)
    return ReponsePut()


httpx.put = faux_put
fils = [_th.Thread(target=github_backup.envoyer_binaire,
                   args=(f"chat_media/{i}.jpg", b"x" * 100)) for i in range(12)]
for f in fils:
    f.start()
for f in fils:
    f.join()
print(f"   {len(faits)} envois, {len(chevauchements)} chevauchement(s)")
assert len(faits) == 12 and not chevauchements

titre(17, "Un conflit GitHub est reessaye, pas abandonne")
essais = {"n": 0}


class Conflit:
    def __init__(self, code):
        self.status_code = code

    def json(self):
        return {}


def put_capricieux(url, headers=None, json=None, timeout=None, **kw):
    essais["n"] += 1
    return Conflit(409) if essais["n"] < 3 else Conflit(201)


httpx.put = put_capricieux
ok = github_backup.envoyer_binaire("chat_media/retente.jpg", b"data")
print(f"   deux conflits puis succes : envoi={ok} apres {essais['n']} tentatives")
assert ok and essais["n"] == 3

shutil.rmtree(DOSSIER, ignore_errors=True)
fin()

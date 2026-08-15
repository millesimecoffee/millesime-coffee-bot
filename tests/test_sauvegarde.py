"""La sauvegarde GitHub ne doit renvoyer que ce qui a réellement changé.

Un travail périodique repousse les six fichiers toutes les dix minutes. Sans
contrôle du contenu, cela faisait environ 800 commits par jour — dont des
fichiers de deux octets — et chaque commit garde une copie entière du fichier.
Sur un an, l'historique du dépôt devenait ingérable.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import titre, fin

os.environ["GITHUB_TOKEN"] = "jeton-de-test"
DOSSIER = tempfile.mkdtemp(prefix="millesime_sauv_")
os.environ["DATA_DIR"] = DOSSIER

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import github_backup as gh
from pathlib import Path

gh._DATA_DIR = Path(DOSSIER)

# On enregistre les appels réseau au lieu de les faire.
envois, lectures = [], []


class Reponse:
    def __init__(self, code=200, corps=None):
        self.status_code = code
        self._corps = corps or {"content": {"sha": "sha-neuf"}, "sha": "sha-neuf"}

    def json(self):
        return self._corps

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


gh.httpx.put = lambda url, **kw: (envois.append(url.rsplit("/", 1)[-1]), Reponse())[1]
gh.httpx.get = lambda url, **kw: (lectures.append(url), Reponse())[1]

FICHIER = Path(DOSSIER) / "orders.json"


def ecrire(contenu: str):
    FICHIER.write_text(contenu, encoding="utf-8")


print("=" * 62)

titre(1, "Premier envoi : le fichier part")
ecrire('[{"order_id": "A1"}]')
envois.clear()
assert gh.upload_file("orders.json") is True
print(f"   envois : {envois}")
assert envois == ["orders.json"]

titre(2, "Contenu inchange : plus rien ne part")
for i in range(20):
    envois.clear()
    assert gh.upload_file("orders.json") is True
    assert envois == [], f"passage {i + 1} : {envois}"
print("   20 passages a contenu identique -> 0 envoi")

titre(3, "Le contenu change : l'envoi repart")
ecrire('[{"order_id": "A1"}, {"order_id": "A2"}]')
envois.clear()
assert gh.upload_file("orders.json") is True
print(f"   envois : {envois}")
assert envois == ["orders.json"]
envois.clear()
gh.upload_file("orders.json")
assert envois == [], "et se retait aussitot"
print("   puis se retait")

titre(4, "Un envoi rate n'est pas pris pour un succes")
ecrire('[{"order_id": "A3"}]')
gh.httpx.put = lambda url, **kw: (envois.append("echec"), Reponse(500))[1]
envois.clear()
assert gh.upload_file("orders.json") is False
print(f"   echec -> {envois}")
# Le contenu n'a pas change, mais comme l'envoi a rate il doit etre retente.
gh.httpx.put = lambda url, **kw: (envois.append(url.rsplit("/", 1)[-1]), Reponse())[1]
envois.clear()
assert gh.upload_file("orders.json") is True
print(f"   nouvelle tentative -> {envois}")
assert envois == ["orders.json"], "un echec doit etre reessaye, pas oublie"

titre(5, "`forcer` passe outre le controle")
envois.clear()
gh.upload_file("orders.json")
assert envois == []
gh.upload_file("orders.json", forcer=True)
print(f"   forcer=True -> {envois}")
assert envois == ["orders.json"]

titre(6, "Ce qu'on vient de telecharger n'est pas renvoye")
import base64
contenu = b'[{"order_id": "B1"}]'
gh.httpx.get = lambda url, **kw: Reponse(200, {
    "content": base64.b64encode(contenu).decode(), "sha": "sha-distant"})
gh._empreintes.pop("orders.json", None)
assert gh.download_file("orders.json") is True
envois.clear()
gh.upload_file("orders.json")
print(f"   apres telechargement -> envois : {envois}")
assert envois == [], "un redemarrage ne doit pas renvoyer les fichiers inchanges"

titre(7, "backup_all sur six fichiers identiques : aucun commit")
for nom in gh._FILES:
    chemin = Path(DOSSIER) / nom
    chemin.write_text("{}", encoding="utf-8")
    gh._empreintes.pop(nom, None)
envois.clear()
gh.backup_all()
premier = len(envois)
envois.clear()
gh.backup_all()
gh.backup_all()
print(f"   1er passage : {premier} envoi(s) | 2e et 3e : {len(envois)}")
assert premier == len(gh._FILES)
assert envois == [], "les passages suivants ne doivent rien renvoyer"

titre(8, "Economie sur une journee de travail periodique")
# 144 passages par jour (toutes les 10 min) x 6 fichiers
envois.clear()
for _ in range(144):
    gh.backup_all()
print(f"   144 passages x {len(gh._FILES)} fichiers = {144 * len(gh._FILES)} envois avant")
print(f"   apres correction : {len(envois)} envoi(s)")
assert envois == []

fin()

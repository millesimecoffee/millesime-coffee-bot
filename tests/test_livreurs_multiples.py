"""Plusieurs livreurs, plusieurs zones — et aucun croisement.

Bruxelles (une ville), l'Espagne (trois villes) et le Sud (trois PAYS
entiers : Italie, Croatie, Grèce). Aucun ne doit voir les courses d'un autre,
ni pouvoir agir dessus, et chacun reçoit ses propres notifications.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import preparer, simuler_telegram, titre, fin, OWNER

webapp = preparer(
    ADMIN_PANEL_PASSWORD="RICH PORTER",
    # Livreur 1 — Belgique
    LIVREUR_PASSWORD="LIVREUR BRUXELLES",
    LIVREUR_ZONES="Belgique:Bruxelles",
    LIVREUR_CHAT_ID="8544248639",
    LIVREUR_USERNAME="yofast17",
    # Livreur 2 — Espagne
    LIVREUR2_PASSWORD="LIVREUR ESPAGNE",
    LIVREUR2_ZONES="Espagne:Barcelone, Espagne:Marbella, Espagne:Malaga",
    LIVREUR2_CHAT_ID="",
    LIVREUR2_USERNAME="",
    # Livreur 3 — trois pays entiers, sans preciser de ville
    LIVREUR3_PASSWORD="SIROCCO SUD 83",
    LIVREUR3_ZONES="Italie, Croatie, Grece",
    LIVREUR3_CHAT_ID="",
    LIVREUR3_USERNAME="",
    # Livreur 4 — deux iles espagnoles, PAS le reste de l'Espagne
    LIVREUR4_PASSWORD="SALINAS ILES 71",
    LIVREUR4_ZONES="Espagne:Ibiza, Espagne:Palma De Majorque",
    LIVREUR4_CHAT_ID="",
    LIVREUR4_USERNAME="",
    # Livreur 5 — le Portugal en entier
    LIVREUR5_PASSWORD="ALGARVE PORTUGAL 28",
    LIVREUR5_ZONES="Portugal",
    LIVREUR5_CHAT_ID="",
    LIVREUR5_USERNAME="",
    DATA_DIR=tempfile.mkdtemp(prefix="millesime_2lv_"))

import github_backup
github_backup.backup_file_async = lambda *a, **k: None

BXL = 8544248639
ESP = 700000123
INTRUS = 999000111

qui = {"v": BXL}
simuler_telegram(webapp, qui)

import storage
COMMANDES = [
    {"order_id": "BXL1", "user_id": 111, "status": "pending", "total": 100,
     "country": "🇧🇪 Belgique", "city": "Bruxelles", "cart": {}, "user_name": "Ann",
     "created_at": "2026-08-15T10:00:00+02:00"},
    {"order_id": "BCN1", "user_id": 222, "status": "pending", "total": 200,
     "country": "🇪🇸 Espagne", "city": "Barcelone", "cart": {}, "user_name": "Pau",
     "created_at": "2026-08-15T10:00:00+02:00"},
    {"order_id": "MRB1", "user_id": 333, "status": "confirmed", "total": 250,
     "country": "🇪🇸 Espagne", "city": "Marbella", "cart": {}, "user_name": "Luz",
     "created_at": "2026-08-15T10:00:00+02:00"},
    {"order_id": "MLG1", "user_id": 444, "status": "pending", "total": 220,
     "country": "🇪🇸 Espagne", "city": "Malaga", "cart": {}, "user_name": "Rio",
     "created_at": "2026-08-15T10:00:00+02:00"},
    {"order_id": "PAR1", "user_id": 555, "status": "pending", "total": 90,
     "country": "🇫🇷 France", "city": "Paris", "cart": {}, "user_name": "Zoe",
     "created_at": "2026-08-15T10:00:00+02:00"},
    {"order_id": "ROM1", "user_id": 666, "status": "pending", "total": 150,
     "country": "🇮🇹 Italie", "city": "Rome", "cart": {}, "user_name": "Gio",
     "created_at": "2026-08-15T10:00:00+02:00"},
    {"order_id": "SPL1", "user_id": 777, "status": "confirmed", "total": 180,
     "country": "🇭🇷 Croatie", "city": "Split", "cart": {}, "user_name": "Ana",
     "created_at": "2026-08-15T10:00:00+02:00"},
    {"order_id": "MYK1", "user_id": 888, "status": "pending", "total": 300,
     "country": "🇬🇷 Grèce", "city": "Mykonos", "cart": {}, "user_name": "Nikos",
     "created_at": "2026-08-15T10:00:00+02:00"},
    {"order_id": "MIL1", "user_id": 999, "status": "pending", "total": 200,
     "country": "🇮🇹 Italie", "city": "Milan", "cart": {}, "user_name": "Luca",
     "created_at": "2026-08-15T10:00:00+02:00"},
    # Deux commandes annulees : elles ne doivent apparaitre chez personne.
    {"order_id": "CRE1", "user_id": 1010, "status": "cancelled", "total": 300,
     "country": "🇬🇷 Grèce", "city": "Crète", "cart": {}, "user_name": "Millésime",
     "created_at": "2026-08-02T15:47:00+02:00"},
    {"order_id": "BXL9", "user_id": 1011, "status": "cancelled_by_client", "total": 80,
     "country": "🇧🇪 Belgique", "city": "Bruxelles", "cart": {}, "user_name": "Sam",
     "created_at": "2026-08-10T10:00:00+02:00"},
    # Une livree, pour verifier que les stats ne bougent pas.
    {"order_id": "ATH1", "user_id": 1012, "status": "delivered", "total": 400,
     "country": "🇬🇷 Grèce", "city": "Athènes", "cart": {}, "user_name": "Elia",
     "created_at": "2026-08-14T10:00:00+02:00",
     "_delivered_at": "2026-08-14T12:00:00+02:00"},
    # Les iles, et le reste de l'Espagne qui ne doit PAS leur revenir.
    {"order_id": "PLM1", "user_id": 1201, "status": "pending", "total": 260,
     "country": "🇪🇸 Espagne", "city": "Palma De Majorque", "cart": {},
     "user_name": "Neus", "created_at": "2026-08-15T09:00:00+02:00"},
    {"order_id": "TEN1", "user_id": 1202, "status": "pending", "total": 190,
     "country": "🇪🇸 Espagne", "city": "Tenerife", "cart": {}, "user_name": "Aday",
     "created_at": "2026-08-15T09:00:00+02:00"},
    # Le Portugal.
    {"order_id": "LIS1", "user_id": 1301, "status": "pending", "total": 210,
     "country": "🇵🇹 Portugal", "city": "Lisbonne", "cart": {}, "user_name": "Rui",
     "created_at": "2026-08-15T09:00:00+02:00"},
    {"order_id": "ALB1", "user_id": 1302, "status": "confirmed", "total": 340,
     "country": "🇵🇹 Portugal", "city": "Albufeira", "cart": {}, "user_name": "Ana",
     "created_at": "2026-08-15T09:00:00+02:00"},
]
storage._load = lambda: [dict(o) for o in COMMANDES]
storage.get_order = lambda oid: next((dict(o) for o in COMMANDES if o["order_id"] == oid), None)
storage.update_order = lambda oid, upd: True

envois = []


class Reponse:
    status_code = 200

    def json(self):
        return {"ok": True, "result": {}}


import httpx
httpx.post = lambda url, **kw: (envois.append(kw.get("json") or {}), Reponse())[1]
httpx.get = lambda *a, **k: Reponse()

app = webapp.app.test_client()


def entrer(uid, mdp):
    qui["v"] = uid
    webapp._pwd_attempts.clear()
    webapp._rate_store.clear()
    return app.post("/api/auth", json={"initData": "x", "password": mdp}).get_json()


def courses():
    return app.post("/api/livreur/courses", json={"initData": "x"})


print("=" * 66)

titre(1, "Les deux mots de passe ouvrent chacun leur acces")
d1 = entrer(BXL, "livreur bruxelles")
print(f"   Bruxelles -> ok={d1.get('ok')}")
assert d1.get("ok")
d2 = entrer(ESP, "livreur espagne")
print(f"   Espagne   -> ok={d2.get('ok')}")
assert d2.get("ok")

titre(2, "Chacun ne voit que ses propres courses")
entrer(BXL, "livreur bruxelles")
r = courses().get_json()
ids_bxl = sorted(c["order_id"] for c in r["courses"])
print(f"   Bruxelles : zones {r['zones']} -> {ids_bxl}")
assert ids_bxl == ["BXL1"], ids_bxl

entrer(ESP, "livreur espagne")
r = courses().get_json()
ids_esp = sorted(c["order_id"] for c in r["courses"])
print(f"   Espagne   : zones {r['zones']} -> {ids_esp}")
assert ids_esp == ["BCN1", "MLG1", "MRB1"], ids_esp

titre(3, "Aucun croisement : Paris n'est a personne")
assert "PAR1" not in ids_bxl + ids_esp
print("   PAR1 n'apparait chez aucun des deux")

titre(4, "Un livreur ne peut pas agir sur la course de l'autre")
entrer(ESP, "livreur espagne")
r = app.post("/api/livreur/course/BXL1/status",
             json={"initData": "x", "status": "delivering"})
print(f"   Espagne -> commande de Bruxelles : HTTP {r.status_code}")
assert r.status_code in (403, 404)
r = app.post("/api/livreur/course/BCN1/status",
             json={"initData": "x", "status": "confirmed"})
print(f"   Espagne -> sa propre commande  : HTTP {r.status_code}")
assert r.status_code == 200

entrer(BXL, "livreur bruxelles")
r = app.post("/api/livreur/course/MLG1/status",
             json={"initData": "x", "status": "delivering"})
print(f"   Bruxelles -> commande d'Espagne : HTTP {r.status_code}")
assert r.status_code in (403, 404)

titre(5, "Le mot de passe de l'un n'ouvre pas l'acces de l'autre")
# ESP tente le mot de passe de Bruxelles : le compte n'est pas declare cote 1.
d = entrer(ESP, "livreur bruxelles")
print(f"   Espagne avec le mot de passe de Bruxelles -> ok={d.get('ok')}")
assert not d.get("ok"), "LIVREUR_CHAT_ID protege le premier acces"

titre(6, "Un inconnu avec le mot de passe espagnol entre (aucun compte declare)")
d = entrer(INTRUS, "livreur espagne")
print(f"   inconnu -> ok={d.get('ok')}  (LIVREUR2_CHAT_ID vide)")
assert d.get("ok"), "sans liste, on doit pouvoir inscrire le livreur"
r = courses().get_json()
print(f"   il voit : {sorted(c['order_id'] for c in r['courses'])}")
assert sorted(c["order_id"] for c in r["courses"]) == ["BCN1", "MLG1", "MRB1"]

titre(7, "Une fois LIVREUR2_CHAT_ID renseigne, lui seul entre")
os.environ["LIVREUR2_CHAT_ID"] = str(ESP)
webapp._livreur_unlocked.clear()
d = entrer(INTRUS, "livreur espagne")
print(f"   inconnu -> ok={d.get('ok')}")
assert not d.get("ok")
d = entrer(ESP, "livreur espagne")
print(f"   le livreur declare -> ok={d.get('ok')}")
assert d.get("ok")
os.environ["LIVREUR2_CHAT_ID"] = ""

titre(8, "Chaque nouvelle course part au bon livreur")
webapp._livreurs_connus.clear()
webapp._retenir_livreur(BXL, "LIVREUR")
webapp._retenir_livreur(ESP, "LIVREUR2")
os.environ["LIVREUR2_CHAT_ID"] = str(ESP)
for cmd, attendu in ((COMMANDES[0], str(BXL)), (COMMANDES[1], str(ESP))):
    envois.clear()
    webapp._prevenir_livreur("test", prefixe=webapp._prefixe_pour_commande(cmd))
    cibles = [str(e.get("chat_id")) for e in envois]
    print(f"   {cmd['city']:10s} -> {cibles}")
    assert cibles == [attendu], cibles
os.environ["LIVREUR2_CHAT_ID"] = ""

titre(9, "Le registre retient a quel acces appartient chaque compte")
print(f"   {webapp._livreurs_connus}")
assert webapp._prefixe_connu(webapp._livreurs_connus[str(BXL)]) == "LIVREUR"
assert webapp._prefixe_connu(webapp._livreurs_connus[str(ESP)]) == "LIVREUR2"

titre(10, "Une entree de l'ancien format reste lisible")
webapp._livreurs_connus["123456"] = 1786700000.0        # ancien format
print(f"   ancien format -> livreur {webapp._prefixe_connu(webapp._livreurs_connus['123456'])}")
assert webapp._prefixe_connu(webapp._livreurs_connus["123456"]) == "LIVREUR"

SUD = 800000321
titre(11, "Un troisieme livreur couvre trois PAYS entiers")
d = entrer(SUD, "sirocco sud 83")
print(f"   acces -> ok={d.get('ok')}")
assert d.get("ok")
r = courses().get_json()
ids = sorted(c["order_id"] for c in r["courses"])
print(f"   zones : {r['zones']}")
print(f"   courses : {ids}")
assert ids == ["ATH1", "MIL1", "MYK1", "ROM1", "SPL1"], ids

titre("11b", "Une commande ANNULEE n'apparait pas dans ses courses")
# Elle n'est ni une course a faire, ni un gain : elle encombrait l'ecran et
# pouvait passer pour une course en attente.
r2 = courses().get_json()
tous = [c["order_id"] for c in r2["courses"]]
print(f"   courses affichees : {sorted(tous)}")
print(f"   CRE1 (annulee) visible : {'CRE1' in tous}")
assert "CRE1" not in tous, "une commande annulee ne doit pas etre proposee"
assert "ATH1" in tous, "une livree reste dans son historique"

titre("11c", "Mais elle ne fausse pas ses statistiques")
st = r2.get("stats") or {}
periodes = {k: v for k, v in st.items() if isinstance(v, dict) and "ca" in v}
print(f"   par periode : {periodes}")
# Seule ATH1 (400 EUR, livree) compte. Les 300 de l'annulee ne doivent
# apparaitre nulle part, et le nombre de courses comptees reste 1.
for nom, v in periodes.items():
    assert v["ca"] in (0.0, 400.0), (nom, v)
    assert v["n"] in (0, 1), (nom, v)
print("   l'annulee (300) ne compte nulle part")

titre(12, "Il ne voit rien des autres zones")
for interdit in ("BXL1", "BCN1", "MRB1", "MLG1", "PAR1", "BXL9"):
    assert interdit not in ids, interdit
print("   ni Bruxelles, ni Espagne, ni Paris")

titre(13, "Et les autres ne voient rien du sud")
entrer(BXL, "livreur bruxelles")
a = sorted(c["order_id"] for c in courses().get_json()["courses"])
print(f"   annulee de Bruxelles visible : {'BXL9' in a}")
assert "BXL9" not in a, "l'annulee de Bruxelles ne doit pas s'afficher non plus"
entrer(ESP, "livreur espagne")
b = sorted(c["order_id"] for c in courses().get_json()["courses"])
print(f"   Bruxelles : {a}")
print(f"   Espagne   : {b}")
for interdit in ("ROM1", "SPL1", "MYK1", "MIL1"):
    assert interdit not in a + b, interdit

titre(14, "Chaque course part au bon livreur")
webapp._livreurs_connus.clear()
os.environ["LIVREUR3_CHAT_ID"] = str(SUD)
for cmd, attendu in ((COMMANDES[5], str(SUD)), (COMMANDES[7], str(SUD)),
                     (COMMANDES[0], str(BXL))):
    envois.clear()
    webapp._prevenir_livreur("test", prefixe=webapp._prefixe_pour_commande(cmd))
    cibles = [str(e.get("chat_id")) for e in envois]
    print(f"   {cmd['city']:10s} -> {cibles}")
    assert cibles == [attendu], (cmd["city"], cibles)
os.environ["LIVREUR3_CHAT_ID"] = ""

titre(15, "Un acces pour deux iles seulement")
ILES = 810000111
d = entrer(ILES, "salinas iles 71")
print(f"   acces -> ok={d.get('ok')}")
assert d.get("ok")
r = courses().get_json()
ids = sorted(c["order_id"] for c in r["courses"])
print(f"   zones   : {r['zones']}")
print(f"   courses : {ids}")
assert ids == ["PLM1"], ids
print("   Tenerife (Espagne, hors zone) reste dehors : "
      f"{'TEN1' not in ids}")
assert "TEN1" not in ids, "les iles ne prennent pas toute l'Espagne"
for interdit in ("BCN1", "MRB1", "MLG1"):
    assert interdit not in ids, interdit
print("   ni Barcelone, ni Marbella, ni Malaga")

titre(16, "Un acces pour tout le Portugal")
PORT = 820000222
d = entrer(PORT, "algarve portugal 28")
assert d.get("ok")
r = courses().get_json()
ids_p = sorted(c["order_id"] for c in r["courses"])
print(f"   zones   : {r['zones']}")
print(f"   courses : {ids_p}")
assert ids_p == ["ALB1", "LIS1"], ids_p

titre(17, "Les cinq acces ne se recouvrent jamais")
vues = {}
for nom, uid, mdp in (("Bruxelles", BXL, "livreur bruxelles"),
                      ("Espagne", ESP, "livreur espagne"),
                      ("Sud", SUD, "sirocco sud 83"),
                      ("Iles", ILES, "salinas iles 71"),
                      ("Portugal", PORT, "algarve portugal 28")):
    entrer(uid, mdp)
    vues[nom] = {c["order_id"] for c in courses().get_json()["courses"]}
    print(f"   {nom:10s} : {sorted(vues[nom])}")
noms = list(vues)
for i in range(len(noms)):
    for j in range(i + 1, len(noms)):
        commun = vues[noms[i]] & vues[noms[j]]
        assert not commun, f"{noms[i]} et {noms[j]} partagent {commun}"
print("   aucun recouvrement entre les cinq")

titre(18, "Une ville sans livreur ne revient a personne")
# Tenerife et Lanzarote ne sont dans aucune zone : elles ne doivent apparaitre
# nulle part, et aucune notification ne doit partir pour elles.
toutes_vues = set().union(*vues.values())
print(f"   TEN1 (Tenerife) visible quelque part : {'TEN1' in toutes_vues}")
assert "TEN1" not in toutes_vues
# Par numero, pas par index : l'ordre de la liste change des qu'on l'etoffe.
tene = next(o for o in COMMANDES if o["order_id"] == "TEN1")
prefixe = webapp._prefixe_pour_commande(tene)
print(f"   livreur attribue a Tenerife : {prefixe or '(aucun)'}")
assert prefixe == "", f"Tenerife ne doit revenir a personne, or : {prefixe}"

fin()

"""Aucune entrée mal formée ne doit faire planter le serveur (HTTP 500).

Chaque endpoint est appelé avec des valeurs aberrantes dans chaque champ :
texte à la place d'un nombre, null, liste, objet, très longue chaîne. Une
erreur 4xx est une réponse correcte ; un 500 est un bug.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import preparer, simuler_telegram, titre, fin, OWNER

# DATA_DIR isolé : le fuzz du chat écrit chats.json, il ne doit pas atterrir
# dans le projet. LIVREUR_PASSWORD pour pouvoir fuzzer aussi ces routes.
webapp = preparer(ADMIN_PANEL_PASSWORD="", LIVREUR_PASSWORD="",
                  TRADUCTION_REPLI="0",
                  DATA_DIR=tempfile.mkdtemp(prefix="millesime_fuzz_"))
import github_backup
github_backup.backup_file_async = lambda *a, **k: None
github_backup.backup_binaire_async = lambda *a, **k: None
uid = {"v": OWNER}
simuler_telegram(webapp, uid)

import storage

COMMANDE = {"order_id": "R1", "user_id": OWNER, "status": "pending", "total": 50,
            "cart": {"❄️ COCA 1G": 1}, "city": "Paris", "country": "🇫🇷 France",
            "created_at": webapp._now_iso(), "username": "", "user_name": "Test"}
storage._load = lambda: [dict(COMMANDE)]
storage.get_order = lambda oid: dict(COMMANDE) if oid == "R1" else None
storage.update_order = lambda oid, upd: True
storage.save_client_note = getattr(storage, "save_client_note", lambda *a, **k: True)


class Reponse:
    status_code = 200
    text = "{}"

    def json(self):
        return {"ok": True, "result": {"username": "bot"}}


import httpx
httpx.post = lambda *a, **k: Reponse()
httpx.get = lambda *a, **k: Reponse()

app = webapp.app.test_client()

# Valeurs pièges injectées dans chaque champ.
PIEGES = ["abc", None, [1, 2], {"a": 1}, -5, 10 ** 12, 3.7, True, "", "é" * 5000]

# endpoint -> champs attendus (au-delà de initData)
ENDPOINTS = [
    ("/api/auth",                    {"password": "PLATA O PLOMO"}),
    ("/api/admin/unlock",            {"password": "RICH PORTER"}),
    ("/api/admin/lock",              {}),
    ("/api/admin/status",            {}),
    ("/api/admin/orders",            {"limit": 50, "status_filter": "pending"}),
    ("/api/admin/order/R1",          {}),
    ("/api/admin/order/R1/status",   {"status": "confirmed", "eta_minutes": 20}),
    ("/api/admin/clients",           {}),
    ("/api/admin/client_note",       {"user_id": OWNER, "note": "ok"}),
    ("/api/admin/contact",           {"order_id": "R1", "user_id": OWNER}),
    ("/api/admin/send_message",      {"user_id": OWNER, "text": "coucou"}),
    ("/api/admin/selfie/envoyer",    {"order_id": "R1"}),
    ("/api/client/orders",           {"limit": 10}),
    ("/api/order/track",             {"order_id": "R1"}),
    ("/api/notify/city",             {"country": "🇫🇷 France", "city": "Paris"}),
    # Endpoints ajoutés depuis : messagerie, livreur, diagnostic.
    ("/api/chat/thread",             {"client_id": OWNER, "chat_ref": "x"}),
    ("/api/chat/send",               {"client_id": OWNER, "texte": "coucou",
                                      "repond_a": "abc", "duree": 3,
                                      "photo_b64": "", "audio_b64": ""}),
    ("/api/chat/supprimer",          {"client_id": OWNER, "chat_ref": "x",
                                      "message_id": "abc"}),
    ("/api/chat/threads",            {}),
    ("/api/chat/resume",             {}),
    ("/api/livreur/courses",         {}),
    ("/api/livreur/course/R1/status", {"status": "confirmed", "eta_minutes": 10}),
    ("/api/livreur/status",          {}),
    ("/api/livreur/lock",            {}),
    ("/api/diag",                    {"platform": "ios", "version": "9.6",
                                      "len": 3, "has_init": True,
                                      "has_user": False, "href": "x"}),
]

print("=" * 62)

titre(1, "Chaque champ recoit tour a tour une valeur aberrante")
plantages = []
appels = 0
for route, champs in ENDPOINTS:
    for nom in list(champs) or [None]:
        for piege in (PIEGES if nom else [None]):
            corps = {"initData": "x", **champs}
            if nom:
                corps[nom] = piege
            r = app.post(route, json=corps)
            appels += 1
            if r.status_code >= 500:
                plantages.append(f"{route} — {nom}={piege!r} → HTTP {r.status_code}")
print(f"   {appels} appels sur {len(ENDPOINTS)} endpoints")
for p in plantages:
    print(f"   PLANTAGE : {p}")
assert not plantages, f"{len(plantages)} plantage(s)"
print("   aucun HTTP 500")

titre(2, "Corps de requete absent, vide ou illisible")
for contenu in [b"", b"{ casse", b"[]", b"null", b'"texte"', b"\xff\xfe\x00"]:
    r = app.post("/api/admin/orders", data=contenu,
                 content_type="application/json")
    print(f"   {contenu[:12]!r:18s} -> HTTP {r.status_code}")
    assert r.status_code < 500

titre(3, "Un nombre de commandes negatif ne cache pas les plus recentes")
storage._load = lambda: [dict(COMMANDE, order_id=f"N{i}",
                              created_at=f"2026-08-0{i}T10:00:00+02:00")
                         for i in range(1, 6)]
d = app.post("/api/admin/orders", json={"initData": "x", "limit": -5}).get_json()
recus = [o["order_id"] for o in d["orders"]]
print(f"   limit=-5 -> {recus}")
assert recus and recus[0] == "N5", "la plus recente doit rester en tete"
d = app.post("/api/admin/orders", json={"initData": "x", "limit": "abc"}).get_json()
print(f"   limit='abc' -> {len(d['orders'])} commandes (valeur par defaut)")
assert len(d["orders"]) == 5

titre(4, "Un nombre de commandes enorme reste borne")
d = app.post("/api/admin/orders", json={"initData": "x", "limit": 10 ** 12}).get_json()
print(f"   limit=10^12 -> {len(d['orders'])} commandes, pas d'erreur")
assert d["ok"] is not False

titre(5, "Statut de commande inconnu -> refuse, rien n'est ecrit")
ecrits = []
storage.update_order = webapp.update_order = lambda oid, upd: (ecrits.append(upd), True)[1]
for faux in ["livree", "", "DELETE", 42, None]:
    r = app.post("/api/admin/order/R1/status",
                 json={"initData": "x", "status": faux})
    print(f"   status={faux!r:10s} -> HTTP {r.status_code}")
    assert r.status_code == 400
assert ecrits == [], "aucune ecriture ne doit passer"

titre(6, "Chemins d'URL exotiques")
for chemin in ["/api/admin/order/" + "A" * 400,
               "/api/admin/order/../../etc/passwd",
               "/api/admin/photo/R1/exe",
               "/api/admin/photo/R1/selfie/../../"]:
    r = app.post(chemin, json={"initData": "x"}) if "photo" not in chemin \
        else app.get(chemin + "?initData=x")
    print(f"   {chemin[:42]:44s} HTTP {r.status_code}")
    assert r.status_code < 500

fin()

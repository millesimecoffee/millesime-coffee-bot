"""Envoi de vidéos dans la messagerie de la Mini App.

On vérifie qu'une vraie vidéo (en-tête reconnu) part et se stocke comme telle,
qu'elle se sert en octets partiels (HTTP Range, indispensable pour lire/seeker),
et qu'un fichier qui n'est pas une vidéo est refusé.
"""
import base64
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import preparer, simuler_telegram, titre, fin, AUTRE

webapp = preparer(ADMIN_PANEL_PASSWORD="", DATA_DIR=tempfile.mkdtemp(prefix="millesime_vid_"))
uid = {"v": AUTRE}
simuler_telegram(webapp, uid)

import chat
import storage
storage._load = lambda: []

import httpx
httpx.post = lambda url, **kw: type("R", (), {"status_code": 200, "text": "{}",
                                              "json": lambda s: {"ok": True}})()
import github_backup
github_backup.backup_file_async = lambda *a, **k: None
github_backup.backup_binaire_async = lambda *a, **k: None
github_backup.telecharger_binaire = lambda *a, **k: b""

app = webapp.app.test_client()

# Un MP4 minimal : boîte ftyp (marque « mp42 ») suivie d'octets de remplissage.
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 512
MP4_B64 = base64.b64encode(MP4).decode()
JPEG = bytes.fromhex("ffd8ffe000104a464946") + b"\x00" * 64   # pas une vidéo

print("=" * 62)

titre(1, "Une vidéo MP4 est acceptée et stockée comme vidéo")
r = app.post("/api/chat/send", json={"initData": "x", "video_b64": MP4_B64})
d = r.get_json()
assert r.status_code == 200 and d["ok"], d
msg = d["message"]
print(f"   type={msg['type']} · media={msg['media']}")
assert msg["type"] == "video"
assert msg["media"].endswith(".mp4"), msg["media"]
media_id = msg["media"]

titre(2, "Le média se sert avec le bon type MIME")
r = app.get(f"/api/chat/media/{media_id}?initData=x")
print(f"   HTTP {r.status_code} · {r.headers.get('Content-Type')} · Accept-Ranges={r.headers.get('Accept-Ranges')}")
assert r.status_code == 200
assert r.headers.get("Content-Type") == "video/mp4"
assert r.headers.get("Accept-Ranges") == "bytes"

titre(3, "Une requête Range renvoie un contenu partiel (206)")
r = app.get(f"/api/chat/media/{media_id}?initData=x", headers={"Range": "bytes=0-9"})
print(f"   HTTP {r.status_code} · Content-Range={r.headers.get('Content-Range')} · {len(r.data)} octets")
assert r.status_code == 206, r.status_code
assert r.headers.get("Content-Range") == f"bytes 0-9/{len(MP4)}"
assert len(r.data) == 10

titre(4, "Un fichier qui n'est pas une vidéo est refusé")
r = app.post("/api/chat/send", json={"initData": "x",
                                     "video_b64": base64.b64encode(JPEG).decode()})
d = r.get_json()
print(f"   HTTP {r.status_code} · error={d.get('error')}")
assert r.status_code == 400 and d.get("error") == "bad_video", d

titre(5, "L'aperçu du fil montre « Vidéo »")
r = app.post("/api/chat/thread", json={"initData": "x"})
msgs = r.get_json().get("messages", [])
assert any(m.get("type") == "video" for m in msgs), "la vidéo doit être dans le fil"
assert chat.resume({"type": "video"}) == "🎥 Vidéo"
print("   résumé =", chat.resume({"type": "video"}))

fin()

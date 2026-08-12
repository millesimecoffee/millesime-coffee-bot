"""Messagerie privée vendeur ↔ client, à l'intérieur de la Mini App.

Une conversation par client, identifiée par son user_id Telegram.

Le texte et les métadonnées vivent dans `chats.json` ; les photos et les
audios sont écrits dans `chat_media/` **en fichiers séparés**. C'est
délibéré : `orders.json` est déjà à 97 % de selfies en base64, ce qui oblige
à relire et à réexpédier tout le fichier au moindre changement. Ici le JSON
reste léger quel que soit le nombre de photos échangées.

Le disque de Render est éphémère : chaque média est donc aussi poussé dans le
dépôt GitHub de sauvegarde, et retéléchargé à la demande s'il a disparu.
"""
import base64
import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

import github_backup as _gh
from storage import _ecrire_json_atomique

logger = logging.getLogger(__name__)

_DATA_DIR = Path(os.getenv("DATA_DIR", str(Path(__file__).parent)))
_FICHIER = _DATA_DIR / "chats.json"
_MEDIA_DIR = _DATA_DIR / "chat_media"
_lock = threading.RLock()

# Un message texte plus long qu'un SMS long n'a pas sa place dans une bulle.
MAX_TEXTE = 2000
# Une photo compressée pèse ~60 Ko, un audio d'une minute ~60 Ko aussi.
MAX_MEDIA = 3 * 1024 * 1024
MAX_DUREE_AUDIO = 180          # secondes
# Au-delà, on ne garde que les plus récents : une conversation ne doit pas
# grossir indéfiniment dans un fichier relu à chaque ouverture.
MAX_MESSAGES = 500

VENDEUR = "vendeur"
CLIENT = "client"

_cache: dict = {"data": None, "sig": None}


def _maintenant() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


# ── Lecture / écriture ───────────────────────────────────────────────────────

def _lire() -> dict:
    """Contenu de chats.json, avec cache invalidé sur la date de modification."""
    with _lock:
        try:
            st = _FICHIER.stat()
        except OSError:
            return {}
        sig = (st.st_mtime_ns, st.st_size)
        if _cache["sig"] == sig and _cache["data"] is not None:
            return _cache["data"]
        try:
            with _FICHIER.open(encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Lecture chats.json : %s", exc)
            return _cache["data"] or {}
        if not isinstance(data, dict):
            return {}
        _cache.update(data=data, sig=sig)
        return data


def _ecrire(data: dict) -> None:
    with _lock:
        _ecrire_json_atomique(_FICHIER, data)
        _cache.update(data=data, sig=None)
    _gh.backup_file_async("chats.json")


def _fil(data: dict, client_id) -> dict:
    """Le fil d'un client, créé au besoin."""
    cle = str(client_id)
    fil = data.get(cle)
    if not isinstance(fil, dict):
        fil = {"messages": [], "lu_vendeur": "", "lu_client": "", "profil": {}}
        data[cle] = fil
    fil.setdefault("messages", [])
    fil.setdefault("lu_vendeur", "")
    fil.setdefault("lu_client", "")
    fil.setdefault("profil", {})
    return fil


# ── Médias ───────────────────────────────────────────────────────────────────

def _chemin_media(media_id: str) -> Path:
    return _MEDIA_DIR / media_id


def _nom_media(kind: str) -> str:
    ext = "jpg" if kind == "photo" else "ogg"
    return f"{uuid.uuid4().hex}.{ext}"


def ecrire_media(donnees: bytes, kind: str) -> str:
    """Enregistre un média et renvoie son identifiant. "" si refusé."""
    if not donnees or len(donnees) > MAX_MEDIA:
        return ""
    media_id = _nom_media(kind)
    try:
        _MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _chemin_media(media_id + ".tmp")
        with tmp.open("wb") as f:
            f.write(donnees)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, _chemin_media(media_id))
    except OSError as exc:
        logger.error("Écriture média %s : %s", media_id, exc)
        return ""
    _gh.backup_binaire_async(f"chat_media/{media_id}", donnees)
    return media_id


def lire_media(media_id: str) -> bytes:
    """Contenu d'un média. Le retélécharge depuis GitHub s'il a disparu du
    disque — ce qui arrive à chaque redéploiement sur Render."""
    if not media_id or "/" in media_id or "\\" in media_id or media_id.startswith("."):
        return b""
    chemin = _chemin_media(media_id)
    try:
        return chemin.read_bytes()
    except OSError:
        pass
    donnees = _gh.telecharger_binaire(f"chat_media/{media_id}")
    if donnees:
        try:
            _MEDIA_DIR.mkdir(parents=True, exist_ok=True)
            chemin.write_bytes(donnees)
        except OSError:
            pass
    return donnees


def type_mime(media_id: str) -> str:
    return "image/jpeg" if media_id.endswith(".jpg") else "audio/ogg"


# ── API ──────────────────────────────────────────────────────────────────────

def ajouter(client_id, de: str, texte: str = "", media_id: str = "",
            kind: str = "texte", duree: float = 0.0, profil: dict | None = None) -> dict:
    """Ajoute un message au fil de `client_id` et le renvoie."""
    if de not in (VENDEUR, CLIENT):
        raise ValueError("expéditeur inconnu")
    texte = (texte or "")[:MAX_TEXTE]
    if not texte and not media_id:
        raise ValueError("message vide")

    msg = {
        "id": uuid.uuid4().hex[:12],
        "de": de,
        "type": kind,
        "texte": texte,
        "at": _maintenant(),
        # `at` est à la seconde, ce qui suffit pour l'affichage mais pas pour
        # ordonner : deux messages de la même seconde seraient à égalité.
        "ts": round(time.time(), 3),
    }
    if media_id:
        msg["media"] = media_id
    if kind == "audio" and duree:
        msg["duree"] = round(min(float(duree), MAX_DUREE_AUDIO), 1)

    with _lock:
        data = _lire()
        fil = _fil(data, client_id)
        fil["messages"].append(msg)
        if len(fil["messages"]) > MAX_MESSAGES:
            fil["messages"] = fil["messages"][-MAX_MESSAGES:]
        if profil:
            fil["profil"].update({k: v for k, v in profil.items() if v})
        # Un message qu'on envoie soi-même est lu par définition.
        fil["lu_vendeur" if de == VENDEUR else "lu_client"] = msg["id"]
        _ecrire(data)
    return msg


def messages(client_id) -> list:
    return list(_fil(_lire(), client_id).get("messages", []))


def profil(client_id) -> dict:
    return dict(_fil(_lire(), client_id).get("profil", {}))


def contient(media_id: str, client_id) -> bool:
    """True si ce média appartient bien au fil de ce client. Sans ce contrôle,
    connaître un identifiant suffirait à lire la photo de n'importe qui."""
    return any(m.get("media") == media_id for m in messages(client_id))


def marquer_lu(client_id, par: str) -> None:
    with _lock:
        data = _lire()
        fil = _fil(data, client_id)
        cle = "lu_vendeur" if par == VENDEUR else "lu_client"
        dernier = fil["messages"][-1]["id"] if fil["messages"] else ""
        if fil.get(cle) != dernier:
            fil[cle] = dernier
            _ecrire(data)


def _apres_lecture(fil: dict, pour: str) -> list:
    """Messages arrivés après le dernier que `pour` a vu.

    On repère la lecture par identifiant de message et non par horodatage :
    celui-ci est à la seconde, donc deux messages de la même seconde se
    comparaient comme égaux et le compteur de non-lus retombait à zéro.
    """
    msgs = fil.get("messages") or []
    vu = fil.get("lu_vendeur" if pour == VENDEUR else "lu_client") or ""
    if not vu:
        return list(msgs)
    for i in range(len(msgs) - 1, -1, -1):
        if msgs[i].get("id") == vu:
            return msgs[i + 1:]
    return list(msgs)      # repère perdu (message trop ancien, purgé)


def non_lus(client_id, pour: str) -> int:
    """Nombre de messages reçus depuis la dernière lecture."""
    fil = _fil(_lire(), client_id)
    autre = CLIENT if pour == VENDEUR else VENDEUR
    return sum(1 for m in _apres_lecture(fil, pour) if m.get("de") == autre)


def fils(pour: str = VENDEUR) -> list:
    """Toutes les conversations, la plus récemment active en premier."""
    data = _lire()
    sortie = []
    for cle, fil in data.items():
        msgs = fil.get("messages") or []
        if not msgs:
            continue
        dernier = msgs[-1]
        sortie.append({
            "client_id": cle,
            "profil": fil.get("profil") or {},
            "dernier": {
                "de": dernier.get("de"),
                "type": dernier.get("type", "texte"),
                "texte": dernier.get("texte", ""),
                "at": dernier.get("at", ""),
            },
            "non_lus": non_lus(cle, pour),
            "total": len(msgs),
            "_ordre": dernier.get("ts") or 0,
        })
    # `ts` d'abord (précis à la milliseconde), `at` en secours pour les
    # messages écrits avant l'ajout de ce champ.
    sortie.sort(key=lambda f: (f["_ordre"], f["dernier"]["at"]), reverse=True)
    for f in sortie:
        f.pop("_ordre", None)
    return sortie


def total_non_lus(pour: str = VENDEUR) -> int:
    return sum(f["non_lus"] for f in fils(pour))


# ── Anti-spam de notification ────────────────────────────────────────────────

_dernier_signal: dict[str, float] = {}
_DELAI_SIGNAL = 60.0


def doit_signaler(client_id, de: str) -> bool:
    """True s'il faut prévenir le destinataire. Une rafale de messages ne
    déclenche qu'une seule notification par minute."""
    cle = f"{client_id}:{de}"
    maintenant = time.time()
    with _lock:
        if maintenant - _dernier_signal.get(cle, 0) < _DELAI_SIGNAL:
            return False
        _dernier_signal[cle] = maintenant
        if len(_dernier_signal) > 500:
            for k in [k for k, t in _dernier_signal.items()
                      if maintenant - t > _DELAI_SIGNAL]:
                del _dernier_signal[k]
    return True


def resume(msg: dict) -> str:
    """Aperçu court d'un message, pour une notification."""
    kind = msg.get("type", "texte")
    if kind == "photo":
        return "📷 Photo"
    if kind == "audio":
        d = msg.get("duree") or 0
        return f"🎤 Message vocal ({int(d)} s)" if d else "🎤 Message vocal"
    texte = (msg.get("texte") or "").strip()
    return texte[:200] + ("…" if len(texte) > 200 else "")


def decoder_b64(b64: str) -> bytes:
    """Décode un média envoyé par la Mini App (avec ou sans préfixe data:)."""
    if not isinstance(b64, str) or not b64:
        return b""
    if "," in b64[:64]:
        b64 = b64.split(",", 1)[1]
    b64 = "".join(b64.split())
    manque = len(b64) % 4
    if manque:
        b64 += "=" * (4 - manque)
    try:
        return base64.b64decode(b64, validate=False)
    except Exception:
        return b""

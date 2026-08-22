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
import datetime as _dt
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
# Une vidéo n'est pas recompressée côté serveur (pas de ffmpeg) : on l'accepte
# telle quelle, avec un plafond plus large mais qui reste raisonnable pour un
# clip envoyé dans une conversation.
MAX_VIDEO = 20 * 1024 * 1024
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


def _vide() -> dict:
    return {"messages": [], "lu_vendeur": "", "lu_client": "", "profil": {}}


def _fil(data: dict, client_id, creer: bool = False) -> dict:
    """Le fil d'un client.

    `creer=False` renvoie un fil détaché sans rien ajouter au dictionnaire :
    sinon la simple ouverture de l'écran par un visiteur inscrirait un fil
    vide, que la première écriture venue graverait dans chats.json.
    """
    cle = str(client_id)
    fil = data.get(cle)
    if not isinstance(fil, dict):
        if not creer:
            return _vide()
        fil = _vide()
        data[cle] = fil
    fil.setdefault("messages", [])
    fil.setdefault("lu_vendeur", "")
    fil.setdefault("lu_client", "")
    fil.setdefault("profil", {})
    return fil


# ── Médias ───────────────────────────────────────────────────────────────────

def _chemin_media(media_id: str) -> Path:
    return _MEDIA_DIR / media_id


def _nom_media(kind: str, ext: str = "") -> str:
    if not ext:
        ext = "jpg" if kind == "photo" else "mp4" if kind == "video" else "ogg"
    return f"{uuid.uuid4().hex}.{ext}"


def detecter_video(donnees: bytes) -> str:
    """Extension si `donnees` est bien une vidéo reconnue, "" sinon.

    On vérifie les octets d'en-tête plutôt que de se fier au type déclaré par le
    client : un fichier renommé ne doit pas passer pour une vidéo."""
    if not donnees or len(donnees) < 12:
        return ""
    if donnees[4:8] == b"ftyp":                     # conteneur ISO (MP4 / MOV)
        return "mov" if donnees[8:10] == b"qt" else "mp4"
    if donnees[:4] == b"\x1a\x45\xdf\xa3":          # Matroska / WebM
        return "webm"
    return ""


def ecrire_media(donnees: bytes, kind: str, ext: str = "") -> str:
    """Enregistre un média et renvoie son identifiant. "" si refusé."""
    limite = MAX_VIDEO if kind == "video" else MAX_MEDIA
    if not donnees or len(donnees) > limite:
        return ""
    media_id = _nom_media(kind, ext)
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


def effacer_media(media_id: str) -> None:
    """Efface un média du disque et de la sauvegarde."""
    if not media_id or "/" in media_id or "\\" in media_id or media_id.startswith("."):
        return
    try:
        _chemin_media(media_id).unlink()
    except OSError:
        pass                                # déjà parti : c'est le but
    _gh.supprimer_binaire_async(f"chat_media/{media_id}")


def type_mime(media_id: str) -> str:
    if media_id.endswith(".jpg"):
        return "image/jpeg"
    if media_id.endswith(".mp4"):
        return "video/mp4"
    if media_id.endswith(".webm"):
        return "video/webm"
    if media_id.endswith(".mov"):
        return "video/quicktime"
    return "audio/ogg"


# ── API ──────────────────────────────────────────────────────────────────────

def apercu_reponse(fil: dict, msg_id: str) -> dict:
    """Extrait de quoi citer un message auquel on répond.

    On fige un aperçu au moment de la réponse plutôt que de renvoyer vers
    l'original : celui-ci peut sortir du fil quand la conversation dépasse le
    plafond, et la citation deviendrait vide.
    """
    for m in fil.get("messages") or []:
        if m.get("id") == msg_id:
            if m.get("supprime"):
                return {}                   # rien à citer d'un message effacé
            kind = m.get("type", "texte")
            apercu = ("📷 Photo" if kind == "photo"
                      else "🎥 Vidéo" if kind == "video"
                      else "📍 Position" if kind == "location"
                      else "🎤 Message vocal" if kind == "audio"
                      else (m.get("texte") or "")[:90])
            return {"id": msg_id, "de": m.get("de"), "type": kind, "apercu": apercu}
    return {}


def ajouter(client_id, de: str, texte: str = "", media_id: str = "",
            kind: str = "texte", duree: float = 0.0, profil: dict | None = None,
            lang: str = "", trad: dict | None = None, repond_a: str = "",
            lat=None, lon=None) -> dict:
    """Ajoute un message au fil de `client_id` et le renvoie."""
    if de not in (VENDEUR, CLIENT):
        raise ValueError("expéditeur inconnu")
    texte = (texte or "")[:MAX_TEXTE]
    if kind == "location":
        if lat is None or lon is None:
            raise ValueError("position vide")
    elif not texte and not media_id:
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
    if kind == "location":
        msg["lat"] = round(float(lat), 6)
        msg["lon"] = round(float(lon), 6)
    if kind == "audio" and duree:
        msg["duree"] = round(min(float(duree), MAX_DUREE_AUDIO), 1)
    if lang:
        msg["lang"] = lang
    if trad:
        # {langue: texte} — chacun lit dans la sienne, l'original reste
        # consultable d'une pression.
        msg["trad"] = {k: v for k, v in trad.items() if v}

    with _lock:
        data = _lire()
        fil = _fil(data, client_id, creer=True)
        if repond_a:
            citation = apercu_reponse(fil, repond_a)
            if citation:
                msg["rep"] = citation
        fil["messages"].append(msg)
        tombes = []
        if len(fil["messages"]) > MAX_MESSAGES:
            # Les messages qui sortent du fil emportent leurs fichiers. Sans
            # ça, photos et vocaux restaient sur le disque et dans la
            # sauvegarde alors que plus rien ne pointait dessus : une
            # conversation active y laissait des centaines de méga-octets à
            # l'année, que personne ne pouvait plus ni voir ni effacer.
            trop = fil["messages"][:-MAX_MESSAGES]
            tombes = [m.get("media") for m in trop if m.get("media")]
            fil["messages"] = fil["messages"][-MAX_MESSAGES:]
        if profil:
            fil["profil"].update({k: v for k, v in profil.items() if v})
        # Un message qu'on envoie soi-même est lu par définition.
        fil["lu_vendeur" if de == VENDEUR else "lu_client"] = msg["id"]
        _ecrire(data)
    # Hors du verrou : effacer un fichier n'a pas à retenir les autres envois.
    for media_id in tombes:
        effacer_media(media_id)
    return msg


class Interdit(Exception):
    """Suppression d'un message dont on n'est pas l'auteur."""


def supprimer(client_id, message_id: str, par: str) -> dict:
    """Efface un message pour les deux côtés de la conversation.

    On laisse une trace (« Ce message a été supprimé ») plutôt que de retirer
    la ligne : l'autre l'a peut-être déjà lu, et une conversation où un message
    s'évapore sans laisser de trace se relit mal. Le contenu, lui, disparaît
    vraiment — texte, traductions, et le média jusque dans la sauvegarde.

    Renvoie le message devenu vide, ou {} s'il n'existe pas.
    """
    message_id = str(message_id or "")
    if not message_id:
        return {}
    a_effacer = ""
    with _lock:
        data = _lire()
        if str(client_id) not in data:
            return {}
        fil = _fil(data, client_id)
        cible = None
        for m in fil.get("messages") or []:
            if m.get("id") == message_id:
                cible = m
                break
        if cible is None:
            return {}
        if cible.get("supprime"):
            return dict(cible)              # déjà fait, on ne re-signale rien
        if cible.get("de") != par:
            raise Interdit(message_id)

        a_effacer = cible.get("media") or ""
        garde = {c: cible.get(c) for c in ("id", "de", "at", "ts")}
        cible.clear()
        cible.update(garde)
        cible["type"] = "texte"
        cible["texte"] = ""
        cible["supprime"] = True

        # Les citations figent un extrait au moment de la réponse : sans ce
        # nettoyage, le texte supprimé resterait lisible dans les réponses.
        for m in fil.get("messages") or []:
            rep = m.get("rep")
            if isinstance(rep, dict) and rep.get("id") == message_id:
                rep["apercu"] = ""
                rep["supprime"] = True
        _ecrire(data)

    if a_effacer:
        effacer_media(a_effacer)
    return dict(cible)


def messages(client_id) -> list:
    return list(_fil(_lire(), client_id).get("messages", []))


def messages_depuis(client_id, depuis_iso: str) -> list:
    """Messages postérieurs à une date ISO. Tout le fil si la date est vide.

    Sert à borner ce qu'un livreur voit : un fil appartient à un client, pas à
    une commande, et il en garde jusqu'à 500 messages. Sans cette borne, le
    livreur d'une course du jour lisait tout ce que le client avait pu écrire
    à la boutique depuis toujours.
    """
    tous = messages(client_id)
    if not depuis_iso:
        return tous
    try:
        seuil = _dt.datetime.fromisoformat(str(depuis_iso).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return tous
    if seuil.tzinfo is None:
        seuil = seuil.astimezone()
    gardes = []
    for m in tous:
        try:
            quand = _dt.datetime.fromisoformat(str(m.get("at", "")).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            gardes.append(m)          # date illisible : on ne cache rien par erreur
            continue
        if quand.tzinfo is None:
            quand = quand.astimezone()
        if quand >= seuil:
            gardes.append(m)
    return gardes


def langue_ecrite(client_id) -> str:
    """Langue des messages que le client a réellement écrits.

    Sert quand il n'a encore aucune commande : sans elle, un client qui écrit
    en français avant de commander recevrait les réponses en anglais, la
    langue par défaut.
    """
    for m in reversed(messages(client_id)):
        if m.get("de") == CLIENT and m.get("lang"):
            return m["lang"]
    return ""


def lu_par(client_id, qui: str) -> str:
    """Identifiant du dernier message que `qui` a lu.

    Sert aux accusés de lecture : l'expéditeur voit d'un coup d'œil jusqu'où
    l'autre est arrivé.
    """
    fil = _fil(_lire(), client_id)
    return fil.get("lu_vendeur" if qui == VENDEUR else "lu_client") or ""


def profil(client_id) -> dict:
    return dict(_fil(_lire(), client_id).get("profil", {}))


def contient(media_id: str, client_id) -> bool:
    """True si ce média appartient bien au fil de ce client. Sans ce contrôle,
    connaître un identifiant suffirait à lire la photo de n'importe qui."""
    return any(m.get("media") == media_id for m in messages(client_id))


def marquer_lu(client_id, par: str) -> None:
    with _lock:
        data = _lire()
        if str(client_id) not in data:
            return                      # rien à marquer, rien à créer
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
                "supprime": bool(dernier.get("supprime")),
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
    if kind == "video":
        return "🎥 Vidéo"
    if kind == "location":
        return "📍 Position"
    if kind == "audio":
        d = msg.get("duree") or 0
        return f"🎤 Message vocal ({int(d)} s)" if d else "🎤 Message vocal"
    texte = (msg.get("texte") or "").strip()
    return texte[:200] + ("…" if len(texte) > 200 else "")


# ── Filtre anti-détournement ────────────────────────────────────────────────
# Dans une conversation où intervient un livreur, on empêche l'échange de
# coordonnées : c'est ce qui permettrait de traiter la commande suivante en
# dehors de la boutique. Le filtre vise les moyens de recontact, pas les
# chiffres en général — un code de porte, un numéro de rue ou un étage doivent
# passer sans encombre.

import re as _re

# 9 chiffres ou plus d'affilée, tolérant les séparateurs habituels d'un numéro.
# Un code d'immeuble (4 à 6 chiffres) ou un numéro de rue restent en dessous.
_MOTIF_TEL = _re.compile(r"(?:\+|00)?\s*(?:\d[\s.\-/()]{0,2}){9,}")
# @pseudo, t.me/…, et les messageries qui serviraient de porte de sortie.
_MOTIF_PSEUDO = _re.compile(r"@[A-Za-z][A-Za-z0-9_]{3,}")
_MOTIF_LIEN = _re.compile(
    r"(?:t\.me/|telegram\.me/|telegram\s*:|wa\.me/|whatsapp|signal\.me/|"
    r"instagram\.com/|snapchat)", _re.IGNORECASE)
# Caractères invisibles glissés entre les chiffres pour passer sous le radar.
_INVISIBLES = _re.compile(r"[​-‏⁠﻿]")


def contient_contact(texte: str) -> str:
    """Motif de refus si le texte transmet un moyen de recontact, sinon "".

    Renvoie « telephone », « pseudo » ou « lien » — de quoi expliquer
    précisément à l'expéditeur ce qui bloque.
    """
    if not texte:
        return ""
    t = _INVISIBLES.sub("", texte)
    if _MOTIF_LIEN.search(t):
        return "lien"
    if _MOTIF_PSEUDO.search(t):
        return "pseudo"
    for bloc in _MOTIF_TEL.finditer(t):
        if sum(c.isdigit() for c in bloc.group()) >= 9:
            return "telephone"
    return ""


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

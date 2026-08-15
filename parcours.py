"""Journal des passages sur le catalogue : qui regarde, quel pays, quelle ville.

Ces informations transitaient déjà — elles servaient à prévenir l'owner par
Telegram et Pushover — mais elles repartaient aussitôt. Rien n'en gardait la
trace, donc rien ne permettait de les consulter après coup.

Le journal est délibérément pauvre : une personne, un pays, une ville, une
date. Pas d'adresse, pas de panier, pas de coordonnées. C'est tout ce que
l'écran de veille montre, et donc tout ce qu'on enregistre.

Il est borné des deux côtés — nombre de lignes ET ancienneté — parce qu'un
fichier réécrit et renvoyé au dépôt à chaque visite doit rester petit quoi
qu'il arrive.
"""
import json
import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import github_backup as _gh
from storage import _ecrire_json_atomique

logger = logging.getLogger(__name__)

_DATA_DIR = Path(os.getenv("DATA_DIR", str(Path(__file__).parent)))
_FICHIER = _DATA_DIR / "parcours.json"
_lock = threading.RLock()

# Au-delà, on ne garde que les plus récents. 800 passages couvrent largement
# ce qu'un écran de veille montre, et le fichier reste sous ~150 Ko.
MAX_PASSAGES = 800
# Un passage plus vieux que ça n'apprend plus rien sur l'activité du jour.
RETENTION_JOURS = 30
# Un même visiteur sur le même pays/ville dans cette fenêtre ne crée qu'une
# ligne : sans ça, les allers-retours entre écrans en produiraient dix.
REGROUPEMENT_SECONDES = 300

_cache: dict = {"data": None, "sig": None}


def _maintenant() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _lire() -> list:
    """Contenu du journal, avec cache invalidé sur la date de modification."""
    with _lock:
        try:
            st = _FICHIER.stat()
        except OSError:
            return []
        sig = (st.st_mtime_ns, st.st_size)
        if _cache["sig"] == sig and _cache["data"] is not None:
            return _cache["data"]
        try:
            with _FICHIER.open(encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Lecture parcours.json : %s", exc)
            return _cache["data"] or []
        if not isinstance(data, list):
            return []
        _cache.update(data=data, sig=sig)
        return data


def _ecrire(data: list) -> None:
    with _lock:
        _ecrire_json_atomique(_FICHIER, data)
        _cache.update(data=data, sig=None)
    _gh.backup_file_async("parcours.json")


def _date(iso: str):
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return d if d.tzinfo else d.astimezone()


def _elaguer(data: list) -> list:
    """Retire ce qui est trop vieux, puis ce qui dépasse le plafond."""
    limite = datetime.now(timezone.utc) - timedelta(days=RETENTION_JOURS)
    gardes = []
    for p in data:
        d = _date(p.get("at"))
        if d is None or d >= limite:
            gardes.append(p)
    return gardes[-MAX_PASSAGES:]


def noter(uid, prenom: str, pays: str, ville: str = "") -> dict | None:
    """Enregistre un passage. Renvoie la ligne écrite, ou None si regroupée
    avec la précédente."""
    if not uid or not pays:
        return None
    ligne = {
        "uid": str(uid),
        "prenom": (prenom or "").strip()[:40],
        "pays": pays,
        "ville": ville or "",
        "at": _maintenant(),
    }
    with _lock:
        data = list(_lire())
        # Même personne, même destination, il y a moins de cinq minutes : on
        # rafraîchit la ligne au lieu d'en ajouter une.
        maintenant = _date(ligne["at"])
        for p in reversed(data[-40:]):
            if (p.get("uid") == ligne["uid"] and p.get("pays") == pays
                    and (p.get("ville") or "") == (ville or "")):
                d = _date(p.get("at"))
                if d and maintenant and \
                        (maintenant - d).total_seconds() < REGROUPEMENT_SECONDES:
                    p["at"] = ligne["at"]
                    if ligne["prenom"]:
                        p["prenom"] = ligne["prenom"]
                    _ecrire(_elaguer(data))
                    return None
                break
        data.append(ligne)
        _ecrire(_elaguer(data))
    return ligne


def passages(limite: int = 200) -> list:
    """Les passages, du plus récent au plus ancien."""
    return list(reversed(_lire()))[:max(1, min(int(limite or 200), MAX_PASSAGES))]


def resume() -> dict:
    """Quelques totaux, pour l'en-tête de l'écran de veille."""
    data = _lire()
    aujourd_hui = datetime.now().astimezone().date()
    du_jour = [p for p in data
               if (_date(p.get("at")) or datetime.now().astimezone()).date() == aujourd_hui]
    return {
        "total": len(data),
        "aujourd_hui": len(du_jour),
        "personnes": len({p.get("uid") for p in data}),
        "personnes_aujourd_hui": len({p.get("uid") for p in du_jour}),
    }

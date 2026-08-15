"""Journal d'activité : qui regarde quoi, et où l'on commande.

Ces informations transitaient déjà — elles servaient à prévenir l'owner par
Telegram et Pushover — mais elles repartaient aussitôt. Rien n'en gardait la
trace, donc rien ne permettait de les consulter après coup.

Le journal est délibérément pauvre. Deux sortes de lignes :

  vue       quelqu'un regarde le catalogue      → personne, pays, ville
  commande  une commande franchit une étape     → personne, pays, ville, étape

Il n'y a NI montant, NI contenu de panier, NI adresse, NI photo, NI numéro de
téléphone : l'écran de veille montre où ça se passe et quand, jamais combien
ni quoi. Un test le vérifie sur le contenu brut du fichier.

Bornage des deux côtés — nombre de lignes ET ancienneté — parce qu'un fichier
réécrit et renvoyé au dépôt à chaque visite doit rester petit.
"""
import json
import logging
import os
import threading
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import github_backup as _gh
from storage import _ecrire_json_atomique

logger = logging.getLogger(__name__)

_DATA_DIR = Path(os.getenv("DATA_DIR", str(Path(__file__).parent)))
_FICHIER = _DATA_DIR / "parcours.json"
_lock = threading.RLock()

MAX_PASSAGES = 1500
RETENTION_JOURS = 60
# Un même visiteur sur le même pays/ville dans cette fenêtre ne crée qu'une
# ligne de vue : sans ça, les allers-retours entre écrans en produiraient dix.
REGROUPEMENT_SECONDES = 300

# Les étapes d'une commande, dans l'ordre. Ce sont les seules qu'on journalise.
ETAPES = {
    "pending":   "lancée",
    "confirmed": "confirmée",
    "delivering": "en route",
    "delivered": "livrée",
    "cancelled": "annulée",
    "cancelled_by_client": "annulée",
}

_cache: dict = {"data": None, "sig": None}


def _maintenant() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _lire() -> list:
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
    limite = datetime.now(timezone.utc) - timedelta(days=RETENTION_JOURS)
    gardes = [p for p in data
              if (_date(p.get("at")) or datetime.now(timezone.utc)) >= limite]
    return gardes[-MAX_PASSAGES:]


def _ajouter(ligne: dict) -> dict:
    with _lock:
        data = list(_lire())
        data.append(ligne)
        _ecrire(_elaguer(data))
    return ligne


def noter(uid, prenom: str, pays: str, ville: str = "") -> dict | None:
    """Quelqu'un regarde le catalogue. Renvoie la ligne, ou None si regroupée
    avec une consultation toute récente de la même destination."""
    if not uid or not pays:
        return None
    ligne = {"type": "vue", "uid": str(uid), "prenom": (prenom or "").strip()[:40],
             "pays": pays, "ville": ville or "", "at": _maintenant()}
    with _lock:
        data = list(_lire())
        maintenant = _date(ligne["at"])
        for p in reversed(data[-60:]):
            if (p.get("type", "vue") == "vue" and p.get("uid") == ligne["uid"]
                    and p.get("pays") == pays and (p.get("ville") or "") == (ville or "")):
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


def noter_commande(order_id, uid, prenom: str, pays: str, ville: str,
                   statut: str) -> dict | None:
    """Une commande franchit une étape.

    On enregistre l'étape et l'endroit, jamais le montant ni le panier :
    l'écran de veille doit montrer que ça bouge, pas ce qui se vend.
    """
    etape = ETAPES.get(statut or "pending")
    if not etape or not pays:
        return None
    return _ajouter({
        "type": "commande",
        "uid": str(uid or ""),
        "prenom": (prenom or "").strip()[:40],
        "pays": pays,
        "ville": ville or "",
        "etape": etape,
        "ref": str(order_id or "")[-4:],   # 4 derniers chiffres : de quoi suivre
        "at": _maintenant(),               # une commande sans l'identifier ailleurs
    })


def passages(limite: int = 200) -> list:
    """Le flux d'activité, du plus récent au plus ancien."""
    return list(reversed(_lire()))[:max(1, min(int(limite or 200), MAX_PASSAGES))]


def _depuis(data: list, jours: int) -> list:
    if not jours:
        return data
    limite = datetime.now(timezone.utc) - timedelta(days=jours)
    return [p for p in data if (_date(p.get("at")) or datetime.now(timezone.utc)) >= limite]


def classements(jours: int = 30) -> dict:
    """Les villes où ça regarde le plus, et celles où ça commande le plus."""
    data = _depuis(_lire(), jours)
    vues, commandes, pays_vues = Counter(), Counter(), Counter()
    for p in data:
        lieu = f"{p.get('pays', '')}|{p.get('ville') or '—'}"
        if p.get("type", "vue") == "vue":
            vues[lieu] += 1
            pays_vues[p.get("pays", "")] += 1
        elif p.get("etape") == "lancée":
            commandes[lieu] += 1

    def _mettre_en_forme(compteur):
        total = sum(compteur.values()) or 1
        return [{"pays": c.split("|", 1)[0], "ville": c.split("|", 1)[1],
                 "n": n, "part": round(n * 100 / total)}
                for c, n in compteur.most_common(8)]

    return {
        "villes_vues": _mettre_en_forme(vues),
        "villes_commandes": _mettre_en_forme(commandes),
        "pays": [{"pays": p, "n": n} for p, n in pays_vues.most_common(6)],
    }


def entonnoir(jours: int = 30) -> dict:
    """Combien de regards, combien de commandes, combien arrivées à bon port."""
    data = _depuis(_lire(), jours)
    etapes = Counter(p.get("etape") for p in data if p.get("type") == "commande")
    return {
        "vues": sum(1 for p in data if p.get("type", "vue") == "vue"),
        "lancees": etapes.get("lancée", 0),
        "confirmees": etapes.get("confirmée", 0),
        "en_route": etapes.get("en route", 0),
        "livrees": etapes.get("livrée", 0),
        "annulees": etapes.get("annulée", 0),
    }


def resume() -> dict:
    data = _lire()
    aujourd_hui = datetime.now().astimezone().date()
    du_jour = [p for p in data
               if (_date(p.get("at")) or datetime.now().astimezone()).date() == aujourd_hui]
    return {
        "total": len(data),
        "aujourd_hui": len(du_jour),
        "personnes": len({p.get("uid") for p in data if p.get("uid")}),
        "personnes_aujourd_hui": len({p.get("uid") for p in du_jour if p.get("uid")}),
        "commandes_aujourd_hui": sum(1 for p in du_jour
                                     if p.get("type") == "commande" and p.get("etape") == "lancée"),
    }

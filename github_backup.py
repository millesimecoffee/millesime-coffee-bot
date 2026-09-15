"""
Sauvegarde automatique des fichiers de données vers un repo GitHub privé.

Permet une persistence "free" sur Render free tier (filesystem éphémère) :
- Au démarrage : restaure orders.json / blacklist.json / blocked.json depuis GitHub
- À chaque écriture : upload en arrière-plan vers GitHub (best-effort)
- Job périodique : sauvegarde toutes les 10 min en filet de sécurité

Requiert l'env var GITHUB_TOKEN (PAT avec scope `repo` ou OAuth gh CLI).
"""
import base64
import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_TOKEN  = os.getenv("GITHUB_TOKEN", "")
_OWNER  = os.getenv("GITHUB_DATA_OWNER", "millesimecoffee")
_REPO   = os.getenv("GITHUB_DATA_REPO",  "coffee-bot-data")
_BRANCH = os.getenv("GITHUB_DATA_BRANCH", "main")
_API    = "https://api.github.com"

_DATA_DIR  = Path(os.getenv("DATA_DIR", str(Path(__file__).parent)))
_FILES = ["orders.json", "blacklist.json", "blocked.json", "chats.json",
          "livreurs.json", "parcours.json", "veilleurs.json", "catalogue.json",
          "sumup_consomme.json"]

_sha_cache: dict[str, str] = {}
_lock = threading.Lock()

# Un seul verrou pour TOUTES les écritures du dépôt.
#
# Un verrou par fichier ne suffit pas : chaque écriture crée un commit sur la
# même branche, et deux commits simultanés — même sur des chemins différents —
# se soldent par un 409 côté GitHub. C'est ce qui faisait échouer l'envoi des
# photos et des vocaux, expédiés en même temps que chats.json.
_upload_locks: dict[str, threading.Lock] = {}
_lock_branche = threading.Lock()


def _get_upload_lock(filename: str) -> threading.Lock:
    return _lock_branche


def is_enabled() -> bool:
    return bool(_TOKEN)


def _headers() -> dict:
    return {
        "Authorization":        f"Bearer {_TOKEN}",
        "Accept":               "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _file_url(path: str) -> str:
    return f"{_API}/repos/{_OWNER}/{_REPO}/contents/{path}"


# Empreinte du contenu réellement envoyé, par fichier. Sert à ne pas
# renvoyer ce qui n'a pas bougé : un travail périodique repoussait les six
# fichiers toutes les dix minutes, y compris ceux de deux octets, soit environ
# 800 commits par jour dont l'immense majorité ne changeait rien. Chaque commit
# garde une copie entière du fichier : à ce rythme, l'historique du dépôt de
# sauvegarde devenait ingérable en quelques mois.
_empreintes: dict[str, str] = {}

# Fichiers dont la restauration au démarrage a ÉCHOUÉ transitoirement (réseau,
# 5xx, timeout) — par opposition à un 404 franc « le fichier n'existe pas encore
# sur le dépôt ». Tant qu'un fichier est ici, on REFUSE de l'envoyer : le local
# a probablement été reconstruit à vide (Render efface le disque au démarrage),
# et l'écraser sur le dépôt détruirait la seule copie survivante. On ne lève le
# blocage qu'après une restauration réussie (« ok ») ou un 404 confirmé.
_restore_incomplet: set[str] = set()


def _empreinte(donnees: bytes) -> str:
    return hashlib.sha256(donnees).hexdigest()


def restauration_incomplete(filename: str) -> bool:
    """True si la dernière restauration de ce fichier a échoué transitoirement
    (donc le dépôt contient peut-être des données qu'on n'a pas pu récupérer).
    storage.py s'en sert pour ne PAS repartir d'une liste vide et écraser la
    sauvegarde. Vaut False si le backup est désactivé (pas de source distante)."""
    if not _TOKEN:
        return False
    with _lock:
        return filename in _restore_incomplet


def _etat_download(filename: str) -> str:
    """Télécharge un fichier depuis le repo. Renvoie l'un de :
      « ok »     — écrit sur le disque local ;
      « absent » — 404 franc : le fichier n'existe pas encore sur le dépôt ;
      « erreur » — panne transitoire (réseau, 5xx, timeout) : le fichier existe
                   peut-être, on n'a simplement pas pu le lire.
    Confondre « absent » et « erreur » est exactement ce qui permettait
    d'écraser une sauvegarde saine par un fichier reconstruit à vide.
    """
    if not _TOKEN:
        return "erreur"
    try:
        r = httpx.get(_file_url(filename), headers=_headers(), timeout=15.0,
                      params={"ref": _BRANCH})
        if r.status_code == 404:
            logger.info("Github: %s n'existe pas encore sur le repo", filename)
            return "absent"
        r.raise_for_status()
        body = r.json()
        content_b64 = body.get("content", "")
        sha = body.get("sha", "")
        if not content_b64:
            # Réponse 200 mais vide : on ne sait pas l'interpréter sûrement.
            # On la traite comme transitoire plutôt que d'affirmer « absent ».
            return "erreur"
        raw = base64.b64decode(content_b64)
        dest = _DATA_DIR / filename
        dest.write_bytes(raw)
        with _lock:
            _sha_cache[filename] = sha
            # Ce qu'on vient de télécharger est, par définition, déjà sur le
            # dépôt : sans cette empreinte, chaque redéploiement renverrait les
            # six fichiers inchangés.
            _empreintes[filename] = _empreinte(raw)
        logger.info("Github: %s restauré (%d bytes)", filename, len(raw))
        return "ok"
    except Exception as exc:
        logger.warning("Github download %s : %s", filename, exc)
        return "erreur"


def download_file(filename: str) -> bool:
    """Télécharge un fichier depuis le repo. True si succès, False sinon.
    Conservé pour compatibilité — préférer _etat_download quand la distinction
    404 / panne compte."""
    return _etat_download(filename) == "ok"


def upload_file(filename: str, forcer: bool = False) -> bool:
    """Upload (create or update) un fichier vers le repo.
    H11: sérialisé par fichier — pas de conflit SHA même avec 10 uploads concurrents.
    H12: SHA cache invalidé sur réponse vide au lieu d'être mis à "".

    `forcer` passe outre le contrôle de contenu identique.
    """
    if not _TOKEN:
        return False
    src = _DATA_DIR / filename
    if not src.exists():
        return False

    # Garde-fou anti-écrasement : si la restauration de ce fichier a échoué au
    # démarrage (panne transitoire, PAS un 404), le local a pu être reconstruit
    # à vide. L'envoyer maintenant remplacerait la sauvegarde par du vide. On
    # refuse tant que le blocage n'est pas levé par une restauration réussie.
    # `forcer` reste un échappatoire volontaire (sauvegarde manuelle explicite).
    if not forcer:
        with _lock:
            bloque = filename in _restore_incomplet
        if bloque:
            logger.warning(
                "Github upload %s : IGNORÉ — restauration incomplète, on ne "
                "risque pas d'écraser la sauvegarde par un fichier reconstruit "
                "à vide", filename)
            return False

    upload_lock = _get_upload_lock(filename)
    with upload_lock:
        try:
            content_bytes = src.read_bytes()

            # Contenu identique au dernier envoi réussi : rien à faire. On sort
            # avant de prendre le réseau, d'encoder en base64 et de créer un
            # commit qui ne changerait rien.
            emp = _empreinte(content_bytes)
            if not forcer:
                with _lock:
                    deja = _empreintes.get(filename)
                if deja == emp:
                    return True

            content_b64   = base64.b64encode(content_bytes).decode("ascii")

            # Récupérer le sha actuel si pas en cache
            with _lock:
                sha = _sha_cache.get(filename)
            if not sha:
                try:
                    r = httpx.get(_file_url(filename), headers=_headers(), timeout=10.0,
                                  params={"ref": _BRANCH})
                    if r.status_code == 200:
                        sha = r.json().get("sha")
                        if sha:
                            with _lock:
                                _sha_cache[filename] = sha
                except Exception:
                    pass

            payload = {
                "message": f"Auto-backup: {filename}",
                "content": content_b64,
                "branch":  _BRANCH,
            }
            if sha:
                payload["sha"] = sha

            r = httpx.put(_file_url(filename), headers=_headers(), json=payload, timeout=20.0)

            # H12: retry une fois sur 409 (sha obsolète) — refetch + retry
            if r.status_code == 409 or r.status_code == 422:
                logger.info("Github upload %s : sha obsolète, refetch + retry", filename)
                r2 = httpx.get(_file_url(filename), headers=_headers(), timeout=10.0,
                               params={"ref": _BRANCH})
                if r2.status_code == 200:
                    fresh_sha = r2.json().get("sha")
                    if fresh_sha:
                        payload["sha"] = fresh_sha
                        r = httpx.put(_file_url(filename), headers=_headers(), json=payload, timeout=20.0)

            r.raise_for_status()
            new_sha = r.json().get("content", {}).get("sha")
            with _lock:
                # H12: ne JAMAIS cacher "" — sinon empoisonne tous les uploads futurs
                if new_sha:
                    _sha_cache[filename] = new_sha
                else:
                    _sha_cache.pop(filename, None)
                # L'empreinte n'est retenue qu'après un envoi réussi : sur
                # échec, le prochain passage réessaie au lieu de croire le
                # fichier déjà sauvegardé.
                _empreintes[filename] = emp
            return True
        except Exception as exc:
            logger.warning("Github upload %s : %s", filename, exc)
            # Invalider le cache en cas d'erreur pour forcer un refetch propre
            with _lock:
                _sha_cache.pop(filename, None)
                _empreintes.pop(filename, None)
            return False


def envoyer_binaire(chemin_repo: str, donnees: bytes) -> bool:
    """Dépose un fichier binaire (photo, audio) à `chemin_repo` dans le dépôt.

    Contrairement aux JSON, chaque média a son propre chemin : on n'envoie que
    lui, jamais l'ensemble. Un média n'est jamais modifié après coup, donc pas
    de sha à gérer — s'il existe déjà, c'est le même contenu.
    """
    if not _TOKEN or not donnees:
        return False
    charge = {
        "message": f"Media: {chemin_repo}",
        "content": base64.b64encode(donnees).decode("ascii"),
        "branch": _BRANCH,
    }
    with _lock_branche:
        for essai in range(4):
            try:
                r = httpx.put(_file_url(chemin_repo), headers=_headers(),
                              timeout=30.0, json=charge)
            except Exception as exc:
                logger.warning("Github media %s : %s", chemin_repo, exc)
                return False
            if r.status_code in (200, 201, 422):   # 422 = déjà présent
                return True
            if r.status_code == 409:
                # La branche a bougé entre-temps : on laisse GitHub se poser.
                time.sleep(0.6 * (essai + 1))
                continue
            logger.warning("Github media %s : HTTP %s", chemin_repo, r.status_code)
            return False
    logger.warning("Github media %s : abandon après conflits répétés", chemin_repo)
    return False


def supprimer_binaire(chemin_repo: str) -> bool:
    """Retire un média du dépôt. Sert quand un message est effacé : sans ça,
    la photo « supprimée » resterait consultable dans la sauvegarde.
    """
    if not _TOKEN:
        return False
    with _lock_branche:
        try:
            r = httpx.get(_file_url(chemin_repo), headers=_headers(), timeout=10.0,
                          params={"ref": _BRANCH})
            if r.status_code == 404:
                return True                     # déjà absent : rien à faire
            r.raise_for_status()
            sha = r.json().get("sha")
            if not sha:
                return False
            for essai in range(4):
                d = httpx.request(
                    "DELETE", _file_url(chemin_repo), headers=_headers(), timeout=30.0,
                    json={"message": f"Suppression: {chemin_repo}", "sha": sha,
                          "branch": _BRANCH})
                if d.status_code == 200:
                    return True
                if d.status_code == 409:
                    time.sleep(0.6 * (essai + 1))
                    continue
                logger.warning("Github suppression %s : HTTP %s",
                               chemin_repo, d.status_code)
                return False
        except Exception as exc:
            logger.warning("Github suppression %s : %s", chemin_repo, exc)
        return False


def supprimer_binaire_async(chemin_repo: str) -> None:
    if not _TOKEN:
        return
    threading.Thread(target=supprimer_binaire, args=(chemin_repo,),
                     daemon=True).start()


def backup_binaire_async(chemin_repo: str, donnees: bytes) -> None:
    """Envoi d'un média en arrière-plan : le client n'attend pas GitHub."""
    if not _TOKEN:
        return
    threading.Thread(target=envoyer_binaire, args=(chemin_repo, donnees),
                     daemon=True).start()


def telecharger_binaire(chemin_repo: str) -> bytes:
    """Récupère un média du dépôt. Sert après un redéploiement, quand le
    disque éphémère de Render a été remis à zéro."""
    if not _TOKEN:
        return b""
    try:
        r = httpx.get(_file_url(chemin_repo), headers=_headers(), timeout=30.0,
                      params={"ref": _BRANCH})
        if r.status_code != 200:
            return b""
        contenu = (r.json() or {}).get("content", "")
        return base64.b64decode(contenu) if contenu else b""
    except Exception as exc:
        logger.warning("Github media download %s : %s", chemin_repo, exc)
        return b""


def _restaurer_un(fn: str, essais: int = 3) -> str:
    """Restaure un fichier avec quelques tentatives sur panne transitoire.
    Met à jour _restore_incomplet en conséquence et renvoie l'état final."""
    etat = "erreur"
    for essai in range(essais):
        etat = _etat_download(fn)
        if etat in ("ok", "absent"):
            break
        if essai < essais - 1:
            time.sleep(0.8 * (essai + 1))
    with _lock:
        if etat == "erreur":
            _restore_incomplet.add(fn)
        else:
            _restore_incomplet.discard(fn)
    return etat


def _retenter_restaurations_incompletes() -> None:
    """Réessaie en arrière-plan de restaurer les fichiers dont la récupération a
    échoué transitoirement, tant qu'il en reste. Chaque succès (ou 404 confirmé)
    lève le garde-fou et réautorise les envois de ce fichier."""
    for _ in range(6):                       # ~ jusqu'à quelques minutes
        with _lock:
            restants = list(_restore_incomplet)
        if not restants:
            return
        time.sleep(30)
        for fn in restants:
            etat = _restaurer_un(fn, essais=2)
            if etat == "ok":
                logger.info("Github: %s finalement restauré, envois réautorisés", fn)
            elif etat == "absent":
                logger.info("Github: %s confirmé absent du dépôt, envois réautorisés", fn)


def restore_all() -> None:
    """Au démarrage : télécharge TOUJOURS depuis GitHub (source of truth).
    H15: avant on skippait si le fichier local existait — mais sur Render free
    le filesystem est éphémère, donc les fichiers locaux sont stale ou inexistants.
    GitHub est la source de vérité.
    """
    if not _TOKEN:
        logger.info("Github backup désactivé (GITHUB_TOKEN absent)")
        return
    for fn in _FILES:
        etat = _restaurer_un(fn)
        if etat == "absent":
            local = _DATA_DIR / fn
            if local.exists():
                logger.info("Github: %s introuvable sur le repo, fichier local conservé", fn)
        elif etat == "erreur":
            logger.error(
                "Github: échec de restauration de %s — envois de ce fichier "
                "suspendus pour ne pas écraser la sauvegarde", fn)
    # S'il reste des restaurations en échec, on retente en tâche de fond : dès
    # qu'une réussit, le garde-fou anti-écrasement se lève tout seul.
    with _lock:
        reste = bool(_restore_incomplet)
    if reste:
        threading.Thread(target=_retenter_restaurations_incompletes,
                         daemon=True).start()


def backup_all() -> None:
    """Sauvegarde tous les fichiers existants vers GitHub."""
    if not _TOKEN:
        return
    for fn in _FILES:
        if (_DATA_DIR / fn).exists():
            upload_file(fn)


def backup_file_async(filename: str) -> None:
    """Lance un upload en arrière-plan (non-bloquant)."""
    if not _TOKEN:
        return
    threading.Thread(target=upload_file, args=(filename,), daemon=True).start()

"""
Sauvegarde automatique des fichiers de données vers un repo GitHub privé.

Permet une persistence "free" sur Render free tier (filesystem éphémère) :
- Au démarrage : restaure orders.json / blacklist.json / blocked.json depuis GitHub
- À chaque écriture : upload en arrière-plan vers GitHub (best-effort)
- Job périodique : sauvegarde toutes les 10 min en filet de sécurité

Requiert l'env var GITHUB_TOKEN (PAT avec scope `repo` ou OAuth gh CLI).
"""
import base64
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
          "livreurs.json"]

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


def download_file(filename: str) -> bool:
    """Télécharge un fichier depuis le repo. True si succès, False sinon."""
    if not _TOKEN:
        return False
    try:
        r = httpx.get(_file_url(filename), headers=_headers(), timeout=15.0,
                      params={"ref": _BRANCH})
        if r.status_code == 404:
            logger.info("Github: %s n'existe pas encore sur le repo", filename)
            return False
        r.raise_for_status()
        body = r.json()
        content_b64 = body.get("content", "")
        sha = body.get("sha", "")
        if not content_b64:
            return False
        raw = base64.b64decode(content_b64)
        dest = _DATA_DIR / filename
        dest.write_bytes(raw)
        with _lock:
            _sha_cache[filename] = sha
        logger.info("Github: %s restauré (%d bytes)", filename, len(raw))
        return True
    except Exception as exc:
        logger.warning("Github download %s : %s", filename, exc)
        return False


def upload_file(filename: str) -> bool:
    """Upload (create or update) un fichier vers le repo.
    H11: sérialisé par fichier — pas de conflit SHA même avec 10 uploads concurrents.
    H12: SHA cache invalidé sur réponse vide au lieu d'être mis à "".
    """
    if not _TOKEN:
        return False
    src = _DATA_DIR / filename
    if not src.exists():
        return False

    upload_lock = _get_upload_lock(filename)
    with upload_lock:
        try:
            content_bytes = src.read_bytes()
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
            return True
        except Exception as exc:
            logger.warning("Github upload %s : %s", filename, exc)
            # Invalider le cache en cas d'erreur pour forcer un refetch propre
            with _lock:
                _sha_cache.pop(filename, None)
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
        ok = download_file(fn)
        if not ok:
            local = _DATA_DIR / fn
            if local.exists():
                logger.info("Github: %s introuvable sur le repo, fichier local conservé", fn)


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

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
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_TOKEN  = os.getenv("GITHUB_TOKEN", "")
_OWNER  = os.getenv("GITHUB_DATA_OWNER", "millesimecoffee")
_REPO   = os.getenv("GITHUB_DATA_REPO",  "coffee-bot-data")
_BRANCH = os.getenv("GITHUB_DATA_BRANCH", "main")
_API    = "https://api.github.com"

_DATA_DIR  = Path(os.getenv("DATA_DIR", str(Path(__file__).parent)))
_FILES = ["orders.json", "blacklist.json", "blocked.json"]

_sha_cache: dict[str, str] = {}
_lock = threading.Lock()


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
    """Upload (create or update) un fichier vers le repo."""
    if not _TOKEN:
        return False
    src = _DATA_DIR / filename
    if not src.exists():
        return False
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
                    sha = r.json().get("sha", "")
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
        r.raise_for_status()
        new_sha = r.json().get("content", {}).get("sha", "")
        with _lock:
            _sha_cache[filename] = new_sha
        return True
    except Exception as exc:
        logger.warning("Github upload %s : %s", filename, exc)
        return False


def restore_all() -> None:
    """Au démarrage : restaure chaque fichier manquant depuis GitHub."""
    if not _TOKEN:
        logger.info("Github backup désactivé (GITHUB_TOKEN absent)")
        return
    for fn in _FILES:
        local = _DATA_DIR / fn
        if not local.exists():
            download_file(fn)


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

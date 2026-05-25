"""
Client HTTP minimaliste pour Supabase / PostgREST.
Aucune nouvelle dépendance — utilise httpx (déjà installé via python-telegram-bot).
"""
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
_KEY = os.getenv("SUPABASE_KEY", "")
_ENABLED = bool(_URL and _KEY)

_client: httpx.Client | None = None


def is_enabled() -> bool:
    """True si SUPABASE_URL et SUPABASE_KEY sont définis."""
    return _ENABLED


def _get_client() -> httpx.Client:
    """Singleton httpx.Client avec base_url et auth headers."""
    global _client
    if _client is None:
        _client = httpx.Client(
            base_url=f"{_URL}/rest/v1",
            headers={
                "apikey":        _KEY,
                "Authorization": f"Bearer {_KEY}",
                "Content-Type":  "application/json",
                "Prefer":        "return=representation",
            },
            timeout=20.0,
        )
    return _client


def select(table: str, **params: Any) -> list[dict]:
    """SELECT * FROM table avec filtres PostgREST.

    Exemples :
        select("orders")                                  # tout
        select("orders", user_id="eq.12345")              # WHERE user_id = 12345
        select("orders", order="created_at.desc")         # ORDER BY
        select("orders", limit=10)
        select("orders", select="user_id")                # colonnes spécifiques
    """
    try:
        r = _get_client().get(f"/{table}", params=params)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as exc:
        logger.error("Supabase select %s : %s", table, exc)
        return []


def insert(table: str, row: dict | list[dict]) -> list[dict]:
    """INSERT INTO table. Retourne les lignes insérées."""
    try:
        r = _get_client().post(f"/{table}", json=row)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as exc:
        logger.error("Supabase insert %s : %s — payload=%s", table, exc, row)
        return []


def upsert(table: str, row: dict | list[dict], on_conflict: str = "id") -> list[dict]:
    """INSERT ... ON CONFLICT (on_conflict) DO UPDATE."""
    try:
        client = _get_client()
        headers = {"Prefer": "resolution=merge-duplicates,return=representation"}
        r = client.post(
            f"/{table}",
            json=row,
            params={"on_conflict": on_conflict},
            headers=headers,
        )
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as exc:
        logger.error("Supabase upsert %s : %s", table, exc)
        return []


def update(table: str, patch: dict, **where: Any) -> list[dict]:
    """UPDATE table SET patch WHERE (where filters PostgREST).

    Ex : update("orders", {"status": "delivered"}, id="eq.ORD-123")
    """
    try:
        r = _get_client().patch(f"/{table}", json=patch, params=where)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as exc:
        logger.error("Supabase update %s : %s", table, exc)
        return []


def delete(table: str, **where: Any) -> bool:
    """DELETE FROM table WHERE ... — True si succès."""
    try:
        r = _get_client().delete(f"/{table}", params=where)
        r.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        logger.error("Supabase delete %s : %s", table, exc)
        return False


def rpc(fn: str, args: dict | None = None) -> Any:
    """Appel d'une fonction stockée (RPC)."""
    try:
        r = _get_client().post(f"/rpc/{fn}", json=args or {})
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as exc:
        logger.error("Supabase rpc %s : %s", fn, exc)
        return None

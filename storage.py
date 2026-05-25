"""
Stockage des commandes, blacklist, blocked et backups.

Backend :
    - Si SUPABASE_URL et SUPABASE_KEY sont définis  →  Supabase (PostgreSQL persistant)
    - Sinon                                          →  fallback fichiers JSON locaux

Toutes les fonctions gardent leur signature d'origine ; bot.py ne change pas.
"""
import json
import logging
import os
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import supabase_client as _sb
import github_backup as _gh

logger = logging.getLogger(__name__)

_DATA_DIR       = Path(os.getenv("DATA_DIR", str(Path(__file__).parent)))
_ORDERS_FILE    = _DATA_DIR / "orders.json"
_BLACKLIST_FILE = _DATA_DIR / "blacklist.json"
_BACKUP_DIR     = _DATA_DIR / "backups"
_lock = threading.Lock()

# H3: Index en mémoire pour lookup O(1) par order_id
_order_index: dict[str, dict] = {}

# Cache TTL pour les lectures « full table » (réduit les round-trips Supabase)
_ALL_CACHE: dict = {"data": None, "ts": 0.0}
_ALL_CACHE_TTL = 10.0  # secondes


def _use_supabase() -> bool:
    return _sb.is_enabled()


# ═══════════════════════════════════════════════════════════════════════════════
# Lecture / écriture orders — Supabase
# ═══════════════════════════════════════════════════════════════════════════════

def _load_from_supabase() -> list:
    """SELECT data FROM orders ORDER BY created_at ASC  →  list[dict]."""
    now = time.time()
    if _ALL_CACHE["data"] is not None and now - _ALL_CACHE["ts"] < _ALL_CACHE_TTL:
        return _ALL_CACHE["data"]

    rows = _sb.select("orders", select="data", order="created_at.asc", limit=10000)
    orders = [r.get("data") or {} for r in rows]
    _ALL_CACHE["data"] = orders
    _ALL_CACHE["ts"]   = now
    return orders


def _invalidate_cache() -> None:
    _ALL_CACHE["data"] = None
    _ALL_CACHE["ts"]   = 0.0


def _load_from_file() -> list:
    if not _ORDERS_FILE.exists():
        return []
    try:
        with _ORDERS_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Lecture orders.json : %s", exc)
        return []


def _save_to_file(orders: list) -> None:
    try:
        with _ORDERS_FILE.open("w", encoding="utf-8") as f:
            json.dump(orders, f, ensure_ascii=False, indent=2)
        _gh.backup_file_async("orders.json")
    except OSError as exc:
        logger.error("Écriture orders.json : %s", exc)


def _load() -> list:
    """Retourne TOUTES les commandes (le format historique : list[dict])."""
    if _use_supabase():
        return _load_from_supabase()
    return _load_from_file()


def _save(orders: list) -> None:
    """Conservé pour compatibilité — n'est utilisé qu'en mode fichier."""
    if not _use_supabase():
        _save_to_file(orders)


# ═══════════════════════════════════════════════════════════════════════════════
# API publique — commandes
# ═══════════════════════════════════════════════════════════════════════════════

def save_order(order: dict) -> None:
    """Ajoute une commande et met à jour l'index mémoire."""
    order.setdefault("created_at", datetime.now().isoformat(timespec="seconds"))
    with _lock:
        if _use_supabase():
            row = {
                "id":         order.get("order_id"),
                "user_id":    int(order.get("user_id") or 0),
                "created_at": _to_tz(order["created_at"]),
                "data":       order,
            }
            _sb.insert("orders", row)
            _invalidate_cache()
        else:
            orders = _load_from_file()
            orders.append(order)
            _save_to_file(orders)

        oid = order.get("order_id")
        if oid:
            _order_index[oid] = order


def get_order(order_id: str) -> dict | None:
    """Retourne la commande par son ID — O(1) en mémoire, fallback DB."""
    if order_id in _order_index:
        return _order_index[order_id]

    if _use_supabase():
        rows = _sb.select("orders", id=f"eq.{order_id}", select="data", limit=1)
        if rows:
            order = rows[0].get("data") or {}
            _order_index[order_id] = order
            return order
        return None

    with _lock:
        for o in _load_from_file():
            if o.get("order_id") == order_id:
                _order_index[order_id] = o
                return o
    return None


def update_order(order_id: str, updates: dict) -> bool:
    """Met à jour les champs d'une commande. Retourne True si trouvée."""
    with _lock:
        if _use_supabase():
            # Lire la commande actuelle, fusionner, ré-écrire le JSONB
            rows = _sb.select("orders", id=f"eq.{order_id}", select="data", limit=1)
            if not rows:
                logger.warning("update_order: '%s' introuvable", order_id)
                return False
            current = rows[0].get("data") or {}
            current.update(updates)
            _sb.update("orders", {"data": current}, id=f"eq.{order_id}")
            if order_id in _order_index:
                _order_index[order_id].update(updates)
            else:
                _order_index[order_id] = current
            _invalidate_cache()
            return True

        # Mode fichier
        orders = _load_from_file()
        for i, o in enumerate(orders):
            if o.get("order_id") == order_id:
                orders[i].update(updates)
                _save_to_file(orders)
                if order_id in _order_index:
                    _order_index[order_id].update(updates)
                return True
    logger.warning("update_order: '%s' introuvable", order_id)
    return False


def get_orders_by_user(user_id: int) -> list:
    """Commandes d'un utilisateur, plus récentes en premier."""
    if _use_supabase():
        rows = _sb.select(
            "orders",
            user_id=f"eq.{int(user_id)}",
            select="data",
            order="created_at.desc",
            limit=100,
        )
        return [r.get("data") or {} for r in rows]

    with _lock:
        orders = _load_from_file()
    return [o for o in reversed(orders) if o.get("user_id") == user_id]


def get_all_user_ids() -> list:
    """user_ids uniques (broadcast)."""
    if _use_supabase():
        rows = _sb.select("orders", select="user_id")
        seen, result = set(), []
        for r in rows:
            uid = r.get("user_id")
            if uid and uid not in seen:
                seen.add(uid)
                result.append(uid)
        return result

    with _lock:
        orders = _load_from_file()
    seen, result = set(), []
    for o in orders:
        uid = o.get("user_id")
        if uid and uid not in seen:
            seen.add(uid)
            result.append(uid)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Statistiques
# ═══════════════════════════════════════════════════════════════════════════════

def get_stats(date_str: str | None = None) -> dict:
    """Statistiques pour une date donnée (défaut = aujourd'hui)."""
    orders = _load()
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    day_orders = [o for o in orders if o.get("created_at", "").startswith(date_str)]

    ca_day = sum(float(o.get("total", 0)) for o in day_orders)
    ca_all = sum(float(o.get("total", 0)) for o in orders)

    # Top villes du jour
    city_stats: dict[str, dict] = {}
    for o in day_orders:
        city = o.get("city") or "Inconnue"
        if city not in city_stats:
            city_stats[city] = {"orders": 0, "ca": 0.0}
        city_stats[city]["orders"] += 1
        city_stats[city]["ca"]     += float(o.get("total", 0))
    top_cities_day = sorted(city_stats.items(), key=lambda x: x[1]["orders"], reverse=True)

    # Top produits du jour
    items_day: dict[str, int] = {}
    for o in day_orders:
        for item, qty in (o.get("cart") or {}).items():
            items_day[item] = items_day.get(item, 0) + qty
    top_items_day = sorted(items_day.items(), key=lambda x: x[1], reverse=True)[:5]

    # Top produits tous les temps
    items_all: dict[str, int] = {}
    for o in orders:
        for item, qty in (o.get("cart") or {}).items():
            items_all[item] = items_all.get(item, 0) + qty
    top_items_all = sorted(items_all.items(), key=lambda x: x[1], reverse=True)[:5]

    avg_day = (ca_day / len(day_orders)) if day_orders else 0.0
    avg_all = (ca_all / len(orders))     if orders     else 0.0

    return {
        "orders_today":    len(day_orders),
        "orders_total":    len(orders),
        "ca_today":        ca_day,
        "ca_total":        ca_all,
        "top_items":       top_items_all,
        "date_str":        date_str,
        "top_cities_day":  top_cities_day,
        "top_items_day":   top_items_day,
        "top_items_all":   top_items_all,
        "avg_basket_day":  avg_day,
        "avg_basket_all":  avg_all,
    }


def get_stats_period(start_date: str, end_date: str) -> dict:
    """Stats pour une période [start_date, end_date] (YYYY-MM-DD)."""
    orders = _load()
    period_orders = [
        o for o in orders
        if start_date <= o.get("created_at", "")[:10] <= end_date
    ]

    ca_period = sum(float(o.get("total", 0)) for o in period_orders)
    ca_all    = sum(float(o.get("total", 0)) for o in orders)

    city_stats: dict = {}
    for o in period_orders:
        city = o.get("city") or "Inconnue"
        if city not in city_stats:
            city_stats[city] = {"orders": 0, "ca": 0.0}
        city_stats[city]["orders"] += 1
        city_stats[city]["ca"]     += float(o.get("total", 0))
    top_cities = sorted(city_stats.items(), key=lambda x: x[1]["orders"], reverse=True)

    items_period: dict = {}
    for o in period_orders:
        for item, qty in (o.get("cart") or {}).items():
            items_period[item] = items_period.get(item, 0) + qty
    top_items_period = sorted(items_period.items(), key=lambda x: x[1], reverse=True)[:5]

    items_all: dict = {}
    for o in orders:
        for item, qty in (o.get("cart") or {}).items():
            items_all[item] = items_all.get(item, 0) + qty
    top_items_all = sorted(items_all.items(), key=lambda x: x[1], reverse=True)[:5]

    avg_period = ca_period / len(period_orders) if period_orders else 0.0
    avg_all    = ca_all    / len(orders)         if orders         else 0.0

    return {
        "start_date":        start_date,
        "end_date":          end_date,
        "orders_period":     len(period_orders),
        "orders_total":      len(orders),
        "ca_period":         ca_period,
        "ca_total":          ca_all,
        "top_cities":        top_cities,
        "top_items_period":  top_items_period,
        "top_items_all":     top_items_all,
        "avg_basket_period": avg_period,
        "avg_basket_all":    avg_all,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Blacklist (bans permanents)
# ═══════════════════════════════════════════════════════════════════════════════

def load_blacklist() -> set:
    if _use_supabase():
        rows = _sb.select("blacklist", select="user_id")
        return {int(r["user_id"]) for r in rows if r.get("user_id")}

    if not _BLACKLIST_FILE.exists():
        return set()
    try:
        with _BLACKLIST_FILE.open("r", encoding="utf-8") as f:
            return {int(uid) for uid in json.load(f)}
    except Exception as exc:
        logger.error("Lecture blacklist.json : %s", exc)
        return set()


def save_blacklist(blacklist: set) -> None:
    if _use_supabase():
        # Approche simple : DELETE puis INSERT en bulk (sets sont petits)
        _sb.delete("blacklist", user_id="gte.0")
        if blacklist:
            rows = [{"user_id": int(uid)} for uid in blacklist]
            _sb.insert("blacklist", rows)
        return

    try:
        with _BLACKLIST_FILE.open("w", encoding="utf-8") as f:
            json.dump(list(blacklist), f)
        _gh.backup_file_async("blacklist.json")
    except Exception as exc:
        logger.error("Écriture blacklist.json : %s", exc)


# ═══════════════════════════════════════════════════════════════════════════════
# Blocked (anti-spam temporaire, 5 min)
# ═══════════════════════════════════════════════════════════════════════════════

def load_blocked() -> dict[int, datetime]:
    """Retourne {user_id: expires_at_datetime} pour les blocages non expirés."""
    now = datetime.now()
    if _use_supabase():
        # PostgREST : filtrer par expires_at > now en ISO
        now_iso = now.replace(tzinfo=timezone.utc).isoformat()
        rows = _sb.select("blocked", select="user_id,expires_at", expires_at=f"gt.{now_iso}")
        result = {}
        for r in rows:
            try:
                exp = datetime.fromisoformat(r["expires_at"].replace("Z", "+00:00"))
                if exp.tzinfo is not None:
                    exp = exp.astimezone().replace(tzinfo=None)
                result[int(r["user_id"])] = exp
            except (ValueError, KeyError, TypeError):
                continue
        return result

    # Fallback fichier
    blocked_file = _DATA_DIR / "blocked.json"
    if not blocked_file.exists():
        return {}
    try:
        with blocked_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
        result = {}
        for uid_str, ts in data.items():
            try:
                exp = datetime.fromisoformat(ts)
                if exp > now:
                    result[int(uid_str)] = exp
            except (ValueError, TypeError):
                continue
        return result
    except Exception as exc:
        logger.error("Lecture blocked.json : %s", exc)
        return {}


def save_blocked(blocked: dict[int, datetime]) -> None:
    """Persiste {user_id: expires_at}. Remplace tout le contenu."""
    if _use_supabase():
        _sb.delete("blocked", user_id="gte.0")
        if blocked:
            rows = [
                {
                    "user_id":    int(uid),
                    "expires_at": _to_tz(exp.isoformat()),
                }
                for uid, exp in blocked.items()
            ]
            _sb.insert("blocked", rows)
        return

    blocked_file = _DATA_DIR / "blocked.json"
    try:
        data = {str(uid): ts.isoformat() for uid, ts in blocked.items()}
        with blocked_file.open("w", encoding="utf-8") as f:
            json.dump(data, f)
        _gh.backup_file_async("blocked.json")
    except Exception as exc:
        logger.error("Écriture blocked.json : %s", exc)


# ═══════════════════════════════════════════════════════════════════════════════
# Backups
# ═══════════════════════════════════════════════════════════════════════════════

def backup_orders() -> str | None:
    """Sauvegarde toutes les commandes dans backups/orders_YYYY-MM-DD.json.
    Garde les 30 derniers backups.
    """
    try:
        _BACKUP_DIR.mkdir(exist_ok=True)
        dest = _BACKUP_DIR / f"orders_{datetime.now().strftime('%Y-%m-%d')}.json"

        if _use_supabase():
            orders = _load_from_supabase()
            with dest.open("w", encoding="utf-8") as f:
                json.dump(orders, f, ensure_ascii=False, indent=2)
        else:
            if not _ORDERS_FILE.exists():
                return None
            shutil.copy2(_ORDERS_FILE, dest)

        # Purge anciens backups
        old_files = sorted(_BACKUP_DIR.glob("orders_*.json"))
        for f in old_files[:-30]:
            f.unlink(missing_ok=True)
        return str(dest)
    except Exception as exc:
        logger.error("Backup orders : %s", exc)
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _to_tz(iso_str: str) -> str:
    """Convertit un ISO naïf en ISO UTC (PostgREST timestamptz)."""
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except (ValueError, TypeError):
        return datetime.now(timezone.utc).isoformat()

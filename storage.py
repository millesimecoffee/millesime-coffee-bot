"""
Stockage des commandes (orders.json), blacklist et backups.
DATA_DIR : répertoire de stockage — défaut = dossier du script.
           Sur Railway, mettre DATA_DIR=/data (volume persistant).
"""
import json
import logging
import os
import shutil
import threading
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_DATA_DIR      = Path(os.getenv("DATA_DIR", str(Path(__file__).parent)))
_ORDERS_FILE   = _DATA_DIR / "orders.json"
_BLACKLIST_FILE = _DATA_DIR / "blacklist.json"
_BACKUP_DIR    = _DATA_DIR / "backups"
_lock = threading.Lock()

# H3: Index en mémoire pour lookup O(1) par order_id
_order_index: dict[str, dict] = {}


def _load() -> list:
    if not _ORDERS_FILE.exists():
        return []
    try:
        with _ORDERS_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Lecture orders.json : %s", exc)
        return []


def _save(orders: list) -> None:
    try:
        with _ORDERS_FILE.open("w", encoding="utf-8") as f:
            json.dump(orders, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        logger.error("Écriture orders.json : %s", exc)


def save_order(order: dict) -> None:
    """Ajoute une commande au fichier orders.json et met à jour l'index."""
    with _lock:
        orders = _load()
        order.setdefault("created_at", datetime.now().isoformat(timespec="seconds"))
        orders.append(order)
        _save(orders)
        oid = order.get("order_id")
        if oid:
            _order_index[oid] = order


def get_order(order_id: str) -> dict | None:
    """Retourne la commande par son ID — O(1) en mémoire, fallback fichier."""
    if order_id in _order_index:
        return _order_index[order_id]
    with _lock:
        orders = _load()
    for o in orders:
        if o.get("order_id") == order_id:
            _order_index[order_id] = o
            return o
    return None


def update_order(order_id: str, updates: dict) -> bool:
    """Met à jour les champs d'une commande existante dans orders.json.

    Paramètres
    ----------
    order_id : str
        Identifiant de la commande à modifier.
    updates : dict
        Clés/valeurs à mettre à jour (ex. {"cart": {...}, "total": 120}).

    Retourne True si la commande a été trouvée et mise à jour, False sinon.
    """
    with _lock:
        orders = _load()
        for i, o in enumerate(orders):
            if o.get("order_id") == order_id:
                orders[i].update(updates)
                _save(orders)
                # Mettre à jour l'index en mémoire s'il est présent
                if order_id in _order_index:
                    _order_index[order_id].update(updates)
                return True
    logger.warning("update_order: commande '%s' introuvable", order_id)
    return False


def get_stats(date_str: str | None = None) -> dict:
    """Retourne les statistiques complètes pour une date donnée (défaut = aujourd'hui).

    Paramètre
    ---------
    date_str : str | None
        Date au format ``YYYY-MM-DD``.  Si None, utilise la date du jour.

    Clés retournées
    ---------------
    Backward-compat :
        orders_today, orders_total, ca_today, ca_total, top_items

    Nouvelles clés :
        date_str        – date analysée (YYYY-MM-DD)
        top_cities_day  – list[(city, {"orders": int, "ca": float})] triée par nb commandes
        top_items_day   – list[(item, qty)]  top 5 produits du jour
        top_items_all   – list[(item, qty)]  top 5 produits tous les temps
        avg_basket_day  – panier moyen du jour (0 si aucune commande)
        avg_basket_all  – panier moyen global  (0 si aucune commande)
    """
    with _lock:
        orders = _load()

    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    day_orders = [o for o in orders if o.get("created_at", "").startswith(date_str)]

    ca_day = sum(o.get("total", 0) for o in day_orders)
    ca_all = sum(o.get("total", 0) for o in orders)

    # ── Top villes du jour ────────────────────────────────────────────────────
    city_stats: dict[str, dict] = {}
    for o in day_orders:
        city = o.get("city") or "Inconnue"
        if city not in city_stats:
            city_stats[city] = {"orders": 0, "ca": 0.0}
        city_stats[city]["orders"] += 1
        city_stats[city]["ca"]     += float(o.get("total", 0))
    top_cities_day = sorted(
        city_stats.items(), key=lambda x: x[1]["orders"], reverse=True
    )

    # ── Top produits du jour ──────────────────────────────────────────────────
    items_day: dict[str, int] = {}
    for o in day_orders:
        for item, qty in (o.get("cart") or {}).items():
            items_day[item] = items_day.get(item, 0) + qty
    top_items_day = sorted(items_day.items(), key=lambda x: x[1], reverse=True)[:5]

    # ── Top produits tous les temps ───────────────────────────────────────────
    items_all: dict[str, int] = {}
    for o in orders:
        for item, qty in (o.get("cart") or {}).items():
            items_all[item] = items_all.get(item, 0) + qty
    top_items_all = sorted(items_all.items(), key=lambda x: x[1], reverse=True)[:5]

    avg_day = (ca_day / len(day_orders)) if day_orders else 0.0
    avg_all = (ca_all / len(orders))     if orders     else 0.0

    return {
        # ── backward-compat ──────────────────────────────────────────────────
        "orders_today":    len(day_orders),
        "orders_total":    len(orders),
        "ca_today":        ca_day,
        "ca_total":        ca_all,
        "top_items":       top_items_all,          # rétro-compat cmd_stats ancien
        # ── nouvelles clés ───────────────────────────────────────────────────
        "date_str":        date_str,
        "top_cities_day":  top_cities_day,
        "top_items_day":   top_items_day,
        "top_items_all":   top_items_all,
        "avg_basket_day":  avg_day,
        "avg_basket_all":  avg_all,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Historique client
# ═══════════════════════════════════════════════════════════════════════════════

def get_orders_by_user(user_id: int) -> list:
    """Retourne les commandes d'un utilisateur (les plus récentes en premier)."""
    with _lock:
        orders = _load()
    return [o for o in reversed(orders) if o.get("user_id") == user_id]


# ═══════════════════════════════════════════════════════════════════════════════
# Broadcast — liste des clients uniques
# ═══════════════════════════════════════════════════════════════════════════════

def get_all_user_ids() -> list:
    """Retourne les user_id uniques ayant passé au moins une commande."""
    with _lock:
        orders = _load()
    seen, result = set(), []
    for o in orders:
        uid = o.get("user_id")
        if uid and uid not in seen:
            seen.add(uid)
            result.append(uid)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Blacklist permanente
# ═══════════════════════════════════════════════════════════════════════════════

def load_blacklist() -> set:
    if not _BLACKLIST_FILE.exists():
        return set()
    try:
        with _BLACKLIST_FILE.open("r", encoding="utf-8") as f:
            return set(int(uid) for uid in json.load(f))
    except Exception as exc:
        logger.error("Lecture blacklist.json : %s", exc)
        return set()


def save_blacklist(blacklist: set) -> None:
    try:
        with _BLACKLIST_FILE.open("w", encoding="utf-8") as f:
            json.dump(list(blacklist), f)
    except Exception as exc:
        logger.error("Écriture blacklist.json : %s", exc)


# ═══════════════════════════════════════════════════════════════════════════════
# Stats sur une période (rapport hebdomadaire)
# ═══════════════════════════════════════════════════════════════════════════════

def get_stats_period(start_date: str, end_date: str) -> dict:
    """Stats pour une période [start_date, end_date] au format YYYY-MM-DD."""
    with _lock:
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
# Backup automatique
# ═══════════════════════════════════════════════════════════════════════════════

def backup_orders() -> str | None:
    """Copie orders.json dans backups/orders_YYYY-MM-DD.json (garde 30 fichiers)."""
    if not _ORDERS_FILE.exists():
        return None
    try:
        _BACKUP_DIR.mkdir(exist_ok=True)
        dest = _BACKUP_DIR / f"orders_{datetime.now().strftime('%Y-%m-%d')}.json"
        shutil.copy2(_ORDERS_FILE, dest)
        # Purge des anciens backups (garder 30)
        old_files = sorted(_BACKUP_DIR.glob("orders_*.json"))
        for f in old_files[:-30]:
            f.unlink(missing_ok=True)
        return str(dest)
    except Exception as exc:
        logger.error("Backup orders.json : %s", exc)
        return None

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


# ── Registre des checkouts SumUp déjà consommés (anti-rejeu de paiement) ──────
# Un checkout payé reste « PAID » côté SumUp indéfiniment : sans ce registre
# PERSISTANT, rejouer /api/finalize_order avec le même sumup_id créerait N
# commandes pour un seul encaissement. Persisté sur disque + sauvegardé GitHub
# (le disque Render est éphémère : un simple set mémoire rouvrirait la faille
# à chaque redémarrage).
_SUMUP_FILE  = _DATA_DIR / "sumup_consomme.json"
_sumup_liste = None      # list chronologique (bornée)
_sumup_set   = None      # set pour lookup O(1)
_sumup_lock  = threading.Lock()
_SUMUP_MAX   = 20000


def _sumup_charger():
    global _sumup_liste, _sumup_set
    if _sumup_liste is None:
        try:
            with _SUMUP_FILE.open(encoding="utf-8") as f:
                _sumup_liste = [str(x) for x in json.load(f)]
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            _sumup_liste = []
        _sumup_set = set(_sumup_liste)
    return _sumup_liste


def sumup_deja_consomme(checkout_id: str) -> bool:
    if not checkout_id:
        return False
    with _sumup_lock:
        _sumup_charger()
        return checkout_id in _sumup_set


def sumup_marquer_consomme(checkout_id: str) -> None:
    if not checkout_id:
        return
    with _sumup_lock:
        lst = _sumup_charger()
        if checkout_id in _sumup_set:
            return
        lst.append(checkout_id)
        _sumup_set.add(checkout_id)
        if len(lst) > _SUMUP_MAX:                 # on oublie les plus anciens
            for old in lst[:len(lst) - _SUMUP_MAX]:
                _sumup_set.discard(old)
            del lst[:len(lst) - _SUMUP_MAX]
        try:
            _ecrire_json_atomique(_SUMUP_FILE, lst)
        except Exception as exc:
            logger.warning("sumup_consomme write : %s", exc)
    try:
        _gh.backup_file_async("sumup_consomme.json")
    except Exception:
        pass

# H3: Index en mémoire pour lookup O(1) par order_id
_order_index: dict[str, dict] = {}

# Cache TTL pour les lectures « full table » (réduit les round-trips Supabase)
_ALL_CACHE: dict = {"data": None, "ts": 0.0}
_ALL_CACHE_TTL = 10.0  # secondes


def _use_supabase() -> bool:
    return _sb.is_enabled()


# ── Découpage des journées ────────────────────────────────────────────────────
# La boutique vit à l'heure de Paris ; le serveur Render, lui, tourne en UTC.
# Comparer bêtement les 10 premiers caractères de created_at rangeait donc une
# commande de 00h30 (Paris) dans la journée de la veille.
try:
    from zoneinfo import ZoneInfo
    _PARIS = ZoneInfo("Europe/Paris")
except Exception:                                  # pragma: no cover
    _PARIS = timezone.utc

# Une commande annulée n'a rapporté aucun argent : elle ne doit apparaître dans
# aucun chiffre d'affaires. Le panel les excluait déjà, pas les rapports du bot.
_ANNULEES = ("cancelled", "cancelled_by_client")


def _jour_de(o: dict) -> str:
    """Date « YYYY-MM-DD » à laquelle la commande compte, heure de Paris."""
    brut = (o.get("created_at") or "").strip()
    if not brut:
        return ""
    try:
        d = datetime.fromisoformat(brut.replace("Z", "+00:00"))
    except ValueError:
        return brut[:10]
    if d.tzinfo is None:                # ancien format sans fuseau : déjà local
        return d.strftime("%Y-%m-%d")
    return d.astimezone(_PARIS).strftime("%Y-%m-%d")


def _aujourdhui_paris() -> str:
    return datetime.now(_PARIS).strftime("%Y-%m-%d")


def _encaisse(o: dict) -> float:
    """Montant réellement encaissé : 0 pour une commande annulée."""
    if (o.get("status") or "pending") in _ANNULEES:
        return 0.0
    try:
        return float(o.get("total", 0))
    except (TypeError, ValueError):
        return 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# Lecture / écriture orders — Supabase
# ═══════════════════════════════════════════════════════════════════════════════

_SUPABASE_LIMIT = 50000  # H13: cap raisonnable (au-delà → pagination requise)

def _load_from_supabase() -> list:
    """SELECT data FROM orders ORDER BY created_at ASC  →  list[dict]."""
    now = time.time()
    if _ALL_CACHE["data"] is not None and now - _ALL_CACHE["ts"] < _ALL_CACHE_TTL:
        return _ALL_CACHE["data"]

    rows = _sb.select("orders", select="data", order="created_at.asc", limit=_SUPABASE_LIMIT)
    if len(rows) >= _SUPABASE_LIMIT:
        logger.warning("⚠ _load_from_supabase: limite %d atteinte, données tronquées !", _SUPABASE_LIMIT)
    orders = [r.get("data") or {} for r in rows]
    _ALL_CACHE["data"] = orders
    _ALL_CACHE["ts"]   = now
    return orders


def _invalidate_cache() -> None:
    _ALL_CACHE["data"] = None
    _ALL_CACHE["ts"]   = 0.0


# Cache de lecture du fichier, invalidé par la signature du fichier lui-même.
# Le panel owner se rafraîchit toutes les 3 s et orders.json est à ~97 % des
# selfies en base64 : sans cache, on ré-analyserait plusieurs mégaoctets de
# JSON en continu pour des données inchangées.
_FILE_CACHE: dict = {"cle": None, "data": None}


class LectureImpossible(Exception):
    """orders.json existe mais n'a pas pu être lu."""


def _load_from_file(pour_ecriture: bool = False) -> list:
    """Lit les commandes. `pour_ecriture` : lève au lieu de renvoyer une liste
    vide si le fichier est illisible — voir le commentaire dans le except."""
    if not _ORDERS_FILE.exists():
        return []
    try:
        st = _ORDERS_FILE.stat()
        cle = (st.st_mtime_ns, st.st_size)
        if _FILE_CACHE["cle"] == cle and _FILE_CACHE["data"] is not None:
            # Copie de surface : un appelant qui ajoute ou retire une commande
            # ne doit pas modifier le cache par effet de bord.
            return list(_FILE_CACHE["data"])
        with _ORDERS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        _FILE_CACHE["cle"] = cle
        _FILE_CACHE["data"] = data
        return list(data)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Lecture orders.json : %s", exc)
        if pour_ecriture:
            # Renvoyer une liste vide ici serait catastrophique : l'appelant
            # ajouterait sa commande à cette liste vide puis réécrirait le
            # fichier, effaçant tout l'historique. On échoue bruyamment.
            raise LectureImpossible(str(exc)) from exc
        return []


def _ecrire_json_atomique(chemin: Path, donnees, indent=None) -> None:
    """Écrit un JSON sans jamais laisser le fichier dans un état partiel.

    Ouvrir directement en « w » vide le fichier avant de le réécrire : toute
    lecture concurrente voit alors du JSON tronqué, et un arrêt du processus
    au mauvais moment le corrompt définitivement. Ce cas s'est produit en
    production sur orders.json. os.replace() est atomique.
    """
    tmp = chemin.with_suffix(chemin.suffix + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(donnees, f, ensure_ascii=False, indent=indent)
            f.flush()
            os.fsync(f.fileno())
        # Windows refuse le remplacement tant qu'un lecteur tient le fichier
        # ouvert (WinError 5), là où POSIX l'autorise toujours.
        derniere = None
        for essai in range(12):
            try:
                os.replace(tmp, chemin)
                return
            except PermissionError as exc:
                derniere = exc
                time.sleep(0.03 * (essai + 1))
        raise derniere
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _save_to_file(orders: list) -> None:
    try:
        _ecrire_json_atomique(_ORDERS_FILE, orders, indent=2)
        _gh.backup_file_async("orders.json")
    except OSError as exc:
        logger.error("Écriture orders.json : %s", exc)
        raise


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

# ── Photos rangées à côté des commandes ──────────────────────────────────────
# Les selfies vivaient DANS orders.json : ils y pesaient 97 % du fichier
# (624 Ko sur 642 Ko pour 19 commandes). Or le fichier entier est réécrit et
# renvoyé au dépôt de sauvegarde à chaque changement de statut. À ce rythme, il
# aurait dépassé 17 Mo en un an, avec autant de copies dans l'historique.
#
# Chaque photo est donc écrite une fois dans son propre fichier, et la commande
# n'en garde qu'une référence. orders.json retombe à quelques kilo-octets et
# n'augmente plus que de la taille d'une ligne de texte par commande.
_PHOTOS_DIR = _DATA_DIR / "photos"
_CHAMPS_PHOTO = ("selfie_b64", "proof_b64")


def _chemin_photo(order_id: str, champ: str) -> Path:
    sur = "".join(c for c in str(order_id) if c.isalnum() or c in "-_")[:40]
    return _PHOTOS_DIR / f"{sur}.{champ}.txt"


def _sortir_photos(order: dict) -> dict:
    """Écrit les photos à côté et renvoie une COPIE de la commande sans elles.

    Une copie, car l'appelant se sert encore de la sienne juste après — la
    notification Pushover envoie le selfie qui vient d'être enregistré.
    """
    oid = order.get("order_id")
    if not oid:
        return order
    allege = dict(order)
    for champ in _CHAMPS_PHOTO:
        valeur = order.get(champ) or ""
        if not valeur:
            continue
        chemin = _chemin_photo(oid, champ)
        try:
            _PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
            tmp = chemin.with_suffix(".tmp")
            tmp.write_text(valeur, encoding="utf-8")
            os.replace(tmp, chemin)
        except OSError as exc:
            # On préfère une commande un peu lourde à une photo perdue.
            logger.error("Écriture photo %s/%s : %s", oid, champ, exc)
            continue
        allege[champ] = ""
        allege[champ.replace("_b64", "_fichier")] = chemin.name
        try:
            _gh.backup_binaire_async(f"photos/{chemin.name}", valeur.encode("utf-8"))
        except Exception as exc:
            logger.warning("Sauvegarde photo %s : %s", chemin.name, exc)
    return allege


def _rendre_photos(order: dict) -> dict:
    """Remet les photos dans la commande. Sans effet sur les anciennes, qui les
    portent encore directement."""
    if not order:
        return order
    manquantes = [c for c in _CHAMPS_PHOTO
                  if not order.get(c) and order.get(c.replace("_b64", "_fichier"))]
    if not manquantes:
        return order
    complet = dict(order)
    for champ in manquantes:
        chemin = _PHOTOS_DIR / str(order[champ.replace("_b64", "_fichier")])
        try:
            complet[champ] = chemin.read_text(encoding="utf-8")
        except OSError:
            # Disparue du disque (Render repart à vide) : on la retélécharge.
            try:
                donnees = _gh.telecharger_binaire(f"photos/{chemin.name}")
            except Exception:
                donnees = b""
            if donnees:
                try:
                    _PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
                    chemin.write_bytes(donnees)
                except OSError:
                    pass
                complet[champ] = donnees.decode("utf-8", "ignore")
            else:
                logger.warning("Photo introuvable : %s", chemin.name)
                complet[champ] = ""
    return complet


def migrer_photos() -> int:
    """Sort les photos des commandes déjà enregistrées.

    Appelée une fois au démarrage. Sans effet si tout est déjà rangé : elle ne
    réécrit le fichier que si elle a effectivement sorti quelque chose. Les
    commandes migrées gardent leur photo, simplement ailleurs.
    """
    if _use_supabase():
        return 0
    try:
        with _lock:
            orders = _load_from_file()
            if not orders:
                return 0
            avant = sum(len(o.get(c) or "") for o in orders for c in _CHAMPS_PHOTO)
            if not avant:
                return 0
            sorties = [_sortir_photos(o) for o in orders]
            deplacees = sum(1 for a, b in zip(orders, sorties)
                            if any(a.get(c) and not b.get(c) for c in _CHAMPS_PHOTO))
            if not deplacees:
                return 0
            _save_to_file(sorties)
            _order_index.clear()
        logger.info("Photos sorties de orders.json : %d commande(s), %d Ko liberes",
                    deplacees, avant // 1024)
        return deplacees
    except Exception as exc:
        # Une migration qui échoue ne doit pas empêcher la boutique de démarrer :
        # les commandes gardent alors leurs photos à l'ancienne, et tout marche.
        logger.error("Migration des photos : %s", exc)
        return 0


def a_une_photo(order: dict, champ: str = "selfie_b64") -> bool:
    """Vrai si la commande a cette photo, qu'elle soit rangée dedans ou à côté.
    Les listes s'en servent pour afficher l'icône sans charger l'image."""
    return bool(order.get(champ) or order.get(champ.replace("_b64", "_fichier")))


def save_order(order: dict) -> None:
    """Ajoute une commande et met à jour l'index mémoire."""
    # Horodatage *avec* décalage UTC : sans lui, le navigateur du panel owner
    # interprète l'ISO comme de l'heure locale alors que le serveur est en UTC,
    # et toute commande fraîche s'affiche « il y a 2 h ».
    order.setdefault(
        "created_at",
        datetime.now().astimezone().isoformat(timespec="seconds"),
    )
    with _lock:
        if _use_supabase():
            row = {
                "id":         order.get("order_id"),
                "user_id":    int(order.get("user_id") or 0),
                "created_at": _to_tz(order["created_at"]),
                "data":       order,
            }
            res = _sb.insert("orders", row)
            _invalidate_cache()
            # _sb.insert avale les erreurs HTTP et renvoie [] ; avec
            # Prefer: return=representation, un insert réussi renvoie la ligne.
            # On LÈVE si rien n'est revenu, avant de peupler l'index mémoire :
            # sinon la commande n'est nulle part en base mais get_order renverrait
            # un faux positif tant que le process vit, puis disparaîtrait au
            # redémarrage — et l'appelant croirait à un succès.
            if not res:
                raise RuntimeError(f"insert Supabase échoué (commande {order.get('order_id')})")
        else:
            # Les photos partent dans leurs propres fichiers : ce qui entre
            # dans orders.json n'en garde qu'une référence.
            allege = _sortir_photos(order)
            orders = _load_from_file(pour_ecriture=True)
            orders.append(allege)
            _save_to_file(orders)
            order = allege

        oid = order.get("order_id")
        if oid:
            _order_index[oid] = order
            # L'index ne garde que les commandes récentes : au-delà, get_order
            # relit le fichier, ce qui est le comportement d'origine. Sans
            # plafond, la mémoire enfle d'une entrée par commande, pour toujours.
            if len(_order_index) > 3000:
                for vieille in list(_order_index)[:len(_order_index) - 3000]:
                    _order_index.pop(vieille, None)


def get_order(order_id: str) -> dict | None:
    """Retourne la commande par son ID — O(1) en mémoire, fallback DB.
    H14: lecture/écriture de _order_index toujours sous _lock.
    """
    with _lock:
        cached = _order_index.get(order_id)
    if cached is not None:
        return _rendre_photos(cached)

    if _use_supabase():
        rows = _sb.select("orders", id=f"eq.{order_id}", select="data", limit=1)
        if rows:
            order = rows[0].get("data") or {}
            with _lock:
                _order_index[order_id] = order
            return _rendre_photos(order)
        return None

    with _lock:
        for o in _load_from_file():
            if o.get("order_id") == order_id:
                complet = _rendre_photos(o)
                _order_index[order_id] = complet
                return complet
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
        orders = _load_from_file(pour_ecriture=True)
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
        date_str = _aujourdhui_paris()

    day_orders = [o for o in orders if _jour_de(o) == date_str]

    ca_day = sum(_encaisse(o) for o in day_orders)
    ca_all = sum(_encaisse(o) for o in orders)

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

    # Panier moyen : rapporté aux seules commandes encaissées, sinon chaque
    # annulation ferait mécaniquement baisser la moyenne.
    payees_jour = [o for o in day_orders if _encaisse(o) > 0]
    payees_tout = [o for o in orders if _encaisse(o) > 0]
    avg_day = (ca_day / len(payees_jour)) if payees_jour else 0.0
    avg_all = (ca_all / len(payees_tout)) if payees_tout else 0.0

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
        if o.get("created_at") and start_date <= _jour_de(o) <= end_date
    ]

    ca_period = sum(_encaisse(o) for o in period_orders)
    ca_all    = sum(_encaisse(o) for o in orders)

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

    payees_periode = [o for o in period_orders if _encaisse(o) > 0]
    payees_tout    = [o for o in orders if _encaisse(o) > 0]
    avg_period = ca_period / len(payees_periode) if payees_periode else 0.0
    avg_all    = ca_all    / len(payees_tout)    if payees_tout    else 0.0

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
    """H10: en mode Supabase, on upsert au lieu de DELETE+INSERT (atomique).
    Les suppressions sont gérées séparément (cf. delete_from_blacklist)."""
    if _use_supabase():
        if blacklist:
            rows = [{"user_id": int(uid)} for uid in blacklist]
            _sb.upsert("blacklist", rows, on_conflict="user_id")
        return

    try:
        _ecrire_json_atomique(_BLACKLIST_FILE, list(blacklist))
        _gh.backup_file_async("blacklist.json")
    except Exception as exc:
        logger.error("Écriture blacklist.json : %s", exc)


def delete_from_blacklist(user_id: int) -> bool:
    """Supprime un user de la blacklist (atomique en mode Supabase)."""
    if _use_supabase():
        return _sb.delete("blacklist", user_id=f"eq.{int(user_id)}")
    return True  # le fichier sera réécrit par save_blacklist(set sans ce uid)


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
    """Persiste {user_id: expires_at}.
    H10: upsert au lieu de DELETE+INSERT pour éviter la fenêtre vide.
    Purge des entrées expirées avant l'écriture.
    """
    now = datetime.now()
    # Purger les expirés
    blocked = {uid: exp for uid, exp in blocked.items() if exp > now}

    if _use_supabase():
        if blocked:
            rows = [
                {
                    "user_id":    int(uid),
                    "expires_at": _to_tz(exp.isoformat()),
                }
                for uid, exp in blocked.items()
            ]
            _sb.upsert("blocked", rows, on_conflict="user_id")
        # Supprimer les expirés côté serveur aussi
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            _sb.delete("blocked", expires_at=f"lt.{now_iso}")
        except Exception:
            pass
        return

    blocked_file = _DATA_DIR / "blocked.json"
    try:
        data = {str(uid): ts.isoformat() for uid, ts in blocked.items()}
        _ecrire_json_atomique(blocked_file, data)
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

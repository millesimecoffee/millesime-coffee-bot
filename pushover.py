"""Notifications Pushover — canal de secours à côté de Telegram.

Pourquoi : les notifications Telegram se noient dans les autres conversations.
Pushover sonne comme une alarme et passe le mode silencieux, ce qui convient
mieux à une nouvelle commande qu'il ne faut pas rater.

Il faut DEUX identifiants, tous deux sur https://pushover.net :
  - PUSHOVER_USER_KEY  : votre clé personnelle, visible sur le tableau de bord
  - PUSHOVER_APP_TOKEN : jeton d'application, à créer via « Create an
    Application/API Token ». C'est lui qui autorise l'envoi.

Tant que l'un des deux manque, ce module ne fait rien et ne lève jamais :
une notification qui échoue ne doit en aucun cas faire perdre une commande.
"""
import logging
import os
import threading

logger = logging.getLogger(__name__)

_API = "https://api.pushover.net/1/messages.json"
_TIMEOUT = 8.0

# On ne veut pas répéter le même avertissement à chaque commande.
_avertissement_emis = False
_avertissement_lock = threading.Lock()


def est_configure() -> bool:
    return bool(os.getenv("PUSHOVER_USER_KEY", "").strip()
                and os.getenv("PUSHOVER_APP_TOKEN", "").strip())


def _avertir_une_fois() -> None:
    global _avertissement_emis
    with _avertissement_lock:
        if _avertissement_emis:
            return
        _avertissement_emis = True
    manque = []
    if not os.getenv("PUSHOVER_USER_KEY", "").strip():
        manque.append("PUSHOVER_USER_KEY")
    if not os.getenv("PUSHOVER_APP_TOKEN", "").strip():
        manque.append("PUSHOVER_APP_TOKEN")
    logger.info("Pushover inactif (manque : %s)", ", ".join(manque))


def envoyer_bloquant(message: str, titre: str = "", priorite: int = 0,
                     url: str = "", url_titre: str = "") -> bool:
    """Envoie et attend la réponse. Retourne True si Pushover a accepté."""
    user  = os.getenv("PUSHOVER_USER_KEY", "").strip()
    token = os.getenv("PUSHOVER_APP_TOKEN", "").strip()
    if not (user and token):
        _avertir_une_fois()
        return False

    donnees = {
        "token":   token,
        "user":    user,
        "message": message[:1024],          # limite Pushover
        "priority": max(-2, min(1, int(priorite))),   # 2 exigerait un accusé
    }
    if titre:
        donnees["title"] = titre[:250]
    if url:
        donnees["url"] = url[:512]
        if url_titre:
            donnees["url_title"] = url_titre[:100]

    try:
        import httpx
        r = httpx.post(_API, data=donnees, timeout=_TIMEOUT)
        # L'API répond 200 + {"status":1} en cas de succès. Un 4xx ne lève pas
        # d'exception avec httpx : sans cette lecture, un jeton invalide
        # passerait totalement inaperçu.
        if r.status_code == 200 and (r.json() or {}).get("status") == 1:
            return True
        logger.warning("Pushover refuse (HTTP %s) : %s", r.status_code, r.text[:200])
    except Exception as exc:
        logger.warning("Pushover injoignable : %s", exc)
    return False


def envoyer(message: str, titre: str = "", priorite: int = 0,
            url: str = "", url_titre: str = "") -> None:
    """Version « on n'attend pas ». Utilisée dans les chemins de commande :
    la confirmation client ne doit jamais attendre un service tiers."""
    if not est_configure():
        _avertir_une_fois()
        return
    threading.Thread(
        target=envoyer_bloquant,
        args=(message, titre, priorite, url, url_titre),
        daemon=True,
    ).start()


def nouvelle_commande(order_id: str, ville: str, total, devise: str,
                      nb_articles: int, client: str = "") -> None:
    """Notification type pour une commande qui vient d'arriver."""
    lignes = [f"{total:,.0f} {devise} · {nb_articles} article(s)".replace(",", " ")]
    if ville:
        lignes.append(f"Ville : {ville}")
    if client:
        lignes.append(f"Client : {client}")
    envoyer(
        message="\n".join(lignes),
        titre=f"Nouvelle commande {order_id}",
        priorite=1,   # haute : contourne les heures de silence
    )

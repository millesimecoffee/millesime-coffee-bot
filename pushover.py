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

Trois moments du parcours client déclenchent une notification, avec des
priorités différentes pour ne pas noyer l'important sous l'anecdotique :
  -1  entrée dans le catalogue (silencieuse)      → webapp._notify_owner_client_entry
   0  pays et ville choisis                       → webapp.api_notify_city
   1  commande passée (passe le mode silencieux)  → nouvelle_commande()
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


# ── Messages du parcours client ─────────────────────────────────────────────
# Formulations fixées par le propriétaire de la boutique : ne pas reformuler
# sans lui demander.

# En français la préposition devant un pays dépend de son genre et de son
# nombre. « EN PORTUGAL » ou « EN PAYS-BAS » seraient fautifs, d'où cette
# table. Tout pays absent prend « EN », qui couvre les féminins (la France,
# l'Italie, la Grèce…), largement majoritaires dans le catalogue.
_PREPOSITION_PAYS = {
    "PORTUGAL":    "AU",
    "MAROC":       "AU",
    "PAYS-BAS":    "AUX",
    "ÉTATS-UNIS":  "AUX",
    "ETATS-UNIS":  "AUX",
}


def _separer_drapeau(pays: str):
    """Découpe « 🇫🇷 France » en ('🇫🇷', 'FRANCE')."""
    pays = (pays or "").strip()
    if " " in pays:
        drapeau, nom = pays.split(" ", 1)
        return drapeau.strip(), nom.strip().upper()
    return "", pays.upper()


def entree_shop() -> None:
    envoyer(message="UN CLIENT EST ENTRÉE DANS LE SHOP 🛍️", priorite=-1)


def pays_choisi(pays: str) -> None:
    """`pays` au format du catalogue : « 🇫🇷 France »."""
    drapeau, nom = _separer_drapeau(pays)
    prep = _PREPOSITION_PAYS.get(nom, "EN")
    envoyer(message=f"UN CLIENT VEUX COMMANDER {prep} {nom} {drapeau}".strip(),
            priorite=0)


def ville_choisie(ville: str, pays: str) -> None:
    drapeau, _ = _separer_drapeau(pays)
    envoyer(message=f"UN CLIENT VEUX COMMANDER À {(ville or '').upper()} {drapeau}".strip(),
            priorite=0)


def nouvelle_commande(order_id: str, adresse: str, articles, total,
                      devise: str = "€", client: str = "") -> None:
    """Bon de commande. `articles` : liste de libellés déjà mis en forme
    (« 1G COCA × 2 »), ou dict {produit: quantité}."""
    if isinstance(articles, dict):
        articles = [f"{p} × {q}" if q and int(q) > 1 else str(p)
                    for p, q in articles.items()]
    articles = [str(a).upper() for a in (articles or []) if str(a).strip()]

    # L'adresse arrive tantôt séparée par des virgules, tantôt déjà sur
    # plusieurs lignes selon d'où elle vient. On accepte les deux et on la
    # remet en forme postale.
    lignes_adresse = [p.strip().upper()
                      for bloc_adr in (adresse or "").split(",")
                      for p in bloc_adr.splitlines() if p.strip()]

    bloc = [f"🔖 BON DE COMMANDE N•{order_id}", ""]
    if lignes_adresse:
        bloc.append("📍 " + "\n".join(lignes_adresse))
        bloc.append("")
    if articles:
        # Un 🛍️ par ligne : avec plusieurs articles, un seul marqueur en tête
        # laissait les suivants sans repère et le bloc paraissait cassé.
        bloc.extend(f"🛍️ {a}" for a in articles)
        bloc.append("")
    try:
        montant = f"{float(total):,.0f}".replace(",", " ")
    except (TypeError, ValueError):
        montant = str(total)
    bloc.append(f"💰 {montant}{devise}")
    if client:
        bloc += ["", client]

    envoyer(message="\n".join(bloc),
            titre="",          # le message se suffit à lui-même
            priorite=1)        # haute : contourne les heures de silence

"""Traduction automatique des messages de la messagerie.

Chacun lit dans sa langue : le client écrit en anglais, la boutique lit en
français ; la boutique répond en français, le client lit en anglais.

Deux fournisseurs, dans cet ordre :
  1. DeepL si DEEPL_API_KEY est défini — officiel, meilleure qualité,
     500 000 caractères par mois sur l'offre gratuite ;
  2. sinon le point d'entrée public de Google Traduction, sans clé. Il rend
     service mais n'est pas documenté : il peut se fermer ou limiter le débit.
     C'est le repli, pas le choix par défaut.

Une traduction ratée n'est jamais bloquante : le message part dans sa langue
d'origine, ce qui vaut infiniment mieux qu'un message perdu.
"""
import logging
import os
import re
import threading
import time

logger = logging.getLogger(__name__)

# Cache : deux clients qui écrivent « thank you » ne coûtent qu'une traduction.
_cache: dict[tuple, str] = {}
_cache_lock = threading.Lock()
_CACHE_MAX = 2000

MAX_CARACTERES = 1500          # au-delà, on n'appelle pas le service

# Mots très fréquents, propres à chaque langue : suffisent à trancher sans
# appeler un service de détection.
_INDICES = {
    "fr": {"le", "la", "les", "un", "une", "des", "je", "tu", "il", "elle",
           "nous", "vous", "est", "sont", "bonjour", "merci", "oui", "non",
           "pour", "avec", "dans", "sur", "où", "quand", "combien", "commande",
           "livraison", "adresse", "arrive", "bien", "bonsoir", "salut", "ça"},
    "en": {"the", "you", "your", "and", "are", "is", "hello", "hi", "thanks",
           "thank", "please", "yes", "no", "for", "with", "in", "on", "where",
           "when", "how", "much", "order", "delivery", "address", "coming",
           "ok", "okay", "good", "can", "will", "im", "i'm", "my"},
    "es": {"el", "la", "los", "las", "un", "una", "yo", "tu", "usted", "es",
           "son", "hola", "gracias", "sí", "no", "para", "con", "en", "sobre",
           "dónde", "cuándo", "cuánto", "pedido", "entrega", "dirección"},
    "ru": {"и", "в", "не", "на", "я", "что", "он", "она", "как", "это",
           "здравствуйте", "привет", "спасибо", "да", "нет", "для", "с", "где",
           "когда", "сколько", "заказ", "доставка", "адрес", "хорошо", "пожалуйста"},
}

# Le russe s'écrit en cyrillique, qu'aucune des trois autres langues n'emploie :
# c'est un indice bien plus sûr qu'une liste de mots.
_CYRILLIQUE = re.compile(r"[Ѐ-ӿ]")


def _mots(texte: str) -> list:
    return re.findall(r"[a-zà-öø-ÿЀ-ӿ']+", (texte or "").casefold())


def detecter(texte: str) -> str:
    """Langue probable du texte : « fr », « en », « es », « ru », ou "" si
    indécis."""
    if _CYRILLIQUE.search(texte or ""):
        return "ru"
    mots = _mots(texte)
    if not mots:
        return ""
    scores = {lg: sum(1 for m in mots if m in indices)
              for lg, indices in _INDICES.items()}
    meilleur = max(scores, key=scores.get)
    if scores[meilleur] == 0:
        return ""
    # Un seul mot reconnu sur un texte long ne prouve rien.
    if scores[meilleur] == 1 and len(mots) > 6:
        return ""
    return meilleur


def est_configure() -> bool:
    return bool(os.getenv("DEEPL_API_KEY", "").strip()) or \
        os.getenv("TRADUCTION_REPLI", "1").strip() not in ("0", "", "non")


def _deepl(texte: str, vers: str, depuis: str = "") -> str:
    cle = os.getenv("DEEPL_API_KEY", "").strip()
    if not cle:
        return ""
    hote = "api-free.deepl.com" if cle.endswith(":fx") else "api.deepl.com"
    try:
        import httpx
        donnees = {"text": texte, "target_lang": vers.upper()}
        if depuis:
            donnees["source_lang"] = depuis.upper()
        r = httpx.post(f"https://{hote}/v2/translate", timeout=10.0,
                       headers={"Authorization": f"DeepL-Auth-Key {cle}"},
                       data=donnees)
        if r.status_code != 200:
            logger.warning("DeepL HTTP %s : %s", r.status_code, r.text[:120])
            return ""
        trads = (r.json() or {}).get("translations") or []
        return (trads[0].get("text") or "") if trads else ""
    except Exception as exc:
        logger.warning("DeepL : %s", exc)
        return ""


def _google_public(texte: str, vers: str, depuis: str = "") -> str:
    """Repli sans clé. Point d'entrée non documenté : on ne s'y fie pas."""
    if os.getenv("TRADUCTION_REPLI", "1").strip() in ("0", "", "non"):
        return ""
    try:
        import httpx
        r = httpx.get("https://translate.googleapis.com/translate_a/single",
                      timeout=10.0,
                      params={"client": "gtx", "sl": depuis or "auto",
                              "tl": vers, "dt": "t", "q": texte})
        if r.status_code != 200:
            logger.warning("traduction repli HTTP %s", r.status_code)
            return ""
        blocs = (r.json() or [])[0] or []
        return "".join(b[0] for b in blocs if b and b[0])
    except Exception as exc:
        logger.warning("traduction repli : %s", exc)
        return ""


def traduire(texte: str, vers: str, depuis: str = "") -> str:
    """Texte traduit, ou "" si la traduction n'a pas pu être obtenue.

    Ne lève jamais : l'appelant envoie le message d'origine en cas d'échec.
    """
    texte = (texte or "").strip()
    if not texte or not vers or len(texte) > MAX_CARACTERES:
        return ""
    if depuis and depuis == vers:
        return ""

    cle = (texte, vers, depuis)
    with _cache_lock:
        if cle in _cache:
            return _cache[cle]

    resultat = _deepl(texte, vers, depuis) or _google_public(texte, vers, depuis)
    if resultat and resultat.strip().casefold() == texte.casefold():
        resultat = ""          # rien n'a changé : inutile de le stocker

    with _cache_lock:
        if len(_cache) >= _CACHE_MAX:
            _cache.clear()
        _cache[cle] = resultat
    return resultat

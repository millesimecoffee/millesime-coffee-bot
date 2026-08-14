"""
Serveur Flask — Mini App Telegram (catalogue + selfie + détection visage OpenCV).
Tourne dans un thread en parallèle du bot Telegram.
"""
import base64
import hashlib
import hmac
import importlib
import logging
import os
import threading
import time

import cv2
import numpy as np
from flask import Flask, jsonify, render_template, request

import chat

logger = logging.getLogger(__name__)

# Les URL de l'API Telegram contiennent le token du bot : httpx les journalise
# en INFO, ce qui met le token en clair dans les logs. Utile aussi quand webapp
# est lancé seul (run_webapp_dev.py), sans passer par la config de bot.py.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB max (selfie)

# Cap dimensions image pour éviter les bombes décompression (50000x50000 → 7 GB RAM)
_MAX_IMAGE_PIXELS = 5_000_000  # 5 MP — largement suffisant pour un selfie

# Une commande peut être annulée par l'owner ou par le client dans sa fenêtre de
# 2 min. Les deux statuts doivent être traités ensemble partout (CA, compteurs,
# filtres), sinon les annulations client échappent au panel.
_CANCELLED_STATUSES = ("cancelled", "cancelled_by_client")


try:
    from zoneinfo import ZoneInfo
    _PARIS = ZoneInfo("Europe/Paris")
except Exception:          # tzdata absent : on retombe sur l'heure du serveur
    _PARIS = None


def _jour_paris(iso_str):
    """Date calendaire d'une commande, à l'heure de Paris.

    Les commandes sont horodatées en UTC. Découper les journées sur l'heure
    du serveur ferait basculer « aujourd'hui » à 1 h ou 2 h du matin, en plein
    service : une commande de minuit et demi tomberait dans la veille.
    """
    dt = _parse_dt(iso_str)
    if dt is None:
        return None
    return (dt.astimezone(_PARIS) if _PARIS else dt.astimezone()).date()


def _ignorer_owner(uid) -> bool:
    """Faut-il taire les notifications de parcours quand c'est l'owner qui
    navigue ? Non par défaut : sinon il ne peut pas tester sa propre boutique
    et croit le système en panne. Passer NOTIF_IGNORER_OWNER=1 pour retrouver
    le silence si ses propres visites deviennent bruyantes."""
    if os.getenv("NOTIF_IGNORER_OWNER", "").strip().lower() not in ("1", "true", "oui"):
        return False
    owner_uid = os.getenv("OWNER_USER_ID", "").strip()
    return bool(owner_uid) and str(uid) == owner_uid


def _corps(req) -> dict:
    """Corps JSON de la requête, toujours sous forme de dictionnaire.

    `request.get_json()` renvoie ce que contient le corps : sur `"texte"`,
    `[]` ou `12`, ce n'est pas un dict et le `.get()` qui suit lève
    AttributeError — y compris dans le contrôle d'authentification, donc sur
    tous les endpoints à la fois.
    """
    try:
        data = req.get_json(force=True, silent=True)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _texte(valeur, maxi: int = 4000) -> str:
    """Convertit une valeur reçue du client en chaîne propre.

    Un `.strip()` appliqué directement au champ lève AttributeError dès qu'il
    n'est pas une chaîne (liste, nombre, objet JSON) : réponse 500. Ici tout
    devient du texte, tronqué à `maxi`.
    """
    if valeur is None or isinstance(valeur, (list, dict, tuple, set, bool)):
        return ""
    if not isinstance(valeur, str):
        valeur = str(valeur)
    return valeur.strip()[:maxi]


def _entier(valeur, defaut: int, mini: int, maxi: int) -> int:
    """Convertit une valeur reçue du client en entier borné.

    Sans ce garde-fou, `int(data["limit"])` lève une exception sur "abc" ou
    null (réponse 500), et une valeur négative découpe la liste à l'envers :
    `orders[:-5]` masque silencieusement les 5 commandes les plus récentes.
    """
    if isinstance(valeur, bool) or isinstance(valeur, (list, dict, tuple, set)):
        return defaut
    try:
        n = int(valeur)
    except (TypeError, ValueError):
        return defaut
    return max(mini, min(maxi, n))


def _telegram_error(resp) -> str:
    """Extrait la description d'erreur d'une réponse Bot API."""
    try:
        body = resp.json() or {}
        return str(body.get("description") or body)[:200]
    except Exception:
        return f"HTTP {getattr(resp, 'status_code', '?')}"


def _now_aware():
    """Maintenant, toujours timezone-aware."""
    from datetime import datetime as _dt
    return _dt.now().astimezone()


def _now_iso() -> str:
    """Horodatage ISO *avec* décalage UTC. Un ISO naïf est relu comme de l'heure
    locale par le navigateur alors que le serveur tourne en UTC : les durées
    affichées dans le panel owner seraient décalées d'autant."""
    return _now_aware().isoformat(timespec="seconds")


def _parse_dt(iso_str):
    """Relit un horodatage stocké, naïf (anciennes commandes) ou aware (récentes),
    et renvoie toujours un datetime aware — sinon toute soustraction lève un
    TypeError « can't subtract offset-naive and offset-aware datetimes »."""
    if not iso_str:
        return None
    from datetime import datetime as _dt
    try:
        dt = _dt.fromisoformat(str(iso_str))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt


@app.after_request
def _security_headers(response):
    """En-têtes de sécurité + bypass ngrok.
    NB : on ne met PAS X-Frame-Options (la Mini App tourne dans l'iframe
    Telegram). La caméra sert au selfie, le micro aux messages vocaux de la
    messagerie : sans microphone=(self), MediaRecorder est bloqué dans
    l'iframe et l'enregistrement échoue sans message d'erreur."""
    response.headers["ngrok-skip-browser-warning"] = "true"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(self), geolocation=(self)"
    response.headers["Cross-Origin-Resource-Policy"] = "same-site"
    return response


@app.route("/")
def root():
    """Health endpoint pour keep-alive Render + check uptime."""
    return "ok", 200


@app.route("/health")
def health():
    return {"ok": True}, 200


# ═══════════════════════════════════════════════════════════════════════════
# MINI APP — Catalogue interactif
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/menu")
def menu_page():
    """Point d'entrée de la Mini App.

    On trace comment la page a été ouverte : un `initData` absent vient
    presque toujours de là — page ouverte dans le navigateur du téléphone au
    lieu du webview Telegram, auquel cas il n'y a aucune session à valider.
    """
    ua = (request.headers.get("User-Agent") or "")[:180]
    logger.info("Mini App ouverte — UA=%r referer=%r site=%r",
                ua,
                (request.headers.get("Referer") or "")[:120],
                request.headers.get("Sec-Fetch-Site") or "")
    return render_template("menu.html", bot_username=_bot_username())


@app.route("/api/diag", methods=["POST"])
def api_diag():
    """Ce que la Mini App voit de son côté, pour diagnostiquer une session
    absente sans avoir à demander des captures d'écran."""
    d = _corps(request)
    logger.info(
        "Diag Mini App — plateforme=%s version=%s initData=%s longueur=%s "
        "user=%s host=%s",
        _texte(d.get("platform"), 30) or "?",
        _texte(d.get("version"), 20) or "?",
        "present" if d.get("has_init") else "ABSENT",
        _entier(d.get("len"), 0, 0, 100000),
        "oui" if d.get("has_user") else "non",
        _texte(d.get("href"), 200) or "?",
    )
    return jsonify({"ok": True})


# ── Photos de ville : fichiers commités + fetch auto Pexels si manquant ──
_city_cache_dir_v = None
_city_fetch_lock = threading.Lock()
_city_fetching: set = set()


def _city_cache_dir():
    global _city_cache_dir_v
    if _city_cache_dir_v is None:
        import tempfile
        base = os.getenv("DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
        d = os.path.join(base, "cityimg_cache")
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            d = os.path.join(tempfile.gettempdir(), "mc_cityimg_cache")
            os.makedirs(d, exist_ok=True)
        _city_cache_dir_v = d
    return _city_cache_dir_v


def _slug_to_city_query(slug: str) -> str:
    """Retrouve le nom de ville (+ pays) depuis le slug, via le catalogue."""
    import unicodedata, re as _re
    def _sl(s):
        return _re.sub(r"[^a-z0-9]+", "", unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower())
    try:
        import catalog as catalog_mod
        importlib.reload(catalog_mod)
        for country, cities in catalog_mod.CATALOG.items():
            for city in cities:
                if _sl(city) == slug:
                    cc = country.split(" ", 1)[1].strip() if " " in country else country
                    return f"{city} {cc}".strip()
    except Exception:
        pass
    return slug


def _fetch_city_pexels(slug: str, dest_path: str) -> bool:
    """Télécharge une belle photo de la ville via Pexels, recadre 1200x675, sauvegarde."""
    key = os.getenv("PEXELS_API_KEY", "").strip()
    if not key:
        return False
    query = _slug_to_city_query(slug)
    import httpx as _httpx
    try:
        with _httpx.Client(timeout=15.0) as c:
            r = c.get(
                "https://api.pexels.com/v1/search",
                headers={"Authorization": key},
                params={"query": query, "per_page": 6, "orientation": "landscape", "size": "large"},
            )
            if r.status_code != 200:
                logger.warning("pexels search %s: HTTP %s", slug, r.status_code)
                return False
            photos = (r.json() or {}).get("photos", []) or []
            for p in photos:
                if int(p.get("width", 0)) < 1200:
                    continue
                src = (p.get("src") or {}).get("large2x") or (p.get("src") or {}).get("large")
                if not src:
                    continue
                img_resp = c.get(src)  # CDN : pas d'en-tête d'auth
                if img_resp.status_code != 200:
                    continue
                arr = np.frombuffer(img_resp.content, np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if img is None or min(img.shape[:2]) < 400:
                    continue
                h, w = img.shape[:2]
                W, H = 1200, 675
                tar, cur = W / H, w / h
                if cur > tar:
                    nw = int(h * tar); x0 = (w - nw) // 2; img = img[:, x0:x0 + nw]
                else:
                    nh = int(w / tar); y0 = (h - nh) // 2; img = img[y0:y0 + nh, :]
                img = cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA)
                # NB : cv2.imwrite refuse l'extension ".tmp" → on encode puis on écrit
                ok_enc, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 88])
                if ok_enc:
                    tmp = dest_path + ".tmp"
                    with open(tmp, "wb") as f:
                        f.write(buf.tobytes())
                    os.replace(tmp, dest_path)
                    logger.info("pexels auto-photo OK: %s (%s)", slug, query)
                    return True
    except Exception as exc:
        logger.warning("pexels fetch %s: %s", slug, exc)
    return False


@app.route("/cityimg/<slug>.jpg")
def serve_city_image(slug):
    """Sert une photo de ville. 1) fichier commité, 2) cache runtime,
    3) fetch auto Pexels (si PEXELS_API_KEY) puis cache. Sinon 404 (repli
    synthwave côté client)."""
    import re as _re
    from flask import send_file
    if not _re.fullmatch(r"[a-z0-9]{1,40}", slug or ""):
        return ("bad request", 400)

    committed = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cityimg", slug + ".jpg")
    if os.path.exists(committed):
        path = committed
    else:
        cached = os.path.join(_city_cache_dir(), slug + ".jpg")
        if not os.path.exists(cached):
            # Éviter les fetch concurrents pour le même slug
            with _city_fetch_lock:
                busy = slug in _city_fetching
                if not busy:
                    _city_fetching.add(slug)
            if busy:
                return ("fetching", 404)
            try:
                ok = _fetch_city_pexels(slug, cached)
            finally:
                with _city_fetch_lock:
                    _city_fetching.discard(slug)
            if not ok:
                return ("not found", 404)
        path = cached

    resp = send_file(path, mimetype="image/jpeg")
    resp.headers["Cache-Control"] = "public, max-age=604800"
    return resp


# Anti-spam très simple : mémorise les essais par IP + user_id
_pwd_attempts: dict[str, list[float]] = {}
_PWD_MAX_ATTEMPTS = 5
_PWD_WINDOW      = 300  # 5 min
_pwd_lock = threading.Lock()

# ── Sécurité : anti-rejeu initData + IP client fiable + rate-limit générique ──
# Un initData Telegram capturé ne doit pas rester valide indéfiniment.
# 24h par défaut : assez large pour ne pas couper une session, assez court
# pour tuer un rejeu d'un vieux jeton. Réglable via env (0 = désactivé).
_INITDATA_MAX_AGE = int(os.getenv("INITDATA_MAX_AGE", "86400"))

# Nombre de proxys de confiance devant l'app (Render = 1). Sert à extraire
# l'IP client réelle sans se faire spoofer par un X-Forwarded-For client.
_TRUSTED_PROXY_HOPS = int(os.getenv("TRUSTED_PROXY_HOPS", "1"))

# Rate-limiter générique en mémoire : {clé: [timestamps]}
_rate_store: dict[str, list[float]] = {}
_rate_lock = threading.Lock()


def _client_ip(req) -> str:
    """IP client fiable. X-Forwarded-For = 'client_spoofé…, IP_réelle_ajoutée_par_proxy'.
    Les entrées de droite sont ajoutées par nos proxys de confiance et ne sont
    pas contrôlables par le client → on prend l'IP à `_TRUSTED_PROXY_HOPS` du bout.
    """
    xff = req.headers.get("X-Forwarded-For", "")
    if xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            idx = len(parts) - _TRUSTED_PROXY_HOPS
            if 0 <= idx < len(parts):
                return parts[idx]
            return parts[-1]
    return req.remote_addr or "?"


def _rate_limited(key: str, max_hits: int, window: float) -> bool:
    """True si `key` a dépassé max_hits sur la fenêtre glissante. Enregistre le hit."""
    now = time.time()
    with _rate_lock:
        recent = [t for t in _rate_store.get(key, []) if now - t < window]
        recent.append(now)
        _rate_store[key] = recent
        # Nettoyage opportuniste pour éviter la croissance mémoire illimitée
        if len(_rate_store) > 5000:
            for k in list(_rate_store.keys()):
                if not any(now - t < window for t in _rate_store[k]):
                    del _rate_store[k]
        return len(recent) > max_hits


def _rate_reset(key: str) -> None:
    """Efface le compteur d'une clé. Sert après une authentification réussie :
    sans ça, les déverrouillages légitimes s'accumulent avec les échecs et
    l'owner finit par se bloquer lui-même en rouvrant l'app."""
    with _rate_lock:
        _rate_store.pop(key, None)


# Throttle des notifications "client entre dans le catalogue" :
# évite de spammer l'owner si l'user ouvre/ferme plusieurs fois.
_entry_notif_last: dict[int, float] = {}
_ENTRY_NOTIF_COOLDOWN = 600  # 10 min entre 2 notifs pour le même user
_entry_notif_lock = threading.Lock()


def _notify_owner_client_entry(parsed_init: dict) -> None:
    """Envoie au owner une notif courte 'Client X est entré dans le catalogue'.
    Auto-throttled : pas plus d'1 notif / 10 min par user.
    """
    bot_token  = os.getenv("BOT_TOKEN", "")
    owner_chat = os.getenv("OWNER_CHAT_ID", "")
    if not (bot_token and owner_chat):
        return
    try:
        import json as _json
        user_obj = _json.loads(parsed_init.get("user", "{}"))
        uid      = int(user_obj.get("id", 0))
        if not uid:
            return
        if _ignorer_owner(uid):
            return

        # Throttle
        now = time.time()
        with _entry_notif_lock:
            last = _entry_notif_last.get(uid, 0)
            if now - last < _ENTRY_NOTIF_COOLDOWN:
                return
            _entry_notif_last[uid] = now

        first_name = (user_obj.get("first_name") or "").strip()
        username   = (user_obj.get("username")   or "").strip()
        lang_code  = (user_obj.get("language_code") or "").upper()[:2]

        # Lien deeplink chat avec le client (uniquement si username)
        deeplink = f"tg://resolve?domain={username}" if username else ""

        # Échapper pour HTML
        def esc(s):
            return (str(s or "")
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;"))

        who = f"@{esc(username)}" if username else esc(first_name) or f"id_{uid}"
        msg = (
            f"👀 <b>{who}</b> vient d'entrer dans le catalogue\n"
            f"   <i>ID:</i> <code>{uid}</code>"
            + (f"  ·  🌐 {lang_code}" if lang_code else "")
        )

        # Même événement sur Pushover. Priorité basse : une entrée n'est pas une
        # commande, elle ne doit pas déclencher la même alerte.
        try:
            import pushover
            pushover.entree_shop()
        except Exception as exc:
            logger.warning("Pushover (entree) ignore : %s", exc)

        import httpx as _httpx
        with _httpx.Client(timeout=8.0) as c:
            c.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id":    owner_chat,
                    "text":       msg,
                    "parse_mode": "HTML",
                    "disable_notification": False,
                    "disable_web_page_preview": True,
                },
            )
    except Exception as exc:
        logger.warning("notify owner entry: %s", exc)


# Anti-répétition des notifications de ville : une seule par couple
# (client, ville) sur la fenêtre. Mémoriser seulement la *dernière* ville ne
# suffirait pas — un client qui fait des allers-retours entre deux villes
# déclencherait une notification à chaque bascule.
_VILLE_COOLDOWN = 180   # 3 min


@app.route("/api/notify/city", methods=["POST"])
def api_notify_city():
    """Signale à l'owner le pays, puis la ville, retenus par un client.
    POST {initData, country, city?}

    Deux notifications distinctes, car un client peut s'arrêter au pays. Le
    serveur décide laquelle envoyer : la recherche de ville court-circuite
    l'écran des pays, et sans cette logique le pays ne serait jamais annoncé.

    Le couple pays/ville est validé contre le catalogue avant tout envoi :
    sans ce contrôle, n'importe qui pourrait faire arriver le texte de son
    choix dans les notifications de l'owner.
    """
    bot_token = os.getenv("BOT_TOKEN", "")
    data = _corps(request)

    parsed = _verify_init_data(data.get("initData", ""), bot_token)
    if not parsed:
        return jsonify({"ok": False, "error": "auth_failed"}), 401

    import json as _json
    try:
        user_obj = _json.loads(parsed.get("user", "{}"))
        uid = int(user_obj.get("id", 0))
    except Exception:
        return jsonify({"ok": False, "error": "no_user"}), 400
    if not uid:
        return jsonify({"ok": False, "error": "no_user"}), 400

    if _ignorer_owner(uid):
        return jsonify({"ok": True, "skipped": "owner"})

    country = _texte(data.get("country"))
    city    = _texte(data.get("city"))
    try:
        import catalog as catalog_mod
        importlib.reload(catalog_mod)
        if country not in catalog_mod.CATALOG:
            return jsonify({"ok": False, "error": "unknown_country"}), 400
        if city and city not in catalog_mod.CATALOG[country]:
            return jsonify({"ok": False, "error": "unknown_city"}), 400
    except Exception:
        return jsonify({"ok": False, "error": "catalog_failed"}), 500

    import pushover
    envoyes = []
    owner_chat = os.getenv("OWNER_CHAT_ID", "")

    def _telegram(texte: str) -> None:
        if not (bot_token and owner_chat):
            return
        try:
            import httpx as _httpx
            _httpx.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": owner_chat, "text": texte,
                      "disable_web_page_preview": True},
                timeout=8.0,
            )
        except Exception as exc:
            logger.warning("notif parcours Telegram : %s", exc)

    # Anti-répétition : les allers-retours entre écrans ne doivent pas spammer.
    # _rate_limited gère déjà la fenêtre glissante et le nettoyage mémoire.
    if not _rate_limited(f"pays:{uid}:{country}", 1, _VILLE_COOLDOWN):
        try:
            pushover.pays_choisi(country)
            envoyes.append("country")
            drapeau, nom = pushover._separer_drapeau(country)
            prep = pushover._PREPOSITION_PAYS.get(nom, "EN")
            _telegram(f"UN CLIENT VEUX COMMANDER {prep} {nom} {drapeau}".strip())
        except Exception as exc:
            logger.warning("Pushover (pays) ignore : %s", exc)

    if city and not _rate_limited(f"ville:{uid}:{city}", 1, _VILLE_COOLDOWN):
        try:
            pushover.ville_choisie(city, country)
            envoyes.append("city")
            drapeau, _ = pushover._separer_drapeau(country)
            _telegram(f"UN CLIENT VEUX COMMANDER À {city.upper()} {drapeau}".strip())
        except Exception as exc:
            logger.warning("Pushover (ville) ignore : %s", exc)

    # Le livreur de la zone est prévenu qu'un client regarde chez lui : il peut
    # se tenir prêt. Même anti-répétition que pour l'owner.
    if city and _dans_zone_livreur({"country": country, "city": city}):
        drapeau, _ = pushover._separer_drapeau(country)
        if _prevenir_livreur(
                f"👀 Un client consulte le catalogue <b>{_html_escape(city)}</b> "
                f"{drapeau}\nTenez-vous prêt.",
                cle_anti_repetition=f"lv:vue:{uid}:{city}"):
            envoyes.append("livreur")

    return jsonify({"ok": True, "sent": envoyes})


@app.route("/api/auth", methods=["POST"])
def api_auth():
    """Vérifie le mot de passe et retourne le catalogue.
    Throttle 5 essais / 5 min par IP.
    """
    expected = os.getenv("BOT_PASSWORD", "")
    if not expected:
        return jsonify({"ok": False, "error": "no_password_configured"}), 500

    bot_token = os.getenv("BOT_TOKEN", "")
    data = _corps(request)

    # 1) Exiger un initData Telegram AUTHENTIQUE : seul un vrai client Telegram
    #    (impossible à forger sans le bot token) peut tenter le mot de passe.
    #    Bloque tout accès script/navigateur direct hors de l'app Telegram.
    #    Deux refus bien distincts, car ils n'ont pas le même remède :
    #      - session absente : la boutique n'a pas été lancée comme Mini App
    #        (lien ouvert dans le navigateur interne de Telegram). Rouvrir ne
    #        sert à rien, il faut repasser par le bouton CATALOGUE.
    #      - session présente mais refusée : signature périmée ou invalide,
    #        là il faut refermer et rouvrir.
    init_recu = _texte(data.get("initData"), 4096)
    parsed = _verify_init_data(init_recu, bot_token)
    if not parsed:
        time.sleep(0.4)
        code = "no_session" if not init_recu else "auth_failed"
        return jsonify({"ok": False, "error": code}), 401

    # Identité vérifiée → rate-limit par user_id (non spoofable) ET par IP réelle
    import json as _json
    try:
        uid = str(int(_json.loads(parsed.get("user", "{}")).get("id", 0)))
    except Exception:
        uid = ""
    ip  = _client_ip(request)
    now = time.time()
    keys = {f"pwd:ip:{ip}"}
    if uid:
        keys.add(f"pwd:uid:{uid}")

    with _pwd_lock:
        # Purge des clés périmées : une entrée par IP visiteuse s'accumulerait
        # sinon indéfiniment dans un processus qui tourne des mois.
        if len(_pwd_attempts) > 2000:
            for k in [k for k, v in _pwd_attempts.items()
                      if not any(now - t < _PWD_WINDOW for t in v)]:
                del _pwd_attempts[k]
        for k in keys:
            recent = [t for t in _pwd_attempts.get(k, []) if now - t < _PWD_WINDOW]
            _pwd_attempts[k] = recent
            if len(recent) >= _PWD_MAX_ATTEMPTS:
                return jsonify({"ok": False, "blocked": True, "error": "rate_limited"})

    pwd = _texte(data.get("password"), 200)

    # Une seule porte d'entrée, deux mots de passe. Le mot de passe admin est
    # testé en premier : il ouvre le panel depuis n'importe quel compte et
    # n'importe quel téléphone, c'est lui qui donne le droit, pas l'identité.
    mdp_admin = _admin_password()
    est_admin = bool(mdp_admin) and hmac.compare_digest(
        _normalise_mdp(pwd), _normalise_mdp(mdp_admin))

    # Puis celui du livreur : même principe, mais il n'ouvre que les courses
    # de sa zone, sans aucune identité de client.
    mdp_livreur = _livreur_password()
    est_livreur = (not est_admin and bool(mdp_livreur) and hmac.compare_digest(
        _normalise_mdp(pwd), _normalise_mdp(mdp_livreur)))

    if (not est_admin and not est_livreur
            and (not pwd or _normalise_mdp(pwd) != _normalise_mdp(expected))):
        with _pwd_lock:
            for k in keys:
                _pwd_attempts.setdefault(k, []).append(now)
        time.sleep(0.5)  # léger throttle pour ralentir le brute force
        return jsonify({"ok": False, "error": "wrong_password"})

    if est_admin and uid:
        with _admin_lock:
            _admin_unlocked[uid] = time.time() + _ADMIN_SESSION_TTL
        logger.info("panel admin ouvert par mot de passe pour %s", uid)

    if est_livreur and uid:
        with _livreur_lock:
            _livreur_unlocked[uid] = time.time() + _ADMIN_SESSION_TTL
        # Sa première connexion suffit à l'inscrire : plus besoin de relever
        # son identifiant Telegram à la main pour lui envoyer les courses.
        _retenir_livreur(uid)
        logger.info("panel livreur ouvert pour %s (zones %s)", uid, _zones_livreur())

    # OK — recharger le catalogue (au cas où on l'aurait modifié)
    try:
        import catalog as catalog_mod
        importlib.reload(catalog_mod)
        resp = {
            "ok":         True,
            "admin":      est_admin,   # la Mini App bascule direct sur le panel
            "livreur":    est_livreur, # … ou sur les courses de sa zone
            "catalog":    catalog_mod.CATALOG,
            "min_orders": catalog_mod.MIN_ORDER,
            "currencies": catalog_mod.CURRENCIES,
            "country_currencies": {c: catalog_mod.get_currencies(c) for c in catalog_mod.CATALOG},
            # Contact vendeur/support pour le bouton "Nous contacter" (tracking client)
            # Défaut = @millesimecoffee (username public), surchargeable via env.
            "support": {
                "username": (os.getenv("SUPPORT_USERNAME", "") or "millesimecoffee").lstrip("@").strip(),
                "user_id":  os.getenv("OWNER_USER_ID", "").strip(),
            },
            "payment_config": {
                "payment_link": os.getenv("PAYMENT_LINK", ""),
                "crypto_eth":   os.getenv("CRYPTO_ETH", ""),
                "crypto_usdt":  os.getenv("CRYPTO_USDT", ""),
            },
        }
        # Notif owner : "client entré dans le catalogue" (si initData valide)
        bot_token = os.getenv("BOT_TOKEN", "")
        init_data = (data or {}).get("initData", "") if isinstance(data, dict) else ""
        parsed = _verify_init_data(init_data, bot_token) if init_data else None
        # Une entrée par le mot de passe admin ou livreur n'est pas une visite
        # client : elle ne doit pas déclencher « UN CLIENT EST ENTRÉE DANS LE
        # SHOP », sinon l'owner serait notifié à chaque connexion de son livreur.
        if parsed and not est_admin and not est_livreur:
            try:
                _notify_owner_client_entry(parsed)
            except Exception:
                pass
        return jsonify(resp)
    except Exception as exc:
        logger.error("api_auth catalog: %s", exc)
        return jsonify({"ok": False, "error": "catalog_load_failed"}), 500


@app.route("/api/catalog", methods=["GET"])
def api_catalog():
    """Retourne le catalogue actuel (utile pour rafraîchir sans rechecker le mdp)."""
    try:
        import catalog as catalog_mod
        importlib.reload(catalog_mod)
        return jsonify({
            "catalog":    catalog_mod.CATALOG,
            "min_orders": catalog_mod.MIN_ORDER,
            "currencies": catalog_mod.CURRENCIES,
            "country_currencies": {c: catalog_mod.get_currencies(c) for c in catalog_mod.CATALOG},
        })
    except Exception as exc:
        logger.error("api_catalog: %s", exc)
        return jsonify({"error": "load_failed"}), 500


# Cart en attente entre la Mini App et le clic paiement dans le chat
# Clé : user_id (str). Expire après 1h.
_pending_carts: dict[str, dict] = {}
_pending_lock = threading.Lock()
_PENDING_TTL  = 3600  # 1h


def get_pending_cart(user_id: str) -> dict | None:
    """Lit (et conserve) le panier en attente pour un user_id donné."""
    with _pending_lock:
        item = _pending_carts.get(str(user_id))
        if not item:
            return None
        if time.time() - item["ts"] > _PENDING_TTL:
            _pending_carts.pop(str(user_id), None)
            return None
        return item


def pop_pending_cart(user_id: str) -> dict | None:
    """Consomme le panier en attente pour un user_id (le supprime ensuite)."""
    with _pending_lock:
        return _pending_carts.pop(str(user_id), None)


def _verify_init_data(init_data: str, bot_token: str) -> dict | None:
    """Valide l'initData Telegram via HMAC-SHA256.
    Retourne le dict des champs si valide, None sinon.
    Voir https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    import hashlib
    import hmac
    from urllib.parse import parse_qsl

    # Chaque refus est tracé avec sa raison : sans ça, une session Telegram
    # périmée et un mauvais mot de passe se ressemblent dans les logs, et on
    # cherche le problème du mauvais côté.
    if not init_data:
        logger.info("initData rejeté : absent (Mini App ouverte hors Telegram ?)")
        return None
    if not bot_token:
        logger.error("initData rejeté : BOT_TOKEN absent côté serveur")
        return None
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=False))
        their_hash = pairs.pop("hash", "")
        if not their_hash:
            logger.info("initData rejeté : signature absente")
            return None
        # Data-check-string : trier alphabétiquement et joindre par \n
        dcs = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
        secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        my_hash = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(my_hash, their_hash):
            logger.info("initData rejeté : signature invalide (token du bot changé ?)")
            return None
        # Anti-rejeu : refuser un initData trop ancien (jeton capturé/rejoué)
        if _INITDATA_MAX_AGE > 0:
            try:
                auth_date = int(pairs.get("auth_date", "0"))
            except (ValueError, TypeError):
                auth_date = 0
            age = time.time() - auth_date if auth_date > 0 else -1
            if auth_date <= 0 or age > _INITDATA_MAX_AGE:
                logger.info("initData rejeté : session ouverte il y a %.0f h (max %.0f h)",
                            age / 3600 if age > 0 else -1, _INITDATA_MAX_AGE / 3600)
                return None
        return pairs
    except Exception as exc:
        logger.warning("verify_init_data exception: %s", exc)
    return None


@app.route("/api/submit_cart", methods=["POST"])
def api_submit_cart():
    """Reçoit le panier final de la Mini App.
    Valide initData → user_id authentique → stocke + envoie message paiement.
    """
    data = _corps(request)
    if not data:
        return jsonify({"ok": False, "error": "bad_json"}), 400

    bot_token = os.getenv("BOT_TOKEN", "")
    init_data = data.get("initData", "")
    parsed = _verify_init_data(init_data, bot_token)
    if not parsed:
        return jsonify({"ok": False, "error": "auth_failed"}), 401

    # Extraire user_id de l'objet user JSON dans initData
    try:
        import json as _json
        user_obj = _json.loads(parsed.get("user", "{}"))
        user_id  = int(user_obj.get("id", 0))
    except Exception:
        return jsonify({"ok": False, "error": "no_user"}), 400
    if not user_id:
        return jsonify({"ok": False, "error": "no_user"}), 400

    # Charger catalogue serveur pour valider
    try:
        import catalog as catalog_mod
        importlib.reload(catalog_mod)
    except Exception as exc:
        logger.error("submit_cart catalog: %s", exc)
        return jsonify({"ok": False, "error": "catalog_failed"}), 500

    lang    = data.get("lang", "fr") if data.get("lang") in ("fr","es","en") else "fr"
    country = data.get("country", "")
    city    = data.get("city", "")
    cart    = data.get("cart", {}) or {}

    if country not in catalog_mod.CATALOG or city not in catalog_mod.CATALOG.get(country, {}):
        return jsonify({"ok": False, "error": "bad_location"}), 400

    products = catalog_mod.CATALOG[country][city]
    total = 0.0
    safe_cart = {}
    for prod, qty in cart.items():
        try:
            q = int(qty)
        except (ValueError, TypeError):
            continue
        if q <= 0 or q > 99 or prod not in products:
            continue
        safe_cart[prod] = q
        total += products[prod] * q

    if not safe_cart:
        return jsonify({"ok": False, "error": "empty_cart"}), 400

    # Vérifier min
    min_order = catalog_mod.MIN_ORDER.get(city)
    if min_order:
        if min_order["type"] == "amount" and total < min_order["value"]:
            return jsonify({"ok": False, "error": f"Minimum {min_order['value']} €"}), 400
        if min_order["type"] == "qty":
            tot_q = sum(safe_cart.values())
            if tot_q < min_order["value"]:
                return jsonify({"ok": False, "error": f"Minimum {min_order['value']} articles"}), 400

    # OK — stocker pour récupération par le bot quand l'user clique le paiement
    with _pending_lock:
        _pending_carts[str(user_id)] = {
            "lang":    lang,
            "country": country,
            "city":    city,
            "cart":    safe_cart,
            "total":   total,
            "ts":      time.time(),
        }

    # Envoyer un message Telegram au user avec les boutons de paiement
    # On utilise l'API Bot directement depuis Flask
    import httpx
    label_count = sum(safe_cart.values())
    msg_text = (
        f"✅ *Panier reçu !*\n\n"
        f"🏙️ {city} — {label_count} article(s) — *{total:,.0f} €*\n\n"
        f"Choisissez votre mode de paiement :"
    )
    # Boutons paiement (callback_data spéciaux pour notre nouveau entry_point)
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "💵 Cash",  "callback_data": "mapay:cash"},
                {"text": "💳 Lien",  "callback_data": "mapay:link"},
            ],
            [
                {"text": "₿ Crypto", "callback_data": "mapay:crypto"},
            ],
            [
                {"text": "❌ Annuler", "callback_data": "mapay:cancel"},
            ],
        ]
    }
    try:
        r = httpx.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={
                "chat_id":      user_id,
                "text":         msg_text,
                "parse_mode":   "Markdown",
                "reply_markup": keyboard,
            },
            timeout=10.0,
        )
        if r.status_code != 200:
            logger.warning("submit_cart sendMessage failed: %s %s", r.status_code, r.text[:200])
            return jsonify({"ok": False, "error": "telegram_send_failed"}), 502
    except Exception as exc:
        logger.error("submit_cart sendMessage exception: %s", exc)
        return jsonify({"ok": False, "error": "telegram_send_failed"}), 502

    return jsonify({"ok": True, "message": "Panier envoyé, choisissez votre paiement dans le chat."})


# ═══════════════════════════════════════════════════════════════════════════
# Détection visage selfie (depuis la Mini App)
# ═══════════════════════════════════════════════════════════════════════════

def _decode_b64_image(photo_b64: str):
    """Décode une data-URL base64 → (img_array, photo_bytes) ou (None, None) si erreur."""
    if not photo_b64:
        return None, None
    if "," in photo_b64:
        photo_b64 = photo_b64.split(",", 1)[1]
    photo_b64 = photo_b64.strip().replace("\n", "").replace("\r", "").replace(" ", "")
    pad = len(photo_b64) % 4
    if pad:
        photo_b64 += "=" * (4 - pad)
    try:
        photo_bytes = base64.b64decode(photo_b64)
    except Exception:
        return None, None
    if len(photo_bytes) < 100:
        return None, None
    arr = np.frombuffer(photo_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return None, None
    h, w = img.shape[:2]
    if h * w > _MAX_IMAGE_PIXELS:
        return None, None
    return img, photo_bytes


@app.route("/api/check_face", methods=["POST"])
def api_check_face():
    """Détecte un visage dans la photo Mini App. Auth via initData."""
    data = _corps(request)
    if not data:
        return jsonify({"ok": False, "error": "bad_json"}), 400

    bot_token = os.getenv("BOT_TOKEN", "")
    if not _verify_init_data(data.get("initData", ""), bot_token):
        return jsonify({"ok": False, "error": "auth_failed"}), 401

    img, _ = _decode_b64_image(data.get("photo", ""))
    if img is None:
        return jsonify({"ok": False, "error": "image_invalid"})

    gray  = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = _face_cascade.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60)
    )
    if len(faces) == 0:
        return jsonify({"ok": False, "error": "no_face"})

    return jsonify({"ok": True})


# ═══════════════════════════════════════════════════════════════════════════
# Geocoding adresse (Nominatim) — depuis la Mini App
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/geocode", methods=["POST"])
def api_geocode():
    """Geocode une adresse via OpenStreetMap Nominatim. Retourne format court + lat/lon."""
    data = _corps(request)
    if not data:
        return jsonify({"ok": False, "error": "bad_json"}), 400

    address = _texte(data.get("address"))
    if not address:
        return jsonify({"ok": False, "error": "empty"}), 400

    country = data.get("country", "") or ""
    city    = data.get("city", "")    or ""
    # Enlever le drapeau du pays
    country_clean = country.split(" ", 1)[1].strip() if " " in country else country

    def _search(query: str):
        try:
            import httpx as _httpx
            r = _httpx.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": query, "format": "json", "limit": 1, "addressdetails": 1},
                headers={"User-Agent": "MillesimeCoffeeBot/1.0"},
                timeout=10.0,
            )
            if r.status_code != 200:
                return None
            results = r.json()
            return results[0] if results else None
        except Exception as exc:
            logger.warning("geocode network: %s", exc)
            return "network_error"

    # 1re passe : adresse brute
    res = _search(address)
    # 2e passe : ajouter contexte ville/pays
    if res is None and (city or country_clean):
        ctx = ", ".join([p for p in [address, city, country_clean] if p])
        res = _search(ctx)

    if res == "network_error":
        return jsonify({"ok": False, "error": "service_down"})

    if not res:
        return jsonify({
            "ok":       True,
            "verified": False,
            "formatted": address,
            "short":    address,
        })

    addr_obj = res.get("address", {}) or {}
    number   = (addr_obj.get("house_number") or "").strip()
    road     = (addr_obj.get("road") or addr_obj.get("pedestrian")
                or addr_obj.get("footway") or addr_obj.get("street")
                or addr_obj.get("place") or "").strip()
    city_val = (addr_obj.get("city") or addr_obj.get("town")
                or addr_obj.get("village") or addr_obj.get("municipality")
                or addr_obj.get("district") or addr_obj.get("county") or "").strip()
    postcode = (addr_obj.get("postcode") or "").strip()
    line1 = f"{number} {road}".strip().upper() if road else ""
    line2 = city_val.upper()
    short_parts = [p for p in [line1, line2, postcode] if p]
    short_addr  = "\n".join(short_parts) if short_parts else res.get("display_name", address)

    lat = res.get("lat")
    lon = res.get("lon")
    maps_link = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}&zoom=17" if lat and lon else ""

    return jsonify({
        "ok":        True,
        "verified":  True,
        "formatted": res.get("display_name", address),
        "short":     short_addr,
        "lat":       lat,
        "lon":       lon,
        "maps_link": maps_link,
    })


def _photon_candidate(feat: dict) -> dict:
    """Transforme un feature GeoJSON Photon en candidat d'adresse."""
    props  = feat.get("properties", {}) or {}
    geom   = feat.get("geometry", {}) or {}
    coords = geom.get("coordinates") or [None, None]
    lon    = coords[0] if len(coords) > 0 else None
    lat    = coords[1] if len(coords) > 1 else None

    housenumber = (props.get("housenumber") or "").strip()
    street      = (props.get("street") or "").strip()
    name        = (props.get("name") or "").strip()
    city        = (props.get("city") or props.get("town") or props.get("village")
                   or props.get("district") or props.get("county") or "").strip()
    postcode    = (props.get("postcode") or "").strip()
    country     = (props.get("country") or "").strip()

    if housenumber and street:
        line1 = f"{housenumber} {street}"
    elif street:
        line1 = street
    else:
        line1 = name

    short_parts = [p for p in [line1.upper(), city.upper(), postcode] if p]
    short_addr  = "\n".join(short_parts)
    label_parts = [p for p in [line1, city, postcode, country] if p]
    label       = ", ".join(label_parts) or name
    maps_link   = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}&zoom=18" if (lat and lon) else ""

    return {
        "label":     label,
        "short":     short_addr or label,
        "formatted": label,
        "lat":       lat,
        "lon":       lon,
        "maps_link": maps_link,
    }


def _mapbox_candidate(feat: dict) -> dict:
    """Transforme un feature Mapbox Geocoding v6 en candidat d'adresse."""
    props  = feat.get("properties", {}) or {}
    geom   = feat.get("geometry", {}) or {}
    coords = geom.get("coordinates") or [None, None]
    lon    = coords[0] if len(coords) > 0 else None
    lat    = coords[1] if len(coords) > 1 else None

    ctx      = props.get("context", {}) or {}
    line1    = (props.get("name") or "").strip()
    city     = ((ctx.get("place") or {}).get("name")
                or (ctx.get("locality") or {}).get("name") or "").strip()
    postcode = ((ctx.get("postcode") or {}).get("name") or "").strip()
    country  = ((ctx.get("country") or {}).get("name") or "").strip()

    short_parts = [p for p in [line1.upper(), city.upper(), postcode] if p]
    short_addr  = "\n".join(short_parts)
    label       = (props.get("full_address") or props.get("place_formatted") or line1 or "").strip()
    maps_link   = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}&zoom=18" if (lat and lon) else ""

    return {
        "label":     label or line1,
        "short":     short_addr or label,
        "formatted": label or line1,
        "lat":       lat,
        "lon":       lon,
        "maps_link": maps_link,
    }


def _suggest_mapbox(q: str, lang: str, bias_lat, bias_lon, token: str):
    """Autocomplétion via Mapbox Geocoding API v6. Retourne (results | None)."""
    params = {
        "q":            q,
        "access_token": token,
        "autocomplete": "true",
        "limit":        6,
        "language":     lang if lang in ("fr", "en", "es", "de", "it", "pt", "nl") else "en",
        "types":        "address,street,place,locality,neighborhood",
    }
    try:
        if bias_lat is not None and bias_lon is not None:
            params["proximity"] = f"{float(bias_lon)},{float(bias_lat)}"
    except (ValueError, TypeError):
        pass
    try:
        import httpx as _httpx
        r = _httpx.get(
            "https://api.mapbox.com/search/geocode/v6/forward",
            params=params, timeout=8.0,
        )
        if r.status_code != 200:
            logger.warning("mapbox suggest HTTP %s: %s", r.status_code, r.text[:200])
            return None
        feats = (r.json() or {}).get("features", []) or []
    except Exception as exc:
        logger.warning("mapbox suggest: %s", exc)
        return None
    return [_mapbox_candidate(f) for f in feats]


def _suggest_photon(q: str, lang: str, bias_lat, bias_lon):
    """Autocomplétion via Photon (OSM). Retourne (results | None)."""
    params = {"q": q, "limit": 6, "lang": lang if lang in ("fr", "en", "de", "it") else "en"}
    try:
        if bias_lat is not None and bias_lon is not None:
            params["lat"] = float(bias_lat)
            params["lon"] = float(bias_lon)
    except (ValueError, TypeError):
        pass
    try:
        import httpx as _httpx
        r = _httpx.get(
            "https://photon.komoot.io/api/",
            params=params,
            headers={"User-Agent": "MillesimeCoffeeBot/1.0"},
            timeout=8.0,
        )
        if r.status_code != 200:
            return None
        feats = (r.json() or {}).get("features", []) or []
    except Exception as exc:
        logger.warning("photon suggest: %s", exc)
        return None
    return [_photon_candidate(f) for f in feats]


@app.route("/api/geocode/suggest", methods=["POST"])
def api_geocode_suggest():
    """Autocomplétion d'adresse. Mapbox si MAPBOX_TOKEN configuré (meilleure
    couverture), sinon repli Photon (OSM, gratuit).
    POST {q, lang?, bias_lat?, bias_lon?} → {ok, results:[...], provider}
    """
    data = _corps(request)

    # Auth : seul un vrai client Telegram peut consommer le geocoding (anti-abus
    # du quota Mapbox par des scripts externes).
    bot_token = os.getenv("BOT_TOKEN", "")
    parsed = _verify_init_data(data.get("initData", ""), bot_token)
    if not parsed:
        return jsonify({"ok": False, "error": "auth_failed"}), 401
    # Rate-limit par utilisateur : 40 requêtes / minute (large pour l'autocomplete)
    import json as _json
    try:
        uid = str(int(_json.loads(parsed.get("user", "{}")).get("id", 0)))
    except Exception:
        uid = _client_ip(request)
    if _rate_limited(f"geo:{uid}", max_hits=40, window=60.0):
        return jsonify({"ok": False, "error": "rate_limited"}), 429

    q = (data.get("q") or data.get("address") or "").strip()
    if len(q) < 3:
        return jsonify({"ok": True, "results": []})

    lang     = (data.get("lang") or "fr").strip().lower()
    bias_lat = data.get("bias_lat")
    bias_lon = data.get("bias_lon")

    mapbox_token = os.getenv("MAPBOX_TOKEN", "").strip()
    provider = "photon"
    raw = None
    if mapbox_token:
        raw = _suggest_mapbox(q, lang, bias_lat, bias_lon, mapbox_token)
        if raw is not None:
            provider = "mapbox"
    if raw is None:   # pas de token, ou Mapbox en échec → repli Photon
        raw = _suggest_photon(q, lang, bias_lat, bias_lon)
        provider = "photon"
    if raw is None:
        return jsonify({"ok": False, "error": "service_down"})

    results, seen = [], set()
    for cand in raw:
        key = cand.get("short") or cand.get("label")
        if key and key not in seen:
            seen.add(key)
            results.append(cand)
    return jsonify({"ok": True, "results": results[:6], "provider": provider})


# ═══════════════════════════════════════════════════════════════════════════
# Finalisation de commande (depuis la Mini App)
# ═══════════════════════════════════════════════════════════════════════════

def _generate_miniapp_order_id() -> str:
    """Format : DDMMSS (séquence journalière). Lit storage._load()."""
    from datetime import datetime as _dt
    from storage import _load as _load_orders
    now = _dt.now()
    prefix = now.strftime("%d%m")
    today  = now.strftime("%Y-%m-%d")
    try:
        orders = _load_orders()
    except Exception:
        orders = []
    count = 0
    for o in orders:
        if o.get("created_at", "").startswith(today):
            count += 1
        elif isinstance(o.get("order_id"), str) and o["order_id"].startswith(prefix):
            count += 1
    seq = count + 1
    width = 2 if seq < 100 else 3
    return f"{prefix}{seq:0{width}d}"


def _html_escape(s: str) -> str:
    """Échappe HTML pour les messages owner Telegram."""
    if s is None:
        return ""
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))


@app.route("/api/finalize_order", methods=["POST"])
def api_finalize_order():
    """Finalise une commande : valide tout, save_order, notifie owner.
    Retourne {ok: true, order_id: "DDMMSS"} ou {ok: false, error}.
    """
    data = _corps(request)
    if not data:
        return jsonify({"ok": False, "error": "bad_json"}), 400

    bot_token = os.getenv("BOT_TOKEN", "")
    parsed = _verify_init_data(data.get("initData", ""), bot_token)
    if not parsed:
        return jsonify({"ok": False, "error": "auth_failed"}), 401

    import json as _json
    try:
        user_obj   = _json.loads(parsed.get("user", "{}"))
        user_id    = int(user_obj.get("id", 0))
        user_first = (user_obj.get("first_name") or "").strip()
        user_name  = (user_obj.get("username")    or "").strip()
    except Exception:
        return jsonify({"ok": False, "error": "no_user"}), 400
    if not user_id:
        return jsonify({"ok": False, "error": "no_user"}), 400

    # Recharger catalogue
    try:
        import catalog as catalog_mod
        importlib.reload(catalog_mod)
    except Exception as exc:
        logger.error("finalize catalog: %s", exc)
        return jsonify({"ok": False, "error": "catalog_failed"}), 500

    lang    = data.get("lang", "fr") if data.get("lang") in ("fr","es","en") else "fr"
    country = data.get("country", "")
    city    = data.get("city", "")
    cart    = data.get("cart", {}) or {}
    payment = data.get("payment", {}) or {}
    address = data.get("address", {}) or {}
    selfie_b64 = data.get("selfie_b64", "")

    if country not in catalog_mod.CATALOG or city not in catalog_mod.CATALOG.get(country, {}):
        return jsonify({"ok": False, "error": "bad_location"}), 400

    # Devise d'affichage choisie par le client — validée contre les devises
    # autorisées pour ce pays (sinon on prend la devise par défaut du pays).
    allowed_currencies = catalog_mod.get_currencies(country)
    disp_cur = str(data.get("display_currency", "")).strip()
    if disp_cur not in allowed_currencies:
        disp_cur = allowed_currencies[0] if allowed_currencies else "€"

    products = catalog_mod.CATALOG[country][city]
    total = 0.0
    safe_cart = {}
    for prod, qty in cart.items():
        try:
            q = int(qty)
        except (ValueError, TypeError):
            continue
        if q <= 0 or q > 99 or prod not in products:
            continue
        safe_cart[prod] = q
        total += products[prod] * q
    if not safe_cart:
        return jsonify({"ok": False, "error": "empty_cart"}), 400

    # Min commande
    min_order = catalog_mod.MIN_ORDER.get(city)
    if min_order:
        if min_order["type"] == "amount" and total < min_order["value"]:
            return jsonify({"ok": False, "error": f"Minimum {min_order['value']} €"}), 400
        if min_order["type"] == "qty":
            tot_q = sum(safe_cart.values())
            if tot_q < min_order["value"]:
                return jsonify({"ok": False, "error": f"Minimum {min_order['value']} articles"}), 400

    # Génération order_id atomique
    with _pending_lock:  # réutilise le lock existant
        order_id = _generate_miniapp_order_id()

    # Construire l'ordre. On stocke les photos COMPRESSÉES en base64 (sans le
    # préfixe data:) pour que le panel admin puisse les afficher plus tard,
    # sans exploser la taille de orders.json.
    def _strip_data_url(b: str) -> str:
        if not b:
            return ""
        return b.split(",", 1)[1] if "," in b else b

    def _compress_photo_b64(b: str, max_dim: int = 720, quality: int = 65) -> str:
        """Réduit une photo base64 → JPEG max_dim px, qualité `quality`.
        Retourne base64 (sans préfixe data:) ou "" si photo invalide.
        Taille cible : ~40-80 KB au lieu de 500 KB+.

        Si la compression échoue : on garde l'original SEULEMENT si sa taille
        décodée est raisonnable (< 400 KB), sinon on drop pour ne pas gonfler
        orders.json avec un blob corrompu ou géant.
        """
        if not b:
            return ""
        try:
            raw_b64 = _strip_data_url(b).strip().replace("\n","").replace("\r","").replace(" ","")
            pad = len(raw_b64) % 4
            if pad:
                raw_b64 += "=" * (4 - pad)
            raw = base64.b64decode(raw_b64)
            orig_size = len(raw)
            arr = np.frombuffer(raw, np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                logger.warning("compress photo: cv2.imdecode returned None (size=%d)", orig_size)
                return raw_b64 if orig_size < 400_000 else ""
            h, w = img.shape[:2]
            # Downscale si nécessaire
            if max(h, w) > max_dim:
                scale = max_dim / max(h, w)
                new_size = (int(w * scale), int(h * scale))
                img = cv2.resize(img, new_size, interpolation=cv2.INTER_AREA)
            # Réencodage JPEG avec quality
            ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
            if not ok:
                logger.warning("compress photo: cv2.imencode failed")
                return raw_b64 if orig_size < 400_000 else ""
            return base64.b64encode(buf.tobytes()).decode("ascii")
        except Exception as exc:
            logger.warning("compress photo: %s", exc)
            return ""

    pay_label = payment.get("label") or payment.get("method", "?")
    order_dict = {
        "order_id":  order_id,
        "user_id":   user_id,
        "user_name": user_first or user_name or "?",
        "username":  user_name,
        "lang":      lang,
        "country":   country,
        "city":      city,
        "cart":      safe_cart,
        "total":     total,
        "payment":   pay_label,
        "payment_method": payment.get("method", ""),
        "payment_currency": payment.get("currency", ""),
        "payment_crypto":   payment.get("crypto_name", ""),
        "display_currency": disp_cur,   # devise d'affichage choisie (symbole)
        "address":   (address.get("short") or address.get("formatted") or address.get("text") or ""),
        "address_verified": bool(address.get("verified")),
        "address_lat": address.get("lat"),
        "address_lon": address.get("lon"),
        "phone":     "",
        "maps_link": address.get("maps_link", ""),
        "status":    "pending",
        "source":    "miniapp",
        # Photos COMPRESSÉES en base64 pour le panel admin (~50 KB au lieu de 500+)
        "selfie_b64": _compress_photo_b64(selfie_b64, max_dim=720, quality=65),
        "proof_b64":  _compress_photo_b64(payment.get("proof_b64", ""), max_dim=900, quality=70),
    }

    # Sauvegarder
    try:
        from storage import save_order
        save_order(order_dict)
    except Exception as exc:
        logger.error("finalize save_order: %s", exc)
        # Continuer quand même — l'important c'est de notifier l'owner

    # Notification Pushover : envoi en arrière-plan, sans bloquer la réponse
    # au client. Inerte tant que les deux identifiants ne sont pas définis.
    try:
        import pushover
        # Le selfie stocké est déjà recompressé (720 px, qualité 65), donc
        # largement sous la limite de pièce jointe de Pushover.
        _, selfie_bytes = _decode_b64_image(order_dict.get("selfie_b64", ""))
        pushover.nouvelle_commande(
            order_id=order_id,
            adresse=(address.get("short") or address.get("formatted")
                     or address.get("text") or ""),
            articles=safe_cart,
            total=total,
            devise=disp_cur,
            client=(f"@{user_name}" if user_name else (user_first or "")),
            selfie=selfie_bytes,
        )
    except Exception as exc:
        logger.warning("Pushover (mini app) ignore : %s", exc)

    # Le livreur de la zone reçoit la course directement : plus besoin que
    # l'owner lui transmette le bon de commande à chaque fois. Comme partout
    # côté livreur, aucune identité — juste de quoi livrer.
    try:
        if _dans_zone_livreur(order_dict):
            lignes = "\n".join(f"  • {_html_escape(p)} × {q}"
                               for p, q in safe_cart.items())
            adresse_lv = (address.get("short") or address.get("formatted")
                          or address.get("text") or "—")
            prenom = _prenom_seul(order_dict)
            _prevenir_livreur(
                f"🛵 <b>NOUVELLE COURSE</b>  N° <code>{_html_escape(order_id)}</code>\n"
                f"📍 {_html_escape(adresse_lv)}\n"
                + (f"👤 Pour {_html_escape(prenom)}\n" if prenom else "")
                + f"{lignes}\n"
                f"💰 {total:,.0f} {_html_escape(disp_cur)} · {_html_escape(pay_label)}\n\n"
                "Ouvrez la boutique pour l'accepter.")
    except Exception as exc:
        logger.warning("notif course livreur : %s", exc)

    # Notifier owner via Bot API
    owner_chat = os.getenv("OWNER_CHAT_ID", "")
    if not owner_chat:
        return jsonify({"ok": True, "order_id": order_id})  # ordre créé mais owner non notifié

    import httpx
    # On garde les \n natifs : <code>...</code> en HTML Telegram préserve les newlines
    addr_disp = (address.get("short") or address.get("formatted") or "—")
    cart_html = "\n".join(
        f"  • {_html_escape(prod)} × {q} = {products[prod]*q:,.0f} {disp_cur}"
        for prod, q in safe_cart.items()
    )
    full_name = _html_escape(user_first or user_name or "?")
    # En-tête scannable : @username + ville + total
    country_clean = country.split(" ", 1)[1].strip() if " " in country else country
    who_short = f"@{_html_escape(user_name)}" if user_name else full_name
    header = (
        f"🆕 <b>NOUVELLE COMMANDE</b> · <code>{order_id}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 {who_short}\n"
        f"📍 <b>{_html_escape(city)}</b> ({_html_escape(country_clean)})\n"
        f"💸 <b>{total:,.0f} {disp_cur}</b> · {sum(safe_cart.values())} article(s)\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    lines = [
        header,
        "",
        f"👤 Client : {full_name} ({user_id})",
    ]
    if user_name:
        lines.append(f"📱 Username : @{_html_escape(user_name)}")
    lines += [
        f"🌐 Langue : {lang.upper()}",
        "",
        f"🌍 Pays : {_html_escape(country)}",
        f"🏙️ Ville : {_html_escape(city)}",
        "",
        f"🛒 <b>Panier ({sum(safe_cart.values())} articles)</b>",
        f"<code>{_html_escape(cart_html)}</code>",
        "",
        f"💸 <b>Total : {total:,.0f} {disp_cur}</b>",
        "",
        f"💳 Paiement : {_html_escape(pay_label)}",
    ]
    if payment.get("crypto_name"):
        lines.append(f"   ↳ Adresse : <code>{_html_escape(payment.get('crypto_addr',''))}</code>")
    lines += [
        "",
        f"📍 <b>Adresse</b>",
        f"<code>{_html_escape(addr_disp)}</code>",
    ]
    if address.get("maps_link"):
        lines.append(f"🗺️ <a href=\"{address['maps_link']}\">Voir sur la carte</a>")

    inline_kb = {
        "inline_keyboard": [
            [{"text": "✅ Commande confirmée",     "callback_data": f"owner:confirmed:{user_id}:{order_id}"}],
            [{"text": "🚚 En cours de livraison", "callback_data": f"owner:delivering:{user_id}:{order_id}"}],
            [{"text": "📦 Commande livrée",       "callback_data": f"owner:delivered:{user_id}:{order_id}"}],
            [{"text": "❌ Annuler la commande",    "callback_data": f"owner:cancelled:{user_id}:{order_id}"}],
        ]
    }
    try:
        with httpx.Client(timeout=15.0) as c:
            c.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id":    owner_chat,
                    "text":       "\n".join(lines),
                    "parse_mode": "HTML",
                    "reply_markup": inline_kb,
                    "disable_web_page_preview": True,
                },
            )
            # Envoyer le selfie si présent
            if selfie_b64:
                _, sb = _decode_b64_image(selfie_b64)
                if sb:
                    c.post(
                        f"https://api.telegram.org/bot{bot_token}/sendPhoto",
                        data={
                            "chat_id": owner_chat,
                            "caption": f"📸 Selfie client — {order_id}",
                        },
                        files={"photo": ("selfie.jpg", sb, "image/jpeg")},
                    )
            # Envoyer preuve virement si présente
            proof_b64 = payment.get("proof_b64", "")
            if proof_b64:
                _, pb = _decode_b64_image(proof_b64)
                if pb:
                    c.post(
                        f"https://api.telegram.org/bot{bot_token}/sendPhoto",
                        data={
                            "chat_id": owner_chat,
                            "caption": f"🏦 Preuve de virement — {order_id}",
                        },
                        files={"photo": ("proof.jpg", pb, "image/jpeg")},
                    )
    except Exception as exc:
        logger.error("finalize notify owner: %s", exc)

    # Envoyer un message de confirmation au client
    try:
        with httpx.Client(timeout=10.0) as c:
            c.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id": user_id,
                    "text": (
                        f"🧾 *Bon de commande — N° {order_id}*\n\n"
                        f"🏙️ {city}\n"
                        f"🛒 {sum(safe_cart.values())} article(s) — *{total:,.0f} €*\n"
                        f"💳 {pay_label}\n\n"
                        f"_Nous vous contactons très bientôt pour la livraison._ 🙏"
                    ),
                    "parse_mode": "Markdown",
                },
            )
    except Exception as exc:
        logger.warning("finalize notify client: %s", exc)

    return jsonify({"ok": True, "order_id": order_id})


# ═══════════════════════════════════════════════════════════════════════════
# PANEL ADMIN OWNER (Mini App) — gestion des commandes
# ═══════════════════════════════════════════════════════════════════════════

def _is_owner_init(parsed_init: dict | None) -> int | None:
    """Si initData parsed correspond au OWNER_USER_ID, retourne le user_id, sinon None."""
    if not parsed_init:
        return None
    try:
        import json as _json
        user_obj = _json.loads(parsed_init.get("user", "{}"))
        uid = int(user_obj.get("id", 0))
        owner_id = os.getenv("OWNER_USER_ID", "")
        if owner_id and str(uid) == str(owner_id):
            return uid
    except Exception:
        return None
    return None




# ═══════════════════════════════════════════════════════════════════════════
# Verrou du panneau admin — 2e barrière après l'identité Telegram
# ═══════════════════════════════════════════════════════════════════════════
# L'identité Telegram seule prouve « ce compte est celui de l'owner ». Ça ne
# protège pas d'un téléphone déverrouillé laissé sans surveillance : le mot de
# passe ci-dessous ajoute quelque chose que l'on sait, en plus de quelque chose
# que l'on possède.
#
# Si ADMIN_PANEL_PASSWORD n'est pas défini, le verrou est inactif et le panel
# se comporte exactement comme avant — on ne se retrouve jamais enfermé dehors
# à cause d'une variable oubliée au déploiement.

_ADMIN_SESSION_TTL   = int(os.getenv("ADMIN_SESSION_TTL", "28800"))  # 8 h
_ADMIN_MAX_ATTEMPTS  = 5
_ADMIN_LOCKOUT       = 900   # 15 min de blocage après trop d'essais

_admin_unlocked: dict[str, float] = {}   # {user_id: expiration}
_admin_lock = threading.Lock()


def _admin_password() -> str:
    """Relu à chaque appel : changer la variable d'env ne demande pas de
    redéploiement complet sur les plateformes qui rechargent le process."""
    return os.getenv("ADMIN_PANEL_PASSWORD", "").strip()


def _normalise_mdp(s: str) -> str:
    """Compare à la casse près et sans se soucier des espaces superflus.

    Un mot de passe en toutes lettres se tape mal sur un clavier de téléphone
    (le champ désactive la majuscule automatique), et une majuscule oubliée
    coûterait un essai sur les cinq autorisés. La solidité du verrou ne repose
    de toute façon pas sur la casse : il faut déjà être connecté au compte
    Telegram de l'owner, et cinq erreurs bloquent l'accès un quart d'heure.
    """
    return " ".join((s or "").split()).casefold()


def _admin_is_unlocked(uid) -> bool:
    with _admin_lock:
        maintenant = time.time()
        # Les sessions d'autres comptes ne sont sinon effacées que si ce compte
        # précis repasse : on purge tout ce qui est périmé au passage.
        for k in [k for k, exp in _admin_unlocked.items() if exp <= maintenant]:
            del _admin_unlocked[k]
        return _admin_unlocked.get(str(uid), 0) > maintenant


def _uid_authentifie(req) -> int | None:
    """user_id d'une session Telegram valide, quel que soit le compte.

    Ne présume pas que la session est celle de l'owner : c'est le mot de
    passe qui donne le droit d'entrer, pas le compte.
    Depuis que le mot de passe admin ouvre le panel depuis n'importe quel
    téléphone, il faut pouvoir identifier une session sans présumer de qui
    elle est : c'est le mot de passe qui donne le droit, pas le compte.
    """
    bot_token = os.getenv("BOT_TOKEN", "")
    if req.method == "POST":
        init_data = _corps(req).get("initData", "")
    else:
        init_data = req.args.get("initData", "")
    if not isinstance(init_data, str):
        return None
    parsed = _verify_init_data(init_data, bot_token)
    if not parsed:
        return None
    import json as _json
    try:
        return int(_json.loads(parsed.get("user", "{}")).get("id", 0)) or None
    except Exception:
        return None


def _a_acces_admin(uid) -> bool:
    """Le panel est ouvert à qui a saisi le mot de passe admin. Si aucun mot de
    passe n'est configuré, on retombe sur l'ancien comportement : seul le
    compte owner entre — pour ne jamais laisser le panel grand ouvert."""
    if uid is None:
        return False
    if _admin_is_unlocked(uid):
        return True
    if not _admin_password():
        owner_id = os.getenv("OWNER_USER_ID", "").strip()
        return bool(owner_id) and str(uid) == owner_id
    return False


def _guard_admin(req):
    """Renvoie None si l'accès au panel est autorisé, sinon la réponse d'erreur.
    À appeler en tête de chaque endpoint /api/admin/*."""
    uid = _uid_authentifie(req)
    if uid is None:
        return jsonify({"ok": False, "error": "auth_failed"}), 401
    if not _a_acces_admin(uid):
        return jsonify({"ok": False, "error": "admin_locked"}), 403
    return None


# ═════════════════════════════════════════════════════════════════════════════
# Accès livreur — les courses de sa zone, sans aucune identité de client
# ═════════════════════════════════════════════════════════════════════════════
# Le livreur a son propre mot de passe et ne voit que ce dont il a besoin pour
# livrer : l'adresse, le panier, le montant. Jamais le nom, le pseudo, l'ID
# Telegram ni le selfie du client. Il lui parle par la messagerie de
# l'application, à travers une référence opaque : même en lisant les réponses
# du serveur, il ne peut pas remonter au compte Telegram de la personne.

_livreur_unlocked: dict[str, float] = {}
_livreur_lock = threading.Lock()


def _livreur_password() -> str:
    return os.getenv("LIVREUR_PASSWORD", "").strip()


def _zones_livreur() -> list[tuple[str, str]]:
    """Zones confiées au livreur : liste de (pays_normalisé, ville_normalisée).

    Format de LIVREUR_ZONES : « Belgique:Bruxelles, France:Paris ».
    Une entrée sans ville couvre tout le pays : « Belgique ».
    """
    brut = os.getenv("LIVREUR_ZONES", "Belgique:Bruxelles")
    zones = []
    for morceau in brut.split(","):
        morceau = morceau.strip()
        if not morceau:
            continue
        pays, _, ville = morceau.partition(":")
        zones.append((_sans_accent(pays), _sans_accent(ville)))
    return zones


def _sans_accent(s: str) -> str:
    """Minuscule sans accent ni drapeau, pour comparer « Belgique » et
    « 🇧🇪 Belgique » sans se soucier de la casse."""
    import unicodedata
    s = "".join(c for c in (s or "") if not (0x1F1E6 <= ord(c) <= 0x1F1FF))
    s = unicodedata.normalize("NFKD", s.strip())
    return "".join(c for c in s if not unicodedata.combining(c)).casefold()


def _dans_zone_livreur(order: dict) -> bool:
    pays = _sans_accent(order.get("country") or "")
    ville = _sans_accent(order.get("city") or "")
    for z_pays, z_ville in _zones_livreur():
        if z_pays and z_pays != pays:
            continue
        if z_ville and z_ville != ville:
            continue
        return True
    return False


# ── À qui envoyer les notifications de courses ───────────────────────────────
# Deux façons de connaître le Telegram du livreur, dans cet ordre :
#   1. LIVREUR_CHAT_ID, si on veut le fixer explicitement ;
#   2. sinon, le compte retenu automatiquement lors de sa connexion au panel.
# La seconde évite d'avoir à relever un identifiant à la main : il se connecte
# une fois avec son mot de passe, et il est inscrit.
_LIVREURS_FICHIER = None
_livreurs_connus: dict[str, float] = {}
_livreurs_lock = threading.Lock()
_LIVREUR_OUBLI = 90 * 24 * 3600      # inactif 90 jours → on ne le notifie plus


def _fichier_livreurs():
    global _LIVREURS_FICHIER
    if _LIVREURS_FICHIER is None:
        from pathlib import Path
        base = os.getenv("DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
        _LIVREURS_FICHIER = Path(base) / "livreurs.json"
        try:
            import json as _json
            with _LIVREURS_FICHIER.open(encoding="utf-8") as f:
                donnees = _json.load(f)
            if isinstance(donnees, dict):
                _livreurs_connus.update({str(k): float(v) for k, v in donnees.items()})
        except (OSError, ValueError):
            pass
    return _LIVREURS_FICHIER


def _retenir_livreur(uid) -> None:
    """Mémorise le compte Telegram d'un livreur qui vient de se connecter."""
    if not uid:
        return
    chemin = _fichier_livreurs()
    with _livreurs_lock:
        maintenant = time.time()
        _livreurs_connus[str(uid)] = maintenant
        for k in [k for k, t in _livreurs_connus.items()
                  if maintenant - t > _LIVREUR_OUBLI]:
            del _livreurs_connus[k]
        copie = dict(_livreurs_connus)
    try:
        from storage import _ecrire_json_atomique
        _ecrire_json_atomique(chemin, copie, indent=2)
        import github_backup
        github_backup.backup_file_async("livreurs.json")
    except Exception as exc:
        logger.warning("enregistrement livreur : %s", exc)


def _pseudos_livreur() -> set[str]:
    """Pseudos Telegram déclarés comme livreurs, sans @ ni casse."""
    brut = os.getenv("LIVREUR_USERNAME", "")
    return {p.strip().lstrip("@").casefold() for p in brut.split(",") if p.strip()}


def enregistrer_livreur_par_pseudo(uid, pseudo) -> bool:
    """Inscrit un livreur reconnu à son pseudo Telegram.

    Un bot ne peut pas écrire à quelqu'un qui ne l'a jamais démarré, et il ne
    peut pas non plus traduire un @pseudo en identifiant. Donner le pseudo ne
    suffit donc pas : il faut que la personne se manifeste au moins une fois.
    Dès qu'elle le fait — /start ou n'importe quel message — on la reconnaît
    et on retient son identifiant.
    """
    pseudo = (pseudo or "").lstrip("@").casefold()
    if not uid or not pseudo or pseudo not in _pseudos_livreur():
        return False
    deja = str(uid) in _livreurs_connus
    _retenir_livreur(uid)
    if not deja:
        logger.info("livreur reconnu au pseudo @%s → id %s", pseudo, uid)
    return True


def _destinataires_livreur() -> list[str]:
    fixe = os.getenv("LIVREUR_CHAT_ID", "").strip()
    if fixe:
        return [x.strip() for x in fixe.split(",") if x.strip()]
    _fichier_livreurs()
    with _livreurs_lock:
        return list(_livreurs_connus)


def _prevenir_livreur(texte: str, cle_anti_repetition: str = "") -> int:
    """Envoie un message Telegram aux livreurs de la zone. Renvoie le nombre
    d'envois réussis. Silencieux si personne n'est enregistré."""
    token = os.getenv("BOT_TOKEN", "")
    cibles = _destinataires_livreur()
    if not token or not cibles:
        return 0
    if cle_anti_repetition and _rate_limited(cle_anti_repetition, 1, _VILLE_COOLDOWN):
        return 0
    envoyes = 0
    import httpx
    for cible in cibles:
        try:
            r = httpx.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": cible, "text": texte, "parse_mode": "HTML",
                      "disable_web_page_preview": True},
                timeout=8.0)
            if r.status_code == 200 and (r.json() or {}).get("ok"):
                envoyes += 1
            else:
                logger.warning("notif livreur %s : %s", cible, _telegram_error(r))
        except Exception as exc:
            logger.warning("notif livreur %s : %s", cible, exc)
    return envoyes


def _livreur_is_unlocked(uid) -> bool:
    with _livreur_lock:
        maintenant = time.time()
        for k in [k for k, exp in _livreur_unlocked.items() if exp <= maintenant]:
            del _livreur_unlocked[k]
        return _livreur_unlocked.get(str(uid), 0) > maintenant


def _a_acces_livreur(uid) -> bool:
    return uid is not None and bool(_livreur_password()) and _livreur_is_unlocked(uid)


def _guard_livreur(req):
    uid = _uid_authentifie(req)
    if uid is None:
        return None, (jsonify({"ok": False, "error": "auth_failed"}), 401)
    if not _a_acces_livreur(uid):
        return None, (jsonify({"ok": False, "error": "livreur_locked"}), 403)
    return uid, None


def _ref_chat(order_id: str) -> str:
    """Référence opaque d'une conversation, dérivée de la commande.

    Le livreur discute avec « la commande 140801 », pas avec un identifiant
    Telegram : impossible pour lui de retrouver la personne hors de l'app.
    """
    cle = (os.getenv("BOT_TOKEN", "") or "millesime").encode()
    return hmac.new(cle, f"chat:{order_id}".encode(), hashlib.sha256).hexdigest()[:24]


def _resoudre_ref_chat(ref: str):
    """(client_id, commande) correspondant à une référence, dans la zone du
    livreur uniquement. Renvoie (None, None) si la référence est inconnue."""
    ref = _texte(ref, 64)
    if not ref:
        return None, None
    try:
        from storage import _load as _load_all
        commandes = _load_all() or []
    except Exception:
        return None, None
    for o in commandes:
        oid = str(o.get("order_id") or "")
        if oid and _dans_zone_livreur(o) and hmac.compare_digest(_ref_chat(oid), ref):
            try:
                return int(o.get("user_id") or 0) or None, o
            except (TypeError, ValueError):
                return None, None
    return None, None


def _prenom_seul(o: dict) -> str:
    """Prénom affichable du client — jamais un moyen de le recontacter.

    Le livreur a besoin de savoir à qui il remet la commande et à qui il
    parle. Il ne doit pas pour autant repartir avec le pseudo Telegram ou le
    numéro du client : ce sont eux qui permettraient de le démarcher en
    dehors de la boutique.

    Piège : `user_name` retombe sur le pseudo Telegram quand le compte n'a
    pas de prénom. Dans ce cas on n'affiche rien plutôt que de livrer un
    identifiant déguisé en prénom.
    """
    nom = (o.get("user_name") or "").strip()
    pseudo = (o.get("username") or "").strip().lstrip("@")
    if not nom or nom == "?":
        return ""
    if pseudo and nom.casefold() == pseudo.casefold():
        return ""
    # Un prénom ne commence pas par @ et n'est pas une suite de chiffres.
    if nom.startswith("@") or nom.replace("+", "").replace(" ", "").isdigit():
        return ""
    return nom[:32]


def _course_pour_livreur(o: dict) -> dict:
    """Vue d'une commande telle que le livreur a le droit de la voir.

    Tout ce qui identifie le client est retiré ; l'adresse reste, sans quoi
    il ne pourrait pas livrer.
    """
    oid = str(o.get("order_id") or "")
    return {
        "order_id":   oid,
        "status":     o.get("status") or "pending",
        "created_at": o.get("created_at"),
        "city":       o.get("city"),
        "country":    o.get("country"),
        "address":    o.get("address") or "",
        "address_lat": o.get("address_lat"),
        "address_lon": o.get("address_lon"),
        "cart":       o.get("cart") or {},
        "total":      o.get("total"),
        "display_currency": o.get("display_currency") or "€",
        "payment":    o.get("payment") or "",
        "_confirmed_at":        o.get("_confirmed_at"),
        "_delivery_started_at": o.get("_delivery_started_at"),
        "_delivered_at":        o.get("_delivered_at"),
        "_eta_minutes":         o.get("_eta_minutes"),
        # Le prénom seul : de quoi s'adresser à la personne à la porte et dans
        # la conversation, sans aucun moyen de la recontacter par ailleurs.
        "client":     _prenom_seul(o),
        # Le selfie sert à vérifier à qui l'on remet la commande. On n'envoie
        # pas le base64 dans la liste (c'est lourd) : juste de quoi savoir
        # qu'il existe, la photo est servie par sa propre route.
        "has_selfie": bool(o.get("selfie_b64")),
        # Pour ouvrir la conversation sans jamais exposer le compte Telegram.
        "chat_ref":   _ref_chat(oid),
    }


@app.route("/api/livreur/courses", methods=["POST"])
def api_livreur_courses():
    """Les courses de la zone du livreur, sans aucune identité de client.
    POST {initData}
    """
    uid, refus = _guard_livreur(request)
    if refus:
        return refus
    try:
        from storage import _load as _load_all
        toutes = _load_all() or []
    except Exception as exc:
        logger.error("livreur_courses load: %s", exc)
        return jsonify({"ok": False, "error": "load_failed"}), 500

    miennes = [o for o in toutes if _dans_zone_livreur(o)]
    miennes.sort(key=lambda o: o.get("created_at") or "", reverse=True)
    courses = [_course_pour_livreur(o) for o in miennes[:200]]

    a_traiter = [c for c in courses
                 if c["status"] in ("pending", "confirmed", "delivering")]

    # ── Son tableau de bord : ce qu'il a LIVRÉ, sur sa zone uniquement ──────
    # Seules les courses livrées comptent — une commande en attente ou annulée
    # n'est pas un gain. Journées découpées à l'heure de Paris, comme partout.
    from datetime import datetime as _dt, timedelta as _td
    auj = _dt.now(_PARIS).date()
    debut7 = auj - _td(days=6)
    debut_mois = auj.replace(day=1)
    stats = {"jour": {"ca": 0.0, "n": 0}, "semaine": {"ca": 0.0, "n": 0},
             "mois": {"ca": 0.0, "n": 0}}
    produits: dict = {}
    devises: dict = {}
    for o in miennes:
        if (o.get("status") or "") != "delivered":
            continue
        jour = _jour_paris(o.get("_delivered_at") or o.get("created_at"))
        if jour is None:
            continue
        try:
            montant = float(o.get("total") or 0)
        except (TypeError, ValueError):
            montant = 0.0
        devise = o.get("display_currency") or "€"
        devises[devise] = devises.get(devise, 0) + 1
        if jour == auj:
            stats["jour"]["ca"] += montant; stats["jour"]["n"] += 1
        if jour >= debut7:
            stats["semaine"]["ca"] += montant; stats["semaine"]["n"] += 1
        if jour >= debut_mois:
            stats["mois"]["ca"] += montant; stats["mois"]["n"] += 1
            for p, q in (o.get("cart") or {}).items():
                try:
                    q = int(q)
                except (TypeError, ValueError):
                    q = 0
                if q > 0:
                    produits[p] = produits.get(p, 0) + q
    stats["devise"] = max(devises, key=devises.get) if devises else "€"
    stats["top_produits"] = [
        {"produit": p, "quantite": q}
        for p, q in sorted(produits.items(), key=lambda x: x[1], reverse=True)[:5]]

    return jsonify({
        "ok": True,
        "zones": [" · ".join(x for x in z if x) for z in _zones_livreur()],
        "courses": courses,
        "a_traiter": len(a_traiter),
        "stats": stats,
        # Par client UNIQUE : un client avec trois commandes dans la zone ne
        # doit pas voir son message non lu compté trois fois.
        "non_lus": sum(chat.non_lus(u, chat.VENDEUR)
                       for u in {o.get("user_id") for o in miennes
                                 if o.get("user_id")}),
    })


# Le livreur fait avancer la course, il ne peut pas la faire reculer ni la
# ressusciter : seules ces transitions lui sont ouvertes.
_TRANSITIONS_LIVREUR = {
    "pending":    {"confirmed", "cancelled"},
    "confirmed":  {"delivering", "cancelled"},
    "delivering": {"delivered", "cancelled"},
}


@app.route("/api/livreur/course/<order_id>/status", methods=["POST"])
def api_livreur_status(order_id):
    """Changement de statut par le livreur, borné à sa zone et aux étapes
    suivantes. POST {initData, status, eta_minutes?}"""
    uid, refus = _guard_livreur(request)
    if refus:
        return refus
    data = _corps(request)
    nouveau = _texte(data.get("status"), 32)

    try:
        from storage import get_order
        order = get_order(order_id)
    except Exception:
        return jsonify({"ok": False, "error": "load_failed"}), 500
    if not order or not _dans_zone_livreur(order):
        return jsonify({"ok": False, "error": "hors_zone"}), 404

    actuel = order.get("status") or "pending"
    if nouveau not in _TRANSITIONS_LIVREUR.get(actuel, set()):
        return jsonify({"ok": False, "error": "transition_interdite",
                        "actuel": actuel}), 400

    return _appliquer_statut(order_id, order, nouveau, data, par="livreur")


@app.route("/api/livreur/course/<order_id>/selfie", methods=["GET"])
def api_livreur_selfie(order_id):
    """Selfie du client, pour vérifier à qui l'on remet la commande.

    Réservé aux courses de la zone du livreur. C'est une photo de contrôle à
    la remise, pas un moyen de recontacter la personne : elle ne s'accompagne
    d'aucun identifiant.
    """
    uid = _uid_authentifie(request)
    if uid is None:
        return ("Forbidden", 403)
    if not _a_acces_livreur(uid):
        return ("Forbidden", 403)
    try:
        from storage import get_order
        order = get_order(order_id)
    except Exception:
        return ("Server error", 500)
    if not order or not _dans_zone_livreur(order):
        return ("Not found", 404)
    b64 = order.get("selfie_b64") or ""
    if not b64:
        return ("No photo", 404)
    try:
        photo = base64.b64decode(b64)
    except Exception:
        return ("Bad photo", 500)
    from flask import Response
    return Response(photo, mimetype="image/jpeg",
                    headers={"Cache-Control": "private, max-age=300"})


@app.route("/api/livreur/status", methods=["POST"])
def api_livreur_etat():
    """Dit à la Mini App si la session est celle d'un livreur. POST {initData}"""
    uid = _uid_authentifie(request)
    return jsonify({
        "ok": True,
        "livreur": _a_acces_livreur(uid),
        "password_set": bool(_livreur_password()),
        "zones": [" · ".join(x for x in z if x) for z in _zones_livreur()],
    })


@app.route("/api/livreur/lock", methods=["POST"])
def api_livreur_lock():
    uid = _uid_authentifie(request)
    if uid is not None:
        with _livreur_lock:
            _livreur_unlocked.pop(str(uid), None)
    return jsonify({"ok": True})


@app.route("/api/admin/status", methods=["POST"])
def api_admin_status():
    """Dit à la Mini App si l'utilisateur est owner et si le panel est verrouillé.
    Volontairement accessible sans déverrouillage : c'est ce qui permet
    d'afficher l'écran de mot de passe plutôt qu'un refus sec.
    POST {initData}
    """
    uid = _uid_authentifie(request)
    if uid is None:
        return jsonify({"ok": True, "is_owner": False, "locked": False})
    verrou = bool(_admin_password())
    acces = _a_acces_admin(uid)
    owner_id = os.getenv("OWNER_USER_ID", "").strip()
    return jsonify({
        "ok": True,
        # « is_owner » = a le droit d'ouvrir le panel maintenant. Ce n'est plus
        # une question d'identité mais de mot de passe saisi.
        "is_owner": acces,
        "compte_owner": bool(owner_id) and str(uid) == owner_id,
        "locked": verrou and not acces,
        "password_set": verrou,
    })


@app.route("/api/admin/unlock", methods=["POST"])
def api_admin_unlock():
    """Déverrouille le panel pour la durée de la session.
    POST {initData, password}
    """
    uid = _uid_authentifie(request)
    if uid is None:
        return jsonify({"ok": False, "error": "auth_failed"}), 401

    attendu = _admin_password()
    if not attendu:
        return jsonify({"ok": True, "no_password": True})

    # Anti-force-brute : la clé combine l'IP et l'user_id pour qu'un changement
    # de réseau ne remette pas le compteur à zéro.
    cle = f"adminpwd:{_client_ip(request)}:{uid}"
    if _rate_limited(cle, _ADMIN_MAX_ATTEMPTS, _ADMIN_LOCKOUT):
        logger.warning("panel admin : trop d'essais pour %s", uid)
        return jsonify({"ok": False, "error": "too_many_attempts",
                        "retry_after": _ADMIN_LOCKOUT}), 429

    data = _corps(request)
    fourni = data.get("password") or ""

    # compare_digest : temps constant, pour ne pas laisser deviner le mot de
    # passe caractère par caractère en mesurant le temps de réponse.
    if not hmac.compare_digest(_normalise_mdp(fourni), _normalise_mdp(attendu)):
        logger.warning("panel admin : mot de passe refuse pour %s", uid)
        return jsonify({"ok": False, "error": "wrong_password"}), 403

    # Succès : on repart d'un compteur vierge pour ne pas pénaliser un owner
    # qui rouvre le panel plusieurs fois dans la même fenêtre.
    _rate_reset(cle)
    with _admin_lock:
        _admin_unlocked[str(uid)] = time.time() + _ADMIN_SESSION_TTL
    logger.info("panel admin deverrouille pour %s", uid)
    return jsonify({"ok": True, "expires_in": _ADMIN_SESSION_TTL})


@app.route("/api/admin/lock", methods=["POST"])
def api_admin_lock():
    """Reverrouille immédiatement (bouton « Verrouiller » du panel).
    POST {initData}
    """
    uid = _uid_authentifie(request)
    if uid is None:
        return jsonify({"ok": False, "error": "auth_failed"}), 401
    with _admin_lock:
        _admin_unlocked.pop(str(uid), None)
    return jsonify({"ok": True})


@app.route("/api/admin/orders", methods=["POST"])
def api_admin_orders():
    """Retourne la liste des commandes pour le panel owner.
    POST {initData, limit?, status_filter?}
    """
    _refus = _guard_admin(request)
    if _refus:
        return _refus

    data = _corps(request)
    limit  = _entier(data.get("limit"), 50, 1, 1000)
    sfilt  = data.get("status_filter", "")  # "", "pending", "confirmed", "delivering", "delivered", "cancelled"

    try:
        from storage import _load as _load_orders
        orders = _load_orders() or []
    except Exception as exc:
        logger.error("admin_orders load: %s", exc)
        return jsonify({"ok": False, "error": "load_failed"}), 500

    # Trier du plus récent au plus ancien
    orders = sorted(orders, key=lambda o: o.get("created_at", ""), reverse=True)

    # Filtrer + tronquer. « cancelled » regroupe les deux origines d'annulation
    # (owner et client), sinon les commandes annulées par le client
    # n'apparaissent dans aucun onglet.
    if sfilt:
        wanted = _CANCELLED_STATUSES if sfilt == "cancelled" else (sfilt,)
        orders = [o for o in orders if (o.get("status") or "pending") in wanted]
    orders = orders[:limit]

    # Construire une version allégée (sans les photos b64 — trop lourd pour la liste)
    light = []
    for o in orders:
        light.append({
            "order_id":   o.get("order_id"),
            "created_at": o.get("created_at"),
            "user_id":    o.get("user_id"),
            "user_name":  o.get("user_name"),
            "username":   o.get("username"),
            "city":       o.get("city"),
            "country":    o.get("country"),
            "total":      o.get("total"),
            "payment":    o.get("payment"),
            "status":     o.get("status") or "pending",
            "source":     o.get("source"),
            "rating":     o.get("rating"),
            "display_currency": o.get("display_currency") or "€",
            "has_selfie": bool(o.get("selfie_b64")),
            "has_proof":  bool(o.get("proof_b64")),
            "cart_count": sum((o.get("cart") or {}).values()) if isinstance(o.get("cart"), dict) else 0,
        })

    # ── Statistiques du tableau de bord ────────────────────────────────────
    # Les bornes de journée sont calculées à l'heure de Paris, pas à celle du
    # serveur : Render tourne en UTC, et « aujourd'hui » basculerait sinon à
    # 1 h ou 2 h du matin, en plein service.
    from datetime import datetime as _dt, timedelta as _td
    maintenant = _dt.now(_PARIS)
    aujourdhui = maintenant.date()
    # 7 jours glissants plutôt que la semaine calendaire : sur un lundi matin,
    # « depuis lundi » vaut zéro et fait disparaître le week-end, alors que
    # c'est justement là que le chiffre se fait. Le mois reste calendaire,
    # c'est le sens comptable de « mensuel ».
    debut_semaine = aujourdhui - _td(days=6)
    debut_mois    = aujourdhui.replace(day=1)

    counts = {"pending": 0, "confirmed": 0, "delivering": 0, "delivered": 0, "cancelled": 0}
    ca = {"jour": 0.0, "semaine": 0.0, "mois": 0.0}
    nb = {"jour": 0, "semaine": 0, "mois": 0}
    today_items: dict[str, int] = {}
    villes: dict[str, dict] = {}
    produits: dict[str, int] = {}

    # Historique 7 jours pour le mini-graphe
    ca_by_day = {(aujourdhui - _td(days=i)).isoformat(): 0.0 for i in range(7)}

    try:
        from storage import _load as _load_all
        for o in (_load_all() or []):
            s = o.get("status") or "pending"
            if s in _CANCELLED_STATUSES:
                counts["cancelled"] += 1
            elif s in counts:
                counts[s] += 1
            if s in _CANCELLED_STATUSES:
                continue          # une commande annulée ne compte dans aucun CA

            jour = _jour_paris(o.get("created_at"))
            if jour is None:
                continue
            montant = float(o.get("total", 0) or 0)

            cle = jour.isoformat()
            if cle in ca_by_day:
                ca_by_day[cle] += montant

            if jour == aujourdhui:
                ca["jour"] += montant; nb["jour"] += 1
                for prod, qte in (o.get("cart") or {}).items():
                    try:
                        q = int(qte)
                    except (TypeError, ValueError):
                        q = 0
                    if q > 0:
                        today_items[prod] = today_items.get(prod, 0) + q
            if jour >= debut_semaine:
                ca["semaine"] += montant; nb["semaine"] += 1
            if jour >= debut_mois:
                ca["mois"] += montant; nb["mois"] += 1

            # Classements sur l'ensemble de l'historique
            ville = (o.get("city") or "").strip()
            if ville:
                v = villes.setdefault(ville, {"ville": ville, "pays": o.get("country", ""),
                                              "ca": 0.0, "commandes": 0})
                v["ca"] += montant
                v["commandes"] += 1
            for prod, qte in (o.get("cart") or {}).items():
                try:
                    q = int(qte)
                except (TypeError, ValueError):
                    q = 0
                if q > 0:
                    produits[prod] = produits.get(prod, 0) + q
    except Exception as exc:
        logger.warning("stats dashboard : %s", exc)

    top_villes = sorted(villes.values(), key=lambda v: v["ca"], reverse=True)[:5]
    top_produits = [{"produit": p, "quantite": q}
                    for p, q in sorted(produits.items(), key=lambda x: x[1], reverse=True)[:5]]

    top_product, top_product_qty = ("", 0)
    if today_items:
        top_product, top_product_qty = max(today_items.items(), key=lambda x: x[1])

    ca_history = [{"day": d, "ca": ca_by_day[d]} for d in sorted(ca_by_day)]

    return jsonify({
        "ok": True,
        "orders": light,
        "counts": counts,
        "today_ca":         ca["jour"],
        "today_count":      nb["jour"],
        "ca_semaine":       ca["semaine"],
        "count_semaine":    nb["semaine"],
        "ca_mois":          ca["mois"],
        "count_mois":       nb["mois"],
        "avg_basket_today": (ca["jour"] / nb["jour"]) if nb["jour"] else 0.0,
        "top_product":      top_product,
        "top_product_qty":  top_product_qty,
        "top_villes":       top_villes,
        "top_produits":     top_produits,
        "ca_history":       ca_history,
    })


@app.route("/api/admin/order/<order_id>", methods=["POST"])
def api_admin_order_detail(order_id):
    """Détail complet d'une commande (avec photos b64).
    POST {initData}
    """
    _refus = _guard_admin(request)
    if _refus:
        return _refus

    try:
        from storage import get_order
        order = get_order(order_id)
    except Exception as exc:
        logger.error("admin_order get: %s", exc)
        return jsonify({"ok": False, "error": "load_failed"}), 500

    if not order:
        return jsonify({"ok": False, "error": "not_found"}), 404

    # Attacher la note privée owner s'il y en a une
    try:
        notes = _load_notes()
        uid = str(order.get("user_id", ""))
        if uid and uid in notes:
            order = {**order, "_client_note": notes[uid]}
    except Exception:
        pass
    return jsonify({"ok": True, "order": order})


@app.route("/api/admin/order/<order_id>/status", methods=["POST"])
def api_admin_set_status(order_id):
    """Modifie le statut d'une commande + notifie le client.
    POST {initData, status: "confirmed"|"delivering"|"delivered"|"cancelled"}
    """
    _refus = _guard_admin(request)
    if _refus:
        return _refus

    data = _corps(request)
    new_status = _texte(data.get("status"))
    if new_status not in ("confirmed", "delivering", "delivered", "cancelled"):
        return jsonify({"ok": False, "error": "bad_status"}), 400

    # Charger order existant
    try:
        from storage import get_order
        order = get_order(order_id)
    except Exception as exc:
        logger.error("admin_set_status load: %s", exc)
        return jsonify({"ok": False, "error": "load_failed"}), 500
    if not order:
        return jsonify({"ok": False, "error": "not_found"}), 404

    return _appliquer_statut(order_id, order, new_status, data, par="admin")


def _appliquer_statut(order_id, order, new_status, data, par="admin"):
    """Écrit le nouveau statut et prévient le client.

    Partagé par le panel admin et le panel livreur : les deux doivent
    horodater les étapes et notifier de la même façon, sinon le suivi client
    afficherait des choses différentes selon qui a appuyé.
    """
    from storage import update_order

    # Idempotence
    if (order.get("status") or "pending") == new_status:
        return jsonify({"ok": True, "unchanged": True})

    # Update + horodatage de chaque passage d'étape. Sans eux, la progression
    # du panel ne peut afficher que « fait », jamais à quelle heure.
    try:
        upd = {"status": new_status}
        if new_status == "confirmed":
            upd["_confirmed_at"] = _now_iso()
        elif new_status == "delivering":
            upd["_delivery_started_at"] = _now_iso()
            # Owner peut préciser un temps de livraison en minutes
            try:
                eta_min = int(data.get("eta_minutes", 0))
                if 1 <= eta_min <= 240:
                    upd["_eta_minutes"] = eta_min
            except (ValueError, TypeError):
                pass
        elif new_status == "delivered":
            upd["_delivered_at"] = _now_iso()
        elif new_status == "cancelled":
            upd["_cancelled_at"] = _now_iso()
        written = update_order(order_id, upd)
    except Exception as exc:
        logger.error("admin_set_status update: %s", exc)
        return jsonify({"ok": False, "error": "update_failed"}), 500

    # update_order renvoie False si la commande n'a pas été retrouvée à
    # l'écriture : sans ce contrôle, le panel afficherait « ✅ Confirmée »
    # alors que rien n'a changé en base.
    if not written:
        logger.error("admin_set_status: écriture sans effet sur %s", order_id)
        return jsonify({"ok": False, "error": "update_failed"}), 500

    # Notifier le client via Bot API
    notified = False
    notify_error = ""
    client_id = order.get("user_id")
    client_lang = order.get("lang", "fr") if order.get("lang") in ("fr","es","en") else "fr"
    bot_token = os.getenv("BOT_TOKEN", "")
    if not client_id:
        notify_error = "no_client_id"
    elif not bot_token:
        notify_error = "no_bot_token"
    if client_id and bot_token:
        msgs = {
            "fr": {
                "confirmed":  f"✅ Votre commande N° `{order_id}` est *confirmée* !",
                "delivering": f"🚚 Votre commande N° `{order_id}` est *en cours de livraison*.",
                "delivered":  f"📦 Votre commande N° `{order_id}` a été *livrée*. Merci !",
                "cancelled":  f"❌ Votre commande N° `{order_id}` a été *annulée*.",
            },
            "en": {
                "confirmed":  f"✅ Your order #{order_id} is *confirmed*!",
                "delivering": f"🚚 Your order #{order_id} is *being delivered*.",
                "delivered":  f"📦 Your order #{order_id} has been *delivered*. Thank you!",
                "cancelled":  f"❌ Your order #{order_id} has been *cancelled*.",
            },
            "es": {
                "confirmed":  f"✅ Tu pedido N° `{order_id}` está *confirmado*.",
                "delivering": f"🚚 Tu pedido N° `{order_id}` está *en entrega*.",
                "delivered":  f"📦 Tu pedido N° `{order_id}` ha sido *entregado*. ¡Gracias!",
                "cancelled":  f"❌ Tu pedido N° `{order_id}` ha sido *cancelado*.",
            },
        }
        text = (msgs.get(client_lang) or msgs["fr"]).get(new_status, "")
        # Ajouter l'ETA au message "en livraison" si l'owner l'a précisé
        if text and new_status == "delivering":
            try:
                _em = int(upd.get("_eta_minutes", 0))
            except (ValueError, TypeError):
                _em = 0
            if _em:
                _eta_line = {
                    "fr": f"\n⏱️ Temps estimé : ~{_em} min.",
                    "en": f"\n⏱️ Estimated time: ~{_em} min.",
                    "es": f"\n⏱️ Tiempo estimado: ~{_em} min.",
                }.get(client_lang, f"\n⏱️ ~{_em} min")
                text += _eta_line
        if text:
            import httpx
            payload = {
                "chat_id":    client_id,
                "text":       text,
                "parse_mode": "Markdown",
            }
            # Si livré : envoyer aussi les boutons de notation 1-5⭐
            if new_status == "delivered":
                payload["reply_markup"] = {
                    "inline_keyboard": [[
                        {"text": "⭐",     "callback_data": f"rate:1:{order_id}"},
                        {"text": "⭐⭐",   "callback_data": f"rate:2:{order_id}"},
                        {"text": "⭐⭐⭐", "callback_data": f"rate:3:{order_id}"},
                        {"text": "⭐⭐⭐⭐",   "callback_data": f"rate:4:{order_id}"},
                        {"text": "⭐⭐⭐⭐⭐", "callback_data": f"rate:5:{order_id}"},
                    ]]
                }
            try:
                r = httpx.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json=payload,
                    timeout=10.0,
                )
                # httpx ne lève pas sur 4xx : sans cette lecture, un client qui a
                # bloqué le bot ou un Markdown invalide passeraient inaperçus et
                # l'owner croirait le client prévenu.
                if r.status_code == 200 and (r.json() or {}).get("ok"):
                    notified = True
                else:
                    notify_error = _telegram_error(r)
                    logger.warning("admin_set_status notify %s: %s", order_id, notify_error)
                    # Repli sans Markdown : la mise en forme ne doit pas coûter
                    # la notification elle-même.
                    if "parse" in (notify_error or "").lower():
                        payload.pop("parse_mode", None)
                        payload["text"] = text.replace("*", "").replace("`", "")
                        r2 = httpx.post(
                            f"https://api.telegram.org/bot{bot_token}/sendMessage",
                            json=payload,
                            timeout=10.0,
                        )
                        if r2.status_code == 200 and (r2.json() or {}).get("ok"):
                            notified, notify_error = True, ""
            except Exception as exc:
                notify_error = str(exc)
                logger.warning("admin_set_status notify client: %s", exc)

    # Le statut est bien enregistré même si le client n'a pas pu être prévenu :
    # on le dit au panel plutôt que d'afficher un succès trompeur.
    return jsonify({
        "ok": True,
        "status": new_status,
        "notified": notified,
        "notify_error": notify_error,
    })


# ═══════════════════════════════════════════════════════════════════════════
# Tracking commande client (style Uber Eats)
# ═══════════════════════════════════════════════════════════════════════════

_DRIVERS = [
    {"name": "Karim",   "emoji": "🧑🏽‍✈️"},
    {"name": "Sofia",   "emoji": "👩🏻‍✈️"},
    {"name": "Mehdi",   "emoji": "🧑🏽"},
    {"name": "Lucas",   "emoji": "👨🏻"},
    {"name": "Emma",    "emoji": "👩🏼"},
    {"name": "Yanis",   "emoji": "🧑🏽‍🦱"},
    {"name": "Chloé",   "emoji": "👩🏼‍🦰"},
    {"name": "Hugo",    "emoji": "👨🏻‍🦱"},
    {"name": "Léna",    "emoji": "👩🏻‍🦱"},
    {"name": "Adam",    "emoji": "🧑🏽‍🦲"},
]

_VEHICLES = [
    {"label": "Scooter", "emoji": "🛵"},
    {"label": "Vélo",    "emoji": "🚴"},
    {"label": "Voiture", "emoji": "🚗"},
    {"label": "Moto",    "emoji": "🏍️"},
]

# Durée totale "delivering" simulée (en secondes) : 15 min
_DELIVERY_DURATION = 15 * 60

# ── Position réelle du livreur ───────────────────────────────────────────────
# Alimentée par le partage de position en direct de l'owner dans Telegram
# (bot.py → set_driver_position). Le bot et Flask tournent dans le même
# processus : un simple dict verrouillé suffit, pas besoin de passer par le
# disque. Au-delà de _DRIVER_POS_TTL sans nouveau point, on considère que le
# partage est terminé et on retombe sur la trajectoire simulée.
_DRIVER_POS_TTL = 120          # secondes
_MIN_SPEED_KMH  = 8.0          # plancher pour ne pas annoncer une ETA absurde
_MAX_SPEED_KMH  = 90.0
_DEFAULT_SPEED_KMH = 18.0      # scooter en ville

_driver_pos: dict = {}
_driver_pos_lock = threading.Lock()


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Distance en km entre deux points GPS."""
    import math
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _bearing_deg(lat1, lon1, lat2, lon2) -> float:
    """Cap en degrés (0 = nord) du point 1 vers le point 2."""
    import math
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def set_driver_position(lat: float, lon: float, heading=None) -> dict:
    """Enregistre un point GPS du livreur. Appelé par bot.py à chaque mise à
    jour de position en direct. Déduit la vitesse et le cap du point précédent
    quand Telegram ne les fournit pas."""
    now = _now_aware()
    with _driver_pos_lock:
        prev = dict(_driver_pos) if _driver_pos else None
        speed_kmh = None
        if prev and prev.get("lat") is not None:
            dt_s = (now - prev["at"]).total_seconds()
            dist = _haversine_km(prev["lat"], prev["lon"], lat, lon)
            # En dessous de 15 m on considère que le livreur est à l'arrêt : le
            # bruit GPS produirait un cap et une vitesse aberrants.
            if dt_s > 0 and dist > 0.015:
                speed_kmh = min(_MAX_SPEED_KMH, dist / (dt_s / 3600.0))
                if heading is None:
                    heading = _bearing_deg(prev["lat"], prev["lon"], lat, lon)
            elif prev.get("heading") is not None and heading is None:
                heading = prev["heading"]
            if speed_kmh is None:
                speed_kmh = prev.get("speed_kmh")
        _driver_pos.clear()
        _driver_pos.update({
            "lat": float(lat),
            "lon": float(lon),
            "heading": float(heading) if heading is not None else None,
            "speed_kmh": speed_kmh,
            "at": now,
        })
        return dict(_driver_pos)


def clear_driver_position() -> None:
    """Fin du partage de position : on repasse en trajectoire simulée."""
    with _driver_pos_lock:
        _driver_pos.clear()


_track_far: dict[str, float] = {}


def _track_far_km(order_id: str, current_km: float) -> float:
    """Mémorise la plus grande distance vue sur cette course. Sert de référence
    à la barre de progression : sans elle, la progression repartirait à zéro à
    chaque redémarrage du partage de position."""
    with _driver_pos_lock:
        far = _track_far.get(order_id, 0.0)
        if current_km > far:
            far = current_km
            _track_far[order_id] = far
        return far


def get_driver_position() -> dict | None:
    """Position du livreur si elle est encore fraîche, sinon None."""
    with _driver_pos_lock:
        if not _driver_pos:
            return None
        pos = dict(_driver_pos)
    age = (_now_aware() - pos["at"]).total_seconds()
    if age > _DRIVER_POS_TTL:
        return None
    pos["age_seconds"] = int(age)
    return pos


def _driver_for_order(order_id: str) -> dict:
    """Choix déterministe d'un livreur depuis l'order_id (hashé)."""
    import hashlib
    h = int(hashlib.sha1(order_id.encode()).hexdigest(), 16)
    drv = _DRIVERS[h % len(_DRIVERS)]
    veh = _VEHICLES[(h // 7) % len(_VEHICLES)]
    # Note livreur entre 4.6 et 5.0
    rating = 4.6 + (h % 5) / 10.0
    # Plaque fictive type "XX-123-XX"
    chars = "ABCDEFGHJKLMNPQRSTVWXYZ"
    p1 = chars[(h     ) % len(chars)] + chars[(h >>  3) % len(chars)]
    p2 = f"{(h >> 6) % 1000:03d}"
    p3 = chars[(h >> 10) % len(chars)] + chars[(h >> 13) % len(chars)]
    plate = f"{p1}-{p2}-{p3}"
    return {
        "name":          drv["name"],
        "emoji":         drv["emoji"],
        "vehicle":       veh["label"],
        "vehicle_emoji": veh["emoji"],
        "rating":        round(rating, 1),
        "plate":         plate,
    }


@app.route("/api/client/orders", methods=["POST"])
def api_client_orders():
    """Retourne les commandes du client authentifié (via initData).
    POST {initData, limit?}
    """
    bot_token = os.getenv("BOT_TOKEN", "")
    data = _corps(request)
    init_data = data.get("initData", "")
    parsed = _verify_init_data(init_data, bot_token)
    if not parsed:
        return jsonify({"ok": False, "error": "auth_failed"}), 401

    import json as _json
    try:
        user_obj = _json.loads(parsed.get("user", "{}"))
        uid      = int(user_obj.get("id", 0))
    except Exception:
        return jsonify({"ok": False, "error": "no_user"}), 400
    if not uid:
        return jsonify({"ok": False, "error": "no_user"}), 400

    limit = _entier(data.get("limit"), 50, 1, 1000)
    try:
        from storage import _load as _load_all
        all_orders = _load_all() or []
    except Exception as exc:
        logger.error("client_orders load: %s", exc)
        return jsonify({"ok": False, "error": "load_failed"}), 500

    mine = [o for o in all_orders if int(o.get("user_id", 0)) == uid]
    mine = sorted(mine, key=lambda o: o.get("created_at", ""), reverse=True)[:limit]

    active_statuses = ("pending", "confirmed", "delivering")
    active = [o for o in mine if (o.get("status") or "pending") in active_statuses]

    def light(o):
        return {
            "order_id":   o.get("order_id"),
            "created_at": o.get("created_at"),
            "city":       o.get("city"),
            "country":    o.get("country"),
            "total":      o.get("total"),
            "payment":    o.get("payment"),
            "status":     o.get("status") or "pending",
            "rating":     o.get("rating"),
            "display_currency": o.get("display_currency") or "€",
            "cart_count": sum((o.get("cart") or {}).values()) if isinstance(o.get("cart"), dict) else 0,
            "cart":       o.get("cart") or {},
        }

    return jsonify({
        "ok":       True,
        "orders":   [light(o) for o in mine],
        "active":   [light(o) for o in active],
        "count":    len(mine),
    })


@app.route("/api/client/reorder", methods=["POST"])
def api_client_reorder():
    """Retourne les données d'une ancienne commande pour re-remplir le panier.
    POST {initData, order_id}
    Retourne : {country, city, cart} (ou error si produit plus dispo)
    """
    bot_token = os.getenv("BOT_TOKEN", "")
    data = _corps(request)
    parsed = _verify_init_data(data.get("initData", ""), bot_token)
    if not parsed:
        return jsonify({"ok": False, "error": "auth_failed"}), 401
    import json as _json
    try:
        user_obj = _json.loads(parsed.get("user", "{}"))
        uid = int(user_obj.get("id", 0))
    except Exception:
        return jsonify({"ok": False, "error": "no_user"}), 400

    order_id = _texte(data.get("order_id"))
    if not order_id:
        return jsonify({"ok": False, "error": "no_order_id"}), 400
    try:
        from storage import get_order
        order = get_order(order_id)
    except Exception:
        return jsonify({"ok": False, "error": "load_failed"}), 500
    if not order:
        return jsonify({"ok": False, "error": "not_found"}), 404
    if int(order.get("user_id", 0)) != uid:
        return jsonify({"ok": False, "error": "forbidden"}), 403

    # Vérifier que la ville existe toujours + filtrer produits encore dispo
    try:
        import catalog as catalog_mod
        importlib.reload(catalog_mod)
    except Exception:
        return jsonify({"ok": False, "error": "catalog_failed"}), 500

    country = order.get("country", "")
    city    = order.get("city", "")
    if country not in catalog_mod.CATALOG or city not in catalog_mod.CATALOG.get(country, {}):
        return jsonify({"ok": False, "error": "location_removed"}), 400

    products    = catalog_mod.CATALOG[country][city]
    old_cart    = order.get("cart") or {}
    valid_cart  = {}
    removed     = []
    for prod, qty in old_cart.items():
        if prod in products:
            try:
                valid_cart[prod] = int(qty)
            except (ValueError, TypeError):
                pass
        else:
            removed.append(prod)

    if not valid_cart:
        return jsonify({"ok": False, "error": "no_products_available"}), 400

    return jsonify({
        "ok":      True,
        "country": country,
        "city":    city,
        "cart":    valid_cart,
        "removed": removed,
    })


# ── Itinéraire routier ───────────────────────────────────────────────────────
# Le trait droit entre le livreur et l'adresse ne ressemble à rien : on trace
# le vrai chemin, rue par rue, via l'API Directions de Mapbox (même jeton que
# l'autocomplétion d'adresse). Le calcul reste côté serveur pour ne pas
# exposer le jeton, et il est mis en cache : recalculer à chaque relevé
# épuiserait le quota pour un tracé quasi identique.
_route_cache: dict[str, dict] = {}
_route_lock = threading.Lock()
_ROUTE_TTL = 75.0          # secondes avant de redemander le même trajet
_ROUTE_ECART_M = 250.0     # le livreur s'est assez écarté pour recalculer


def _itineraire_mapbox(depart, arrivee):
    """Trajet routier depart → arrivee.

    Renvoie (points, metres, secondes) où `points` est une liste [lat, lon],
    ou (None, None, None) si le service n'a rien pu fournir — l'appelant
    retombe alors sur la ligne droite, qui vaut mieux qu'une carte vide.
    """
    token = os.getenv("MAPBOX_TOKEN", "").strip()
    if not token:
        return None, None, None
    url = ("https://api.mapbox.com/directions/v5/mapbox/driving/"
           f"{depart[1]:.6f},{depart[0]:.6f};{arrivee[1]:.6f},{arrivee[0]:.6f}")
    try:
        import httpx
        r = httpx.get(url, timeout=8.0, params={
            "geometries": "geojson",
            "overview": "full",       # tracé détaillé, pas simplifié
            "access_token": token,
        })
        if r.status_code != 200:
            logger.warning("Mapbox directions HTTP %s : %s", r.status_code, r.text[:150])
            return None, None, None
        routes = (r.json() or {}).get("routes") or []
        if not routes:
            return None, None, None
        coords = routes[0].get("geometry", {}).get("coordinates") or []
        if len(coords) < 2:
            return None, None, None
        # GeoJSON donne [lon, lat] ; Leaflet attend [lat, lon].
        points = [[round(c[1], 6), round(c[0], 6)] for c in coords]
        return points, routes[0].get("distance"), routes[0].get("duration")
    except Exception as exc:
        logger.warning("Mapbox directions : %s", exc)
        return None, None, None


def _route_pour(order_id: str, depart, arrivee):
    """Itinéraire mis en cache par commande.

    Recalculé seulement si le cache est vieux ou si le livreur s'est écarté
    de plus de `_ROUTE_ECART_M` du point de départ du tracé : entre deux
    calculs, le client se contente de raccourcir le tracé existant.
    """
    maintenant = time.time()
    with _route_lock:
        entree = _route_cache.get(order_id)
        if entree:
            ecart_km = _haversine_km(depart[0], depart[1],
                                     entree["depart"][0], entree["depart"][1])
            if (maintenant - entree["at"] < _ROUTE_TTL
                    and ecart_km * 1000 < _ROUTE_ECART_M):
                return entree["points"], entree["metres"], entree["secondes"]

    points, metres, secondes = _itineraire_mapbox(depart, arrivee)
    if not points:
        return None, None, None

    with _route_lock:
        _route_cache[order_id] = {"points": points, "metres": metres,
                                  "secondes": secondes, "depart": depart,
                                  "at": maintenant}
        # Purge : une commande livrée ne sera plus jamais demandée.
        if len(_route_cache) > 200:
            for k in [k for k, v in _route_cache.items()
                      if maintenant - v["at"] > 3600]:
                del _route_cache[k]
    return points, metres, secondes


def _oublier_route(order_id: str) -> None:
    with _route_lock:
        _route_cache.pop(order_id, None)


@app.route("/api/order/track", methods=["POST"])
def api_order_track():
    """Tracking d'une commande pour le client.
    POST {initData, order_id}
    Auth : initData doit correspondre au user_id de la commande.
    """
    bot_token = os.getenv("BOT_TOKEN", "")
    data = _corps(request)
    init_data = data.get("initData", "")
    parsed = _verify_init_data(init_data, bot_token)
    if not parsed:
        return jsonify({"ok": False, "error": "auth_failed"}), 401

    import json as _json
    try:
        user_obj = _json.loads(parsed.get("user", "{}"))
        client_uid = int(user_obj.get("id", 0))
    except Exception:
        return jsonify({"ok": False, "error": "no_user"}), 400

    order_id = _texte(data.get("order_id"))
    if not order_id:
        return jsonify({"ok": False, "error": "no_order_id"}), 400

    # Charger la commande
    try:
        from storage import get_order
        order = get_order(order_id)
    except Exception:
        return jsonify({"ok": False, "error": "load_failed"}), 500
    if not order:
        return jsonify({"ok": False, "error": "not_found"}), 404

    # Vérifier que c'est bien la commande de l'user (ou owner)
    owner_uid = os.getenv("OWNER_USER_ID", "")
    if int(order.get("user_id", 0)) != client_uid and str(client_uid) != str(owner_uid):
        return jsonify({"ok": False, "error": "forbidden"}), 403

    status = order.get("status", "pending")
    driver = _driver_for_order(order_id)

    # Coordonnées destination
    try:
        dest_lat = float(order.get("address_lat") or order.get("lat") or 0)
        dest_lon = float(order.get("address_lon") or order.get("lon") or 0)
    except Exception:
        dest_lat = 0.0
        dest_lon = 0.0
    # Fallback : parser maps_link "?mlat=X&mlon=Y"
    if (dest_lat == 0.0 or dest_lon == 0.0) and order.get("maps_link"):
        try:
            import re as _re
            m_lat = _re.search(r"mlat=([\-0-9.]+)", order["maps_link"])
            m_lon = _re.search(r"mlon=([\-0-9.]+)", order["maps_link"])
            if m_lat and m_lon:
                dest_lat = float(m_lat.group(1))
                dest_lon = float(m_lon.group(1))
        except Exception:
            pass

    # ETA calculée à partir de _eta_minutes défini par l'owner (défaut 15 min)
    eta_seconds = None
    progress    = 0.0   # 0..1 (0 = vient de partir, 1 = arrivé)
    duration_seconds = _DELIVERY_DURATION
    try:
        if order.get("_eta_minutes"):
            duration_seconds = int(order.get("_eta_minutes")) * 60
    except (ValueError, TypeError):
        pass

    if status == "delivering":
        start   = _parse_dt(order.get("_delivery_started_at"))
        elapsed = (_now_aware() - start).total_seconds() if start else 0.0
        progress = max(0.0, min(1.0, elapsed / duration_seconds))
        eta_seconds = max(0, int(duration_seconds - elapsed))
    elif status == "delivered":
        progress = 1.0
        eta_seconds = 0

    # Position du livreur : la vraie si l'owner partage sa position en direct,
    # sinon la trajectoire simulée (comportement historique).
    driver_lat = driver_lon = None
    driver_heading = None
    is_live = False
    distance_km = None

    live = get_driver_position() if status == "delivering" else None
    if live and dest_lat and dest_lon:
        driver_lat = live["lat"]
        driver_lon = live["lon"]
        driver_heading = live.get("heading")
        if driver_heading is None:
            driver_heading = _bearing_deg(driver_lat, driver_lon, dest_lat, dest_lon)
        is_live = True
        distance_km = _haversine_km(driver_lat, driver_lon, dest_lat, dest_lon)
        # ETA sur la distance restante réelle plutôt que sur un minuteur fixe.
        # Majoration de 30 % : à vol d'oiseau on sous-estime toujours la route.
        speed = live.get("speed_kmh") or _DEFAULT_SPEED_KMH
        speed = max(_MIN_SPEED_KMH, min(_MAX_SPEED_KMH, speed))
        eta_seconds = int((distance_km * 1.3) / speed * 3600)
        # La barre de progression se cale sur la distance parcourue, en gardant
        # en mémoire le point le plus lointain vu pour cette course.
        far = _track_far_km(order_id, distance_km)
        progress = max(0.0, min(1.0, 1.0 - (distance_km / far))) if far else 0.0

    elif dest_lat and dest_lon and status in ("delivering", "delivered"):
        # Trajectoire simulée : point de départ déterministe dérivé de l'order_id
        import hashlib
        h = int(hashlib.sha1(order_id.encode()).hexdigest(), 16)
        radius_km = 2.5
        # 1 deg lat ≈ 111 km
        start_lat = dest_lat + (radius_km / 111.0) * (1 if (h >> 4) % 2 else -1) * 0.5
        start_lon = dest_lon + (radius_km / 111.0) * (1 if (h >> 5) % 2 else -1) * 0.5
        # Interpolation
        driver_lat = start_lat + (dest_lat - start_lat) * progress
        driver_lon = start_lon + (dest_lon - start_lon) * progress
        driver_heading = _bearing_deg(driver_lat, driver_lon, dest_lat, dest_lon) \
            if progress < 1.0 else None
        distance_km = _haversine_km(driver_lat, driver_lon, dest_lat, dest_lon)

    # ── Itinéraire réel, rue par rue ────────────────────────────────────────
    # Tant qu'on n'a pas le tracé, le client verra la ligne droite ; dès qu'il
    # arrive, la distance et l'ETA passent en distance ROUTIÈRE, toujours plus
    # longue que le vol d'oiseau et donc plus honnête.
    route = None
    if driver_lat is not None and dest_lat and dest_lon and status == "delivering":
        route, metres, secondes = _route_pour(
            order_id, (driver_lat, driver_lon), (dest_lat, dest_lon))
        if route and metres:
            distance_km = metres / 1000.0
            if secondes:
                eta_seconds = int(secondes)
            far = _track_far_km(order_id, distance_km)
            progress = max(0.0, min(1.0, 1.0 - (distance_km / far))) if far else 0.0
    elif status == "delivered":
        _oublier_route(order_id)

    # Étapes visuelles
    steps_status = {
        "received":    True,                                                        # reçue : toujours OK
        "preparing":   status in ("confirmed", "delivering", "delivered"),         # préparée
        "delivering":  status in ("delivering", "delivered"),                       # en route
        "delivered":   status == "delivered",                                       # livrée
    }
    # Heure de passage de chaque étape, pour l'afficher sous la timeline.
    # Ces horodatages sont posés par le panel à chaque changement de statut.
    step_times = {
        "received":   order.get("created_at"),
        "preparing":  order.get("_confirmed_at"),
        "delivering": order.get("_delivery_started_at"),
        "delivered":  order.get("_delivered_at"),
    }
    step_times = {k: v for k, v in step_times.items() if v and steps_status.get(k)}

    # Heure d'arrivée estimée, calculée côté serveur pour que tout le monde
    # lise la même : le téléphone du client peut être à la mauvaise heure.
    eta_at = None
    if eta_seconds is not None and status == "delivering":
        from datetime import timedelta as _td
        eta_at = (_now_aware() + _td(seconds=eta_seconds)).isoformat(timespec="seconds")

    return jsonify({
        "ok":        True,
        "order_id":  order_id,
        "status":    status,
        "rating":    order.get("rating"),
        "driver":    driver,
        "eta_seconds": eta_seconds,
        "progress":  progress,
        "dest": {
            "lat": dest_lat or None,
            "lon": dest_lon or None,
            "address": order.get("address"),
        },
        "driver_pos": (
            {
                "lat": driver_lat,
                "lon": driver_lon,
                "heading": driver_heading,
                "live": is_live,
                "age_seconds": (live or {}).get("age_seconds") if is_live else None,
            }
            if driver_lat is not None else None
        ),
        # Le client doit savoir s'il regarde une position réelle ou une estimation.
        "live":        is_live,
        "distance_km": round(distance_km, 2) if distance_km is not None else None,
        # Tracé routier [[lat, lon], …]. Absent = le client trace la ligne droite.
        "route":       route,
        "steps": steps_status,
        "step_times": step_times,
        "eta_at": eta_at,
        "city":  order.get("city"),
        "total": order.get("total"),
        "display_currency": order.get("display_currency") or "€",
        # De quoi remplir « Voir les détails de la commande » sans second appel.
        "cart":    order.get("cart") or {},
        "address": order.get("address") or "",
        "payment": order.get("payment") or "",
        "created_at": order.get("created_at"),
    })


# ═══════════════════════════════════════════════════════════════════════════
# Notes privées sur les clients (visible seulement par l'owner)
# ═══════════════════════════════════════════════════════════════════════════
_CLIENT_NOTES_FILE = None   # calculé au démarrage
_client_notes_cache: dict[str, str] = {}   # {user_id_str: note}
_client_notes_lock = threading.Lock()
_client_notes_loaded = False


def _notes_file_path():
    global _CLIENT_NOTES_FILE
    if _CLIENT_NOTES_FILE is None:
        from pathlib import Path
        data_dir = os.getenv("DATA_DIR", str(Path(__file__).parent))
        _CLIENT_NOTES_FILE = os.path.join(data_dir, "client_notes.json")
    return _CLIENT_NOTES_FILE


def _load_notes():
    global _client_notes_loaded
    with _client_notes_lock:
        if _client_notes_loaded:
            return _client_notes_cache
        try:
            import json as _json
            p = _notes_file_path()
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    data = _json.load(f)
                    if isinstance(data, dict):
                        _client_notes_cache.update({str(k): str(v) for k, v in data.items()})
        except Exception as exc:
            logger.warning("load notes: %s", exc)
        _client_notes_loaded = True
        return _client_notes_cache


def _save_notes():
    """Écriture atomique : write .tmp puis os.replace (rename atomique POSIX/NT).
    Évite la corruption du fichier si le worker crashe mid-write.
    """
    with _client_notes_lock:
        try:
            import json as _json
            p = _notes_file_path()
            tmp = p + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                _json.dump(_client_notes_cache, f, ensure_ascii=False, indent=2)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
            os.replace(tmp, p)
        except Exception as exc:
            logger.error("save notes: %s", exc)


@app.route("/api/admin/client_note", methods=["POST"])
def api_admin_client_note():
    """GET la note ou POST/PUT/DELETE.
    POST {initData, user_id, action: 'get'|'set'|'delete', note?}
    """
    _refus = _guard_admin(request)
    if _refus:
        return _refus
    data = _corps(request)
    try:
        uid = str(int(data.get("user_id", 0)))
    except (ValueError, TypeError):
        return jsonify({"ok": False, "error": "bad_uid"}), 400
    if uid == "0":
        return jsonify({"ok": False, "error": "bad_uid"}), 400

    action = (data.get("action") or "get").strip()
    notes = _load_notes()

    if action == "get":
        return jsonify({"ok": True, "note": notes.get(uid, "")})
    if action == "set":
        note = _texte(data.get("note"))
        if len(note) > 2000:
            return jsonify({"ok": False, "error": "too_long"}), 400
        with _client_notes_lock:
            if note:
                notes[uid] = note
            else:
                notes.pop(uid, None)
        _save_notes()
        return jsonify({"ok": True, "note": note})
    if action == "delete":
        with _client_notes_lock:
            notes.pop(uid, None)
        _save_notes()
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "bad_action"}), 400


@app.route("/api/admin/clients", methods=["POST"])
def api_admin_clients():
    """Répertoire des clients uniques agrégé depuis toutes les commandes.
    POST {initData, segment?}
    segment : "all" (default), "active", "dormant", "vip"
    """
    _refus = _guard_admin(request)
    if _refus:
        return _refus

    data = _corps(request)
    segment = (data.get("segment") or "all").strip()

    try:
        from storage import _load as _load_all
        from datetime import datetime as _dt, timedelta as _td
        all_orders = _load_all() or []
    except Exception as exc:
        logger.error("clients load: %s", exc)
        return jsonify({"ok": False, "error": "load_failed"}), 500

    # Agrégation par user_id
    clients: dict[int, dict] = {}
    now = _dt.now()
    cutoff_dormant = now - _td(days=30)

    for o in all_orders:
        uid = int(o.get("user_id") or 0)
        if not uid:
            continue
        c = clients.get(uid)
        if c is None:
            c = {
                "user_id":     uid,
                "user_name":   o.get("user_name") or "",
                "username":    o.get("username") or "",
                "lang":        o.get("lang") or "fr",
                "orders":      0,
                "total_spent": 0.0,
                "last_order":  "",
                "first_order": "",
                "city":        o.get("city"),
                "country":     o.get("country"),
            }
            clients[uid] = c
        s = o.get("status") or "pending"
        # Le total dépensé exclut les annulées
        if s not in _CANCELLED_STATUSES:
            c["total_spent"] += float(o.get("total", 0) or 0)
        c["orders"] += 1
        created = o.get("created_at") or ""
        if created > c["last_order"]:
            c["last_order"] = created
            # Prendre les infos les plus récentes
            if o.get("user_name"):    c["user_name"]    = o.get("user_name")
            if o.get("username"):     c["username"]     = o.get("username")
            if o.get("lang"):         c["lang"]         = o.get("lang")
            if o.get("city"):         c["city"]         = o.get("city")
            if o.get("country"):      c["country"]      = o.get("country")
        if not c["first_order"] or created < c["first_order"]:
            c["first_order"] = created

    # Segmentation
    def _seg(c):
        try:
            last = _dt.fromisoformat(c["last_order"])
            if last.tzinfo is not None:
                last = last.astimezone().replace(tzinfo=None)
        except Exception:
            last = _dt.min
        if c["orders"] >= 3 or c["total_spent"] >= 500:
            base = "vip"
        elif last >= cutoff_dormant:
            base = "active"
        else:
            base = "dormant"
        return base

    for c in clients.values():
        c["segment"] = _seg(c)

    # Filtrer par segment demandé
    result = list(clients.values())
    if segment == "active":
        result = [c for c in result if c["segment"] == "active"]
    elif segment == "dormant":
        result = [c for c in result if c["segment"] == "dormant"]
    elif segment == "vip":
        result = [c for c in result if c["segment"] == "vip"]
    # all → pas de filtre

    # Tri par dernière commande (récent → ancien)
    result.sort(key=lambda c: c.get("last_order", ""), reverse=True)

    # Counts globaux (peu importe le filtre)
    counts = {"all": len(clients), "active": 0, "dormant": 0, "vip": 0}
    for c in clients.values():
        counts[c["segment"]] += 1

    return jsonify({
        "ok":      True,
        "clients": result,
        "counts":  counts,
    })


# Throttle broadcast : 25 msg/s max
_BROADCAST_DELAY = 0.05
# Jobs de broadcast en cours (state en mémoire, key = job_id)
_broadcast_jobs: dict[str, dict] = {}
_broadcast_lock = threading.Lock()


def _compute_client_segments():
    """Retourne (clients_dict, segments_dict) agrégés depuis orders.json."""
    from storage import _load as _load_all
    from datetime import datetime as _dt, timedelta as _td
    all_orders = _load_all() or []
    now = _dt.now()
    cutoff_dormant = now - _td(days=30)
    clients: dict[int, dict] = {}
    for o in all_orders:
        uid = int(o.get("user_id") or 0)
        if not uid:
            continue
        c = clients.get(uid)
        if c is None:
            c = {"user_id": uid, "orders": 0, "total_spent": 0.0, "last_order": ""}
            clients[uid] = c
        s = o.get("status") or "pending"
        if s not in _CANCELLED_STATUSES:
            c["total_spent"] += float(o.get("total", 0) or 0)
        c["orders"] += 1
        created = o.get("created_at") or ""
        if created > c["last_order"]:
            c["last_order"] = created

    for c in clients.values():
        try:
            last = _dt.fromisoformat(c["last_order"])
            if last.tzinfo is not None:
                last = last.astimezone().replace(tzinfo=None)
        except Exception:
            last = _dt.min
        if c["orders"] >= 3 or c["total_spent"] >= 500:
            c["segment"] = "vip"
        elif last >= cutoff_dormant:
            c["segment"] = "active"
        else:
            c["segment"] = "dormant"
    return clients


def _run_broadcast_job(job_id: str, targets: list[int], text: str, bot_token: str):
    """Thread worker qui envoie les messages sans bloquer le worker Flask.
    Robustesse :
      - Détecte Markdown mal formé (400) sur le 1er envoi → fallback plain text pour tout le batch
      - Respecte le retry_after de Telegram sur 429
      - Comptabilise séparément les users qui ont bloqué le bot (403)
    """
    import httpx as _httpx
    sent = failed = blocked = 0
    use_markdown = True

    def _send(client, uid, use_md):
        body = {"chat_id": uid, "text": text}
        if use_md:
            body["parse_mode"] = "Markdown"
        return client.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json=body,
        )

    with _httpx.Client(timeout=10.0) as c:
        for i, uid in enumerate(targets):
            attempt = 0
            while True:
                attempt += 1
                try:
                    r = _send(c, uid, use_markdown)
                    if r.status_code == 200:
                        sent += 1
                        break
                    # Rate limit → attendre retry_after et réessayer (1x)
                    if r.status_code == 429 and attempt <= 2:
                        try:
                            retry_after = int(r.json().get("parameters", {}).get("retry_after", 3))
                        except Exception:
                            retry_after = 3
                        time.sleep(min(retry_after, 30))
                        continue
                    # User a bloqué le bot / chat introuvable
                    if r.status_code == 403:
                        blocked += 1
                        break
                    # Parse Markdown mal formé sur le 1er user → disable Markdown pour tout le reste
                    if r.status_code == 400 and use_markdown and i == 0 and attempt == 1:
                        use_markdown = False
                        continue
                    failed += 1
                    break
                except Exception:
                    failed += 1
                    break
            # Update job state
            with _broadcast_lock:
                if job_id in _broadcast_jobs:
                    _broadcast_jobs[job_id]["sent"]     = sent
                    _broadcast_jobs[job_id]["failed"]   = failed
                    _broadcast_jobs[job_id]["blocked"]  = blocked
                    _broadcast_jobs[job_id]["progress"] = i + 1
                    if _broadcast_jobs[job_id].get("cancelled"):
                        _broadcast_jobs[job_id]["status"] = "cancelled"
                        _broadcast_jobs[job_id]["ended_at"] = time.time()
                        return
            time.sleep(_BROADCAST_DELAY)
    with _broadcast_lock:
        if job_id in _broadcast_jobs:
            _broadcast_jobs[job_id]["status"] = "done"
            _broadcast_jobs[job_id]["ended_at"] = time.time()
            _broadcast_jobs[job_id]["markdown_used"] = use_markdown


@app.route("/api/admin/broadcast", methods=["POST"])
def api_admin_broadcast():
    """Démarre un envoi broadcast en background thread.
    POST {initData, text, segment?}
    Retourne {ok, job_id, total} — utiliser /api/admin/broadcast/status/<job_id> pour poll.
    """
    _refus = _guard_admin(request)
    if _refus:
        return _refus

    data = _corps(request)
    text    = _texte(data.get("text"))
    segment = (data.get("segment") or "all").strip()

    if not text:
        return jsonify({"ok": False, "error": "empty_text"}), 400
    if len(text) > 3500:
        return jsonify({"ok": False, "error": "too_long"}), 400

    bot_token = os.getenv("BOT_TOKEN", "")
    if not bot_token:
        return jsonify({"ok": False, "error": "no_token"}), 500

    try:
        clients = _compute_client_segments()
    except Exception:
        return jsonify({"ok": False, "error": "load_failed"}), 500

    targets = [uid for uid, c in clients.items() if segment == "all" or c["segment"] == segment]

    if not targets:
        return jsonify({"ok": True, "job_id": None, "total": 0})

    # Créer le job + démarrer thread
    import uuid
    job_id = uuid.uuid4().hex[:12]
    with _broadcast_lock:
        _broadcast_jobs[job_id] = {
            "status":    "running",
            "total":     len(targets),
            "sent":      0,
            "failed":    0,
            "blocked":   0,
            "progress":  0,
            "segment":   segment,
            "started_at": time.time(),
        }
        # Nettoyer les vieux jobs (> 1h)
        for jid in list(_broadcast_jobs.keys()):
            if time.time() - _broadcast_jobs[jid].get("started_at", 0) > 3600:
                del _broadcast_jobs[jid]

    threading.Thread(
        target=_run_broadcast_job,
        args=(job_id, targets, text, bot_token),
        daemon=True,
    ).start()

    return jsonify({
        "ok":     True,
        "job_id": job_id,
        "total":  len(targets),
    })


@app.route("/api/admin/broadcast/status/<job_id>", methods=["POST"])
def api_admin_broadcast_status(job_id):
    """Retourne le statut d'un broadcast en cours."""
    _refus = _guard_admin(request)
    if _refus:
        return _refus
    with _broadcast_lock:
        job = _broadcast_jobs.get(job_id)
        if not job:
            return jsonify({"ok": False, "error": "not_found"}), 404
        return jsonify({"ok": True, **job})


@app.route("/api/admin/broadcast/cancel/<job_id>", methods=["POST"])
def api_admin_broadcast_cancel(job_id):
    """Annule un broadcast en cours."""
    _refus = _guard_admin(request)
    if _refus:
        return _refus
    with _broadcast_lock:
        job = _broadcast_jobs.get(job_id)
        if not job:
            return jsonify({"ok": False, "error": "not_found"}), 404
        job["cancelled"] = True
    return jsonify({"ok": True})


@app.route("/api/admin/send_message", methods=["POST"])
def api_admin_send_message():
    """L'owner envoie un message libre à un client via le bot.
    POST {initData, user_id, text}
    """
    _refus = _guard_admin(request)
    if _refus:
        return _refus
    data = _corps(request)
    try:
        target_uid = int(data.get("user_id", 0))
    except (ValueError, TypeError):
        target_uid = 0
    text = _texte(data.get("text"))
    if not target_uid or not text:
        return jsonify({"ok": False, "error": "missing_args"}), 400
    if len(text) > 3500:
        return jsonify({"ok": False, "error": "too_long"}), 400

    bot_token = os.getenv("BOT_TOKEN", "")
    if not bot_token:
        return jsonify({"ok": False, "error": "no_token"}), 500

    try:
        import httpx
        r = httpx.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={
                "chat_id": target_uid,
                "text":    "📩 *Message de l'équipe Millésime :*\n\n" + text,
                "parse_mode": "Markdown",
            },
            timeout=10.0,
        )
        if r.status_code != 200:
            logger.warning("admin_send_message failed %s: %s", r.status_code, r.text[:200])
            return jsonify({"ok": False, "error": "send_failed", "detail": r.text[:200]}), 502
    except Exception as exc:
        logger.error("admin_send_message exception: %s", exc)
        return jsonify({"ok": False, "error": "exception"}), 500

    return jsonify({"ok": True})


_bot_username_cache = {"nom": "", "at": 0.0}


def _bot_username() -> str:
    """@username du bot, mis en cache 1 h (getMe)."""
    now = time.time()
    if _bot_username_cache["nom"] and now - _bot_username_cache["at"] < 3600:
        return _bot_username_cache["nom"]
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        return ""
    try:
        import httpx
        r = httpx.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10.0)
        nom = (r.json().get("result") or {}).get("username", "") if r.status_code == 200 else ""
    except Exception as exc:
        logger.warning("getMe: %s", exc)
        nom = ""
    if nom:
        _bot_username_cache.update(nom=nom, at=now)
    return nom


@app.route("/api/admin/contact", methods=["POST"])
def api_admin_contact():
    """Raccourci vers la conversation avec le client d'une commande.

    POST {initData, order_id} ou {initData, user_id}

    Un client sans @username n'a aucun lien t.me : la seule façon d'ouvrir sa
    conversation est un lien `tg://user?id=` — que la Mini App ne peut pas
    ouvrir elle-même, mais qu'un message du bot peut porter. On envoie donc à
    l'admin connecté (n'importe quel compte, cf. mot de passe unifié) un message
    avec ce lien, et on le renvoie vers le chat du bot où il n'a qu'à appuyer.
    """
    _refus = _guard_admin(request)
    if _refus:
        return _refus
    admin_uid = _uid_authentifie(request)
    data = _corps(request)
    order_id = _texte(data.get("order_id"))
    try:
        demande_uid = int(data.get("user_id") or 0)
    except (ValueError, TypeError):
        demande_uid = 0

    from storage import get_order
    order = get_order(order_id) if order_id else None
    if not order and demande_uid:
        # Répertoire clients : pas de commande précise, on prend la plus
        # récente de ce client pour récupérer son pseudo et son nom.
        from storage import _load as _load_all
        siennes = [o for o in _load_all()
                   if str(o.get("user_id") or "") == str(demande_uid)]
        siennes.sort(key=lambda o: o.get("created_at") or "")
        order = siennes[-1] if siennes else {"user_id": demande_uid}
    if not order:
        return jsonify({"ok": False, "error": "order_not_found"}), 404
    order_id = str(order.get("order_id") or order_id or "")

    try:
        client_uid = int(order.get("user_id") or 0)
    except (ValueError, TypeError):
        client_uid = 0
    username = (order.get("username") or "").lstrip("@").strip()
    nom = (order.get("user_name") or "").strip() or (f"#{client_uid}" if client_uid else "client")

    # Cas simple : un @username, donc un lien t.me directement ouvrable.
    if username:
        return jsonify({"ok": True, "mode": "username",
                        "link": f"https://t.me/{username}", "name": nom})

    if not client_uid:
        return jsonify({"ok": False, "error": "no_user_id"}), 400
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        return jsonify({"ok": False, "error": "no_token"}), 500
    if not admin_uid:
        return jsonify({"ok": False, "error": "no_admin_uid"}), 400

    ville = " · ".join(x for x in [order.get("city"), order.get("country")] if x)
    texte = (
        f"👤 <b>{_html_escape(nom)}</b>"
        + (f"\nCommande N° <code>{_html_escape(order_id)}</code>" if order_id else "")
        + (f"\n{_html_escape(ville)}" if ville else "")
        + f"\n\n➤ <a href=\"tg://user?id={client_uid}\">Ouvrir la conversation</a>"
    )
    try:
        import httpx
        r = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": admin_uid,
                "text": texte,
                "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": [[
                    {"text": f"💬 Écrire à {nom}"[:60],
                     "url": f"tg://user?id={client_uid}"},
                ]]},
            },
            timeout=10.0,
        )
        if r.status_code != 200:
            logger.warning("admin_contact sendMessage %s: %s", r.status_code, r.text[:200])
            return jsonify({"ok": False, "error": "send_failed",
                            "detail": _telegram_error(r)}), 502
    except Exception as exc:
        logger.error("admin_contact: %s", exc)
        return jsonify({"ok": False, "error": "exception"}), 500

    bot_nom = _bot_username()
    return jsonify({"ok": True, "mode": "bot", "name": nom,
                    "link": f"https://t.me/{bot_nom}" if bot_nom else ""})


@app.route("/api/admin/selfie/envoyer", methods=["POST"])
def api_admin_selfie_envoyer():
    """Envoie le selfie dans le chat Telegram de celui qui le demande.

    Aucune page web ne peut écrire dans la pellicule d'un iPhone : c'est une
    protection du système, pas une limite de l'application. Le chemin le plus
    court reste donc la feuille de partage iOS ; quand elle n'est pas
    disponible, on pousse la photo dans le chat, où l'appui long propose
    « Enregistrer dans les photos ».
    POST {initData, order_id}
    """
    _refus = _guard_admin(request)
    if _refus:
        return _refus
    uid = _uid_authentifie(request)
    order_id = _texte(_corps(request).get("order_id"), 64)
    try:
        from storage import get_order
        order = get_order(order_id)
    except Exception:
        return jsonify({"ok": False, "error": "load_failed"}), 500
    if not order:
        return jsonify({"ok": False, "error": "not_found"}), 404
    b64 = order.get("selfie_b64") or ""
    if not b64:
        return jsonify({"ok": False, "error": "no_photo"}), 404
    token = os.getenv("BOT_TOKEN", "")
    if not token or not uid:
        return jsonify({"ok": False, "error": "no_token"}), 500
    try:
        photo = base64.b64decode(b64)
        import httpx
        r = httpx.post(
            f"https://api.telegram.org/bot{token}/sendPhoto",
            data={"chat_id": str(uid),
                  "caption": f"📸 Selfie — commande {order_id}\n"
                             "Appui long sur la photo → « Enregistrer dans les photos »."},
            files={"photo": (f"selfie-{order_id}.jpg", photo, "image/jpeg")},
            timeout=20.0)
        if r.status_code != 200:
            return jsonify({"ok": False, "error": "send_failed",
                            "detail": _telegram_error(r)}), 502
    except Exception as exc:
        logger.error("selfie_envoyer: %s", exc)
        return jsonify({"ok": False, "error": "exception"}), 500
    return jsonify({"ok": True})


@app.route("/api/admin/photo/<order_id>/<kind>", methods=["GET"])
def api_admin_photo(order_id, kind):
    """Sert une photo (selfie ou proof) de la commande en JPEG.
    Auth via initData en query string : ?initData=...
    """
    # Cette route sert les selfies clients : elle doit suivre le même verrou
    # que le reste du panel, sinon les photos resteraient accessibles alors
    # que l'admin est verrouillé.
    uid = _uid_authentifie(request)
    if uid is None:
        return ("Forbidden", 403)
    if not _a_acces_admin(uid):
        return ("Locked", 403)
    if kind not in ("selfie", "proof"):
        return ("Bad kind", 400)
    try:
        from storage import get_order
        order = get_order(order_id)
    except Exception:
        return ("Server error", 500)
    if not order:
        return ("Not found", 404)
    b64 = order.get("selfie_b64" if kind == "selfie" else "proof_b64", "")
    if not b64:
        return ("No photo", 404)
    try:
        photo_bytes = base64.b64decode(b64)
    except Exception:
        return ("Bad photo", 500)
    from flask import Response
    entetes = {"Cache-Control": "private, max-age=300"}
    # ?download=1 → le navigateur enregistre le fichier au lieu de l'afficher,
    # ce qui permet au bouton « Enregistrer la photo » du panel de viser la
    # pellicule plutôt que d'ouvrir un onglet.
    if request.args.get("download"):
        entetes["Content-Disposition"] = f'attachment; filename="{kind}-{order_id}.jpg"'
    return Response(photo_bytes, mimetype="image/jpeg", headers=entetes)


# ═════════════════════════════════════════════════════════════════════════════
# Messagerie privée vendeur ↔ client, dans la Mini App
# ═════════════════════════════════════════════════════════════════════════════

def _qui_parle(req):
    """Identifie l'appelant d'un endpoint de messagerie.

    Renvoie (role, client_id, erreur). Le vendeur doit préciser le client avec
    qui il discute ; un client ne peut jamais désigner que lui-même — sans
    quoi il lirait la conversation des autres.
    """
    uid = _uid_authentifie(req)
    if uid is None:
        return None, None, (jsonify({"ok": False, "error": "auth_failed"}), 401)
    data = _corps(req)
    if _a_acces_admin(uid):
        client_id = _entier(data.get("client_id"), 0, 0, 10 ** 15)
        if client_id:
            return chat.VENDEUR, client_id, None
        # Admin sans destinataire : c'est le mode client (« Discuter avec le
        # vendeur »). On lui ouvre son propre fil plutôt qu'une erreur.
        return chat.CLIENT, uid, None
    # Le livreur désigne la conversation par une référence opaque, jamais par
    # l'identifiant Telegram du client : il parle « à la commande », pas à une
    # personne qu'il pourrait ensuite retrouver hors de l'application.
    if _a_acces_livreur(uid):
        client_id, _cmd = _resoudre_ref_chat(data.get("chat_ref"))
        if not client_id:
            return None, None, (jsonify({"ok": False, "error": "ref_inconnue"}), 400)
        return chat.VENDEUR, client_id, None
    return chat.CLIENT, uid, None


# ── Présence dans l'application ──────────────────────────────────────────────
# L'API des bots ne donne pas le statut « en ligne » de Telegram : aucun bot ne
# peut le connaître. On montre donc ce qui compte vraiment pendant une
# livraison — la personne est-elle dans l'application, en train de lire.
# En mémoire seulement : une présence n'a aucun intérêt après un redémarrage.
_presences: dict[str, float] = {}
_presence_lock = threading.Lock()
_PRESENCE_EN_LIGNE = 45          # secondes : au-delà, on n'est plus « en ligne »


def _marquer_presence(uid) -> None:
    if not uid:
        return
    with _presence_lock:
        _presences[str(uid)] = time.time()
        if len(_presences) > 3000:
            limite = time.time() - 86400
            for k in [k for k, t in _presences.items() if t < limite]:
                del _presences[k]


def _presence(uid):
    """Secondes depuis la dernière activité, ou None si jamais vue."""
    with _presence_lock:
        vu = _presences.get(str(uid))
    return int(time.time() - vu) if vu else None


def _langue_client(client_id) -> str:
    """Langue du client, telle qu'il l'a choisie à l'entrée de la boutique."""
    try:
        from storage import _load as _load_all
        siennes = [o for o in _load_all()
                   if str(o.get("user_id") or "") == str(client_id)]
    except Exception:
        siennes = []
    siennes.sort(key=lambda o: o.get("created_at") or "")
    for o in reversed(siennes):
        lg = (o.get("lang") or "").strip().lower()
        if lg in ("fr", "en", "es"):
            return lg
    return ""


def _langue_lecture_client(client_id) -> str:
    """Langue dans laquelle CE client lit : celle choisie à l'entrée de la
    boutique, sinon celle de ses propres messages, anglais en dernier recours."""
    return _langue_client(client_id) or chat.langue_ecrite(client_id) or "en"


def _traduire_message(texte: str, role: str, client_id):
    """(langue détectée, {langue: traduction}) pour un message qui part.

    Le côté boutique (owner et livreur) travaille en français ; le client,
    dans la langue qu'il a choisie — anglais par défaut quand on l'ignore.
    Une traduction qui échoue n'empêche jamais l'envoi : le message part dans
    sa langue d'origine.
    """
    texte = (texte or "").strip()
    if not texte:
        return "", {}
    try:
        import traduction
    except Exception:
        return "", {}

    source = traduction.detecter(texte)
    if role == chat.CLIENT:
        cibles = ["fr"]                      # la boutique lit en français
    else:
        cibles = [_langue_lecture_client(client_id)]
    trads = {}
    for cible in cibles:
        if cible and cible != source:
            resultat = traduction.traduire(texte, cible, source)
            if resultat:
                trads[cible] = resultat
    return source, trads


def _selfie_avatar(client_id, pour_livreur: bool = False) -> str:
    """Chemin de la photo de profil d'un fil : le dernier selfie du client.

    Le selfie est déjà la photo de contrôle de la boutique — c'est ce visage
    que l'owner comme le livreur associent à la commande. On le sert par les
    routes photo existantes, qui portent déjà les bons contrôles d'accès :
    panel déverrouillé côté admin, zone côté livreur.
    """
    try:
        from storage import _load as _load_all
        siens = [o for o in _load_all()
                 if str(o.get("user_id") or "") == str(client_id)
                 and o.get("selfie_b64")]
    except Exception:
        return ""
    if pour_livreur:
        siens = [o for o in siens if _dans_zone_livreur(o)]
    if not siens:
        return ""
    siens.sort(key=lambda o: o.get("created_at") or "")
    oid = str(siens[-1].get("order_id") or "")
    if not oid:
        return ""
    return (f"/api/livreur/course/{oid}/selfie" if pour_livreur
            else f"/api/admin/photo/{oid}/selfie")


def _filtrer_contacts(req, client_id) -> bool:
    """Faut-il empêcher l'échange de coordonnées dans ce fil ?

    Oui dès qu'un livreur est impliqué : quand c'est lui qui écrit, et quand
    le client répond alors qu'une de ses commandes est en cours dans une zone
    livreur. L'owner n'est jamais filtré — c'est sa boutique, il donne son
    numéro à qui il veut.
    """
    uid = _uid_authentifie(req)
    if uid is None or _a_acces_admin(uid):
        return False
    if _a_acces_livreur(uid):
        return True
    if not _livreur_password():
        return False
    # Côté client : seulement pendant qu'une course est entre les mains d'un
    # livreur. Une fois livré, il redialogue normalement avec la boutique.
    try:
        from storage import _load as _load_all
        return any(
            str(o.get("user_id") or "") == str(client_id)
            and (o.get("status") or "pending") in ("pending", "confirmed", "delivering")
            and _dans_zone_livreur(o)
            for o in (_load_all() or []))
    except Exception:
        return False


def _profil_client(uid) -> dict:
    """Nom et pseudo du client, repris de sa commande la plus récente."""
    try:
        from storage import _load as _load_all
        siennes = [o for o in _load_all() if str(o.get("user_id") or "") == str(uid)]
    except Exception:
        siennes = []
    siennes.sort(key=lambda o: o.get("created_at") or "")
    dernier = siennes[-1] if siennes else {}
    return {
        "user_name": dernier.get("user_name") or "",
        "username": dernier.get("username") or "",
        "city": dernier.get("city") or "",
        "country": dernier.get("country") or "",
    }


@app.route("/api/chat/thread", methods=["POST"])
def api_chat_thread():
    """Messages d'une conversation. POST {initData, client_id?}"""
    role, client_id, erreur = _qui_parle(request)
    if erreur:
        return erreur
    # Celui qui consulte le fil est, par définition, présent.
    _marquer_presence(_uid_authentifie(request))
    chat.marquer_lu(client_id, role)

    # Le livreur ne reçoit ni profil ni identifiant : ni nom, ni pseudo, ni
    # user_id Telegram. Il voit la conversation rattachée à une commande.
    livreur = _a_acces_livreur(_uid_authentifie(request)) and not _a_acces_admin(
        _uid_authentifie(request))
    if livreur:
        _cid, commande = _resoudre_ref_chat(_corps(request).get("chat_ref"))
        commande = commande or {}
        prenom = _prenom_seul(commande)
        # Le prénom, et rien d'autre : ni pseudo Telegram, ni numéro, ni
        # identifiant. De quoi tenir une conversation, pas de quoi démarcher
        # le client en dehors de la boutique.
        return jsonify({
            "ok": True,
            "role": role,
            "client_id": "",
            "titre": prenom or "Client",
            "sous_titre": " · ".join(x for x in [
                f"Commande {commande.get('order_id', '')}".strip(),
                commande.get("city") or ""] if x.strip()),
            "messages": chat.messages(client_id),
            "profil": {},
            "ma_langue": "fr",
            "lu_par_autre": chat.lu_par(client_id, chat.CLIENT),
            "presence": _presence(client_id),
            "avatar_path": _selfie_avatar(client_id, pour_livreur=True),
        })

    profil = chat.profil(client_id) or (_profil_client(client_id) if role == chat.VENDEUR else {})
    return jsonify({
        "ok": True,
        "role": role,
        "client_id": str(client_id),
        "messages": chat.messages(client_id),
        "profil": profil,
        "vendeur": os.getenv("SUPPORT_USERNAME", "") or "millesimecoffee",
        # Langue de lecture de celui qui regarde, et jusqu'où l'autre a lu :
        # de quoi afficher chaque message traduit et poser les accusés.
        "ma_langue": "fr" if role == chat.VENDEUR else _langue_lecture_client(client_id),
        "lu_par_autre": chat.lu_par(
            client_id, chat.CLIENT if role == chat.VENDEUR else chat.VENDEUR),
        # Présence de l'autre : secondes depuis sa dernière activité dans
        # l'application, None si on ne l'a jamais vu.
        "presence": _presence(client_id) if role == chat.VENDEUR else None,
        # Photo de profil du fil : le dernier selfie du client. Rien côté
        # client — il n'a pas à voir sa propre photo en face de lui.
        "avatar_path": _selfie_avatar(client_id) if role == chat.VENDEUR else "",
    })


@app.route("/api/chat/send", methods=["POST"])
def api_chat_send():
    """Envoi d'un message. POST {initData, client_id?, texte?, photo_b64?,
    audio_b64?, duree?}"""
    role, client_id, erreur = _qui_parle(request)
    if erreur:
        return erreur
    _marquer_presence(_uid_authentifie(request))
    data = _corps(request)
    texte = _texte(data.get("texte"), chat.MAX_TEXTE)

    # Dès qu'un livreur est partie prenante, les coordonnées ne circulent pas :
    # c'est par là que passerait un détournement de client. L'owner, lui, reste
    # libre d'échanger ce qu'il veut avec ses clients.
    if texte and _filtrer_contacts(request, client_id):
        motif = chat.contient_contact(texte)
        if motif:
            return jsonify({"ok": False, "error": "contact_interdit",
                            "motif": motif}), 400

    kind, media_id = "texte", ""
    photo_b64 = data.get("photo_b64")
    audio_b64 = data.get("audio_b64")
    duree = 0.0

    if isinstance(photo_b64, str) and photo_b64:
        brut = chat.decoder_b64(photo_b64)
        if not brut:
            return jsonify({"ok": False, "error": "bad_photo"}), 400
        # Recompressée comme les selfies : une photo de téléphone fait 3 Mo,
        # une bulle de conversation n'en a pas besoin.
        compresse = _compresser_jpeg(brut, max_dim=1280, quality=72)
        media_id = chat.ecrire_media(compresse or brut, "photo")
        if not media_id:
            return jsonify({"ok": False, "error": "media_too_big"}), 413
        kind = "photo"
    elif isinstance(audio_b64, str) and audio_b64:
        brut = chat.decoder_b64(audio_b64)
        if not brut:
            return jsonify({"ok": False, "error": "bad_audio"}), 400
        media_id = chat.ecrire_media(brut, "audio")
        if not media_id:
            return jsonify({"ok": False, "error": "media_too_big"}), 413
        kind = "audio"
        duree = _entier(data.get("duree"), 0, 0, chat.MAX_DUREE_AUDIO)

    if not texte and not media_id:
        return jsonify({"ok": False, "error": "empty"}), 400

    if _rate_limited(f"chat:{role}:{client_id}", 30, 60.0):
        return jsonify({"ok": False, "error": "too_fast"}), 429

    # Chacun lit dans sa langue : le client écrit en anglais, la boutique lit
    # en français ; la boutique répond en français, le client lit dans la
    # sienne. La traduction est faite ici, une fois, et rangée avec le message.
    langue, trads = _traduire_message(texte, role, client_id)

    try:
        msg = chat.ajouter(client_id, role, texte=texte, media_id=media_id,
                           kind=kind, duree=duree, lang=langue, trad=trads,
                           repond_a=_texte(data.get("repond_a"), 32),
                           profil=_profil_client(client_id) if role == chat.CLIENT else None)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.error("chat_send: %s", exc)
        return jsonify({"ok": False, "error": "save_failed"}), 500

    _signaler_message(client_id, role, msg)
    return jsonify({"ok": True, "message": msg})


@app.route("/api/chat/threads", methods=["POST"])
def api_chat_threads():
    """Liste des conversations, réservée au vendeur. POST {initData}"""
    _refus = _guard_admin(request)
    if _refus:
        return _refus
    fils = chat.fils(chat.VENDEUR)
    for f in fils:
        if not f["profil"].get("user_name"):
            f["profil"] = _profil_client(f["client_id"])
        f["avatar_path"] = _selfie_avatar(f["client_id"])
    return jsonify({"ok": True, "threads": fils,
                    "non_lus": sum(f["non_lus"] for f in fils)})


@app.route("/api/chat/resume", methods=["POST"])
def api_chat_resume():
    """Compteur de messages non lus, pour la pastille. POST {initData}"""
    uid = _uid_authentifie(request)
    if uid is None:
        return jsonify({"ok": True, "non_lus": 0})
    # Le client qui suit sa commande consulte ce compteur toutes les 8 s :
    # c'est le signal le plus fiable de sa présence dans l'application.
    _marquer_presence(uid)
    if _a_acces_admin(uid):
        return jsonify({"ok": True, "role": chat.VENDEUR,
                        "non_lus": chat.total_non_lus(chat.VENDEUR)})
    if _a_acces_livreur(uid):
        # Non-lus des seules courses de sa zone, par client UNIQUE : plusieurs
        # commandes du même client ne multiplient pas ses messages.
        try:
            from storage import _load as _load_all
            uids = {o.get("user_id") for o in (_load_all() or [])
                    if o.get("user_id") and _dans_zone_livreur(o)}
            total = sum(chat.non_lus(u, chat.VENDEUR) for u in uids)
        except Exception:
            total = 0
        return jsonify({"ok": True, "role": "livreur", "non_lus": total})
    return jsonify({"ok": True, "role": chat.CLIENT,
                    "non_lus": chat.non_lus(uid, chat.CLIENT)})


@app.route("/api/chat/media/<media_id>", methods=["GET"])
def api_chat_media(media_id):
    """Sert une photo ou un audio de la conversation.

    L'identifiant seul ne suffit pas : il faut être partie prenante du fil qui
    contient ce média.
    """
    uid = _uid_authentifie(request)
    if uid is None:
        return ("Forbidden", 403)
    if _a_acces_admin(uid):
        client_id = _entier(request.args.get("client_id"), 0, 0, 10 ** 15)
        if not client_id:
            return ("Bad request", 400)
    elif _a_acces_livreur(uid):
        client_id, _cmd = _resoudre_ref_chat(request.args.get("chat_ref"))
        if not client_id:
            return ("Bad request", 400)
    else:
        client_id = uid
    if not chat.contient(media_id, client_id):
        return ("Not found", 404)
    donnees = chat.lire_media(media_id)
    if not donnees:
        return ("Not found", 404)
    from flask import Response
    return Response(donnees, mimetype=chat.type_mime(media_id),
                    headers={"Cache-Control": "private, max-age=86400"})


def _compresser_jpeg(brut: bytes, max_dim: int = 1280, quality: int = 72) -> bytes:
    """Réduit une image ; renvoie b"" si elle est illisible ou démesurée."""
    try:
        img = cv2.imdecode(np.frombuffer(brut, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return b""
        h, w = img.shape[:2]
        if h * w > _MAX_IMAGE_PIXELS:
            return b""
        echelle = min(1.0, max_dim / max(h, w))
        if echelle < 1.0:
            img = cv2.resize(img, (int(w * echelle), int(h * echelle)),
                             interpolation=cv2.INTER_AREA)
        ok, enc = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        return enc.tobytes() if ok else b""
    except Exception as exc:
        logger.warning("compression photo chat : %s", exc)
        return b""


def _signaler_message(client_id, de: str, msg: dict) -> None:
    """Prévient le destinataire qu'un message l'attend dans l'application.

    Rien n'est envoyé si le destinataire vient déjà d'être prévenu : sans ça,
    dix bulles d'affilée feraient dix notifications.
    """
    if not chat.doit_signaler(client_id, de):
        return
    apercu = chat.resume(msg)
    token = os.getenv("BOT_TOKEN", "")

    if de == chat.CLIENT:
        nom = (chat.profil(client_id) or {}).get("user_name") or f"#{client_id}"
        try:
            import pushover
            pushover.envoyer(apercu, titre=f"💬 {nom} vous écrit")
        except Exception as exc:
            logger.warning("chat pushover : %s", exc)
        destinataire = os.getenv("OWNER_CHAT_ID", "") or os.getenv("OWNER_USER_ID", "")
        texte = f"💬 <b>{_html_escape(nom)}</b> vous a écrit dans l'application :\n\n{_html_escape(apercu)}"
    else:
        destinataire = str(client_id)
        texte = ("💬 <b>Millésime Coffee</b> vous a répondu :\n\n"
                 f"{_html_escape(apercu)}\n\nOuvrez l'application pour répondre.")

    if not token or not destinataire:
        return
    try:
        import httpx
        httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": destinataire, "text": texte, "parse_mode": "HTML"},
            timeout=10.0,
        )
    except Exception as exc:
        logger.warning("chat notification Telegram : %s", exc)


_lock = threading.Lock()
_store: dict  = {}   # {user_id: {"photo": bytes}}
_tokens: dict = {}   # C1: {user_id: token_str}

_face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)


def register_token(user_id: str, token: str) -> None:
    """C1: Enregistre le token one-time pour cet utilisateur."""
    with _lock:
        _tokens[str(user_id)] = token


@app.route("/selfie")
def selfie_page():
    user_id = request.args.get("user_id", "")
    # H3: refuser tout user_id non numérique (anti-XSS dans le template)
    if not user_id.isdigit() or len(user_id) > 20:
        return "Bad request", 400
    return render_template("selfie.html", user_id=user_id)


@app.route("/verify", methods=["POST"])
def verify():
    try:
        data      = _corps(request)
        user_id   = _texte(data.get("user_id"), 32)
        token     = _texte(data.get("token"), 128)
        photo_b64 = data.get("photo", "")
        if not isinstance(photo_b64, str):
            photo_b64 = ""

        # C1: Valider le token avant tout traitement
        with _lock:
            expected = _tokens.get(user_id)
        if not expected or token != expected:
            logger.warning("Token invalide pour user_id=%s", user_id)
            return jsonify({"ok": False, "error": "Token invalide ou expiré"})

        # Retirer le préfixe data:image/...;base64,
        if "," in photo_b64:
            photo_b64 = photo_b64.split(",", 1)[1]

        photo_b64 = photo_b64.strip().replace("\n", "").replace("\r", "").replace(" ", "")
        missing = len(photo_b64) % 4
        if missing:
            photo_b64 += "=" * (4 - missing)

        photo_bytes = base64.b64decode(photo_b64)
        logger.info("Photo reçue : %d octets pour user=%s", len(photo_bytes), user_id)

        if len(photo_bytes) < 100:
            return jsonify({"ok": False, "error": "Image trop petite ou corrompue"})

        nparr = np.frombuffer(photo_bytes, np.uint8)
        img   = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            return jsonify({"ok": False, "error": "Format image non reconnu — réessayez"})

        # H2: refuser les images trop grandes en pixels (anti-décompression-bomb)
        h, w = img.shape[:2]
        if h * w > _MAX_IMAGE_PIXELS:
            logger.warning("Image bombe rejetée: %dx%d = %d MP", w, h, h*w // 1_000_000)
            del img, nparr
            return jsonify({"ok": False, "error": "Image trop grande, réduisez la résolution"})

        gray  = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = _face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60)
        )

        if len(faces) == 0:
            return jsonify({"ok": False, "error": "Aucun visage détecté — repositionnez-vous face à la caméra"})

        # C1: Consommer le token seulement en cas de succès
        with _lock:
            _tokens.pop(user_id, None)
            _store[user_id] = {"photo": photo_bytes}

        return jsonify({"ok": True})

    except Exception as exc:
        logger.error("Erreur verify: %s", exc)
        return jsonify({"ok": False, "error": "Erreur serveur, réessayez"})


def get_selfie(user_id: str) -> dict | None:
    with _lock:
        return _store.pop(str(user_id), None)


def run_server(port: int = 5000):
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)  # H4

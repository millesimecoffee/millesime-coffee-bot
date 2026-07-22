"""
Serveur Flask — Mini App Telegram (catalogue + selfie + détection visage OpenCV).
Tourne dans un thread en parallèle du bot Telegram.
"""
import base64
import importlib
import logging
import os
import threading
import time

import cv2
import numpy as np
from flask import Flask, jsonify, render_template, request

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB max (selfie + preuve virement)

# Cap dimensions image pour éviter les bombes décompression (50000x50000 → 7 GB RAM)
_MAX_IMAGE_PIXELS = 5_000_000  # 5 MP — largement suffisant pour un selfie


@app.after_request
def _bypass_ngrok_warning(response):
    """Indique à ngrok de ne PAS afficher la page d'avertissement browser."""
    response.headers["ngrok-skip-browser-warning"] = "true"
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
    """Point d'entrée de la Mini App."""
    return render_template("menu.html")


# Anti-spam très simple : mémorise les essais par IP
_pwd_attempts: dict[str, list[float]] = {}
_PWD_MAX_ATTEMPTS = 5
_PWD_WINDOW      = 300  # 5 min
_pwd_lock = threading.Lock()

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
        # Owner se filtre lui-même (pas de notif quand toi-même tu ouvres)
        owner_uid = os.getenv("OWNER_USER_ID", "")
        if owner_uid and str(uid) == str(owner_uid):
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


@app.route("/api/auth", methods=["POST"])
def api_auth():
    """Vérifie le mot de passe et retourne le catalogue.
    Throttle 5 essais / 5 min par IP.
    """
    expected = os.getenv("BOT_PASSWORD", "")
    if not expected:
        return jsonify({"ok": False, "error": "no_password_configured"}), 500

    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0].strip()
    now = time.time()

    # Purge des essais expirés + check rate limit
    with _pwd_lock:
        recent = [t for t in _pwd_attempts.get(ip, []) if now - t < _PWD_WINDOW]
        if len(recent) >= _PWD_MAX_ATTEMPTS:
            _pwd_attempts[ip] = recent
            return jsonify({"ok": False, "blocked": True, "error": "rate_limited"})
        _pwd_attempts[ip] = recent

    try:
        data = request.get_json(force=True) or {}
    except Exception:
        data = {}
    pwd = str(data.get("password", "")).strip()

    if not pwd or pwd != expected:
        with _pwd_lock:
            _pwd_attempts.setdefault(ip, []).append(now)
        time.sleep(0.5)  # léger throttle pour ralentir le brute force
        return jsonify({"ok": False, "error": "wrong_password"})

    # OK — recharger le catalogue (au cas où on l'aurait modifié)
    try:
        import catalog as catalog_mod
        importlib.reload(catalog_mod)
        resp = {
            "ok":         True,
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
                "bank_iban":    os.getenv("BANK_IBAN", ""),
                "payment_link": os.getenv("PAYMENT_LINK", ""),
                "crypto_eth":   os.getenv("CRYPTO_ETH", ""),
                "crypto_usdt":  os.getenv("CRYPTO_USDT", ""),
                # Carte / Apple Pay via SumUp — actif seulement si clés configurées
                "sumup":        bool(os.getenv("SUMUP_API_KEY", "") and os.getenv("SUMUP_MERCHANT_CODE", "")),
                "sumup_currency": os.getenv("SUMUP_CURRENCY", "EUR"),
            },
        }
        # Notif owner : "client entré dans le catalogue" (si initData valide)
        bot_token = os.getenv("BOT_TOKEN", "")
        init_data = (data or {}).get("initData", "") if isinstance(data, dict) else ""
        parsed = _verify_init_data(init_data, bot_token) if init_data else None
        if parsed:
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


# ═══════════════════════════════════════════════════════════════════════════
# Paiement SumUp — Apple Pay + carte, montant exact (Checkouts API)
# Doc : POST /v0.1/checkouts (hosted_checkout) → hosted_checkout_url
#       GET  /v0.1/checkouts/{id} → status PENDING/PAID/FAILED/EXPIRED
# Gated par SUMUP_API_KEY + SUMUP_MERCHANT_CODE (sinon endpoints désactivés).
# ═══════════════════════════════════════════════════════════════════════════
_SUMUP_API = "https://api.sumup.com/v0.1/checkouts"


def _sumup_conf():
    return (
        os.getenv("SUMUP_API_KEY", "").strip(),
        os.getenv("SUMUP_MERCHANT_CODE", "").strip(),
        os.getenv("SUMUP_CURRENCY", "EUR").strip() or "EUR",
    )


@app.route("/api/pay/sumup/create", methods=["POST"])
def api_pay_sumup_create():
    """Crée un checkout SumUp pour le montant exact du panier.
    POST {initData, amount, description?}
    Retourne {ok, id, url}.
    """
    api_key, merchant_code, currency = _sumup_conf()
    if not (api_key and merchant_code):
        return jsonify({"ok": False, "error": "sumup_not_configured"}), 400

    bot_token = os.getenv("BOT_TOKEN", "")
    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        data = {}
    if not _verify_init_data(data.get("initData", ""), bot_token):
        return jsonify({"ok": False, "error": "auth_failed"}), 401

    # Montant : positif, plafonné (garde-fou)
    try:
        amount = round(float(data.get("amount", 0)), 2)
    except (ValueError, TypeError):
        return jsonify({"ok": False, "error": "bad_amount"}), 400
    if amount <= 0 or amount > 100000:
        return jsonify({"ok": False, "error": "bad_amount"}), 400

    description = str(data.get("description", "") or "Commande")[:200]

    import uuid
    checkout_ref = "MC-" + uuid.uuid4().hex[:16]
    payload = {
        "checkout_reference": checkout_ref,
        "amount":             amount,
        "currency":           currency,
        "merchant_code":      merchant_code,
        "description":        description,
        "hosted_checkout":    {"enabled": True},
    }

    import httpx as _httpx
    try:
        with _httpx.Client(timeout=15.0) as c:
            r = c.post(
                _SUMUP_API,
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            )
    except Exception as exc:
        logger.error("sumup create: %s", exc)
        return jsonify({"ok": False, "error": "sumup_unreachable"}), 502

    if r.status_code not in (200, 201):
        logger.error("sumup create HTTP %s: %s", r.status_code, r.text[:300])
        return jsonify({"ok": False, "error": "sumup_error"}), 502

    try:
        body = r.json()
    except Exception:
        return jsonify({"ok": False, "error": "sumup_bad_response"}), 502

    checkout_id = body.get("id") or ""
    hosted_url  = body.get("hosted_checkout_url") or ""
    if not (checkout_id and hosted_url):
        logger.error("sumup create missing id/url: %s", str(body)[:300])
        return jsonify({"ok": False, "error": "sumup_no_url"}), 502

    return jsonify({"ok": True, "id": checkout_id, "url": hosted_url, "reference": checkout_ref})


@app.route("/api/pay/sumup/status", methods=["POST"])
def api_pay_sumup_status():
    """Statut d'un checkout SumUp.
    POST {initData, id}
    Retourne {ok, status} — status ∈ PENDING|PAID|FAILED|EXPIRED.
    """
    api_key, merchant_code, _ = _sumup_conf()
    if not (api_key and merchant_code):
        return jsonify({"ok": False, "error": "sumup_not_configured"}), 400

    bot_token = os.getenv("BOT_TOKEN", "")
    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        data = {}
    if not _verify_init_data(data.get("initData", ""), bot_token):
        return jsonify({"ok": False, "error": "auth_failed"}), 401

    checkout_id = str(data.get("id", "")).strip()
    if not checkout_id:
        return jsonify({"ok": False, "error": "no_id"}), 400

    import httpx as _httpx
    try:
        with _httpx.Client(timeout=15.0) as c:
            r = c.get(
                f"{_SUMUP_API}/{checkout_id}",
                headers={"Authorization": f"Bearer {api_key}"},
            )
    except Exception as exc:
        logger.error("sumup status: %s", exc)
        return jsonify({"ok": False, "error": "sumup_unreachable"}), 502

    if r.status_code != 200:
        return jsonify({"ok": False, "error": "sumup_error"}), 502
    try:
        body = r.json()
    except Exception:
        return jsonify({"ok": False, "error": "sumup_bad_response"}), 502

    return jsonify({"ok": True, "status": (body.get("status") or "PENDING")})


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

    if not init_data or not bot_token:
        return None
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=False))
        their_hash = pairs.pop("hash", "")
        if not their_hash:
            return None
        # Data-check-string : trier alphabétiquement et joindre par \n
        dcs = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
        secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        my_hash = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(my_hash, their_hash):
            return pairs
    except Exception as exc:
        logger.warning("verify_init_data exception: %s", exc)
    return None


@app.route("/api/submit_cart", methods=["POST"])
def api_submit_cart():
    """Reçoit le panier final de la Mini App.
    Valide initData → user_id authentique → stocke + envoie message paiement.
    """
    try:
        data = request.get_json(force=True) or {}
    except Exception:
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
                {"text": "💵 Cash",     "callback_data": "mapay:cash"},
                {"text": "🏦 Virement", "callback_data": "mapay:virement"},
            ],
            [
                {"text": "💳 Lien",    "callback_data": "mapay:link"},
                {"text": "₿ Crypto",   "callback_data": "mapay:crypto"},
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
    try:
        data = request.get_json(force=True) or {}
    except Exception:
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
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify({"ok": False, "error": "bad_json"}), 400

    address = (data.get("address") or "").strip()
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
    try:
        data = request.get_json(force=True) or {}
    except Exception:
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
        "payment_sumup_id": payment.get("sumup_id", ""),   # id checkout SumUp si carte/Apple Pay
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


def _check_owner(req) -> int | None:
    """Lit initData depuis le body JSON (POST) ou la query string (GET)
    et vérifie que c'est bien le owner. Retourne user_id ou None.
    """
    bot_token = os.getenv("BOT_TOKEN", "")
    if req.method == "POST":
        try:
            data = req.get_json(force=True, silent=True) or {}
        except Exception:
            data = {}
        init_data = data.get("initData", "")
    else:
        init_data = req.args.get("initData", "")
    parsed = _verify_init_data(init_data, bot_token)
    return _is_owner_init(parsed)


@app.route("/api/admin/orders", methods=["POST"])
def api_admin_orders():
    """Retourne la liste des commandes pour le panel owner.
    POST {initData, limit?, status_filter?}
    """
    if _check_owner(request) is None:
        return jsonify({"ok": False, "error": "not_owner"}), 403

    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        data = {}
    limit  = int(data.get("limit", 50))
    sfilt  = data.get("status_filter", "")  # "", "pending", "confirmed", "delivering", "delivered", "cancelled"

    try:
        from storage import _load as _load_orders
        orders = _load_orders() or []
    except Exception as exc:
        logger.error("admin_orders load: %s", exc)
        return jsonify({"ok": False, "error": "load_failed"}), 500

    # Trier du plus récent au plus ancien
    orders = sorted(orders, key=lambda o: o.get("created_at", ""), reverse=True)

    # Filtrer + tronquer
    if sfilt:
        orders = [o for o in orders if (o.get("status") or "pending") == sfilt]
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

    # Stats utiles : counts par status + stats du jour + top produit + panier moyen
    counts = {"pending": 0, "confirmed": 0, "delivering": 0, "delivered": 0, "cancelled": 0}
    today_ca    = 0.0
    today_count = 0
    today_items: dict[str, int] = {}
    # Petit historique CA sur 7 jours pour mini-graph
    from datetime import datetime as _dt, timedelta as _td
    ca_by_day: dict[str, float] = {}
    for i in range(7):
        ca_by_day[(_dt.now() - _td(days=i)).strftime("%Y-%m-%d")] = 0.0

    try:
        from storage import _load as _load_all
        today_str  = _dt.now().strftime("%Y-%m-%d")
        all_orders = _load_all() or []
        for o in all_orders:
            s = o.get("status") or "pending"
            if s in counts:
                counts[s] += 1
            day_key = (o.get("created_at") or "")[:10]
            excluded = s in ("cancelled", "cancelled_by_client")
            if day_key in ca_by_day and not excluded:
                ca_by_day[day_key] += float(o.get("total", 0) or 0)
            if day_key == today_str and not excluded:
                today_ca    += float(o.get("total", 0) or 0)
                today_count += 1
                for prod, qty in (o.get("cart") or {}).items():
                    try:
                        q = int(qty)
                    except Exception:
                        q = 0
                    if q > 0:
                        today_items[prod] = today_items.get(prod, 0) + q
    except Exception:
        pass

    avg_basket_today = (today_ca / today_count) if today_count else 0.0
    top_product = ""
    top_product_qty = 0
    if today_items:
        top_product, top_product_qty = max(today_items.items(), key=lambda x: x[1])

    # Convertir ca_by_day en liste triée du plus ancien → plus récent
    ca_history = [{"day": d, "ca": ca_by_day[d]} for d in sorted(ca_by_day.keys())]

    return jsonify({
        "ok": True,
        "orders": light,
        "counts": counts,
        "today_ca":         today_ca,
        "today_count":      today_count,
        "avg_basket_today": avg_basket_today,
        "top_product":      top_product,
        "top_product_qty":  top_product_qty,
        "ca_history":       ca_history,
    })


@app.route("/api/admin/order/<order_id>", methods=["POST"])
def api_admin_order_detail(order_id):
    """Détail complet d'une commande (avec photos b64).
    POST {initData}
    """
    if _check_owner(request) is None:
        return jsonify({"ok": False, "error": "not_owner"}), 403

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
    if _check_owner(request) is None:
        return jsonify({"ok": False, "error": "not_owner"}), 403

    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        data = {}
    new_status = (data.get("status") or "").strip()
    if new_status not in ("confirmed", "delivering", "delivered", "cancelled"):
        return jsonify({"ok": False, "error": "bad_status"}), 400

    # Charger order existant
    try:
        from storage import get_order, update_order
        order = get_order(order_id)
    except Exception as exc:
        logger.error("admin_set_status load: %s", exc)
        return jsonify({"ok": False, "error": "load_failed"}), 500
    if not order:
        return jsonify({"ok": False, "error": "not_found"}), 404

    # Idempotence
    if (order.get("status") or "pending") == new_status:
        return jsonify({"ok": True, "unchanged": True})

    # Update + horodatage de passage en delivering (pour ETA tracking)
    try:
        upd = {"status": new_status}
        if new_status == "delivering":
            from datetime import datetime as _dt
            upd["_delivery_started_at"] = _dt.now().isoformat(timespec="seconds")
            # Owner peut préciser un temps de livraison en minutes
            try:
                eta_min = int(data.get("eta_minutes", 0))
                if 1 <= eta_min <= 240:
                    upd["_eta_minutes"] = eta_min
            except (ValueError, TypeError):
                pass
        elif new_status == "delivered":
            from datetime import datetime as _dt
            upd["_delivered_at"] = _dt.now().isoformat(timespec="seconds")
        update_order(order_id, upd)
    except Exception as exc:
        logger.error("admin_set_status update: %s", exc)
        return jsonify({"ok": False, "error": "update_failed"}), 500

    # Notifier le client via Bot API
    client_id = order.get("user_id")
    client_lang = order.get("lang", "fr") if order.get("lang") in ("fr","es","en") else "fr"
    bot_token = os.getenv("BOT_TOKEN", "")
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
        if text:
            import httpx
            try:
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
                httpx.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json=payload,
                    timeout=10.0,
                )
            except Exception as exc:
                logger.warning("admin_set_status notify client: %s", exc)

    return jsonify({"ok": True, "status": new_status})


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
    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        data = {}
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

    limit = int(data.get("limit", 50))
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
    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        data = {}
    parsed = _verify_init_data(data.get("initData", ""), bot_token)
    if not parsed:
        return jsonify({"ok": False, "error": "auth_failed"}), 401
    import json as _json
    try:
        user_obj = _json.loads(parsed.get("user", "{}"))
        uid = int(user_obj.get("id", 0))
    except Exception:
        return jsonify({"ok": False, "error": "no_user"}), 400

    order_id = (data.get("order_id") or "").strip()
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


@app.route("/api/order/track", methods=["POST"])
def api_order_track():
    """Tracking d'une commande pour le client.
    POST {initData, order_id}
    Auth : initData doit correspondre au user_id de la commande.
    """
    bot_token = os.getenv("BOT_TOKEN", "")
    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        data = {}
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

    order_id = (data.get("order_id") or "").strip()
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
        from datetime import datetime as _dt
        start_delivery = order.get("_delivery_started_at")
        if start_delivery:
            try:
                start = _dt.fromisoformat(start_delivery)
            except Exception:
                start = _dt.now()
        else:
            start = _dt.now()
        elapsed = (_dt.now() - start).total_seconds()
        progress = max(0.0, min(1.0, elapsed / duration_seconds))
        eta_seconds = max(0, int(duration_seconds - elapsed))
    elif status == "delivered":
        progress = 1.0
        eta_seconds = 0

    # Position du livreur (interpolation entre point de départ fictif et destination)
    # Point de départ fictif : 2.5 km à l'est de la destination (random selon order_id)
    driver_lat = driver_lon = None
    if dest_lat and dest_lon and status in ("delivering", "delivered"):
        # Offset déterministe par order_id (pour que ça paraisse cohérent)
        import hashlib
        h = int(hashlib.sha1(order_id.encode()).hexdigest(), 16)
        angle = (h % 360) * 3.14159 / 180
        radius_km = 2.5
        # 1 deg lat ≈ 111 km
        start_lat = dest_lat + (radius_km / 111.0) * (1 if (h >> 4) % 2 else -1) * 0.5
        start_lon = dest_lon + (radius_km / 111.0) * (1 if (h >> 5) % 2 else -1) * 0.5
        # Interpolation
        driver_lat = start_lat + (dest_lat - start_lat) * progress
        driver_lon = start_lon + (dest_lon - start_lon) * progress

    # Étapes visuelles
    steps_status = {
        "received":    True,                                                        # reçue : toujours OK
        "preparing":   status in ("confirmed", "delivering", "delivered"),         # préparée
        "delivering":  status in ("delivering", "delivered"),                       # en route
        "delivered":   status == "delivered",                                       # livrée
    }

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
            {"lat": driver_lat, "lon": driver_lon}
            if driver_lat is not None else None
        ),
        "steps": steps_status,
        "city":  order.get("city"),
        "total": order.get("total"),
        "display_currency": order.get("display_currency") or "€",
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
    if _check_owner(request) is None:
        return jsonify({"ok": False, "error": "not_owner"}), 403
    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        data = {}
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
        note = (data.get("note") or "").strip()
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
    if _check_owner(request) is None:
        return jsonify({"ok": False, "error": "not_owner"}), 403

    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        data = {}
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
        if s not in ("cancelled", "cancelled_by_client"):
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
        if s not in ("cancelled", "cancelled_by_client"):
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
    if _check_owner(request) is None:
        return jsonify({"ok": False, "error": "not_owner"}), 403

    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        data = {}
    text    = (data.get("text") or "").strip()
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
    if _check_owner(request) is None:
        return jsonify({"ok": False, "error": "not_owner"}), 403
    with _broadcast_lock:
        job = _broadcast_jobs.get(job_id)
        if not job:
            return jsonify({"ok": False, "error": "not_found"}), 404
        return jsonify({"ok": True, **job})


@app.route("/api/admin/broadcast/cancel/<job_id>", methods=["POST"])
def api_admin_broadcast_cancel(job_id):
    """Annule un broadcast en cours."""
    if _check_owner(request) is None:
        return jsonify({"ok": False, "error": "not_owner"}), 403
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
    if _check_owner(request) is None:
        return jsonify({"ok": False, "error": "not_owner"}), 403
    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        data = {}
    try:
        target_uid = int(data.get("user_id", 0))
    except (ValueError, TypeError):
        target_uid = 0
    text = (data.get("text") or "").strip()
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


@app.route("/api/admin/photo/<order_id>/<kind>", methods=["GET"])
def api_admin_photo(order_id, kind):
    """Sert une photo (selfie ou proof) de la commande en JPEG.
    Auth via initData en query string : ?initData=...
    """
    if _check_owner(request) is None:
        return ("Forbidden", 403)
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
    return Response(photo_bytes, mimetype="image/jpeg",
                    headers={"Cache-Control": "private, max-age=300"})


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
        data      = request.get_json(force=True)
        user_id   = str(data.get("user_id", ""))
        token     = str(data.get("token", ""))
        photo_b64 = data.get("photo", "")

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

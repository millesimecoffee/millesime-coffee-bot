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
        return jsonify({
            "ok":         True,
            "catalog":    catalog_mod.CATALOG,
            "min_orders": catalog_mod.MIN_ORDER,
            "currencies": catalog_mod.CURRENCIES,
            "payment_config": {
                "bank_iban":    os.getenv("BANK_IBAN", ""),
                "payment_link": os.getenv("PAYMENT_LINK", ""),
                "crypto_eth":   os.getenv("CRYPTO_ETH", ""),
                "crypto_usdt":  os.getenv("CRYPTO_USDT", ""),
            },
        })
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

    # Construire l'ordre
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
        "address":   (address.get("short") or address.get("formatted") or address.get("text") or ""),
        "address_verified": bool(address.get("verified")),
        "phone":     "",
        "maps_link": address.get("maps_link", ""),
        "status":    "pending",
        "source":    "miniapp",
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
    addr_disp = (address.get("short") or address.get("formatted") or "—").replace("\n", "<br>")
    cart_html = "\n".join(
        f"  • {_html_escape(prod)} × {q} = {products[prod]*q:,.0f} €"
        for prod, q in safe_cart.items()
    )
    full_name = _html_escape(user_first or user_name or "?")
    lines = [
        f"🆕 <b>Nouvelle commande !</b> <code>{order_id}</code> 📲 <i>via Mini App</i>",
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
        f"💸 <b>Total : {total:,.0f} €</b>",
        "",
        f"💳 Paiement : {_html_escape(pay_label)}",
    ]
    if payment.get("crypto_name"):
        lines.append(f"   ↳ Adresse : <code>{_html_escape(payment.get('crypto_addr',''))}</code>")
    lines += [
        "",
        f"📍 <b>Adresse</b>",
        f"<code>{_html_escape(addr_disp).replace('&lt;br&gt;', chr(10))}</code>",
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

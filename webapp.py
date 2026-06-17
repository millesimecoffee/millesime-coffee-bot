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
app.config["MAX_CONTENT_LENGTH"] = 3 * 1024 * 1024  # 3 MB max (selfie réaliste)

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

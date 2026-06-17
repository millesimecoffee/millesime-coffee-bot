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

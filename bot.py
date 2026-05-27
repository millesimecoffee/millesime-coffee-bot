"""
Bot Telegram — Catalogue multilingue (FR/ES/EN), panier, géoloc OpenStreetMap,
selfie WebApp et notifications owner.
"""
import csv
import io
import json
import os
import html as _html
import logging
import secrets
import threading
import importlib
import requests
from datetime import datetime, timedelta, time as dt_time
from zoneinfo import ZoneInfo
from io import BytesIO
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    WebAppInfo,
    BotCommand,
    CopyTextButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

import catalog as catalog_mod
from translations import t
from storage import (
    save_order, update_order, get_order, get_stats, get_stats_period,
    get_orders_by_user, get_all_user_ids,
    load_blacklist, save_blacklist,
    backup_orders,
    _load as _load_orders,
)

load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────
_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
logging.basicConfig(format=_LOG_FORMAT, level=logging.INFO)
logger = logging.getLogger(__name__)
# M4: RotatingFileHandler ajouté dans main()

# ── Config ────────────────────────────────────────────────────────────────────
BOT_TOKEN      = os.getenv("BOT_TOKEN", "")
BOT_PASSWORD   = os.getenv("BOT_PASSWORD", "SECRET123")
OWNER_CHAT_ID  = os.getenv("OWNER_CHAT_ID", "")   # où arrivent les notifs (privé ou groupe)

# OWNER_USER_ID = ID Telegram personnel de l'admin (jamais un groupe = jamais négatif)
# Fallback OWNER_CHAT_ID seulement s'il est positif (chat privé), sinon vide
_raw_owner_uid = os.getenv("OWNER_USER_ID", "")
if not _raw_owner_uid and OWNER_CHAT_ID and not OWNER_CHAT_ID.lstrip("-").isdigit():
    _raw_owner_uid = ""
elif not _raw_owner_uid and OWNER_CHAT_ID:
    # Si OWNER_CHAT_ID est positif (chat privé), on peut l'utiliser comme user_id
    _raw_owner_uid = OWNER_CHAT_ID if not OWNER_CHAT_ID.startswith("-") else ""
OWNER_USER_ID = _raw_owner_uid
WEBAPP_URL     = os.getenv("WEBAPP_URL", "")
NGROK_TOKEN    = os.getenv("NGROK_AUTH_TOKEN", "")

# ── Paiement — configurer dans .env ──────────────────────────────────────────
BANK_IBAN    = os.getenv("BANK_IBAN",    "")
PAYMENT_LINK = os.getenv("PAYMENT_LINK", "")
CRYPTO_ETH   = os.getenv("CRYPTO_ETH",  "")
CRYPTO_USDT  = os.getenv("CRYPTO_USDT", "")

MAX_PASSWORD_ATTEMPTS = 3
BLOCK_DURATION_MIN    = 5

# ── Horaires d'ouverture ────────────────────────────────────────────────────
# Le bot accepte les commandes de OPEN_HOUR (matin) à CLOSE_HOUR (matin suivant).
# Avec OPEN=11 et CLOSE=6 → ouvert 11h00 jusqu'à 05h59 le lendemain (19h/jour).
OPEN_HOUR  = 11   # ouverture (heure locale du PC)
CLOSE_HOUR = 6    # fermeture (heure locale du PC) — exclusive

# Message multi-langue affiché au /start hors horaires
_CLOSED_BANNER = (
    "🌙 *Service fermé / Closed / Cerrado*\n\n"
    f"🕘 Horaires : *{OPEN_HOUR:02d}h → {CLOSE_HOUR:02d}h* tous les jours\n"
    f"🕘 Hours: *{OPEN_HOUR:02d}:00 → {CLOSE_HOUR:02d}:00 AM* every day\n"
    f"🕘 Horario: *{OPEN_HOUR:02d}h → {CLOSE_HOUR:02d}h* todos los días\n\n"
    f"_Revenez à {OPEN_HOUR}h / Come back at {OPEN_HOUR} AM / Vuelve a las {OPEN_HOUR}h_"
)


def _is_open() -> bool:
    """True si l'heure actuelle est dans la fenêtre d'ouverture."""
    h = datetime.now().hour
    # Fenêtre wrap-around : ouvert si h >= OPEN OU h < CLOSE
    if OPEN_HOUR <= CLOSE_HOUR:
        # Cas normal sans wrap (ex. 9h → 17h)
        return OPEN_HOUR <= h < CLOSE_HOUR
    return h >= OPEN_HOUR or h < CLOSE_HOUR

# ── Anti-spam — persisté via storage (Supabase ou fichier) ─────────────────────
_DATA_DIR = Path(os.getenv("DATA_DIR", str(Path(__file__).parent)))
_password_attempts: dict[int, list[datetime]] = {}
_blocked: dict[int, datetime] = {}

# ── Blacklist permanente ───────────────────────────────────────────────────────
_blacklist: set = set()

# ── Pause d'urgence (idée #40) ─────────────────────────────────────────────────
# L'owner peut désactiver temporairement le bot via /pause (en cas de panne,
# rupture de stock, problème de livraison, etc.) et le réactiver via /resume.
# Mémoire-seule : un redémarrage réinitialise (= bot fonctionne par défaut).
_paused: bool = False
_paused_reason: str = ""


def _load_blocked() -> dict[int, datetime]:
    from storage import load_blocked
    try:
        return load_blocked()
    except Exception as exc:
        logger.error("Chargement blocked : %s", exc)
        return {}


def _save_blocked() -> None:
    from storage import save_blocked
    try:
        save_blocked(_blocked)
    except Exception as exc:
        logger.error("Sauvegarde blocked : %s", exc)


# ── Génération de l'ID commande : DDMMSS (séquence journalière) ───────────────
_oid_lock = threading.Lock()

def _generate_order_id() -> str:
    """Format : DDMMSS — DD=jour, MM=mois, SS=numéro de la commande du jour.

    Exemple : 25 mai, 1re commande -> '250501'
              25 mai, 2e commande -> '250502'

    Si la séquence dépasse 99, passe à 3 chiffres (250100 -> '2501100').
    """
    from storage import _load as _load_orders
    with _oid_lock:
        now = datetime.now()
        prefix = now.strftime("%d%m")              # ex. "2505"
        today  = now.strftime("%Y-%m-%d")          # ex. "2026-05-25"
        try:
            orders = _load_orders()
        except Exception:
            orders = []
        # Compte les commandes du jour (par leur created_at OU leur order_id préfixe)
        count = 0
        for o in orders:
            if o.get("created_at", "").startswith(today):
                count += 1
            elif isinstance(o.get("order_id"), str) and o["order_id"].startswith(prefix):
                count += 1
        seq = count + 1
        width = 2 if seq < 100 else 3
        return f"{prefix}{seq:0{width}d}"


# ── États ─────────────────────────────────────────────────────────────────────
(
    SELECTING_LANGUAGE,
    WAITING_PASSWORD,
    REQUESTING_PHONE,
    SELECTING_COUNTRY,
    SELECTING_CITY,
    BROWSING_MENU,
    VIEWING_CART,
    SELECTING_PAYMENT,
    ENTERING_ADDRESS,
    CONFIRMING_ADDRESS,
    SENDING_SELFIE,
    CONFIRMING_ORDER,
    ORDER_MANAGEMENT,
) = range(13)
AWAITING_TRANSFER_PROOF = 13   # état supplémentaire hors range


# ═════════════════════════════════════════════════════════════════════════════
# Helpers d'échappement texte
# ═════════════════════════════════════════════════════════════════════════════

def _md_escape(text) -> str:
    """Échappe les caractères Markdown legacy Telegram (`* _ [ ] ` `).
    Accepte None et le convertit en '?'.
    """
    if text is None:
        return "?"
    s = str(text)
    for ch in ("\\", "*", "_", "`", "["):
        s = s.replace(ch, "\\" + ch)
    return s


def _safe_html(text) -> str:
    """Wrapper sur html.escape qui gère None."""
    return _html.escape(str(text)) if text is not None else "?"


def _user_display(user) -> str:
    """Nom utilisateur formatté pour affichage (jamais None, jamais vide)."""
    if user is None:
        return "?"
    name = user.first_name or user.username or f"id_{user.id}"
    return name


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════

def _lang(ud: dict) -> str:
    return ud.get("lang", "fr")


def _touch(ud: dict) -> None:
    ud["last_activity"] = datetime.now()


def _order_summary(ud: dict) -> str:
    """H5: Protégé contre les KeyError si le catalogue a changé."""
    lang = _lang(ud)
    try:
        country  = ud["country"]
        city     = ud["city"]
        cart     = ud["cart"]
        menu     = catalog_mod.CATALOG[country][city]
        currency = catalog_mod.get_currency(country)
    except KeyError:
        return t("generic_error", lang)

    pay_str = ud.get("payment_label") or (t(ud["payment_key"], lang) if ud.get("payment_key") else "—")
    address = ud.get("address", "—")

    lines = [t("summary_title", lang)]
    total = 0
    for item, qty in cart.items():
        if item in menu:
            sub    = menu[item] * qty
            total += sub
            lines.append(f"• {item} x{qty} — {sub:,.0f} {currency}")
    lines.append("\n" + t("cart_total", lang, total=f"{total:,.0f}", cur=currency))
    lines.append(t("summary_payment", lang, p=pay_str))
    lines.append(t("summary_address", lang, a=address))
    lines.append(t("summary_city", lang, c=city, co=country))
    ud["order_total"] = total
    return "\n".join(lines)


async def _notify_owner(context: ContextTypes.DEFAULT_TYPE, user, ud: dict, order_id: str):
    """Notification owner — format personnalisé."""
    if not OWNER_CHAT_ID:
        return
    try:
        country  = ud["country"]
        city     = ud["city"]
        cart     = ud["cart"]
        menu     = catalog_mod.CATALOG[country][city]
        currency = catalog_mod.get_currency(country)
    except KeyError:
        logger.error("_notify_owner: données manquantes dans ud")
        return

    pay_str   = ud.get("payment_label") or (t(ud["payment_key"], "fr") if ud.get("payment_key") else "—")
    address   = ud.get("address", "—")
    maps_link = ud.get("maps_link", "")
    total     = ud.get("order_total", 0)
    phone     = ud.get("phone", "")

    # Nom complet du client
    full_name = user.first_name or ""
    if getattr(user, "last_name", None):
        full_name = f"{full_name} {user.last_name}".strip()

    # Adresse : déjà sur plusieurs lignes si géocodée, sinon on découpe sur ", "
    address_fmt = address.replace(", ", "\n")

    safe_name    = _html.escape(full_name)
    safe_city    = _html.escape(city)
    safe_country = _html.escape(country)
    safe_oid     = _html.escape(order_id)
    safe_pay     = _html.escape(pay_str)
    safe_address = _html.escape(address_fmt)

    lines = [
        f"🆕 <b>Nouvelle commande !</b> {safe_oid}",
        "",
        f"👤 Client : {safe_name} ({user.id})",
    ]
    if user.username:
        lines.append(f"📱 Username : @{_html.escape(user.username)}")
    if phone:
        lines.append(f"📞 Téléphone : {_html.escape(phone)}")
    lines.append(f"🌐 Langue : {_lang(ud).upper()}")
    lines += [
        "",
        f"🌍 Pays : {safe_country}",
        f"🏙️ Ville : {safe_city}",
        "",
        "🛒 Articles :",
    ]
    for item, qty in cart.items():
        if item in menu:
            lines.append(f"  • {_html.escape(item)} x{qty} — {menu[item] * qty:,.0f} {currency}")
    lines += [
        "",
        f"💸 Total : {total:,.0f} {currency}",
        safe_pay,
        "",
        "📍 Adresse :",
        safe_address,
    ]
    if maps_link:
        lines.append(f"🗺️ <a href='{maps_link}'>Voir sur OpenStreetMap</a>")
    lines += [
        "",
        f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}",
    ]

    owner_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Contacter le client",   url=f"tg://user?id={user.id}")],
        [InlineKeyboardButton("✅ Commande confirmée",     callback_data=f"owner:confirmed:{user.id}:{order_id}")],
        [InlineKeyboardButton("🚚 En cours de livraison", callback_data=f"owner:delivering:{user.id}:{order_id}")],
        [InlineKeyboardButton("📦 Commande livrée",       callback_data=f"owner:delivered:{user.id}:{order_id}")],
        [InlineKeyboardButton("❌ Annuler la commande",    callback_data=f"owner:cancelled:{user.id}:{order_id}")],
    ])

    try:
        await context.bot.send_message(
            chat_id=OWNER_CHAT_ID,
            text="\n".join(lines),
            parse_mode="HTML",
            reply_markup=owner_kb,
        )
        selfie_fid   = ud.get("selfie_file_id")
        selfie_bytes = ud.get("selfie_bytes")
        if selfie_fid:
            await context.bot.send_photo(
                chat_id=OWNER_CHAT_ID,
                photo=selfie_fid,
                caption=f"📸 Selfie client — {order_id}",
            )
        elif selfie_bytes:
            sent_msg = await context.bot.send_photo(
                chat_id=OWNER_CHAT_ID,
                photo=BytesIO(selfie_bytes),
                caption=f"📸 Selfie client — {order_id}",
            )
            # H8: dès que Telegram a la photo, on remplace les bytes (lourd)
            # par le file_id (léger) et on libère la RAM
            try:
                if sent_msg.photo:
                    ud["selfie_file_id"] = sent_msg.photo[-1].file_id
            except Exception:
                pass
            ud.pop("selfie_bytes", None)
        proof_fid = ud.get("transfer_proof_file_id")
        if proof_fid:
            await context.bot.send_photo(
                chat_id=OWNER_CHAT_ID,
                photo=proof_fid,
                caption=f"🏦 Preuve de virement — {order_id}",
            )
    except Exception as exc:
        logger.error("Échec envoi owner: %s", exc)


def _management_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t("manage_cancel",  lang), callback_data="manage:cancel")],
        [InlineKeyboardButton(t("manage_address", lang), callback_data="manage:address")],
        [InlineKeyboardButton(t("manage_cart",    lang), callback_data="manage:cart")],
    ])


def _selfie_webapp_keyboard(user_id: str, lang: str, token: str = "") -> ReplyKeyboardMarkup:
    """Construit le clavier Mini App selfie avec token optionnel."""
    url = f"{WEBAPP_URL}/selfie?user_id={user_id}"
    if token:
        url += f"&token={token}"
    return ReplyKeyboardMarkup(
        [[KeyboardButton(t("btn_take_selfie", lang), web_app=WebAppInfo(url=url))]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def _restart_keyboard() -> ReplyKeyboardMarkup:
    """Bouton /start persistant affiché en fin de session."""
    return ReplyKeyboardMarkup(
        [[KeyboardButton("/start")]],
        resize_keyboard=True,
        is_persistent=True,
    )


# ═════════════════════════════════════════════════════════════════════════════
# /start → choix de langue → welcome + mot de passe
# ═════════════════════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id_int   = update.effective_user.id
    is_owner_user = str(user_id_int) == str(OWNER_USER_ID)

    # Blacklist permanente
    if user_id_int in _blacklist:
        await update.message.reply_text(t("blacklisted", "fr"))
        return ConversationHandler.END

    # Pause d'urgence owner (#40)
    if _paused and not is_owner_user:
        reason = _paused_reason or "service temporairement indisponible"
        await update.message.reply_text(
            f"⏸️ *Service en pause*\n\n_{reason}_\n\nRéessayez plus tard. 🙏",
            parse_mode="Markdown",
            reply_markup=_restart_keyboard(),
        )
        return ConversationHandler.END

    # Hors horaires : message "fermé" multi-langue et fin de session.
    if not _is_open() and not is_owner_user:
        await update.message.reply_text(
            _CLOSED_BANNER,
            parse_mode="Markdown",
            reply_markup=_restart_keyboard(),
        )
        return ConversationHandler.END

    context.user_data.clear()
    _touch(context.user_data)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🇫🇷 Français", callback_data="lang:fr")],
        [InlineKeyboardButton("🇪🇸 Español",  callback_data="lang:es")],
        [InlineKeyboardButton("🇬🇧 English",  callback_data="lang:en")],
    ])
    await update.message.reply_text(
        "🌐 *Choose your language / Choisissez votre langue / Elige tu idioma:*",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
    return SELECTING_LANGUAGE


async def select_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    lang = query.data.split(":")[1]
    if lang not in ("fr", "es", "en"):
        lang = "fr"
    context.user_data["lang"] = lang
    _touch(context.user_data)
    # H4: escape Markdown du first_name (sinon "Jean_Pierre" casse le parsing)
    safe_name = _md_escape(update.effective_user.first_name or "?")
    await query.edit_message_text(
        t("welcome_after_lang", lang, name=safe_name),
        parse_mode="Markdown",
    )
    return WAITING_PASSWORD


# ═════════════════════════════════════════════════════════════════════════════
# Mot de passe + anti-spam
# ═════════════════════════════════════════════════════════════════════════════

async def check_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    ud      = context.user_data
    lang    = _lang(ud)

    if user_id in _blocked:
        if datetime.now() < _blocked[user_id]:
            remaining = int((_blocked[user_id] - datetime.now()).total_seconds() / 60) + 1
            await update.message.reply_text(t("blocked", lang, min=remaining))
            return WAITING_PASSWORD
        del _blocked[user_id]
        _password_attempts.pop(user_id, None)
        _save_blocked()

    if update.message.text.strip() == BOT_PASSWORD:
        _password_attempts.pop(user_id, None)
        _touch(ud)

        # Notifier l'owner qu'un client vient d'entrer dans le catalogue
        if OWNER_CHAT_ID:
            try:
                user      = update.effective_user
                full_name = user.first_name or ""
                if getattr(user, "last_name", None):
                    full_name = f"{full_name} {user.last_name}".strip()
                username_line = (
                    f"\n📱 Username : @{_html.escape(user.username)}"
                    if user.username else ""
                )
                await context.bot.send_message(
                    chat_id=OWNER_CHAT_ID,
                    text=(
                        f"👀 <b>Nouveau client dans le catalogue !</b>"
                        f"{username_line}\n"
                        f"👤 Nom : {_html.escape(full_name)}\n"
                        f"🆔 ID : <code>{user.id}</code>\n"
                        f"🌐 Langue : {_lang(ud).upper()}\n"
                        f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                    ),
                    parse_mode="HTML",
                )
            except Exception as exc:
                logger.warning("Notif entrée catalogue : %s", exc)

        return await _request_phone(update, context)

    attempts = _password_attempts.setdefault(user_id, [])
    attempts.append(datetime.now())
    attempts[:] = [a for a in attempts if datetime.now() - a < timedelta(minutes=10)]

    if len(attempts) >= MAX_PASSWORD_ATTEMPTS:
        _blocked[user_id] = datetime.now() + timedelta(minutes=BLOCK_DURATION_MIN)
        _password_attempts.pop(user_id, None)
        _save_blocked()
        await update.message.reply_text(t("blocked", lang, min=BLOCK_DURATION_MIN))
        return WAITING_PASSWORD

    await update.message.reply_text(t("wrong_password", lang, n=len(attempts)))
    return WAITING_PASSWORD


# ═════════════════════════════════════════════════════════════════════════════
# Téléphone (M1)
# ═════════════════════════════════════════════════════════════════════════════

async def _request_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _lang(context.user_data)
    kb = ReplyKeyboardMarkup(
        [
            [KeyboardButton(t("btn_share_phone", lang), request_contact=True)],
            [KeyboardButton(t("phone_skip_btn", lang))],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await update.message.reply_text(t("phone_request", lang), reply_markup=kb, parse_mode="Markdown")
    return REQUESTING_PHONE


async def receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ud      = context.user_data
    lang    = _lang(ud)
    contact = update.message.contact
    _touch(ud)
    if contact and contact.phone_number:
        ud["phone"] = contact.phone_number
    await update.message.reply_text(
        t("phone_received", lang),
        reply_markup=ReplyKeyboardRemove(),
    )
    return await _show_countries(update, context)


async def skip_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _lang(context.user_data)
    _touch(context.user_data)
    await update.message.reply_text(
        t("phone_skipped", lang),
        reply_markup=ReplyKeyboardRemove(),
    )
    return await _show_countries(update, context)


# ═════════════════════════════════════════════════════════════════════════════
# Pays / Ville / Menu
# ═════════════════════════════════════════════════════════════════════════════

async def _show_countries(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang      = _lang(context.user_data)
    countries = list(catalog_mod.CATALOG.keys())
    keyboard  = []
    for i in range(0, len(countries), 2):
        row = [InlineKeyboardButton(c, callback_data=f"country:{c}") for c in countries[i:i+2]]
        keyboard.append(row)
    msg = t("choose_country", lang)
    if update.callback_query:
        await update.callback_query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return SELECTING_COUNTRY


async def select_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _touch(context.user_data)
    country = query.data.split(":", 1)[1]
    # Validation : refuser les pays inconnus (injection callback)
    if country not in catalog_mod.CATALOG:
        lang = _lang(context.user_data)
        await query.answer("Pays invalide", show_alert=True)
        return await _show_countries(update, context)
    context.user_data["country"] = country
    context.user_data["cart"]    = {}
    return await _show_cities(update, context)


async def _show_cities(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang    = _lang(context.user_data)
    country = context.user_data["country"]
    cities  = list(catalog_mod.CATALOG[country].keys())
    keyboard = []
    for i in range(0, len(cities), 2):
        row = [InlineKeyboardButton(c, callback_data=f"city:{c}") for c in cities[i:i+2]]
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton(t("back_countries", lang), callback_data="back:countries")])
    msg = t("choose_city", lang, country=country)
    if update.callback_query:
        await update.callback_query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return SELECTING_CITY


async def select_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _touch(context.user_data)
    if query.data == "back:countries":
        return await _show_countries(update, context)
    city = query.data.split(":", 1)[1]
    # Validation : refuser les villes inconnues pour le pays sélectionné
    country = context.user_data.get("country")
    if not country or country not in catalog_mod.CATALOG or city not in catalog_mod.CATALOG[country]:
        await query.answer("Ville invalide", show_alert=True)
        return await _show_cities(update, context)
    context.user_data["city"] = city
    context.user_data["cart"] = {}
    return await _show_menu(update, context)


async def _show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ud   = context.user_data
    lang = _lang(ud)

    # H1: Protéger contre les KeyError après /reload
    try:
        country  = ud["country"]
        city     = ud["city"]
        menu     = catalog_mod.CATALOG[country][city]
        currency = catalog_mod.get_currency(country)
    except KeyError:
        if update.callback_query:
            await update.callback_query.answer(t("generic_error", lang), show_alert=True)
        return await _show_countries(update, context)

    cart     = ud.get("cart", {})
    keyboard = []
    for item, price in menu.items():
        qty   = cart.get(item, 0)
        label = f"{item} — {price:,.0f} {currency}"
        if qty > 0:
            label += f"   ×{qty}"
        keyboard.append([InlineKeyboardButton(label, callback_data="noop")])
        keyboard.append([
            InlineKeyboardButton("➖", callback_data=f"menu_minus:{item}"),
            InlineKeyboardButton(f"  {qty}  ", callback_data="noop"),
            InlineKeyboardButton("➕", callback_data=f"menu_plus:{item}"),
        ])

    cart_total = sum(menu[i] * q for i, q in cart.items() if i in menu)
    cart_count = sum(cart.values())

    if cart_count > 0:
        keyboard.append([InlineKeyboardButton(
            t("view_cart", lang, n=cart_count, total=f"{cart_total:,.0f}", cur=currency),
            callback_data="view:cart",
        )])

    if ud.get("modifying") != "cart":
        keyboard.append([InlineKeyboardButton(t("back_cities", lang), callback_data="back:cities")])

    # Afficher la note de minimum de commande dans le titre du menu
    msg = t("menu_title", lang, city=city)
    min_rule = getattr(catalog_mod, "MIN_ORDER", {}).get(city)
    if min_rule:
        if min_rule["type"] == "amount":
            msg += "\n" + t("min_note_amount", lang,
                             min=f"{min_rule['value']:,.0f}", cur=currency)
        else:
            msg += "\n" + t("min_note_qty", lang, min=min_rule["value"])

    if update.callback_query:
        await update.callback_query.edit_message_text(
            msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )
    return BROWSING_MENU


async def browse_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    data  = query.data
    _touch(context.user_data)

    if data == "noop":
        await query.answer()
        return BROWSING_MENU
    if data == "back:cities":
        await query.answer()
        return await _show_cities(update, context)
    if data == "view:cart":
        await query.answer()
        return await _show_cart(update, context)
    if data.startswith("menu_plus:"):
        item = data.split(":", 1)[1]
        cart = context.user_data.get("cart", {})
        cart[item] = cart.get(item, 0) + 1
        context.user_data["cart"] = cart
        await query.answer(f"➕ {item}")
        return await _show_menu(update, context)
    if data.startswith("menu_minus:"):
        item = data.split(":", 1)[1]
        cart = context.user_data.get("cart", {})
        if cart.get(item, 0) > 1:
            cart[item] -= 1
        else:
            cart.pop(item, None)
        context.user_data["cart"] = cart
        await query.answer(f"➖ {item}")
        return await _show_menu(update, context)
    await query.answer()
    return BROWSING_MENU


# ═════════════════════════════════════════════════════════════════════════════
# Panier
# ═════════════════════════════════════════════════════════════════════════════

async def _show_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ud       = context.user_data
    lang     = _lang(ud)
    query    = update.callback_query
    country  = ud["country"]
    city     = ud["city"]
    cart     = ud.get("cart", {})
    menu     = catalog_mod.CATALOG[country][city]
    currency = catalog_mod.get_currency(country)

    if not cart:
        try:
            await query.answer(t("cart_empty", lang))
        except Exception:
            pass
        return await _show_menu(update, context)

    lines    = [t("cart_title", lang)]
    total    = 0
    keyboard = []
    for item, qty in cart.items():
        if item in menu:
            sub    = menu[item] * qty
            total += sub
            lines.append(f"• {item} ×{qty} — {sub:,.0f} {currency}")
            keyboard.append([
                InlineKeyboardButton("➕", callback_data=f"cart_add:{item}"),
                InlineKeyboardButton(f"  {item[:22]}  ", callback_data="noop"),
                InlineKeyboardButton("➖", callback_data=f"cart_remove:{item}"),
                InlineKeyboardButton("🗑️", callback_data=f"cart_delete:{item}"),
            ])

    lines.append("\n" + t("cart_total", lang, total=f"{total:,.0f}", cur=currency))

    # Vérification du minimum de commande (amount € ou quantité articles)
    min_rule  = getattr(catalog_mod, "MIN_ORDER", {}).get(city)
    min_ok    = True

    if min_rule:
        if min_rule["type"] == "amount":
            min_val = min_rule["value"]
            if total < min_val:
                min_ok = False
                diff = min_val - total
                lines.append("\n" + t("min_order_required", lang,
                                      min=f"{min_val:,.0f}", cur=currency,
                                      diff=f"{diff:,.0f}"))
                # Bouton verrouillé avec ce qui manque
                keyboard.append([InlineKeyboardButton(
                    f"🔒 Minimum {min_val:,.0f}{currency} — encore {diff:,.0f}{currency}",
                    callback_data="noop",
                )])
        elif min_rule["type"] == "qty":
            min_qty   = min_rule["value"]
            cart_qty  = sum(cart.values())
            if cart_qty < min_qty:
                min_ok = False
                diff_q = min_qty - cart_qty
                lines.append("\n" + t("min_order_qty_required", lang,
                                      min=min_qty, diff=diff_q))
                # Bouton verrouillé avec ce qui manque
                manque = f"{diff_q} article" + ("s" if diff_q > 1 else "")
                keyboard.append([InlineKeyboardButton(
                    f"🔒 Minimum {min_qty} articles — encore {manque}",
                    callback_data="noop",
                )])

    if min_ok:
        if ud.get("modifying") == "cart":
            keyboard.append([InlineKeyboardButton(t("btn_validate_changes", lang), callback_data="checkout")])
        else:
            keyboard.append([InlineKeyboardButton(t("btn_checkout", lang), callback_data="checkout")])

    keyboard.append([InlineKeyboardButton(t("btn_continue_shopping", lang), callback_data="back:menu")])

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )
    return VIEWING_CART


async def manage_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data  = query.data
    cart  = context.user_data.get("cart", {})
    _touch(context.user_data)

    if data == "noop":
        return VIEWING_CART
    if data == "back:menu":
        return await _show_menu(update, context)
    if data == "checkout":
        if context.user_data.get("modifying") == "cart":
            return await _finalize_cart_modification(update, context)
        return await _show_payment(update, context)

    if data.startswith("cart_add:"):
        item = data.split(":", 1)[1]
        cart[item] = cart.get(item, 0) + 1
    elif data.startswith("cart_remove:"):
        item = data.split(":", 1)[1]
        if cart.get(item, 0) > 1:
            cart[item] -= 1
        else:
            cart.pop(item, None)
    elif data.startswith("cart_delete:"):
        item = data.split(":", 1)[1]
        cart.pop(item, None)

    context.user_data["cart"] = cart
    if not cart:
        return await _show_menu(update, context)
    return await _show_cart(update, context)


# ═════════════════════════════════════════════════════════════════════════════
# Paiement
# ═════════════════════════════════════════════════════════════════════════════

async def _show_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang  = _lang(context.user_data)
    query = update.callback_query
    keyboard = [
        [
            InlineKeyboardButton(t("pay_btn_cash",     lang), callback_data="pay_method:cash"),
            InlineKeyboardButton(t("pay_btn_virement", lang), callback_data="pay_method:virement"),
        ],
        [
            InlineKeyboardButton(t("pay_btn_link",   lang), callback_data="pay_method:link"),
            InlineKeyboardButton(t("pay_btn_crypto", lang), callback_data="pay_method:crypto"),
        ],
        [InlineKeyboardButton(t("back_cart", lang), callback_data="back:cart")],
    ]
    await query.edit_message_text(
        t("choose_payment", lang),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )
    return SELECTING_PAYMENT


async def _send_crypto_qr(query, context, lang: str, *, name: str, icon: str, address: str) -> None:
    """Envoie l'adresse crypto sous forme de QR code + bouton 'Copier'.
    Remplace l'écran texte précédent par une photo avec inline keyboard.

    Download le QR en bytes nous-mêmes (httpx) puis upload à Telegram :
    plus fiable que de passer une URL externe que Telegram doit fetcher
    (certaines APIs sont bloquées côté serveurs Telegram → HTTP 400).
    """
    caption = t("pay_crypto_caption", lang, icon=icon, name=name, address=address)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("btn_copy_address", lang), copy_text=CopyTextButton(text=address))],
        [InlineKeyboardButton(t("btn_crypto_sent",  lang), callback_data="pay_crypto:paid")],
        [InlineKeyboardButton(t("btn_pay_back",     lang), callback_data="pay:back")],
    ])

    # Télécharger le QR code via plusieurs services (failover)
    qr_bytes = None
    import httpx
    qr_services = [
        f"https://quickchart.io/qr?text={address}&size=512&margin=4",
        f"https://api.qrserver.com/v1/create-qr-code/?size=512x512&margin=10&data={address}",
    ]
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        for url in qr_services:
            try:
                r = await client.get(url)
                if r.status_code == 200 and len(r.content) > 100:
                    qr_bytes = r.content
                    break
            except Exception as exc:
                logger.debug("QR service %s failed: %s", url, exc)

    # Supprimer le message texte précédent (panel de choix crypto)
    try:
        await query.message.delete()
    except Exception as exc:
        logger.debug("Impossible de supprimer le msg crypto précédent : %s", exc)

    # Envoyer la photo (bytes) avec fallback texte si tout a échoué
    if qr_bytes:
        try:
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=BytesIO(qr_bytes),
                caption=caption,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
            return
        except Exception as exc:
            logger.warning("send_photo %s échoué (%s) — fallback texte", name, exc)

    # Fallback : juste le texte avec l'adresse (pas de QR)
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=caption,
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


async def select_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gère tous les callbacks de l'écran paiement et ses sous-menus.
    IMPORTANT : query.answer() est appelé dans chaque branche (jamais en tête)
    pour éviter le double-answer qui lèverait une BadRequest Telegram.
    """
    query = update.callback_query
    ud   = context.user_data
    lang = _lang(ud)
    data = query.data
    _touch(ud)

    # ── Retour panier ─────────────────────────────────────────────────────
    if data == "back:cart":
        await query.answer()
        return await _show_cart(update, context)

    # ── Retour écran paiement ─────────────────────────────────────────────
    if data == "pay:back":
        await query.answer()
        return await _show_payment(update, context)

    # ══════════════════════════════════════════════════════════════════════
    # 1. CASH → sous-menu devises
    # ══════════════════════════════════════════════════════════════════════
    if data == "pay_method:cash":
        await query.answer()
        currencies = [
            ("EUR", "🇪🇺 EUR — Euro"),
            ("USD", "🇺🇸 USD — Dollar"),
            ("GBP", "🇬🇧 GBP — Livre sterling"),
            ("CHF", "🇨🇭 CHF — Franc suisse"),
            ("AED", "🇦🇪 AED — Dirham EAU"),
            ("MAD", "🇲🇦 MAD — Dirham marocain"),
        ]
        keyboard = [[InlineKeyboardButton(label, callback_data=f"pay_cash:{code}")]
                    for code, label in currencies]
        keyboard.append([InlineKeyboardButton(t("btn_pay_back", lang), callback_data="pay:back")])
        await query.edit_message_text(
            t("pay_choose_currency", lang),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
        return SELECTING_PAYMENT

    if data.startswith("pay_cash:"):
        await query.answer()
        cur = data.split(":", 1)[1]
        ud["payment_key"]   = "pay_btn_cash"
        ud["payment_label"] = f"💵 Cash — {cur}"
        await query.edit_message_text(
            t("pay_cash_confirmed", lang, cur=cur),
            parse_mode="Markdown",
        )
        return ENTERING_ADDRESS

    # ══════════════════════════════════════════════════════════════════════
    # 2. VIREMENT BANCAIRE → attend capture d'écran (AWAITING_TRANSFER_PROOF)
    # ══════════════════════════════════════════════════════════════════════
    if data == "pay_method:virement":
        await query.answer()
        ud["payment_key"]   = "pay_btn_virement"
        ud["payment_label"] = t("pay_btn_virement", lang)
        iban_display = BANK_IBAN if BANK_IBAN else "⚠️ Non configuré"
        back_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(t("btn_pay_back", lang), callback_data="pay:back")],
        ])
        await query.edit_message_text(
            t("pay_virement_info", lang, iban=iban_display),
            reply_markup=back_kb,
            parse_mode="Markdown",
        )
        return AWAITING_TRANSFER_PROOF

    # ══════════════════════════════════════════════════════════════════════
    # 3. LIEN DE PAIEMENT
    # ══════════════════════════════════════════════════════════════════════
    if data == "pay_method:link":
        if not PAYMENT_LINK:
            # show_alert n'est valide que si la query n'est pas encore répondue
            await query.answer(t("pay_link_not_configured", lang), show_alert=True)
            return SELECTING_PAYMENT
        await query.answer()
        ud["payment_key"]   = "pay_btn_link"
        ud["payment_label"] = t("pay_btn_link", lang)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(t("btn_i_paid",   lang), callback_data="pay_link:paid")],
            [InlineKeyboardButton(t("btn_pay_back", lang), callback_data="pay:back")],
        ])
        await query.edit_message_text(
            t("pay_link_info", lang, link=PAYMENT_LINK),
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        return SELECTING_PAYMENT

    if data == "pay_link:paid":
        await query.answer()
        await query.edit_message_text(
            t("pay_link_confirmed", lang),
            parse_mode="Markdown",
        )
        return ENTERING_ADDRESS

    # ══════════════════════════════════════════════════════════════════════
    # 4. CRYPTO → sous-menu ETH / USDT
    # ══════════════════════════════════════════════════════════════════════
    if data == "pay_method:crypto":
        await query.answer()
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⟠ ETH",  callback_data="pay_crypto:eth"),
                InlineKeyboardButton("₮ USDT", callback_data="pay_crypto:usdt"),
            ],
            [InlineKeyboardButton(t("btn_pay_back", lang), callback_data="pay:back")],
        ])
        await query.edit_message_text(
            t("pay_crypto_choose", lang),
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        return SELECTING_PAYMENT

    if data == "pay_crypto:eth":
        if not CRYPTO_ETH:
            await query.answer(t("pay_crypto_not_configured", lang, name="ETH"), show_alert=True)
            return SELECTING_PAYMENT
        await query.answer()
        ud["payment_key"]   = "pay_btn_crypto"
        ud["payment_label"] = "₿ Crypto — ETH"
        await _send_crypto_qr(query, context, lang, name="ETH", icon="⟠", address=CRYPTO_ETH)
        return SELECTING_PAYMENT

    if data == "pay_crypto:usdt":
        if not CRYPTO_USDT:
            await query.answer(t("pay_crypto_not_configured", lang, name="USDT"), show_alert=True)
            return SELECTING_PAYMENT
        await query.answer()
        ud["payment_key"]   = "pay_btn_crypto"
        ud["payment_label"] = "₿ Crypto — USDT"
        await _send_crypto_qr(query, context, lang, name="USDT", icon="₮", address=CRYPTO_USDT)
        return SELECTING_PAYMENT

    if data == "pay_crypto:paid":
        await query.answer()
        name = ud.get("payment_label", "Crypto").replace("₿ Crypto — ", "")
        await query.edit_message_text(
            t("pay_crypto_confirmed", lang, name=name),
            parse_mode="Markdown",
        )
        return ENTERING_ADDRESS

    await query.answer(t("generic_error", lang), show_alert=True)
    logger.warning("select_payment: donnée inattendue — %s", data)
    return SELECTING_PAYMENT


# ═════════════════════════════════════════════════════════════════════════════
# Preuve de virement bancaire
# ═════════════════════════════════════════════════════════════════════════════

async def handle_transfer_proof(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Attend la capture d'écran du virement (AWAITING_TRANSFER_PROOF)."""
    ud   = context.user_data
    lang = _lang(ud)
    _touch(ud)

    if update.message.photo:
        ud["transfer_proof_file_id"] = update.message.photo[-1].file_id
        await update.message.reply_text(
            t("pay_virement_received", lang),
            parse_mode="Markdown",
        )
        return ENTERING_ADDRESS

    # Pas une photo → demander à nouveau
    await update.message.reply_text(
        t("pay_virement_need_photo", lang),
        parse_mode="Markdown",
    )
    return AWAITING_TRANSFER_PROOF


# ═════════════════════════════════════════════════════════════════════════════
# Adresse (Nominatim)
# ═════════════════════════════════════════════════════════════════════════════

def _geocode_nominatim(address: str,
                       city_hint: str = "",
                       country_hint: str = "") -> dict:
    """Retourne {formatted, lat, lon, maps_link} OU {error: 'notfound'|'service'}.

    Stratégie à deux passes :
      1. Recherche brute du texte fourni par le client (rue, code postal, monument…)
      2. Si introuvable et qu'un contexte géo est disponible, second essai avec
         « {adresse}, {ville}, {pays} » — permet de retrouver "Moulin Rouge",
         "Tour Eiffel", "Hard Rock Café", etc. sans adresse postale complète.
    """
    def _search(query: str) -> dict:
        try:
            resp = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": query, "format": "json", "limit": 1, "addressdetails": 1},
                headers={"User-Agent": "MillesimeCoffeeBot/1.0"},
                timeout=10,
            )
            if resp.status_code != 200:
                return {"error": "service"}
            results = resp.json()
            if not results:
                return {"error": "notfound"}
            r = results[0]

            # ── Adresse courte depuis les champs structurés Nominatim ──────
            addr_obj = r.get("address", {})
            number   = addr_obj.get("house_number", "").strip()
            road     = (
                addr_obj.get("road") or addr_obj.get("pedestrian") or
                addr_obj.get("footway") or addr_obj.get("street") or
                addr_obj.get("place") or ""
            ).strip()
            city_val = (
                addr_obj.get("city") or addr_obj.get("town") or
                addr_obj.get("village") or addr_obj.get("municipality") or
                addr_obj.get("district") or addr_obj.get("county") or ""
            ).strip()
            postcode = addr_obj.get("postcode", "").strip()

            line1 = f"{number} {road}".strip().upper() if road else ""
            line2 = city_val.upper()
            short_parts = [l for l in [line1, line2, postcode] if l]
            short_addr  = "\n".join(short_parts) if short_parts else r.get("display_name", query)

            return {
                "formatted": r.get("display_name", query),
                "short":     short_addr,
                "lat":       r["lat"],
                "lon":       r["lon"],
                "maps_link": (
                    f"https://www.openstreetmap.org/"
                    f"?mlat={r['lat']}&mlon={r['lon']}&zoom=17"
                ),
            }
        except (requests.RequestException, ValueError) as exc:
            logger.warning("Nominatim error: %s", exc)
            return {"error": "service"}

    # Passe 1 : requête brute
    result = _search(address)

    # Passe 2 : ajouter le contexte géographique si pas trouvé
    if result.get("error") == "notfound" and city_hint:
        parts = [address, city_hint]
        if country_hint:
            parts.append(country_hint)
        result = _search(", ".join(parts))

    return result


async def handle_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ud   = context.user_data
    lang = _lang(ud)
    _touch(ud)
    address_text = update.message.text.strip()

    # Contexte géo du client (pour le fallback monument/lieu)
    city    = ud.get("city", "")
    country = ud.get("country", "")
    # Enlever le drapeau emoji du pays (ex : "🇫🇷 France" → "France")
    country_clean = country.split(" ", 1)[1].strip() if " " in country else country

    loading_msg = await update.message.reply_text(t("searching_address", lang))
    # C10: Nominatim est sync (requests) → wrap dans un thread pour ne pas
    # freezer tout le bot pendant les ~10s du timeout HTTP
    import asyncio
    result = await asyncio.to_thread(
        _geocode_nominatim,
        address_text,
        city_hint=city,
        country_hint=country_clean,
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("btn_addr_yes", lang), callback_data="addr:confirm")],
        [InlineKeyboardButton(t("btn_addr_no",  lang), callback_data="addr:change")],
    ])

    if "error" not in result:
        ud["address"]   = result["short"]
        ud["maps_link"] = result["maps_link"]
        await loading_msg.edit_text(
            t("address_found", lang, addr=result["short"], link=result["maps_link"]),
            reply_markup=keyboard,
            parse_mode="Markdown",
            disable_web_page_preview=False,
        )
    elif result["error"] == "service":
        ud["address"]   = address_text
        ud["maps_link"] = ""
        await loading_msg.edit_text(
            t("address_service_down", lang, addr=address_text),
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
    else:
        ud["address"]   = address_text
        ud["maps_link"] = ""
        await loading_msg.edit_text(
            t("address_unverified", lang, addr=address_text),
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
    return CONFIRMING_ADDRESS


async def confirm_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    ud   = context.user_data
    lang = _lang(ud)
    _touch(ud)

    if query.data == "addr:change":
        await query.edit_message_text(t("enter_new_address", lang), parse_mode="Markdown")
        return ENTERING_ADDRESS

    modifying = ud.get("modifying")
    if modifying == "address":
        order_id  = ud.get("order_id", "N/A")
        address   = ud.get("address", "—")
        maps_link = ud.get("maps_link", "")

        # Mettre à jour orders.json avec la nouvelle adresse
        try:
            update_order(order_id, {"address": address, "maps_link": maps_link})
        except Exception as exc:
            logger.error("update_order (adresse) : %s", exc)

        if OWNER_CHAT_ID:
            try:
                user = update.effective_user
                await context.bot.send_message(
                    chat_id=OWNER_CHAT_ID,
                    text=(
                        f"✏️ <b>Adresse modifiée</b> — Commande <code>{_safe_html(order_id)}</code>\n"
                        f"Client : {_safe_html(user.first_name)}\n"
                        f"Nouvelle adresse : <code>{_safe_html(address)}</code>"
                    ),
                    parse_mode="HTML",
                )
            except Exception as exc:
                logger.error("Notif modif adresse: %s", exc)
        ud.pop("modifying", None)
        await query.edit_message_text(
            t("address_updated", lang, a=address),
            reply_markup=_management_keyboard(lang),
            parse_mode="Markdown",
        )
        return ORDER_MANAGEMENT

    # Flux normal : C1 — générer token one-time et demander selfie en direct
    await query.edit_message_text(t("address_confirmed", lang))

    if WEBAPP_URL:
        user_id = str(update.effective_user.id)
        token   = secrets.token_urlsafe(16)
        ud["selfie_token"] = token
        from webapp import register_token
        register_token(user_id, token)
        kb = _selfie_webapp_keyboard(user_id, lang, token)
        await query.message.reply_text(
            t("selfie_webapp", lang),
            reply_markup=kb,
            parse_mode="Markdown",
        )
    else:
        await query.message.reply_text(
            t("selfie_fallback", lang),
            parse_mode="Markdown",
        )
    return SENDING_SELFIE


# ═════════════════════════════════════════════════════════════════════════════
# Selfie
# ═════════════════════════════════════════════════════════════════════════════

async def handle_web_app_selfie(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from webapp import get_selfie
    ud   = context.user_data
    lang = _lang(ud)
    _touch(ud)

    data = update.message.web_app_data.data if update.message.web_app_data else ""
    if data != "SELFIE_OK":
        await update.message.reply_text(t("selfie_error", lang), reply_markup=ReplyKeyboardRemove())
        return SENDING_SELFIE

    user_id     = str(update.effective_user.id)
    selfie_data = get_selfie(user_id)
    if selfie_data and selfie_data.get("photo"):
        ud["selfie_bytes"] = selfie_data["photo"]

    await update.message.reply_text(
        t("selfie_ok", lang),
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown",
    )

    summary  = _order_summary(ud)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("btn_confirm_order", lang), callback_data="order:confirm")],
        [InlineKeyboardButton(t("btn_cancel",         lang), callback_data="order:cancel")],
    ])
    await update.message.reply_text(summary, reply_markup=keyboard, parse_mode="Markdown")
    return CONFIRMING_ORDER


async def handle_selfie(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ud   = context.user_data
    lang = _lang(ud)
    _touch(ud)

    # Bloquer les photos de galerie/caméra quand la Mini App est active
    # → seul le selfie en direct via le bouton WebApp est accepté
    if WEBAPP_URL and update.message.photo:
        user_id = str(update.effective_user.id)
        token   = ud.get("selfie_token", "")
        kb = _selfie_webapp_keyboard(user_id, lang, token)
        await update.message.reply_text(
            t("selfie_photo_blocked", lang),
            reply_markup=kb,
            parse_mode="Markdown",
        )
        return SENDING_SELFIE

    if not update.message.photo:
        # L'utilisateur a envoyé du texte → lui rappeler d'utiliser le bouton
        if WEBAPP_URL:
            user_id = str(update.effective_user.id)
            token   = ud.get("selfie_token", "")
            kb = _selfie_webapp_keyboard(user_id, lang, token)
            await update.message.reply_text(
                t("selfie_use_button", lang),
                reply_markup=kb,
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(t("selfie_need_photo", lang), parse_mode="Markdown")
        return SENDING_SELFIE

    # Selfie direct accepté (WEBAPP_URL non actif — mode fallback)
    ud["selfie_file_id"] = update.message.photo[-1].file_id

    await update.message.reply_text(t("selfie_ok", lang), parse_mode="Markdown")

    summary  = _order_summary(ud)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("btn_confirm_order", lang), callback_data="order:confirm")],
        [InlineKeyboardButton(t("btn_cancel",         lang), callback_data="order:cancel")],
    ])
    await update.message.reply_text(summary, reply_markup=keyboard, parse_mode="Markdown")
    return CONFIRMING_ORDER


# ═════════════════════════════════════════════════════════════════════════════
# Confirmation finale
# ═════════════════════════════════════════════════════════════════════════════

async def _send_order_receipt(context: ContextTypes.DEFAULT_TYPE,
                              user, ud: dict, order_id: str) -> None:
    """Envoie automatiquement le bon de commande au client dès la confirmation.

    Envoyé depuis le compte personnel @millesimecoffee (Telethon) si disponible,
    sinon depuis le bot en fallback.
    """
    lang = _lang(ud)
    try:
        country  = ud["country"]
        city     = ud["city"]
        cart     = ud["cart"]
        menu     = catalog_mod.CATALOG[country][city]
        currency = catalog_mod.get_currency(country)
    except KeyError:
        logger.warning("_send_order_receipt: données manquantes")
        return

    total   = ud.get("order_total", 0)
    pay_str = ud.get("payment_label") or (
        t(ud["payment_key"], lang) if ud.get("payment_key") else "—"
    )
    address = ud.get("address", "—")

    SEP = "━━━━━━━━━━━━━━━━━"
    lines = [
        t("receipt_title", lang, id=order_id),
        f"_{datetime.now().strftime('%d/%m/%Y %H:%M')}_",
        "",
        SEP,
        t("receipt_items", lang),
    ]
    for item, qty in cart.items():
        if item in menu:
            lines.append(f"  • {item} ×{qty} — {menu[item] * qty:,.0f} {currency}")
    lines += [
        "",
        f"💸 *{total:,.0f} {currency}*",
        f"_{pay_str}_",
        "",
        SEP,
        t("receipt_address", lang),
        f"`{address}`",
        SEP,
        "",
        t("receipt_thanks", lang),
    ]
    text = "\n".join(lines)

    # Envoi depuis le compte personnel (Telethon) si disponible
    sent = False
    try:
        from personal_sender import send_personal_message, is_ready
        if is_ready():
            sent = await send_personal_message(user.id, text)
    except Exception as exc:
        logger.warning("Receipt Telethon : %s", exc)

    # Fallback : envoi depuis le bot
    if not sent:
        try:
            await context.bot.send_message(
                chat_id=user.id,
                text=text,
                parse_mode="Markdown",
            )
        except Exception as exc:
            logger.error("Receipt bot : %s", exc)


async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    ud   = context.user_data
    lang = _lang(ud)
    _touch(ud)

    if query.data == "order:cancel":
        await query.edit_message_text(t("order_cancelled", lang))
        return ConversationHandler.END

    # H1 + H9: Générer l'ID ET sauvegarder en DB AVANT de notifier le owner.
    # Sinon (1) collision possible sur 2 commandes simultanées, (2) si save
    # échoue, owner croit avoir reçu une cmd qui n'existe pas en DB.
    order_id = _generate_order_id()
    ud["order_id"] = order_id

    user = update.effective_user
    pay_label = ud.get("payment_label") or (
        t(ud["payment_key"], "fr") if ud.get("payment_key") else ""
    )
    order_data = {
        "order_id":  order_id,
        "user_id":   user.id,
        "user_name": user.first_name,
        "username":  user.username,
        "lang":      lang,
        "country":   ud.get("country"),
        "city":      ud.get("city"),
        "cart":      ud.get("cart", {}),
        "total":     ud.get("order_total", 0),
        "payment":   pay_label,
        "address":   ud.get("address"),
        "phone":     ud.get("phone", ""),
        "maps_link": ud.get("maps_link", ""),
        "status":    "pending",
    }
    try:
        save_order(order_data)
    except Exception as exc:
        logger.error("Sauvegarde commande échouée: %s", exc)
        # Continuer quand même : l'owner doit voir la cmd même si DB down.

    await query.edit_message_text(
        t("order_confirmed", lang, id=order_id),
        reply_markup=_management_keyboard(lang),
        parse_mode="Markdown",
    )

    await _notify_owner(context, update.effective_user, ud, order_id)

    # Envoyer le bon de commande au client depuis le compte @millesimecoffee
    await _send_order_receipt(context, update.effective_user, ud, order_id)

    # H2: Libérer la mémoire selfie + preuve virement après envoi à l'owner
    ud.pop("selfie_bytes",           None)
    ud.pop("selfie_file_id",         None)
    ud.pop("selfie_token",           None)
    ud.pop("transfer_proof_file_id", None)

    # Fenêtre d'annulation 2 min — message bot avec bouton
    try:
        cancel_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(t("client_cancel_btn", lang),
                                 callback_data=f"client_cancel:{order_id}")
        ]])
        cancel_msg = await context.bot.send_message(
            chat_id=update.effective_user.id,
            text=t("client_cancel_window", lang),
            reply_markup=cancel_kb,
            parse_mode="Markdown",
        )
        # Programme l'expiration du bouton dans 120 s
        if context.job_queue:
            context.job_queue.run_once(
                _expire_cancel_button,
                when=120,
                data={"chat_id": cancel_msg.chat_id,
                      "message_id": cancel_msg.message_id,
                      "lang": lang},
                name=f"cancel_expire_{order_id}",
            )
    except Exception as exc:
        logger.warning("Envoi bouton annulation : %s", exc)

    return ORDER_MANAGEMENT


# ═════════════════════════════════════════════════════════════════════════════
# Gestion post-commande
# ═════════════════════════════════════════════════════════════════════════════

async def order_management(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    ud     = context.user_data
    lang   = _lang(ud)
    _touch(ud)
    action = query.data.split(":", 1)[1]

    if action == "cancel":
        await query.edit_message_text(
            t("confirm_cancel", lang),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t("btn_yes_cancel", lang), callback_data="manage:do_cancel")],
                [InlineKeyboardButton(t("btn_keep_order", lang), callback_data="manage:keep")],
            ]),
            parse_mode="Markdown",
        )

    elif action == "do_cancel":
        order_id = ud.get("order_id", "N/A")
        # Mettre à jour le status en DB (sinon /stats compte la cmd comme pending)
        try:
            update_order(order_id, {"status": "cancelled"})
        except Exception as exc:
            logger.error("update_order cancelled: %s", exc)
        if OWNER_CHAT_ID:
            try:
                user = update.effective_user
                await context.bot.send_message(
                    chat_id=OWNER_CHAT_ID,
                    text=(
                        f"❌ <b>Commande annulée</b> : <code>{_html.escape(order_id)}</code>\n"
                        f"Client : {_html.escape(user.first_name or '?')}"
                    ),
                    parse_mode="HTML",
                )
            except Exception as exc:
                logger.error("Notif annulation owner: %s", exc)
        await query.edit_message_text(t("order_cancelled_final", lang))
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=t("restart_hint", lang),
            reply_markup=_restart_keyboard(),
        )
        return ConversationHandler.END

    elif action == "keep":
        await query.edit_message_text(
            t("order_kept", lang),
            reply_markup=_management_keyboard(lang),
            parse_mode="Markdown",
        )

    elif action == "address":
        ud["modifying"] = "address"
        await query.edit_message_text(t("enter_new_address", lang), parse_mode="Markdown")
        return ENTERING_ADDRESS

    elif action == "cart":
        ud["modifying"] = "cart"
        return await _show_menu(update, context)

    return ORDER_MANAGEMENT


async def _finalize_cart_modification(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query    = update.callback_query
    ud       = context.user_data
    lang     = _lang(ud)
    summary  = _order_summary(ud)   # met à jour ud["order_total"]
    order_id = ud.get("order_id", "N/A")

    # Mettre à jour orders.json avec le nouveau panier et le nouveau total
    try:
        update_order(order_id, {
            "cart":  ud.get("cart", {}),
            "total": ud.get("order_total", 0),
        })
    except Exception as exc:
        logger.error("update_order (panier) : %s", exc)

    # Notif owner — formatée en HTML (sans passer par _order_summary Markdown)
    if OWNER_CHAT_ID:
        try:
            user     = update.effective_user
            country  = ud.get("country", "")
            city     = ud.get("city", "")
            currency = catalog_mod.get_currency(country)
            menu     = catalog_mod.CATALOG[country][city]
            new_total = ud.get("order_total", 0)

            cart_html = "\n".join(
                f"  • {_html.escape(item)} ×{qty} — {menu[item] * qty:,.0f} {currency}"
                for item, qty in (ud.get("cart") or {}).items()
                if item in menu
            ) or "  (panier vide)"

            await context.bot.send_message(
                chat_id=OWNER_CHAT_ID,
                text=(
                    f"✏️ <b>Panier modifié</b> — "
                    f"Commande <code>{_safe_html(order_id)}</code>\n"
                    f"Client : {_safe_html(user.first_name)}\n\n"
                    f"🛒 Nouveau panier :\n{cart_html}\n\n"
                    f"💸 Nouveau total : <b>{new_total:,.0f} {currency}</b>"
                ),
                parse_mode="HTML",
            )
        except Exception as exc:
            logger.error("Notif modif panier: %s", exc)

    ud.pop("modifying", None)
    await query.edit_message_text(
        t("cart_updated", lang, s=summary),
        reply_markup=_management_keyboard(lang),
        parse_mode="Markdown",
    )
    return ORDER_MANAGEMENT


# ═════════════════════════════════════════════════════════════════════════════
# Suivi (owner → client)
# ═════════════════════════════════════════════════════════════════════════════

async def owner_status_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gestion des boutons de statut owner.

    Envoi AUTOMATIQUE au client :
    - Si TELEGRAM_SESSION configuré → message envoyé depuis le compte PERSONNEL de l'admin
    - Sinon → message envoyé depuis le bot (fallback automatique)
    """
    query = update.callback_query

    # Sécurité : seul l'owner peut déclencher ces boutons
    if not _is_owner(update):
        await query.answer("⛔ Action non autorisée.", show_alert=True)
        return

    await query.answer()

    parts     = query.data.split(":")   # owner:STATUS:USER_ID:ORDER_ID
    status    = parts[1]
    client_id = int(parts[2])
    order_id  = parts[3] if len(parts) > 3 else "N/A"

    # H6: idempotence — si la cmd est déjà dans ce statut, on ignore (évite spam client)
    current_order = get_order(order_id)
    if current_order:
        client_lang = current_order.get("lang", "fr")
        if current_order.get("status") == status:
            await query.answer(f"Statut déjà = {status}", show_alert=False)
            return
    else:
        client_lang = "fr"

    # Marquer le nouveau statut en DB immédiatement (évite double-clic concurrent)
    try:
        update_order(order_id, {"status": status})
    except Exception as exc:
        logger.warning("update_order(%s, status=%s): %s", order_id, status, exc)

    # Texte du message selon le statut
    messages = {
        "confirmed":  t("status_confirmed",       client_lang, id=order_id),
        "delivering": t("status_delivering",      client_lang, id=order_id),
        "delivered":  t("status_delivered",       client_lang, id=order_id),
        "cancelled":  t("status_cancelled_owner", client_lang, id=order_id),
    }
    status_labels = {
        "confirmed":  "✅ Confirmée",
        "delivering": "🚚 En livraison",
        "delivered":  "📦 Livrée",
        "cancelled":  "❌ Annulée",
    }

    msg_text = messages.get(status, "Mise à jour de votre commande.")
    label    = status_labels.get(status, status)

    # ── Envoi automatique du message au client ────────────────────────────────
    sent_personally = False
    try:
        from personal_sender import send_personal_message, is_ready
        if is_ready():
            sent_personally = await send_personal_message(client_id, msg_text)
    except Exception as exc:
        logger.warning("Telethon send ignoré : %s", exc)

    if not sent_personally:
        try:
            await context.bot.send_message(
                chat_id=client_id,
                text=msg_text,
                parse_mode="Markdown",
            )
        except Exception as exc:
            logger.error("Fallback bot send_message : %s", exc)

    # ── Feature 9 : demande de note après livraison ───────────────────────────
    if status == "delivered":
        try:
            rating_kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("⭐",     callback_data=f"rate:1:{order_id}"),
                InlineKeyboardButton("⭐⭐",   callback_data=f"rate:2:{order_id}"),
                InlineKeyboardButton("⭐⭐⭐", callback_data=f"rate:3:{order_id}"),
                InlineKeyboardButton("⭐⭐⭐⭐",   callback_data=f"rate:4:{order_id}"),
                InlineKeyboardButton("⭐⭐⭐⭐⭐", callback_data=f"rate:5:{order_id}"),
            ]])
            await context.bot.send_message(
                chat_id=client_id,
                text=t("rating_request", client_lang, id=order_id),
                reply_markup=rating_kb,
                parse_mode="Markdown",
            )
        except Exception as exc:
            logger.warning("Rating request : %s", exc)

    # ── Mettre à jour le clavier de la notification ───────────────────────────
    source_label = "💬 depuis ton compte" if sent_personally else "🤖 depuis le bot"
    try:
        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📱 Contacter le client",   url=f"tg://user?id={client_id}")],
                [InlineKeyboardButton("✅ Commande confirmée",     callback_data=f"owner:confirmed:{client_id}:{order_id}")],
                [InlineKeyboardButton("🚚 En cours de livraison", callback_data=f"owner:delivering:{client_id}:{order_id}")],
                [InlineKeyboardButton("📦 Commande livrée",       callback_data=f"owner:delivered:{client_id}:{order_id}")],
                [InlineKeyboardButton("❌ Annuler la commande",    callback_data=f"owner:cancelled:{client_id}:{order_id}")],
                [InlineKeyboardButton(f"✓ {label} — envoyé {source_label}", callback_data="noop")],
            ])
        )
    except Exception as exc:
        logger.error("Erreur edit_message_reply_markup : %s", exc)


async def _noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()


# ═════════════════════════════════════════════════════════════════════════════
# /cancel
# ═════════════════════════════════════════════════════════════════════════════

async def session_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _lang(context.user_data)
    context.user_data.clear()
    target = update.effective_chat
    if target:
        try:
            await context.bot.send_message(
                chat_id=target.id,
                text=t("session_timeout", lang),
                reply_markup=_restart_keyboard(),
            )
        except Exception:
            pass
    # Répondre à l'éventuel callback query pour éviter le spinner Telegram
    if update.callback_query:
        try:
            await update.callback_query.answer()
        except Exception:
            pass
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _lang(context.user_data)
    await update.message.reply_text(
        t("order_cancelled", lang),
        reply_markup=_restart_keyboard(),
    )
    return ConversationHandler.END


# ═════════════════════════════════════════════════════════════════════════════
# /help (client)
# ═════════════════════════════════════════════════════════════════════════════

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = _lang(context.user_data) if context.user_data else "fr"
    await update.message.reply_text(t("help_text", lang), parse_mode="Markdown")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche si le service est actuellement ouvert ou fermé."""
    lang = _lang(context.user_data) if context.user_data else "fr"
    key  = "status_open" if _is_open() else "status_closed"
    await update.message.reply_text(t(key, lang), parse_mode="Markdown")


async def cmd_getid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner : affiche l'ID du chat courant (utile pour configurer un groupe)."""
    if not _is_owner(update):
        return
    chat = update.effective_chat
    user = update.effective_user
    lines = [
        "🆔 <b>Identifiants du chat</b>",
        "",
        f"💬 Chat ID  : <code>{chat.id}</code>",
        f"📝 Type     : {chat.type}",
    ]
    if chat.title:
        lines.append(f"👥 Nom      : {_html.escape(chat.title)}")
    lines += [
        "",
        f"👤 Ton ID   : <code>{user.id}</code>",
        f"📌 Username : @{user.username or '—'}",
        "",
        "👉 Pour utiliser un groupe comme destination des notifications :",
        "  1. Ajoute le bot au groupe",
        "  2. Envoie <code>/getid</code> dans le groupe",
        "  3. Copie le <b>Chat ID</b> dans <code>OWNER_CHAT_ID</code> du fichier .env",
        "  4. Redémarre le bot",
    ]
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ═════════════════════════════════════════════════════════════════════════════
# Commandes owner : /stats  /reload  /export
# ═════════════════════════════════════════════════════════════════════════════

def _is_owner(update: Update) -> bool:
    """True si l'utilisateur est l'admin autorisé (OWNER_USER_ID)."""
    return str(update.effective_user.id) == str(OWNER_USER_ID)


# Médailles pour les classements
# ═════════════════════════════════════════════════════════════════════════════
# Feature 5 — /orders (historique client)
# ═════════════════════════════════════════════════════════════════════════════

async def cmd_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche les 5 dernières commandes du client."""
    user    = update.effective_user
    lang    = _lang(context.user_data) if context.user_data else "fr"
    orders  = get_orders_by_user(user.id)[:5]

    if not orders:
        await update.message.reply_text(t("orders_empty", lang))
        return

    lines = [t("orders_title", lang, n=len(orders))]
    for o in orders:
        dt_str  = o.get("created_at", "")[:16].replace("T", " ")
        total   = float(o.get("total", 0))
        city    = o.get("city", "—")
        status  = o.get("status", "pending")
        status_icons = {
            "pending":    "⏳",
            "confirmed":  "✅",
            "delivering": "🚚",
            "delivered":  "📦",
            "cancelled":  "❌",
        }
        icon = status_icons.get(status, "•")
        lines.append(
            f"{icon} `{o['order_id']}`\n"
            f"   📅 {dt_str} · 🏙️ {city}\n"
            f"   💸 {total:,.0f} €\n"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ═════════════════════════════════════════════════════════════════════════════
# Feature 6 — /broadcast (owner)
# ═════════════════════════════════════════════════════════════════════════════

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner : diffuse un message à tous les clients ayant passé une commande.
    Usage : /broadcast <message>
    """
    if not _is_owner(update):
        return

    text = " ".join(context.args) if context.args else ""
    if not text:
        await update.message.reply_text(
            "📢 Usage : <code>/broadcast votre message ici</code>\n\n"
            "Le message sera envoyé à tous vos clients depuis votre compte @millesimecoffee.",
            parse_mode="HTML",
        )
        return

    user_ids = get_all_user_ids()
    if not user_ids:
        await update.message.reply_text("📭 Aucun client trouvé dans les commandes.")
        return

    progress = await update.message.reply_text(
        f"📤 Envoi en cours à {len(user_ids)} client(s)…"
    )
    sent = failed = 0
    import asyncio
    for uid in user_ids:
        try:
            from personal_sender import send_personal_message, is_ready
            ok = False
            if is_ready():
                ok = await send_personal_message(uid, text)
            if not ok:
                await context.bot.send_message(chat_id=uid, text=text)
            sent += 1
        except Exception as exc:
            logger.warning("Broadcast uid=%s : %s", uid, exc)
            failed += 1
        # H7: throttle ~25 msg/s (Telegram limite à 30/s, marge de sécurité)
        await asyncio.sleep(0.04)

    await progress.edit_text(
        f"✅ Broadcast terminé !\n"
        f"  • Envoyés : {sent}\n"
        f"  • Échecs  : {failed}"
    )


# ═════════════════════════════════════════════════════════════════════════════
# Feature 7 — /block /unblock /banlist (owner)
# ═════════════════════════════════════════════════════════════════════════════

async def cmd_block(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner : bloque définitivement un utilisateur. Usage : /block USER_ID"""
    if not _is_owner(update):
        return
    if not context.args:
        await update.message.reply_text("Usage : <code>/block USER_ID</code>", parse_mode="HTML")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID invalide — doit être un nombre entier.")
        return
    _blacklist.add(uid)
    save_blacklist(_blacklist)
    await update.message.reply_text(
        f"🚫 Utilisateur <code>{uid}</code> bloqué définitivement.",
        parse_mode="HTML",
    )


async def cmd_unblock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner : débloque un utilisateur. Usage : /unblock USER_ID"""
    if not _is_owner(update):
        return
    if not context.args:
        await update.message.reply_text("Usage : <code>/unblock USER_ID</code>", parse_mode="HTML")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID invalide.")
        return
    _blacklist.discard(uid)
    save_blacklist(_blacklist)
    await update.message.reply_text(
        f"✅ Utilisateur <code>{uid}</code> débloqué.",
        parse_mode="HTML",
    )


async def cmd_banlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner : affiche la liste des utilisateurs bannis."""
    if not _is_owner(update):
        return
    if not _blacklist:
        await update.message.reply_text("✅ Aucun utilisateur banni.")
        return
    ids = "\n".join(f"  • <code>{uid}</code>" for uid in sorted(_blacklist))
    await update.message.reply_text(
        f"🚫 <b>Utilisateurs bannis ({len(_blacklist)}) :</b>\n{ids}",
        parse_mode="HTML",
    )


# ═════════════════════════════════════════════════════════════════════════════
# Pause d'urgence (idée #40)
# ═════════════════════════════════════════════════════════════════════════════

async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner : pause d'urgence du bot. Usage : /pause [raison libre]
    Tant que pausé, les clients reçoivent un message d'indisponibilité.
    """
    if not _is_owner(update):
        return
    global _paused, _paused_reason
    _paused = True
    _paused_reason = " ".join(context.args).strip() if context.args else "Service temporairement indisponible"
    await update.message.reply_text(
        f"🔴 <b>Bot en pause</b>\n"
        f"Raison : <i>{_safe_html(_paused_reason)}</i>\n\n"
        f"Utilise /resume pour réactiver.",
        parse_mode="HTML",
    )


async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner : réactive le bot après /pause."""
    if not _is_owner(update):
        return
    global _paused, _paused_reason
    was_paused = _paused
    _paused = False
    _paused_reason = ""
    msg = "🟢 <b>Bot réactivé</b>" if was_paused else "🟢 Le bot n'était pas en pause."
    await update.message.reply_text(msg, parse_mode="HTML")


# ═════════════════════════════════════════════════════════════════════════════
# Version (debug owner)
# ═════════════════════════════════════════════════════════════════════════════

async def cmd_version(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner : version actuelle (commit + branche) du bot déployé."""
    if not _is_owner(update):
        return
    sha    = os.getenv("RENDER_GIT_COMMIT", "")[:7] or "local"
    branch = os.getenv("RENDER_GIT_BRANCH", "") or "?"
    service= os.getenv("RENDER_SERVICE_NAME", "local")
    is_paused = "🔴 Oui" if _paused else "🟢 Non"
    pause_info = f"\nRaison : {_paused_reason}" if _paused else ""
    await update.message.reply_text(
        f"📦 <b>Version</b>\n"
        f"Commit : <code>{sha}</code>\n"
        f"Branche : <code>{branch}</code>\n"
        f"Service : <code>{service}</code>\n"
        f"En pause : {is_paused}{pause_info}",
        parse_mode="HTML",
    )


# ═════════════════════════════════════════════════════════════════════════════
# Annulation client (fenêtre 2 min)
# ═════════════════════════════════════════════════════════════════════════════

async def _expire_cancel_button(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Edite le message d'annulation après 2 min pour retirer le bouton."""
    data = context.job.data
    try:
        await context.bot.edit_message_text(
            chat_id=data["chat_id"],
            message_id=data["message_id"],
            text=t("client_cancel_expired_msg", data.get("lang", "fr")),
            parse_mode="Markdown",
        )
    except Exception as exc:
        # Message déjà supprimé/modifié → ignore
        logger.debug("Expire cancel button : %s", exc)


async def handle_client_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère le callback client_cancel:ORDER_ID — annulation par le client."""
    query    = update.callback_query
    parts    = query.data.split(":", 1)
    order_id = parts[1] if len(parts) > 1 else ""
    user     = update.effective_user

    if not order_id:
        await query.answer("Order ID invalide", show_alert=True)
        return

    order = get_order(order_id)
    if not order:
        await query.answer("Commande introuvable.", show_alert=True)
        return

    # Langue : prendre celle stockée sur la commande (plus fiable que la session)
    lang = order.get("lang") or (_lang(context.user_data) if context.user_data else "fr")

    # Vérifier que c'est bien le bon client
    if int(order.get("user_id", 0)) != int(user.id):
        await query.answer("⛔ Cette commande ne vous appartient pas.", show_alert=True)
        return

    # Vérifier la fenêtre 2 min — robuste aux datetime timezone-aware (Supabase)
    try:
        created = datetime.fromisoformat(order.get("created_at", ""))
        # Normaliser : si aware, convertir en naïf UTC ; sinon supposer local
        if created.tzinfo is not None:
            created = created.astimezone().replace(tzinfo=None)
    except (ValueError, TypeError):
        created = datetime.now()
    age = (datetime.now() - created).total_seconds()

    if age > 120:
        await query.answer()
        await query.edit_message_text(
            t("client_cancel_too_late", lang),
            parse_mode="Markdown",
        )
        return

    # OK — annuler
    update_order(order_id, {"status": "cancelled_by_client"})

    # Annuler le job d'expiration (le bouton est consommé)
    if context.job_queue:
        for job in context.job_queue.get_jobs_by_name(f"cancel_expire_{order_id}"):
            job.schedule_removal()

    await query.answer("Annulation effectuée")
    await query.edit_message_text(
        t("client_cancel_done", lang, id=order_id),
        parse_mode="Markdown",
    )

    # Notifier le owner
    name = user.first_name or "?"
    if user.username:
        name = f"{name} (@{user.username})"
    try:
        await context.bot.send_message(
            chat_id=OWNER_CHAT_ID,
            text=t("owner_client_cancelled", "fr", name=_html.escape(name), id=_html.escape(order_id)),
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.warning("Notification annulation owner : %s", exc)


# ═════════════════════════════════════════════════════════════════════════════
# Feature 9 — Note après livraison
# ═════════════════════════════════════════════════════════════════════════════

async def handle_rating(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère les callbacks rate:SCORE:ORDER_ID envoyés par le client."""
    query    = update.callback_query
    parts    = query.data.split(":")      # rate:SCORE:ORDER_ID

    # Validation stricte des paramètres
    try:
        score    = int(parts[1])
        order_id = parts[2] if len(parts) > 2 else ""
    except (ValueError, IndexError):
        await query.answer("Callback invalide", show_alert=True)
        return

    if not (1 <= score <= 5) or not order_id:
        await query.answer("Note invalide", show_alert=True)
        return

    # Récupérer la commande et vérifier le owner
    order = get_order(order_id)
    if not order:
        await query.answer("Commande introuvable.", show_alert=True)
        return

    if int(order.get("user_id", 0)) != int(update.effective_user.id):
        await query.answer("⛔ Cette commande ne vous appartient pas.", show_alert=True)
        return

    # Pas de double-notation
    if order.get("rating"):
        await query.answer("Vous avez déjà noté cette commande.", show_alert=True)
        return

    client_lang = order.get("lang", "fr")

    # Sauvegarder la note
    try:
        update_order(order_id, {"rating": score})
    except Exception as exc:
        logger.warning("Sauvegarde note : %s", exc)

    stars = "⭐" * score
    await query.answer()
    await query.edit_message_text(
        t("rating_saved", client_lang, stars=stars, score=score),
        parse_mode="Markdown",
    )

    # Notifier l'owner
    if OWNER_CHAT_ID:
        try:
            user = update.effective_user
            full = user.first_name or "?"
            if getattr(user, "last_name", None):
                full = f"{full} {user.last_name}".strip()
            await context.bot.send_message(
                chat_id=OWNER_CHAT_ID,
                text=(
                    f"⭐ <b>Note reçue !</b>\n"
                    f"📦 Commande : <code>{_html.escape(order_id)}</code>\n"
                    f"👤 Client : {_html.escape(full)}\n"
                    f"Note : {stars} <b>({score}/5)</b>"
                ),
                parse_mode="HTML",
            )
        except Exception as exc:
            logger.warning("Notif note owner : %s", exc)

    # Idée #30 : si note ≤ 3, demander un feedback détaillé
    if score <= 3:
        try:
            fkb = InlineKeyboardMarkup([
                [InlineKeyboardButton(t("feedback_btn_slow",    client_lang), callback_data=f"fb:slow:{order_id}")],
                [InlineKeyboardButton(t("feedback_btn_wrong",   client_lang), callback_data=f"fb:wrong:{order_id}")],
                [InlineKeyboardButton(t("feedback_btn_cold",    client_lang), callback_data=f"fb:cold:{order_id}")],
                [InlineKeyboardButton(t("feedback_btn_quality", client_lang), callback_data=f"fb:quality:{order_id}")],
                [InlineKeyboardButton(t("feedback_btn_other",   client_lang), callback_data=f"fb:other:{order_id}")],
            ])
            await context.bot.send_message(
                chat_id=update.effective_user.id,
                text=t("rating_low_followup", client_lang),
                reply_markup=fkb,
                parse_mode="Markdown",
            )
        except Exception as exc:
            logger.debug("Envoi follow-up feedback : %s", exc)


async def handle_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reçoit le motif de note basse via les boutons fb:REASON:ORDER_ID."""
    query = update.callback_query
    parts = query.data.split(":", 2)
    if len(parts) < 3:
        await query.answer("Callback invalide", show_alert=True)
        return
    reason   = parts[1]
    order_id = parts[2]

    order = get_order(order_id)
    if not order:
        await query.answer("Commande introuvable.", show_alert=True)
        return

    if int(order.get("user_id", 0)) != int(update.effective_user.id):
        await query.answer("⛔ Cette commande ne vous appartient pas.", show_alert=True)
        return

    client_lang = order.get("lang", "fr")

    # Sauvegarder le motif dans la commande
    try:
        update_order(order_id, {"feedback_reason": reason})
    except Exception as exc:
        logger.warning("Sauvegarde feedback : %s", exc)

    await query.answer()
    await query.edit_message_text(t("feedback_thanks", client_lang), parse_mode="Markdown")

    # Alerter l'owner immédiatement — note basse + motif
    if OWNER_CHAT_ID:
        reason_labels = {
            "slow":    "⏰ Livraison trop longue",
            "wrong":   "❌ Erreur dans la commande",
            "cold":    "🥶 Produit pas à bonne température",
            "quality": "⚠️ Qualité décevante",
            "other":   "📝 Autre",
        }
        rating = order.get("rating", "?")
        try:
            user = update.effective_user
            full = (user.first_name or "?") + (f" (@{user.username})" if user.username else "")
            await context.bot.send_message(
                chat_id=OWNER_CHAT_ID,
                text=(
                    f"⚠️ <b>RETOUR CLIENT NÉGATIF</b>\n\n"
                    f"📦 Commande : <code>{_safe_html(order_id)}</code>\n"
                    f"👤 Client : {_safe_html(full)}\n"
                    f"⭐ Note : <b>{rating}/5</b>\n"
                    f"💬 Motif : {reason_labels.get(reason, reason)}\n\n"
                    f"<i>Contacte ce client rapidement.</i>"
                ),
                parse_mode="HTML",
            )
        except Exception as exc:
            logger.warning("Notif feedback owner : %s", exc)


# ═════════════════════════════════════════════════════════════════════════════
# Feature 8 — Rapport hebdomadaire (lundi 08h00)
# ═════════════════════════════════════════════════════════════════════════════

def _build_weekly_report(s: dict) -> str:
    """Formate le rapport de la semaine écoulée."""
    try:
        d0 = datetime.strptime(s["start_date"], "%Y-%m-%d")
        d1 = datetime.strptime(s["end_date"],   "%Y-%m-%d")
        start_lbl = f"{d0.day} {_FR_MONTHS[d0.month - 1]}"
        end_lbl   = f"{d1.day} {_FR_MONTHS[d1.month - 1]} {d1.year}"
    except Exception:
        start_lbl = s.get("start_date", "")
        end_lbl   = s.get("end_date", "")

    SEP = "━━━━━━━━━━━━━━━━━"
    lines = [
        "📊 *RAPPORT HEBDOMADAIRE*",
        f"📅 _{start_lbl} → {end_lbl}_",
        "",
        SEP, "💰 *CHIFFRE D'AFFAIRES DE LA SEMAINE*", SEP,
        f"  • Commandes   : *{s['orders_period']}*",
        f"  • CA semaine  : *{s['ca_period']:,.0f} €*",
        f"  • Panier moyen : *{s['avg_basket_period']:,.0f} €*",
    ]

    lines += ["", SEP, "🏙️ *TOP VILLES — SEMAINE*", SEP]
    cities = s.get("top_cities", [])
    if cities:
        for i, (city, info) in enumerate(cities[:5]):
            medal = _MEDALS[i] if i < len(_MEDALS) else f"{i+1}."
            lines.append(f"  {medal} {city} — {info['orders']} cmd · {info['ca']:,.0f} €")
    else:
        lines.append("  _(aucune commande cette semaine)_")

    lines += ["", SEP, "📦 *TOP PRODUITS — SEMAINE*", SEP]
    for i, (item, qty) in enumerate(s.get("top_items_period", [])):
        medal  = _MEDALS[i] if i < len(_MEDALS) else f"{i+1}."
        s_mark = "s" if qty > 1 else ""
        lines.append(f"  {medal} {item} — {qty} vendu{s_mark}")
    if not s.get("top_items_period"):
        lines.append("  _(aucune vente cette semaine)_")

    lines += [
        "", SEP, "📈 *CUMUL TOTAL*", SEP,
        f"  • Commandes totales : *{s['orders_total']}*",
        f"  • CA total          : *{s['ca_total']:,.0f} €*",
        f"  • Panier moyen global : *{s['avg_basket_all']:,.0f} €*",
    ]
    return "\n".join(lines)


async def _send_weekly_report(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job lundi 08h00 : envoie le bilan de la semaine écoulée (lun→dim)."""
    if not OWNER_CHAT_ID:
        return
    today      = datetime.now(ZoneInfo("Europe/Paris"))
    end_date   = (today - timedelta(days=1)).strftime("%Y-%m-%d")   # dimanche
    start_date = (today - timedelta(days=7)).strftime("%Y-%m-%d")   # lundi précédent
    s   = get_stats_period(start_date, end_date)
    txt = _build_weekly_report(s)
    try:
        await context.bot.send_message(
            chat_id=int(OWNER_CHAT_ID), text=txt, parse_mode="Markdown"
        )
        logger.info("Rapport hebdomadaire envoyé (%s → %s)", start_date, end_date)
    except Exception as exc:
        logger.error("Erreur rapport hebdomadaire : %s", exc)


# ═════════════════════════════════════════════════════════════════════════════
# Feature 12 — Backup automatique quotidien
# ═════════════════════════════════════════════════════════════════════════════

async def _backup_orders_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job minuit : sauvegarde orders.json dans backups/."""
    path = backup_orders()
    if path:
        logger.info("Backup orders.json → %s", path)
    else:
        logger.info("Backup : rien à sauvegarder.")


_MEDALS = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]

_FR_DAYS   = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
_FR_MONTHS = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def _build_daily_report(s: dict, title: str = "📊 *RAPPORT JOURNALIER*") -> str:
    """Formate un rapport Markdown complet à partir du dict retourné par get_stats()."""
    # ── Date lisible en français ──────────────────────────────────────────────
    try:
        d = datetime.strptime(s["date_str"], "%Y-%m-%d")
        date_label = f"{_FR_DAYS[d.weekday()]} {d.day} {_FR_MONTHS[d.month - 1]} {d.year}"
    except Exception:
        date_label = s.get("date_str", "")

    SEP = "━━━━━━━━━━━━━━━━━"

    lines: list[str] = [
        title,
        f"📅 _{date_label}_",
        "",
        SEP,
        "💰 *CHIFFRE D'AFFAIRES DU JOUR*",
        SEP,
        f"  • Commandes   : *{s['orders_today']}*",
        f"  • CA du jour  : *{s['ca_today']:,.0f} €*",
        f"  • Panier moyen : *{s['avg_basket_day']:,.0f} €*",
    ]

    # ── Top villes du jour ────────────────────────────────────────────────────
    lines += ["", SEP, "🏙️ *TOP VILLES — AUJOURD'HUI*", SEP]
    cities = s.get("top_cities_day", [])
    if cities:
        for i, (city, info) in enumerate(cities[:5]):
            medal = _MEDALS[i] if i < len(_MEDALS) else f"{i + 1}."
            lines.append(
                f"  {medal} {city} — "
                f"{info['orders']} cmd · {info['ca']:,.0f} €"
            )
    else:
        lines.append("  _(aucune commande aujourd'hui)_")

    # ── Top produits du jour ──────────────────────────────────────────────────
    lines += ["", SEP, "📦 *TOP PRODUITS — AUJOURD'HUI*", SEP]
    items_day = s.get("top_items_day", [])
    if items_day:
        for i, (item, qty) in enumerate(items_day):
            medal = _MEDALS[i] if i < len(_MEDALS) else f"{i + 1}."
            s_mark = "s" if qty > 1 else ""
            lines.append(f"  {medal} {item} — {qty} vendu{s_mark}")
    else:
        lines.append("  _(aucune vente aujourd'hui)_")

    # ── Cumul global ──────────────────────────────────────────────────────────
    lines += [
        "", SEP, "📈 *CUMUL TOTAL*", SEP,
        f"  • Commandes totales : *{s['orders_total']}*",
        f"  • CA total          : *{s['ca_total']:,.0f} €*",
        f"  • Panier moyen global : *{s['avg_basket_all']:,.0f} €*",
    ]

    # ── Top produits tous les temps ───────────────────────────────────────────
    lines += ["", SEP, "🏆 *TOP PRODUITS — TOUS LES TEMPS*", SEP]
    items_all = s.get("top_items_all", [])
    if items_all:
        for i, (item, qty) in enumerate(items_all):
            medal = _MEDALS[i] if i < len(_MEDALS) else f"{i + 1}."
            s_mark = "s" if qty > 1 else ""
            lines.append(f"  {medal} {item} — {qty} vendu{s_mark}")
    else:
        lines.append("  _(aucune commande enregistrée)_")

    return "\n".join(lines)


async def _send_daily_report(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job automatique : envoie le rapport de la journée écoulée à l'owner à minuit."""
    if not OWNER_CHAT_ID:
        logger.warning("OWNER_CHAT_ID non défini — rapport minuit ignoré.")
        return
    # On récupère la date d'hier (le job tourne à 00:00:05, on veut J-1)
    yesterday = (
        datetime.now(ZoneInfo("Europe/Paris")) - timedelta(days=1)
    ).strftime("%Y-%m-%d")
    s   = get_stats(date_str=yesterday)
    txt = _build_daily_report(s, title="📊 *RAPPORT AUTOMATIQUE — MINUIT*")
    try:
        await context.bot.send_message(
            chat_id=int(OWNER_CHAT_ID),
            text=txt,
            parse_mode="Markdown",
        )
        logger.info("Rapport minuit envoyé pour le %s", yesterday)
    except Exception as exc:
        logger.error("Erreur envoi rapport minuit : %s", exc)


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner : affiche le rapport complet du jour en cours."""
    if not _is_owner(update):
        return
    s   = get_stats()   # date du jour par défaut
    txt = _build_daily_report(s)
    await update.message.reply_text(txt, parse_mode="Markdown")


async def cmd_reload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        return
    try:
        importlib.reload(catalog_mod)
        await update.message.reply_text(
            f"✅ Catalogue rechargé !\n{len(catalog_mod.CATALOG)} pays.",
        )
    except Exception as exc:
        await update.message.reply_text(f"❌ Erreur reload : `{exc}`", parse_mode="Markdown")


def _csv_safe(value) -> str:
    """Préfixe ' devant les caractères dangereux pour Excel (=, +, -, @)."""
    if value is None:
        return ""
    s = str(value)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        s = "'" + s
    return s


async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """B5: Exporte toutes les commandes en CSV (Excel-compatible UTF-8 BOM)."""
    if not _is_owner(update):
        return
    orders = _load_orders()
    if not orders:
        await update.message.reply_text("Aucune commande à exporter.")
        return
    fields = ["order_id", "created_at", "user_name", "user_id", "country", "city",
              "total", "payment", "address", "phone", "status", "lang"]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for o in orders:
        # Échapper CSV injection (formules Excel)
        writer.writerow({k: _csv_safe(o.get(k, "")) for k in fields})
    csv_bytes = output.getvalue().encode("utf-8-sig")
    await update.message.reply_document(
        document=BytesIO(csv_bytes),
        filename=f"orders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        caption=f"📊 Export — {len(orders)} commandes",
    )


# ═════════════════════════════════════════════════════════════════════════════
# Lancement
# ═════════════════════════════════════════════════════════════════════════════

async def _stale_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Répond aux boutons inline obsolètes (session expirée).

    Exception : les boutons owner (owner:*) et noop sont redirigés vers
    leur handler dédié pour ne PAS afficher le popup timeout à l'owner.
    """
    data = (update.callback_query.data or "")

    # Boutons de gestion de commande owner → déléguer au bon handler
    if data.startswith("owner:"):
        await owner_status_update(update, context)
        return

    # Bouton noop (indicateur de statut) → répondre silencieusement
    if data == "noop":
        await _noop_callback(update, context)
        return

    # Tous les autres boutons obsolètes → popup session expirée
    try:
        lang = _lang(context.user_data) if context.user_data else "fr"
        await update.callback_query.answer(
            t("session_timeout", lang)[:200],  # Telegram limite à 200 chars
            show_alert=True,
        )
    except Exception:
        pass


def build_conv_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        per_message=False,
        conversation_timeout=1800,   # 30 min d'inactivité → session_timeout
        states={
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, session_timeout),
                CallbackQueryHandler(session_timeout),
            ],
            SELECTING_LANGUAGE: [
                CallbackQueryHandler(select_language, pattern="^lang:"),
            ],
            WAITING_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, check_password),
            ],
            REQUESTING_PHONE: [
                MessageHandler(filters.CONTACT, receive_phone),
                MessageHandler(filters.TEXT & ~filters.COMMAND, skip_phone),
                CommandHandler("skip", skip_phone),
            ],
            SELECTING_COUNTRY: [
                CallbackQueryHandler(select_country, pattern="^country:"),
            ],
            SELECTING_CITY: [
                CallbackQueryHandler(select_city, pattern="^(city:|back:)"),
            ],
            BROWSING_MENU: [
                CallbackQueryHandler(browse_menu),
            ],
            VIEWING_CART: [
                CallbackQueryHandler(manage_cart),
            ],
            SELECTING_PAYMENT: [
                CallbackQueryHandler(select_payment),
            ],
            AWAITING_TRANSFER_PROOF: [
                # Bouton « Retour » sur l'écran virement
                CallbackQueryHandler(select_payment, pattern="^pay:back$"),
                MessageHandler(filters.PHOTO, handle_transfer_proof),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_transfer_proof),
            ],
            ENTERING_ADDRESS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_address),
            ],
            CONFIRMING_ADDRESS: [
                CallbackQueryHandler(confirm_address, pattern="^addr:"),
            ],
            SENDING_SELFIE: [
                MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_selfie),
                MessageHandler(filters.PHOTO, handle_selfie),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_selfie),
            ],
            CONFIRMING_ORDER: [
                CallbackQueryHandler(confirm_order, pattern="^order:"),
            ],
            ORDER_MANAGEMENT: [
                CallbackQueryHandler(order_management, pattern="^manage:"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start",  start),
            # Boutons inline obsolètes (session expirée) → répondre proprement
            CallbackQueryHandler(_stale_callback),
        ],
        allow_reentry=True,
    )


async def _post_init(app: Application) -> None:
    # Menu client : uniquement /start
    _client_cmds = [
        BotCommand("start", "🛍️ Démarrer / accéder au catalogue"),
    ]
    # Menu owner : toutes les commandes
    _owner_cmds = [
        BotCommand("start",      "🛍️ Démarrer / accéder au catalogue"),
        BotCommand("stats",      "📊 Statistiques"),
        BotCommand("orders",     "📋 Mes commandes"),
        BotCommand("broadcast",  "📣 Diffuser un message"),
        BotCommand("pause",      "⏸️ Mettre le bot en pause"),
        BotCommand("resume",     "▶️ Réactiver le bot"),
        BotCommand("block",      "🚫 Bannir un utilisateur"),
        BotCommand("unblock",    "✅ Débannir un utilisateur"),
        BotCommand("banlist",    "📋 Liste des bannis"),
        BotCommand("reload",     "🔄 Recharger le catalogue"),
        BotCommand("export",     "📁 Exporter commandes CSV"),
        BotCommand("version",    "📦 Version du bot"),
        BotCommand("getid",      "🆔 Obtenir l'ID du chat"),
    ]
    try:
        from telegram import BotCommandScopeDefault, BotCommandScopeChat
        # Menu global (clients)
        await app.bot.set_my_commands(_client_cmds, scope=BotCommandScopeDefault())
        # Menu owner — uniquement pour @millesimecoffee
        if OWNER_USER_ID:
            await app.bot.set_my_commands(
                _owner_cmds,
                scope=BotCommandScopeChat(chat_id=int(OWNER_USER_ID)),
            )
    except Exception as exc:
        logger.warning("set_my_commands: %s", exc)

    # Initialiser le client Telethon (envoi depuis compte personnel admin)
    try:
        from personal_sender import init_personal_client
        await init_personal_client()
    except Exception as exc:
        logger.warning("Telethon init ignoré : %s", exc)


def main():
    global WEBAPP_URL, _blocked, _blacklist

    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN manquant dans le fichier .env !")

    # M4: Logging fichier rotatif (désactivé sur serveur si DATA_DIR=/data)
    _log_file = _DATA_DIR / "bot.log"
    try:
        fh = RotatingFileHandler(str(_log_file), maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
        fh.setFormatter(logging.Formatter(_LOG_FORMAT))
        logging.getLogger().addHandler(fh)
        logger.info("Logging fichier actif : %s", _log_file)
    except OSError:
        logger.info("Logging fichier désactivé (répertoire non accessible)")

    # Restauration des fichiers depuis le repo GitHub (free-tier persistence)
    try:
        import github_backup
        github_backup.restore_all()
    except Exception as exc:
        logger.warning("Restauration GitHub : %s", exc)

    # C3: Charger les blocages persistés
    _blocked = _load_blocked()
    if _blocked:
        logger.info("%d utilisateur(s) bloqué(s) chargés depuis blocked.json", len(_blocked))

    # Charger la blacklist permanente
    _blacklist = load_blacklist()
    if _blacklist:
        logger.info("%d utilisateur(s) bannis chargés depuis blacklist.json", len(_blacklist))

    # Démarrage du serveur Flask (Mini App)
    _flask_port = int(os.getenv("PORT", 5000))
    from webapp import run_server
    flask_thread = threading.Thread(target=run_server, kwargs={"port": _flask_port}, daemon=True)
    flask_thread.start()
    logger.info("Serveur Mini App démarré (port %d)", _flask_port)

    # Tunnel ngrok — uniquement en local si WEBAPP_URL n'est pas déjà défini
    if NGROK_TOKEN and not WEBAPP_URL:
        try:
            from pyngrok import ngrok as _ngrok
            _ngrok.set_auth_token(NGROK_TOKEN)
            tunnel     = _ngrok.connect(_flask_port, bind_tls=True)
            WEBAPP_URL = tunnel.public_url
            logger.info("Tunnel ngrok : %s", WEBAPP_URL)
        except Exception as exc:
            logger.error("Échec ngrok : %s", exc)
    elif WEBAPP_URL:
        # M7: URL fixe depuis .env (Railway, Render, ngrok fixe…)
        logger.info("WebApp URL fixe : %s", WEBAPP_URL)
    else:
        logger.warning("NGROK_AUTH_TOKEN absent — selfie WebApp désactivé")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(_post_init)
        .build()
    )
    app.add_handler(build_conv_handler())
    app.add_handler(CallbackQueryHandler(owner_status_update, pattern="^owner:"))
    app.add_handler(CallbackQueryHandler(_noop_callback,       pattern="^noop$"))
    app.add_handler(CommandHandler("help",   cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("getid",  cmd_getid))
    app.add_handler(CommandHandler("stats",     cmd_stats))
    app.add_handler(CommandHandler("reload",    cmd_reload))
    app.add_handler(CommandHandler("export",    cmd_export))
    app.add_handler(CommandHandler("orders",    cmd_orders))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(CommandHandler("block",     cmd_block))
    app.add_handler(CommandHandler("unblock",   cmd_unblock))
    app.add_handler(CommandHandler("banlist",   cmd_banlist))
    app.add_handler(CommandHandler("pause",     cmd_pause))
    app.add_handler(CommandHandler("resume",    cmd_resume))
    app.add_handler(CommandHandler("version",   cmd_version))
    app.add_handler(CallbackQueryHandler(handle_rating,        pattern="^rate:"))
    app.add_handler(CallbackQueryHandler(handle_feedback,      pattern="^fb:"))
    app.add_handler(CallbackQueryHandler(handle_client_cancel, pattern="^client_cancel:"))

    # ── Job minuit : rapport automatique à 00h00:05 heure de Paris ───────────
    app.job_queue.run_daily(
        _send_daily_report,
        time=dt_time(0, 0, 5, tzinfo=ZoneInfo("Europe/Paris")),
        name="daily_stats_report",
    )
    logger.info("Job rapport minuit enregistré (00:00:05 Europe/Paris)")

    # ── Job lundi 08h00 : rapport hebdomadaire ───────────────────────────────
    app.job_queue.run_daily(
        _send_weekly_report,
        time=dt_time(8, 0, 5, tzinfo=ZoneInfo("Europe/Paris")),
        days=(0,),
        name="weekly_stats_report",
    )
    logger.info("Job rapport hebdomadaire enregistré (lundi 08:00:05 Europe/Paris)")

    # ── Job minuit : backup automatique orders.json ──────────────────────────
    app.job_queue.run_daily(
        _backup_orders_job,
        time=dt_time(0, 0, 10, tzinfo=ZoneInfo("Europe/Paris")),
        name="daily_backup",
    )
    logger.info("Job backup enregistré (00:00:10 Europe/Paris)")

    # ── Job toutes les 10 min : sync vers le repo GitHub de données ──────────
    async def _github_backup_job(ctx):
        try:
            import github_backup
            github_backup.backup_all()
            logger.info("Backup GitHub effectué (orders/blacklist/blocked)")
        except Exception as exc:
            logger.warning("Backup GitHub : %s", exc)

    app.job_queue.run_repeating(_github_backup_job, interval=600, first=300, name="github_backup_sync")
    logger.info("Job sync GitHub enregistré (toutes les 10 min)")

    # ── Job toutes les 15 min : purge des entrées _blocked expirées ──────────
    async def _purge_blocked_job(ctx):
        now = datetime.now()
        before = len(_blocked)
        expired = [uid for uid, exp in _blocked.items() if exp <= now]
        for uid in expired:
            del _blocked[uid]
        if expired:
            try:
                _save_blocked()
            except Exception:
                pass
            logger.info("Purge anti-spam : %d entrées expirées supprimées (avant=%d après=%d)",
                        len(expired), before, len(_blocked))

    app.job_queue.run_repeating(_purge_blocked_job, interval=900, first=120, name="purge_blocked")

    # ── Self keep-alive : ping HTTP propre URL toutes les 4 min ─────────────
    # Render free tier dort après 15 min sans HTTP entrant. Le GitHub Actions
    # peut avoir des délais. Le self-ping en COMPLÉMENT garantit qu'on reste
    # éveillé tant que le process tourne (pendant qu'il tourne, il hit son URL).
    async def _self_keepalive(ctx):
        url = os.getenv("WEBAPP_URL", "").rstrip("/")
        if not url:
            return
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.get(f"{url}/health")
                logger.debug("Self keep-alive: %s -> HTTP %s", url, r.status_code)
        except Exception as exc:
            logger.debug("Self keep-alive failed (normal si premier ping): %s", exc)

    app.job_queue.run_repeating(_self_keepalive, interval=240, first=240, name="self_keepalive")
    logger.info("Self keep-alive enregistré (toutes les 4 min)")

    # ── Error handler global — évite que les conflits 409 ou autres erreurs crashent l'app ──
    async def _error_handler(update, context):
        err = context.error
        # Conflict polling = ancien instance pas encore tué pendant un redeploy
        from telegram.error import Conflict
        if isinstance(err, Conflict):
            logger.warning("Conflict polling (redeploy overlap) — ignoré")
            return
        logger.error("Erreur non gérée: %s", err, exc_info=err)
    app.add_error_handler(_error_handler)

    logger.info("Bot démarré. Ctrl+C pour arrêter.")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,    # évite Conflict 409 sur redeploy
    )


if __name__ == "__main__":
    main()

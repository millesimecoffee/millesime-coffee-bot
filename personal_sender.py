"""
Envoi de messages depuis le compte Telegram PERSONNEL de l'admin (via Telethon).
Activé uniquement si TELEGRAM_API_ID / TELEGRAM_API_HASH / TELEGRAM_SESSION
sont définis dans le fichier .env.

Si non configuré, owner_status_update retombe en mode bot normal.
"""
import logging
import os

logger = logging.getLogger(__name__)

_API_ID   = int(os.getenv("TELEGRAM_API_ID",  "0") or "0")
_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
_SESSION  = os.getenv("TELEGRAM_SESSION",  "")

_client = None
_ready  = False


async def init_personal_client() -> bool:
    """Initialise le client Telethon.  Appeler une fois au démarrage du bot."""
    global _client, _ready

    if not _API_ID or not _API_HASH or not _SESSION:
        logger.info(
            "Envoi personnel désactivé "
            "(TELEGRAM_API_ID / TELEGRAM_API_HASH / TELEGRAM_SESSION non définis)"
        )
        return False

    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        _client = TelegramClient(StringSession(_SESSION), _API_ID, _API_HASH)
        await _client.connect()

        if not await _client.is_user_authorized():
            logger.warning(
                "Session Telethon expirée ou invalide — "
                "relancez setup_session.py pour en générer une nouvelle."
            )
            return False

        me = await _client.get_me()
        _ready = True
        logger.info("✅ Telethon connecté en tant que : %s (id=%s)", me.first_name, me.id)
        return True

    except ImportError:
        logger.error("Telethon non installé — pip install telethon")
        return False
    except Exception as exc:
        logger.error("Telethon init : %s", exc)
        return False


async def send_personal_message(user_id: int, text: str) -> bool:
    """Envoie *text* depuis le compte PERSONNEL de l'admin vers *user_id*.

    Retourne True en cas de succès, False sinon.
    Si le client n'est pas prêt, retourne False silencieusement.
    """
    if not _ready or _client is None:
        return False
    try:
        await _client.send_message(int(user_id), text, parse_mode="markdown")
        logger.info("Message personnel envoyé à user_id=%s", user_id)
        return True
    except Exception as exc:
        logger.error("Telethon send_message(user_id=%s) : %s", user_id, exc)
        return False


def is_ready() -> bool:
    """True si l'envoi personnel est opérationnel."""
    return _ready

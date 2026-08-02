"""
Watchdog — relance automatique du bot Telegram s'il crash.
Notifie le owner sur Telegram si crash inattendu.
"""
import os
import sys
import time
import logging
import subprocess
from pathlib import Path

import requests
from dotenv import load_dotenv

HERE = Path(__file__).parent
load_dotenv(HERE / ".env")

BOT_TOKEN     = os.getenv("BOT_TOKEN", "")
OWNER_CHAT_ID = os.getenv("OWNER_CHAT_ID", "")
PYTHON_EXE    = sys.executable  # le même python que celui qui lance le watchdog

# Délais
RESTART_DELAY_SEC   = 10   # pause entre 2 démarrages
INSTANT_CRASH_SEC   = 30   # si le bot vit moins, c'est un crash immédiat
MAX_INSTANT_CRASHES = 3    # arrêter le watchdog après N crashs immédiats consécutifs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(HERE / "watchdog.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("watchdog")


def notify_owner(text: str) -> None:
    """Envoie un message à l'owner via l'API Telegram (sans dépendre du bot)."""
    if not BOT_TOKEN or not OWNER_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": OWNER_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=5,
        )
    except Exception as exc:
        logger.warning("Notif owner échouée: %s", exc)


def kill_leftover_ngrok() -> None:
    """Tue les processus ngrok orphelins (évite ERR_NGROK_334 au redémarrage)."""
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", "ngrok.exe"],
            capture_output=True, text=True,
        )
    except Exception:
        pass


def main():
    logger.info("=" * 60)
    logger.info("🐶 Watchdog démarré. Python : %s", PYTHON_EXE)
    logger.info("=" * 60)

    restart_count   = 0
    instant_crashes = 0

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    while True:
        restart_count += 1
        logger.info("▶️  Démarrage du bot (tentative #%d)…", restart_count)
        start_time = time.time()

        try:
            proc = subprocess.Popen(
                [PYTHON_EXE, "bot.py"],
                cwd=str(HERE),
                env=env,
            )
            exit_code = proc.wait()
        except KeyboardInterrupt:
            logger.info("🛑 Ctrl+C reçu — arrêt du watchdog.")
            try:
                proc.terminate()
            except Exception:
                pass
            break
        except Exception as exc:
            logger.error("❌ Erreur watchdog : %s", exc)
            exit_code = -1

        elapsed = time.time() - start_time

        if elapsed < INSTANT_CRASH_SEC:
            instant_crashes += 1
            logger.error(
                "💥 Crash immédiat (vécu %.1fs, code %s). %d/%d.",
                elapsed, exit_code, instant_crashes, MAX_INSTANT_CRASHES,
            )
            if instant_crashes == 1:
                notify_owner(
                    f"🚨 <b>Le bot a planté !</b>\n"
                    f"Crash immédiat ({elapsed:.0f}s, code {exit_code}).\n"
                    f"Redémarrage automatique en cours…"
                )
            if instant_crashes >= MAX_INSTANT_CRASHES:
                notify_owner(
                    f"❌ <b>Le bot crash en boucle !</b>\n"
                    f"{MAX_INSTANT_CRASHES} crashs immédiats consécutifs. "
                    f"Vérifie le code et relance manuellement."
                )
                logger.critical("Trop de crashs immédiats — arrêt du watchdog.")
                break
        else:
            instant_crashes = 0
            logger.warning(
                "⚠️  Bot arrêté après %.1fmin (code %s). Redémarrage dans %ds…",
                elapsed / 60, exit_code, RESTART_DELAY_SEC,
            )

        kill_leftover_ngrok()
        time.sleep(RESTART_DELAY_SEC)


if __name__ == "__main__":
    main()

"""Socle partagé par les tests : environnement isolé et faux Telegram.

Les tests tournent sans réseau et sans toucher aux vraies données : la
signature Telegram est simulée, le stockage est remplacé en mémoire, et
Pushover comme Telegram sont laissés hors configuration donc inertes.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

OWNER = 8674345458
AUTRE = 100000042


def preparer(**extra):
    """Prépare l'environnement puis importe webapp. À appeler AVANT l'import."""
    os.environ.update({
        "BOT_TOKEN": "jeton-de-test",
        "OWNER_USER_ID": str(OWNER),
        "OWNER_CHAT_ID": "",
        "BOT_PASSWORD": "PLATA O PLOMO",
        "ADMIN_PANEL_PASSWORD": "RICH PORTER",
        "PUSHOVER_USER_KEY": "",
        "PUSHOVER_APP_TOKEN": "",
        "NOTIF_IGNORER_OWNER": "",
    })
    os.environ.update(extra)
    import webapp
    return webapp


def simuler_telegram(webapp, uid_courant):
    """Remplace la vérification de signature. `uid_courant` est un dict mutable
    {"v": id} pour pouvoir changer d'utilisateur en cours de test."""
    webapp._verify_init_data = lambda init, token: (
        {"user": json.dumps({"id": uid_courant["v"], "username": "compte_test",
                             "first_name": "Test"})} if init else None
    )


def titre(n, texte):
    print(f"\n{n}) {texte}")


def fin():
    print("\n" + "=" * 62)
    print("TOUS LES CONTROLES SONT PASSES")

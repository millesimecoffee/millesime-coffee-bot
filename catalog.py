# catalog.py — Modifiez ce fichier pour personnaliser vos produits, villes et pays
# Format : CATALOG[pays][ville][produit] = prix
#
# Ce fichier définit le catalogue PAR DÉFAUT. Dès que l'owner édite quelque chose
# depuis l'espace admin de la Mini App, l'état complet est enregistré dans
# `catalogue.json` (voir plus bas) et ré-appliqué par-dessus au chargement.

import json
import logging
import os
import threading
from pathlib import Path

CATALOG = {
    "🇫🇷 France": {
        "Paris": {
            "❄️ COCA 1G":   100.00,
            "🍾 MDMA 1G":    70.00,
            "🍬 EXTA 6PCS":  70.00,
            "🐘 KETA 1G":    70.00,
            "🥦 WEED 5G":    70.00,
            "🍫 HASH 10G":   70.00,
        },
    },
    "🇧🇪 Belgique": {
        "Bruxelles": {
            "❄️ COCA 1G": 100.00,
        },
    },
    "🇬🇧 Angleterre": {
        "Londres": {
            "❄️ COCA 1G":   100.00,
            "🍾 MDMA 1G":    40.00,
            "🍬 EXTA 5PCS":  60.00,
            "🐘 KETA 1G":    40.00,
            "🌸 TUCI 1G":    50.00,
        },
        "Manchester": {
            "❄️ COCA 1G":   100.00,
            "🍾 MDMA 1G":    40.00,
            "🍬 EXTA 5PCS":  60.00,
            "🐘 KETA 1G":    40.00,
            "🌸 TUCI 1G":    50.00,
        },
    },
    "🇪🇸 Espagne": {
        # Barcelone — MDMA et KETA descendus à 60 €
        "Barcelone": {
            "❄️ COCA 1G":    100.00,
            "🍬 EXTA 10PCS":  70.00,
            "🍾 MDMA 1G":     60.00,
            "🐘 KETA 1G":     60.00,
            "🌸 TUCI 1G":    120.00,
        },
        # Marbella — même menu que Barcelone, min 200 €
        "Marbella": {
            "❄️ COCA 1G":    100.00,
            "🍬 EXTA 10PCS":  70.00,
            "🍾 MDMA 1G":     60.00,
            "🐘 KETA 1G":     60.00,
            "🌸 TUCI 1G":    120.00,
        },
        # Malaga — même menu que Barcelone, min 200 €
        "Malaga": {
            "❄️ COCA 1G":    100.00,
            "🍬 EXTA 10PCS":  70.00,
            "🍾 MDMA 1G":     60.00,
            "🐘 KETA 1G":     60.00,
            "🌸 TUCI 1G":    120.00,
        },
        # Palma De Majorque (renommée depuis "Majorque") — menu réduit
        "Palma De Majorque": {
            "❄️ COCA 1G":    130.00,
            "🍾 MDMA 1G":     80.00,
        },
        # Tenerife — INCHANGÉ (pas listé dans le nouveau menu)
        "Tenerife": {
            "❄️ COCA 1G":    120.00,
            "🍬 EXTA 10PCS":  70.00,
            "🍾 MDMA 1G":     70.00,
            "🐘 KETA 1G":     70.00,
            "🥦 WEED 1.2G":   30.00,
        },
        # Lanzarote — NOUVELLE ville
        "Lanzarote": {
            "❄️ COCA 2G":    240.00,
            "🥦 WEED 1G":     40.00,
            "🌸 TUCI 1G":    130.00,
        },
    },
    "🇬🇷 Grèce": {
        # Groupe A (Mykonos, Santorini, Athènes) — COCA 130, TUCI 150, MDMA 100, EXTA 40
        "Mykonos": {
            "❄️ COCA 1G":  130.00,
            "🌸 TUCI 1G":  150.00,
            "🍾 MDMA 1G":  100.00,
            "🍬 EXTA 1X":   40.00,
        },
        "Santorini": {
            "❄️ COCA 1G":  130.00,
            "🌸 TUCI 1G":  150.00,
            "🍾 MDMA 1G":  100.00,
            "🍬 EXTA 1X":   40.00,
        },
        "Athènes": {
            "❄️ COCA 1G":  130.00,
            "🌸 TUCI 1G":  150.00,
            "🍾 MDMA 1G":  100.00,
            "🍬 EXTA 1X":   40.00,
        },
        # Groupe B (Corfu, Rhodes, Crète, Zakynthos) — COCA 150, TUCI 160, MDMA 120, EXTA 60
        "Corfu": {
            "❄️ COCA 1G":  150.00,
            "🌸 TUCI 1G":  160.00,
            "🍾 MDMA 1G":  120.00,
            "🍬 EXTA 1X":   60.00,
        },
        "Rhodes": {
            "❄️ COCA 1G":  150.00,
            "🌸 TUCI 1G":  160.00,
            "🍾 MDMA 1G":  120.00,
            "🍬 EXTA 1X":   60.00,
        },
        "Crète": {
            "❄️ COCA 1G":  150.00,
            "🌸 TUCI 1G":  160.00,
            "🍾 MDMA 1G":  120.00,
            "🍬 EXTA 1X":   60.00,
        },
        "Zakynthos": {
            "❄️ COCA 1G":  150.00,
            "🌸 TUCI 1G":  160.00,
            "🍾 MDMA 1G":  120.00,
            "🍬 EXTA 1X":   60.00,
        },
    },
    "🇵🇹 Portugal": {
        # Groupe 1 (Albufeira, Vilamoura, Lisbonne) — pas de min
        "Albufeira": {
            "❄️ COCA 1G":  130.00,
            "🍾 MDMA 1G":   80.00,
            "🐘 KETA 1G":   80.00,
            "🌸 TUCI 1G":  120.00,
            "🍬 EXTA 1X":   30.00,
        },
        "Vilamoura": {
            "❄️ COCA 1G":  130.00,
            "🍾 MDMA 1G":   80.00,
            "🐘 KETA 1G":   80.00,
            "🌸 TUCI 1G":  120.00,
            "🍬 EXTA 1X":   30.00,
        },
        "Lisbonne": {
            "❄️ COCA 1G":  130.00,
            "🍾 MDMA 1G":   80.00,
            "🐘 KETA 1G":   80.00,
            "🌸 TUCI 1G":  120.00,
            "🍬 EXTA 1X":   30.00,
        },
        # Porto — INCHANGÉ (pas listé dans le nouveau menu)
        "Porto": {
            "❄️ COCA 1G":    130.00,
            "🌸 TUCI 1G":    130.00,
            "🍬 EXTA 10PCS": 120.00,
            "🐘 KETA 3G":    120.00,
        },
        # Groupe 2 (min 250 €) — même menu que le Groupe 1
        "Portimao": {
            "❄️ COCA 1G":  130.00,
            "🍾 MDMA 1G":   80.00,
            "🐘 KETA 1G":   80.00,
            "🌸 TUCI 1G":  120.00,
            "🍬 EXTA 1X":   30.00,
        },
        "Carvoeiro": {
            "❄️ COCA 1G":  130.00,
            "🍾 MDMA 1G":   80.00,
            "🐘 KETA 1G":   80.00,
            "🌸 TUCI 1G":  120.00,
            "🍬 EXTA 1X":   30.00,
        },
        "Quinta Do Lago": {
            "❄️ COCA 1G":  130.00,
            "🍾 MDMA 1G":   80.00,
            "🐘 KETA 1G":   80.00,
            "🌸 TUCI 1G":  120.00,
            "🍬 EXTA 1X":   30.00,
        },
        "Almancil": {
            "❄️ COCA 1G":  130.00,
            "🍾 MDMA 1G":   80.00,
            "🐘 KETA 1G":   80.00,
            "🌸 TUCI 1G":  120.00,
            "🍬 EXTA 1X":   30.00,
        },
        "Armação De Pera": {
            "❄️ COCA 1G":  130.00,
            "🍾 MDMA 1G":   80.00,
            "🐘 KETA 1G":   80.00,
            "🌸 TUCI 1G":  120.00,
            "🍬 EXTA 1X":   30.00,
        },
        "Ferragudo": {
            "❄️ COCA 1G":  130.00,
            "🍾 MDMA 1G":   80.00,
            "🐘 KETA 1G":   80.00,
            "🌸 TUCI 1G":  120.00,
            "🍬 EXTA 1X":   30.00,
        },
        "Alvor": {
            "❄️ COCA 1G":  130.00,
            "🍾 MDMA 1G":   80.00,
            "🐘 KETA 1G":   80.00,
            "🌸 TUCI 1G":  120.00,
            "🍬 EXTA 1X":   30.00,
        },
    },
    "🇮🇹 Italie": {
        # Milan, Rome, Florence — nouveau menu min 2 articles
        "Milan": {
            "❄️ COCA 1G":  130.00,
            "🌸 TUCI 1G":  150.00,
            "🍾 MDMA 1G":  100.00,
            "🍬 EXTA 1X":   40.00,
        },
        "Rome": {
            "❄️ COCA 1G":  130.00,
            "🌸 TUCI 1G":  150.00,
            "🍾 MDMA 1G":  100.00,
            "🍬 EXTA 1X":   40.00,
        },
        "Florence": {
            "❄️ COCA 1G":  130.00,
            "🌸 TUCI 1G":  150.00,
            "🍾 MDMA 1G":  100.00,
            "🍬 EXTA 1X":   40.00,
        },
    },
    "🇭🇷 Croatie": {
        # NOUVEAU PAYS — min 2 articles
        "Dubrovnik": {
            "❄️ COCA 1G":  150.00,
            "🌸 TUCI 1G":  160.00,
            "🍾 MDMA 1G":  100.00,
            "🍬 EXTA 1X":   40.00,
        },
        "Split": {
            "❄️ COCA 1G":  150.00,
            "🌸 TUCI 1G":  160.00,
            "🍾 MDMA 1G":  100.00,
            "🍬 EXTA 1X":   40.00,
        },
    },
    "🇭🇺 Hongrie": {
        "Budapest": {
            "❄️ COCA 1G":    80.00,
            "🍾 MDMA 1G":    60.00,
            "🍬 EXTA 10PCS": 60.00,
            "🐘 KETA 1G":    60.00,
            "🌸 TUCI 1G":   100.00,
        },
    },
    "🇦🇱 Albanie": {
        "Tirana": {
            "❄️ COCA 1G":   120.00,
        },
    },
    "🇳🇱 Pays-Bas": {
        # Amsterdam, Eindhoven, Tilburg — pas de min
        "Amsterdam": {
            "❄️ COCA 1G":  120.00,
            "🍾 MDMA 1G":   70.00,
            "🐘 KETA 1G":   70.00,
            "🌸 TUCI 1G":  130.00,
            "🍬 EXTA 1X":   20.00,
            "💊 3MMC 1G":   70.00,
        },
        "Eindhoven": {
            "❄️ COCA 1G":  120.00,
            "🍾 MDMA 1G":   70.00,
            "🐘 KETA 1G":   70.00,
            "🌸 TUCI 1G":  130.00,
            "🍬 EXTA 1X":   20.00,
            "💊 3MMC 1G":   70.00,
        },
        "Tilburg": {
            "❄️ COCA 1G":  120.00,
            "🍾 MDMA 1G":   70.00,
            "🐘 KETA 1G":   70.00,
            "🌸 TUCI 1G":  130.00,
            "🍬 EXTA 1X":   20.00,
            "💊 3MMC 1G":   70.00,
        },
        # Utrecht, Rotterdam — min 250 €
        "Utrecht": {
            "❄️ COCA 1G":  120.00,
            "🍾 MDMA 1G":   70.00,
            "🐘 KETA 1G":   70.00,
            "🌸 TUCI 1G":  130.00,
            "🍬 EXTA 1X":   20.00,
            "💊 3MMC 1G":   70.00,
        },
        "Rotterdam": {
            "❄️ COCA 1G":  120.00,
            "🍾 MDMA 1G":   70.00,
            "🐘 KETA 1G":   70.00,
            "🌸 TUCI 1G":  130.00,
            "🍬 EXTA 1X":   20.00,
            "💊 3MMC 1G":   70.00,
        },
    },
    "🇩🇪 Allemagne": {
        "Berlin": {
            "❄️ COCA 1G":    80.00,
            "🍾 MDMA 1G":    60.00,
            "🍬 EXTA 10PCS": 60.00,
            "🐘 KETA 1G":    60.00,
            "🌸 TUCI 1G":   100.00,
            "🥦 WEED 5G":    60.00,
            "🍫 HASH 10G":   60.00,
        },
    },
    "🇺🇸 États-Unis": {
        "Las Vegas": {
            "❄️ COCA 1G":   120.00,
            "🍾 MDMA 1G":    80.00,
            "🍬 EXTA 5PCS":  80.00,
            "🐘 KETA 1G":    70.00,
            "🌸 TUCI 1G":   150.00,
            "🥦 WEED 3.5G":  60.00,
        },
        "Miami": {
            "❄️ COCA 1G":   150.00,
            "🌸 TUCI 1G":   200.00,
            "🐘 KETA 1G":   150.00,
        },
    },
    "🇹🇭 Thaïlande": {
        "Phuket": {
            "❄️ COCA 1G":   100.00,
            "🍾 MDMA 1G":    60.00,
            "🍬 EXTA 5PCS":  60.00,
            "🐘 KETA 1G":    50.00,
            "🥦 WEED 5G":    40.00,
            "🍫 HASH 10G":   50.00,
        },
        "Bangkok": {
            "❄️ COCA 1G":   100.00,
            "🍾 MDMA 1G":    60.00,
            "🍬 EXTA 5PCS":  60.00,
            "🐘 KETA 1G":    50.00,
            "🥦 WEED 5G":    40.00,
            "🍫 HASH 10G":   50.00,
        },
    },
    "🇲🇦 Maroc": {
        "Marrakech": {
            "❄️ COCA 1G":   80.00,
            "🥦 WEED 5G":   30.00,
            "🍫 HASH 10G":  30.00,
            "🍬 EXTA 5PCS": 60.00,
            "🐘 KETA 1G":   60.00,
        },
        "Tanger": {
            "❄️ COCA 1G":   80.00,
            "🥦 WEED 5G":   30.00,
            "🍫 HASH 10G":  30.00,
            "🍬 EXTA 5PCS": 60.00,
            "🐘 KETA 1G":   60.00,
        },
    },
}

# Devises par pays (tous en euros ici)
CURRENCIES = {
    "🇫🇷 France":     "€",
    "🇧🇪 Belgique":   "€",
    "🇬🇧 Angleterre": "€",
    "🇪🇸 Espagne":    "€",
    "🇬🇷 Grèce":      "€",
    "🇵🇹 Portugal":   "€",
    "🇮🇹 Italie":     "€",
    "🇭🇷 Croatie":    "€",
    "🇭🇺 Hongrie":    "€",
    "🇦🇱 Albanie":    "€",
    "🇳🇱 Pays-Bas":    "€",
    "🇩🇪 Allemagne":   "€",
    "🇺🇸 États-Unis":  "€",
    "🇹🇭 Thaïlande":   "€",
    "🇲🇦 Maroc":       "€",
}


# Commande minimum par ville.
# type "amount" → montant minimum en devise locale (€)
# type "qty"    → nombre minimum d'articles dans le panier (toutes références confondues)
MIN_ORDER: dict[str, dict] = {
    # France
    "Paris":       {"type": "amount", "value": 70},
    # Belgique
    "Bruxelles":   {"type": "amount", "value": 100},
    # Angleterre
    "Londres":     {"type": "amount", "value": 40},
    "Manchester":  {"type": "amount", "value": 40},
    # Espagne
    "Barcelone":         {"type": "amount", "value": 70},
    "Marbella":          {"type": "amount", "value": 200},
    "Malaga":            {"type": "amount", "value": 200},
    # Palma De Majorque, Tenerife, Lanzarote → pas de min
    # Grèce — min 2 articles (toutes villes)
    "Mykonos":     {"type": "qty",    "value": 2},
    "Santorini":   {"type": "qty",    "value": 2},
    "Athènes":     {"type": "qty",    "value": 2},
    "Corfu":       {"type": "qty",    "value": 2},
    "Rhodes":      {"type": "qty",    "value": 2},
    "Crète":       {"type": "qty",    "value": 2},
    "Zakynthos":   {"type": "qty",    "value": 2},
    # Portugal
    # Albufeira, Vilamoura, Lisbonne → pas de min dans le nouveau menu
    "Porto":       {"type": "amount", "value": 120},   # inchangé
    # Portugal Groupe 2 — min 250 €
    "Portimao":         {"type": "amount", "value": 250},
    "Carvoeiro":        {"type": "amount", "value": 250},
    "Quinta Do Lago":   {"type": "amount", "value": 250},
    "Almancil":         {"type": "amount", "value": 250},
    "Armação De Pera":  {"type": "amount", "value": 250},
    "Ferragudo":        {"type": "amount", "value": 250},
    "Alvor":            {"type": "amount", "value": 250},
    # Italie — min 2 articles
    "Milan":       {"type": "qty",    "value": 2},
    "Rome":        {"type": "qty",    "value": 2},
    "Florence":    {"type": "qty",    "value": 2},
    # Croatie — min 2 articles
    "Dubrovnik":   {"type": "qty",    "value": 2},
    "Split":       {"type": "qty",    "value": 2},
    # Hongrie
    "Budapest":    {"type": "amount", "value": 60},
    # Albanie
    "Tirana":      {"type": "amount", "value": 120},
    # Pays-Bas
    # Amsterdam, Eindhoven, Tilburg → pas de min
    "Utrecht":     {"type": "amount", "value": 250},
    "Rotterdam":   {"type": "amount", "value": 250},
    # Allemagne
    "Berlin":      {"type": "amount", "value": 60},
    # États-Unis
    "Las Vegas":   {"type": "amount", "value": 80},
    # Thaïlande
    "Phuket":      {"type": "amount", "value": 60},
    "Bangkok":     {"type": "amount", "value": 60},
    # Maroc
    "Marrakech":   {"type": "amount", "value": 50},
    "Tanger":      {"type": "amount", "value": 50},
}


def get_currency(country: str) -> str:
    return CURRENCIES.get(country, "€")


# ═══════════════════════════════════════════════════════════════════════════
# Devises d'AFFICHAGE proposées au client, par pays.
# Modèle "même montant, symbole change" : le prix (ex: 150) reste identique,
# seul le symbole affiché change. La 1ʳᵉ devise de la liste est celle par
# défaut. Si la liste a une seule devise → pas de sélecteur (imposée).
# ═══════════════════════════════════════════════════════════════════════════
ALL_CURRENCIES = ["€", "$", "£"]   # "toutes les monnaies" pour le reste du monde

# On encaisse la monnaie du pays, et elle seule : c'est ce qui circule sur
# place, et le livreur n'a pas à faire de change à la porte du client.
COUNTRY_CURRENCIES: dict[str, list[str]] = {
    # Zone euro
    "🇫🇷 France":     ["€"],
    "🇧🇪 Belgique":   ["€"],
    "🇳🇱 Pays-Bas":   ["€"],
    "🇪🇸 Espagne":    ["€"],
    "🇮🇹 Italie":     ["€"],
    "🇬🇷 Grèce":      ["€"],
    "🇵🇹 Portugal":   ["€"],
    "🇩🇪 Allemagne":  ["€"],
    "🇭🇷 Croatie":    ["€"],
    # Hors zone euro : la monnaie locale
    "🇺🇸 États-Unis": ["$"],
    "🇬🇧 Angleterre": ["£"],
    "🇹🇭 Thaïlande":  ["฿"],
    "🇲🇦 Maroc":      ["dh"],
    # Hongrie et Albanie ne sont pas listées : leur monnaie n'est ni l'euro ni
    # une de celles qu'on encaisse. Elles gardent donc le choix par défaut
    # jusqu'à décision — mieux vaut une liste large qu'une devise inventée.
}


# ═══════════════════════════════════════════════════════════════════════════
# Règles de paiement par VILLE, quand elles diffèrent de celles du pays.
#
# Une ville peut n'accepter qu'une partie des moyens de paiement, et n'être
# réglée que dans certaines devises. Ce qui n'est pas listé ici suit le pays.
# ═══════════════════════════════════════════════════════════════════════════
METHODES_PAIEMENT = ["cash", "link", "crypto"]

# ── Paiements en stand-by ─────────────────────────────────────────────────────
# Un moyen listé ici est suspendu : retiré de TOUTES les villes, aussi bien
# côté client (sa carte disparaît de la Mini App) que côté serveur (une commande
# passée avec ce moyen est refusée). C'est le point unique pour couper puis
# rétablir un paiement sans toucher au reste du code.
#
# Rétablir un moyen = le retirer de cet ensemble. Sans redéploiement, on peut
# aussi piloter la liste depuis Render via la variable d'environnement
# PAIEMENTS_STANDBY (moyens séparés par des virgules ; une valeur vide réactive
# tout et prime alors sur la valeur ci-dessous).
#
# Suspendu actuellement : « link » = Carte bancaire · Apple Pay · Google Pay
# (le lien de paiement). Le liquide (« cash ») et la crypto restent actifs.
MOYENS_STANDBY = {"link"}


def _moyens_standby() -> set:
    """Moyens de paiement suspendus. La variable d'environnement PAIEMENTS_STANDBY,
    si elle est définie (même vide), l'emporte sur MOYENS_STANDBY."""
    brut = os.getenv("PAIEMENTS_STANDBY")
    if brut is None:
        return set(MOYENS_STANDBY)
    return {m.strip() for m in brut.split(",") if m.strip()}


PAIEMENT_PAR_VILLE: dict[tuple[str, str], dict] = {
    # Espagne : ces trois villes ne prennent que du liquide, en euros.
    ("🇪🇸 Espagne", "Barcelone"): {"methodes": ["cash"], "devises": ["€"]},
    ("🇪🇸 Espagne", "Marbella"):  {"methodes": ["cash"], "devises": ["€"]},
    ("🇪🇸 Espagne", "Malaga"):    {"methodes": ["cash"], "devises": ["€"]},
}


def get_payment_methods(country: str, city: str = "") -> list[str]:
    """Moyens de paiement acceptés pour cette ville. Tous par défaut, moins ceux
    en stand-by (voir MOYENS_STANDBY / PAIEMENTS_STANDBY)."""
    regle = PAIEMENT_PAR_VILLE.get((country, city)) or {}
    standby = _moyens_standby()
    methodes = [m for m in (regle.get("methodes") or METHODES_PAIEMENT)
                if m in METHODES_PAIEMENT and m not in standby]
    # Une ville sans aucun moyen de paiement serait invendable : on retombe
    # sur le liquide, qui ne dépend d'aucune configuration extérieure.
    return methodes or ["cash"]


def get_currencies(country: str, city: str = "") -> list[str]:
    """Devises d'affichage proposées. La ville l'emporte sur le pays.
    Défaut = toutes les devises majeures (€/$/£)."""
    regle = PAIEMENT_PAR_VILLE.get((country, city)) or {}
    if regle.get("devises"):
        return list(regle["devises"])
    return COUNTRY_CURRENCIES.get(country, ALL_CURRENCIES)


# ═══════════════════════════════════════════════════════════════════════════
# ÉDITION DU CATALOGUE DEPUIS L'ESPACE ADMIN
#
# Le catalogue défini plus haut est le SOCLE par défaut. Dès que l'owner édite
# quoi que ce soit depuis la Mini App, l'état complet est validé, enregistré
# dans `catalogue.json` (dans DATA_DIR) et sauvegardé sur GitHub — le disque de
# Render étant éphémère. À chaque import de ce module (et webapp le recharge à
# chaque requête touchant le catalogue), cet overlay est ré-appliqué par-dessus
# le socle : une modification est donc active immédiatement, sans redéploiement.
# ═══════════════════════════════════════════════════════════════════════════
_logger = logging.getLogger(__name__)
_DATA_DIR = Path(os.getenv("DATA_DIR", str(Path(__file__).parent)))
_FICHIER_CATALOGUE = _DATA_DIR / "catalogue.json"
_verrou_catalogue = threading.RLock()

# Plafonds de sûreté. Un catalogue reste petit ; ils bloquent surtout un envoi
# aberrant qui ferait gonfler le fichier ou l'écran.
_MAX_PAYS = 80
_MAX_VILLES = 80
_MAX_PRODUITS = 60
_MAX_NOM = 60
_PRIX_MAX = 100000
# Devises d'affichage autorisées (symbole seul ; le montant, lui, ne change pas).
_SYMBOLES_OK = ["€", "$", "£", "฿", "dh"]


class CatalogueInvalide(ValueError):
    """Le catalogue soumis n'est pas exploitable ; le message dit pourquoi."""


def snapshot() -> dict:
    """État complet et éditable du catalogue, tel qu'envoyé à l'éditeur admin.

    Chaque pays porte ses devises d'affichage, chaque ville ses produits (nom +
    prix), son minimum de commande, ses moyens de paiement et ses devises. Un
    `None` sur `methodes`/`devises` d'une ville veut dire « suit le réglage par
    défaut » (tous les moyens / les devises du pays)."""
    pays_list = []
    for pays, villes in CATALOG.items():
        villes_list = []
        for ville, produits in villes.items():
            regle = PAIEMENT_PAR_VILLE.get((pays, ville)) or {}
            villes_list.append({
                "nom": ville,
                "produits": [{"nom": nom, "prix": float(prix)}
                             for nom, prix in produits.items()],
                "min": (dict(MIN_ORDER[ville]) if ville in MIN_ORDER else None),
                "methodes": (list(regle["methodes"])
                             if regle.get("methodes") is not None else None),
                "devises": (list(regle["devises"]) if regle.get("devises") else None),
            })
        pays_list.append({
            "nom": pays,
            "devises": list(COUNTRY_CURRENCIES.get(pays, ALL_CURRENCIES)),
            "villes": villes_list,
        })
    return {
        "version": 1,
        "pays": pays_list,
        # De quoi peupler les listes déroulantes de l'éditeur, sans les coder
        # en dur côté client.
        "symboles_possibles": list(_SYMBOLES_OK),
        "methodes_possibles": list(METHODES_PAIEMENT),
        "moyens_standby": sorted(_moyens_standby()),
    }


# ── Validation / normalisation ───────────────────────────────────────────────

def _txt(v, quoi: str) -> str:
    if not isinstance(v, str):
        raise CatalogueInvalide(f"{quoi} : texte attendu")
    v = v.strip()
    if not v:
        raise CatalogueInvalide(f"{quoi} : ne peut pas être vide")
    if len(v) > _MAX_NOM:
        raise CatalogueInvalide(f"{quoi} : trop long (max {_MAX_NOM} caractères)")
    return v


def _valider_prix(v, quoi: str) -> float:
    try:
        prix = float(v)
    except (TypeError, ValueError):
        raise CatalogueInvalide(f"{quoi} : prix invalide")
    if prix != prix or prix < 0 or prix > _PRIX_MAX:      # NaN ou hors bornes
        raise CatalogueInvalide(f"{quoi} : prix hors limites (0 à {_PRIX_MAX})")
    prix = round(prix, 2)
    return int(prix) if prix == int(prix) else prix


def _valider_min(v, ville: str):
    if not v:
        return None
    if not isinstance(v, dict):
        raise CatalogueInvalide(f"{ville} : minimum mal formé")
    typ = v.get("type")
    if typ not in ("amount", "qty"):
        raise CatalogueInvalide(f"{ville} : type de minimum inconnu")
    try:
        val = float(v.get("value"))
    except (TypeError, ValueError):
        raise CatalogueInvalide(f"{ville} : valeur de minimum invalide")
    if val <= 0 or val > 1000000:
        raise CatalogueInvalide(f"{ville} : minimum hors limites")
    if typ == "qty":
        return {"type": "qty", "value": int(val)}
    val = round(val, 2)
    return {"type": "amount", "value": int(val) if val == int(val) else val}


def _valider_methodes(v, ville: str):
    if v is None:
        return None
    if not isinstance(v, list):
        raise CatalogueInvalide(f"{ville} : moyens de paiement mal formés")
    m = [x for x in METHODES_PAIEMENT if x in v]   # ordre canonique, ignore l'inconnu
    if not m:
        raise CatalogueInvalide(f"{ville} : au moins un moyen de paiement")
    if m == list(METHODES_PAIEMENT):
        return None                                # tous acceptés = pas de règle
    return m


def _valider_devises(v):
    """Liste de devises valides en préservant l'ordre (la 1ʳᵉ = par défaut)."""
    if not v:
        return None
    if not isinstance(v, list):
        raise CatalogueInvalide("devises mal formées")
    d = []
    for s in v:
        if s in _SYMBOLES_OK and s not in d:
            d.append(s)
    if not d:
        raise CatalogueInvalide("devise inconnue")
    return d


def valider(data) -> dict:
    """Vérifie et NORMALISE un snapshot reçu de l'éditeur. Lève
    CatalogueInvalide avec un message clair au premier problème rencontré."""
    if not isinstance(data, dict):
        raise CatalogueInvalide("format inattendu")
    pays_in = data.get("pays")
    if not isinstance(pays_in, list) or not pays_in:
        raise CatalogueInvalide("Il faut au moins un pays.")
    if len(pays_in) > _MAX_PAYS:
        raise CatalogueInvalide(f"Trop de pays (max {_MAX_PAYS}).")

    noms_pays = set()
    villes_globales = set()      # unicité GLOBALE des villes (clé de MIN_ORDER)
    pays_out = []
    for p in pays_in:
        if not isinstance(p, dict):
            raise CatalogueInvalide("pays mal formé")
        nom_pays = _txt(p.get("nom"), "Nom du pays")
        if nom_pays.lower() in noms_pays:
            raise CatalogueInvalide(f"Pays en double : {nom_pays}")
        noms_pays.add(nom_pays.lower())
        devises_pays = _valider_devises(p.get("devises")) or list(ALL_CURRENCIES)

        villes_in = p.get("villes")
        if not isinstance(villes_in, list):
            raise CatalogueInvalide(f"{nom_pays} : liste de villes attendue")
        if len(villes_in) > _MAX_VILLES:
            raise CatalogueInvalide(f"{nom_pays} : trop de villes (max {_MAX_VILLES}).")

        villes_out = []
        for v in villes_in:
            if not isinstance(v, dict):
                raise CatalogueInvalide(f"{nom_pays} : ville mal formée")
            nom_ville = _txt(v.get("nom"), "Nom de la ville")
            if nom_ville.lower() in villes_globales:
                raise CatalogueInvalide(
                    f"Ville en double : {nom_ville} — les noms de ville doivent "
                    f"être uniques (même entre pays).")
            villes_globales.add(nom_ville.lower())

            produits_in = v.get("produits") or []
            if not isinstance(produits_in, list):
                raise CatalogueInvalide(f"{nom_ville} : liste de produits attendue")
            if len(produits_in) > _MAX_PRODUITS:
                raise CatalogueInvalide(f"{nom_ville} : trop de produits (max {_MAX_PRODUITS}).")
            noms_prod = set()
            produits_out = []
            for pr in produits_in:
                if not isinstance(pr, dict):
                    raise CatalogueInvalide(f"{nom_ville} : produit mal formé")
                nom_prod = _txt(pr.get("nom"), "Nom du produit")
                if nom_prod.lower() in noms_prod:
                    raise CatalogueInvalide(f"{nom_ville} : produit en double : {nom_prod}")
                noms_prod.add(nom_prod.lower())
                produits_out.append({"nom": nom_prod,
                                     "prix": _valider_prix(pr.get("prix"), nom_prod)})

            villes_out.append({
                "nom": nom_ville,
                "produits": produits_out,
                "min": _valider_min(v.get("min"), nom_ville),
                "methodes": _valider_methodes(v.get("methodes"), nom_ville),
                "devises": _valider_devises(v.get("devises")),
            })
        pays_out.append({"nom": nom_pays, "devises": devises_pays, "villes": villes_out})
    return {"version": 1, "pays": pays_out}


# ── Application / persistance ────────────────────────────────────────────────

def _appliquer_donnees(data: dict) -> None:
    """Remplace les tables du module par les données (déjà validées)."""
    global CATALOG, MIN_ORDER, CURRENCIES, COUNTRY_CURRENCIES, PAIEMENT_PAR_VILLE
    cat, mini_o, cur, cc, pv = {}, {}, {}, {}, {}
    for p in data["pays"]:
        pays = p["nom"]
        cat[pays] = {}
        cur[pays] = "€"                               # encaisse (hérité, tout en €)
        cc[pays] = list(p.get("devises") or ALL_CURRENCIES)
        for v in p["villes"]:
            ville = v["nom"]
            cat[pays][ville] = {pr["nom"]: float(pr["prix"]) for pr in v["produits"]}
            if v.get("min"):
                mini_o[ville] = dict(v["min"])
            regle = {}
            if v.get("methodes") is not None:
                regle["methodes"] = list(v["methodes"])
            if v.get("devises"):
                regle["devises"] = list(v["devises"])
            if regle:
                pv[(pays, ville)] = regle
    CATALOG, MIN_ORDER, CURRENCIES = cat, mini_o, cur
    COUNTRY_CURRENCIES, PAIEMENT_PAR_VILLE = cc, pv


def _ecrire_overlay(data: dict) -> None:
    """Écrit catalogue.json de façon atomique (écriture temp puis remplacement)."""
    tmp = _FICHIER_CATALOGUE.with_name(_FICHIER_CATALOGUE.name + ".tmp")
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, _FICHIER_CATALOGUE)
    except OSError as exc:
        _logger.error("Écriture catalogue.json : %s", exc)
        raise


def sauver_catalogue(data) -> dict:
    """Valide, applique EN MÉMOIRE puis persiste un catalogue édité. Renvoie le
    snapshot à jour. Lève CatalogueInvalide si les données sont inexploitables."""
    propre = valider(data)
    with _verrou_catalogue:
        _appliquer_donnees(propre)
        _ecrire_overlay(propre)
    try:
        import github_backup
        github_backup.backup_file_async("catalogue.json")
    except Exception as exc:                            # backup best-effort
        _logger.warning("catalogue.json : backup GitHub différé (%s)", exc)
    return snapshot()


def _charger_overlay() -> None:
    """Au chargement du module : ré-applique catalogue.json s'il existe. Un
    fichier illisible ou invalide est ignoré — on garde le socle par défaut
    plutôt que de casser la boutique."""
    try:
        if not _FICHIER_CATALOGUE.exists():
            return
        with _FICHIER_CATALOGUE.open(encoding="utf-8") as f:
            data = json.load(f)
        _appliquer_donnees(valider(data))
    except CatalogueInvalide as exc:
        _logger.error("catalogue.json ignoré (invalide) : %s", exc)
    except (OSError, json.JSONDecodeError) as exc:
        _logger.error("catalogue.json illisible : %s", exc)


_charger_overlay()

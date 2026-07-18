# catalog.py — Modifiez ce fichier pour personnaliser vos produits, villes et pays
# Format : CATALOG[pays][ville][produit] = prix

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

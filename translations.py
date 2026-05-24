# translations.py — Toutes les chaînes visibles par le client en FR / ES / EN
# Ajouter une nouvelle clé : T["ma_cle"] = {"fr": "...", "es": "...", "en": "..."}

T = {
    # ── Accueil ────────────────────────────────────────────────────────────
    "welcome_title": {
        "fr": "🛍️ *Bienvenue !*",
        "es": "🛍️ *¡Bienvenido!*",
        "en": "🛍️ *Welcome!*",
    },
    "welcome_body": {
        "fr": "Appuyez sur le bouton ci-dessous pour accéder au catalogue.",
        "es": "Pulsa el botón de abajo para acceder al catálogo.",
        "en": "Press the button below to access the catalog.",
    },
    "btn_open_catalog": {
        "fr": "🛍️ Accéder au catalogue",
        "es": "🛍️ Acceder al catálogo",
        "en": "🛍️ Open catalog",
    },

    # ── Langue ─────────────────────────────────────────────────────────────
    "choose_language": {
        "fr": "🌐 *Choisissez votre langue :*",
        "es": "🌐 *Elige tu idioma:*",
        "en": "🌐 *Choose your language:*",
    },

    # ── Mot de passe ───────────────────────────────────────────────────────
    "ask_password": {
        "fr": "🔐 Pour accéder au service, entrez le *mot de passe* :",
        "es": "🔐 Para acceder al servicio, introduce la *contraseña*:",
        "en": "🔐 To access the service, enter the *password*:",
    },
    "wrong_password": {
        "fr": "❌ Mot de passe incorrect. Tentative {n}/3.",
        "es": "❌ Contraseña incorrecta. Intento {n}/3.",
        "en": "❌ Wrong password. Attempt {n}/3.",
    },
    "blocked": {
        "fr": "🚫 Trop de tentatives. Réessayez dans {min} minutes.",
        "es": "🚫 Demasiados intentos. Vuelve a intentarlo en {min} minutos.",
        "en": "🚫 Too many attempts. Try again in {min} minutes.",
    },
    "welcome_user": {
        "fr": "✅ *Bienvenue, {name} !* 🎉",
        "es": "✅ *¡Bienvenido, {name}!* 🎉",
        "en": "✅ *Welcome, {name}!* 🎉",
    },
    # Affiché juste après le choix de langue (welcome localisé + demande mot de passe)
    "welcome_after_lang": {
        "fr": "🛍️ *Bienvenue, {name} !* 🎉\n\n🔐 Entrez le *mot de passe* pour accéder au catalogue :",
        "es": "🛍️ *¡Bienvenido, {name}!* 🎉\n\n🔐 Introduce la *contraseña* para acceder al catálogo:",
        "en": "🛍️ *Welcome, {name}!* 🎉\n\n🔐 Enter the *password* to access the catalog:",
    },
    # /help client
    "help_text": {
        "fr": "📖 *Aide*\n\n*Horaires :* 11h00 → 06h00 — tous les jours\n\n*Commandes :*\n/start — Démarrer ou redémarrer\n/status — Voir si le service est ouvert\n/cancel — Annuler la commande en cours\n/skip — Passer l'étape téléphone\n/help — Afficher cette aide\n\n*Flux de commande :*\n1️⃣ Langue\n2️⃣ Mot de passe\n3️⃣ Téléphone (optionnel)\n4️⃣ Pays → Ville\n5️⃣ Sélection des articles\n6️⃣ Paiement → Adresse\n7️⃣ Selfie de vérification\n8️⃣ Confirmation",
        "es": "📖 *Ayuda*\n\n*Horario:* 11:00 → 06:00 — todos los días\n\n*Comandos:*\n/start — Iniciar o reiniciar\n/status — Ver si el servicio está abierto\n/cancel — Cancelar el pedido en curso\n/skip — Omitir el paso del teléfono\n/help — Mostrar esta ayuda\n\n*Flujo del pedido:*\n1️⃣ Idioma\n2️⃣ Contraseña\n3️⃣ Teléfono (opcional)\n4️⃣ País → Ciudad\n5️⃣ Selección de artículos\n6️⃣ Pago → Dirección\n7️⃣ Selfie de verificación\n8️⃣ Confirmación",
        "en": "📖 *Help*\n\n*Hours:* 11:00 → 06:00 — every day\n\n*Commands:*\n/start — Start or restart\n/status — Check if service is open\n/cancel — Cancel current order\n/skip — Skip phone step\n/help — Show this help\n\n*Order flow:*\n1️⃣ Language\n2️⃣ Password\n3️⃣ Phone (optional)\n4️⃣ Country → City\n5️⃣ Item selection\n6️⃣ Payment → Address\n7️⃣ Verification selfie\n8️⃣ Confirmation",
    },
    # Statut ouvert / fermé
    "status_open": {
        "fr": "✅ *Service ouvert !*\n\n🕘 Horaires : 11h00 → 06h00\n\nTapez /start pour commander.",
        "es": "✅ *¡Servicio abierto!*\n\n🕘 Horario: 11:00 → 06:00\n\nEscribe /start para pedir.",
        "en": "✅ *Service open!*\n\n🕘 Hours: 11:00 → 06:00\n\nType /start to order.",
    },
    "status_closed": {
        "fr": "🌙 *Service fermé.*\n\n🕘 Horaires : *11h00 → 06h00* tous les jours.\n\nRevenez à *11h00* !",
        "es": "🌙 *Servicio cerrado.*\n\n🕘 Horario: *11:00 → 06:00* todos los días.\n\n¡Vuelve a las *11:00*!",
        "en": "🌙 *Service closed.*\n\n🕘 Hours: *11:00 → 06:00* every day.\n\nCome back at *11:00 AM*!",
    },

    # ── Téléphone (M1) ────────────────────────────────────────────────────────
    "phone_request": {
        "fr": "📱 *Étape de sécurité*\n\nPartagez votre numéro pour faciliter les prochaines commandes.\n\n_Optionnel — appuyez sur « Passer » si vous préférez ne pas le partager._",
        "es": "📱 *Paso de seguridad*\n\nComparte tu número para facilitar futuros pedidos.\n\n_Opcional — pulsa «Omitir» si prefieres no compartirlo._",
        "en": "📱 *Security step*\n\nShare your number to make future orders easier.\n\n_Optional — press «Skip» if you prefer not to share._",
    },
    "btn_share_phone": {
        "fr": "📱 Partager mon numéro",
        "es": "📱 Compartir mi número",
        "en": "📱 Share my number",
    },
    "phone_skip_btn": {
        "fr": "⏭️ Passer",
        "es": "⏭️ Omitir",
        "en": "⏭️ Skip",
    },
    "phone_received": {
        "fr": "✅ Numéro enregistré !",
        "es": "✅ ¡Número registrado!",
        "en": "✅ Number saved!",
    },
    "phone_skipped": {
        "fr": "👍 Étape passée.",
        "es": "👍 Paso omitido.",
        "en": "👍 Step skipped.",
    },

    # ── Pays / Ville ───────────────────────────────────────────────────────
    "choose_country": {
        "fr": "🌍 *Sélectionnez votre pays :*",
        "es": "🌍 *Selecciona tu país:*",
        "en": "🌍 *Select your country:*",
    },
    "choose_city": {
        "fr": "🏙️ *{country}* — Sélectionnez votre ville :",
        "es": "🏙️ *{country}* — Selecciona tu ciudad:",
        "en": "🏙️ *{country}* — Select your city:",
    },
    "back_countries": {
        "fr": "◀️ Retour aux pays",
        "es": "◀️ Volver a países",
        "en": "◀️ Back to countries",
    },
    "back_cities": {
        "fr": "◀️ Changer de ville",
        "es": "◀️ Cambiar de ciudad",
        "en": "◀️ Change city",
    },

    # ── Menu / Panier ──────────────────────────────────────────────────────
    "menu_title": {
        "fr": "🍽️ *Menu — {city}*\n\nSélectionnez vos articles :",
        "es": "🍽️ *Menú — {city}*\n\nSelecciona tus artículos:",
        "en": "🍽️ *Menu — {city}*\n\nSelect your items:",
    },
    "view_cart": {
        "fr": "🛒 Voir panier ({n}) — {total} {cur}",
        "es": "🛒 Ver carrito ({n}) — {total} {cur}",
        "en": "🛒 View cart ({n}) — {total} {cur}",
    },
    "cart_title": {
        "fr": "🛒 *Votre panier :*\n",
        "es": "🛒 *Tu carrito:*\n",
        "en": "🛒 *Your cart:*\n",
    },
    "cart_empty": {
        "fr": "Votre panier est vide !",
        "es": "¡Tu carrito está vacío!",
        "en": "Your cart is empty!",
    },
    "cart_total": {
        "fr": "💰 *Total : {total} {cur}*",
        "es": "💰 *Total: {total} {cur}*",
        "en": "💰 *Total: {total} {cur}*",
    },
    "btn_checkout": {
        "fr": "✅ Passer la commande",
        "es": "✅ Realizar pedido",
        "en": "✅ Place order",
    },
    "btn_continue_shopping": {
        "fr": "◀️ Continuer les achats",
        "es": "◀️ Seguir comprando",
        "en": "◀️ Continue shopping",
    },
    "btn_validate_changes": {
        "fr": "✅ Valider les modifications",
        "es": "✅ Confirmar los cambios",
        "en": "✅ Confirm changes",
    },

    # ── Paiement — écran principal ─────────────────────────────────────────
    "choose_payment": {
        "fr": "💳 *Choisissez votre mode de paiement :*",
        "es": "💳 *Elige tu método de pago:*",
        "en": "💳 *Choose your payment method:*",
    },
    "back_cart": {
        "fr": "◀️ Retour au panier",
        "es": "◀️ Volver al carrito",
        "en": "◀️ Back to cart",
    },
    "btn_pay_back": {
        "fr": "◀️ Retour aux paiements",
        "es": "◀️ Volver a los pagos",
        "en": "◀️ Back to payments",
    },
    # Boutons des 4 méthodes
    "pay_btn_cash":     {"fr": "💵 Cash",              "es": "💵 Efectivo",       "en": "💵 Cash"},
    "pay_btn_virement": {"fr": "🏦 Virement bancaire", "es": "🏦 Transferencia",  "en": "🏦 Bank transfer"},
    "pay_btn_link":     {"fr": "🔗 Lien de paiement",  "es": "🔗 Enlace de pago", "en": "🔗 Payment link"},
    "pay_btn_crypto":   {"fr": "₿ Crypto",             "es": "₿ Cripto",          "en": "₿ Crypto"},
    # ── Cash → devise ─────────────────────────────────────────────────────
    "pay_choose_currency": {
        "fr": "💵 *Cash — Choisissez votre devise :*",
        "es": "💵 *Efectivo — Elige tu divisa:*",
        "en": "💵 *Cash — Choose your currency:*",
    },
    "pay_cash_confirmed": {
        "fr": "✅ Paiement *cash* en *{cur}* noté.\n\n📍 *Adresse de livraison* :\n_Rue + ville, code postal, ou nom d'un lieu (Tour Eiffel, Moulin Rouge…)_",
        "es": "✅ Pago *efectivo* en *{cur}* registrado.\n\n📍 *Dirección de entrega* :\n_Calle, código postal o nombre de un lugar (Sagrada Família…)_",
        "en": "✅ *Cash* in *{cur}* noted.\n\n📍 *Delivery address* :\n_Street, postcode, or landmark name (Eiffel Tower, Big Ben…)_",
    },
    # ── Virement ──────────────────────────────────────────────────────────
    "pay_virement_info": {
        "fr": "🏦 *Virement bancaire*\n\nEffectuez le virement du *montant exact* de votre commande vers le RIB suivant :\n\n```\n{iban}\n```\n\n_Une fois le virement effectué, envoyez une *capture d'écran* comme preuve._",
        "es": "🏦 *Transferencia bancaria*\n\nRealiza la transferencia del *importe exacto* al siguiente IBAN:\n\n```\n{iban}\n```\n\n_Una vez hecha, envía una *captura de pantalla* como prueba._",
        "en": "🏦 *Bank transfer*\n\nSend the *exact amount* of your order to:\n\n```\n{iban}\n```\n\n_Once done, send a *screenshot* of your transfer as proof._",
    },
    "pay_virement_need_photo": {
        "fr": "📸 Veuillez envoyer une *photo* (capture d'écran du virement), pas du texte.",
        "es": "📸 Por favor envía una *foto* (captura de la transferencia), no texto.",
        "en": "📸 Please send a *photo* (transfer screenshot), not text.",
    },
    "pay_virement_received": {
        "fr": "✅ *Capture reçue !* Virement en cours de vérification.\n\n📍 *Adresse de livraison* :\n_Rue + ville, code postal, ou nom d'un lieu (Tour Eiffel, Moulin Rouge…)_",
        "es": "✅ *¡Captura recibida!* Verificando transferencia.\n\n📍 *Dirección de entrega* :\n_Calle, código postal o nombre de un lugar (Sagrada Família…)_",
        "en": "✅ *Screenshot received!* Verifying transfer.\n\n📍 *Delivery address* :\n_Street, postcode, or landmark name (Eiffel Tower, Big Ben…)_",
    },
    # ── Lien de paiement ──────────────────────────────────────────────────
    "pay_link_info": {
        "fr": "🔗 *Lien de paiement*\n\nCliquez sur le lien ci-dessous :\n\n{link}\n\n_Une fois le paiement effectué, appuyez sur ✅ ci-dessous._",
        "es": "🔗 *Enlace de pago*\n\nHaz clic en el enlace:\n\n{link}\n\n_Una vez pagado, pulsa ✅ abajo._",
        "en": "🔗 *Payment link*\n\nClick the link below:\n\n{link}\n\n_Once paid, press ✅ below._",
    },
    "pay_link_not_configured": {
        "fr": "⚠️ Lien de paiement non encore configuré. Choisissez un autre mode.",
        "es": "⚠️ Enlace de pago aún no configurado. Elige otro método.",
        "en": "⚠️ Payment link not configured yet. Please choose another method.",
    },
    "btn_i_paid": {
        "fr": "✅ J'ai effectué le paiement",
        "es": "✅ He realizado el pago",
        "en": "✅ I have paid",
    },
    "pay_link_confirmed": {
        "fr": "✅ Paiement via lien noté.\n\n📍 *Adresse de livraison* :\n_Rue + ville, code postal, ou nom d'un lieu (Tour Eiffel, Moulin Rouge…)_",
        "es": "✅ Pago por enlace registrado.\n\n📍 *Dirección de entrega* :\n_Calle, código postal o nombre de un lugar (Sagrada Família…)_",
        "en": "✅ Link payment noted.\n\n📍 *Delivery address* :\n_Street, postcode, or landmark name (Eiffel Tower, Big Ben…)_",
    },
    # ── Crypto ────────────────────────────────────────────────────────────
    "pay_crypto_choose": {
        "fr": "₿ *Paiement en crypto*\n\nChoisissez votre cryptomonnaie :",
        "es": "₿ *Pago en cripto*\n\nElige tu criptomoneda:",
        "en": "₿ *Crypto payment*\n\nChoose your cryptocurrency:",
    },
    "pay_crypto_address": {
        "fr": "{icon} *Paiement {name}*\n\nEnvoyez le montant exact à cette adresse :\n\n```\n{address}\n```\n_(appuyez pour copier)_\n\n_Une fois envoyé, appuyez sur ✅ ci-dessous._",
        "es": "{icon} *Pago {name}*\n\nEnvía el importe exacto a esta dirección:\n\n```\n{address}\n```\n_(pulsa para copiar)_\n\n_Una vez enviado, pulsa ✅ abajo._",
        "en": "{icon} *{name} Payment*\n\nSend the exact amount to:\n\n```\n{address}\n```\n_(tap to copy)_\n\n_Once sent, press ✅ below._",
    },
    "pay_crypto_not_configured": {
        "fr": "⚠️ Adresse {name} non configurée. Choisissez un autre mode.",
        "es": "⚠️ Dirección {name} no configurada. Elige otro método.",
        "en": "⚠️ {name} address not configured. Please choose another method.",
    },
    "btn_crypto_sent": {
        "fr": "✅ J'ai envoyé la crypto",
        "es": "✅ He enviado la cripto",
        "en": "✅ I have sent the crypto",
    },
    "pay_crypto_confirmed": {
        "fr": "✅ Paiement *{name}* noté.\n\n📍 *Adresse de livraison* :\n_Rue + ville, code postal, ou nom d'un lieu (Tour Eiffel, Moulin Rouge…)_",
        "es": "✅ Pago *{name}* registrado.\n\n📍 *Dirección de entrega* :\n_Calle, código postal o nombre de un lugar (Sagrada Família…)_",
        "en": "✅ *{name}* payment noted.\n\n📍 *Delivery address* :\n_Street, postcode, or landmark name (Eiffel Tower, Big Ben…)_",
    },
    # Compatibilité — résumé commande
    "payment_selected": {
        "fr": "✅ Mode de paiement : *{p}*\n\n📍 *Adresse de livraison* :\n_Rue + ville, code postal, ou nom d'un lieu (Tour Eiffel, Moulin Rouge…)_",
        "es": "✅ Método de pago: *{p}*\n\n📍 *Dirección de entrega* :\n_Calle, código postal o nombre de un lugar (Sagrada Família…)_",
        "en": "✅ Payment: *{p}*\n\n📍 *Delivery address* :\n_Street, postcode, or landmark name (Eiffel Tower, Big Ben…)_",
    },

    # ── Adresse ────────────────────────────────────────────────────────────
    "searching_address": {
        "fr": "🔍 Recherche de l'adresse…",
        "es": "🔍 Buscando la dirección…",
        "en": "🔍 Searching address…",
    },
    "address_found": {
        "fr": "📍 *Adresse trouvée :*\n\n`{addr}`\n\n[🗺️ Voir sur OpenStreetMap]({link})\n\nEst-ce bien la bonne adresse ?",
        "es": "📍 *Dirección encontrada:*\n\n`{addr}`\n\n[🗺️ Ver en OpenStreetMap]({link})\n\n¿Es esta la dirección correcta?",
        "en": "📍 *Address found:*\n\n`{addr}`\n\n[🗺️ View on OpenStreetMap]({link})\n\nIs this the correct address?",
    },
    "address_unverified": {
        "fr": "📍 *Adresse enregistrée :*\n\n`{addr}`\n\n_Lieu non trouvé sur la carte — l'adresse sera utilisée telle quelle._\n\nEst-ce bien correct ?",
        "es": "📍 *Dirección registrada:*\n\n`{addr}`\n\n_Lugar no encontrado en el mapa — se usará tal cual._\n\n¿Es correcto?",
        "en": "📍 *Address saved:*\n\n`{addr}`\n\n_Location not found on map — address will be used as entered._\n\nIs this correct?",
    },
    "address_service_down": {
        "fr": "⚠️ Service de géolocalisation indisponible. Votre adresse a été enregistrée telle quelle :\n\n`{addr}`\n\nEst-ce bien la bonne adresse ?",
        "es": "⚠️ Servicio de geolocalización no disponible. Tu dirección se ha guardado tal cual:\n\n`{addr}`\n\n¿Es esta la dirección correcta?",
        "en": "⚠️ Geolocation service unavailable. Your address has been saved as-is:\n\n`{addr}`\n\nIs this the correct address?",
    },
    "btn_addr_yes": {
        "fr": "✅ Oui, c'est correct !",
        "es": "✅ Sí, es correcta!",
        "en": "✅ Yes, that's correct!",
    },
    "btn_addr_no": {
        "fr": "✏️ Non, modifier",
        "es": "✏️ No, modificar",
        "en": "✏️ No, change it",
    },
    "address_confirmed": {
        "fr": "✅ Adresse confirmée !",
        "es": "✅ ¡Dirección confirmada!",
        "en": "✅ Address confirmed!",
    },
    "enter_new_address": {
        "fr": "✏️ *Nouvelle adresse de livraison* :\n_Rue + ville, code postal, ou nom d'un lieu (Tour Eiffel, Moulin Rouge…)_",
        "es": "✏️ *Nueva dirección de entrega* :\n_Calle, código postal o nombre de un lugar (Sagrada Família…)_",
        "en": "✏️ *New delivery address* :\n_Street, postcode, or landmark name (Eiffel Tower, Big Ben…)_",
    },

    # ── Selfie ─────────────────────────────────────────────────────────────
    "selfie_webapp": {
        "fr": "📸 *Dernière étape :*\n\nAppuyez sur le bouton pour ouvrir la caméra *en direct* dans Telegram.\n\n_Votre visage sera vérifié automatiquement._",
        "es": "📸 *Último paso:*\n\nPulsa el botón para abrir la cámara *en directo* en Telegram.\n\n_Tu rostro se verificará automáticamente._",
        "en": "📸 *Last step:*\n\nPress the button to open the *live* camera in Telegram.\n\n_Your face will be checked automatically._",
    },
    "btn_take_selfie": {
        "fr": "📸 Prendre mon selfie en direct",
        "es": "📸 Tomar mi selfie en directo",
        "en": "📸 Take live selfie",
    },
    "selfie_fallback": {
        "fr": "📸 *Dernière étape :* Envoyez un *selfie* pour valider votre commande.",
        "es": "📸 *Último paso:* Envía un *selfie* para validar tu pedido.",
        "en": "📸 *Last step:* Send a *selfie* to validate your order.",
    },
    "selfie_use_button": {
        "fr": "📱 Utilisez le bouton *« Prendre mon selfie en direct »* pour ouvrir la caméra.",
        "es": "📱 Usa el botón *« Tomar mi selfie en directo »* para abrir la cámara.",
        "en": "📱 Use the *« Take live selfie »* button to open the camera.",
    },
    "selfie_need_photo": {
        "fr": "❌ Veuillez envoyer une *photo* (selfie) pour continuer.",
        "es": "❌ Por favor, envía una *foto* (selfie) para continuar.",
        "en": "❌ Please send a *photo* (selfie) to continue.",
    },
    "selfie_ok": {
        "fr": "✅ *Selfie validé !* 📸",
        "es": "✅ *¡Selfie validado!* 📸",
        "en": "✅ *Selfie validated!* 📸",
    },
    "selfie_error": {
        "fr": "❌ Erreur lors du selfie. Réessayez.",
        "es": "❌ Error con el selfie. Inténtalo de nuevo.",
        "en": "❌ Selfie error. Try again.",
    },

    # ── Récap & confirmation ───────────────────────────────────────────────
    "summary_title": {
        "fr": "📋 *Récapitulatif de la commande :*\n",
        "es": "📋 *Resumen del pedido:*\n",
        "en": "📋 *Order summary:*\n",
    },
    "summary_payment": {
        "fr": "💳 Paiement : {p}",
        "es": "💳 Pago: {p}",
        "en": "💳 Payment: {p}",
    },
    "summary_address": {
        "fr": "📍 Livraison : `{a}`",
        "es": "📍 Entrega: `{a}`",
        "en": "📍 Delivery: `{a}`",
    },
    "summary_city": {
        "fr": "🏙️ Ville : {c} ({co})",
        "es": "🏙️ Ciudad: {c} ({co})",
        "en": "🏙️ City: {c} ({co})",
    },
    "btn_confirm_order": {
        "fr": "✅ Confirmer la commande",
        "es": "✅ Confirmar pedido",
        "en": "✅ Confirm order",
    },
    "btn_cancel": {
        "fr": "❌ Annuler",
        "es": "❌ Cancelar",
        "en": "❌ Cancel",
    },
    "order_cancelled": {
        "fr": "❌ Commande annulée.\n\nTapez /start pour recommencer.",
        "es": "❌ Pedido cancelado.\n\nEscribe /start para empezar de nuevo.",
        "en": "❌ Order cancelled.\n\nType /start to start again.",
    },
    "order_confirmed": {
        "fr": "🎉 *Commande confirmée !*\n\n📦 N° de commande : `{id}`\n\nVotre commande est en cours de traitement. Nous vous contacterons pour la livraison. Merci ! 🙏\n\nQue souhaitez-vous faire ?",
        "es": "🎉 *¡Pedido confirmado!*\n\n📦 N° de pedido: `{id}`\n\nTu pedido se está procesando. Te contactaremos para la entrega. ¡Gracias! 🙏\n\n¿Qué deseas hacer?",
        "en": "🎉 *Order confirmed!*\n\n📦 Order #: `{id}`\n\nYour order is being processed. We'll contact you for delivery. Thank you! 🙏\n\nWhat would you like to do?",
    },

    # ── Gestion post-commande ──────────────────────────────────────────────
    "manage_cancel": {
        "fr": "❌ Annuler la commande",
        "es": "❌ Cancelar el pedido",
        "en": "❌ Cancel order",
    },
    "manage_address": {
        "fr": "✏️ Modifier l'adresse",
        "es": "✏️ Modificar la dirección",
        "en": "✏️ Change address",
    },
    "manage_cart": {
        "fr": "🛒 Modifier le panier",
        "es": "🛒 Modificar el carrito",
        "en": "🛒 Edit cart",
    },
    "confirm_cancel": {
        "fr": "⚠️ Êtes-vous sûr de vouloir *annuler* votre commande ?",
        "es": "⚠️ ¿Seguro que quieres *cancelar* tu pedido?",
        "en": "⚠️ Are you sure you want to *cancel* your order?",
    },
    "btn_yes_cancel": {
        "fr": "✅ Oui, annuler",
        "es": "✅ Sí, cancelar",
        "en": "✅ Yes, cancel",
    },
    "btn_keep_order": {
        "fr": "◀️ Non, garder la commande",
        "es": "◀️ No, mantener el pedido",
        "en": "◀️ No, keep order",
    },
    "order_cancelled_final": {
        "fr": "✅ Votre commande a été annulée.\n\nTapez /start pour recommencer.",
        "es": "✅ Tu pedido ha sido cancelado.\n\nEscribe /start para empezar de nuevo.",
        "en": "✅ Your order has been cancelled.\n\nType /start to start again.",
    },
    "order_kept": {
        "fr": "✅ Commande maintenue. Que souhaitez-vous faire ?",
        "es": "✅ Pedido mantenido. ¿Qué deseas hacer?",
        "en": "✅ Order kept. What would you like to do?",
    },
    "address_updated": {
        "fr": "✅ Adresse mise à jour !\n\n`{a}`\n\nQue souhaitez-vous faire ?",
        "es": "✅ ¡Dirección actualizada!\n\n`{a}`\n\n¿Qué deseas hacer?",
        "en": "✅ Address updated!\n\n`{a}`\n\nWhat would you like to do?",
    },
    "cart_updated": {
        "fr": "✅ Panier mis à jour !\n\n{s}\n\nQue souhaitez-vous faire ?",
        "es": "✅ ¡Carrito actualizado!\n\n{s}\n\n¿Qué deseas hacer?",
        "en": "✅ Cart updated!\n\n{s}\n\nWhat would you like to do?",
    },

    # ── Suivi (owner → client) ─────────────────────────────────────────────
    "status_confirmed": {
        "fr": "✅ *Commande confirmée !*\n\n📦 N° `{id}`\n\nVotre commande a été confirmée et est en préparation. Nous vous tiendrons informé.",
        "es": "✅ *¡Pedido confirmado!*\n\n📦 N° `{id}`\n\nTu pedido ha sido confirmado y está en preparación. Te mantendremos informado.",
        "en": "✅ *Order confirmed!*\n\n📦 # `{id}`\n\nYour order has been confirmed and is being prepared. We'll keep you updated.",
    },
    "status_delivering": {
        "fr": "🚚 *Votre commande est en route !*\n\n📦 N° `{id}`\n\nVotre livreur est en chemin. Restez disponible à l'adresse indiquée.",
        "es": "🚚 *¡Tu pedido está en camino!*\n\n📦 N° `{id}`\n\nTu repartidor está en camino. Mantente disponible en la dirección indicada.",
        "en": "🚚 *Your order is on the way!*\n\n📦 # `{id}`\n\nYour driver is on the way. Please stay at the indicated address.",
    },
    "status_delivered": {
        "fr": "📦 *Commande livrée !*\n\n📦 N° `{id}`\n\nVotre commande a été livrée. Merci de votre confiance ! 🙏",
        "es": "📦 *¡Pedido entregado!*\n\n📦 N° `{id}`\n\nTu pedido ha sido entregado. ¡Gracias por tu confianza! 🙏",
        "en": "📦 *Order delivered!*\n\n📦 # `{id}`\n\nYour order has been delivered. Thank you for your trust! 🙏",
    },
    "status_cancelled_owner": {
        "fr": "❌ *Commande annulée*\n\n📦 N° `{id}`\n\nVotre commande a été annulée. Pour plus d'informations, contactez-nous.",
        "es": "❌ *Pedido cancelado*\n\n📦 N° `{id}`\n\nTu pedido ha sido cancelado. Para más información, contáctanos.",
        "en": "❌ *Order cancelled*\n\n📦 # `{id}`\n\nYour order has been cancelled. Contact us for more info.",
    },

    # ── Selfie bloqué / retry (C2, M2) ────────────────────────────────────────
    "selfie_photo_blocked": {
        "fr": "📱 Veuillez utiliser le bouton *selfie en direct* — les photos directes ne sont pas acceptées.",
        "es": "📱 Por favor, usa el botón de *selfie en directo* — no se aceptan fotos directas.",
        "en": "📱 Please use the *live selfie* button — direct photos are not accepted.",
    },

    # ── Commande minimum ───────────────────────────────────────────────────────
    # Dans le texte du panier — type montant
    "min_order_required": {
        "fr": "⚠️ *Commande minimum : {min} {cur}*\n_Il manque {diff} {cur} pour atteindre le minimum._",
        "es": "⚠️ *Pedido mínimo: {min} {cur}*\n_Faltan {diff} {cur} para alcanzar el mínimo._",
        "en": "⚠️ *Minimum order: {min} {cur}*\n_{diff} {cur} more needed to reach the minimum._",
    },
    # Dans le texte du panier — type quantité articles
    "min_order_qty_required": {
        "fr": "⚠️ *Minimum {min} article(s)*\n_Il vous en manque {diff} — ajoutez-en dans le menu._",
        "es": "⚠️ *Mínimo {min} artículo(s)*\n_Te faltan {diff} — agrégalos en el menú._",
        "en": "⚠️ *Minimum {min} item(s)*\n_{diff} more needed — add them from the menu._",
    },
    # Note dans le titre du menu
    "min_note_amount": {
        "fr": "📋 Commande minimum : {min} {cur}",
        "es": "📋 Pedido mínimo: {min} {cur}",
        "en": "📋 Minimum order: {min} {cur}",
    },
    "min_note_qty": {
        "fr": "📋 Minimum {min} articles",
        "es": "📋 Mínimo {min} artículos",
        "en": "📋 Minimum {min} items",
    },

    # ── Blacklist ──────────────────────────────────────────────────────────────
    "blacklisted": {
        "fr": "⛔ Vous n'êtes plus autorisé à utiliser ce service.",
        "es": "⛔ Ya no está autorizado a usar este servicio.",
        "en": "⛔ You are no longer allowed to use this service.",
    },

    # ── Historique commandes (/orders) ─────────────────────────────────────────
    "orders_title": {
        "fr": "📋 *Vos {n} dernière(s) commande(s) :*\n",
        "es": "📋 *Sus {n} último(s) pedido(s):*\n",
        "en": "📋 *Your last {n} order(s):*\n",
    },
    "orders_empty": {
        "fr": "📭 Vous n'avez pas encore de commandes.",
        "es": "📭 Aún no tienes pedidos.",
        "en": "📭 You have no orders yet.",
    },

    # ── Note après livraison ───────────────────────────────────────────────────
    "rating_request": {
        "fr": "⭐ *Comment s'est passée votre livraison ?*\n\n📦 N° `{id}`\n\nAppuyez sur une note :",
        "es": "⭐ *¿Cómo fue tu entrega?*\n\n📦 N° `{id}`\n\nPulsa una valoración:",
        "en": "⭐ *How was your delivery?*\n\n📦 #{id}\n\nTap a rating:",
    },
    "rating_saved": {
        "fr": "{stars} Merci pour votre avis ! Votre note de *{score}/5* a bien été enregistrée.",
        "es": "{stars} ¡Gracias por tu opinión! Tu nota *{score}/5* ha sido guardada.",
        "en": "{stars} Thank you for your feedback! Your rating *{score}/5* has been saved.",
    },

    # ── Bon de commande automatique (envoyé au client à la confirmation) ─────
    "receipt_title": {
        "fr": "🧾 *Bon de commande — N° {id}*",
        "es": "🧾 *Albarán — N° {id}*",
        "en": "🧾 *Order Receipt — #{id}*",
    },
    "receipt_items": {
        "fr": "🛒 *Articles :*",
        "es": "🛒 *Artículos:*",
        "en": "🛒 *Items:*",
    },
    "receipt_address": {
        "fr": "📍 *Adresse de livraison :*",
        "es": "📍 *Dirección de entrega:*",
        "en": "📍 *Delivery address:*",
    },
    "receipt_thanks": {
        "fr": "_Merci pour votre commande ! Nous vous contacterons très prochainement pour la livraison._ 🙏",
        "es": "_¡Gracias por tu pedido! Nos pondremos en contacto contigo muy pronto._ 🙏",
        "en": "_Thank you for your order! We will contact you very soon for delivery._ 🙏",
    },

    # ── Divers ─────────────────────────────────────────────────────────────
    "restart_hint": {
        "fr": "↩️ Appuyez sur /start pour passer une nouvelle commande.",
        "es": "↩️ Pulsa /start para hacer un nuevo pedido.",
        "en": "↩️ Press /start to place a new order.",
    },
    "session_timeout": {
        "fr": "⏱️ Votre session a expiré (inactif 30 min). Tapez /start pour recommencer.",
        "es": "⏱️ Tu sesión ha caducado (inactivo 30 min). Escribe /start para empezar de nuevo.",
        "en": "⏱️ Your session expired (30 min inactive). Type /start to start again.",
    },
    "generic_error": {
        "fr": "❌ Erreur, réessayez.",
        "es": "❌ Error, vuelve a intentarlo.",
        "en": "❌ Error, try again.",
    },
}


def t(key: str, lang: str = "fr", **kwargs) -> str:
    """Retourne la traduction. Fallback : français → clé brute."""
    entry = T.get(key, {})
    text  = entry.get(lang) or entry.get("fr") or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    return text

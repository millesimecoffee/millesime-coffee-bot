# translations.py — Toutes les chaînes visibles par le client en FR / ES / EN / RU
# Ajouter une nouvelle clé : T["ma_cle"] = {"fr": ..., "es": ..., "en": ..., "ru": ...}
#
# LANGUES est la liste de référence : le reste du projet s'y rapporte plutôt
# que de recopier les codes. Sans ça, ajouter une langue oblige à retrouver
# chaque endroit où la liste avait été réécrite à la main.
LANGUES = ("fr", "es", "en", "ru")

T = {
    # ── Accueil ────────────────────────────────────────────────────────────
    "welcome_title": {
        "fr": "🛍️ *Bienvenue !*",
        "es": "🛍️ *¡Bienvenido!*",
        "en": "🛍️ *Welcome!*",
        "ru": "🛍️ *Добро пожаловать!*",
    },
    "welcome_body": {
        "fr": "Appuyez sur le bouton ci-dessous pour accéder au catalogue.",
        "es": "Pulsa el botón de abajo para acceder al catálogo.",
        "en": "Press the button below to access the catalog.",
        "ru": "Нажмите кнопку ниже, чтобы открыть каталог.",
    },
    "btn_open_catalog": {
        "fr": "🛍️ Accéder au catalogue",
        "es": "🛍️ Acceder al catálogo",
        "en": "🛍️ Open catalog",
        "ru": "🛍️ Открыть каталог",
    },

    # ── Langue ─────────────────────────────────────────────────────────────
    "choose_language": {
        "fr": "🌐 *Choisissez votre langue :*",
        "es": "🌐 *Elige tu idioma:*",
        "en": "🌐 *Choose your language:*",
        "ru": "🌐 *Выберите язык:*",
    },

    # ── Mot de passe ───────────────────────────────────────────────────────
    "ask_password": {
        "fr": "🔐 Pour accéder au service, entrez le *mot de passe* :",
        "es": "🔐 Para acceder al servicio, introduce la *contraseña*:",
        "en": "🔐 To access the service, enter the *password*:",
        "ru": "🔐 Чтобы получить доступ, введите *пароль*:",
    },
    "wrong_password": {
        "fr": "❌ Mot de passe incorrect. Tentative {n}/3.",
        "es": "❌ Contraseña incorrecta. Intento {n}/3.",
        "en": "❌ Wrong password. Attempt {n}/3.",
        "ru": "❌ Неверный пароль. Попытка {n}/3.",
    },
    "blocked": {
        "fr": "🚫 Trop de tentatives. Réessayez dans {min} minutes.",
        "es": "🚫 Demasiados intentos. Vuelve a intentarlo en {min} minutos.",
        "en": "🚫 Too many attempts. Try again in {min} minutes.",
        "ru": "🚫 Слишком много попыток. Повторите через {min} мин.",
    },
    "welcome_user": {
        "fr": "✅ *Bienvenue, {name} !* 🎉",
        "es": "✅ *¡Bienvenido, {name}!* 🎉",
        "en": "✅ *Welcome, {name}!* 🎉",
        "ru": "✅ *Добро пожаловать, {name}!* 🎉",
    },
    # Affiché juste après le choix de langue (welcome localisé + demande mot de passe)
    "welcome_after_lang": {
        "fr": "🛍️ *Bienvenue, {name} !* 🎉\n\n🔐 Entrez le *mot de passe* pour accéder au catalogue :",
        "es": "🛍️ *¡Bienvenido, {name}!* 🎉\n\n🔐 Introduce la *contraseña* para acceder al catálogo:",
        "en": "🛍️ *Welcome, {name}!* 🎉\n\n🔐 Enter the *password* to access the catalog:",
        "ru": "🛍️ *Добро пожаловать, {name}!* 🎉\n\n🔐 Введите *пароль*, чтобы открыть каталог:",
    },
    # /help client
    "help_text": {
        "fr": "📖 *Aide*\n\n*Horaires :* 11h00 → 06h00 — tous les jours\n\n*Commandes :*\n/start — Démarrer ou redémarrer\n/status — Voir si le service est ouvert\n/cancel — Annuler la commande en cours\n/skip — Passer l'étape téléphone\n/help — Afficher cette aide\n\n*Flux de commande :*\n1️⃣ Langue\n2️⃣ Mot de passe\n3️⃣ Téléphone (optionnel)\n4️⃣ Pays → Ville\n5️⃣ Sélection des articles\n6️⃣ Paiement → Adresse\n7️⃣ Selfie de vérification\n8️⃣ Confirmation",
        "es": "📖 *Ayuda*\n\n*Horario:* 11:00 → 06:00 — todos los días\n\n*Comandos:*\n/start — Iniciar o reiniciar\n/status — Ver si el servicio está abierto\n/cancel — Cancelar el pedido en curso\n/skip — Omitir el paso del teléfono\n/help — Mostrar esta ayuda\n\n*Flujo del pedido:*\n1️⃣ Idioma\n2️⃣ Contraseña\n3️⃣ Teléfono (opcional)\n4️⃣ País → Ciudad\n5️⃣ Selección de artículos\n6️⃣ Pago → Dirección\n7️⃣ Selfie de verificación\n8️⃣ Confirmación",
        "en": "📖 *Help*\n\n*Hours:* 11:00 → 06:00 — every day\n\n*Commands:*\n/start — Start or restart\n/status — Check if service is open\n/cancel — Cancel current order\n/skip — Skip phone step\n/help — Show this help\n\n*Order flow:*\n1️⃣ Language\n2️⃣ Password\n3️⃣ Phone (optional)\n4️⃣ Country → City\n5️⃣ Item selection\n6️⃣ Payment → Address\n7️⃣ Verification selfie\n8️⃣ Confirmation",
        "ru": "📖 *Помощь*\n\n*Часы работы:* 11:00 → 06:00 — ежедневно\n\n*Команды:*\n/start — Начать или перезапустить\n/status — Узнать, открыт ли сервис\n/cancel — Отменить текущий заказ\n/skip — Пропустить шаг с телефоном\n/help — Показать эту справку\n\n*Порядок заказа:*\n1️⃣ Язык\n2️⃣ Пароль\n3️⃣ Телефон (по желанию)\n4️⃣ Страна → Город\n5️⃣ Выбор товаров\n6️⃣ Оплата → Адрес\n7️⃣ Селфи для проверки\n8️⃣ Подтверждение",
    },
    # Statut ouvert / fermé
    "status_open": {
        "fr": "✅ *Service ouvert !*\n\n🕘 Horaires : 11h00 → 06h00\n\nTapez /start pour commander.",
        "es": "✅ *¡Servicio abierto!*\n\n🕘 Horario: 11:00 → 06:00\n\nEscribe /start para pedir.",
        "en": "✅ *Service open!*\n\n🕘 Hours: 11:00 → 06:00\n\nType /start to order.",
        "ru": "✅ *Сервис открыт!*\n\n🕘 Часы работы: 11:00 → 06:00\n\nНапишите /start, чтобы сделать заказ.",
    },
    "status_closed": {
        "fr": "🌙 *Service fermé.*\n\n🕘 Horaires : *11h00 → 06h00* tous les jours.\n\nRevenez à *11h00* !",
        "es": "🌙 *Servicio cerrado.*\n\n🕘 Horario: *11:00 → 06:00* todos los días.\n\n¡Vuelve a las *11:00*!",
        "en": "🌙 *Service closed.*\n\n🕘 Hours: *11:00 → 06:00* every day.\n\nCome back at *11:00 AM*!",
        "ru": "🌙 *Сервис закрыт.*\n\n🕘 Часы работы: *11:00 → 06:00* ежедневно.\n\nВозвращайтесь в *11:00*!",
    },

    # ── Téléphone (M1) ────────────────────────────────────────────────────────
    "phone_request": {
        "fr": "📱 *Étape de sécurité*\n\nPartagez votre numéro pour faciliter les prochaines commandes.\n\n_Optionnel — appuyez sur « Passer » si vous préférez ne pas le partager._",
        "es": "📱 *Paso de seguridad*\n\nComparte tu número para facilitar futuros pedidos.\n\n_Opcional — pulsa «Omitir» si prefieres no compartirlo._",
        "en": "📱 *Security step*\n\nShare your number to make future orders easier.\n\n_Optional — press «Skip» if you prefer not to share._",
        "ru": "📱 *Шаг безопасности*\n\nПоделитесь номером, чтобы следующие заказы оформлялись быстрее.\n\n_Необязательно — нажмите «Пропустить», если не хотите._",
    },
    "btn_share_phone": {
        "fr": "📱 Partager mon numéro",
        "es": "📱 Compartir mi número",
        "en": "📱 Share my number",
        "ru": "📱 Поделиться номером",
    },
    "phone_skip_btn": {
        "fr": "⏭️ Passer",
        "es": "⏭️ Omitir",
        "en": "⏭️ Skip",
        "ru": "⏭️ Пропустить",
    },
    "phone_received": {
        "fr": "✅ Numéro enregistré !",
        "es": "✅ ¡Número registrado!",
        "en": "✅ Number saved!",
        "ru": "✅ Номер сохранён!",
    },
    "phone_skipped": {
        "fr": "👍 Étape passée.",
        "es": "👍 Paso omitido.",
        "en": "👍 Step skipped.",
        "ru": "👍 Шаг пропущен.",
    },

    # ── Pays / Ville ───────────────────────────────────────────────────────
    "choose_country": {
        "fr": "🌍 *Sélectionnez votre pays :*",
        "es": "🌍 *Selecciona tu país:*",
        "en": "🌍 *Select your country:*",
        "ru": "🌍 *Выберите страну:*",
    },
    "choose_city": {
        "fr": "🏙️ *{country}* — Sélectionnez votre ville :",
        "es": "🏙️ *{country}* — Selecciona tu ciudad:",
        "en": "🏙️ *{country}* — Select your city:",
        "ru": "🏙️ *{country}* — Выберите город:",
    },
    "back_countries": {
        "fr": "◀️ Retour aux pays",
        "es": "◀️ Volver a países",
        "en": "◀️ Back to countries",
        "ru": "◀️ Назад к странам",
    },
    "back_cities": {
        "fr": "◀️ Changer de ville",
        "es": "◀️ Cambiar de ciudad",
        "en": "◀️ Change city",
        "ru": "◀️ Сменить город",
    },

    # ── Menu / Panier ──────────────────────────────────────────────────────
    "menu_title": {
        "fr": "🍽️ *Menu — {city}*\n\nSélectionnez vos articles :",
        "es": "🍽️ *Menú — {city}*\n\nSelecciona tus artículos:",
        "en": "🍽️ *Menu — {city}*\n\nSelect your items:",
        "ru": "🍽️ *Меню — {city}*\n\nВыберите товары:",
    },
    "view_cart": {
        "fr": "🛒 Voir panier ({n}) — {total} {cur}",
        "es": "🛒 Ver carrito ({n}) — {total} {cur}",
        "en": "🛒 View cart ({n}) — {total} {cur}",
        "ru": "🛒 Корзина ({n}) — {total} {cur}",
    },
    "cart_title": {
        "fr": "🛒 *Votre panier :*\n",
        "es": "🛒 *Tu carrito:*\n",
        "en": "🛒 *Your cart:*\n",
        "ru": "🛒 *Ваша корзина:*\n",
    },
    "cart_empty": {
        "fr": "Votre panier est vide !",
        "es": "¡Tu carrito está vacío!",
        "en": "Your cart is empty!",
        "ru": "Ваша корзина пуста!",
    },
    "cart_total": {
        "fr": "💰 *Total : {total} {cur}*",
        "es": "💰 *Total: {total} {cur}*",
        "en": "💰 *Total: {total} {cur}*",
        "ru": "💰 *Итого: {total} {cur}*",
    },
    "btn_checkout": {
        "fr": "✅ Passer la commande",
        "es": "✅ Realizar pedido",
        "en": "✅ Place order",
        "ru": "✅ Оформить заказ",
    },
    "btn_continue_shopping": {
        "fr": "◀️ Continuer les achats",
        "es": "◀️ Seguir comprando",
        "en": "◀️ Continue shopping",
        "ru": "◀️ Продолжить покупки",
    },
    "btn_validate_changes": {
        "fr": "✅ Valider les modifications",
        "es": "✅ Confirmar los cambios",
        "en": "✅ Confirm changes",
        "ru": "✅ Подтвердить изменения",
    },

    # ── Paiement — écran principal ─────────────────────────────────────────
    "choose_payment": {
        "fr": "💳 *Choisissez votre mode de paiement :*",
        "es": "💳 *Elige tu método de pago:*",
        "en": "💳 *Choose your payment method:*",
        "ru": "💳 *Выберите способ оплаты:*",
    },
    "back_cart": {
        "fr": "◀️ Retour au panier",
        "es": "◀️ Volver al carrito",
        "en": "◀️ Back to cart",
        "ru": "◀️ Назад в корзину",
    },
    "btn_pay_back": {
        "fr": "◀️ Retour aux paiements",
        "es": "◀️ Volver a los pagos",
        "en": "◀️ Back to payments",
        "ru": "◀️ Назад к оплате",
    },
    # Boutons des 3 méthodes
    "pay_btn_cash":     {"fr": "💵 Cash",              "es": "💵 Efectivo",       "en": "💵 Cash", "ru": "💵 Наличные"},
    "pay_btn_link":     {"fr": "🔗 Lien de paiement",  "es": "🔗 Enlace de pago", "en": "🔗 Payment link", "ru": "🔗 Ссылка на оплату"},
    "pay_btn_crypto":   {"fr": "₿ Crypto",             "es": "₿ Cripto",          "en": "₿ Crypto", "ru": "₿ Криптовалюта"},
    # ── Cash → devise ─────────────────────────────────────────────────────
    "pay_choose_currency": {
        "fr": "💵 *Cash — Choisissez votre devise :*",
        "es": "💵 *Efectivo — Elige tu divisa:*",
        "en": "💵 *Cash — Choose your currency:*",
        "ru": "💵 *Наличные — Выберите валюту:*",
    },
    "pay_cash_confirmed": {
        "fr": "✅ Paiement *cash* en *{cur}* noté.\n\n📍 *Adresse de livraison* :\n_Rue + ville, code postal, ou nom d'un lieu (Tour Eiffel, Moulin Rouge…)_",
        "es": "✅ Pago *efectivo* en *{cur}* registrado.\n\n📍 *Dirección de entrega* :\n_Calle, código postal o nombre de un lugar (Sagrada Família…)_",
        "en": "✅ *Cash* in *{cur}* noted.\n\n📍 *Delivery address* :\n_Street, postcode, or landmark name (Eiffel Tower, Big Ben…)_",
        "ru": "✅ *Наличные* в *{cur}* приняты.\n\n📍 *Адрес доставки* :\n_Улица, индекс или название ориентира (Эйфелева башня, Биг-Бен…)_",
    },
    # ── Lien de paiement ──────────────────────────────────────────────────
    "pay_link_info": {
        "fr": "🔗 *Lien de paiement*\n\nCliquez sur le lien ci-dessous :\n\n{link}\n\n_Une fois le paiement effectué, appuyez sur ✅ ci-dessous._",
        "es": "🔗 *Enlace de pago*\n\nHaz clic en el enlace:\n\n{link}\n\n_Una vez pagado, pulsa ✅ abajo._",
        "en": "🔗 *Payment link*\n\nClick the link below:\n\n{link}\n\n_Once paid, press ✅ below._",
        "ru": "🔗 *Ссылка на оплату*\n\nНажмите на ссылку ниже:\n\n{link}\n\n_После оплаты нажмите ✅ ниже._",
    },
    "pay_link_not_configured": {
        "fr": "⚠️ Lien de paiement non encore configuré. Choisissez un autre mode.",
        "es": "⚠️ Enlace de pago aún no configurado. Elige otro método.",
        "en": "⚠️ Payment link not configured yet. Please choose another method.",
        "ru": "⚠️ Ссылка на оплату ещё не настроена. Выберите другой способ.",
    },
    "btn_i_paid": {
        "fr": "✅ J'ai effectué le paiement",
        "es": "✅ He realizado el pago",
        "en": "✅ I have paid",
        "ru": "✅ Я оплатил",
    },
    "pay_link_confirmed": {
        "fr": "✅ Paiement via lien noté.\n\n📍 *Adresse de livraison* :\n_Rue + ville, code postal, ou nom d'un lieu (Tour Eiffel, Moulin Rouge…)_",
        "es": "✅ Pago por enlace registrado.\n\n📍 *Dirección de entrega* :\n_Calle, código postal o nombre de un lugar (Sagrada Família…)_",
        "en": "✅ Link payment noted.\n\n📍 *Delivery address* :\n_Street, postcode, or landmark name (Eiffel Tower, Big Ben…)_",
        "ru": "✅ Оплата по ссылке принята.\n\n📍 *Адрес доставки* :\n_Улица, индекс или название ориентира (Эйфелева башня, Биг-Бен…)_",
    },
    # ── Crypto ────────────────────────────────────────────────────────────
    "pay_crypto_choose": {
        "fr": "₿ *Paiement en crypto*\n\nChoisissez votre cryptomonnaie :",
        "es": "₿ *Pago en cripto*\n\nElige tu criptomoneda:",
        "en": "₿ *Crypto payment*\n\nChoose your cryptocurrency:",
        "ru": "₿ *Оплата криптовалютой*\n\nВыберите криптовалюту:",
    },
    "pay_crypto_address": {
        "fr": "{icon} *Paiement {name}*\n\nEnvoyez le montant exact à cette adresse :\n\n```\n{address}\n```\n_(appuyez pour copier)_\n\n_Une fois envoyé, appuyez sur ✅ ci-dessous._",
        "es": "{icon} *Pago {name}*\n\nEnvía el importe exacto a esta dirección:\n\n```\n{address}\n```\n_(pulsa para copiar)_\n\n_Una vez enviado, pulsa ✅ abajo._",
        "en": "{icon} *{name} Payment*\n\nSend the exact amount to:\n\n```\n{address}\n```\n_(tap to copy)_\n\n_Once sent, press ✅ below._",
        "ru": "{icon} *Оплата {name}*\n\nОтправьте точную сумму на:\n\n```\n{address}\n```\n_(нажмите, чтобы скопировать)_\n\n_После отправки нажмите ✅ ниже._",
    },
    "pay_crypto_not_configured": {
        "fr": "⚠️ Adresse {name} non configurée. Choisissez un autre mode.",
        "es": "⚠️ Dirección {name} no configurada. Elige otro método.",
        "en": "⚠️ {name} address not configured. Please choose another method.",
        "ru": "⚠️ Адрес {name} не настроен. Выберите другой способ.",
    },
    "btn_crypto_sent": {
        "fr": "✅ J'ai envoyé la crypto",
        "es": "✅ He enviado la cripto",
        "en": "✅ I have sent the crypto",
        "ru": "✅ Я отправил криптовалюту",
    },
    "btn_copy_address": {
        "fr": "📋 Copier l'adresse",
        "es": "📋 Copiar la dirección",
        "en": "📋 Copy address",
        "ru": "📋 Скопировать адрес",
    },
    "pay_crypto_caption": {
        "fr": "{icon} *Paiement {name}*\n\n📲 *Scannez le QR* ou appuyez sur 📋 pour copier l'adresse :\n\n`{address}`\n\n_Une fois envoyé, appuyez sur ✅ ci-dessous._",
        "es": "{icon} *Pago {name}*\n\n📲 *Escanea el QR* o pulsa 📋 para copiar la dirección:\n\n`{address}`\n\n_Una vez enviado, pulsa ✅ abajo._",
        "en": "{icon} *{name} Payment*\n\n📲 *Scan the QR code* or tap 📋 to copy the address:\n\n`{address}`\n\n_Once sent, press ✅ below._",
        "ru": "{icon} *Оплата {name}*\n\n📲 *Отсканируйте QR-код* или нажмите 📋, чтобы скопировать адрес:\n\n`{address}`\n\n_После отправки нажмите ✅ ниже._",
    },
    "pay_crypto_confirmed": {
        "fr": "✅ Paiement *{name}* noté.\n\n📍 *Adresse de livraison* :\n_Rue + ville, code postal, ou nom d'un lieu (Tour Eiffel, Moulin Rouge…)_",
        "es": "✅ Pago *{name}* registrado.\n\n📍 *Dirección de entrega* :\n_Calle, código postal o nombre de un lugar (Sagrada Família…)_",
        "en": "✅ *{name}* payment noted.\n\n📍 *Delivery address* :\n_Street, postcode, or landmark name (Eiffel Tower, Big Ben…)_",
        "ru": "✅ Оплата *{name}* принята.\n\n📍 *Адрес доставки* :\n_Улица, индекс или название ориентира (Эйфелева башня, Биг-Бен…)_",
    },
    # Compatibilité — résumé commande
    "payment_selected": {
        "fr": "✅ Mode de paiement : *{p}*\n\n📍 *Adresse de livraison* :\n_Rue + ville, code postal, ou nom d'un lieu (Tour Eiffel, Moulin Rouge…)_",
        "es": "✅ Método de pago: *{p}*\n\n📍 *Dirección de entrega* :\n_Calle, código postal o nombre de un lugar (Sagrada Família…)_",
        "en": "✅ Payment: *{p}*\n\n📍 *Delivery address* :\n_Street, postcode, or landmark name (Eiffel Tower, Big Ben…)_",
        "ru": "✅ Оплата: *{p}*\n\n📍 *Адрес доставки* :\n_Улица, индекс или название ориентира (Эйфелева башня, Биг-Бен…)_",
    },

    # ── Adresse ────────────────────────────────────────────────────────────
    "searching_address": {
        "fr": "🔍 Recherche de l'adresse…",
        "es": "🔍 Buscando la dirección…",
        "en": "🔍 Searching address…",
        "ru": "🔍 Ищем адрес…",
    },
    "address_found": {
        "fr": "📍 *Adresse trouvée :*\n\n`{addr}`\n\n[🗺️ Voir sur OpenStreetMap]({link})\n\nEst-ce bien la bonne adresse ?",
        "es": "📍 *Dirección encontrada:*\n\n`{addr}`\n\n[🗺️ Ver en OpenStreetMap]({link})\n\n¿Es esta la dirección correcta?",
        "en": "📍 *Address found:*\n\n`{addr}`\n\n[🗺️ View on OpenStreetMap]({link})\n\nIs this the correct address?",
        "ru": "📍 *Адрес найден:*\n\n`{addr}`\n\n[🗺️ Посмотреть на OpenStreetMap]({link})\n\nЭто верный адрес?",
    },
    "address_unverified": {
        "fr": "📍 *Adresse enregistrée :*\n\n`{addr}`\n\n_Lieu non trouvé sur la carte — l'adresse sera utilisée telle quelle._\n\nEst-ce bien correct ?",
        "es": "📍 *Dirección registrada:*\n\n`{addr}`\n\n_Lugar no encontrado en el mapa — se usará tal cual._\n\n¿Es correcto?",
        "en": "📍 *Address saved:*\n\n`{addr}`\n\n_Location not found on map — address will be used as entered._\n\nIs this correct?",
        "ru": "📍 *Адрес сохранён:*\n\n`{addr}`\n\n_Место не найдено на карте — адрес будет использован как есть._\n\nВсё верно?",
    },
    "address_service_down": {
        "fr": "⚠️ Service de géolocalisation indisponible. Votre adresse a été enregistrée telle quelle :\n\n`{addr}`\n\nEst-ce bien la bonne adresse ?",
        "es": "⚠️ Servicio de geolocalización no disponible. Tu dirección se ha guardado tal cual:\n\n`{addr}`\n\n¿Es esta la dirección correcta?",
        "en": "⚠️ Geolocation service unavailable. Your address has been saved as-is:\n\n`{addr}`\n\nIs this the correct address?",
        "ru": "⚠️ Сервис геолокации недоступен. Ваш адрес сохранён как есть:\n\n`{addr}`\n\nЭто верный адрес?",
    },
    "btn_addr_yes": {
        "fr": "✅ Oui, c'est correct !",
        "es": "✅ Sí, es correcta!",
        "en": "✅ Yes, that's correct!",
        "ru": "✅ Да, всё верно!",
    },
    "btn_addr_no": {
        "fr": "✏️ Non, modifier",
        "es": "✏️ No, modificar",
        "en": "✏️ No, change it",
        "ru": "✏️ Нет, изменить",
    },
    "address_confirmed": {
        "fr": "✅ Adresse confirmée !",
        "es": "✅ ¡Dirección confirmada!",
        "en": "✅ Address confirmed!",
        "ru": "✅ Адрес подтверждён!",
    },
    "enter_new_address": {
        "fr": "✏️ *Nouvelle adresse de livraison* :\n_Rue + ville, code postal, ou nom d'un lieu (Tour Eiffel, Moulin Rouge…)_",
        "es": "✏️ *Nueva dirección de entrega* :\n_Calle, código postal o nombre de un lugar (Sagrada Família…)_",
        "en": "✏️ *New delivery address* :\n_Street, postcode, or landmark name (Eiffel Tower, Big Ben…)_",
        "ru": "✏️ *Новый адрес доставки* :\n_Улица, индекс или название ориентира (Эйфелева башня, Биг-Бен…)_",
    },

    # ── Selfie ─────────────────────────────────────────────────────────────
    "selfie_webapp": {
        "fr": "📸 *Dernière étape :*\n\nAppuyez sur le bouton pour ouvrir la caméra *en direct* dans Telegram.\n\n_Votre visage sera vérifié automatiquement._",
        "es": "📸 *Último paso:*\n\nPulsa el botón para abrir la cámara *en directo* en Telegram.\n\n_Tu rostro se verificará automáticamente._",
        "en": "📸 *Last step:*\n\nPress the button to open the *live* camera in Telegram.\n\n_Your face will be checked automatically._",
        "ru": "📸 *Последний шаг:*\n\nНажмите кнопку, чтобы открыть камеру *в прямом эфире* в Telegram.\n\n_Ваше лицо будет проверено автоматически._",
    },
    "btn_take_selfie": {
        "fr": "📸 Prendre mon selfie en direct",
        "es": "📸 Tomar mi selfie en directo",
        "en": "📸 Take live selfie",
        "ru": "📸 Сделать селфи",
    },
    "selfie_fallback": {
        "fr": "📸 *Dernière étape :* Envoyez un *selfie* pour valider votre commande.",
        "es": "📸 *Último paso:* Envía un *selfie* para validar tu pedido.",
        "en": "📸 *Last step:* Send a *selfie* to validate your order.",
        "ru": "📸 *Последний шаг:* отправьте *селфи*, чтобы подтвердить заказ.",
    },
    "selfie_use_button": {
        "fr": "📱 Utilisez le bouton *« Prendre mon selfie en direct »* pour ouvrir la caméra.",
        "es": "📱 Usa el botón *« Tomar mi selfie en directo »* para abrir la cámara.",
        "en": "📱 Use the *« Take live selfie »* button to open the camera.",
        "ru": "📱 Используйте кнопку *«Сделать селфи»*, чтобы открыть камеру.",
    },
    "selfie_need_photo": {
        "fr": "❌ Veuillez envoyer une *photo* (selfie) pour continuer.",
        "es": "❌ Por favor, envía una *foto* (selfie) para continuar.",
        "en": "❌ Please send a *photo* (selfie) to continue.",
        "ru": "❌ Пожалуйста, отправьте *фото* (селфи), чтобы продолжить.",
    },
    "selfie_ok": {
        "fr": "✅ *Selfie validé !* 📸",
        "es": "✅ *¡Selfie validado!* 📸",
        "en": "✅ *Selfie validated!* 📸",
        "ru": "✅ *Селфи принято!* 📸",
    },
    "selfie_error": {
        "fr": "❌ Erreur lors du selfie. Réessayez.",
        "es": "❌ Error con el selfie. Inténtalo de nuevo.",
        "en": "❌ Selfie error. Try again.",
        "ru": "❌ Ошибка селфи. Попробуйте ещё раз.",
    },

    # ── Récap & confirmation ───────────────────────────────────────────────
    "summary_title": {
        "fr": "📋 *Récapitulatif de la commande :*\n",
        "es": "📋 *Resumen del pedido:*\n",
        "en": "📋 *Order summary:*\n",
        "ru": "📋 *Сводка заказа:*\n",
    },
    "summary_payment": {
        "fr": "💳 Paiement : {p}",
        "es": "💳 Pago: {p}",
        "en": "💳 Payment: {p}",
        "ru": "💳 Оплата: {p}",
    },
    "summary_address": {
        "fr": "📍 Livraison : `{a}`",
        "es": "📍 Entrega: `{a}`",
        "en": "📍 Delivery: `{a}`",
        "ru": "📍 Доставка: `{a}`",
    },
    "summary_city": {
        "fr": "🏙️ Ville : {c} ({co})",
        "es": "🏙️ Ciudad: {c} ({co})",
        "en": "🏙️ City: {c} ({co})",
        "ru": "🏙️ Город: {c} ({co})",
    },
    "btn_confirm_order": {
        "fr": "✅ Confirmer la commande",
        "es": "✅ Confirmar pedido",
        "en": "✅ Confirm order",
        "ru": "✅ Подтвердить заказ",
    },
    "btn_cancel": {
        "fr": "❌ Annuler",
        "es": "❌ Cancelar",
        "en": "❌ Cancel",
        "ru": "❌ Отменить",
    },
    "order_cancelled": {
        "fr": "❌ Commande annulée.\n\nTapez /start pour recommencer.",
        "es": "❌ Pedido cancelado.\n\nEscribe /start para empezar de nuevo.",
        "en": "❌ Order cancelled.\n\nType /start to start again.",
        "ru": "❌ Заказ отменён.\n\nНапишите /start, чтобы начать заново.",
    },
    "order_confirmed": {
        "fr": "🎉 *Commande confirmée !*\n\n📦 N° de commande : `{id}`\n\nVotre commande est en cours de traitement. Nous vous contacterons pour la livraison. Merci ! 🙏\n\nQue souhaitez-vous faire ?",
        "es": "🎉 *¡Pedido confirmado!*\n\n📦 N° de pedido: `{id}`\n\nTu pedido se está procesando. Te contactaremos para la entrega. ¡Gracias! 🙏\n\n¿Qué deseas hacer?",
        "en": "🎉 *Order confirmed!*\n\n📦 Order #: `{id}`\n\nYour order is being processed. We'll contact you for delivery. Thank you! 🙏\n\nWhat would you like to do?",
        "ru": "🎉 *Заказ подтверждён!*\n\n📦 Номер заказа: `{id}`\n\nВаш заказ в обработке. Мы свяжемся с вами для доставки. Спасибо! 🙏\n\nЧто вы хотите сделать?",
    },

    # ── Gestion post-commande ──────────────────────────────────────────────
    "manage_cancel": {
        "fr": "❌ Annuler la commande",
        "es": "❌ Cancelar el pedido",
        "en": "❌ Cancel order",
        "ru": "❌ Отменить заказ",
    },
    "manage_address": {
        "fr": "✏️ Modifier l'adresse",
        "es": "✏️ Modificar la dirección",
        "en": "✏️ Change address",
        "ru": "✏️ Изменить адрес",
    },
    "manage_cart": {
        "fr": "🛒 Modifier le panier",
        "es": "🛒 Modificar el carrito",
        "en": "🛒 Edit cart",
        "ru": "🛒 Изменить корзину",
    },
    "confirm_cancel": {
        "fr": "⚠️ Êtes-vous sûr de vouloir *annuler* votre commande ?",
        "es": "⚠️ ¿Seguro que quieres *cancelar* tu pedido?",
        "en": "⚠️ Are you sure you want to *cancel* your order?",
        "ru": "⚠️ Вы уверены, что хотите *отменить* заказ?",
    },
    "btn_yes_cancel": {
        "fr": "✅ Oui, annuler",
        "es": "✅ Sí, cancelar",
        "en": "✅ Yes, cancel",
        "ru": "✅ Да, отменить",
    },
    "btn_keep_order": {
        "fr": "◀️ Non, garder la commande",
        "es": "◀️ No, mantener el pedido",
        "en": "◀️ No, keep order",
        "ru": "◀️ Нет, оставить заказ",
    },
    "order_cancelled_final": {
        "fr": "✅ Votre commande a été annulée.\n\nTapez /start pour recommencer.",
        "es": "✅ Tu pedido ha sido cancelado.\n\nEscribe /start para empezar de nuevo.",
        "en": "✅ Your order has been cancelled.\n\nType /start to start again.",
        "ru": "✅ Ваш заказ отменён.\n\nНапишите /start, чтобы начать заново.",
    },
    "order_kept": {
        "fr": "✅ Commande maintenue. Que souhaitez-vous faire ?",
        "es": "✅ Pedido mantenido. ¿Qué deseas hacer?",
        "en": "✅ Order kept. What would you like to do?",
        "ru": "✅ Заказ сохранён. Что вы хотите сделать?",
    },
    "address_updated": {
        "fr": "✅ Adresse mise à jour !\n\n`{a}`\n\nQue souhaitez-vous faire ?",
        "es": "✅ ¡Dirección actualizada!\n\n`{a}`\n\n¿Qué deseas hacer?",
        "en": "✅ Address updated!\n\n`{a}`\n\nWhat would you like to do?",
        "ru": "✅ Адрес обновлён!\n\n`{a}`\n\nЧто вы хотите сделать?",
    },
    "cart_updated": {
        "fr": "✅ Panier mis à jour !\n\n{s}\n\nQue souhaitez-vous faire ?",
        "es": "✅ ¡Carrito actualizado!\n\n{s}\n\n¿Qué deseas hacer?",
        "en": "✅ Cart updated!\n\n{s}\n\nWhat would you like to do?",
        "ru": "✅ Корзина обновлена!\n\n{s}\n\nЧто вы хотите сделать?",
    },

    # ── Suivi (owner → client) ─────────────────────────────────────────────
    "status_confirmed": {
        "fr": "✅ *Commande confirmée !*\n\n📦 N° `{id}`\n\nVotre commande a été confirmée et est en préparation. Nous vous tiendrons informé.",
        "es": "✅ *¡Pedido confirmado!*\n\n📦 N° `{id}`\n\nTu pedido ha sido confirmado y está en preparación. Te mantendremos informado.",
        "en": "✅ *Order confirmed!*\n\n📦 # `{id}`\n\nYour order has been confirmed and is being prepared. We'll keep you updated.",
        "ru": "✅ *Заказ подтверждён!*\n\n📦 № `{id}`\n\nВаш заказ подтверждён и готовится. Мы будем держать вас в курсе.",
    },
    "status_delivering": {
        "fr": "🚚 *Votre commande est en route !*\n\n📦 N° `{id}`\n\nVotre livreur est en chemin. Restez disponible à l'adresse indiquée.",
        "es": "🚚 *¡Tu pedido está en camino!*\n\n📦 N° `{id}`\n\nTu repartidor está en camino. Mantente disponible en la dirección indicada.",
        "en": "🚚 *Your order is on the way!*\n\n📦 # `{id}`\n\nYour driver is on the way. Please stay at the indicated address.",
        "ru": "🚚 *Ваш заказ в пути!*\n\n📦 № `{id}`\n\nКурьер уже едет. Пожалуйста, будьте по указанному адресу.",
    },
    "status_delivered": {
        "fr": "📦 *Commande livrée !*\n\n📦 N° `{id}`\n\nVotre commande a été livrée. Merci de votre confiance ! 🙏",
        "es": "📦 *¡Pedido entregado!*\n\n📦 N° `{id}`\n\nTu pedido ha sido entregado. ¡Gracias por tu confianza! 🙏",
        "en": "📦 *Order delivered!*\n\n📦 # `{id}`\n\nYour order has been delivered. Thank you for your trust! 🙏",
        "ru": "📦 *Заказ доставлен!*\n\n📦 № `{id}`\n\nВаш заказ доставлен. Спасибо за доверие! 🙏",
    },
    "status_cancelled_owner": {
        "fr": "❌ *Commande annulée*\n\n📦 N° `{id}`\n\nVotre commande a été annulée. Pour plus d'informations, contactez-nous.",
        "es": "❌ *Pedido cancelado*\n\n📦 N° `{id}`\n\nTu pedido ha sido cancelado. Para más información, contáctanos.",
        "en": "❌ *Order cancelled*\n\n📦 # `{id}`\n\nYour order has been cancelled. Contact us for more info.",
        "ru": "❌ *Заказ отменён*\n\n📦 № `{id}`\n\nВаш заказ был отменён. Свяжитесь с нами для подробностей.",
    },

    # ── Selfie bloqué / retry (C2, M2) ────────────────────────────────────────
    "selfie_photo_blocked": {
        "fr": "📱 Veuillez utiliser le bouton *selfie en direct* — les photos directes ne sont pas acceptées.",
        "es": "📱 Por favor, usa el botón de *selfie en directo* — no se aceptan fotos directas.",
        "en": "📱 Please use the *live selfie* button — direct photos are not accepted.",
        "ru": "📱 Пожалуйста, используйте кнопку *селфи в прямом эфире* — обычные фото не принимаются.",
    },

    # ── Commande minimum ───────────────────────────────────────────────────────
    # Dans le texte du panier — type montant
    "min_order_required": {
        "fr": "⚠️ *Commande minimum : {min} {cur}*\n_Il manque {diff} {cur} pour atteindre le minimum._",
        "es": "⚠️ *Pedido mínimo: {min} {cur}*\n_Faltan {diff} {cur} para alcanzar el mínimo._",
        "en": "⚠️ *Minimum order: {min} {cur}*\n_{diff} {cur} more needed to reach the minimum._",
        "ru": "⚠️ *Минимальный заказ: {min} {cur}*\n_Не хватает {diff} {cur} до минимума._",
    },
    # Dans le texte du panier — type quantité articles
    "min_order_qty_required": {
        "fr": "⚠️ *Minimum {min} article(s)*\n_Il vous en manque {diff} — ajoutez-en dans le menu._",
        "es": "⚠️ *Mínimo {min} artículo(s)*\n_Te faltan {diff} — agrégalos en el menú._",
        "en": "⚠️ *Minimum {min} item(s)*\n_{diff} more needed — add them from the menu._",
        "ru": "⚠️ *Минимум {min} товар(ов)*\n_Нужно ещё {diff} — добавьте их из меню._",
    },
    # Note dans le titre du menu
    "min_note_amount": {
        "fr": "📋 Commande minimum : {min} {cur}",
        "es": "📋 Pedido mínimo: {min} {cur}",
        "en": "📋 Minimum order: {min} {cur}",
        "ru": "📋 Минимальный заказ: {min} {cur}",
    },
    "min_note_qty": {
        "fr": "📋 Minimum {min} articles",
        "es": "📋 Mínimo {min} artículos",
        "en": "📋 Minimum {min} items",
        "ru": "📋 Минимум {min} товаров",
    },

    # ── Blacklist ──────────────────────────────────────────────────────────────
    "blacklisted": {
        "fr": "⛔ Vous n'êtes plus autorisé à utiliser ce service.",
        "es": "⛔ Ya no está autorizado a usar este servicio.",
        "en": "⛔ You are no longer allowed to use this service.",
        "ru": "⛔ Вам больше не разрешено пользоваться этим сервисом.",
    },

    # ── Historique commandes (/orders) ─────────────────────────────────────────
    "orders_title": {
        "fr": "📋 *Vos {n} dernière(s) commande(s) :*\n",
        "es": "📋 *Sus {n} último(s) pedido(s):*\n",
        "en": "📋 *Your last {n} order(s):*\n",
        "ru": "📋 *Ваши последние {n} заказ(ов):*\n",
    },
    "orders_empty": {
        "fr": "📭 Vous n'avez pas encore de commandes.",
        "es": "📭 Aún no tienes pedidos.",
        "en": "📭 You have no orders yet.",
        "ru": "📭 У вас пока нет заказов.",
    },

    # ── Note après livraison ───────────────────────────────────────────────────
    "rating_request": {
        "fr": "⭐ *Comment s'est passée votre livraison ?*\n\n📦 N° `{id}`\n\nAppuyez sur une note :",
        "es": "⭐ *¿Cómo fue tu entrega?*\n\n📦 N° `{id}`\n\nPulsa una valoración:",
        "en": "⭐ *How was your delivery?*\n\n📦 # `{id}`\n\nTap a rating:",
        "ru": "⭐ *Как прошла доставка?*\n\n📦 № `{id}`\n\nВыберите оценку:",
    },
    "rating_saved": {
        "fr": "{stars} Merci pour votre avis ! Votre note de *{score}/5* a bien été enregistrée.",
        "es": "{stars} ¡Gracias por tu opinión! Tu nota *{score}/5* ha sido guardada.",
        "en": "{stars} Thank you for your feedback! Your rating *{score}/5* has been saved.",
        "ru": "{stars} Спасибо за отзыв! Ваша оценка *{score}/5* сохранена.",
    },
    "rating_low_followup": {
        "fr": "😕 Désolé que ça ne se soit pas bien passé. *Qu'est-ce qui n'a pas marché ?*",
        "es": "😕 Lamentamos que no haya ido bien. *¿Qué no funcionó?*",
        "en": "😕 Sorry it didn't go well. *What went wrong?*",
        "ru": "😕 Жаль, что всё прошло не так. *Что было не так?*",
    },
    "feedback_btn_slow": {
        "fr": "⏰ Livraison trop longue",
        "es": "⏰ Entrega demasiado lenta",
        "en": "⏰ Delivery too slow",
        "ru": "⏰ Слишком долгая доставка",
    },
    "feedback_btn_wrong": {
        "fr": "❌ Erreur dans ma commande",
        "es": "❌ Error en mi pedido",
        "en": "❌ Wrong order",
        "ru": "❌ Неверный заказ",
    },
    "feedback_btn_cold": {
        "fr": "🥶 Produit pas à bonne température",
        "es": "🥶 Producto frío / mal conservado",
        "en": "🥶 Wrong temperature",
        "ru": "🥶 Не та температура",
    },
    "feedback_btn_quality": {
        "fr": "⚠️ Qualité décevante",
        "es": "⚠️ Calidad decepcionante",
        "en": "⚠️ Disappointing quality",
        "ru": "⚠️ Разочаровало качество",
    },
    "feedback_btn_other": {
        "fr": "📝 Autre",
        "es": "📝 Otro",
        "en": "📝 Other",
        "ru": "📝 Другое",
    },
    "feedback_thanks": {
        "fr": "🙏 Merci ! Votre retour a été transmis. Nous ferons mieux la prochaine fois.",
        "es": "🙏 ¡Gracias! Tu opinión ha sido enviada. Lo haremos mejor la próxima vez.",
        "en": "🙏 Thanks! Your feedback was sent. We'll do better next time.",
        "ru": "🙏 Спасибо! Ваш отзыв отправлен. В следующий раз будет лучше.",
    },

    # ── Bon de commande automatique (envoyé au client à la confirmation) ─────
    "receipt_title": {
        "fr": "🧾 *Bon de commande — N° {id}*",
        "es": "🧾 *Albarán — N° {id}*",
        "en": "🧾 *Order Receipt — #{id}*",
        "ru": "🧾 *Чек заказа — №{id}*",
    },
    "receipt_items": {
        "fr": "🛒 *Articles :*",
        "es": "🛒 *Artículos:*",
        "en": "🛒 *Items:*",
        "ru": "🛒 *Товары:*",
    },
    "receipt_address": {
        "fr": "📍 *Adresse de livraison :*",
        "es": "📍 *Dirección de entrega:*",
        "en": "📍 *Delivery address:*",
        "ru": "📍 *Адрес доставки:*",
    },
    "receipt_thanks": {
        "fr": "_Merci pour votre commande ! Nous vous contacterons très prochainement pour la livraison._ 🙏",
        "es": "_¡Gracias por tu pedido! Nos pondremos en contacto contigo muy pronto._ 🙏",
        "en": "_Thank you for your order! We will contact you very soon for delivery._ 🙏",
        "ru": "_Спасибо за заказ! Мы очень скоро свяжемся с вами для доставки._ 🙏",
    },

    # ── Annulation client (fenêtre 2 min après confirmation) ─────────────────
    "client_cancel_window": {
        "fr": "⏱️ Vous avez *2 minutes* pour annuler cette commande si vous changez d'avis.",
        "es": "⏱️ Tienes *2 minutos* para cancelar este pedido si cambias de opinión.",
        "en": "⏱️ You have *2 minutes* to cancel this order if you change your mind.",
        "ru": "⏱️ У вас есть *2 минуты*, чтобы отменить этот заказ, если передумаете.",
    },
    "client_cancel_btn": {
        "fr": "❌ Annuler ma commande",
        "es": "❌ Cancelar mi pedido",
        "en": "❌ Cancel my order",
        "ru": "❌ Отменить мой заказ",
    },
    "client_cancel_expired_msg": {
        "fr": "⏱️ _Le délai d'annulation (2 min) est expiré._",
        "es": "⏱️ _El plazo de cancelación (2 min) ha expirado._",
        "en": "⏱️ _The cancellation window (2 min) has expired._",
        "ru": "⏱️ _Срок отмены (2 мин) истёк._",
    },
    "client_cancel_too_late": {
        "fr": "⏱️ Désolé, le délai d'annulation (2 min) est dépassé. Contactez-nous directement si besoin.",
        "es": "⏱️ Lo sentimos, ha pasado el plazo de cancelación (2 min). Contáctanos directamente si lo necesitas.",
        "en": "⏱️ Sorry, the cancellation window (2 min) has passed. Contact us directly if needed.",
        "ru": "⏱️ К сожалению, срок отмены (2 мин) истёк. Свяжитесь с нами напрямую, если нужно.",
    },
    "client_cancel_done": {
        "fr": "✅ Votre commande *N° {id}* a été annulée.",
        "es": "✅ Tu pedido *N° {id}* ha sido cancelado.",
        "en": "✅ Your order *#{id}* has been cancelled.",
        "ru": "✅ Ваш заказ *№{id}* отменён.",
    },
    "owner_client_cancelled": {
        "fr": "❌ <b>Annulation client</b> — Le client {name} a annulé la commande <code>{id}</code> (dans la fenêtre 2 min).",
        "es": "❌ <b>Cancelación del cliente</b> — El cliente {name} ha cancelado el pedido <code>{id}</code> (dentro de la ventana de 2 min).",
        "en": "❌ <b>Client cancellation</b> — Client {name} cancelled order <code>{id}</code> (within 2 min window).",
        "ru": "❌ <b>Отмена клиентом</b> — Клиент {name} отменил заказ <code>{id}</code> (в течение 2 мин).",
    },

    # ── Divers ─────────────────────────────────────────────────────────────
    "restart_hint": {
        "fr": "↩️ Appuyez sur /start pour passer une nouvelle commande.",
        "es": "↩️ Pulsa /start para hacer un nuevo pedido.",
        "en": "↩️ Press /start to place a new order.",
        "ru": "↩️ Нажмите /start, чтобы сделать новый заказ.",
    },
    "session_timeout": {
        "fr": "⏱️ Votre session a expiré (inactif 30 min). Tapez /start pour recommencer.",
        "es": "⏱️ Tu sesión ha caducado (inactivo 30 min). Escribe /start para empezar de nuevo.",
        "en": "⏱️ Your session expired (30 min inactive). Type /start to start again.",
        "ru": "⏱️ Сессия истекла (30 мин без действий). Напишите /start, чтобы начать заново.",
    },
    "generic_error": {
        "fr": "❌ Erreur, réessayez.",
        "es": "❌ Error, vuelve a intentarlo.",
        "en": "❌ Error, try again.",
        "ru": "❌ Ошибка, попробуйте ещё раз.",
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

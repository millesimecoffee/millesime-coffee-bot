"""Le bot ne fait qu'ouvrir la Mini App : un bouton, aucune conversation."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _commun import preparer, titre, fin, OWNER, AUTRE

preparer(WEBAPP_URL="https://exemple.test")
import bot

bot.WEBAPP_URL = "https://exemple.test"
bot._blacklist = set()
bot._blocked = {}
bot._paused = False
bot._is_open = lambda: True


class FauxMessage:
    def __init__(self):
        self.reponses = []

    async def reply_text(self, texte, **kw):
        self.reponses.append((texte, kw.get("reply_markup")))
        return self


class FauxUser:
    def __init__(self, uid):
        self.id = uid
        self.first_name = "Test"
        self.username = "test"


class FauxUpdate:
    def __init__(self, uid):
        self.effective_user = FauxUser(uid)
        self.message = FauxMessage()


class FauxContext:
    def __init__(self):
        self.user_data = {}


def lancer(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def bouton_de(update):
    """Renvoie (libellé, url) du bouton web_app de la dernière réponse."""
    _, markup = update.message.reponses[-1]
    b = markup.keyboard[0][0]
    return b.text, (b.web_app.url if b.web_app else None)


print("=" * 62)

titre(1, "/start repond un seul bouton qui ouvre la Mini App")
u = FauxUpdate(AUTRE)
etat = lancer(bot.start(u, FauxContext()))
libelle, url = bouton_de(u)
print(f"   messages envoyes : {len(u.message.reponses)}")
print(f"   bouton           : {libelle!r} -> {url}")
print(f"   texte            : {u.message.reponses[0][0].splitlines()[0]}")
assert len(u.message.reponses) == 1, "un seul message"
_, markup = u.message.reponses[0]
assert len(markup.keyboard) == 1 and len(markup.keyboard[0]) == 1, "un seul bouton"
assert url.endswith("/menu") and "CATALOGUE" in libelle
assert markup.is_persistent, "le bouton doit rester affiche"

titre(2, "Plus de choix de langue ni de mot de passe dans le chat")
print(f"   etat de conversation retourne : {etat} (fin attendue)")
assert etat == bot.ConversationHandler.END

titre(3, "Le client ecrit au bot -> renvoye vers le bouton, sans dialogue")
for texte in ["bonjour", "PLATA O PLOMO", "vous avez quoi ?", "/menu"]:
    u = FauxUpdate(AUTRE)
    lancer(bot.rappel_catalogue(u, FauxContext()))
    libelle, _ = bouton_de(u)
    print(f"   {texte!r:20s} -> {libelle!r}")
    assert len(u.message.reponses) == 1 and "CATALOGUE" in libelle

titre(4, "L'owner n'est pas spamme par le rappel : ses commandes marchent")
u = FauxUpdate(OWNER)
lancer(bot.rappel_catalogue(u, FauxContext()))
print(f"   messages envoyes a l'owner : {len(u.message.reponses)} (0 attendu)")
assert u.message.reponses == []

titre(5, "/start n'est plus une entree de l'ancien parcours texte")
conv = bot.build_conv_handler()
noms = [type(h).__name__ for h in conv.entry_points]
commandes = [c for h in conv.entry_points for c in getattr(h, "commands", [])]
print(f"   points d'entree : {noms}")
print(f"   commandes       : {commandes or 'aucune'}")
assert "start" not in commandes

titre(6, "Bot en pause -> message de pause, pas de bouton")
bot._paused = True
bot._paused_reason = "maintenance"
u = FauxUpdate(AUTRE)
lancer(bot.start(u, FauxContext()))
print(f"   {u.message.reponses[0][0].splitlines()[0]}")
assert u.message.reponses[0][1] is None
bot._paused = False

titre(7, "Hors horaires -> banniere fermee, pas de bouton")
bot._is_open = lambda: False
u = FauxUpdate(AUTRE)
lancer(bot.start(u, FauxContext()))
print(f"   {u.message.reponses[0][0].splitlines()[0]}")
assert u.message.reponses[0][1] is None
print("   l'owner passe quand meme :")
u = FauxUpdate(OWNER)
lancer(bot.start(u, FauxContext()))
libelle, _ = bouton_de(u)
print(f"   {libelle!r}")
assert "CATALOGUE" in libelle
bot._is_open = lambda: True

titre(8, "Client banni -> aucun acces au catalogue")
bot._blacklist = {AUTRE}
u = FauxUpdate(AUTRE)
lancer(bot.start(u, FauxContext()))
print(f"   reponse : {u.message.reponses[0][0][:40]!r}, bouton : {u.message.reponses[0][1]}")
assert u.message.reponses[0][1] is None
bot._blacklist = set()

titre(9, "Sans WEBAPP_URL -> avertissement clair au lieu d'un bouton casse")
bot.WEBAPP_URL = ""
u = FauxUpdate(AUTRE)
lancer(bot.start(u, FauxContext()))
print(f"   {u.message.reponses[0][0]}")
assert "WEBAPP_URL" in u.message.reponses[0][0]
bot.WEBAPP_URL = "https://exemple.test"

titre(10, "L'owner AUSSI a le bouton CATALOGUE dans son chat")
print("    (sans lui, il ouvrait la boutique par un lien, donc hors de")
print("     Telegram, donc sans session : mot de passe refuse sans raison)")
poses = []


class FauxBot:
    async def set_my_commands(self, cmds, scope=None):
        pass

    async def set_chat_menu_button(self, menu_button=None, chat_id=None):
        poses.append((chat_id, type(menu_button).__name__,
                      getattr(menu_button, "text", "")))


class FauxApp:
    bot = FauxBot()


lancer(bot._post_init(FauxApp()))
for chat_id, genre, texte in poses:
    print(f"   chat={chat_id if chat_id else 'tous'}  {genre}  {texte!r}")
assert poses, "aucun bouton de menu configure"
assert all(g == "MenuButtonWebApp" for _, g, _ in poses), \
    "l'owner ne doit pas recevoir un bouton different"
assert any(c == OWNER for c, _, _ in poses), "rien de pose sur le chat de l'owner"

titre(11, "/app affiche exactement le meme bouton que /start")
u1, u2 = FauxUpdate(AUTRE), FauxUpdate(AUTRE)
lancer(bot.start(u1, FauxContext()))
lancer(bot.cmd_app(u2, FauxContext()))
print(f"   /start -> {bouton_de(u1)}")
print(f"   /app   -> {bouton_de(u2)}")
assert bouton_de(u1) == bouton_de(u2)

fin()

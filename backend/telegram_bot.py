"""Bot Telegram : notifications + commandes."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

from backend.config import BotMode, settings

if TYPE_CHECKING:
    from backend.bot import OracleBot

logger = logging.getLogger(__name__)


class _Notifier(Protocol):
    async def send(self, text: str) -> None: ...


class NullNotifier:
    """Notifier no-op utilise quand Telegram n'est pas configure."""

    async def send(self, text: str) -> None:
        logger.info("[telegram-noop] %s", text)


class TelegramNotifier:
    """Notifier reel base sur python-telegram-bot."""

    def __init__(self, token: str, chat_id: str) -> None:
        self.token = token
        self.chat_id = chat_id
        self._bot = None

    def _client(self):  # type: ignore[no-untyped-def]
        if self._bot is None:
            from telegram import Bot  # type: ignore[import-not-found]

            self._bot = Bot(token=self.token)
        return self._bot

    async def send(self, text: str) -> None:
        try:
            await self._client().send_message(chat_id=self.chat_id, text=text)
        except Exception as exc:
            logger.warning("Telegram send echoue: %s", exc)


def build_notifier() -> _Notifier:
    if settings.telegram_enabled:
        return TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id)
    return NullNotifier()


class TelegramCommandBot:
    """Polling Telegram pour traiter les commandes /start /stop /mise /mode /solde /stats /status."""

    def __init__(self, bot: OracleBot) -> None:
        self.bot = bot
        self._app = None

    async def start(self) -> None:
        if not settings.telegram_enabled:
            logger.info("Telegram non configure — commandes /start /stop /mise ignorees.")
            return
        try:
            from telegram import Update  # type: ignore[import-not-found]
            from telegram.ext import (  # type: ignore[import-not-found]
                ApplicationBuilder,
                CommandHandler,
                ContextTypes,
            )
        except ImportError:
            logger.warning("python-telegram-bot non installe — commandes desactivees.")
            return

        app = ApplicationBuilder().token(settings.telegram_bot_token).build()

        async def reply(update: Update, text: str) -> None:
            msg = update.effective_message
            if msg is None:
                return
            await msg.reply_text(text)

        async def on_start(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
            await self.bot.start()
            await reply(update, "Oracle Bot demarre.")

        async def on_stop(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
            await self.bot.stop()
            await reply(update, "Oracle Bot arrete.")

        async def on_mise(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
            try:
                amount = float((ctx.args or ["0"])[0])
                await self.bot.set_bet_amount(amount)
                await reply(update, f"Mise reglee a {amount:.2f} USDC.")
            except (ValueError, IndexError):
                await reply(update, "Usage: /mise <montant>")

        async def on_mode(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
            arg = (ctx.args or [""])[0].lower()
            if arg not in {"demo", "prod"}:
                await reply(update, "Usage: /mode demo|prod")
                return
            await self.bot.set_mode(BotMode(arg))
            await reply(update, f"Mode change vers {arg.upper()}.")

        async def on_solde(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
            s = self.bot.state
            await reply(update, f"Solde {s.mode.upper()}: {s.balance:.2f} USDC (PnL {s.pnl:+.2f}).")

        async def on_stats(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
            s = self.bot.state
            await reply(
                update,
                f"Total paris: {s.bets_total} (W{s.bets_won}/L{s.bets_lost}/S{s.bets_skipped})\n"
                f"Win rate: {s.win_rate}% | PnL: {s.pnl:+.2f} USDC",
            )

        async def on_status(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
            s = self.bot.state
            status = "Actif" if s.running else "Arrete"
            await reply(
                update,
                f"{status} | mode={s.mode} | BTC={s.btc_price:.2f} | signal={s.current_signal}",
            )

        app.add_handler(CommandHandler("start", on_start))
        app.add_handler(CommandHandler("stop", on_stop))
        app.add_handler(CommandHandler("mise", on_mise))
        app.add_handler(CommandHandler("mode", on_mode))
        app.add_handler(CommandHandler("solde", on_solde))
        app.add_handler(CommandHandler("stats", on_stats))
        app.add_handler(CommandHandler("status", on_status))

        await app.initialize()
        await app.start()
        if app.updater is not None:
            await app.updater.start_polling()
        self._app = app  # type: ignore[assignment]
        logger.info("Telegram command bot demarre.")

    async def stop(self) -> None:
        if self._app is None:
            return
        try:
            if self._app.updater is not None:
                await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
        except Exception as exc:
            logger.warning("Erreur arret Telegram: %s", exc)
        self._app = None

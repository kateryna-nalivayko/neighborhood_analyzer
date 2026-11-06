"""Точка входу: python -m bot"""

from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from .cache import TTLCache
from .config import ConfigError, load_settings
from .google_client import GoogleMapsClient
from .handlers import router


async def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # httpx логує повні URL — разом із ключем Geocoding API. Ховаємо ці записи.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    try:
        settings = load_settings()
    except ConfigError as exc:
        logging.error("%s", exc)
        sys.exit(1)

    google = GoogleMapsClient(settings.google_api_key, language=settings.language,
                              region=settings.region, cache_ttl=settings.cache_ttl_seconds)
    bot = Bot(token=settings.telegram_token,
              default=DefaultBotProperties(parse_mode=ParseMode.HTML,
                                           link_preview_is_disabled=True))
    # Об'єкти, передані в Dispatcher, aiogram підставляє в обробники за назвою аргументу.
    dp = Dispatcher(google=google, settings=settings,
                    addresses=TTLCache(ttl_seconds=24 * 3600, max_items=5000))
    dp.include_router(router)

    await bot.set_my_commands([
        BotCommand(command="start", description="Почати роботу"),
        BotCommand(command="help", description="Як користуватися ботом"),
    ])
    logging.info("Neighborhood Analyzer запущено. Натисніть Ctrl+C для зупинки.")
    try:
        await dp.start_polling(bot)
    finally:
        await google.aclose()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

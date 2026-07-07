import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, LOG_LEVEL
from database.db import init_db
from handlers import start, participants, sharing, expenses, calculate, export


async def main() -> None:

    # getattr(logging, "INFO") превращает строку "INFO" в logging.INFO
    logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))

    await init_db()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(start.router)
    dp.include_router(participants.router)
    dp.include_router(sharing.router)
    dp.include_router(expenses.router)
    dp.include_router(calculate.router)
    dp.include_router(export.router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
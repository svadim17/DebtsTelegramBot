from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from database import crud


async def require_editor(session: AsyncSession, callback: CallbackQuery, event_id: int) -> bool:
    """Проверяет, что пользователь — редактор события, и если нет,
    сама отвечает пользователю всплывающим предупреждением.
    Используется одинаково в handlers/participants.py, sharing.py и
    expenses.py — вынесено сюда, чтобы логика доступа была в одном месте.
    """
    if await crud.is_user_editor(session, event_id, callback.from_user.id):
        return True
    await callback.answer("У тебя нет доступа к этому событию 🚫", show_alert=True)
    return False

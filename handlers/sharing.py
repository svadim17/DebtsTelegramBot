from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

from database import crud
from database.db import async_session
from handlers.access import require_editor
from keyboards.inline import share_menu_keyboard

router = Router()


def _format_editor_label(editor) -> str:
    """Формирует читаемое имя редактора для списка "у кого есть доступ".
    Приоритет: имя (first_name) > username > просто tg_user_id,
    так как имя есть почти всегда, а username может отсутствовать.
    """
    label = editor.tg_first_name or editor.tg_username or f"id{editor.tg_user_id}"
    if editor.is_owner:
        label += " (владелец)"
    return label


async def _render_share_menu(callback: CallbackQuery, bot: Bot, event_id: int) -> None:
    """Общая отрисовка экрана "Доступ" — используется и при открытии,
    и после обновления ссылки, чтобы не дублировать код."""
    async with async_session() as session:
        event = await crud.get_event_by_id(session, event_id)
        editors = await crud.get_event_editors(session, event_id)

    if event is None:
        await callback.message.edit_text("Событие не найдено.")
        return

    # Получаем username бота, чтобы собрать диплинк — get_me() кэшируется
    # внутри aiogram, так что лишней нагрузки на Telegram API это не создаёт
    bot_info = await bot.get_me()
    invite_link = f"https://t.me/{bot_info.username}?start=join_{event.invite_token}"

    editors_text = "\n".join(f"• {_format_editor_label(e)}" for e in editors)

    text = (f"🔗 Доступ к событию «{event.title}»\n\n"
            f"Перешли эту ссылку тем, кто должен иметь возможность вместе с тобой "
            f"добавлять участников и траты:\n{invite_link}\n\n"
            f"👥 Сейчас доступ есть у:\n{editors_text}")

    await callback.message.edit_text(text, reply_markup=share_menu_keyboard(event_id))


@router.callback_query(F.data.startswith("share:"))
async def show_share_menu(callback: CallbackQuery, bot: Bot) -> None:
    event_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        if not await require_editor(session, callback, event_id):
            await callback.answer("У тебя нет доступа к этому событию 🚫", show_alert=True)
            return

    await _render_share_menu(callback, bot, event_id)
    await callback.answer()


@router.callback_query(F.data.startswith("regenerate_link:"))
async def regenerate_link(callback: CallbackQuery, bot: Bot) -> None:
    event_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        if not await require_editor(session, callback, event_id):
            await callback.answer("У тебя нет доступа к этому событию 🚫", show_alert=True)
            return
        await crud.regenerate_invite_token(session, event_id)

    await callback.answer("Ссылка обновлена — старая больше не действует.", show_alert=True)
    await _render_share_menu(callback, bot, event_id)
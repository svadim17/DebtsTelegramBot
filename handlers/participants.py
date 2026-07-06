from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from config import MAX_PARTICIPANTS_PER_EVENT
from database import crud
from database.db import async_session
from keyboards.inline import (confirm_delete_participant_keyboard, event_menu_keyboard, participants_menu_keyboard)
from states.fsm_states import AddParticipants, RenameParticipant


router = Router()


async def _check_access(session: AsyncSession, callback: CallbackQuery, event_id: int) -> bool:
    """ Проверяет, что пользователь имеет право редактировать это событие. """
    if await crud.is_user_editor(session, event_id, callback.from_user.id):
        return True
    await callback.answer("У тебя нет доступа к этому событию 🚫", show_alert=True)
    return False


async def _render_participants_list(callback: CallbackQuery, event_id: int) -> None:
    """Общая функция отрисовки списка участников — используется в нескольких
    местах (после добавления, удаления, переименования), чтобы не дублировать код."""
    async with async_session() as session:
        event = await crud.get_event_by_id(session, event_id)
        participants = await crud.get_participants(session, event_id)

    if event is None:
        await callback.message.edit_text("Событие не найдено.")
        return

    if participants:
        names = "\n".join(f"• {p.name}" for p in participants)
        text = f"👥 Участники события «{event.title}»:\n\n{names}"
    else:
        text = f"👥 Событие «{event.title}».\n\n Пока нет ни одного участника. Добавь их кнопкой ниже."

    await callback.message.edit_text(text, reply_markup=participants_menu_keyboard(event_id, participants))


@router.callback_query(F.data.startswith("participants:"))
async def show_participants(callback: CallbackQuery) -> None:
    event_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        if not await _check_access(session, callback, event_id):
            return

    await _render_participants_list(callback, event_id)
    await callback.answer()


@router.callback_query(F.data.startswith("add_participants:"))
async def add_participants_start(callback: CallbackQuery, state: FSMContext) -> None:
    event_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        if not await _check_access(session, callback, event_id):
            return
        current_count = await crud.count_participants(session, event_id)

    if current_count >= MAX_PARTICIPANTS_PER_EVENT:
        await callback.answer(f"Достигнут лимит участников на событие ({MAX_PARTICIPANTS_PER_EVENT}).",
                              show_alert=True)
        return

    # Сохраняем event_id в состоянии, чтобы использовать его в следующем шаге,
    # когда придёт обычное текстовое сообщение (у него уже не будет callback_data)
    await state.update_data(event_id=event_id)
    await state.set_state(AddParticipants.waiting_for_names)

    await callback.message.edit_text("Введи имена участников через запятую или каждое с новой строки.\n\n"
                                     "Например:\nВася, Петя, Оля")
    await callback.answer()


@router.message(AddParticipants.waiting_for_names)
async def add_participants_finish(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    event_id = data["event_id"]

    # Разбиваем ввод и по запятым, и по переносам строк — пользователю
    # удобнее вводить как привычнее, а не подстраиваться под формат
    raw_text = message.text.replace("\n", ",")
    names = [name.strip() for name in raw_text.split(",") if name.strip()]

    if not names:
        await message.answer("Не нашёл ни одного имени. Попробуй ещё раз:")
        return

    async with async_session() as session:
        current_count = await crud.count_participants(session, event_id)
        available_slots = MAX_PARTICIPANTS_PER_EVENT - current_count

        if available_slots <= 0:
            await message.answer(f"Достигнут лимит участников на событие ({MAX_PARTICIPANTS_PER_EVENT}).")
            await state.clear()
            return

        # Если прислали больше имён, чем осталось свободных слотов — берём только часть
        names_to_add = names[:available_slots]
        created = await crud.add_participants(session, event_id, names_to_add)
        event = await crud.get_event_by_id(session, event_id)
        participants = await crud.get_participants(session, event_id)

    await state.clear()

    skipped = len(names) - len(created)
    result_text = f"✅ Добавлено участников: {len(created)}"
    if skipped > 0:
        result_text += f"\n(пропущено {skipped} — дубликаты или превышен лимит)"

    names_list = "\n".join(f"• {p.name}" for p in participants)
    await message.answer(f"{result_text}\n\n👥 Участники события «{event.title}»:\n\n{names_list}",
                         reply_markup=participants_menu_keyboard(event_id, participants))


@router.callback_query(F.data.startswith("rename_participant:"))
async def rename_participant_start(callback: CallbackQuery, state: FSMContext) -> None:
    participant_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        participant = await crud.get_participant_by_id(session, participant_id)
        if participant is None:
            await callback.answer("Участник не найден.", show_alert=True)
            return
        if not await _check_access(session, callback, participant.event_id):
            return

    # Сохраняем и participant_id, и event_id — второй нужен, чтобы вернуться
    # к списку участников после переименования
    await state.update_data(participant_id=participant_id, event_id=participant.event_id)
    await state.set_state(RenameParticipant.waiting_for_new_name)

    await callback.message.edit_text(f"Введи новое имя вместо «{participant.name}»:")
    await callback.answer()


@router.message(RenameParticipant.waiting_for_new_name)
async def rename_participant_finish(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    participant_id = data["participant_id"]
    event_id = data["event_id"]

    new_name = message.text.strip()
    if not new_name:
        await message.answer("Имя не может быть пустым. Попробуй ещё раз:")
        return

    async with async_session() as session:
        await crud.rename_participant(session, participant_id, new_name)
        event = await crud.get_event_by_id(session, event_id)
        participants = await crud.get_participants(session, event_id)

    await state.clear()

    names_list = "\n".join(f"• {p.name}" for p in participants)
    await message.answer(f"✅ Имя обновлено.\n\n👥 Участники события «{event.title}»:\n\n{names_list}",
                         reply_markup=participants_menu_keyboard(event_id, participants))


@router.callback_query(F.data.startswith("delete_participant:"))
async def delete_participant_ask(callback: CallbackQuery) -> None:
    participant_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        participant = await crud.get_participant_by_id(session, participant_id)
        if participant is None:
            await callback.answer("Участник не найден.", show_alert=True)
            return
        if not await _check_access(session, callback, participant.event_id):
            return
        event_id = participant.event_id

    await callback.message.edit_text(f"Удалить участника «{participant.name}»?\n""Это действие нельзя отменить.")
    await callback.message.edit_reply_markup(reply_markup=confirm_delete_participant_keyboard(participant_id, event_id))
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_delete_participant:"))
async def confirm_delete_participant(callback: CallbackQuery) -> None:
    participant_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        participant = await crud.get_participant_by_id(session, participant_id)
        if participant is None:
            await callback.answer("Участник уже удалён.", show_alert=True)
            return

        event_id = participant.event_id
        if not await _check_access(session, callback, event_id):
            return

        deleted = await crud.delete_participant(session, participant_id)

    if not deleted:
        # Такое может случиться начиная с этапа 4, когда у участников
        # появятся связанные траты — тогда удаление блокируется намеренно
        await callback.answer("Нельзя удалить: у участника уже есть траты в этом событии.",
                              show_alert=True)
        await _render_participants_list(callback, event_id)
        return

    await _render_participants_list(callback, event_id)
    await callback.answer("Участник удалён.")
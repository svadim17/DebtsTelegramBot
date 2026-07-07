from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import MAX_EXPENSES_PER_EVENT
from database import crud
from database.db import async_session
from handlers.access import require_editor
from keyboards.inline import (
    confirm_delete_expense_keyboard,
    event_menu_keyboard,
    expense_detail_keyboard,
    expenses_list_keyboard,
    payer_picker_keyboard,
    skip_description_keyboard,
    split_choice_keyboard,
    split_custom_keyboard,
)
from states.fsm_states import AddExpense

router = Router()


async def _render_expenses_list(callback: CallbackQuery, event_id: int, page: int = 0) -> None:
    async with async_session() as session:
        event = await crud.get_event_by_id(session, event_id)
        expenses = await crud.get_expenses(session, event_id)

    if event is None:
        await callback.message.edit_text("Событие не найдено.")
        return

    if expenses:
        text = f"💸 Траты события «{event.title}»:"
    else:
        text = (f"💸 Событие «{event.title}»\n\n""Пока нет ни одной траты. Добавь первую кнопкой ниже.")

    await callback.message.edit_text(text, reply_markup=expenses_list_keyboard(event_id, expenses, page))


@router.callback_query(F.data.startswith("expenses:"))
async def show_expenses(callback: CallbackQuery) -> None:
    event_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        if not await require_editor(session, callback, event_id):
            return

    await _render_expenses_list(callback, event_id)
    await callback.answer()


@router.callback_query(F.data.startswith("expenses_page:"))
async def expenses_page(callback: CallbackQuery) -> None:
    _, event_id_str, page_str = callback.data.split(":")
    event_id, page = int(event_id_str), int(page_str)

    async with async_session() as session:
        if not await require_editor(session, callback, event_id):
            return

    await _render_expenses_list(callback, event_id, page)
    await callback.answer()


# --- Шаг 1: выбор плательщика ---

@router.callback_query(F.data.startswith("add_expense:"))
async def add_expense_start(callback: CallbackQuery, state: FSMContext) -> None:
    event_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        if not await require_editor(session, callback, event_id):
            return

        current_count = await crud.count_expenses(session, event_id)
        if current_count >= MAX_EXPENSES_PER_EVENT:
            await callback.answer(f"Достигнут лимит трат на событие ({MAX_EXPENSES_PER_EVENT}).", show_alert=True)
            return

        participants = await crud.get_participants(session, event_id)

    if not participants:
        await callback.answer("Сначала добавь хотя бы одного участника события.", show_alert=True)
        return

    # event_id понадобится на всех следующих шагах FSM — сохраняем сразу
    await state.update_data(event_id=event_id)

    await callback.message.edit_text("Кто заплатил?", reply_markup=payer_picker_keyboard(participants))
    await callback.answer()


@router.callback_query(F.data.startswith("pick_payer:"))
async def pick_payer(callback: CallbackQuery, state: FSMContext) -> None:
    payer_id = int(callback.data.split(":")[1])

    await state.update_data(payer_id=payer_id)
    await state.set_state(AddExpense.waiting_for_amount)

    await callback.message.edit_text("Введи сумму траты (например: 35 или 35.50):")
    await callback.answer()


# --- Шаг 2: сумма ---

@router.message(AddExpense.waiting_for_amount)
async def enter_amount(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Пришли сумму текстом, например: 35.50")
        return

    # Разрешаем и точку, и запятую как разделитель дробной части —
    # частая привычка вводить "1500,50" вместо "1500.50"
    raw_amount = message.text.strip().replace(",", ".")

    try:
        amount = float(raw_amount)
    except ValueError:
        await message.answer("Не похоже на число. Введи сумму ещё раз (например: 35.50):")
        return

    if amount <= 0:
        await message.answer("Сумма должна быть больше нуля. Попробуй ещё раз:")
        return

    if amount > 5000:
        await message.answer("У тебя столько денег нет. Попробуй ещё раз:")
        return

    await state.update_data(amount=round(amount, 2))
    await state.set_state(AddExpense.waiting_for_description)

    await message.answer("Добавь короткое описание (например: «Шашлык» или «Топливо»)\nили нажми «Пропустить»:",
                         reply_markup=skip_description_keyboard())


# --- Шаг 3: описание (можно пропустить) ---

@router.message(AddExpense.waiting_for_description)
async def enter_description(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Пришли описание текстом или нажми «Пропустить» выше.")
        return

    description = message.text.strip()
    await state.update_data(description=description or None)
    await _ask_split_type(message.answer, state)


@router.callback_query(AddExpense.waiting_for_description, F.data == "skip_description")
async def skip_description(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(description=None)
    await _ask_split_type(callback.message.edit_text, state)
    await callback.answer()


async def _ask_split_type(send_func, state: FSMContext) -> None:
    """Показывает выбор способа деления траты. send_func — это либо
    message.answer, либо message.edit_text (разные шаги ведут сюда
    разными путями, поэтому функция отправки параметризована)."""
    await state.set_state(AddExpense.choosing_participants)
    await send_func("Кто участвует в этой трате?", reply_markup=split_choice_keyboard())


# --- Шаг 4а: поровну на всех участников события ---

@router.callback_query(AddExpense.choosing_participants, F.data == "split_all")
async def split_all(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()

    async with async_session() as session:
        participants = await crud.get_participants(session, data["event_id"])
        participant_ids = [p.id for p in participants]

    await _finalize_expense(callback, state, participant_ids)


# --- Шаг 4б: выбрать участников вручную (мультивыбор с чекбоксами) ---

@router.callback_query(AddExpense.choosing_participants, F.data == "split_custom")
async def split_custom_start(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()

    async with async_session() as session:
        participants = await crud.get_participants(session, data["event_id"])

    # По умолчанию отмечаем всех — пользователю обычно проще снять
    # галочки с 1-2 лишних, чем отмечать всех по одному
    selected_ids = {p.id for p in participants}
    await state.update_data(selected_ids=list(selected_ids))

    await callback.message.edit_text("Отметь, кто участвует в этой трате:",
                                     reply_markup=split_custom_keyboard(participants, selected_ids))
    await callback.answer()


@router.callback_query(AddExpense.choosing_participants, F.data.startswith("toggle_split_participant:"))
async def toggle_split_participant(callback: CallbackQuery, state: FSMContext) -> None:
    participant_id = int(callback.data.split(":")[1])

    data = await state.get_data()
    selected_ids = set(data.get("selected_ids", []))

    if participant_id in selected_ids:
        selected_ids.discard(participant_id)
    else:
        selected_ids.add(participant_id)

    await state.update_data(selected_ids=list(selected_ids))

    async with async_session() as session:
        participants = await crud.get_participants(session, data["event_id"])

    await callback.message.edit_reply_markup(reply_markup=split_custom_keyboard(participants, selected_ids))
    await callback.answer()


@router.callback_query(AddExpense.choosing_participants, F.data == "confirm_custom_split")
async def confirm_custom_split(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    selected_ids = data.get("selected_ids", [])

    if not selected_ids:
        await callback.answer("Отметь хотя бы одного участника.", show_alert=True)
        return

    await _finalize_expense(callback, state, selected_ids)


# --- Финальный шаг: сохранение траты ---

async def _finalize_expense(callback: CallbackQuery, state: FSMContext, participant_ids: list[int]) -> None:
    data = await state.get_data()

    async with async_session() as session:
        expense = await crud.create_expense(session,
                                            event_id=data["event_id"],
                                            payer_id=data["payer_id"],
                                            amount=data["amount"],
                                            description=data.get("description"),
                                            participant_ids=participant_ids,
                                            created_by=callback.from_user.id)

    await state.clear()

    description_line = f" ({expense.description})" if expense.description else ""
    await callback.message.edit_text(f"✅ Трата добавлена: {expense.payer.name} заплатил "
                                     f"{expense.amount:.2f}{description_line}\n"
                                     f"Разделена между {len(participant_ids)} участниками.",
                                     reply_markup=event_menu_keyboard(data["event_id"]))
    await callback.answer()


@router.callback_query(F.data == "cancel_add_expense")
async def cancel_add_expense(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    event_id = data.get("event_id")
    await state.clear()

    if event_id is not None:
        await _render_expenses_list(callback, event_id)
    await callback.answer("Добавление траты отменено.")


# --- Просмотр и удаление конкретной траты ---

@router.callback_query(F.data.startswith("view_expense:"))
async def view_expense(callback: CallbackQuery) -> None:
    expense_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        expense = await crud.get_expense_by_id(session, expense_id)
        if expense is None:
            await callback.answer("Трата не найдена.", show_alert=True)
            return
        if not await require_editor(session, callback, expense.event_id):
            return

    shares_text = "\n".join(f"  • {share.participant.name}: {share.share_amount:.2f}" for share in expense.shares)
    description_line = f"\n📝 {expense.description}" if expense.description else ""

    text = (f"💸 Плательщик: {expense.payer.name}\n"
            f"💰 Сумма: {expense.amount:.2f}{description_line}\n\n"
            f"Доли участников:\n{shares_text}")

    await callback.message.edit_text(text, reply_markup=expense_detail_keyboard(expense_id, expense.event_id))
    await callback.answer()


@router.callback_query(F.data.startswith("delete_expense:"))
async def delete_expense_ask(callback: CallbackQuery) -> None:
    expense_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        expense = await crud.get_expense_by_id(session, expense_id)
        if expense is None:
            await callback.answer("Трата не найдена.", show_alert=True)
            return
        if not await require_editor(session, callback, expense.event_id):
            return
        event_id = expense.event_id

    await callback.message.edit_text(f"Удалить трату «{expense.payer.name}: {expense.amount:.2f}»?\n"
                                     "Это действие нельзя отменить.")
    await callback.message.edit_reply_markup(reply_markup=confirm_delete_expense_keyboard(expense_id, event_id))
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_delete_expense:"))
async def confirm_delete_expense(callback: CallbackQuery) -> None:
    expense_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        expense = await crud.get_expense_by_id(session, expense_id)
        if expense is None:
            await callback.answer("Трата уже удалена.", show_alert=True)
            return
        event_id = expense.event_id
        if not await require_editor(session, callback, event_id):
            return

        await crud.delete_expense(session, expense_id)

    await _render_expenses_list(callback, event_id)
    await callback.answer("Трата удалена.")
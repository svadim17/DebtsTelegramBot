from aiogram import F, Router
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from database import crud
from database.db import async_session
from keyboards.inline import (event_menu_keyboard, events_list_keyboard, main_menu_keyboard)
from states.fsm_states import CreateEvent

router = Router()

WELCOME_TEXT = (
    "👋 Привет, я от Вадима @svadim17! Я помогу рассчитать, кто кому должен денег после мероприятия.\n\n"
    "Как это работает:\n"
    "1. Ты создаёшь событие и добавляешь участников\n"
    "2. Вносишь, кто сколько заплатил\n"
    "3. Я считаю итоговые переводы — кто кому и сколько должен\n\n"
    "Выбери действие:"
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, command: CommandObject) -> None:
    await state.clear()

    args = command.args
    if args and args.startswith("join_"):
        token = args.removeprefix("join_")
        await _join_event_by_link(message, token)
        return

    await message.answer(WELCOME_TEXT, reply_markup=main_menu_keyboard())

async def _join_event_by_link(message: Message, token: str) -> None:
    """ Обрабатывает переход по ссылке-приглашению https://t.me/bot?start=join_<token>.
    Добавляет пользователя в редакторы события (если он ещё не редактор) и сразу открывает меню события. """

    async with async_session() as session:
        event = await crud.join_event_by_token(session,
                                               token=token,
                                               tg_user_id=message.from_user.id,
                                               tg_username=message.from_user.username,
                                               tg_first_name=message.from_user.first_name)

    if event is None:
        await message.answer("⚠️ Ссылка недействительна или устарела — возможно, "
                             "владелец события обновил её.\n\n"
                             "Попроси актуальную ссылку у того, кто тебя приглашал.",
                             reply_markup=main_menu_keyboard())
        return

    await message.answer(f"✅ Ты получил доступ к событию «{event.title}»!\n"
                         f"Теперь можешь вместе с остальными добавлять участников и траты.",
                         reply_markup=event_menu_keyboard(event.id))


@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(WELCOME_TEXT, reply_markup=main_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "create_event")
async def create_event_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CreateEvent.waiting_for_title)
    await callback.message.edit_text("Введи название события (например: «Поездка на дачу»):")
    await callback.answer()


@router.message(CreateEvent.waiting_for_title)
async def create_event_finish(message: Message, state: FSMContext) -> None:
    title = message.text.strip()
    if not title:
        await message.answer("Название не может быть пустым. Попробуй ещё раз:")
        return

    async with async_session() as session:
        event = await crud.create_event(session, title=title, owner_tg_id=message.from_user.id)

    await state.clear()
    await message.answer(f"✅ Событие «{event.title}» создано!\n\n"
                         f"Теперь добавь участников и вноси траты.",
                         reply_markup=event_menu_keyboard(event.id))


@router.callback_query(F.data == "my_events")
async def show_my_events(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    async with async_session() as session:
        events = await crud.get_user_events(session, callback.from_user.id)

    if not events:
        await callback.message.edit_text("У тебя пока нет активных событий.", reply_markup=main_menu_keyboard())
        await callback.answer()
        return

    await callback.message.edit_text("Выбери событие:", reply_markup=events_list_keyboard(events))
    await callback.answer()


@router.callback_query(F.data.startswith("open_event:"))
async def open_event(callback: CallbackQuery) -> None:
    event_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        event = await crud.get_event_by_id(session, event_id)

    if event is None:
        await callback.answer("Событие не найдено", show_alert=True)
        return

    await callback.message.edit_text(f"📌 Событие: «{event.title}»\n\nВыбери действие:",
                                     reply_markup=event_menu_keyboard(event.id))
    await callback.answer()
    

@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery) -> None:
    """Декоративная кнопка (например, индикатор "2/5" в пагинации) —
    ничего не делает, просто гасит нажатие без всплывающей ошибки."""
    await callback.answer()


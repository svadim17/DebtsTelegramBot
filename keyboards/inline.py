from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.models import Event, Participant


def main_menu_keyboard() -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Создать мероприятие", callback_data="create_event")
    builder.button(text="📋 Мои мероприятия", callback_data="my_events")
    builder.adjust(1)
    return builder.as_markup()


def events_list_keyboard(events: list[Event]) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    for event in events:
        builder.row(InlineKeyboardButton(text=event.title, callback_data=f"open_event:{event.id}"))
    builder.row(InlineKeyboardButton(text="⬅️ В меню", callback_data="back_to_main"))
    return builder.as_markup()


def event_menu_keyboard(event_id: int) -> InlineKeyboardBuilder:
    """ Меню внутри события """
    builder = InlineKeyboardBuilder()
    builder.button(text="👥 Участники", callback_data=f"participants:{event_id}")
    builder.button(text="💸 Затраты", callback_data=f"expenses:{event_id}")
    builder.button(text="📊 Итог", callback_data=f"calculate:{event_id}")
    builder.button(text="📤 Экспорт данных", callback_data=f"export:{event_id}")
    builder.button(text="🔗 Доступ", callback_data=f"share:{event_id}")
    builder.button(text="⬅️ Назад", callback_data="my_events")
    builder.adjust(2)
    return builder.as_markup()


def participants_menu_keyboard(event_id: int, participants: list[Participant]) -> InlineKeyboardBuilder:
    """Список участников: у каждого — кнопка переименовать и удалить в одной строке."""
    builder = InlineKeyboardBuilder()

    for participant in participants:
        builder.row(InlineKeyboardButton(text=f"✏️ {participant.name}",
                                         callback_data=f"rename_participant:{participant.id}",),
                    InlineKeyboardButton(text="❌",
                                         callback_data=f"delete_participant:{participant.id}"))

    builder.row(InlineKeyboardButton(text="➕ Добавить участников", callback_data=f"add_participants:{event_id}",))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"open_event:{event_id}"))
    return builder.as_markup()


def confirm_delete_participant_keyboard(participant_id: int, event_id: int) -> InlineKeyboardBuilder:
    """Подтверждение перед удалением участника — чтобы не удалить случайным нажатием."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, удалить", callback_data=f"confirm_delete_participant:{participant_id}",)
    builder.button(text="Отмена", callback_data=f"participants:{event_id}")
    builder.adjust(1)
    return builder.as_markup()
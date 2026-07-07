from aiogram.fsm.state import State, StatesGroup


class CreateEvent(StatesGroup):
    waiting_for_title = State()


class AddParticipants(StatesGroup):
    waiting_for_names = State()


class RenameParticipant(StatesGroup):
    waiting_for_new_name = State()


class AddExpense(StatesGroup):
    # Выбор плательщика происходит через inline-кнопки
    waiting_for_amount = State()
    waiting_for_description = State()
    choosing_participants = State()
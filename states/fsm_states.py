from aiogram.fsm.state import State, StatesGroup


class CreateEvent(StatesGroup):
    waiting_for_title = State()


class AddParticipants(StatesGroup):
    waiting_for_names = State()


class RenameParticipant(StatesGroup):
    waiting_for_new_name = State()
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import secrets
from database.models import Event, EventEditor, EventStatus, Expense, ExpenseShare, Participant
from services.money import split_equally

async def create_event(session: AsyncSession, title: str, owner_tg_id: int, chat_id: int | None = None) -> Event:
    """Создаёт новое событие и делает создателя владельцем-редактором."""
    event = Event(title=title, created_by=owner_tg_id, chat_id=chat_id)
    session.add(event)
    await session.flush()  # чтобы получить event.id до коммита

    editor = EventEditor(event_id=event.id, tg_user_id=owner_tg_id, is_owner=True)
    session.add(editor)

    await session.commit()
    await session.refresh(event)
    return event


async def get_user_events(session: AsyncSession, tg_user_id: int) -> list[Event]:
    """Возвращает все активные события, где пользователь является редактором."""
    result = await session.execute(
        select(Event)
        .join(EventEditor, EventEditor.event_id == Event.id)
        .where(
            EventEditor.tg_user_id == tg_user_id,
            Event.status == EventStatus.ACTIVE,
        )
        .order_by(Event.created_at.desc())
    )
    return list(result.scalars().all())


async def get_event_by_id(session: AsyncSession, event_id: int) -> Event | None:
    return await session.get(Event, event_id)


async def is_user_editor(session: AsyncSession, event_id: int, tg_user_id: int) -> bool:
    result = await session.execute(
        select(EventEditor).where(
            EventEditor.event_id == event_id,
            EventEditor.tg_user_id == tg_user_id,
        )
    )
    return result.scalar_one_or_none() is not None


# --- Участники события ---

async def get_participants(session: AsyncSession, event_id: int) -> list[Participant]:
    """Возвращает всех участников события в порядке добавления (по id)."""
    result = await session.execute(
        select(Participant)
        .where(Participant.event_id == event_id)
        .order_by(Participant.id)
    )
    return list(result.scalars().all())


async def count_participants(session: AsyncSession, event_id: int) -> int:
    """Считает участников события — нужно для проверки лимита из config.yaml."""
    participants = await get_participants(session, event_id)
    return len(participants)


async def add_participants(
    session: AsyncSession, event_id: int, names: list[str]
) -> list[Participant]:
    """Добавляет сразу несколько участников по списку имён.

    Дубликаты имён (без учёта регистра) внутри одного события пропускаются,
    чтобы случайно не завести два разных "Вася" из-за опечатки в регистре.
    """
    existing = await get_participants(session, event_id)
    existing_names_lower = {p.name.lower() for p in existing}

    created: list[Participant] = []
    for raw_name in names:
        name = raw_name.strip()
        if not name:
            continue
        if name.lower() in existing_names_lower:
            # уже есть такой участник — не дублируем
            continue

        participant = Participant(event_id=event_id, name=name)
        session.add(participant)
        created.append(participant)
        existing_names_lower.add(name.lower())

    await session.commit()
    for participant in created:
        await session.refresh(participant)

    return created


async def get_participant_by_id(
    session: AsyncSession, participant_id: int
) -> Participant | None:
    return await session.get(Participant, participant_id)


async def rename_participant(
    session: AsyncSession, participant_id: int, new_name: str
) -> Participant | None:
    participant = await session.get(Participant, participant_id)
    if participant is None:
        return None
    participant.name = new_name.strip()
    await session.commit()
    await session.refresh(participant)
    return participant


async def participant_has_expenses(session: AsyncSession, participant_id: int) -> bool:
    """ Проверяет, участвует ли участник в каких-либо тратах — как плательщик
    или как один из тех, кто делит трату.
    Нужно, чтобы не дать удалить участника, если по нему уже есть история
    трат — иначе расчёт долгов станет некорректным задним числом. """
    as_payer = await session.execute(
        select(Expense.id).where(Expense.payer_id == participant_id).limit(1)
    )
    if as_payer.scalar_one_or_none() is not None:
        return True

    as_share = await session.execute(
        select(ExpenseShare.id)
        .where(ExpenseShare.participant_id == participant_id)
        .limit(1)
    )
    return as_share.scalar_one_or_none() is not None


async def delete_participant(session: AsyncSession, participant_id: int) -> bool:
    """Удаляет участника. Возвращает False, если у него уже есть траты
    (удалять нельзя — сначала нужно удалить/переназначить связанные траты)."""
    participant = await session.get(Participant, participant_id)
    if participant is None:
        return False

    if await participant_has_expenses(session, participant_id):
        return False

    await session.delete(participant)
    await session.commit()
    return True


async def get_event_by_invite_token(session: AsyncSession, token: str) -> Event | None:
    """Ищет событие по токену из диплинка вида ?start=join_<token>."""
    result = await session.execute(select(Event).where(Event.invite_token == token))
    return result.scalar_one_or_none()


async def join_event_by_token(session: AsyncSession,
                              token: str,
                              tg_user_id: int,
                              tg_username: str | None,
                              tg_first_name: str | None) -> Event | None:
    """Добавляет пользователя в редакторы события по токену приглашения.
    Если пользователь уже редактор (например, повторно перешёл по той же
    ссылке) — просто возвращает событие без дублирования записи.
    Возвращает None, если токен не найден (ссылка недействительна,
    например была сгенерирована заново через "Обновить ссылку").
    """
    event = await get_event_by_invite_token(session, token)
    if event is None:
        return None

    already_editor = await is_user_editor(session, event.id, tg_user_id)
    if not already_editor:
        editor = EventEditor(event_id=event.id,
                             tg_user_id=tg_user_id,
                             is_owner=False,
                             tg_username=tg_username,
                             tg_first_name=tg_first_name)
        session.add(editor)
        await session.commit()

    return event


async def get_event_editors(session: AsyncSession, event_id: int) -> list[EventEditor]:
    """Возвращает список всех, у кого есть доступ на редактирование события."""
    result = await session.execute(
        select(EventEditor)
        .where(EventEditor.event_id == event_id)
        .order_by(EventEditor.is_owner.desc(), EventEditor.id)
    )
    return list(result.scalars().all())


async def regenerate_invite_token(session: AsyncSession, event_id: int) -> Event | None:
    """Генерирует новый токен приглашения — старая ссылка перестаёт работать.
    Полезно, если ссылка случайно попала не в те руки и нужно "отозвать" доступ
    для тех, кто ещё не успел по ней перейти (уже присоединившихся редакторов
    это не затрагивает — их можно только удалить из EventEditor вручную).
    """
    event = await session.get(Event, event_id)
    if event is None:
        return None

    event.invite_token = secrets.token_urlsafe(12)
    await session.commit()
    await session.refresh(event)
    return event


# --- Траты (Этап 4) ---

# Общие "жадные" опции загрузки связанных данных для Expense.
# Нужны, потому что после закрытия сессии обращение к expense.payer
# или expense.shares без предварительной подгрузки вызовет ошибку —
# в отличие от простых колонок (title, name), связи по умолчанию
# подгружаются лениво и требуют активной сессии.
_EXPENSE_LOAD_OPTIONS = (
    selectinload(Expense.payer),
    selectinload(Expense.shares).selectinload(ExpenseShare.participant),
)


async def create_expense(session: AsyncSession,
                         event_id: int,
                         payer_id: int,
                         amount: float,
                         description: str | None,
                         participant_ids: list[int],
                         created_by: int) -> Expense:
    """Создаёт трату и сразу считает доли участников (поровну).
    participant_ids — те, кто потребляет эту трату (не обязательно все участники события).
    """
    expense = Expense(event_id=event_id, payer_id=payer_id, amount=amount, description=description, created_by=created_by)
    session.add(expense)
    await session.flush()  # получаем expense.id для создания ExpenseShare

    shares = split_equally(amount, participant_ids)
    for participant_id, share_amount in shares.items():
        session.add(ExpenseShare(expense_id=expense.id, participant_id=participant_id, share_amount=share_amount))

    await session.commit()

    # Перечитываем с подгруженными связями, чтобы сразу можно было
    # показать пользователю итоговую карточку траты
    result = await session.execute(
        select(Expense).where(Expense.id == expense.id).options(*_EXPENSE_LOAD_OPTIONS)
    )
    return result.scalar_one()


async def get_expenses(session: AsyncSession, event_id: int) -> list[Expense]:
    """Возвращает все траты события, отсортированные от новых к старым."""
    result = await session.execute(
        select(Expense)
        .where(Expense.event_id == event_id)
        .options(*_EXPENSE_LOAD_OPTIONS)
        .order_by(Expense.created_at.desc())
    )
    return list(result.scalars().all())


async def get_expense_by_id(session: AsyncSession, expense_id: int) -> Expense | None:
    result = await session.execute(
        select(Expense)
        .where(Expense.id == expense_id)
        .options(*_EXPENSE_LOAD_OPTIONS)
    )
    return result.scalar_one_or_none()


async def count_expenses(session: AsyncSession, event_id: int) -> int:
    """Считает траты события — нужно для проверки лимита из config.yaml."""
    result = await session.execute(
        select(Expense.id).where(Expense.event_id == event_id)
    )
    return len(result.all())


async def delete_expense(session: AsyncSession, expense_id: int) -> bool:
    """Удаляет трату вместе со всеми её долями (cascade настроен в модели)."""
    expense = await session.get(Expense, expense_id)
    if expense is None:
        return False
    await session.delete(expense)
    await session.commit()
    return True
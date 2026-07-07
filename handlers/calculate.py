from aiogram import F, Router
from aiogram.types import CallbackQuery

from database import crud
from database.db import async_session
from handlers.access import require_editor
from keyboards.inline import calculate_result_keyboard
from services.debt_calculator import calculate_balances, minimize_transactions

router = Router()

# Балансы меньше этого порога считаем нулевыми — защита от "хвостов"
# вроде 0.0000000001 из-за особенностей float, которые иначе показали бы
# участнику пустячный долг в доли копейки
ZERO_THRESHOLD = 0.005

async def build_report_data(session, event_id: int) -> dict:
    """Собирает все данные, нужные и для экрана "Итог", и для экспорта
    (Этап 6) — вынесено сюда, чтобы не дублировать один и тот же запрос
    к БД и один и тот же расчёт балансов в двух разных хендлерах.

    Возвращает словарь. Если участников или трат ещё нет, соответствующие
    поля balance/transactions/name_by_id будут None — вызывающий код
    должен сам решить, как об этом сообщить пользователю.
    """
    event = await crud.get_event_by_id(session, event_id)
    participants = await crud.get_participants(session, event_id)
    expenses = await crud.get_expenses(session, event_id)

    paid = owed = balance = transactions = name_by_id = None
    if participants and expenses:
        paid, owed, balance = calculate_balances(participants, expenses)
        transactions = minimize_transactions(balance)
        name_by_id = {p.id: p.name for p in participants}

    return {
        "event": event,
        "participants": participants,
        "expenses": expenses,
        "paid": paid,
        "owed": owed,
        "balance": balance,
        "transactions": transactions,
        "name_by_id": name_by_id,
    }


@router.callback_query(F.data.startswith("calculate:"))
async def show_calculation(callback: CallbackQuery) -> None:
    event_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        if not await require_editor(session, callback, event_id):
            return

        event = await crud.get_event_by_id(session, event_id)
        participants = await crud.get_participants(session, event_id)
        expenses = await crud.get_expenses(session, event_id)

    if event is None:
        await callback.message.edit_text("Событие не найдено.")
        await callback.answer()
        return

    if not participants:
        await callback.message.edit_text(f"📊 Событие «{event.title}»\n\n"
                                         "Пока нет ни одного участника — добавь их в разделе «Участники», "
                                         "чтобы можно было посчитать баланс.",
                                         reply_markup=calculate_result_keyboard(event_id))
        await callback.answer()
        return

    if not expenses:
        await callback.message.edit_text(f"📊 Событие «{event.title}»\n\n"
                                         "Пока нет ни одной траты — добавь их в разделе «Траты», "
                                         "чтобы бот посчитал, кто кому должен.",
                                         reply_markup=calculate_result_keyboard(event_id))
        await callback.answer()
        return

    paid, owed, balance = calculate_balances(participants, expenses)
    transactions = minimize_transactions(balance)
    name_by_id = {p.id: p.name for p in participants}

    text = _render_result_text(event.title, participants, paid, owed, balance, transactions, name_by_id)

    await callback.message.edit_text(text, reply_markup=calculate_result_keyboard(event_id))
    await callback.answer()


def _render_result_text(event_title: str,
                        participants: list,
                        paid: dict[int, float],
                        owed: dict[int, float],
                        balance: dict[int, float],
                        transactions: list[tuple[int, int, float]],
                        name_by_id: dict[int, str]) -> str:
    """Собирает финальный текст экрана "Итог" — вынесено в отдельную функцию,
    чтобы саму отрисовку можно было протестировать без Telegram и без БД."""

    balance_lines = []
    for participant in participants:
        pid = participant.id
        bal = balance[pid]

        if bal > ZERO_THRESHOLD:
            status = f"ему должны {bal:.2f}"
        elif bal < -ZERO_THRESHOLD:
            status = f"должен {abs(bal):.2f}"
        else:
            status = "в расчёте"

        balance_lines.append(f"• {participant.name}: заплатил {paid[pid]:.2f}, должен был {owed[pid]:.2f} → {status}")

    if transactions:
        transactions_lines = [f"{name_by_id[debtor_id]} → {name_by_id[creditor_id]}: {amount:.2f}"
                              for debtor_id, creditor_id, amount in transactions]
        transactions_text = "\n".join(transactions_lines)
    else:
        transactions_text = "Все в расчёте — переводы не нужны! 🎉"

    return (f"📊 Итоги события «{event_title}»\n\n"
            + "\n".join(balance_lines)
            + "\n\n💸 Кто кому переводит:\n"
            + transactions_text)
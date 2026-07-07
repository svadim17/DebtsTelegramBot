def calculate_balances(participants: list, expenses: list) -> tuple[dict[int, float], dict[int, float], dict[int, float]]:
    """Считает для каждого участника: сколько заплатил, сколько должен был
    заплатить по факту (сумма его долей во всех тратах) и итоговый баланс.

    Возвращает три словаря {participant_id: сумма}:
    - paid    — сколько реально заплатил (как плательщик трат)
    - owed    — сколько должен был заплатить (сумма его долей)
    - balance — paid - owed. Положительный — ему должны, отрицательный — он должен.

    Ожидает участников с атрибутом .id и траты с атрибутами .payer_id, .amount
    и .shares (список объектов с .participant_id и .share_amount) — то есть
    подходит и для настоящих ORM-объектов Expense, и для простых тестовых
    заглушек с такими же полями.
    """
    paid = {p.id: 0.0 for p in participants}
    owed = {p.id: 0.0 for p in participants}

    for expense in expenses:
        # На случай траты от участника, которого почему-то нет в списке
        # (не должно происходить в норме, но не хотим падать с KeyError)
        paid[expense.payer_id] = paid.get(expense.payer_id, 0.0) + expense.amount

        for share in expense.shares:
            owed[share.participant_id] = (owed.get(share.participant_id, 0.0) + share.share_amount)

    balance = {participant_id: round(paid[participant_id] - owed[participant_id], 2)for participant_id in paid}

    return paid, owed, balance


def minimize_transactions(balances: dict[int, float]) -> list[tuple[int, int, float]]:
    """Строит минимальный набор переводов, закрывающий все балансы.

    Жадный алгоритм: на каждом шаге берём самого крупного должника и самого
    крупного кредитора, гасим между ними максимально возможную сумму и
    повторяем, пока все балансы не обнулятся. Это даёт не более (N-1)
    переводов вместо N*(N-1)/2 при наивном попарном расчёте.

    Считаем в целых копейках (int), а не в float — иначе на длинной
    цепочке сложений/вычитаний могут накопиться ошибки округления
    (0.1 + 0.2 != 0.3 в float) и в конце останется "хвост" в доли копейки.

    Возвращает список (debtor_id, creditor_id, amount) — amount уже в рублях.
    """
    # Переводим в копейки
    cents = {pid: round(bal * 100) for pid, bal in balances.items()}

    creditors = sorted(((pid, c) for pid, c in cents.items() if c > 0), key=lambda x: -x[1])
    debtors = sorted(((pid, c) for pid, c in cents.items() if c < 0), key=lambda x: x[1])

    # Списки нужно сделать изменяемыми (кортежи sorted() неизменяемы),
    # чтобы обновлять остаток долга/переплаты на каждом шаге
    creditors = [list(item) for item in creditors]
    debtors = [list(item) for item in debtors]

    transactions: list[tuple[int, int, float]] = []
    i, j = 0, 0

    while i < len(debtors) and j < len(creditors):
        debtor_id, debtor_cents = debtors[i]  # debtor_cents отрицательный
        creditor_id, creditor_cents = creditors[j]  # положительный

        amount_cents = min(-debtor_cents, creditor_cents)
        if amount_cents > 0:
            transactions.append((debtor_id, creditor_id, amount_cents / 100))

        debtors[i][1] += amount_cents
        creditors[j][1] -= amount_cents

        if debtors[i][1] == 0:
            i += 1
        if creditors[j][1] == 0:
            j += 1

    return transactions
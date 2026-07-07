def split_equally(amount: float, participant_ids: list[int]) -> dict[int, float]:
    """Делит сумму amount поровну между participant_ids с точностью до копейки.

    Проблема, которую решает эта функция: 1000 / 3 = 333.333... — если просто
    округлить каждую долю, сумма долей (333.33 * 3 = 999.99) не совпадёт
    с исходной суммой. Разница в 1-2 копейки при обычном делении неизбежна
    из-за округления, поэтому недостающие/лишние копейки нужно кому-то
    явно докинуть, а не просто отбросить.

    Алгоритм:
    1. Переводим сумму в целые копейки (int), чтобы избежать ошибок
       плавающей точки при делении (float может давать 0.1+0.2 != 0.3)
    2. Делим копейки нацело — получаем базовую долю каждого
    3. Остаток от деления (всегда меньше, чем количество участников)
       раздаём по одной копейке первым в списке участникам

    Возвращает словарь {participant_id: доля_в_рублях}.
    """
    if not participant_ids:
        return {}

    total_cents = round(amount * 100)
    count = len(participant_ids)

    base_share_cents = total_cents // count
    remainder_cents = total_cents % count

    shares: dict[int, float] = {}
    for index, participant_id in enumerate(participant_ids):
        # Первым `remainder_cents` участникам в списке достаётся +1 копейка,
        # чтобы сумма долей точно совпала с total_cents
        cents = base_share_cents + (1 if index < remainder_cents else 0)
        shares[participant_id] = cents / 100

    return shares
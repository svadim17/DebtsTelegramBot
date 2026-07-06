import os
import sys
import yaml


CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")


def _load_config() -> dict:
    """ Читает config.yaml и возвращает его содержимое как словарь. """

    if not os.path.exists(CONFIG_PATH):
        sys.exit(f"Не найден файл конфигурации: {CONFIG_PATH}\n")

    with open(CONFIG_PATH, "r", encoding="utf-8") as file:
        try:
            data = yaml.safe_load(file)
        except yaml.YAMLError as error:
            sys.exit(f"Ошибка в config.yaml — проверь синтаксис (отступы, кавычки):\n{error}")

    if not data:
        sys.exit("config.yaml пустой или некорректный.")

    return data


_config = _load_config()


def _get(path: str, default=None, required: bool = False):
    """ Достаёт значение из вложенного словаря по пути вида "bot.token". """
    value = _config
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            if required:
                sys.exit(f"В config.yaml не найден обязательный параметр: {path}")
            return default
        value = value[key]
    return value


BOT_TOKEN: str = _get("bot.token", required=True)
if BOT_TOKEN in (None, ""):
    sys.exit("Впиши свой токен бота в config.yaml (bot.token) — сейчас там заглушка.")

# --- Режим доступа: "all" — все пользователи, "admins" — только из admin_ids ---
ACCESS_MODE: str = _get("bot.access_mode", default="all")

# --- Список Telegram user_id администраторов (пригодится на этапе полировки) ---
ADMIN_IDS: list[int] = _get("bot.admin_ids", default=[])

# --- Путь к файлу SQLite базы данных ---
DB_PATH: str = _get("database.path", default="splitbot.db")
DATABASE_URL: str = f"sqlite+aiosqlite:///{DB_PATH}"   # Собираем строку подключения для SQLAlchemy (async-драйвер aiosqlite)

# --- Уровень логирования (используется в bot.py при настройке logging) ---
LOG_LEVEL: str = _get("logging.level", default="INFO")

# --- Лимиты для защиты от абьюза ---
MAX_PARTICIPANTS_PER_EVENT: int = _get("limits.max_participants_per_event", default=30)
MAX_EXPENSES_PER_EVENT: int = _get("limits.max_expenses_per_event", default=200)
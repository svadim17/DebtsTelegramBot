from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery

from database.db import async_session
from handlers.access import require_editor
from handlers.calculate import build_report_data
from keyboards.inline import export_menu_keyboard
from services.exporters import export_pdf, export_txt, export_xlsx

router = Router()

# Символы, недопустимые в именах файлов на Windows/macOS/Linux
_UNSAFE_FILENAME_CHARS = '/\\:*?"<>|'


def _safe_filename(title: str, extension: str) -> str:
    """Убирает из названия события символы, которые могут сломать имя файла
    (например, если в названии есть "/" — Telegram-клиент может некорректно
    его обработать)."""
    cleaned = "".join(ch for ch in title if ch not in _UNSAFE_FILENAME_CHARS).strip()
    return f"{cleaned or 'event'}.{extension}"


@router.callback_query(F.data.startswith("export:"))
async def show_export_menu(callback: CallbackQuery) -> None:
    event_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        if not await require_editor(session, callback, event_id):
            return

    await callback.message.edit_text(
        "В каком формате выгрузить отчёт?", reply_markup=export_menu_keyboard(event_id)
    )
    await callback.answer()


async def _load_report_or_none(callback: CallbackQuery, event_id: int) -> dict | None:
    """Общая часть для всех трёх форматов: проверка доступа + сбор данных.
    Возвращает None, если доступа нет или события не существует (в этом
    случае сама функция уже ответила пользователю)."""
    async with async_session() as session:
        if not await require_editor(session, callback, event_id):
            return None
        report = await build_report_data(session, event_id)

    if report["event"] is None:
        await callback.answer("Событие не найдено.", show_alert=True)
        return None

    return report


@router.callback_query(F.data.startswith("export_txt:"))
async def export_as_txt(callback: CallbackQuery) -> None:
    event_id = int(callback.data.split(":")[1])
    report = await _load_report_or_none(callback, event_id)
    if report is None:
        return

    text_content = export_txt(report)
    # Telegram отправляет файлы как байты — кодируем текст в UTF-8
    file = BufferedInputFile(
        text_content.encode("utf-8"), filename=_safe_filename(report["event"].title, "txt")
    )

    await callback.message.answer_document(file)
    await callback.answer()


@router.callback_query(F.data.startswith("export_xlsx:"))
async def export_as_xlsx(callback: CallbackQuery) -> None:
    event_id = int(callback.data.split(":")[1])
    report = await _load_report_or_none(callback, event_id)
    if report is None:
        return

    file_bytes = export_xlsx(report)
    file = BufferedInputFile(file_bytes, filename=_safe_filename(report["event"].title, "xlsx"))

    await callback.message.answer_document(file)
    await callback.answer()


@router.callback_query(F.data.startswith("export_pdf:"))
async def export_as_pdf(callback: CallbackQuery) -> None:
    event_id = int(callback.data.split(":")[1])
    report = await _load_report_or_none(callback, event_id)
    if report is None:
        return

    file_bytes = export_pdf(report)
    file = BufferedInputFile(file_bytes, filename=_safe_filename(report["event"].title, "pdf"))

    await callback.message.answer_document(file)
    await callback.answer()
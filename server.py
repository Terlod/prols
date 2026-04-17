import asyncio
import randomimport os
from dotenv import load_dotenv
from typing import Dict, List

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties  # <-- Новый импорт

# ------------------ Конфигурация ------------------

os.environ.get('API_TOKEN')

# ------------------ Хранилище данных ------------------
class Prole:
    def __init__(self, name: str, position: str):
        self.name = name
        self.position = position
        self.traits: List[str] = []

    def __str__(self):
        traits_str = ", ".join(self.traits) if self.traits else "нет черт"
        return f"👤 {self.name} | {self.position}\nЧерты: {traits_str}"


proles: List[Prole] = []
# Для каждого чата храним ID последнего выданного прола (индекс в списке)
last_shown_index: Dict[int, int] = {}


# ------------------ FSM для диалогов ------------------
class AddProleForm(StatesGroup):
    waiting_for_name = State()
    waiting_for_position = State()
    waiting_for_next = State()


class DeleteProlesForm(StatesGroup):
    waiting_for_names = State()


# Состояние для ввода черты (без класса, просто строка, но с фильтром)
TRAIT_WAITING_STATE = "trait_waiting"

# ------------------ Клавиатура управления ------------------
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Добавить прола")],
        [KeyboardButton(text="🎲 Случайный прол")],
        [KeyboardButton(text="✨ Добавить черту последнему")],
        [KeyboardButton(text="📋 Список пролов")],
        [KeyboardButton(text="❌ Удалить пролов")],
    ],
    resize_keyboard=True
)

cancel_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="❌ Отмена")]],
    resize_keyboard=True
)

# ------------------ Роутер ------------------
router = Router()


# ---------- Команда /start ----------
@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "🤖 Бот управления пролами\n\n"
        "Используйте кнопки или команды:\n"
        "/add — добавить одного прола\n"
        "/add_multiple — добавить несколько пролов\n"
        "/random — случайный прол\n"
        "/trait — добавить черту последнему выданному\n"
        "/list — список всех пролов\n"
        "/delete — удалить одного или нескольких пролов",
        reply_markup=main_kb
    )


# ---------- Обработка кнопок главного меню ----------
@router.message(F.text == "➕ Добавить прола")
async def add_prole_button(message: Message, state: FSMContext):
    await state.set_state(AddProleForm.waiting_for_name)
    await message.answer("Введите имя прола:", reply_markup=cancel_kb)


@router.message(F.text == "🎲 Случайный прол")
async def random_prole_button(message: Message):
    await cmd_random(message)


@router.message(F.text == "✨ Добавить черту последнему")
async def add_trait_button(message: Message, state: FSMContext):
    await start_trait_dialog(message, state)


@router.message(F.text == "📋 Список пролов")
async def list_proles_button(message: Message):
    await cmd_list(message)


@router.message(F.text == "❌ Удалить пролов")
async def delete_proles_button(message: Message, state: FSMContext):
    await state.set_state(DeleteProlesForm.waiting_for_names)
    await message.answer(
        "Введите имена пролов, которых нужно удалить, через запятую.\n"
        "Пример: Иван, Петр, Мария",
        reply_markup=cancel_kb
    )


@router.message(F.text == "❌ Отмена")
async def cancel_action(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()
    await message.answer("Действие отменено.", reply_markup=main_kb)


# ---------- Команда /add (один прол) ----------
@router.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext):
    await state.set_state(AddProleForm.waiting_for_name)
    await message.answer("Введите имя прола:", reply_markup=cancel_kb)


# ---------- FSM: добавление прола (один или batch) ----------
@router.message(StateFilter(AddProleForm.waiting_for_name))
async def process_name(message: Message, state: FSMContext):
    if message.text is None:
        await message.answer("Пожалуйста, введите текст.")
        return
    await state.update_data(temp_name=message.text.strip())
    await state.set_state(AddProleForm.waiting_for_position)
    await message.answer("Теперь введите должность:", reply_markup=cancel_kb)


@router.message(StateFilter(AddProleForm.waiting_for_position))
async def process_position(message: Message, state: FSMContext):
    if message.text is None:
        await message.answer("Пожалуйста, введите текст.")
        return
    data = await state.get_data()
    name = data.get("temp_name")
    position = message.text.strip()

    # Проверяем, в режиме ли multiple
    is_multiple = data.get("multiple", False)
    if is_multiple:
        batch = data.get("batch", [])
        batch.append({"name": name, "position": position})
        await state.update_data(batch=batch)
        await state.set_state(AddProleForm.waiting_for_name)
        await message.answer(
            f"✅ Запомнил: {name}, {position}\n"
            "Введите имя следующего прола или отправьте /done для завершения.",
            reply_markup=cancel_kb
        )
    else:
        proles.append(Prole(name, position))
        await state.clear()
        await message.answer(f"✅ Прол добавлен:\n{proles[-1]}", reply_markup=main_kb)


# ---------- Команда /add_multiple (несколько пролов) ----------
@router.message(Command("add_multiple"))
async def cmd_add_multiple(message: Message, state: FSMContext):
    await state.set_state(AddProleForm.waiting_for_name)
    await state.update_data(multiple=True, batch=[])
    await message.answer(
        "Начинаем добавление нескольких пролов.\n"
        "Введите имя первого прола (или /done для завершения):",
        reply_markup=cancel_kb
    )


@router.message(StateFilter(AddProleForm.waiting_for_name), Command("done"))
async def done_adding_multiple(message: Message, state: FSMContext):
    data = await state.get_data()
    batch = data.get("batch", [])
    if batch:
        for item in batch:
            proles.append(Prole(item["name"], item["position"]))
        await message.answer(f"✅ Добавлено пролов: {len(batch)}", reply_markup=main_kb)
    else:
        await message.answer("Ни одного прола не добавлено.", reply_markup=main_kb)
    await state.clear()


# ---------- Команда /random ----------
@router.message(Command("random"))
async def cmd_random(message: Message):
    if not proles:
        await message.answer("Список пролов пуст. Сначала добавьте кого-нибудь.")
        return
    idx = random.randrange(len(proles))
    last_shown_index[message.chat.id] = idx
    await message.answer(f"🎲 Случайный прол:\n{proles[idx]}")


# ---------- Добавление черты последнему выданному ----------
async def start_trait_dialog(message: Message, state: FSMContext):
    chat_id = message.chat.id
    if chat_id not in last_shown_index:
        await message.answer("Сначала получите случайного прола с помощью /random.")
        return
    idx = last_shown_index[chat_id]
    if idx >= len(proles):
        await message.answer("Последний выданный прол больше не существует.")
        return
    await state.update_data(trait_idx=idx)
    await state.set_state(TRAIT_WAITING_STATE)
    await message.answer(f"Введите черту для '{proles[idx].name}':", reply_markup=cancel_kb)


@router.message(Command("trait"))
async def cmd_trait(message: Message, command: CommandObject, state: FSMContext):
    # Если аргумент передан, добавляем сразу
    trait = command.args
    if trait:
        chat_id = message.chat.id
        if chat_id not in last_shown_index:
            await message.answer("Сначала получите случайного прола с помощью /random.")
            return
        idx = last_shown_index[chat_id]
        if idx >= len(proles):
            await message.answer("Последний выданный прол больше не существует.")
            return
        proles[idx].traits.append(trait.strip())
        await message.answer(f"✅ Черта '{trait}' добавлена пролу '{proles[idx].name}'.")
    else:
        # Если без аргумента — запускаем диалог
        await start_trait_dialog(message, state)


@router.message(F.text, StateFilter(TRAIT_WAITING_STATE))
async def trait_received(message: Message, state: FSMContext):
    data = await state.get_data()
    idx = data["trait_idx"]
    trait = message.text.strip()
    proles[idx].traits.append(trait)
    await state.clear()
    await message.answer(f"✅ Черта '{trait}' добавлена.", reply_markup=main_kb)


# ---------- Команда /list ----------
@router.message(Command("list"))
async def cmd_list(message: Message):
    if not proles:
        await message.answer("Список пролов пуст.")
        return
    text = "📋 Список пролов:\n\n"
    for i, p in enumerate(proles, 1):
        text += f"{i}. {p}\n\n"
    await message.answer(text)


# ---------- Удаление пролов ----------
@router.message(Command("delete"))
async def cmd_delete(message: Message, command: CommandObject):
    args = command.args
    if not args:
        await message.answer("Укажите имена для удаления через запятую.\nПример: /delete Иван, Петр")
        return
    names = [n.strip() for n in args.split(",") if n.strip()]
    deleted_count = delete_proles_by_names(names)
    if deleted_count:
        await message.answer(f"✅ Удалено пролов: {deleted_count}")
    else:
        await message.answer("❌ Ни один из указанных пролов не найден.")


@router.message(StateFilter(DeleteProlesForm.waiting_for_names))
async def process_delete_names(message: Message, state: FSMContext):
    if message.text is None:
        await message.answer("Введите имена.")
        return
    names = [n.strip() for n in message.text.split(",") if n.strip()]
    deleted_count = delete_proles_by_names(names)
    await state.clear()
    if deleted_count:
        await message.answer(f"✅ Удалено пролов: {deleted_count}", reply_markup=main_kb)
    else:
        await message.answer("❌ Ни один из указанных пролов не найден.", reply_markup=main_kb)


def delete_proles_by_names(names: List[str]) -> int:
    """Удаляет пролов по списку имён (регистронезависимо) и возвращает количество удалённых."""
    global proles
    deleted = 0
    for name in names:
        for i, p in enumerate(proles):
            if p.name.lower() == name.lower():
                del proles[i]
                deleted += 1
                break  # удаляем только первого с таким именем
    return deleted


# ---------- Основная функция запуска ----------
async def main():
    # Новый способ задания параметров по умолчанию (aiogram >= 3.7.0)
    bot = Bot(
        token=API_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    # Используем хранилище в памяти (MemoryStorage) для состояний FSM
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    dp.include_router(router)

    # Запускаем поллинг
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

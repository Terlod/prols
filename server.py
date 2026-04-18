import asyncio
import random
import os
from typing import Dict, List

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# ------------------ Конфигурация ------------------
API_TOKEN = os.environ.get('API_TOKEN')
if not API_TOKEN:
    raise ValueError("Не задан API_TOKEN в переменных окружения")

# ------------------ Хранилище данных ------------------
class Prole:
    def __init__(self, name: str, position: str):
        self.name = name
        self.position = position
        self.traits: List[str] = []

    def __str__(self):
        traits_str = ", ".join(self.traits) if self.traits else "нет черт"
        return f"👤 {self.name} | {self.position}\nЧерты: {traits_str}"

# Данные для каждого чата отдельно
chat_proles: Dict[int, List[Prole]] = {}
chat_last_shown: Dict[int, int] = {}

def get_proles(chat_id: int) -> List[Prole]:
    if chat_id not in chat_proles:
        chat_proles[chat_id] = []
    return chat_proles[chat_id]

# ------------------ FSM для диалогов ------------------
class AddProleForm(StatesGroup):
    waiting_for_name = State()
    waiting_for_position = State()
    waiting_for_next = State()

class DeleteProlesForm(StatesGroup):
    waiting_for_names = State()

class SearchProleForm(StatesGroup):
    waiting_for_query = State()

TRAIT_WAITING_STATE = "trait_waiting"

# ------------------ Inline‑клавиатуры ------------------
def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить прола", callback_data="add_prole")],
            [InlineKeyboardButton(text="🎲 Случайный прол", callback_data="random")],
            [InlineKeyboardButton(text="✨ Добавить черту последнему", callback_data="add_trait")],
            [InlineKeyboardButton(text="📋 Список пролов", callback_data="list")],
            [InlineKeyboardButton(text="🔍 Найти прола", callback_data="search")],
            [InlineKeyboardButton(text="❌ Удалить пролов", callback_data="delete")],
        ]
    )

def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")],
        ]
    )

def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ В главное меню", callback_data="back_to_menu")],
        ]
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
        "/search — найти прола по имени\n"
        "/delete — удалить одного или нескольких пролов",
        reply_markup=main_menu_keyboard()
    )

# ---------- Возврат в главное меню ----------
@router.callback_query(F.data == "back_to_menu")
async def back_to_menu_callback(callback: CallbackQuery):
    await callback.message.edit_text(
        "🤖 Главное меню",
        reply_markup=main_menu_keyboard()
    )
    await callback.answer()

# ---------- Обработчики inline‑кнопок главного меню ----------
@router.callback_query(F.data == "add_prole")
async def add_prole_callback(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddProleForm.waiting_for_name)
    await callback.message.edit_text("Введите имя прола:", reply_markup=cancel_keyboard())
    await callback.answer()

@router.callback_query(F.data == "random")
async def random_prole_callback(callback: CallbackQuery):
    await cmd_random_callback(callback)
    await callback.answer()

@router.callback_query(F.data == "add_trait")
async def add_trait_callback(callback: CallbackQuery, state: FSMContext):
    await start_trait_dialog_callback(callback, state)
    await callback.answer()

@router.callback_query(F.data == "list")
async def list_proles_callback(callback: CallbackQuery):
    await cmd_list_callback(callback)
    await callback.answer()

@router.callback_query(F.data == "search")
async def search_prole_callback(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SearchProleForm.waiting_for_query)
    await callback.message.edit_text(
        "🔍 Введите имя или часть имени прола для поиска:",
        reply_markup=cancel_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "delete")
async def delete_proles_callback(callback: CallbackQuery, state: FSMContext):
    await state.set_state(DeleteProlesForm.waiting_for_names)
    await callback.message.edit_text(
        "Введите имена пролов, которых нужно удалить, через запятую.\n"
        "Пример: Иван, Петр, Мария",
        reply_markup=cancel_keyboard()
    )
    await callback.answer()

# Универсальная отмена из любого состояния через inline‑кнопку
@router.callback_query(F.data == "cancel_action")
async def cancel_action_callback(callback: CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()
    await callback.message.edit_text("Действие отменено.", reply_markup=main_menu_keyboard())
    await callback.answer()

# Также оставим команду /cancel для текстовой отмены
@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()
    await message.answer("Действие отменено.", reply_markup=main_menu_keyboard())

# ---------- Команда /add ----------
@router.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext):
    await state.set_state(AddProleForm.waiting_for_name)
    await message.answer("Введите имя прола:", reply_markup=cancel_keyboard())

# ---------- FSM: добавление одного прола ----------
@router.message(StateFilter(AddProleForm.waiting_for_name))
async def process_name(message: Message, state: FSMContext):
    if message.text is None:
        await message.answer("Пожалуйста, введите текст.")
        return
    await state.update_data(temp_name=message.text.strip())
    await state.set_state(AddProleForm.waiting_for_position)
    await message.answer("Теперь введите должность:", reply_markup=cancel_keyboard())

@router.message(StateFilter(AddProleForm.waiting_for_position))
async def process_position(message: Message, state: FSMContext):
    if message.text is None:
        await message.answer("Пожалуйста, введите текст.")
        return
    data = await state.get_data()
    name = data.get("temp_name")
    position = message.text.strip()
    chat_id = message.chat.id
    proles = get_proles(chat_id)

    is_multiple = data.get("multiple", False)
    if is_multiple:
        batch = data.get("batch", [])
        batch.append({"name": name, "position": position})
        await state.update_data(batch=batch)
        await state.set_state(AddProleForm.waiting_for_name)
        await message.answer(
            f"✅ Запомнил: {name}, {position}\n"
            "Введите имя следующего прола или отправьте /done для завершения.",
            reply_markup=cancel_keyboard()
        )
    else:
        proles.append(Prole(name, position))
        await state.clear()
        await message.answer(f"✅ Прол добавлен:\n{proles[-1]}", reply_markup=main_menu_keyboard())

# ---------- Команда /add_multiple ----------
@router.message(Command("add_multiple"))
async def cmd_add_multiple(message: Message, state: FSMContext):
    await state.set_state(AddProleForm.waiting_for_name)
    await state.update_data(multiple=True, batch=[])
    await message.answer(
        "Начинаем добавление нескольких пролов.\n"
        "Введите имя первого прола (или /done для завершения):",
        reply_markup=cancel_keyboard()
    )

@router.message(StateFilter(AddProleForm.waiting_for_name), Command("done"))
async def done_adding_multiple(message: Message, state: FSMContext):
    data = await state.get_data()
    batch = data.get("batch", [])
    chat_id = message.chat.id
    proles = get_proles(chat_id)
    if batch:
        for item in batch:
            proles.append(Prole(item["name"], item["position"]))
        await message.answer(f"✅ Добавлено пролов: {len(batch)}", reply_markup=main_menu_keyboard())
    else:
        await message.answer("Ни одного прола не добавлено.", reply_markup=main_menu_keyboard())
    await state.clear()

# ---------- Команда /random ----------
@router.message(Command("random"))
async def cmd_random(message: Message):
    chat_id = message.chat.id
    proles = get_proles(chat_id)
    if not proles:
        await message.answer("Список пролов пуст. Сначала добавьте кого-нибудь.")
        return
    idx = random.randrange(len(proles))
    chat_last_shown[chat_id] = idx
    await message.answer(
        f"🎲 Случайный прол:\n{proles[idx]}",
        reply_markup=prole_actions_keyboard(idx)
    )

async def cmd_random_callback(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    proles = get_proles(chat_id)
    if not proles:
        await callback.message.edit_text(
            "Список пролов пуст. Сначала добавьте кого-нибудь.",
            reply_markup=main_menu_keyboard()
        )
        return
    idx = random.randrange(len(proles))
    chat_last_shown[chat_id] = idx
    await callback.message.edit_text(
        f"🎲 Случайный прол:\n{proles[idx]}",
        reply_markup=prole_actions_keyboard(idx)
    )

# ---------- Добавление черты ----------
def prole_actions_keyboard(idx: int) -> InlineKeyboardMarkup:
    """Клавиатура с действиями над конкретным пролом."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✨ Добавить черту", callback_data=f"add_trait_to:{idx}")],
            [InlineKeyboardButton(text="◀️ В главное меню", callback_data="back_to_menu")],
        ]
    )

async def start_trait_dialog(message: Message, state: FSMContext):
    chat_id = message.chat.id
    proles = get_proles(chat_id)
    if chat_id not in chat_last_shown:
        await message.answer("Сначала получите случайного прола с помощью /random.")
        return
    idx = chat_last_shown[chat_id]
    if idx >= len(proles):
        await message.answer("Последний выданный прол больше не существует.")
        return
    await state.update_data(trait_idx=idx)
    await state.set_state(TRAIT_WAITING_STATE)
    await message.answer(f"Введите черту для '{proles[idx].name}':", reply_markup=cancel_keyboard())

async def start_trait_dialog_callback(callback: CallbackQuery, state: FSMContext):
    chat_id = callback.message.chat.id
    proles = get_proles(chat_id)
    if chat_id not in chat_last_shown:
        await callback.message.edit_text(
            "Сначала получите случайного прола с помощью /random.",
            reply_markup=main_menu_keyboard()
        )
        return
    idx = chat_last_shown[chat_id]
    if idx >= len(proles):
        await callback.message.edit_text(
            "Последний выданный прол больше не существует.",
            reply_markup=main_menu_keyboard()
        )
        return
    await state.update_data(trait_idx=idx)
    await state.set_state(TRAIT_WAITING_STATE)
    await callback.message.edit_text(
        f"Введите черту для '{proles[idx].name}':",
        reply_markup=cancel_keyboard()
    )

@router.message(Command("trait"))
async def cmd_trait(message: Message, command: CommandObject, state: FSMContext):
    trait = command.args
    chat_id = message.chat.id
    proles = get_proles(chat_id)
    if trait:
        if chat_id not in chat_last_shown:
            await message.answer("Сначала получите случайного прола с помощью /random.")
            return
        idx = chat_last_shown[chat_id]
        if idx >= len(proles):
            await message.answer("Последний выданный прол больше не существует.")
            return
        proles[idx].traits.append(trait.strip())
        await message.answer(
            f"✅ Черта '{trait}' добавлена пролу '{proles[idx].name}'.",
            reply_markup=main_menu_keyboard()
        )
    else:
        await start_trait_dialog(message, state)

@router.message(F.text, StateFilter(TRAIT_WAITING_STATE))
async def trait_received(message: Message, state: FSMContext):
    data = await state.get_data()
    idx = data["trait_idx"]
    trait = message.text.strip()
    chat_id = message.chat.id
    proles = get_proles(chat_id)
    if idx >= len(proles):
        await state.clear()
        await message.answer("Прол не найден.", reply_markup=main_menu_keyboard())
        return
    proles[idx].traits.append(trait)
    await state.clear()
    await message.answer(f"✅ Черта '{trait}' добавлена.", reply_markup=main_menu_keyboard())

# Добавление черты конкретному пролу через callback (из поиска или случайного)
@router.callback_query(F.data.startswith("add_trait_to:"))
async def add_trait_to_callback(callback: CallbackQuery, state: FSMContext):
    idx_str = callback.data.split(":")[1]
    try:
        idx = int(idx_str)
    except ValueError:
        await callback.answer("Некорректный индекс.", show_alert=True)
        return
    chat_id = callback.message.chat.id
    proles = get_proles(chat_id)
    if idx >= len(proles):
        await callback.answer("Прол не найден.", show_alert=True)
        return
    await state.update_data(trait_idx=idx)
    await state.set_state(TRAIT_WAITING_STATE)
    await callback.message.edit_text(
        f"Введите черту для '{proles[idx].name}':",
        reply_markup=cancel_keyboard()
    )
    await callback.answer()

# ---------- Команда /list ----------
@router.message(Command("list"))
async def cmd_list(message: Message):
    chat_id = message.chat.id
    proles = get_proles(chat_id)
    if not proles:
        await message.answer("Список пролов пуст.")
        return
    text = "📋 Список пролов:\n\n"
    for i, p in enumerate(proles, 1):
        text += f"{i}. {p}\n\n"
    await message.answer(text, reply_markup=main_menu_keyboard())

async def cmd_list_callback(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    proles = get_proles(chat_id)
    if not proles:
        await callback.message.edit_text("Список пролов пуст.", reply_markup=main_menu_keyboard())
        return
    text = "📋 Список пролов:\n\n"
    for i, p in enumerate(proles, 1):
        text += f"{i}. {p}\n\n"
    await callback.message.edit_text(text, reply_markup=main_menu_keyboard())

# ---------- Поиск прола по имени ----------
@router.message(StateFilter(SearchProleForm.waiting_for_query))
async def process_search_query(message: Message, state: FSMContext):
    query = message.text.strip().lower()
    chat_id = message.chat.id
    proles = get_proles(chat_id)
    if not proles:
        await message.answer("Список пролов пуст.", reply_markup=main_menu_keyboard())
        await state.clear()
        return

    # Ищем пролов, содержащих запрос в имени (регистронезависимо)
    matches = [(idx, p) for idx, p in enumerate(proles) if query in p.name.lower()]
    if not matches:
        await message.answer(
            f"🔍 По запросу «{message.text.strip()}» ничего не найдено.",
            reply_markup=main_menu_keyboard()
        )
        await state.clear()
        return

    if len(matches) == 1:
        # Если найден один – сразу показываем его карточку
        idx, prole = matches[0]
        chat_last_shown[chat_id] = idx
        await message.answer(
            f"🔍 Найден прол:\n{prole}",
            reply_markup=prole_actions_keyboard(idx)
        )
    else:
        # Несколько совпадений – показываем список для выбора
        kb_buttons = []
        for idx, prole in matches:
            kb_buttons.append([
                InlineKeyboardButton(
                    text=f"{prole.name} ({prole.position})",
                    callback_data=f"show_prole:{idx}"
                )
            ])
        kb_buttons.append([InlineKeyboardButton(text="◀️ В главное меню", callback_data="back_to_menu")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=kb_buttons)
        await message.answer(
            f"🔍 Найдено совпадений: {len(matches)}. Выберите прола:",
            reply_markup=keyboard
        )
    await state.clear()

@router.callback_query(F.data.startswith("show_prole:"))
async def show_prole_callback(callback: CallbackQuery):
    idx_str = callback.data.split(":")[1]
    try:
        idx = int(idx_str)
    except ValueError:
        await callback.answer("Некорректный индекс.", show_alert=True)
        return
    chat_id = callback.message.chat.id
    proles = get_proles(chat_id)
    if idx >= len(proles):
        await callback.answer("Прол не найден.", show_alert=True)
        return
    chat_last_shown[chat_id] = idx
    await callback.message.edit_text(
        f"👤 {proles[idx]}",
        reply_markup=prole_actions_keyboard(idx)
    )
    await callback.answer()

# ---------- Удаление пролов ----------
@router.message(Command("delete"))
async def cmd_delete(message: Message, command: CommandObject):
    args = command.args
    if not args:
        await message.answer("Укажите имена для удаления через запятую.\nПример: /delete Иван, Петр")
        return
    names = [n.strip() for n in args.split(",") if n.strip()]
    chat_id = message.chat.id
    deleted_count = delete_proles_by_names(chat_id, names)
    if deleted_count:
        await message.answer(f"✅ Удалено пролов: {deleted_count}", reply_markup=main_menu_keyboard())
    else:
        await message.answer("❌ Ни один из указанных пролов не найден.", reply_markup=main_menu_keyboard())

@router.message(StateFilter(DeleteProlesForm.waiting_for_names))
async def process_delete_names(message: Message, state: FSMContext):
    if message.text is None:
        await message.answer("Введите имена.")
        return
    names = [n.strip() for n in message.text.split(",") if n.strip()]
    chat_id = message.chat.id
    deleted_count = delete_proles_by_names(chat_id, names)
    await state.clear()
    if deleted_count:
        await message.answer(f"✅ Удалено пролов: {deleted_count}", reply_markup=main_menu_keyboard())
    else:
        await message.answer("❌ Ни один из указанных пролов не найден.", reply_markup=main_menu_keyboard())

def delete_proles_by_names(chat_id: int, names: List[str]) -> int:
    proles = get_proles(chat_id)
    deleted = 0
    for name in names:
        for i, p in enumerate(proles):
            if p.name.lower() == name.lower():
                del proles[i]
                deleted += 1
                break
    return deleted

# ---------- Основная функция запуска ----------
async def main():
    bot = Bot(
        token=API_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

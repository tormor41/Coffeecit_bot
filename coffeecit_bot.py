import logging
import json
import os
import re
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    ReplyKeyboardRemove
)
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота
API_TOKEN = 'id bot'  # Замените на реальный токен
bot = Bot(
    token=API_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Файлы для хранения данных
USERS_FILE = 'users.json'
PROMOTIONS_FILE = 'promotions.json'
ADMINS_FILE = 'admins.json'


# Состояния для FSM
class UserStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()


class AdminStates(StatesGroup):
    add_promotion_title = State()
    add_promotion_desc = State()
    add_discount = State()
    find_user = State()


# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def load_data(filename, default=dict):
    if not os.path.exists(filename):
        return default()
    with open(filename, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return default()


def save_data(data, filename):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


async def show_main_menu(message: Message):
    """Показывает главное меню"""
    users = load_data(USERS_FILE)
    admins = load_data(ADMINS_FILE)
    user_id = str(message.from_user.id)

    buttons = [
        [KeyboardButton(text="🎁 Акции")],
        [KeyboardButton(text="💳 Моя скидка")]
    ]

    if user_id in users:
        buttons.append([KeyboardButton(text="📞 Мой профиль")])
        if user_id in admins:
            buttons.append([KeyboardButton(text="⚙️ Админка")])
    else:
        buttons.append([KeyboardButton(text="/start")])

    keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
    await message.answer("Главное меню:", reply_markup=keyboard)


# ========== ОСНОВНЫЕ КОМАНДЫ ==========
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    users = load_data(USERS_FILE)

    if user_id not in users:
        await state.set_state(UserStates.waiting_for_name)
        await message.answer(
            "👋 Добро пожаловать в нашу кофейню! Пожалуйста, введите ваше имя:",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        await message.answer("☕ С возвращением!")
        await show_main_menu(message)


@dp.message(UserStates.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(UserStates.waiting_for_phone)
    await message.answer(
        "📱 Введите ваш номер телефона (в формате +79991234567):",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отправить номер", request_contact=True)]],
            resize_keyboard=True
        )
    )


@dp.message(UserStates.waiting_for_phone)
async def process_phone(message: Message, state: FSMContext):
    phone = message.contact.phone_number if message.contact else message.text

    if not re.match(r'^\+?\d{10,15}$', phone):
        await message.answer("❌ Неверный формат номера. Попробуйте еще раз:")
        return

    data = await state.get_data()
    user_id = str(message.from_user.id)

    users = load_data(USERS_FILE)
    users[user_id] = {
        'name': data['name'],
        'phone': phone,
        'discount': 0,
        'registration_date': message.date.isoformat()
    }
    save_data(users, USERS_FILE)

    await message.answer(
        "✅ Регистрация завершена!",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.clear()
    await show_main_menu(message)


# ========== ФУНКЦИОНАЛ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ ==========
@dp.message(lambda message: message.text == "🎁 Акции")
async def show_promotions(message: Message):
    promotions = load_data(PROMOTIONS_FILE)

    if not promotions:
        await message.answer("Сейчас нет активных акций.")
        return

    response = "🔥 Текущие акции:\n\n"
    for promo_id, promo in promotions.items():
        response += f"🎁 <b>{promo['title']}</b>\n{promo['description']}\n\n"

    await message.answer(response)


@dp.message(lambda message: message.text == "💳 Моя скидка")
async def show_discount(message: Message):
    user_id = str(message.from_user.id)
    users = load_data(USERS_FILE)

    if user_id not in users:
        await message.answer("❌ Вы не зарегистрированы. Нажмите /start")
        return

    discount = users[user_id].get('discount', 0)
    await message.answer(f"✅ Ваша текущая скидка: {discount}%")


@dp.message(lambda message: message.text == "📞 Мой профиль")
async def show_profile(message: Message):
    user_id = str(message.from_user.id)
    users = load_data(USERS_FILE)

    if user_id not in users:
        await message.answer("❌ Вы не зарегистрированы. Нажмите /start")
        return

    user = users[user_id]
    response = (
        "👤 Ваш профиль:\n\n"
        f"📌 Имя: {user.get('name', 'не указано')}\n"
        f"📱 Телефон: {user.get('phone', 'не указан')}\n"
        f"🎁 Скидка: {user.get('discount', 0)}%\n"
        f"📅 Дата регистрации: {user.get('registration_date', 'неизвестно')}"
    )
    await message.answer(response)


# ========== АДМИН-ПАНЕЛЬ ==========
@dp.message(lambda message: message.text == "⚙️ Админка")
async def admin_panel(message: Message):
    user_id = str(message.from_user.id)
    admins = load_data(ADMINS_FILE)

    if user_id not in admins:
        await message.answer("❌ У вас нет доступа!")
        return

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить акцию")],
            [KeyboardButton(text="👥 Управление клиентами")],
            [KeyboardButton(text="🔙 Назад")]
        ],
        resize_keyboard=True
    )
    await message.answer("⚙️ Админ-панель:", reply_markup=keyboard)


@dp.message(lambda message: message.text == "➕ Добавить акцию")
async def add_promotion_start(message: Message, state: FSMContext):
    admins = load_data(ADMINS_FILE)
    if str(message.from_user.id) not in admins:
        return

    await state.set_state(AdminStates.add_promotion_title)
    await message.answer("Введите название акции:")


@dp.message(AdminStates.add_promotion_title)
async def add_promotion_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(AdminStates.add_promotion_desc)
    await message.answer("Теперь введите описание акции:")


@dp.message(AdminStates.add_promotion_desc)
async def add_promotion_desc(message: Message, state: FSMContext):
    data = await state.get_data()

    promotions = load_data(PROMOTIONS_FILE)
    promo_id = str(len(promotions) + 1)
    promotions[promo_id] = {
        'title': data['title'],
        'description': message.text
    }
    save_data(promotions, PROMOTIONS_FILE)

    await message.answer("✅ Акция добавлена!")
    await state.clear()
    await admin_panel(message)


@dp.message(lambda message: message.text == "👥 Управление клиентами")
async def manage_clients(message: Message):
    admins = load_data(ADMINS_FILE)
    if str(message.from_user.id) not in admins:
        return

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Список клиентов")],
            [KeyboardButton(text="🔍 Найти по номеру")],
            [KeyboardButton(text="🎁 Дать скидку")],
            [KeyboardButton(text="🔙 Назад")]
        ],
        resize_keyboard=True
    )
    await message.answer("👥 Управление клиентами:", reply_markup=keyboard)


@dp.message(lambda message: message.text == "📋 Список клиентов")
async def show_clients(message: Message):
    users = load_data(USERS_FILE)

    if not users:
        await message.answer("❌ Нет зарегистрированных клиентов.")
        return

    response = "📋 Клиенты:\n\n"
    for user_id, user in users.items():
        response += f"👤 {user.get('name')} - {user.get('phone')} - Скидка: {user.get('discount', 0)}%\n"

    await message.answer(response[:4000])  # Ограничение длины


@dp.message(lambda message: message.text == "🔍 Найти по номеру")
async def find_client_start(message: Message, state: FSMContext):
    await state.set_state(AdminStates.find_user)
    await message.answer("Введите номер телефона:")


@dp.message(AdminStates.find_user)
async def find_client(message: Message, state: FSMContext):
    phone = message.text.strip()
    users = load_data(USERS_FILE)

    found = []
    for user_id, user in users.items():
        if user.get('phone') == phone:
            found.append(user)

    if not found:
        await message.answer("❌ Клиент не найден")
    else:
        response = "🔍 Результаты:\n\n"
        for user in found:
            response += f"👤 {user.get('name')} (ID: {user_id})\n📱 {user.get('phone')}\n🎁 Скидка: {user.get('discount', 0)}%\n\n"

        await message.answer(response)

    await state.clear()


@dp.message(lambda message: message.text == "🎁 Дать скидку")
async def add_discount_start(message: Message, state: FSMContext):
    await state.set_state(AdminStates.add_discount)
    await message.answer("Введите ID пользователя и размер скидки (например: 123456789 10):")


@dp.message(AdminStates.add_discount)
async def add_discount(message: Message, state: FSMContext):
    try:
        user_id, discount = message.text.split()
        discount = int(discount)

        if not 0 <= discount <= 100:
            raise ValueError

        users = load_data(USERS_FILE)
        if user_id not in users:
            await message.answer("❌ Пользователь не найден")
            return

        users[user_id]['discount'] = discount
        save_data(users, USERS_FILE)
        await message.answer(f"✅ Пользователю {users[user_id].get('name')} установлена скидка {discount}%")

    except (ValueError, IndexError):
        await message.answer("❌ Неверный формат. Пример: 123456789 10")

    await state.clear()


@dp.message(lambda message: message.text == "🔙 Назад")
async def back_to_menu(message: Message):
    await show_main_menu(message)


# ========== ЗАПУСК БОТА ==========
async def main():
    # Создаем файлы если их нет
    for filename in [USERS_FILE, PROMOTIONS_FILE, ADMINS_FILE]:
        if not os.path.exists(filename):
            save_data({}, filename)

    # Добавляем первого админа
    admins = load_data(ADMINS_FILE)
    if not admins:
        admins[str(id tg)] = True  # Замените на ваш ID
        save_data(admins, ADMINS_FILE)

    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())

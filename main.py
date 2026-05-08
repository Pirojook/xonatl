import json
import logging
import asyncio
import os
import sys
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from datetime import datetime

from db import db  # Импортируем нашу базу данных
from bill import billing

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Конфигурация
API_TOKEN = '8350331260:AAFCMbZz2WsFes2DU-FNSKYP2a35-tsZFQw'
GROUP_CHAT_ID = -1003065380323  # ID группы для отправки заказов

# Список администраторов (замените на реальные ID)
ADMIN_IDS = [6828316648, 512534440]  # Добавьте сюда свой Telegram ID

# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Загрузка меню из JSON и импорт в базу данных
try:
    with open('menu.json', 'r', encoding='utf-8') as f:
        menu_data = json.load(f)
        db.import_menu_from_json(menu_data)
        logging.info("Меню успешно импортировано в базу данных")
except FileNotFoundError:
    logging.error("Файл menu.json не найден")

# Состояния FSM для основного бота
class OrderStates(StatesGroup):
    waiting_for_table_number = State()
    selecting_category = State()
    selecting_item = State()
    adding_quantity = State()
    preview_order = State()
    editing_order = State()
    adding_comment = State()

# Состояния для админ-панели
class AdminStates(StatesGroup):
    admin_menu = State()
    waiting_for_category_name = State()
    waiting_for_item_name = State()
    waiting_for_item_price = State()
    waiting_for_category_select = State()
    waiting_for_item_select = State()
    waiting_for_edit_name = State()
    waiting_for_edit_price = State()

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# Функция проверки прав администратора
def is_admin(user_id):
    return user_id in ADMIN_IDS

# Функция для форматирования цены в сумы
def format_price(price):
    return f"{int(price):,}".replace(",", " ") + " сум"

# Функция для экранирования специальных символов Markdown
def escape_markdown(text):
    if not text:
        return ""
    # Экранируем все специальные символы MarkdownV2
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    result = ""
    for char in str(text):
        if char in escape_chars:
            result += '\\' + char
        else:
            result += char
    return result

# Главное меню
@dp.message(Command("start", "menu"))
async def show_main_menu(message: types.Message):
    # Регистрируем официанта в базе данных
    waiter_id = db.add_waiter(message.from_user.id, message.from_user.full_name)
    
    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text="📋 Создать новый заказ"))
    builder.add(types.KeyboardButton(text="👀 Посмотреть активные заказы"))
    builder.adjust(2)
    
    await message.answer(
        "🍽️ *Добро пожаловать в систему заказов ресторана!*\n\n"
        "Выберите действие:",
        reply_markup=builder.as_markup(resize_keyboard=True),
        parse_mode='Markdown'
    )

# Команда для входа в админ-панель
@dp.message(Command("admin"))
async def admin_panel(message: types.Message, state: FSMContext):
    
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Просмотреть меню", callback_data="admin_view_menu")
    builder.button(text="➕ Добавить категорию", callback_data="admin_add_category")
    builder.button(text="➖ Удалить категорию", callback_data="admin_del_category")
    builder.button(text="🍽️ Добавить блюдо", callback_data="admin_add_item")
    builder.button(text="✏️ Редактировать блюдо", callback_data="admin_edit_item")
    builder.button(text="🗑 Удалить блюдо", callback_data="admin_delete_item")
    builder.button(text="🔄 Обновить меню в БД", callback_data="admin_refresh_menu")
    builder.button(text="❌ Закрыть", callback_data="admin_close")
    builder.adjust(2)
    
    await state.set_state(AdminStates.admin_menu)
    await message.answer(
        "👨‍💼 *Админ-панель управления меню*\n\n"
        "Выберите действие:",
        reply_markup=builder.as_markup(),
        parse_mode='Markdown'
    )

# Просмотр меню
@dp.callback_query(F.data == "admin_view_menu", AdminStates.admin_menu)
async def admin_view_menu(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        with open(resource_path("menu.json"), "r", encoding="utf-8") as f:
            menu_data = json.load(f)
        
        message_text = "📋 *ТЕКУЩЕЕ МЕНЮ*\n\n"
        
        for category in menu_data['menu']:
            message_text += f"*{category['category']}*\n"
            for item in category['items']:
                message_text += f"  • {item['name']} - {format_price(item['price'])}\n"
            message_text += "\n"
        
        # Кнопка назад
        builder = InlineKeyboardBuilder()
        builder.button(text="◀️ Назад в админ-панель", callback_data="admin_back")
        
        await callback_query.message.edit_text(
            message_text,
            reply_markup=builder.as_markup(),
            parse_mode='Markdown'
        )
    except Exception as e:
        await callback_query.answer(f"Ошибка: {str(e)}")

# Добавление категории
@dp.callback_query(F.data == "admin_add_category", AdminStates.admin_menu)
async def admin_add_category_start(callback_query: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_category_name)
    await callback_query.message.edit_text(
        "📝 *Введите название новой категории:*\n\n"
        "(или отправьте /cancel для отмены)",
        parse_mode='Markdown'
    )

@dp.message(AdminStates.waiting_for_category_name)
async def admin_add_category_process(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Добавление категории отменено")
        return
    
    category_name = message.text.strip()
    
    try:
        with open('menu.json', 'r', encoding='utf-8') as f:
            menu_data = json.load(f)
        
        # Проверяем, существует ли уже такая категория
        for category in menu_data['menu']:
            if category['category'].lower() == category_name.lower():
                await message.answer("❌ Такая категория уже существует!")
                return
        
        # Добавляем новую категорию
        menu_data['menu'].append({
            "category": category_name,
            "items": []
        })
        
        with open('menu.json', 'w', encoding='utf-8') as f:
            json.dump(menu_data, f, ensure_ascii=False, indent=2)
        
        await message.answer(f"✅ Категория *{category_name}* успешно добавлена!\n\nНе забудьте обновить меню в БД командой /admin → 'Обновить меню в БД'", parse_mode='Markdown')
        
        # Возвращаемся в админ-панель
        await admin_panel(message, state)
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

# Удаление категории
@dp.callback_query(F.data == "admin_del_category", AdminStates.admin_menu)
async def admin_delete_category_start(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        with open('menu.json', 'r', encoding='utf-8') as f:
            menu_data = json.load(f)
        
        builder = InlineKeyboardBuilder()
        for category in menu_data['menu']:
            builder.button(
                text=f"🗑 {category['category']}",
                callback_data=f"delcat_{category['category']}"
            )
        builder.button(text="◀️ Назад", callback_data="admin_back")
        builder.adjust(2)
        
        await state.set_state(AdminStates.waiting_for_category_select)
        await callback_query.message.edit_text(
            "🗑 *Выберите категорию для удаления:*\n\n"
            "⚠️ Внимание: все блюда в этой категории будут удалены!",
            reply_markup=builder.as_markup(),
            parse_mode='Markdown'
        )
    except Exception as e:
        await callback_query.answer(f"Ошибка: {str(e)}")

@dp.callback_query(F.data.startswith("delcat_"), AdminStates.waiting_for_category_select)
async def admin_delete_category_process(callback_query: types.CallbackQuery, state: FSMContext):
    category_name = callback_query.data.replace("delcat_", "")
    
    try:
        with open('menu.json', 'r', encoding='utf-8') as f:
            menu_data = json.load(f)
        
        # Удаляем категорию
        menu_data['menu'] = [cat for cat in menu_data['menu'] if cat['category'] != category_name]
        
        with open('menu.json', 'w', encoding='utf-8') as f:
            json.dump(menu_data, f, ensure_ascii=False, indent=2)
        
        await callback_query.answer(f"✅ Категория удалена")
        await callback_query.message.edit_text(
            f"✅ Категория *{category_name}* успешно удалена!\n\nНе забудьте обновить меню в БД",
            parse_mode='Markdown'
        )
        
        # Возвращаемся в админ-панель
        await admin_panel(callback_query.message, state)
        
    except Exception as e:
        await callback_query.answer(f"Ошибка: {str(e)}")

# Добавление блюда
@dp.callback_query(F.data == "admin_add_item", AdminStates.admin_menu)
async def admin_add_item_category_select(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        with open('menu.json', 'r', encoding='utf-8') as f:
            menu_data = json.load(f)
        
        builder = InlineKeyboardBuilder()
        for category in menu_data['menu']:
            builder.button(
                text=f"➕ {category['category']}",
                callback_data=f"additemcat_{category['category']}"
            )
        builder.button(text="◀️ Назад", callback_data="admin_back")
        builder.adjust(2)
        
        await state.set_state(AdminStates.waiting_for_category_select)
        await callback_query.message.edit_text(
            "🍽️ *Выберите категорию для добавления блюда:*",
            reply_markup=builder.as_markup(),
            parse_mode='Markdown'
        )
    except Exception as e:
        await callback_query.answer(f"Ошибка: {str(e)}")

@dp.callback_query(F.data.startswith("additemcat_"), AdminStates.waiting_for_category_select)
async def admin_add_item_name(callback_query: types.CallbackQuery, state: FSMContext):
    category_name = callback_query.data.replace("additemcat_", "")
    await state.update_data(add_category=category_name)
    await state.set_state(AdminStates.waiting_for_item_name)
    
    await callback_query.message.edit_text(
        f"📝 *Введите название блюда* для категории *{category_name}*:\n\n"
        "(или отправьте /cancel для отмены)",
        parse_mode='Markdown'
    )

@dp.message(AdminStates.waiting_for_item_name)
async def admin_add_item_price(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Добавление блюда отменено")
        return
    
    item_name = message.text.strip()
    await state.update_data(add_item_name=item_name)
    await state.set_state(AdminStates.waiting_for_item_price)
    
    await message.answer(
        f"💰 *Введите цену* для блюда *{item_name}* (в сумах):\n\n"
        "(или отправьте /cancel для отмены)",
        parse_mode='Markdown'
    )

@dp.message(AdminStates.waiting_for_item_price)
async def admin_add_item_save(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Добавление блюда отменено")
        return
    
    try:
        price = int(message.text.strip())
        data = await state.get_data()
        category_name = data['add_category']
        item_name = data['add_item_name']
        
        with open('menu.json', 'r', encoding='utf-8') as f:
            menu_data = json.load(f)
        
        # Находим категорию и добавляем блюдо
        for category in menu_data['menu']:
            if category['category'] == category_name:
                category['items'].append({"name": item_name, "price": price})
                break
        
        with open('menu.json', 'w', encoding='utf-8') as f:
            json.dump(menu_data, f, ensure_ascii=False, indent=2)
        
        await message.answer(
            f"✅ Блюдо *{item_name}* добавлено в категорию *{category_name}* с ценой {format_price(price)}\n\nНе забудьте обновить меню в БД",
            parse_mode='Markdown'
        )
        
        # Возвращаемся в админ-панель
        await admin_panel(message, state)
        
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число (цену в сумах)")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

# Редактирование блюда
@dp.callback_query(F.data == "admin_edit_item", AdminStates.admin_menu)
async def admin_edit_category_select(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        with open('menu.json', 'r', encoding='utf-8') as f:
            menu_data = json.load(f)
        
        builder = InlineKeyboardBuilder()
        for category in menu_data['menu']:
            builder.button(
                text=f"✏️ {category['category']}",
                callback_data=f"editcat_{category['category']}"
            )
        builder.button(text="◀️ Назад", callback_data="admin_back")
        builder.adjust(2)
        
        await state.set_state(AdminStates.waiting_for_category_select)
        await callback_query.message.edit_text(
            "✏️ *Выберите категорию с блюдом для редактирования:*",
            reply_markup=builder.as_markup(),
            parse_mode='Markdown'
        )
    except Exception as e:
        await callback_query.answer(f"Ошибка: {str(e)}")

@dp.callback_query(F.data.startswith("editcat_"), AdminStates.waiting_for_category_select)
async def admin_edit_item_select(callback_query: types.CallbackQuery, state: FSMContext):
    category_name = callback_query.data.replace("editcat_", "")
    await state.update_data(edit_category=category_name)
    
    try:
        with open('menu.json', 'r', encoding='utf-8') as f:
            menu_data = json.load(f)
        
        # Находим категорию
        for category in menu_data['menu']:
            if category['category'] == category_name:
                builder = InlineKeyboardBuilder()
                for item in category['items']:
                    builder.button(
                        text=f"✏️ {item['name']} - {format_price(item['price'])}",
                        callback_data=f"edititem_{item['name']}"
                    )
                builder.button(text="◀️ Назад", callback_data="admin_back")
                builder.adjust(1)
                
                await callback_query.message.edit_text(
                    f"✏️ *Выберите блюдо для редактирования* в категории *{category_name}*:",
                    reply_markup=builder.as_markup(),
                    parse_mode='Markdown'
                )
                await state.set_state(AdminStates.waiting_for_item_select)
                break
    except Exception as e:
        await callback_query.answer(f"Ошибка: {str(e)}")

@dp.callback_query(F.data.startswith("edititem_"), AdminStates.waiting_for_item_select)
async def admin_edit_item_options(callback_query: types.CallbackQuery, state: FSMContext):
    item_name = callback_query.data.replace("edititem_", "")
    await state.update_data(edit_item_name=item_name)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Изменить название", callback_data="edit_name")
    builder.button(text="💰 Изменить цену", callback_data="edit_price")
    builder.button(text="◀️ Назад", callback_data="admin_back")
    builder.adjust(2)
    
    await callback_query.message.edit_text(
        f"✏️ *Редактирование блюда:* {item_name}\n\nЧто хотите изменить?",
        reply_markup=builder.as_markup(),
        parse_mode='Markdown'
    )

@dp.callback_query(F.data == "edit_name")
async def admin_edit_name(callback_query: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_edit_name)
    await callback_query.message.edit_text(
        "📝 *Введите новое название блюда:*\n\n"
        "(или отправьте /cancel для отмены)",
        parse_mode='Markdown'
    )

@dp.message(AdminStates.waiting_for_edit_name)
async def admin_save_new_name(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Редактирование отменено")
        return
    
    new_name = message.text.strip()
    data = await state.get_data()
    category_name = data['edit_category']
    old_name = data['edit_item_name']
    
    try:
        with open('menu.json', 'r', encoding='utf-8') as f:
            menu_data = json.load(f)
        
        # Находим и обновляем блюдо
        for category in menu_data['menu']:
            if category['category'] == category_name:
                for item in category['items']:
                    if item['name'] == old_name:
                        item['name'] = new_name
                        break
        
        with open('menu.json', 'w', encoding='utf-8') as f:
            json.dump(menu_data, f, ensure_ascii=False, indent=2)
        
        await message.answer(f"✅ Название блюда изменено с *{old_name}* на *{new_name}*", parse_mode='Markdown')
        await admin_panel(message, state)
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

@dp.callback_query(F.data == "edit_price")
async def admin_edit_price(callback_query: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_edit_price)
    await callback_query.message.edit_text(
        "💰 *Введите новую цену блюда* (в сумах):\n\n"
        "(или отправьте /cancel для отмены)",
        parse_mode='Markdown'
    )

@dp.message(AdminStates.waiting_for_edit_price)
async def admin_save_new_price(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Редактирование отменено")
        return
    
    try:
        new_price = int(message.text.strip())
        data = await state.get_data()
        category_name = data['edit_category']
        item_name = data['edit_item_name']
        
        with open('menu.json', 'r', encoding='utf-8') as f:
            menu_data = json.load(f)
        
        # Находим и обновляем блюдо
        for category in menu_data['menu']:
            if category['category'] == category_name:
                for item in category['items']:
                    if item['name'] == item_name:
                        old_price = item['price']
                        item['price'] = new_price
                        break
        
        with open('menu.json', 'w', encoding='utf-8') as f:
            json.dump(menu_data, f, ensure_ascii=False, indent=2)
        
        await message.answer(
            f"✅ Цена блюда *{item_name}* изменена с {format_price(old_price)} на {format_price(new_price)}",
            parse_mode='Markdown'
        )
        await admin_panel(message, state)
        
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число (цену в сумах)")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

# Удаление блюда
@dp.callback_query(F.data == "admin_delete_item", AdminStates.admin_menu)
async def admin_delete_item_category(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        with open('menu.json', 'r', encoding='utf-8') as f:
            menu_data = json.load(f)
        
        builder = InlineKeyboardBuilder()
        for category in menu_data['menu']:
            builder.button(
                text=f"🗑 {category['category']}",
                callback_data=f"delitemcat_{category['category']}"
            )
        builder.button(text="◀️ Назад", callback_data="admin_back")
        builder.adjust(2)
        
        await state.set_state(AdminStates.waiting_for_category_select)
        await callback_query.message.edit_text(
            "🗑 *Выберите категорию с блюдом для удаления:*",
            reply_markup=builder.as_markup(),
            parse_mode='Markdown'
        )
    except Exception as e:
        await callback_query.answer(f"Ошибка: {str(e)}")

@dp.callback_query(F.data.startswith("delitemcat_"), AdminStates.waiting_for_category_select)
async def admin_delete_item_select(callback_query: types.CallbackQuery, state: FSMContext):
    category_name = callback_query.data.replace("delitemcat_", "")
    await state.update_data(del_category=category_name)
    
    try:
        with open('menu.json', 'r', encoding='utf-8') as f:
            menu_data = json.load(f)
        
        # Находим категорию
        for category in menu_data['menu']:
            if category['category'] == category_name:
                builder = InlineKeyboardBuilder()
                for item in category['items']:
                    builder.button(
                        text=f"🗑 {item['name']} - {format_price(item['price'])}",
                        callback_data=f"delitem_{item['name']}"
                    )
                builder.button(text="◀️ Назад", callback_data="admin_back")
                builder.adjust(1)
                
                await callback_query.message.edit_text(
                    f"🗑 *Выберите блюдо для удаления* в категории *{category_name}*:",
                    reply_markup=builder.as_markup(),
                    parse_mode='Markdown'
                )
                await state.set_state(AdminStates.waiting_for_item_select)
                break
    except Exception as e:
        await callback_query.answer(f"Ошибка: {str(e)}")

@dp.callback_query(F.data.startswith("delitem_"), AdminStates.waiting_for_item_select)
async def admin_delete_item_confirm(callback_query: types.CallbackQuery, state: FSMContext):
    item_name = callback_query.data.replace("delitem_", "")
    data = await state.get_data()
    category_name = data['del_category']
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, удалить", callback_data=f"confirm_del_{item_name}")
    builder.button(text="❌ Нет, отмена", callback_data="admin_back")
    builder.adjust(2)
    
    await callback_query.message.edit_text(
        f"⚠️ *Вы уверены, что хотите удалить блюдо*\n*{item_name}* из категории *{category_name}*?",
        reply_markup=builder.as_markup(),
        parse_mode='Markdown'
    )

@dp.callback_query(F.data.startswith("confirm_del_"))
async def admin_delete_item_final(callback_query: types.CallbackQuery, state: FSMContext):
    item_name = callback_query.data.replace("confirm_del_", "")
    data = await state.get_data()
    category_name = data['del_category']
    
    try:
        with open('menu.json', 'r', encoding='utf-8') as f:
            menu_data = json.load(f)
        
        # Находим и удаляем блюдо
        for category in menu_data['menu']:
            if category['category'] == category_name:
                category['items'] = [item for item in category['items'] if item['name'] != item_name]
                break
        
        with open('menu.json', 'w', encoding='utf-8') as f:
            json.dump(menu_data, f, ensure_ascii=False, indent=2)
        
        await callback_query.answer(f"✅ Блюдо удалено")
        await callback_query.message.edit_text(
            f"✅ Блюдо *{item_name}* успешно удалено из категории *{category_name}*!\n\nНе забудьте обновить меню в БД",
            parse_mode='Markdown'
        )
        
        # Возвращаемся в админ-панель
        await admin_panel(callback_query.message, state)
        
    except Exception as e:
        await callback_query.answer(f"Ошибка: {str(e)}")

# Обновление меню в БД
@dp.callback_query(F.data == "admin_refresh_menu", AdminStates.admin_menu)
async def admin_refresh_menu(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        with open('menu.json', 'r', encoding='utf-8') as f:
            menu_data = json.load(f)
        
        db.import_menu_from_json(menu_data)
        
        await callback_query.answer("✅ Меню обновлено в БД")
        await callback_query.message.edit_text(
            "✅ *Меню успешно обновлено в базе данных!*\n\nТеперь бот работает с актуальным меню.",
            parse_mode='Markdown'
        )
        
        # Возвращаемся в админ-панель
        await admin_panel(callback_query.message, state)
        
    except Exception as e:
        await callback_query.answer(f"Ошибка: {str(e)}")

# Кнопка "Назад"
@dp.callback_query(F.data == "admin_back")
async def admin_back(callback_query: types.CallbackQuery, state: FSMContext):
    await admin_panel(callback_query.message, state)

# Кнопка "Закрыть"
@dp.callback_query(F.data == "admin_close")
async def admin_close(callback_query: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback_query.message.delete()
    await callback_query.message.answer("🔒 Админ-панель закрыта")

# Обработка кнопки создания нового заказа
@dp.message(F.text == "📋 Создать новый заказ")
async def create_new_order(message: types.Message, state: FSMContext):
    await state.set_state(OrderStates.waiting_for_table_number)
    await show_table_selection(message)

# Показать выбор стола через инлайн кнопки
async def show_table_selection(message: types.Message):
    builder = InlineKeyboardBuilder()
    
    # Создаем кнопки для 12 столов
    for table_num in range(1, 14):
        builder.button(text=f"🍽️ Стол {table_num}", callback_data=f"table_{table_num}")
    
    builder.adjust(3)  # 3 кнопки в ряд
    
    await message.answer(
        "🪑 *Выберите номер стола:*",
        reply_markup=builder.as_markup(),
        parse_mode='Markdown'
    )

# Обработка выбора стола
@dp.callback_query(F.data.startswith('table_'), OrderStates.waiting_for_table_number)
async def process_table_selection(callback_query: types.CallbackQuery, state: FSMContext):
    table_number = int(callback_query.data.replace('table_', ''))
    
    waiter = db.get_waiter(callback_query.from_user.id)
    if not waiter:
        await callback_query.answer("Ошибка: официант не найден")
        return
    
    # Проверяем, есть ли уже активный заказ для этого стола
    existing_order = db.get_active_order(table_number, waiter['id'])
    if existing_order:
        await state.update_data(table_number=table_number)
        await callback_query.answer(f"Выбран стол {table_number}")
        await show_categories_from_callback(callback_query, state)
    else:
        # Создаем новый заказ
        db.create_order(table_number, waiter['id'])
        await state.update_data(table_number=table_number)
        await callback_query.answer(f"Создан заказ для стола {table_number}")
        await show_categories_from_callback(callback_query, state)

@dp.message(F.text == "👀 Посмотреть активные заказы")
async def show_active_orders(message: types.Message):
    waiter = db.get_waiter(message.from_user.id)
    if not waiter:
        await message.answer("Официант не найден")
        return
    
    orders = db.get_waiter_orders(waiter['id'])
    
    if orders:
        response = f"👨‍🍳 *Официант: {waiter['full_name']}*\n\n"
        response += "📋 *Ваши активные заказы:*\n\n"
        
        for order in orders:
            order_items = db.get_order_items(order['table_number'])
            response += f"🍽️ *Стол {order['table_number']}:*\n"
            total = order['total_amount']
            for item in order_items:
                response += f"   • {item['item_name']} x{item['quantity']} - {format_price(item['total_price'])}\n"
            
            response += f"   💰 *Итого: {format_price(total)}*\n"
            response += f"   ⏰ *Создан: {order['created_at']}*\n\n"
        
        # Добавляем кнопки для управления заказами
        builder = InlineKeyboardBuilder()
        for order in orders:
            builder.button(text=f"✏️ Редактировать стол {order['table_number']}", callback_data=f"edit_table_{order['table_number']}")
        builder.adjust(1)
        
        await message.answer(response, reply_markup=builder.as_markup(), parse_mode='Markdown')
    else:
        await message.answer("У вас нет активных заказов.")

# Обработка редактирования стола из активных заказов
@dp.callback_query(F.data.startswith('edit_table_'))
async def handle_edit_table(callback_query: types.CallbackQuery, state: FSMContext):
    table_number = int(callback_query.data.replace('edit_table_', ''))
    
    waiter = db.get_waiter(callback_query.from_user.id)
    if not waiter:
        await callback_query.answer("Официант не найден")
        return
    
    # Находим заказ для этого стола
    order = db.get_active_order(table_number, waiter['id'])
    if not order:
        await callback_query.answer("Заказ не найден")
        return
    
    # Сохраняем данные в state и переходим к редактированию
    await state.update_data(table_number=table_number)
    await show_order_for_editing(callback_query, state, table_number)

# Показать заказ для редактирования
async def show_order_for_editing(callback_query: types.CallbackQuery, state: FSMContext, table_number: int):
    user_data = await state.get_data()
    
    order_items = db.get_order_items(table_number)
    waiter_name = callback_query.from_user.full_name
    comment = user_data.get('order_comment', '')
    comment_text = f"💬 *Комментарий:* {escape_markdown(comment)}\n" if comment else ""
    
    order_message = f"✏️ *РЕДАКТИРОВАНИЕ ЗАКАЗА*\n\n"
    order_message += f"👨‍🍳 *Официант:* {escape_markdown(waiter_name)}\n"
    order_message += f"🪑 *Стол:* {table_number}\n\n"
    order_message += "📋 *Текущий заказ:*\n"
    
    total = 0
    for item in order_items:
        # Экранируем названия блюд
        escaped_item_name = escape_markdown(item['item_name'])
        order_message += f"• {escaped_item_name} x{item['quantity']} - {format_price(item['total_price'])}\n"
        total += item['total_price']
    
    order_message += f"\n{comment_text}"
    order_message += f"💰 *Общая сумма:* {format_price(total)}"
    
    builder = InlineKeyboardBuilder()
    
    # Кнопки для каждого блюда
    for item in order_items:
        escaped_item_name = escape_markdown(item['item_name'])
        builder.button(text=f"❌ Удалить {escaped_item_name}", callback_data=f"remove_{item['item_name']}_{table_number}")
        builder.button(text=f"✏️ Изменить {escaped_item_name}", callback_data=f"change_{item['item_name']}_{table_number}")
    
    builder.button(text="💬 Редактировать комментарий", callback_data=f"edit_comment_{table_number}")
    builder.button(text="➕ Добавить блюда", callback_data=f"add_items_{table_number}")
    builder.button(text="✅ Завершить редактирование", callback_data=f"finish_edit_{table_number}")
    builder.button(text="📋 Отправить заказ", callback_data=f"send_from_edit_{table_number}")
    builder.button(text="💰 Рассчитать стол", callback_data=f"calculate_table_{table_number}")
    
    builder.adjust(2)
    
    await state.set_state(OrderStates.editing_order)
    await callback_query.message.edit_text(
        order_message,
        reply_markup=builder.as_markup(),
        parse_mode='Markdown'
    )

# Обработка редактирования комментария
@dp.callback_query(F.data.startswith('edit_comment_'))
async def edit_comment_handler(callback_query: types.CallbackQuery, state: FSMContext):
    table_number = int(callback_query.data.replace('edit_comment_', ''))
    await state.update_data(table_number=table_number)
    
    user_data = await state.get_data()
    current_comment = user_data.get('order_comment', '')
    
    await callback_query.message.edit_text(
        f"💬 *Редактирование комментария:*\n\n"
        f"Текущий комментарий: {escape_markdown(current_comment)}\n\n"
        "Введите новый комментарий",
        parse_mode='Markdown'
    )
    await state.set_state(OrderStates.adding_comment)

# Расчет стола
@dp.callback_query(F.data.startswith('calculate_table_'))
async def calculate_table(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.message.delete()
    
    table_number = int(callback_query.data.replace('calculate_table_', ''))

    billing(table_number)   # генерируем HTML/PDF чек
    db.complete_order(table_number)

    await state.clear()

    # клавиатура
    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text="📋 Создать новый заказ"))
    builder.add(types.KeyboardButton(text="👀 Посмотреть активные заказы"))
    builder.adjust(2)

    # путь к файлу
    file_path = f"bill_table_{table_number}.html"

    # Проверим, что файл реально есть
    if not os.path.exists(file_path):
        await callback_query.message.answer(f"Файл не найден: {file_path}")
        return

    # Отправка файла
    document = FSInputFile(file_path)
    await bot.send_document(
        chat_id=callback_query.message.chat.id,
        document=document
    )

    await callback_query.message.answer(
        "🍽️ *Чек успешно создан!*\n\nВыберите действие:",
        reply_markup=builder.as_markup(resize_keyboard=True),
        parse_mode='Markdown'
    )

# Удаление блюда из заказа
@dp.callback_query(F.data.startswith('remove_'))
async def remove_item_from_order(callback_query: types.CallbackQuery, state: FSMContext):
    data_parts = callback_query.data.split('_')
    item_name = data_parts[1]
    table_number = int(data_parts[2])
    
    user_data = await state.get_data()
    
    # Удаляем блюдо из заказа
    success = db.remove_order_item(table_number, item_name)
    if success:
        await callback_query.answer(f"❌ Удалено: {item_name}")
        await show_order_for_editing(callback_query, state, table_number)
    else:
        await callback_query.answer("Блюдо не найдено")

# Изменение количества блюда
@dp.callback_query(F.data.startswith('change_'))
async def change_item_quantity(callback_query: types.CallbackQuery, state: FSMContext):
    data_parts = callback_query.data.split('_')
    item_name = data_parts[1]
    table_number = int(data_parts[2])
    
    user_data = await state.get_data()
    
    # Получаем текущее количество
    order_items = db.get_order_items(table_number)
    current_quantity = next((item['quantity'] for item in order_items if item['item_name'] == item_name), 0)
    
    builder = InlineKeyboardBuilder()
    for i in range(1, 21):
        builder.button(text=str(i), callback_data=f"set_quantity_{item_name}_{table_number}_{i}")
    
    builder.adjust(5)
    
    await callback_query.message.edit_text(
        f"✏️ *Изменение количества:*\n\n{item_name}\nТекущее количество: {current_quantity}\n\nВыберите новое количество:",
        reply_markup=builder.as_markup(),
        parse_mode='Markdown'
    )

# Установка нового количества
@dp.callback_query(F.data.startswith('set_quantity_'))
async def set_new_quantity(callback_query: types.CallbackQuery, state: FSMContext):
    data_parts = callback_query.data.split('_')
    item_name = data_parts[2]
    table_number = int(data_parts[3])
    new_quantity = int(data_parts[4])
    
    user_data = await state.get_data()
    
    # Обновляем количество в заказе
    success = db.update_order_item_quantity(table_number, item_name, new_quantity)
    if success:
        await callback_query.answer(f"✅ Изменено: {item_name} x{new_quantity}")
        await show_order_for_editing(callback_query, state, table_number)
    else:
        await callback_query.answer("Блюдо не найдено")

# Добавление блюд при редактировании
@dp.callback_query(F.data.startswith('add_items_'))
async def add_items_during_edit(callback_query: types.CallbackQuery, state: FSMContext):
    table_number = int(callback_query.data.replace('add_items_', ''))
    await state.update_data(table_number=table_number)
    await show_categories_from_callback(callback_query, state)

# Завершение редактирования
@dp.callback_query(F.data.startswith('finish_edit_'))
async def finish_editing(callback_query: types.CallbackQuery, state: FSMContext):
    table_number = int(callback_query.data.replace('finish_edit_', ''))
    
    user_data = await state.get_data()
    
    order_items = db.get_order_items(table_number)
    if not order_items:
        # Если заказ пустой, удаляем его
        db.cancel_order(table_number)
        await callback_query.answer("Заказ удален (пустой)")
    else:
        await callback_query.answer("Редактирование завершено")
    
    # Возвращаемся к списку активных заказов
    await show_active_orders_from_callback(callback_query)

# Отправка заказа из режима редактирования
@dp.callback_query(F.data.startswith('send_from_edit_'))
async def send_order_from_edit(callback_query: types.CallbackQuery, state: FSMContext):
    table_number = int(callback_query.data.replace('send_from_edit_', ''))
    
    user_data = await state.get_data()
    
    await state.update_data(table_number=table_number)
    await show_order_preview(callback_query, state)

# Показать активные заказы из callback
async def show_active_orders_from_callback(callback_query: types.CallbackQuery):
    waiter = db.get_waiter(callback_query.from_user.id)
    if not waiter:
        await callback_query.message.edit_text("Официант не найден")
        return
    
    orders = db.get_waiter_orders(waiter['id'])
    
    if orders:
        response = f"👨‍🍳 *Официант: {waiter['full_name']}*\n\n"
        response += "📋 *Ваши активные заказы:*\n\n"
        
        for order in orders:
            order_items = db.get_order_items(order['table_number'])
            response += f"🍽️ *Стол {order['table_number']}:*\n"
            total = order['total_amount']
            for item in order_items:
                response += f"   • {item['item_name']} x{item['quantity']} - {format_price(item['total_price'])}\n"
            
            response += f"   💰 *Итого: {format_price(total)}*\n"
            response += f"   ⏰ *Создан: {order['created_at']}*\n\n"
        
        builder = InlineKeyboardBuilder()
        for order in orders:
            builder.button(text=f"✏️ Редактировать стол {order['table_number']}", callback_data=f"edit_table_{order['table_number']}")
        builder.adjust(1)
        
        await callback_query.message.edit_text(response, reply_markup=builder.as_markup(), parse_mode='Markdown')
    else:
        await callback_query.message.edit_text("У вас нет активных заказов.")

# Показать категории из callback
async def show_categories_from_callback(callback_query: types.CallbackQuery, state: FSMContext):
    categories = db.get_menu_categories()
    
    builder = InlineKeyboardBuilder()
    for category in categories:
        builder.button(text=category, callback_data=f"category_{category}")
    
    # Добавляем кнопку просмотра текущего заказа
    user_data = await state.get_data()
    table_number = user_data.get('table_number')
    
    if table_number:
        builder.button(text="📋 Посмотреть заказ", callback_data="view_current_order")
    
    builder.adjust(2)
    await state.set_state(OrderStates.selecting_category)
    
    try:
        await callback_query.message.edit_text(
            "🍽️ *Выберите категорию:*",
            reply_markup=builder.as_markup(),
            parse_mode='Markdown'
        )
    except:
        await callback_query.message.answer(
            "🍽️ *Выберите категорию:*",
            reply_markup=builder.as_markup(),
            parse_mode='Markdown'
        )

# Обработка выбора категории
@dp.callback_query(F.data.startswith('category_'), OrderStates.selecting_category)
async def process_category(callback_query: types.CallbackQuery, state: FSMContext):
    category_name = callback_query.data.replace('category_', '')
    
    menu_items = db.get_menu_items(category_name)
    
    if menu_items:
        builder = InlineKeyboardBuilder()
        
        for item in menu_items:
            builder.button(
                text=f"{item['name']} - {format_price(item['price'])}",
                callback_data=f"item_{item['name']}_{item['price']}"
            )
        
        # Добавляем кнопки навигации
        builder.button(text="⬅️ Назад к категориям", callback_data="back_to_categories")
        
        user_data = await state.get_data()
        table_number = user_data.get('table_number')
        
        if table_number:
            builder.button(text="📋 Посмотреть заказ", callback_data="view_current_order")
        
        builder.adjust(1)
        
        await state.set_state(OrderStates.selecting_item)
        await callback_query.message.edit_text(
            f"🍽️ *{category_name}:*\nВыберите блюдо:",
            reply_markup=builder.as_markup(),
            parse_mode='Markdown'
        )
    else:
        await callback_query.answer("В этой категории пока нет блюд")

# Обработка кнопки "Назад"
@dp.callback_query(F.data == 'back_to_categories')
async def back_to_categories(callback_query: types.CallbackQuery, state: FSMContext):
    await show_categories_from_callback(callback_query, state)

# Обработка выбора блюда
@dp.callback_query(F.data.startswith('item_'), OrderStates.selecting_item)
async def process_item(callback_query: types.CallbackQuery, state: FSMContext):
    item_data = callback_query.data.replace('item_', '').split('_')
    item_name = item_data[0]
    item_price = float(item_data[1])
    
    await state.update_data(selected_item=item_name, selected_price=item_price)
    
    builder = InlineKeyboardBuilder()
    for i in range(1, 21):
        builder.button(text=str(i), callback_data=f"quantity_{i}")
    
    builder.adjust(5)
    await state.set_state(OrderStates.adding_quantity)
    await callback_query.message.edit_text(
        f"🍽️ *{item_name}*\n💰 Цена: {format_price(item_price)}\n\nВыберите количество:",
        reply_markup=builder.as_markup(),
        parse_mode='Markdown'
    )

# Обработка выбора количества - с суммированием позиций
@dp.callback_query(F.data.startswith('quantity_'), OrderStates.adding_quantity)
async def process_quantity(callback_query: types.CallbackQuery, state: FSMContext):
    quantity = int(callback_query.data.replace('quantity_', ''))
    
    user_data = await state.get_data()
    table_number = user_data['table_number']
    item_name = user_data['selected_item']
    item_price = user_data['selected_price']
    
    # Добавляем блюдо в заказ (база данных сама суммирует если уже есть)
    db.add_order_item(table_number, item_name, item_price, quantity)
    
    await callback_query.answer(f"✅ Добавлено: {item_name} x{quantity}")
    
    # ВОЗВРАЩАЕМСЯ К МЕНю КАТЕГОРИЙ после добавления
    await show_categories_from_callback(callback_query, state)

# Просмотр текущего заказа из инлайн меню
@dp.callback_query(F.data == 'view_current_order')
async def view_current_order_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await show_order_preview(callback_query, state)

# Показать превью заказа
async def show_order_preview(callback_query: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    table_number = user_data.get('table_number')
    waiter_name = callback_query.from_user.full_name
    
    if table_number:
        order_items = db.get_order_items(table_number)
        order = db.get_active_order(table_number, callback_query.from_user.id)
        order_total = order['total_amount'] if order else sum(item['total_price'] for item in order_items)
        
        # Проверяем, есть ли уже комментарий (экранируем его)
        comment = user_data.get('order_comment', '')
        comment_text = f"💬 *Комментарий:* {escape_markdown(comment)}\n" if comment else ""
        
        # Формируем сообщение превью
        order_message = f"🍽️ *ПРЕВЬЮ ЗАКАЗА* 🍽️\n\n"
        order_message += f"👨‍🍳 *Официант:* {escape_markdown(waiter_name)}\n"
        order_message += f"🪑 *Стол:* {table_number}\n\n"
        order_message += "📋 *Заказ:*\n"
        
        for item in order_items:
            # Экранируем названия блюд
            escaped_item_name = escape_markdown(item['item_name'])
            order_message += f"• {escaped_item_name} x{item['quantity']} - {format_price(item['total_price'])}\n"
        
        order_message += f"\n{comment_text}"
        order_message += f"💰 *Общая сумма:* {format_price(order_total)}\n"
        order_message += f"⏰ *Время:* {datetime.now().strftime('%H:%M')}"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="💬 Добавить комментарий", callback_data="add_comment")
        builder.button(text="✅ Подтвердить и отправить", callback_data="confirm_send_order")
        builder.button(text="➕ Добавить еще блюда", callback_data="add_more_items")
        builder.button(text="✏️ Редактировать заказ", callback_data=f"edit_table_{table_number}")
        builder.button(text="💰 Рассчитать стол", callback_data=f"calculate_table_{table_number}")
        builder.adjust(1)
        
        await state.set_state(OrderStates.preview_order)
        
        # Пытаемся отредактировать, если не получится - отправляем новое сообщение
        try:
            await callback_query.message.edit_text(
                order_message,
                reply_markup=builder.as_markup(),
                parse_mode='Markdown'
            )
        except:
            await callback_query.message.answer(
                order_message,
                reply_markup=builder.as_markup(),
                parse_mode='Markdown'
            )
    else:
        await callback_query.answer("Нет активного заказа для просмотра")

@dp.callback_query(F.data == 'add_comment', OrderStates.preview_order)
async def add_comment_handler(callback_query: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    current_comment = user_data.get('order_comment', '')
    
    message_text = "💬 *Введите комментарий к заказу:*\n\n"
    if current_comment:
        message_text += f"Текущий комментарий: {escape_markdown(current_comment)}\n\n"
    
    # Отправляем новое сообщение вместо редактирования
    await callback_query.message.answer(
        message_text,
        parse_mode='Markdown'
    )
    await state.set_state(OrderStates.adding_comment)
    await callback_query.answer()

# Обновляем обработчик отмены комментария
@dp.message(Command("cancel"), OrderStates.adding_comment)
async def cancel_comment(message: types.Message, state: FSMContext):
    # Удаляем сообщение с запросом комментария
    try:
        await message.delete()
    except:
        pass
    
    await state.set_state(OrderStates.preview_order)
    await show_order_preview_message(message, state)
    await message.answer("❌ Добавление комментария отменено")

async def show_order_preview_message(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    table_number = user_data.get('table_number')
    waiter_name = message.from_user.full_name
    
    if table_number:
        order_items = db.get_order_items(table_number)
        order = db.get_active_order(table_number, message.from_user.id)
        order_total = order['total_amount'] if order else sum(item['total_price'] for item in order_items)
        
        # Проверяем, есть ли уже комментарий (экранируем его)
        comment = user_data.get('order_comment', '')
        comment_text = f"💬 *Комментарий:* {escape_markdown(comment)}\n" if comment else ""
        
        # Формируем сообщение превью
        order_message = f"🍽️ *ПРЕВЬЮ ЗАКАЗА* 🍽️\n\n"
        order_message += f"👨‍🍳 *Официант:* {escape_markdown(waiter_name)}\n"
        order_message += f"🪑 *Стол:* {table_number}\n\n"
        order_message += "📋 *Заказ:*\n"
        
        for item in order_items:
            # Экранируем названия блюд
            escaped_item_name = escape_markdown(item['item_name'])
            order_message += f"• {escaped_item_name} x{item['quantity']} - {format_price(item['total_price'])}\n"
        
        order_message += f"\n{comment_text}"
        order_message += f"💰 *Общая сумма:* {format_price(order_total)}\n"
        order_message += f"⏰ *Время:* {datetime.now().strftime('%H:%M')}"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="💬 Добавить комментарий", callback_data="add_comment")
        builder.button(text="✅ Подтвердить и отправить", callback_data="confirm_send_order")
        builder.button(text="➕ Добавить еще блюда", callback_data="add_more_items")
        builder.button(text="✏️ Редактировать заказ", callback_data=f"edit_table_{table_number}")
        builder.button(text="💰 Рассчитать стол", callback_data=f"calculate_table_{table_number}")
        builder.adjust(1)
        
        await state.set_state(OrderStates.preview_order)
        await message.answer(
            order_message,
            reply_markup=builder.as_markup(),
            parse_mode='Markdown'
        )

@dp.message(OrderStates.adding_comment)
async def process_comment(message: types.Message, state: FSMContext):
    comment = message.text.strip()
    if len(comment) > 200:
        await message.answer("❌ Комментарий слишком длинный (максимум 200 символов). Попробуйте снова:")
        return
    
    await state.update_data(order_comment=comment)
    
    # Удаляем предыдущее сообщение с запросом комментария
    try:
        await message.delete()
    except:
        pass
    
    # Отправляем новое сообщение с превью вместо редактирования
    await show_order_preview_message(message, state)
    await message.answer("✅ Комментарий добавлен!")

# Подтверждение и отправка заказа
@dp.callback_query(F.data == 'confirm_send_order', OrderStates.preview_order)
async def confirm_send_order(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.message.delete()

    user_data = await state.get_data()
    table_number = user_data.get('table_number')
    waiter_name = callback_query.from_user.full_name
    comment = user_data.get('order_comment', '')
    
    if table_number:
        order_items = db.get_order_items(table_number)
        order = db.get_active_order(table_number, callback_query.from_user.id)
        order_total = order['total_amount'] if order else sum(item['total_price'] for item in order_items)
        
        # Формируем сообщение для кухни
        order_message = f"🍽️ *НОВЫЙ ЗАКАЗ!* 🍽️\n\n"
        order_message += f"👨‍🍳 *Официант:* {escape_markdown(waiter_name)}\n"
        order_message += f"🪑 *Стол:* {table_number}\n\n"
        order_message += "📋 *Заказ:*\n"
        
        for item in order_items:
            # Экранируем названия блюд
            escaped_item_name = escape_markdown(item['item_name'])
            order_message += f"• {escaped_item_name} x{item['quantity']} - {format_price(item['total_price'])}\n"
        
        # Добавляем комментарий (экранированный), если есть
        if comment:
            escaped_comment = escape_markdown(comment)
            order_message += f"\n💬 *Комментарий:* {escaped_comment}\n"
        
        order_message += f"\n💰 *Общая сумма:* {format_price(order_total)}\n"
        order_message += f"⏰ *Время:* {datetime.now().strftime('%H:%M')}"
        
        # Отправляем в группу
        try:
            await bot.send_message(GROUP_CHAT_ID, order_message, parse_mode='Markdown')
            await callback_query.answer("✅ Заказ отправлен на кухню!")
            
            # Очищаем состояние
            await state.clear()
            
            # Возвращаем в главное меню
            builder = ReplyKeyboardBuilder()
            builder.add(types.KeyboardButton(text="📋 Создать новый заказ"))
            builder.add(types.KeyboardButton(text="👀 Посмотреть активные заказы"))
            builder.adjust(2)
            
            await callback_query.message.answer(
                "🍽️ *Заказ успешно отправлен!*\n\nВыберите действие:",
                reply_markup=builder.as_markup(resize_keyboard=True),
                parse_mode='Markdown'
            )
            
        except Exception as e:
            print(f"Ошибка отправки: {e}")
            await callback_query.answer("❌ Ошибка отправки заказа")
    
    else:
        await callback_query.answer("Нет активного заказа для отправки")

# Обработка добавления еще блюд из превью
@dp.callback_query(F.data == 'add_more_items')
async def add_more_items_from_preview(callback_query: types.CallbackQuery, state: FSMContext):
    await show_categories_from_callback(callback_query, state)

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
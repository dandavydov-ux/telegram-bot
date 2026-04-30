import asyncio
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import logging

# 🔑 НАСТРОЙКИ
# Вставьте ваш токен в кавычках
BOT_TOKEN = "8771258586:AAGhr-XQVc78MM7bxOoj9Rp-v184bWZmA2k"

# ID канала: либо числовой (с одним минусом, без кавычек), либо юзернейм (с @, в кавычках)
# Вариант 1 (числовой, рекомендуется):
CHANNEL_ID = -1003054634333
# Вариант 2 (если первый не сработает — раскомментируйте строку ниже, а верхнюю закомментируйте):
# CHANNEL_ID = "@silentium41"

# 📚 СПИСОК ID СООБЩЕНИЙ
# [0]=Вступление 1, [1]=Вступление 2, [2]=День 1, ..., [42]=День 41
COURSE_MESSAGE_IDS = [
    7, 8,  # Вступительные сообщения
    *list(range(11, 52))  # Дни 1-41: сообщения 11,12,13,...,51
]

# 🔍 Проверка списка при старте
def verify_course_list():
    expected_total = 43  # 2 вступления + 41 день
    if len(COURSE_MESSAGE_IDS) != expected_total:
        logging.error(f"❌ Ошибка: ожидалось {expected_total} ID, найдено {len(COURSE_MESSAGE_IDS)}")
        return False
    if COURSE_MESSAGE_IDS[0] != 7 or COURSE_MESSAGE_IDS[1] != 8:
        logging.error("❌ Ошибка: первые два ID должны быть 7 и 8")
        return False
    if COURSE_MESSAGE_IDS[2] != 11 or COURSE_MESSAGE_IDS[-1] != 51:
        logging.error("❌ Ошибка: дни должны идти с 11 по 51")
        return False
    logging.info(f"✅ Список проверен: {len(COURSE_MESSAGE_IDS)} сообщений, дни 1-41 → ID 11-51")
    return True

# 🗄️ База данных
DB_NAME = "users.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        current_day INTEGER DEFAULT 0,
        notify_hour INTEGER,
        is_active INTEGER DEFAULT 0
    )""")
    conn.commit()
    conn.close()

def save_user(user_id, hour=0):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, notify_hour, current_day) VALUES (?, ?, 0)", (user_id, hour))
    conn.commit()
    conn.close()

def update_user(user_id, current_day=None, notify_hour=None, is_active=None):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    updates, values = [], []
    if current_day is not None:
        updates.append("current_day=?"); values.append(current_day)
    if notify_hour is not None:
        updates.append("notify_hour=?"); values.append(notify_hour)
    if is_active is not None:
        updates.append("is_active=?"); values.append(is_active)
    if updates:
        c.execute(f"UPDATE users SET {', '.join(updates)} WHERE user_id=?", values + [user_id])
        conn.commit()
    conn.close()

# 🤖 Aiogram
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# 🔘 Клавиатуры
kb_start = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🚀 Начать курс", callback_data="start_course")]
])
kb_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🔄 Начать сначала", callback_data="restart")],
    [InlineKeyboardButton(text="⏰ Поменять время", callback_data="change_time")]
])
kb_time = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text=f"{h}:00", callback_data=f"time_{h}")] for h in range(5, 13)
])

# 📨 Обработчики
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Добро пожаловать! Чтобы начать обучение, нажмите кнопку ниже:",
        reply_markup=kb_start
    )

@dp.callback_query(lambda c: c.data == "start_course")
async def handle_start_course(call: types.CallbackQuery):
    if not verify_course_list():
        await call.message.answer("⚠️ Ошибка конфигурации курса. Проверьте логи.")
        return
    save_user(call.from_user.id)
    try:
        await bot.copy_message(chat_id=call.from_user.id, from_chat_id=CHANNEL_ID, message_id=COURSE_MESSAGE_IDS[0])
        await bot.copy_message(chat_id=call.from_user.id, from_chat_id=CHANNEL_ID, message_id=COURSE_MESSAGE_IDS[1])
    except Exception as e:
        logging.error(f"Ошибка копирования: {e}")
        await call.message.answer("⚠️ Не удалось загрузить сообщения. Проверьте права бота в канале.")
        return
    await call.message.answer(
        "Выберите удобное время для ежедневных уведомлений:",
        reply_markup=kb_time
    )
    await call.answer()

@dp.callback_query(lambda c: c.data.startswith("time_"))
async def handle_time_selected(call: types.CallbackQuery):
    hour = int(call.data.split("_")[1])
    update_user(call.from_user.id, notify_hour=hour, is_active=1)
    await call.message.answer(
        "✅ Курс начат! Первое задание вы получите завтра в выбранное время.",
        reply_markup=kb_menu
    )
    await call.answer()

@dp.message(Command("menu"))
async def cmd_menu(message: types.Message):
    await message.answer("📋 Меню:", reply_markup=kb_menu)

@dp.callback_query(lambda c: c.data == "restart")
async def handle_restart(call: types.CallbackQuery):
    update_user(call.from_user.id, current_day=0, is_active=0)
    await call.message.answer(
        "🔄 Курс сброшен. Нажмите /start, чтобы начать заново.",
        reply_markup=kb_start
    )
    await call.answer()

@dp.callback_query(lambda c: c.data == "change_time")
async def handle_change_time(call: types.CallbackQuery):
    await call.message.answer(
        "Выберите новое время отправки:",
        reply_markup=kb_time
    )
    await call.answer()

# ⏰ Ежедневная рассылка
async def daily_checker():
    now = datetime.now()
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT user_id, current_day, notify_hour FROM users WHERE is_active=1")
    users = c.fetchall()
    conn.close()

    for uid, day, hour in users:
        if now.hour == hour and now.minute == 0 and day < 42:
            msg_index = day + 2  # День 0 → индекс 2 → сообщение 11
            if msg_index < len(COURSE_MESSAGE_IDS):
                try:
                    await bot.copy_message(
                        chat_id=uid,
                        from_chat_id=CHANNEL_ID,
                        message_id=COURSE_MESSAGE_IDS[msg_index]
                    )
                    update_user(uid, current_day=day + 1)
                    logging.info(f"✅ День {day+1} (msg {COURSE_MESSAGE_IDS[msg_index]}) отправлен пользователю {uid}")
                except Exception as e:
                    logging.error(f"Ошибка отправки {uid}: {e}")
            else:
                update_user(uid, is_active=0)
                try:
                    await bot.send_message(
                        uid,
                        "🎉 Поздравляем! Вы завершили курс!",
                        reply_markup=kb_menu
                    )
                except:
                    pass

# 🚀 Запуск
async def main():
    init_db()
    verify_course_list()
    scheduler.add_job(daily_checker, IntervalTrigger(minutes=1))
    scheduler.start()
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logging.info("🤖 Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

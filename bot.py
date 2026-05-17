import asyncio
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import logging
import pytz

BOT_TOKEN = " 8771258586:AAGhr-XQVc78MM7bxOoj9Rp-v184bWZmA2k"
CHANNEL_ID = -1003054634333

COURSE_MESSAGE_IDS = [
    7, 8,
    *list(range(11, 52))
]

# 🌍 таймзоны
TIMEZONES = {
    "Moscow": pytz.timezone("Europe/Moscow"),
    "Berlin": pytz.timezone("Europe/Berlin"),
    "New_York": pytz.timezone("America/New_York"),
}

DB_NAME = "users.db"

# ---------------- DB ----------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        current_day INTEGER DEFAULT 0,
        notify_hour INTEGER,
        timezone TEXT DEFAULT 'Europe/Berlin',
        last_sent_date TEXT,
        is_active INTEGER DEFAULT 0
    )""")
    conn.commit()
    conn.close()

def save_user(user_id, hour=0, tz="Berlin"):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
    INSERT OR IGNORE INTO users (user_id, notify_hour, timezone, current_day)
    VALUES (?, ?, ?, 0)
    """, (user_id, hour, tz))
    conn.commit()
    conn.close()

def update_user(user_id, **kwargs):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    keys = []
    values = []

    for k, v in kwargs.items():
        keys.append(f"{k}=?")
        values.append(v)

    if keys:
        c.execute(
            f"UPDATE users SET {', '.join(keys)} WHERE user_id=?",
            values + [user_id]
        )
        conn.commit()
    conn.close()

def get_users():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT user_id, current_day, notify_hour, timezone, last_sent_date FROM users WHERE is_active=1")
    data = c.fetchall()
    conn.close()
    return data

# ---------------- BOT ----------------
bot = Bot(token= "8771258586:AAGhr-XQVc78MM7bxOoj9Rp-v184bWZmA2k")
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# ---------------- UI ----------------
kb_start = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🚀 Начать курс", callback_data="start_course")]
])

kb_time = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text=f"{h}:00", callback_data=f"time_{h}")] for h in range(6, 13)
])

kb_tz = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🇩🇪 Берлин", callback_data="tz_Berlin")],
    [InlineKeyboardButton(text="🇷🇺 Москва", callback_data="tz_Moscow")],
    [InlineKeyboardButton(text="🇺🇸 Нью-Йорк", callback_data="tz_New_York")]
])

kb_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🔄 Начать сначала", callback_data="restart")]
])

# ---------------- START ----------------
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("🚀 Начнём курс:", reply_markup=kb_start)

@dp.callback_query(lambda c: c.data == "start_course")
async def start_course(call: types.CallbackQuery):
    save_user(call.from_user.id)

    await bot.copy_message(call.from_user.id, CHANNEL_ID, COURSE_MESSAGE_IDS[0])
    await bot.copy_message(call.from_user.id, CHANNEL_ID, COURSE_MESSAGE_IDS[1])

    await call.message.answer("🌍 Выбери свой часовой пояс:", reply_markup=kb_tz)
    await call.answer()

# ---------------- TZ ----------------
@dp.callback_query(lambda c: c.data.startswith("tz_"))
async def set_timezone(call: types.CallbackQuery):
    tz = call.data.split("_", 1)[1]
    update_user(call.from_user.id, timezone=tz)

    await call.message.answer("⏰ Выбери время уведомлений:", reply_markup=kb_time)
    await call.answer()

# ---------------- TIME ----------------
@dp.callback_query(lambda c: c.data.startswith("time_"))
async def set_time(call: types.CallbackQuery):
    hour = int(call.data.split("_")[1])
    update_user(call.from_user.id, notify_hour=hour, is_active=1)

    await call.message.answer("✅ Курс запущен!", reply_markup=kb_menu)
    await call.answer()

# ---------------- DAILY ----------------
async def daily_checker():
    users = get_users()
    
    for uid, day, hour, tz_name, last_sent in users:
        tz = TIMEZONES.get(tz_name, pytz.timezone("Europe/Berlin"))
        now_local = datetime.now(tz)
        today_str = now_local.strftime("%Y-%m-%d")

        # ✅ Окно срабатывания: с XX:00 до XX:09 (защита от лагов интернета/сервера)
        if now_local.hour == hour and now_local.minute < 10 and last_sent != today_str:
            
            # 🎉 Курс завершён
            if day >= 41:
                update_user(uid, is_active=0)
                try: await bot.send_message(uid, "🎉 Курс завершён!")
                except: pass
                continue  # Переходим к следующему пользователю

            # 📦 Отправляем задание
            msg_index = day + 2
            try:
                await bot.copy_message(uid, CHANNEL_ID, COURSE_MESSAGE_IDS[msg_index])
                # ⬆️ Обновляем день И фиксируем, что за сегодня уже отправили
                update_user(uid, current_day=day + 1, last_sent_date=today_str)
                logging.info(f"✅ День {day+1} отправлен {uid} в {now_local.strftime('%H:%M')}")
            except Exception as e:
                logging.error(f"Ошибка отправки {uid}: {e}")
                

        elif day >= 41:
            update_user(uid, is_active=0)
            await bot.send_message(uid, "🎉 Курс завершён!")

# ---------------- RUN ----------------
async def main():
    init_db()

    scheduler.add_job(daily_checker, IntervalTrigger(minutes=1))
    scheduler.start()

    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

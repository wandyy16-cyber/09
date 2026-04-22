import asyncio
import sqlite3
import secrets
import string
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.bot import DefaultBotProperties

# ===== НАСТРОЙКИ =====
API_TOKEN = '8413380142:AAGqbQxT3dMyQFApJLLSWrpewVoX_nudjOc'  # НОВЫЙ ТОКЕН
ADMIN_ID = 6938587500

bot = Bot(token=API_TOKEN, default=DefaultBotProperties())
dp = Dispatcher()

# База данных (НЕ УДАЛЯЕМ старую, чтобы сохранить ссылки!)
conn = sqlite3.connect('anonymous_bot.db', check_same_thread=False)
cursor = conn.cursor()

# Таблица пользователей
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        secret_key TEXT UNIQUE,
        created_at TEXT
    )
''')

# Таблица сообщений для пользователей
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

# Таблица для логов админа
cursor.execute('''
    CREATE TABLE IF NOT EXISTS admin_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_user_id INTEGER,
        from_name TEXT,
        from_username TEXT,
        to_user_id INTEGER,
        to_name TEXT,
        to_username TEXT,
        message_text TEXT,
        timestamp TEXT
    )
''')

# Временная таблица для контекста
cursor.execute('''
    CREATE TABLE IF NOT EXISTS temp_context (
        user_id INTEGER PRIMARY KEY,
        target_id INTEGER,
        reply_to_message_id INTEGER
    )
''')

conn.commit()
print("✅ База данных готова (постоянные ключи пользователей сохранены)")

def generate_secret_key():
    """Генерирует уникальный секретный ключ"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(16))

def generate_reply_token():
    """Генерирует уникальный токен для ответа"""
    return secrets.token_urlsafe(16)

def get_user_by_secret(secret_key):
    """Находит пользователя по секретному ключу (навсегда)"""
    cursor.execute('SELECT user_id, full_name FROM users WHERE secret_key = ?', (secret_key,))
    return cursor.fetchone()

def get_user_secret_key(user_id):
    """Получает секретный ключ пользователя (существующий или создает новый ОДИН РАЗ)"""
    cursor.execute('SELECT secret_key FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    
    if result:
        # Ключ уже есть - возвращаем его (НИЧЕГО НЕ МЕНЯЕМ)
        return result[0]
    else:
        # Новый пользователь - создаем ключ (ОДИН РАЗ НАВСЕГДА)
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

    # Проверяем, не передан ли секретный ключ (переход по ссылке)
    args = message.text.split()
    if len(args) > 1:
        secret_key = args[1]
        # Это переход по ссылке для отправки сообщения
        target_user = get_user_by_secret(secret_key)

        if target_user:
            # Сохраняем в контексте, что пользователь хочет написать
            cursor.execute('''
                INSERT OR REPLACE INTO temp_context (user_id, target_id)
                VALUES (?, ?)
            ''', (user_id, target_user[0]))
            conn.commit()

            await message.answer(
                f"📝 Вы хотите написать анонимное сообщение!\n\n"
                f"Просто отправьте мне сообщение, и оно будет доставлено анонимно.\n\n"
                f"❌ Для отмены отправьте /cancel"
            )
            return
        else:
            await message.answer("❌ Неверная или устаревшая ссылка!\n\n"
                               "💡 Убедитесь, что вы скопировали полную ссылку.")
            return

    # Обновляем информацию о пользователе (username, full_name могут измениться)
    cursor.execute('''
        UPDATE users 
        SET username = ?, full_name = ? 
        WHERE user_id = ?
    ''', (username, full_name, user_id))
    conn.commit()
    
    # Получаем или создаем секретный ключ (ОДИН РАЗ НАВСЕГДА)
    secret_key = get_user_secret_key(user_id)

    # Показываем главное меню
    bot_username = (await bot.get_me()).username
    anonymous_link = f"https://t.me/{bot_username}?start={secret_key}"

    await message.answer(
        f"👋 Привет, {full_name}!\n\n"
        f"✅ Твой профиль создан!\n\n"
        f"🔗 Твоя ПОСТОЯННАЯ анонимная ссылка:\n"
        f"`{anonymous_link}`\n\n"
        f"⚠️ ВАЖНО: Эта ссылка НИКОГДА НЕ ИЗМЕНИТСЯ!\n"
        f"Сохрани её и делись с друзьями.\n\n"
        f"📊 Команды:\n"
        f"/start - Показать мою ссылку\n"
        f"/messages - Мои сообщения\n"
        f"/stats - Моя статистика",
        parse_mode="Markdown"
    )

@dp.message(Command('cancel'))
async def cancel(message: Message):
    cursor.execute('DELETE FROM temp_context WHERE user_id = ?', (message.from_user.id,))
    conn.commit()
    await message.answer("❌ Отправка сообщения отменена!")

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
        await message.answer("📭 У вас нет сообщений.\n\n"
                           "💡 Поделитесь своей анонимной ссылкой (команда /start), чтобы получать сообщения!")
        return

    for msg in messages:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="💬 Ответить анонимно", callback_data=f"reply_{msg[0]}_{msg[4]}"),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_{msg[0]}")
            ]
        ])
        
        await message.answer(
            f"📨 *Анонимное сообщение:*\n\n{msg[2]}\n\n🕐 {msg[3]}",
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
        f"📨 Всего сообщений: {total}\n"
        f"🆕 Непрочитанных: {unread}",
        parse_mode="Markdown"
    )

@dp.message(Command('antihide'))
async def antihide(message: Message):
    """Команда для админа - показывает ВСЕ сообщения"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас нет доступа к этой команде! Только для админа.")
        return

    cursor.execute('''
        SELECT id, from_name, from_username, to_name, to_username, message_text, timestamp
        FROM admin_logs 
        ORDER BY id DESC 
        LIMIT 50
    ''')
    all_messages = cursor.fetchall()

    if not all_messages:
        await message.answer("📭 Пока нет ни одного сообщения.")
        return

    for msg in all_messages:
        text = (
            f"🔍 *ВСЕ СООБЩЕНИЯ* 🔍\n\n"
            f"*От:* {msg[1]}\n"
            f"*Юзернейм:* @{msg[2] if msg[2] else 'нет'}\n"
            f"*Кому:* {msg[3]}\n"
            f"*Юзернейм:* @{msg[4] if msg[4] else 'нет'}\n"
            f"*Сообщение:* {msg[5]}\n"
            f"*Время:* {msg[6]}\n"
            f"─" * 30
        )
        await message.answer(text, parse_mode="Markdown")

    cursor.execute('SELECT COUNT(*) FROM admin_logs')
    total = cursor.fetchone()[0]
    await message.answer(f"📊 *Всего сообщений в боте:* {total}", parse_mode="Markdown")

@dp.message(Command('test'))
async def test(message: Message):
    await message.answer("✅ Бот работает!\n\n"
                        "🔗 Ссылки пользователей ПОСТОЯННЫЕ и не меняются после перезапуска!\n"
                        "")

@dp.callback_query()
async def handle_callback(callback: types.CallbackQuery):
    if callback.data.startswith("delete_"):
        msg_id = int(callback.data.split("_")[1])
        cursor.execute('DELETE FROM messages WHERE id = ?', (msg_id,))
        conn.commit()
        await callback.message.answer("✅ Сообщение удалено.")
        await callback.answer()
    
    elif callback.data.startswith("reply_"):
        parts = callback.data.split("_")
        message_id = int(parts[1])
        reply_token = parts[2]
        
        cursor.execute('SELECT from_user_id, to_user_id FROM messages WHERE id = ?', (message_id,))
        original_msg = cursor.fetchone()
        
        if original_msg:
            from_user_id = original_msg[0]
            
            cursor.execute('''
                INSERT OR REPLACE INTO temp_context (user_id, target_id, reply_to_message_id)
                VALUES (?, ?, ?)
            ''', (callback.from_user.id, from_user_id, message_id))
            conn.commit()
            
            await callback.message.answer(
                f"💬 *Вы отвечаете анонимно*\n\n"
                f"Отправьте ваше сообщение, и оно будет доставлено анонимно.\n\n"
                f"❌ Для отмены отправьте /cancel",
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
            
            reply_token = generate_reply_token()
            
            cursor.execute('''
                INSERT INTO messages (from_user_id, to_user_id, message_text, timestamp, reply_token)
                VALUES (?, ?, ?, ?, ?)
            ''', (from_user_id, to_user_id, message.text, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), reply_token))
            
            msg_id = cursor.lastrowid
            
            cursor.execute('''
                INSERT INTO admin_logs (from_user_id, from_name, from_username, to_user_id, to_name, to_username, message_text, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (from_user_id, from_name, from_username, to_user_id, to_name, to_username, message.text, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            conn.commit()
            
            reply_markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💬 Ответить", callback_data=f"reply_{msg_id}_{reply_token}")]
            ])
            
            try:
                if reply_to_msg_id:
                    await bot.send_message(
                        to_user_id,
                        f"📨 *Новый анонимный ответ!*\n\n"
                        f"*Сообщение:* {message.text}\n\n"
                        f"💡 Нажмите 'Ответить', чтобы продолжить диалог",
                        reply_markup=reply_markup,
                        parse_mode="Markdown"
                    )
                else:
                    await bot.send_message(
                        to_user_id,
                        f"📨 *Новое анонимное сообщение!*\n\n"
                        f"*Сообщение:* {message.text}\n\n"
                        f"💡 Нажмите 'Ответить', чтобы написать в ответ",
                        reply_markup=reply_markup,
                        parse_mode="Markdown"
                    )
            except Exception as e:
                print(f"Ошибка отправки: {e}")
            
            cursor.execute('DELETE FROM temp_context WHERE user_id = ?', (from_user_id,))
            conn.commit()
            
            await message.answer("✅ Ваше сообщение отправлено анонимно!")
            
            reply_info = " (ОТВЕТ НА СООБЩЕНИЕ)" if reply_to_msg_id else ""
            await bot.send_message(
                ADMIN_ID,
                f"📨 *НОВОЕ АНОНИМНОЕ СООБЩЕНИЕ{reply_info}!*\n\n"
                f"*От:* {from_name} (@{from_username if from_username else 'нет'})\n"
                f"*Кому:* {to_name} (@{to_username if to_username else 'нет'})\n"
                f"*Текст:* {message.text}\n"
                f"*Время:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"🔍 Используй /antihide для просмотра всех сообщений",
                parse_mode="Markdown"
            )
        else:
            await message.answer("❌ Ошибка: получатель не найден.")
    else:
        # Если нет контекста, показываем меню
        await start(message)

async def main():
    print("🤖 Бот запускается...")
    print(f"👤 Админ ID: {ADMIN_ID}")
    print(f"🤖 Бот ID: {API_TOKEN.split(':')[0]}")
    print("\n✅ Бот готов к работе!")
    print("\n📝 Команды:")
    print("   /start - Главное меню (показать ПОСТОЯННУЮ ссылку)")
    print("   /antihide - Показать ВСЕ сообщения (только админ)")
    print("   /messages - Мои сообщения")
    print("   /stats - Моя статистика")
    print("   /test - Проверка работы")
    print("\n🔗 ВАЖНО: Ссылки пользователей теперь ПОСТОЯННЫЕ и не меняются после перезапуска!")
    
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())

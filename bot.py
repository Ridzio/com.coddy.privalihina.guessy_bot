import os
import random
import sqlite3
import telebot
from dotenv import load_dotenv
import html

# Загружаем переменные из файла .env
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise SystemExit("Токен не найден. Создайте файл .env со строкой BOT_TOKEN=...")

bot = telebot.TeleBot(TOKEN)
DB_NAME = "/tmp/quiz_game.db"


def init_db():
    """Создает таблицу для хранения состояния игр, если её ещё нет."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS games (
                chat_id INTEGER PRIMARY KEY,
                stage TEXT,
                low INTEGER,
                high INTEGER,
                max_attempts INTEGER,
                tries INTEGER,
                secret INTEGER
            )
        """)
        conn.commit()


def get_game(chat_id):
    """Получает состояние игры из базы данных."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT stage, low, high, max_attempts, tries, secret FROM games WHERE chat_id = ?", (chat_id,))
        row = cursor.fetchone()
        if row:
            # 🌟 ЧЁТКО РАСКЛАДЫВАЕМ ЭЛЕМЕНТЫ СТРОКИ ПО ИНДЕКСАМ И ПРИВОДИМ К ТИПАМ
            return {
                "stage": str(row[0]),  # Текст стадии (строка)
                "low": int(row[1]) if row[1] is not None else None,
                "high": int(row[2]) if row[2] is not None else None,
                "max_attempts": int(row[3]) if row[3] is not None else None,
                "tries": int(row[4]) if row[4] is not None else None,
                "secret": int(row[5]) if row[5] is not None else None
            }
        return None


def save_game(chat_id, game):
    """Сохраняет или обновляет состояние игры в базе данных."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO games (chat_id, stage, low, high, max_attempts, tries, secret)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                stage=excluded.stage,
                low=excluded.low,
                high=excluded.high,
                max_attempts=excluded.max_attempts,
                tries=excluded.tries,
                secret=excluded.secret
        """, (chat_id, game.get("stage"), game.get("low"), game.get("high"), game.get("max_attempts"),
              game.get("tries"), game.get("secret")))
        conn.commit()


def delete_game(chat_id):
    """Удаляет игру из базы данных после окончания."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM games WHERE chat_id = ?", (chat_id,))
        conn.commit()


def parse_int(text):
    """Превращает текст в целое число или возвращает None."""
    try:
        return int(text.strip())
    except ValueError:
        return None


def get_user_mention(message):
    """Безопасно создает упоминание пользователя через HTML-разметку."""
    user = message.from_user
    if user and user.username:
        # Экранируем юзернейм на случай странных символов
        return f"@{html.escape(user.username)}"
    elif user and user.first_name:
        # Экранируем имя, чтобы символы вроде < > или * не ломали теги ссылки
        safe_name = html.escape(user.first_name)
        return f'<a href="tg://user?id={user.id}">{safe_name}</a>'
    return "Игрок"


def set_bot_commands():
    """Регистрирует подсказки команд в меню Telegram для ЛС и Групп."""
    commands = [
        telebot.types.BotCommand("start", "Перезапустить бота и показать справку"),
        telebot.types.BotCommand("play", "Начать новую игру в угадайку"),
        telebot.types.BotCommand("stop", "Сдаться, узнать число и сбросить игру"),
        telebot.types.BotCommand("help", "Показать правила игры и список команд")
    ]
    bot.set_my_commands(commands, scope=telebot.types.BotCommandScopeAllPrivateChats())
    bot.set_my_commands(commands, scope=telebot.types.BotCommandScopeAllGroupChats())


@bot.message_handler(commands=["start", "help"])
def start(message):
    bot.send_message(
        message.chat.id,
        "Привет! Я загадываю число, а ты угадываешь 🎲\n\n"
        "Команды:\n"
        "/play — начать новую игру\n"
        "/stop — сдаться и узнать число\n"
        "/help — показать это сообщение",
        message_thread_id=message.message_thread_id
    )


@bot.message_handler(commands=["play"])
def play(message):
    chat_id = message.chat.id
    save_game(chat_id, {"stage": "range"})
    bot.send_message(
        chat_id,
        "Введи диапазон двумя числами через пробел.\nНапример: 1 100",
        message_thread_id=message.message_thread_id
    )


@bot.message_handler(commands=["stop"])
def stop(message):
    chat_id = message.chat.id
    game = get_game(chat_id)
    if game and game["stage"] == "playing":
        delete_game(chat_id)
        bot.send_message(
            chat_id,
            f"Игра остановлена. Моё число было {game['secret']}.\n"
            "Новая игра: /play",
            message_thread_id=message.message_thread_id
        )
    else:
        bot.send_message(
            chat_id,
            "Сейчас нет активной игры. Начать: /play",
            message_thread_id=message.message_thread_id
        )


@bot.message_handler(content_types=["text"])
def handle_text(message):
    chat_id = message.chat.id
    game = get_game(chat_id)

    if game is None:
        # Если игра в группе не запущена, тихо молчим, чтобы не спамить во флудилке
        return

    # --- Этап 1: ввод диапазона ---
    if game["stage"] == "range":
        parts = message.text.split()
        if len(parts) != 2:
            bot.send_message(
                chat_id,
                "Нужно ровно два числа через пробел, например: 1 100",
                message_thread_id=message.message_thread_id
            )
            return

        low, high = parse_int(parts[0]), parse_int(parts[1])

        # Safe check (Убираем предупреждение PyCharm): проверяем, что оба числа успешно распознались
        if low is None or high is None:
            bot.send_message(
                chat_id,
                "Нужно ввести именно целые числа через пробел! Попробуй ещё раз.",
                message_thread_id=message.message_thread_id
            )
            return

        if low >= high:
            bot.send_message(
                chat_id,
                "Первое число должно быть меньше второго. Попробуй ещё раз.",
                message_thread_id=message.message_thread_id
            )
            return

        game["low"] = low
        game["high"] = high
        game["stage"] = "attempts"
        save_game(chat_id, game)
        bot.send_message(
            chat_id,
            "Сколько попыток даём всей группе? Введи число, например: 7",
            message_thread_id=message.message_thread_id
        )
        return

    # --- Этап 2: ввод количества попыток ---
    if game["stage"] == "attempts":
        max_attempts = parse_int(message.text)
        if max_attempts is None or max_attempts < 1:
            bot.send_message(
                chat_id,
                "Нужно целое число больше нуля, например: 7",
                message_thread_id=message.message_thread_id
            )
            return

        game["max_attempts"] = max_attempts
        game["tries"] = 0
        game["secret"] = random.randint(game["low"], game["high"])
        game["stage"] = "playing"
        save_game(chat_id, game)
        bot.send_message(
            chat_id,
            f"🎯 Игра началась для всей группы!\n"
            f"Я загадал число от {game['low']} до {game['high']}.\n"
            f"У вас {max_attempts} общих попыток. Угадывайте вместе!",
            message_thread_id=message.message_thread_id
        )
        return

    # --- Этап 3: сама игра ---
    guess = parse_int(message.text)
    if guess is None:
        return  # Если прислали не число во время игры, просто игнорируем флуд

    game["tries"] += 1
    secret = game["secret"]
    left = game["max_attempts"] - game["tries"]

    # Мгновенно фиксируем и сохраняем ход в базу данных, чтобы не терять сообщения от игроков
    save_game(chat_id, game)

    user_mention = get_user_mention(message)

    if guess == secret:
        bot.send_message(
            chat_id,
            f"🎉 {user_mention}, ты угадал число группы! Моё число было {secret}.\n"
            f"Всего попыток потрачено: {game['tries']}.\n"
            "Сыграем ещё? /play",
            parse_mode="HTML",  # 🌟 ЗАМЕНИЛИ НА HTML
            message_thread_id=message.message_thread_id
        )
        delete_game(chat_id)
    elif left <= 0:
        bot.send_message(
            chat_id,
            f"Общие попытки закончились 😢 {user_mention}, моё число было {secret}.\n"
            "Попробуете ещё раз вместе? /play",
            parse_mode="HTML",  # 🌟 ЗАМЕНИЛИ НА HTML
            message_thread_id=message.message_thread_id
        )
        delete_game(chat_id)
    else:
        hint = "больше" if guess < secret else "меньше"
        bot.send_message(
            chat_id,
            f"🎲 {user_mention}, моё число {hint}. Осталось общих попыток: {left}.",
            parse_mode="HTML",  # 🌟 ЗАМЕНИЛИ НА HTML
            message_thread_id=message.message_thread_id
        )

if __name__ == "__main__":
    init_db()  # Обязательно инициализируем БД перед запуском
    set_bot_commands()  # Накатываем подсказки команд для ЛС и Групп
    print("Бот запущен с поддержкой базы данных...")
    bot.infinity_polling()
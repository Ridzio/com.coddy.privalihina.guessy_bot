import os
import random
import sqlite3
import telebot
from dotenv import load_dotenv

# Загружаем переменные из файла .env
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise SystemExit("Токен не найден. Создайте файл .env со строкой BOT_TOKEN=...")

bot = telebot.TeleBot(TOKEN)
DB_NAME = "quiz_game.db"


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
            return {
                "stage": row[0],
                "low": row[1],
                "high": row[2],
                "max_attempts": row[3],
                "tries": row[4],
                "secret": row[5]
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
        """, (chat_id, game.get("stage"), game.get("low"), game.get("high"), game.get("max_attempts"), game.get("tries"), game.get("secret")))
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


@bot.message_handler(commands=["start", "help"])
def start(message):
    bot.send_message(
        message.chat.id,
        "Привет! Я загадываю число, а ты угадываешь 🎲\n\n"
        "Команды:\n"
        "/play — начать новую игру\n"
        "/stop — сдаться и узнать число\n"
        "/help — показать это сообщение",
    )


@bot.message_handler(commands=["play"])
def play(message):
    chat_id = message.chat.id
    save_game(chat_id, {"stage": "range"})
    bot.send_message(
        chat_id,
        "Введи диапазон двумя числами через пробел.\nНапример: 1 100",
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
        )
    else:
        bot.send_message(chat_id, "Сейчас нет активной игры. Начать: /play")


@bot.message_handler(content_types=["text"])
def handle_text(message):
    chat_id = message.chat.id
    game = get_game(chat_id)

    if game is None:
        bot.send_message(chat_id, "Чтобы сыграть, напиши /play")
        return

    # --- Этап 1: ввод диапазона ---
    if game["stage"] == "range":
        parts = message.text.split()
        if len(parts) != 2 or parse_int(parts[0]) is None or parse_int(parts[1]) is None:
            bot.send_message(chat_id, "Нужно два числа через пробел, например: 1 100")
            return

        low, high = parse_int(parts[0]), parse_int(parts[1])
        if low >= high:
            bot.send_message(chat_id, "Первое число должно быть меньше второго. Попробуй ещё раз.")
            return

        game["low"] = low
        game["high"] = high
        game["stage"] = "attempts"
        save_game(chat_id, game)
        bot.send_message(chat_id, "Сколько попыток даём? Введи число, например: 7")
        return

    # --- Этап 2: ввод количества попыток ---
    if game["stage"] == "attempts":
        max_attempts = parse_int(message.text)
        if max_attempts is None or max_attempts < 1:
            bot.send_message(chat_id, "Нужно целое число больше нуля, например: 7")
            return

        game["max_attempts"] = max_attempts
        game["tries"] = 0
        game["secret"] = random.randint(game["low"], game["high"])
        game["stage"] = "playing"
        save_game(chat_id, game)
        bot.send_message(
            chat_id,
            f"Я загадал число от {game['low']} до {game['high']}.\n"
            f"У тебя {max_attempts} попыток. Угадывай!",
        )
        return

    # --- Этап 3: сама игра ---
    guess = parse_int(message.text)
    if guess is None:
        bot.send_message(chat_id, "Пришли число 🙂")
        return

    game["tries"] += 1
    secret = game["secret"]
    left = game["max_attempts"] - game["tries"]

    if guess == secret:
        bot.send_message(
            chat_id,
            f"🎉 Ты угадал! Моё число {secret}.\n"
            f"Попыток потрачено: {game['tries']}.\n"
            "Сыграем ещё? /play",
        )
        delete_game(chat_id)
    elif left == 0:
        bot.send_message(
            chat_id,
            f"Попытки закончились 😢 Моё число было {secret}.\n"
            "Попробуешь ещё раз? /play",
        )
        delete_game(chat_id)
    else:
        hint = "больше" if guess < secret else "меньше"
        save_game(chat_id, game)
        bot.send_message(
            chat_id,
            f"Моё число {hint}. Осталось попыток: {left}.",
        )


if __name__ == "__main__":
    init_db()  # Обязательно инициализируем БД перед запуском
    print("Бот запущен с поддержкой базы данных...")
    bot.infinity_polling()
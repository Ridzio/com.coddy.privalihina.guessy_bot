import threading
import os
from bot import bot, init_db  # Добавили импорт init_db
from flask import Flask

app = Flask(__name__)


@app.route('/')
def home():
    return "Бот работает!"


def run_bot():
    print("Инициализация базы данных...")
    init_db()  # Создаем таблицы, если их нет
    print("Запуск бесконечного опроса Telegram...")
    bot.infinity_polling()


if __name__ == "__main__":
    # Запускаем бота в отдельном фоновом потоке
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # Запускаем веб-сервер Flask
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
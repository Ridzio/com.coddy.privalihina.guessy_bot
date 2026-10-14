from bot import bot
import threading
from flask import Flask

app = Flask(__name__)

@app.route('/')
def home():
    return "Бот работает!"

def run_bot():
    bot.infinity_polling()

# Запускаем бота в отдельном независимом потоке
threading.Thread(target=run_bot, daemon=True).start()
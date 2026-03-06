from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = 8671339317:AAGKQJd0LXGVOh-aJfqo3PIGhn76agzPb5o
# команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Бот работает 🚀")

# создание приложения
app = ApplicationBuilder().token(TOKEN).build()

# добавляем команду
app.add_handler(CommandHandler("start", start))

print("Бот запущен...")

# запуск
app.run_polling()
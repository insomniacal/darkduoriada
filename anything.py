from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "8671339317:AAGKQJd0LXGVOh-aJfqo3PIGhn76agzPb5o"
# команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Бот работает 🚀n/n")
 "Напиши /help чтобы увидеть список команд."
    )


# команда /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Список команд:\n\n"
        "/start — запустить бота\n"
        "/help — показать список команд"
    )


# создание приложения
app = ApplicationBuilder().token(TOKEN).build()

# обработчики команд
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))

print("Бот запущен...")

# запуск бота
app.run_polling()

# создание приложения
app = ApplicationBuilder().token(TOKEN).build()

# добавляем команду
app.add_handler(CommandHandler("start", start))

print("Бот запущен...")

# запуск
app.run_polling()
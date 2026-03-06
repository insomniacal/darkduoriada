from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "8671339317:AAGKQJd0LXGVOh-aJfqo3PIGhn76agzPb5o"

#/start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "здравствуйте, вас приветствует бот который может послать вас куда подальше а именно нахуй.\n\n"
        "Напиши /help дабы узнать список комманд для дальнейших действий"
    )

#/help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Список команд:\n\n"
        "/start — запустить бота\n"
        "/help — показать список команд"
    )

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))

print("Бот запущен...")

app.run_polling()
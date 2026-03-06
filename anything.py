from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
import os

TOKEN = "8671339317:AAGKQJd0LXGVOh-aJfqo3PIGhn76agzPb5o"

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("ВЕРГИЛИЙ И ДАНТЕ", callback_data="Casey Edwards - Bury the Light.mp3")],
        [InlineKeyboardButton("БЛЯДСКАЯ НАТУРА", callback_data="LoToR - Блядская натура.mp3")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Здравствуйте! Бот может отправлять музыку.\n\n"
        "Напиши /help, чтобы узнать список команд.",
        reply_markup=reply_markup
    )

# /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Список команд:\n\n"
        "/start — запустить бота\n"
        "/help — показать список команд"
    )

# обработка кнопок
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    file_name = query.data

    if os.path.exists(file_name):
        await query.message.reply_audio(open(file_name, "rb"))
    else:
        await query.message.reply_text(f"Файл '{file_name}' не найден!")

# регистрация команд (чтобы появлялись подсказки при /)
async def set_commands(app):
    commands = [
        BotCommand("start", "Запустить бота"),
        BotCommand("help", "Показать список команд"),
    ]
    await app.bot.set_my_commands(commands)

# создание приложения
app = ApplicationBuilder().token(TOKEN).build()

# добавляем обработчики
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CallbackQueryHandler(button))

# выполняем установку команд
app.post_init = set_commands

print("Бот запущен...")

# запуск
app.run_polling()
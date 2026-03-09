from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp
import os

TOKEN = "8671339317:AAGKQJd0LXGVOh-aJfqo3PIGhn76agzPb5o"

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Напиши название песни или любую фразу, "
        "и я постараюсь найти её в интернете и отправить аудио."
    )

# /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Просто напиши название песни, исполнителя или фразу из песни.\n"
        "Бот найдет и отправит первый результат с YouTube в mp3 формате."
    )

# поиск и отправка песни
async def search_song(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    await update.message.reply_text(f"Ищу песню по запросу: {query}... 🎵")

    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'outtmpl': 'song.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }

    try:
        # ytsearch: ищет видео по тексту, берёт первый результат
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch:{query}", download=True)['entries'][0]

        # отправка аудио пользователю
        await update.message.reply_audio(open("song.mp3", "rb"))

        # удаляем временный файл после отправки
        os.remove("song.mp3")

    except Exception as e:
        await update.message.reply_text(f"Не удалось найти песню: {e}")

# создаём приложение
app = ApplicationBuilder().token(TOKEN).build()

# обработчики
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_song))

print("Бот запущен...")
app.run_polling()
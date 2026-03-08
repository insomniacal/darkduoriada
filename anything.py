from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp
import os

TOKEN = "8671339317:AAGKQJd0LXGVOh-aJfqo3PIGhn76agzPb5o"

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 Музыкальный бот\n\n"
        "Напиши название песни или исполнителя. или пошел нахуй хуесос"
    )

# /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Как пользоваться:\n\n"
        "Просто отправь название песни.\n"
        "Бот найдёт её и отправит mp3 файл."
    )

# поиск и отправка песни
async def search_song(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.message.text.strip()

    msg = await update.message.reply_text("🔎 Ищу твое музло пидр ебучий...")

    try:
        # 1️⃣ ищем видео
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(f"ytsearch1:{query}", download=False)

        video = info['entries'][0]
        video_url = video['webpage_url']

        await msg.edit_text("⬇️ Скачиваю порно...")

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': 'song.%(ext)s',
            'quiet': True,

            'retries': 10,
            'fragment_retries': 10,
            'socket_timeout': 60,

            'concurrent_fragment_downloads': 3,
            'nocheckcertificate': True,

            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }

        # 2️⃣ скачиваем
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        # 3️⃣ отправляем
        if os.path.exists("song.mp3"):
            await update.message.reply_audio(open("song.mp3", "rb"))

            os.remove("song.mp3")

        else:
            await update.message.reply_text("❌ Ошибка: твоя мать шлюха а именно файл не найден.")

    except Exception as e:
        await update.message.reply_text(f"❌ Не удалось найти песню как и твою мертвую семью.\n{e}")

# запуск приложения
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_song))

print("Бот запущен...")

app.run_polling()
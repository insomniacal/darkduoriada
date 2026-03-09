from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor

TOKEN = "8671339317:AAGKQJd0LXGVOh-aJfqo3PIGhn76agzPb5o"  # Вставь свой токен сюда

executor = ThreadPoolExecutor(max_workers=4)

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Напиши название песни или исполнителя, и я пришлю mp3.\n\n"
        "🔍 Поиск идёт по YouTube, SoundCloud, Bandcamp и другим источникам."
    )

# /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 Просто напиши запрос, например:\n"
        "  • Название песни\n"
        "  • Исполнитель + название\n"
        "  • Фраза из песни\n\n"
        "Поддерживаемые источники:\n"
        "YouTube, SoundCloud, Bandcamp, Deezer и другие.\n\n"
        "⚡️ Поиск займёт 5–15 секунд."
    )

def download_song(query: str) -> dict | None:
    """Скачивает аудио синхронно — запускается в отдельном потоке."""

    # Пробуем источники по порядку: SoundCloud быстрее YouTube
    sources = [
        f"scsearch:{query}",     # SoundCloud — быстро, хорошее качество
        f"ytsearch:{query}",     # YouTube — резервный вариант
    ]

    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'outtmpl': f'song_{os.getpid()}.%(ext)s',  # уникальное имя файла
        'socket_timeout': 15,
        'retries': 2,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        # Берём только первый результат — быстрее
        'playlistend': 1,
        'noplaylist': True,
    }

    for source in sources:
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(source, download=True)
                entry = info['entries'][0] if 'entries' in info else info
                return {
                    'title': entry.get('title', query),
                    'duration': entry.get('duration', 0),
                    'uploader': entry.get('uploader', ''),
                    'source': entry.get('extractor', ''),
                }
        except Exception:
            continue  # пробуем следующий источник

    return None


async def search_song(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    msg = await update.message.reply_text(f"🔍 Ищу: *{query}*...", parse_mode="Markdown")

    loop = asyncio.get_event_loop()
    mp3_path = f"song_{os.getpid()}.mp3"

    try:
        # Запускаем скачивание в потоке, чтобы не блокировать бота
        result = await asyncio.wait_for(
            loop.run_in_executor(executor, download_song, query),
            timeout=60  # максимум 60 секунд
        )

        if result is None or not os.path.exists(mp3_path):
            await msg.edit_text("😔 Не удалось найти песню. Попробуй уточнить запрос.")
            return

        await msg.edit_text(
            f"✅ Нашёл: *{result['title']}*\n"
            f"👤 {result['uploader']}  •  🌐 {result['source']}\n"
            f"⏱️ {int(result['duration']) // 60}:{int(result['duration']) % 60:02d}\n\n"
            "📤 Отправляю...",
            parse_mode="Markdown"
        )

        with open(mp3_path, "rb") as audio_file:
            await update.message.reply_audio(
                audio=audio_file,
                title=result['title'],
                performer=result['uploader'],
            )

        await msg.delete()

    except asyncio.TimeoutError:
        await msg.edit_text("⏳ Слишком долго. Попробуй ещё раз или уточни запрос.")
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")
    finally:
        if os.path.exists(mp3_path):
            os.remove(mp3_path)


app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_song))

print("Бот запущен... ✅")
app.run_polling()
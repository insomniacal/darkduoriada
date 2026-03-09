from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp
import os
import asyncio
import re
from concurrent.futures import ThreadPoolExecutor

TOKEN = "8671339317:AAGKQJd0LXGVOh-aJfqo3PIGhn76agzPb5o"

executor = ThreadPoolExecutor(max_workers=4)

# Поддерживаемые домены для ссылок
URL_PATTERN = re.compile(
    r'https?://(www\.)?(youtube\.com|youtu\.be|tiktok\.com|pinterest\.com|pin\.it'
    r'|soundcloud\.com|open\.spotify\.com)',
    re.IGNORECASE
)

def is_url(text: str) -> bool:
    return bool(URL_PATTERN.search(text))

def extract_spotify_query(url: str) -> str | None:
    """Spotify не даёт скачивать — извлекаем название трека из URL для поиска на YouTube."""
    try:
        ydl_opts = {'quiet': True, 'no_warnings': True, 'skip_download': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get('title', '')
            artist = info.get('artist') or info.get('uploader', '')
            return f"{artist} {title}".strip() if title else None
    except Exception:
        return None

def download_song(query_or_url: str) -> dict | None:
    """Скачивает аудио синхронно — запускается в отдельном потоке."""

    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'outtmpl': f'song_{os.getpid()}.%(ext)s',
        'socket_timeout': 20,
        'retries': 2,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'playlistend': 1,
        'noplaylist': True,
    }

    # Если это Spotify — извлекаем название и ищем на YouTube
    if 'spotify.com' in query_or_url:
        spotify_query = extract_spotify_query(query_or_url)
        if spotify_query:
            sources = [f"ytsearch:{spotify_query}", f"scsearch:{spotify_query}"]
        else:
            return None

    # Pinterest — там нет аудио
    elif 'pinterest.com' in query_or_url or 'pin.it' in query_or_url:
        return {'error': 'pinterest'}

    # Прямые ссылки (YouTube, TikTok, SoundCloud)
    elif is_url(query_or_url):
        sources = [query_or_url]

    # Текстовый запрос — сначала SoundCloud (быстрее), потом YouTube
    else:
        sources = [
            f"scsearch:{query_or_url}",
            f"ytsearch:{query_or_url}",
        ]

    for source in sources:
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(source, download=True)
                entry = info['entries'][0] if 'entries' in info else info
                return {
                    'title': entry.get('title', query_or_url),
                    'duration': entry.get('duration', 0) or 0,
                    'uploader': entry.get('uploader', ''),
                    'source': entry.get('extractor', ''),
                }
        except Exception:
            continue

    return None


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    url_match = is_url(text)
    starts_with_find = text.lower().startswith("найти ")

    if not url_match and not starts_with_find:
        await update.message.reply_text(
            "💡 Чтобы найти песню, напиши:\n"
            "  • <b>найти</b> название песни\n"
            "  • Или просто пришли ссылку:\n"
            "    YouTube, TikTok, SoundCloud, Spotify\n\n"
            "<i>Пример: найти Imagine Dragons Believer</i>",
            parse_mode="HTML"
        )
        return

    if url_match:
        query = text
        display = "по ссылке"
    else:
        query = text[6:].strip()  # убираем "найти "
        display = f"<b>{query}</b>"

    msg = await update.message.reply_text(f"🔍 Ищу {display}...", parse_mode="HTML")

    loop = asyncio.get_event_loop()
    mp3_path = f"song_{os.getpid()}.mp3"
    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(executor, download_song, query),
            timeout=60
        )

        if result and result.get('error') == 'pinterest':
            await msg.edit_text(
                "📌 Pinterest не содержит аудио.\n"
                "Напиши название песни: <b>найти [название]</b>",
                parse_mode="HTML"
            )
            return

        if result is None or not os.path.exists(mp3_path):
            await msg.edit_text("😔 Не удалось найти песню. Попробуй уточнить запрос.")
            return

        duration = int(result['duration'])
        src = result['source'].lower().split(':')[0]
        source_label = {
            'youtube': '▶️ YouTube',
            'soundcloud': '🔊 SoundCloud',
            'tiktok': '🎵 TikTok',
        }.get(src, f"🌐 {result['source']}")

        await msg.edit_text(
            f"✅ Нашёл: <b>{result['title']}</b>\n"
            f"👤 {result['uploader']}  •  {source_label}\n"
            f"⏱ {duration // 60}:{duration % 60:02d}\n\n"
            "📤 Отправляю...",
            parse_mode="HTML"
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я музыкальный бот.\n\n"
        "🔍 <b>Поиск по названию:</b>\n"
        "  найти Imagine Dragons Believer\n\n"
        "🔗 <b>Поиск по ссылке:</b>\n"
        "  Просто пришли ссылку из:\n"
        "  ▶️ YouTube  •  🎵 TikTok\n"
        "  🔊 SoundCloud  •  🎧 Spotify\n\n"
        "📌 Pinterest — только картинки, аудио не поддерживается.",
        parse_mode="HTML"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 <b>Как пользоваться ботом:</b>\n\n"
        "1️⃣ Напиши <b>найти</b> + название:\n"
        "   <i>найти Coldplay Yellow</i>\n\n"
        "2️⃣ Или пришли ссылку:\n"
        "   • youtube.com/watch?v=...\n"
        "   • tiktok.com/@.../video/...\n"
        "   • soundcloud.com/...\n"
        "   • open.spotify.com/track/...\n\n"
        "⚡️ Поиск занимает 5–20 секунд.",
        parse_mode="HTML"
    )


app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("Бот запущен... ✅")
app.run_polling()